#!/usr/bin/env python3
"""
One-Time Language Migration Script

Reads language from raw YouTube video JSONL files in S3 and updates
the MetadataTracker with the correct language for each video.

This script is needed for videos crawled before the language detection
fix was implemented.

Usage:
    python migrate_languages.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import setup_logging, get_logger


console = Console()
logger = get_logger(__name__)


def migrate_languages():
    """
    Migrate language data from raw JSONL files to MetadataTracker.
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Language Migration[/bold cyan]\n"
        "Updating MetadataTracker with languages from raw JSONL files",
        border_style="cyan"
    ))
    console.print()

    setup_logging("INFO")

    try:
        # Initialize S3 and tracker
        storage = S3Storage()
        tracker = MetadataTracker(storage)

        # Get all content with completed stage 1
        content_to_migrate = []
        for content_id, content_data in tracker._cache.items():
            stage_1 = content_data['stages']['stage_1_crawl']
            if stage_1['status'] == 'complete':
                # Check if language is already in metadata
                stage_metadata = stage_1.get('metadata', {})
                if 'language' not in stage_metadata or stage_metadata.get('language') == 'unknown':
                    content_to_migrate.append({
                        'content_id': content_id,
                        'stage_1': stage_1
                    })

        if not content_to_migrate:
            console.print("[green]✓ All videos already have language metadata[/green]\n")
            return

        console.print(f"[cyan]Found {len(content_to_migrate)} videos to migrate[/cyan]\n")

        # Migrate languages
        updated_count = 0
        failed_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Migrating languages...",
                total=len(content_to_migrate)
            )

            for item in content_to_migrate:
                content_id = item['content_id']
                stage_1 = item['stage_1']

                try:
                    # Get S3 paths from stage 1
                    s3_paths = stage_1.get('s3_paths', [])
                    if not s3_paths:
                        logger.warning(f"No S3 paths found for {content_id}")
                        failed_count += 1
                        progress.advance(task)
                        continue

                    # Download the JSONL file
                    s3_path = s3_paths[0]  # Use first path
                    data = storage.download_jsonl(s3_path)

                    if not data:
                        logger.warning(f"Could not download data for {content_id}")
                        failed_count += 1
                        progress.advance(task)
                        continue

                    # Find the video data for this content_id
                    video_data = None
                    for video in data:
                        # Extract video ID from content_id (youtube_VIDEO_ID)
                        video_id = content_id.replace('youtube_', '')
                        if video.get('source_id') == video_id or video.get('source_url', '').endswith(video_id):
                            video_data = video
                            break

                    if not video_data:
                        logger.warning(f"Could not find video data for {content_id} in {s3_path}")
                        failed_count += 1
                        progress.advance(task)
                        continue

                    # Get language from video data
                    language = video_data.get('language', 'unknown')

                    if language == 'unknown':
                        logger.warning(f"No language found for {content_id}")
                        failed_count += 1
                        progress.advance(task)
                        continue

                    # Update stage metadata with language
                    stage_metadata = stage_1.get('metadata', {})
                    stage_metadata['language'] = language

                    # Update the tracker cache
                    tracker._cache[content_id]['stages']['stage_1_crawl']['metadata'] = stage_metadata

                    updated_count += 1
                    logger.debug(f"Updated {content_id} with language: {language}")

                except Exception as e:
                    logger.error(f"Error migrating {content_id}: {e}")
                    failed_count += 1

                progress.advance(task)

        # Save updated metadata to S3
        if updated_count > 0:
            console.print("\n[cyan]Saving updated metadata to S3...[/cyan]")
            tracker.save_to_s3()
            console.print(f"[green]✓ Saved updated metadata to S3[/green]\n")

        # Summary
        console.print("=" * 70)
        console.print(f"[bold]Migration Summary[/bold]")
        console.print("=" * 70)
        console.print(f"[green]✓ Updated: {updated_count} videos[/green]")
        if failed_count > 0:
            console.print(f"[yellow]⚠ Failed: {failed_count} videos[/yellow]")
        console.print(f"[cyan]Total: {len(content_to_migrate)} videos[/cyan]")
        console.print("=" * 70)
        console.print()

        if updated_count > 0:
            console.print("[green]✓ Language migration completed successfully![/green]")
            console.print("\n[cyan]You can now run:[/cyan] ./crawl.sh languages\n")
        else:
            console.print("[yellow]⚠ No videos were updated[/yellow]\n")

    except Exception as e:
        console.print(f"[red]✗ Migration failed: {e}[/red]\n")
        logger.error(f"Migration error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    migrate_languages()
