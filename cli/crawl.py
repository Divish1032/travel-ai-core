#!/usr/bin/env python3
"""
Command-line interface for the Travel AI YouTube crawler.

Provides commands to crawl YouTube videos, save to local storage or S3,
and validate existing data files.

Usage:
    # Crawl videos from URLs file
    python cli/crawl.py youtube --input urls.txt --output local
    python cli/crawl.py youtube --input urls.txt --output s3 --limit 10

    # Validate existing JSONL file
    python cli/crawl.py validate --input data/raw/batch.jsonl

    # Dry run (test without crawling)
    python cli/crawl.py youtube --input urls.txt --dry-run
"""
import sys
import json
import signal
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Set

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from pydantic import ValidationError

from src.crawlers.youtube import crawl_videos, extract_video_id
from src.storage.s3 import S3Storage, S3StorageError
from src.utils.schemas import YouTubeVideo
from src.utils.config import config
from src.utils.logging import setup_logging, get_logger, log_crawler_stats
from src.utils.metadata_tracker import MetadataTracker
from src.utils.content_id import generate_content_id


# Initialize console and logger
console = Console()
logger = get_logger(__name__)

# Global flag for graceful shutdown
interrupted = False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    global interrupted
    interrupted = True
    console.print("\n[yellow]⚠ Interrupt received. Saving partial results...[/yellow]")


# Register signal handler
signal.signal(signal.SIGINT, signal_handler)


