#!/usr/bin/env python3
"""
S3 Audit & Stage Reset Tool

Provides functionality to:
1. Audit actual S3 files vs metadata tracking
2. Reset stage status for videos
3. Verify data consistency

Usage:
    # Audit Stage 2 data
    python cli/audit_s3.py audit --stage stage_2_extract

    # Reset Stage 2 for all videos
    python cli/audit_s3.py reset --stage stage_2_extract

    # Reset Stage 2 for specific videos
    python cli/audit_s3.py reset --stage stage_2_extract --video-id youtube_abc123

    # Dry run (show what would be reset)
    python cli/audit_s3.py reset --stage stage_2_extract --dry-run
"""

import sys
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import setup_logging, get_logger

console = Console()
logger = get_logger(__name__)


def get_actual_s3_files(s3_storage: S3Storage, stage: str) -> Set[str]:
    """
    Get list of actual video IDs that have data in S3 for a given stage.

    Args:
        s3_storage: S3Storage instance
        stage: Stage name (e.g., 'stage_2_extract')

    Returns:
        Set of video IDs that have actual S3 files
    """
    video_ids = set()

    if stage == 'stage_2_extract':
        # List all files in stage2-extracted/new/ and stage2-extracted/stage3_processed/
        try:
            for prefix in ['stage2-extracted/new/', 'stage2-extracted/stage3_processed/']:
                paginator = s3_storage.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(
                    Bucket=s3_storage.bucket_name,
                    Prefix=prefix
                )

                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            key = obj['Key']
                            # Extract video ID from filename
                            # Format: stage2-extracted/new/youtube_video_ABC123_extracted.jsonl
                            if key.endswith('_extracted.jsonl'):
                                filename = key.split('/')[-1]
                                # Extract video ID: youtube_video_ABC123_extracted.jsonl -> ABC123
                                parts = filename.replace('youtube_video_', '').replace('_extracted.jsonl', '')
                                video_id = f"youtube_{parts}"
                                video_ids.add(video_id)

        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")

    elif stage == 'stage_1_crawl':
        # List all files in raw/new/ and raw/stage2_processed/
        try:
            import json
            for prefix in ['raw/new/', 'raw/stage2_processed/']:
                paginator = s3_storage.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(
                    Bucket=s3_storage.bucket_name,
                    Prefix=prefix
                )

                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            key = obj['Key']
                            # Format: raw/new/youtube_video_ABC123.jsonl
                            if key.endswith('.jsonl'):
                                filename = key.split('/')[-1]
                                # Extract video ID: youtube_video_ABC123.jsonl -> ABC123
                                parts = filename.replace('youtube_video_', '').replace('.jsonl', '')
                                video_id = f"youtube_{parts}"
                                video_ids.add(video_id)

        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")

    elif stage == 'stage_3_deduplicate':
        # List all files in stage2-extracted/stage3_extracted/
        # These are files that were consumed by Stage 3 (moved from new/)
        try:
            for prefix in ['stage2-extracted/stage3_extracted/', 'stage2-extracted/new/']:
                paginator = s3_storage.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(
                    Bucket=s3_storage.bucket_name,
                    Prefix=prefix
                )

                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            key = obj['Key']
                            # Extract video ID from filename
                            # Format: stage2-extracted/stage3_extracted/youtube_video_ABC123_extracted.jsonl
                            if key.endswith('_extracted.jsonl'):
                                filename = key.split('/')[-1]
                                # Extract video ID: youtube_video_ABC123_extracted.jsonl -> ABC123
                                parts = filename.replace('youtube_video_', '').replace('_extracted.jsonl', '')
                                video_id = f"youtube_{parts}"
                                video_ids.add(video_id)

        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")

    elif stage == 'stage_4_vectorize':
        # Stage 4 uses ChromaDB, not S3 files
        # Check vector database collections instead
        try:
            from src.vectordb.chromadb_client import ChromaDBClient

            chroma_client = ChromaDBClient.initialize_from_env()

            # Get all entity IDs from entities collection (use direct attribute access)
            entities_collection = chroma_client.entities_collection
            if entities_collection:
                # Get all entity IDs in the collection
                results = entities_collection.get()
                if results and 'ids' in results:
                    # Entity IDs in ChromaDB are in format: entity_id (e.g., ATT_001)
                    # But we need to track by video_id for metadata tracker
                    # We'll extract unique video IDs from metadata
                    for idx, entity_id in enumerate(results['ids']):
                        if results.get('metadatas') and idx < len(results['metadatas']):
                            metadata = results['metadatas'][idx]
                            # Extract video_ids from metadata
                            if 'video_ids' in metadata:
                                # video_ids is stored as comma-separated string
                                video_id_list = metadata['video_ids'].split(',')
                                video_ids.update(video_id_list)

        except Exception as e:
            logger.warning(f"Stage 4 uses ChromaDB - sync may not be applicable: {e}")

    return video_ids


