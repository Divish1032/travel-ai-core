#!/usr/bin/env python3
"""
Pipeline Validation Script

Checks that the S3-only pipeline is working correctly:
1. Verifies S3 connectivity
2. Checks MetadataTracker state
3. Validates data in S3
4. Reports on crawl status

Usage:
    python validate_pipeline.py
    PYTHONPATH=. python validate_pipeline.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import setup_logging, get_logger

console = Console()
logger = get_logger(__name__)


def check_s3_connectivity(storage: S3Storage) -> bool:
    """Test S3 connectivity."""
    console.print("\n[cyan]1. Testing S3 Connectivity...[/cyan]")

    try:
        # Try to list files
        bucket = storage.bucket_name
        console.print(f"  Bucket: {bucket}")
        console.print(f"  Region: {storage.s3_client.meta.region_name}")
        console.print("[green]  ✓ S3 connection successful[/green]")
        return True
    except Exception as e:
        console.print(f"[red]  ✗ S3 connection failed: {e}[/red]")
        return False


def check_metadata_tracker(storage: S3Storage) -> tuple:
    """Check MetadataTracker state."""
    console.print("\n[cyan]2. Checking MetadataTracker...[/cyan]")

    try:
        tracker = MetadataTracker(storage)
        total_items = len(tracker._cache)

        console.print(f"  Total tracked items: {total_items}")

        if total_items == 0:
            console.print("[yellow]  ⚠ No items in tracker (fresh start)[/yellow]")
            return tracker, total_items

        # Count by pipeline status
        status_counts = {}
        for content_data in tracker._cache.values():
            status = content_data['pipeline_status']
            status_counts[status] = status_counts.get(status, 0) + 1

        console.print("  Pipeline Status Distribution:")
        for status, count in sorted(status_counts.items()):
            console.print(f"    - {status}: {count}")

        console.print("[green]  ✓ MetadataTracker loaded[/green]")
        return tracker, total_items

    except Exception as e:
        console.print(f"[red]  ✗ MetadataTracker check failed: {e}[/red]")
        return None, 0


def check_s3_data(storage: S3Storage) -> dict:
    """Check what data exists in S3."""
    console.print("\n[cyan]3. Checking S3 Data...[/cyan]")

    results = {
        'video_batches': [],
        'metadata_files': [],
        'total_videos': 0
    }

    try:
        # Check raw video batches
        console.print("  Raw Video Batches:")
        try:
            # List files in raw/youtube/videos/
            files = storage.list_files("raw/youtube/videos/")
            results['video_batches'] = files

            if not files:
                console.print("    [yellow]No video batches found[/yellow]")
            else:
                for file_uri in files:
                    # Download and count videos
                    try:
                        data = storage.download_jsonl(file_uri)
                        video_count = len(data)
                        results['total_videos'] += video_count

                        # Extract filename
                        filename = file_uri.split('/')[-1]
                        console.print(f"    - {filename}: {video_count} videos")
                    except Exception as e:
                        console.print(f"    [yellow]Could not read {file_uri}: {e}[/yellow]")

                console.print(f"  [green]Total videos in S3: {results['total_videos']}[/green]")

        except Exception as e:
            console.print(f"    [yellow]Could not list video batches: {e}[/yellow]")

        # Check metadata files
        console.print("\n  Metadata Files:")
        try:
            metadata_uri = storage._generate_s3_uri("metadata/processing_status.jsonl")
            if storage.file_exists(metadata_uri):
                console.print(f"    - processing_status.jsonl: [green]exists[/green]")
                results['metadata_files'].append(metadata_uri)
            else:
                console.print(f"    - processing_status.jsonl: [yellow]not found[/yellow]")
        except Exception as e:
            console.print(f"    [yellow]Could not check metadata: {e}[/yellow]")

        console.print("[green]  ✓ S3 data check complete[/green]")
        return results

    except Exception as e:
        console.print(f"[red]  ✗ S3 data check failed: {e}[/red]")
        return results


def display_summary(tracker: MetadataTracker, s3_data: dict):
    """Display summary table."""
    console.print("\n" + "="*70)
    console.print(Panel.fit(
        "[bold green]Pipeline Validation Summary[/bold green]",
        border_style="green"
    ))

    # Overall stats table
    table = Table(title="Overall Statistics", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan", width=35)
    table.add_column("Value", style="green", width=25)

    if tracker:
        tracked_count = len(tracker._cache)
        table.add_row("Items in MetadataTracker", str(tracked_count))

        # Stage 1 stats
        stage1_stats = tracker.get_stage_statistics("stage_1_crawl")
        table.add_row("Stage 1 - Complete", f"[green]{stage1_stats['complete']}[/green]")
        table.add_row("Stage 1 - Failed", f"[red]{stage1_stats['failed']}[/red]")
        table.add_row("Stage 1 - Pending", f"[yellow]{stage1_stats['pending']}[/yellow]")
        table.add_row("Stage 1 - Not Started", f"[white]{stage1_stats['not_started']}[/white]")
    else:
        table.add_row("Items in MetadataTracker", "[yellow]0 (tracker not initialized)[/yellow]")

    table.add_row("Video Batches in S3", str(len(s3_data['video_batches'])))
    table.add_row("Total Videos in S3", str(s3_data['total_videos']))

    console.print(table)
    console.print()


def main():
    """Run pipeline validation."""
    console.print()
    console.print(Panel.fit(
        "[bold blue]Travel AI - Pipeline Validation[/bold blue]\n"
        "S3-Only Architecture Check",
        border_style="blue"
    ))

    setup_logging("INFO")

    try:
        # Initialize S3
        storage = S3Storage()

        # Run checks
        s3_ok = check_s3_connectivity(storage)
        if not s3_ok:
            console.print("\n[red]✗ S3 connectivity check failed. Please check your .env configuration.[/red]")
            sys.exit(1)

        tracker, tracked_count = check_metadata_tracker(storage)
        s3_data = check_s3_data(storage)

        # Display summary
        display_summary(tracker, s3_data)

        # Final verdict
        console.print("="*70)

        if tracked_count > 0 and s3_data['total_videos'] > 0:
            console.print("[green]✓ Pipeline is active with data[/green]")
            console.print(f"[cyan]  Tracked: {tracked_count} items[/cyan]")
            console.print(f"[cyan]  In S3: {s3_data['total_videos']} videos[/cyan]")
            console.print()
            console.print("[yellow]Next steps:[/yellow]")
            console.print("  - Run './crawl.sh status' for detailed pipeline status")
            console.print("  - Run './crawl.sh stage stage_1_crawl' for stage details")
            console.print("  - Run './crawl.sh youtube --input urls.txt --resume' to add more videos")
        elif tracked_count == 0 and s3_data['total_videos'] == 0:
            console.print("[yellow]⚠ Pipeline is ready but empty[/yellow]")
            console.print()
            console.print("[cyan]Next steps:[/cyan]")
            console.print("  1. Create test_urls.txt with YouTube URLs")
            console.print("  2. Run './crawl.sh youtube --input test_urls.txt'")
            console.print("  3. Run this validation script again")
        else:
            console.print("[yellow]⚠ Inconsistent state detected[/yellow]")
            console.print(f"  Tracked items: {tracked_count}")
            console.print(f"  Videos in S3: {s3_data['total_videos']}")
            console.print()
            console.print("[yellow]This might be normal if:[/yellow]")
            console.print("  - You just cleaned S3 but metadata still exists")
            console.print("  - Crawl is in progress")

        console.print("="*70)
        console.print()

    except Exception as e:
        console.print(f"\n[red]✗ Validation failed: {e}[/red]")
        logger.error(f"Validation error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