def load_urls_from_file(file_path: str) -> List[str]:
    """
    Load URLs from text file (one URL per line).

    Args:
        file_path: Path to text file

    Returns:
        List of URLs

    Raises:
        click.ClickException: If file doesn't exist or is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise click.ClickException(f"Input file not found: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        if not urls:
            raise click.ClickException(f"No URLs found in {file_path}")

        logger.info(f"Loaded {len(urls)} URLs from {file_path}")
        return urls

    except Exception as e:
        raise click.ClickException(f"Error reading file {file_path}: {e}")


def load_crawled_video_ids_from_s3(storage: S3Storage) -> Set[str]:
    """
    Load video IDs from S3 MetadataTracker for resume capability.

    Args:
        storage: S3Storage instance

    Returns:
        Set of already crawled video IDs
    """
    crawled_ids = set()

    try:
        # Initialize MetadataTracker (loads from S3)
        tracker = MetadataTracker(storage)

        # Get all content where stage_1_crawl is complete
        for content_id, content_data in tracker._cache.items():
            stage_data = content_data['stages']['stage_1_crawl']
            if stage_data['status'] == 'complete':
                # Extract video ID from source_url
                source_url = content_data['source_url']
                try:
                    video_id = extract_video_id(source_url)
                    crawled_ids.add(video_id)
                except Exception:
                    # If URL parsing fails, use content_id
                    if content_id.startswith('youtube_'):
                        crawled_ids.add(content_id.replace('youtube_', ''))

        if crawled_ids:
            logger.info(f"Found {len(crawled_ids)} already crawled videos in S3 (will skip)")

    except Exception as e:
        logger.warning(f"Could not load crawled videos from S3: {e}")
        logger.info("Continuing without resume capability")

    return crawled_ids


def save_failed_urls(failed_urls: List[str], output_path: Path) -> None:
    """
    Save failed URLs to a text file for retry.

    Args:
        failed_urls: List of URLs that failed
        output_path: Path to save failed URLs
    """
    if not failed_urls:
        return

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(failed_urls))
        console.print(f"[yellow]Failed URLs saved to: {output_path}[/yellow]")
        logger.info(f"Saved {len(failed_urls)} failed URLs to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save failed URLs: {e}")


# Removed save_to_local_jsonl - S3-only storage
# All data should be stored in S3 to maintain single source of truth for team collaboration


def display_summary(
    total: int,
    successful: int,
    failed: int,
    skipped: int,
    duration_seconds: float,
    output_location: str,
    total_transcript_duration: float = 0
) -> None:
    """
    Display beautiful summary table using Rich.

    Args:
        total: Total videos attempted
        successful: Number of successful crawls
        failed: Number of failed crawls
        skipped: Number of skipped videos
        duration_seconds: Total time taken
        output_location: Where data was saved
        total_transcript_duration: Total duration of transcripts in seconds
    """
    # Create summary table
    table = Table(title="Crawl Summary", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", style="green", width=40)

    # Add rows
    table.add_row("Total Videos Attempted", str(total))
    table.add_row("✓ Successful", f"[green]{successful}[/green]")
    table.add_row("✗ Failed", f"[red]{failed}[/red]")
    table.add_row("⊘ Skipped (no transcript)", f"[yellow]{skipped}[/yellow]")

    if successful > 0:
        success_rate = (successful / total * 100) if total > 0 else 0
        table.add_row("Success Rate", f"{success_rate:.1f}%")

    # Time stats
    mins, secs = divmod(duration_seconds, 60)
    table.add_row("Time Taken", f"{int(mins)}m {secs:.1f}s")

    if successful > 0 and duration_seconds > 0:
        rate = successful / duration_seconds
        table.add_row("Crawl Rate", f"{rate:.2f} videos/second")

    # Transcript duration
    if total_transcript_duration > 0:
        hours, remainder = divmod(total_transcript_duration, 3600)
        mins, secs = divmod(remainder, 60)
        table.add_row("Total Transcript Duration", f"{int(hours)}h {int(mins)}m {int(secs)}s")

    # Output location
    table.add_row("Output Location", output_location)

    console.print()
    console.print(table)
    console.print()


@click.group()
def cli():
    """Travel AI YouTube Crawler CLI"""
    # Setup logging
    setup_logging()


@cli.command()
@click.option('--input', '-i', 'input_file', required=True, type=str,
              help='Path to text file with YouTube URLs (one per line)')
@click.option('--limit', '-l', type=int, default=None,
              help='Maximum number of videos to crawl (for testing)')
@click.option('--dry-run', is_flag=True, default=False,
              help='Show what would be crawled without actually crawling')
@click.option('--force', is_flag=True, default=False,
              help='Force re-processing of all videos (skip deduplication check)')
def youtube(input_file: str, limit: Optional[int], dry_run: bool, force: bool):
    """
    Crawl YouTube videos and save metadata + transcripts to S3.

    All data is stored in S3 only (no local storage) to maintain a single
    source of truth for team collaboration.

    AUTOMATIC DEDUPLICATION: By default, checks S3 and skips already processed videos.
    Use --force to re-process videos that already exist in S3.

    Examples:

        # Crawl videos (automatically skips duplicates)
        PYTHONPATH=. python cli/crawl.py youtube --input urls.txt

        # Crawl first 10 videos (for testing)
        PYTHONPATH=. python cli/crawl.py youtube --input urls.txt --limit 10

        # Test run without actually crawling
        PYTHONPATH=. python cli/crawl.py youtube --input urls.txt --dry-run

        # Force re-processing (overwrites existing data)
        PYTHONPATH=. python cli/crawl.py youtube --input urls.txt --force
    """
    global interrupted

    # Display header
    console.print()
    console.print(Panel.fit(
        "[bold blue]Travel AI YouTube Crawler (S3-Only)[/bold blue]\n"
        f"Input: {input_file}\n"
        f"Output: S3 (single source of truth)\n"
        f"{'Limit: ' + str(limit) if limit else 'Limit: None (all videos)'}",
        border_style="blue"
    ))
    console.print()

    start_time = datetime.now()

    try:
        # Load URLs
        console.print("[cyan]Loading URLs...[/cyan]")
        urls = load_urls_from_file(input_file)
        console.print(f"[green]✓ Loaded {len(urls)} URLs[/green]\n")

        # Apply limit
        if limit and limit < len(urls):
            urls = urls[:limit]
            console.print(f"[yellow]Limiting to first {limit} videos[/yellow]\n")

        # AUTOMATIC DEDUPLICATION: Always check S3 unless --force is used
        crawled_ids = set()
        if force:
            console.print("[yellow]⚠️  --force flag detected[/yellow]")
            console.print("[yellow]⚠️  Skipping deduplication check - will re-process all videos[/yellow]\n")
        else:
            # Always check S3 for duplicates (safe by default)
            console.print("[cyan]Checking S3 for already processed videos...[/cyan]")
            storage = S3Storage()
            crawled_ids = load_crawled_video_ids_from_s3(storage)
            if crawled_ids:
                console.print(f"[green]✓ Found {len(crawled_ids)} already processed videos in S3 (will skip)[/green]\n")
            else:
                console.print(f"[cyan]No previously processed videos found in S3[/cyan]\n")

        # Filter out already crawled URLs (unless --force)
        if not force and crawled_ids:
            original_count = len(urls)
            urls = [url for url in urls if extract_video_id(url) not in crawled_ids]
            skipped_count = original_count - len(urls)
            if skipped_count > 0:
                console.print(f"[yellow]Skipping {skipped_count} already processed videos[/yellow]")
                console.print(f"[cyan]Remaining to crawl: {len(urls)} videos[/cyan]\n")

        if not urls:
            console.print("[yellow]No videos to crawl (all already processed)[/yellow]")
            return

        # Dry run
        if dry_run:
            console.print("[yellow]DRY RUN - No actual crawling will be performed[/yellow]\n")
            console.print("Videos that would be crawled:")
            for i, url in enumerate(urls[:10], 1):
                console.print(f"  {i}. {url}")
            if len(urls) > 10:
                console.print(f"  ... and {len(urls) - 10} more")
            console.print(f"\nTotal: {len(urls)} videos")
            return

        # Crawl videos
        console.print(f"[cyan]Starting crawl of {len(urls)} videos...[/cyan]\n")

        rate_limit = config.CRAWLER_RATE_LIMIT if config else 2.0
        max_retries = config.MAX_RETRIES if config else 3

        successful_videos, failed_urls = crawl_videos(
            urls=urls,
            rate_limit=rate_limit,
            max_retries=max_retries,
            language="en"
        )

        # Check if interrupted
        if interrupted:
            console.print("\n[yellow]Crawl interrupted by user[/yellow]")

        # Calculate stats
        total_attempted = len(urls)
        successful_count = len(successful_videos)
        failed_count = len(failed_urls)
        skipped_count = total_attempted - successful_count - failed_count
        duration = (datetime.now() - start_time).total_seconds()

        # Calculate total transcript duration
        total_transcript_duration = sum(
            video.get_transcript_duration() for video in successful_videos
        )

        # Save results - S3 only (single source of truth)
        output_location = ""

        if successful_videos:
            # Upload to S3
            console.print("\n[cyan]Uploading to S3...[/cyan]")
            try:
                storage = S3Storage()
                video_dicts = [video.to_dict() for video in successful_videos]
                s3_uri = storage.upload_jsonl(
                    data=video_dicts,
                    source="youtube",
                    data_type="videos"
                )
                output_location = s3_uri
                console.print(f"[green]✓ Uploaded to S3: {s3_uri}[/green]")

                # Update MetadataTracker for each successfully crawled video
                console.print("[cyan]Updating metadata tracker...[/cyan]")
                tracker = MetadataTracker(storage)

                for video in successful_videos:
                    content_id = generate_content_id("youtube", video.source_url)

                    # Register if not exists
                    if not tracker.content_exists(content_id):
                        tracker.register_content(
                            content_id=content_id,
                            source="youtube",
                            source_url=video.source_url,
                            title=video.title
                        )

                    # Mark stage 1 as complete
                    tracker.start_stage(content_id, "stage_1_crawl")
                    tracker.complete_stage(
                        content_id=content_id,
                        stage="stage_1_crawl",
                        s3_paths=[s3_uri],
                        metadata={
                            "video_id": video.source_id,
                            "duration_seconds": video.duration_seconds,
                            "transcript_segments": len(video.transcript),
                            "view_count": video.metadata.view_count,
                            "language": video.language  # Store detected language
                        }
                    )

                console.print(f"[green]✓ Updated tracking for {len(successful_videos)} videos[/green]")

            except S3StorageError as e:
                console.print(f"[red]✗ S3 upload failed: {e}[/red]")
                console.print("[red]ERROR: Cannot proceed without S3 storage.[/red]")
                console.print("[yellow]Please check your AWS credentials and S3 configuration in .env[/yellow]")
                sys.exit(1)

        else:
            output_location = "No data saved (no successful crawls)"
            console.print("\n[red]No videos were successfully crawled[/red]")

        # Save failed URLs
        if failed_urls:
            failed_file = Path("data/raw") / f"failed_urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            save_failed_urls(failed_urls, failed_file)

        # Display summary
        display_summary(
            total=total_attempted,
            successful=successful_count,
            failed=failed_count,
            skipped=skipped_count,
            duration_seconds=duration,
            output_location=output_location,
            total_transcript_duration=total_transcript_duration
        )

        # Log stats
        log_crawler_stats(
            total=total_attempted,
            success=successful_count,
            failed=failed_count,
            skipped=skipped_count,
            duration_seconds=duration
        )

        # Exit with appropriate code
        if failed_count > 0:
            sys.exit(1)

    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        console.print(f"\n[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option('--input', '-i', 'input_file', required=True, type=str,
              help='Path to JSONL file to validate')
@click.option('--verbose', '-v', is_flag=True, default=False,
              help='Show detailed validation errors')
def validate(input_file: str, verbose: bool):
    """
    Validate JSONL file against YouTubeVideo schema.

    Checks that all entries in the JSONL file conform to the expected
    schema and reports any validation errors.

    Examples:

        # Validate JSONL file
        python cli/crawl.py validate --input data/raw/batch.jsonl

        # Show detailed errors
        python cli/crawl.py validate --input data/raw/batch.jsonl --verbose
    """
    # Display header
    console.print()
    console.print(Panel.fit(
        "[bold blue]JSONL Schema Validator[/bold blue]\n"
        f"File: {input_file}",
        border_style="blue"
    ))
    console.print()

    try:
        # Check file exists
        path = Path(input_file)
        if not path.exists():
            raise click.ClickException(f"File not found: {input_file}")

        # Validate each line
        console.print("[cyan]Validating JSONL file...[/cyan]\n")

        valid_count = 0
        invalid_count = 0
        errors = []

        with open(path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    # Parse JSON
                    data = json.loads(line)

                    # Validate with schema
                    video = YouTubeVideo(**data)
                    valid_count += 1

                    if verbose:
                        console.print(f"[green]✓ Line {line_num}: {video.title}[/green]")

                except json.JSONDecodeError as e:
                    invalid_count += 1
                    error_msg = f"Line {line_num}: Invalid JSON - {e}"
                    errors.append(error_msg)
                    if verbose:
                        console.print(f"[red]✗ {error_msg}[/red]")

                except ValidationError as e:
                    invalid_count += 1
                    error_msg = f"Line {line_num}: Schema validation failed"
                    errors.append(error_msg)
                    if verbose:
                        console.print(f"[red]✗ {error_msg}[/red]")
                        for err in e.errors():
                            field = '.'.join(str(x) for x in err['loc'])
                            console.print(f"    Field: {field}")
                            console.print(f"    Error: {err['msg']}")

        # Display results
        console.print()
        table = Table(title="Validation Results", box=box.ROUNDED)
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")

        table.add_row("[green]Valid Entries[/green]", f"[green]{valid_count}[/green]")
        table.add_row("[red]Invalid Entries[/red]", f"[red]{invalid_count}[/red]")

        total = valid_count + invalid_count
        if total > 0:
            validity_rate = (valid_count / total * 100)
            table.add_row("Validity Rate", f"{validity_rate:.1f}%")

        console.print(table)
        console.print()

        # Show errors summary (if not verbose)
        if errors and not verbose:
            console.print(f"[yellow]Found {len(errors)} validation errors[/yellow]")
            console.print("[dim]Use --verbose flag to see detailed errors[/dim]\n")

        # Exit code
        if invalid_count > 0:
            logger.warning(f"Validation found {invalid_count} invalid entries")
            sys.exit(1)
        else:
            console.print("[green]✓ All entries are valid![/green]\n")
            logger.info("Validation successful")

    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        console.print(f"\n[red]✗ Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