def get_metadata_video_ids(tracker: MetadataTracker, stage: str, status: Optional[str] = None) -> Set[str]:
    """
    Get list of video IDs from metadata tracker for a given stage.

    Args:
        tracker: MetadataTracker instance
        stage: Stage name
        status: Optional status filter ('complete', 'failed', 'pending', etc.)

    Returns:
        Set of video IDs in metadata
    """
    video_ids = set()

    all_items = tracker.get_all_items()
    for content_id, content_data in all_items.items():
        stage_data = content_data.get('stages', {}).get(stage, {})
        stage_status = stage_data.get('status', 'not_started')

        if status:
            if stage_status == status:
                video_ids.add(content_id)
        else:
            video_ids.add(content_id)

    return video_ids


@click.group()
def cli():
    """S3 Audit & Stage Reset Tool"""
    setup_logging("INFO")


@cli.command()
@click.option('--stage', required=True, help='Stage name (e.g., stage_2_extract)')
@click.option('--show-missing', is_flag=True, help='Show videos missing in S3')
@click.option('--show-extra', is_flag=True, help='Show videos in S3 but not in metadata')
def audit(stage: str, show_missing: bool, show_extra: bool):
    """
    Audit actual S3 files vs metadata tracking.

    Compares what's actually stored in S3 with what the metadata tracker says.
    This helps identify discrepancies between actual data and tracking.

    Examples:
        # Audit Stage 2
        python cli/audit_s3.py audit --stage stage_2_extract

        # Show videos missing in S3
        python cli/audit_s3.py audit --stage stage_2_extract --show-missing
    """
    console.print()
    console.print(Panel.fit(
        f"[bold blue]S3 Audit: {stage}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    try:
        # Initialize
        s3_storage = S3Storage()
        tracker = MetadataTracker(s3_storage=s3_storage)
        tracker.load_from_s3()

        # Get actual S3 files
        console.print("[cyan]Scanning S3 bucket for actual files...[/cyan]")
        actual_s3_files = get_actual_s3_files(s3_storage, stage)

        # Get metadata status
        console.print("[cyan]Loading metadata tracker...[/cyan]")
        metadata_complete = get_metadata_video_ids(tracker, stage, status='complete')
        metadata_all = get_metadata_video_ids(tracker, stage)

        # Calculate differences
        missing_in_s3 = metadata_complete - actual_s3_files
        extra_in_s3 = actual_s3_files - metadata_all
        correct = actual_s3_files & metadata_complete

        console.print()

        # Summary table
        summary_table = Table(title="Audit Summary", box=box.ROUNDED)
        summary_table.add_column("Metric", style="cyan", width=40)
        summary_table.add_column("Count", justify="right", style="green", width=10)

        summary_table.add_row("Videos in S3 (actual files)", str(len(actual_s3_files)))
        summary_table.add_row("Videos in Metadata (complete)", str(len(metadata_complete)))
        summary_table.add_row("Videos in Metadata (all statuses)", str(len(metadata_all)))
        summary_table.add_row("", "")
        summary_table.add_row("✅ Correct (in both S3 and metadata)", str(len(correct)))
        summary_table.add_row("⚠️  Missing in S3 (metadata says complete)", str(len(missing_in_s3)), style="yellow")
        summary_table.add_row("⚠️  Extra in S3 (not in metadata)", str(len(extra_in_s3)), style="yellow")

        console.print(summary_table)
        console.print()

        # Show discrepancies
        if missing_in_s3:
            console.print(f"[yellow]⚠️  {len(missing_in_s3)} videos marked as complete in metadata but missing in S3[/yellow]")

            if show_missing:
                console.print("\n[yellow]Missing in S3:[/yellow]")
                for idx, video_id in enumerate(sorted(missing_in_s3)[:20], 1):
                    console.print(f"  {idx}. {video_id}")
                if len(missing_in_s3) > 20:
                    console.print(f"  ... and {len(missing_in_s3) - 20} more")

        if extra_in_s3:
            console.print(f"[yellow]⚠️  {len(extra_in_s3)} videos found in S3 but not tracked in metadata[/yellow]")

            if show_extra:
                console.print("\n[yellow]Extra in S3:[/yellow]")
                for idx, video_id in enumerate(sorted(extra_in_s3)[:20], 1):
                    console.print(f"  {idx}. {video_id}")
                if len(extra_in_s3) > 20:
                    console.print(f"  ... and {len(extra_in_s3) - 20} more")

        if not missing_in_s3 and not extra_in_s3:
            console.print("[green]✅ Perfect sync! S3 and metadata are consistent.[/green]")
        else:
            console.print()
            console.print("[yellow]💡 Tip: Use 'reset' command to fix metadata inconsistencies[/yellow]")

        console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"Audit error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option('--stage', required=True, help='Stage name to reset (e.g., stage_2_extract)')
@click.option('--video-id', multiple=True, help='Specific video ID(s) to reset (can specify multiple)')
@click.option('--all', 'reset_all', is_flag=True, help='Reset all videos for this stage')
@click.option('--status', type=click.Choice(['complete', 'failed', 'pending', 'running']),
              help='Reset only videos with specific status')
@click.option('--dry-run', is_flag=True, help='Show what would be reset without actually resetting')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
def reset(stage: str, video_id: tuple, reset_all: bool, status: Optional[str], dry_run: bool, yes: bool):
    """
    Reset stage status for videos.

    This sets the stage status back to 'not_started', allowing reprocessing.
    Use this when you need to rerun a stage for specific videos.

    Examples:
        # Reset Stage 2 for specific video
        python cli/audit_s3.py reset --stage stage_2_extract --video-id youtube_abc123

        # Reset Stage 2 for multiple videos
        python cli/audit_s3.py reset --stage stage_2_extract --video-id youtube_abc123 --video-id youtube_def456

        # Reset all videos marked as complete in Stage 2
        python cli/audit_s3.py reset --stage stage_2_extract --status complete --all

        # Dry run to see what would be reset
        python cli/audit_s3.py reset --stage stage_2_extract --all --dry-run
    """
    console.print()
    console.print(Panel.fit(
        f"[bold blue]Reset Stage: {stage}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    try:
        # Initialize
        s3_storage = S3Storage()
        tracker = MetadataTracker(s3_storage=s3_storage)
        tracker.load_from_s3()

        # Determine which videos to reset
        videos_to_reset = []

        if video_id:
            # Specific video IDs provided
            for vid in video_id:
                if tracker.content_exists(vid):
                    videos_to_reset.append(vid)
                else:
                    console.print(f"[yellow]⚠️  Video not found in metadata: {vid}[/yellow]")

        elif reset_all:
            # Reset all videos for this stage
            all_items = tracker.get_all_items()
            for content_id, content_data in all_items.items():
                stage_data = content_data.get('stages', {}).get(stage, {})
                stage_status = stage_data.get('status', 'not_started')

                # Filter by status if specified
                if status:
                    if stage_status == status:
                        videos_to_reset.append(content_id)
                else:
                    # Reset any non-not_started status
                    if stage_status != 'not_started':
                        videos_to_reset.append(content_id)

        else:
            console.print("[red]Error: Must specify either --video-id or --all[/red]\n")
            sys.exit(1)

        if not videos_to_reset:
            console.print("[yellow]No videos found to reset[/yellow]\n")
            return

        # Show what will be reset
        console.print(f"[cyan]Found {len(videos_to_reset)} videos to reset:[/cyan]\n")

        # Group by current status
        status_groups = {}
        for content_id in videos_to_reset:
            info = tracker.get_content_info(content_id)
            current_status = info['stages'][stage]['status']
            if current_status not in status_groups:
                status_groups[current_status] = []
            status_groups[current_status].append(content_id)

        for status_name, video_list in sorted(status_groups.items()):
            console.print(f"  {status_name}: {len(video_list)} videos")

        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
            console.print("Videos that would be reset:")
            for idx, vid in enumerate(sorted(videos_to_reset)[:10], 1):
                info = tracker.get_content_info(vid)
                current_status = info['stages'][stage]['status']
                console.print(f"  {idx}. {vid} (current: {current_status})")
            if len(videos_to_reset) > 10:
                console.print(f"  ... and {len(videos_to_reset) - 10} more")
            console.print()
            return

        # Confirm before resetting
        if not yes:
            console.print(f"[yellow]⚠️  This will reset {len(videos_to_reset)} videos to 'not_started' status[/yellow]")
            console.print(f"[yellow]   Stage: {stage}[/yellow]")
            console.print()

            confirm = click.confirm("Are you sure you want to continue?", default=False)
            if not confirm:
                console.print("[yellow]Reset cancelled[/yellow]\n")
                return

        # Perform reset
        console.print(f"\n[cyan]Resetting {len(videos_to_reset)} videos...[/cyan]\n")

        reset_count = 0
        for content_id in videos_to_reset:
            try:
                # Reset the stage
                content_data = tracker._cache.get(content_id)
                if content_data:
                    stage_data = content_data.get('stages', {}).get(stage, {})

                    # Reset to not_started
                    stage_data['status'] = 'not_started'
                    stage_data['started_at'] = None
                    stage_data['completed_at'] = None
                    stage_data['duration_seconds'] = None
                    stage_data['s3_paths'] = []
                    stage_data['metadata'] = {}
                    stage_data['error'] = None
                    stage_data['retry_count'] = 0

                    # Update last_updated
                    content_data['last_updated'] = datetime.utcnow().isoformat() + 'Z'

                    # Update pipeline status
                    if stage == 'stage_2_extract':
                        content_data['pipeline_status'] = 'stage_2_pending'
                    elif stage == 'stage_1_crawl':
                        content_data['pipeline_status'] = 'stage_1_pending'

                    reset_count += 1

            except Exception as e:
                console.print(f"[red]Error resetting {content_id}: {e}[/red]")
                logger.error(f"Reset error for {content_id}: {e}")

        # Save to S3
        console.print(f"[cyan]Saving changes to S3...[/cyan]")
        tracker.save_to_s3()

        console.print()
        console.print(f"[green]✅ Successfully reset {reset_count} videos to 'not_started'[/green]")
        console.print(f"[green]   You can now reprocess them using the appropriate stage command[/green]")
        console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"Reset error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option('--stage', required=True, help='Stage name (e.g., stage_2_extract)')
def sync(stage: str):
    """
    Sync metadata with actual S3 files.

    For videos that have files in S3 but metadata shows 'not_started',
    this will update metadata to match reality.

    Examples:
        # Sync Stage 2 metadata with S3
        python cli/audit_s3.py sync --stage stage_2_extract
    """
    console.print()
    console.print(Panel.fit(
        f"[bold blue]Sync Metadata with S3: {stage}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    try:
        # Initialize
        s3_storage = S3Storage()
        tracker = MetadataTracker(s3_storage=s3_storage)
        tracker.load_from_s3()

        # Get actual S3 files
        console.print("[cyan]Scanning S3 bucket...[/cyan]")
        actual_s3_files = get_actual_s3_files(s3_storage, stage)

        # Get metadata
        console.print("[cyan]Checking metadata...[/cyan]")

        # Find videos in S3 but not marked as complete
        to_update = []
        for video_id in actual_s3_files:
            if tracker.content_exists(video_id):
                info = tracker.get_content_info(video_id)
                stage_status = info['stages'][stage]['status']

                if stage_status != 'complete':
                    to_update.append(video_id)

        if not to_update:
            console.print("[green]✅ Metadata is already in sync with S3[/green]\n")
            return

        console.print(f"\n[yellow]Found {len(to_update)} videos to update[/yellow]\n")

        # Update metadata
        for content_id in to_update:
            # This is a simplified update - in real scenario you'd want to
            # parse the S3 file and extract actual metadata
            content_data = tracker._cache.get(content_id)
            if content_data:
                stage_data = content_data.get('stages', {}).get(stage, {})
                stage_data['status'] = 'complete'
                console.print(f"  Updated: {content_id}")

        # Save
        tracker.save_to_s3()

        console.print()
        console.print(f"[green]✅ Updated {len(to_update)} videos in metadata[/green]\n")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"Sync error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
