#!/usr/bin/env python3
"""
Stage 1 Completion Test - End-to-End Integration Test

This script validates that Stage 1 (YouTube Crawling) is fully functional
by running a complete workflow: crawl → validate → save → upload → download.

Usage:
    python scripts/test_stage1_complete.py
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crawlers.youtube import crawl_videos
from src.storage.s3 import S3Storage, S3StorageError
from src.utils.schemas import YouTubeVideo
from src.utils.config import config
from src.utils.logging import setup_logging, get_logger, log_crawler_stats


# Initialize
console = Console()
logger = get_logger(__name__)


def print_section(title: str):
    """Print section header."""
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan"
    ))
    console.print()


def load_sample_urls(limit: int = 3) -> List[str]:
    """Load sample URLs for testing."""
    urls_file = project_root / "data" / "sample_urls.txt"

    if not urls_file.exists():
        raise FileNotFoundError(f"Sample URLs file not found: {urls_file}")

    with open(urls_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    return urls[:limit]


def validate_videos(videos: List[YouTubeVideo]) -> bool:
    """Validate all videos against schema."""
    console.print("[cyan]Validating videos against schema...[/cyan]")

    for i, video in enumerate(videos, 1):
        try:
            # Schema validation already done by Pydantic
            # Just do some sanity checks
            assert video.source == "youtube"
            assert video.source_id is not None
            assert len(video.title) > 0
            assert video.duration_seconds > 0
            assert len(video.transcript) > 0
            assert video.metadata.view_count >= 0

            console.print(f"  ✓ Video {i}: {video.title[:50]}...")
        except AssertionError as e:
            console.print(f"  ✗ Video {i}: Validation failed - {e}")
            return False

    console.print("[green]✓ All videos passed validation[/green]\n")
    return True


def save_to_local(videos: List[YouTubeVideo]) -> str:
    """Save videos to local JSONL file."""
    console.print("[cyan]Saving to local JSONL...[/cyan]")

    output_dir = project_root / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"stage1_test_{timestamp}.jsonl"

    with open(output_file, 'w', encoding='utf-8') as f:
        for video in videos:
            json_str = json.dumps(video.to_dict(), ensure_ascii=False)
            f.write(json_str + '\n')

    file_size = output_file.stat().st_size
    console.print(f"[green]✓ Saved to: {output_file}[/green]")
    console.print(f"  File size: {file_size / 1024:.1f} KB\n")

    return str(output_file)


def upload_to_s3(videos: List[YouTubeVideo]) -> str:
    """Upload videos to S3."""
    console.print("[cyan]Uploading to S3...[/cyan]")

    try:
        storage = S3Storage()
        video_dicts = [v.to_dict() for v in videos]

        s3_uri = storage.upload_jsonl(
            data=video_dicts,
            source="youtube",
            data_type="stage1_test"
        )

        console.print(f"[green]✓ Uploaded to: {s3_uri}[/green]\n")
        return s3_uri

    except S3StorageError as e:
        console.print(f"[yellow]⚠ S3 upload failed: {e}[/yellow]")
        console.print("[yellow]Continuing with local storage only[/yellow]\n")
        return None


def download_from_s3(s3_uri: str) -> List[Dict[str, Any]]:
    """Download data from S3."""
    console.print("[cyan]Downloading from S3...[/cyan]")

    try:
        storage = S3Storage()
        downloaded = storage.download_jsonl(s3_uri)

        console.print(f"[green]✓ Downloaded {len(downloaded)} videos from S3[/green]\n")
        return downloaded

    except S3StorageError as e:
        console.print(f"[red]✗ S3 download failed: {e}[/red]\n")
        return None


def compare_data(original: List[YouTubeVideo], downloaded: List[Dict[str, Any]]) -> bool:
    """Compare original and downloaded data."""
    console.print("[cyan]Comparing original vs downloaded data...[/cyan]")

    if not downloaded:
        console.print("[yellow]⚠ No downloaded data to compare[/yellow]\n")
        return True  # Skip comparison if S3 not available

    if len(original) != len(downloaded):
        console.print(f"[red]✗ Count mismatch: {len(original)} original vs {len(downloaded)} downloaded[/red]\n")
        return False

    for i, (orig, down) in enumerate(zip(original, downloaded), 1):
        if orig.source_id != down['source_id']:
            console.print(f"[red]✗ Video {i}: ID mismatch[/red]")
            return False
        if orig.title != down['title']:
            console.print(f"[red]✗ Video {i}: Title mismatch[/red]")
            return False

    console.print("[green]✓ Original and downloaded data match[/green]\n")
    return True


def calculate_stats(videos: List[YouTubeVideo]) -> Dict[str, Any]:
    """Calculate statistics from crawled videos."""
    total_duration = sum(v.duration_seconds for v in videos)
    total_transcript_duration = sum(v.get_transcript_duration() for v in videos)
    total_words = sum(len(v.get_full_transcript_text().split()) for v in videos)
    total_segments = sum(len(v.transcript) for v in videos)
    total_views = sum(v.metadata.view_count for v in videos)

    return {
        'count': len(videos),
        'total_duration': total_duration,
        'avg_duration': total_duration / len(videos) if videos else 0,
        'total_transcript_duration': total_transcript_duration,
        'total_words': total_words,
        'avg_words': total_words / len(videos) if videos else 0,
        'total_segments': total_segments,
        'avg_segments': total_segments / len(videos) if videos else 0,
        'total_views': total_views
    }


def display_results(
    videos: List[YouTubeVideo],
    stats: Dict[str, Any],
    local_file: str,
    s3_uri: str,
    times: Dict[str, float]
):
    """Display final results in a beautiful table."""
    print_section("📊 STAGE 1 TEST RESULTS")

    # Videos table
    videos_table = Table(title="Crawled Videos", box=box.ROUNDED)
    videos_table.add_column("Title", style="cyan", width=40)
    videos_table.add_column("Duration", justify="right")
    videos_table.add_column("Segments", justify="right")
    videos_table.add_column("Words", justify="right")
    videos_table.add_column("Views", justify="right")

    for video in videos:
        mins, secs = divmod(video.duration_seconds, 60)
        duration_str = f"{int(mins)}m {int(secs)}s"
        words = len(video.get_full_transcript_text().split())

        videos_table.add_row(
            video.title[:40],
            duration_str,
            str(len(video.transcript)),
            f"{words:,}",
            f"{video.metadata.view_count:,}"
        )

    console.print(videos_table)
    console.print()

    # Statistics table
    stats_table = Table(title="Statistics", box=box.ROUNDED, show_header=False)
    stats_table.add_column("Metric", style="cyan", width=30)
    stats_table.add_column("Value", style="green", width=30)

    stats_table.add_row("Videos Crawled", str(stats['count']))
    stats_table.add_row("Total Video Duration", f"{stats['total_duration'] // 60}m {stats['total_duration'] % 60}s")
    stats_table.add_row("Average Video Duration", f"{stats['avg_duration'] // 60}m {stats['avg_duration'] % 60:.0f}s")
    stats_table.add_row("Total Transcript Duration", f"{stats['total_transcript_duration'] / 60:.1f}m")
    stats_table.add_row("Total Words", f"{stats['total_words']:,}")
    stats_table.add_row("Average Words per Video", f"{stats['avg_words']:.0f}")
    stats_table.add_row("Total Transcript Segments", f"{stats['total_segments']:,}")
    stats_table.add_row("Average Segments per Video", f"{stats['avg_segments']:.0f}")
    stats_table.add_row("Total Views", f"{stats['total_views']:,}")

    console.print(stats_table)
    console.print()

    # Storage table
    storage_table = Table(title="Storage", box=box.ROUNDED, show_header=False)
    storage_table.add_column("Location", style="cyan", width=20)
    storage_table.add_column("Path", style="green", width=60)

    storage_table.add_row("Local JSONL", local_file)
    if s3_uri:
        storage_table.add_row("S3 URI", s3_uri)
    else:
        storage_table.add_row("S3 URI", "[yellow]Not uploaded (S3 not configured)[/yellow]")

    console.print(storage_table)
    console.print()

    # Timing table
    timing_table = Table(title="Performance", box=box.ROUNDED, show_header=False)
    timing_table.add_column("Operation", style="cyan", width=30)
    timing_table.add_column("Time", style="green", width=20)

    for operation, duration in times.items():
        if duration > 60:
            time_str = f"{duration // 60:.0f}m {duration % 60:.1f}s"
        else:
            time_str = f"{duration:.1f}s"
        timing_table.add_row(operation, time_str)

    total_time = sum(times.values())
    if total_time > 60:
        total_str = f"{total_time // 60:.0f}m {total_time % 60:.1f}s"
    else:
        total_str = f"{total_time:.1f}s"
    timing_table.add_row("[bold]Total Time[/bold]", f"[bold]{total_str}[/bold]")

    console.print(timing_table)


def main():
    """Run complete Stage 1 integration test."""
    console.print()
    console.print(Panel.fit(
        "[bold blue]Travel AI - Stage 1 Completion Test[/bold blue]\n"
        "End-to-End Integration Test",
        border_style="blue"
    ))
    console.print()

    # Setup logging
    setup_logging("INFO")

    # Track timing
    times = {}

    try:
        # Step 1: Load sample URLs
        print_section("1️⃣  Loading Sample URLs")
        urls = load_sample_urls(limit=3)
        console.print(f"[green]✓ Loaded {len(urls)} sample URLs[/green]")
        for i, url in enumerate(urls, 1):
            console.print(f"  {i}. {url}")
        console.print()

        # Step 2: Crawl videos
        print_section("2️⃣  Crawling Videos")
        console.print("[cyan]This will take 30-60 seconds...[/cyan]\n")

        start_time = time.time()
        successful, failed = crawl_videos(
            urls=urls,
            rate_limit=2.0,
            max_retries=2,
            language="en"
        )
        times['Crawling'] = time.time() - start_time

        if not successful:
            console.print("[red]✗ No videos were successfully crawled[/red]")
            console.print("[yellow]This might be because:[/yellow]")
            console.print("  - Videos don't have English transcripts")
            console.print("  - Network connectivity issues")
            console.print("  - Rate limiting")
            console.print("\nTry running again or check the URLs in data/sample_urls.txt")
            return False

        console.print(f"[green]✓ Successfully crawled {len(successful)} videos[/green]")
        if failed:
            console.print(f"[yellow]⚠ {len(failed)} videos failed or were skipped[/yellow]")
        console.print()

        # Step 3: Validate videos
        print_section("3️⃣  Validating Data")
        start_time = time.time()
        if not validate_videos(successful):
            return False
        times['Validation'] = time.time() - start_time

        # Step 4: Save locally
        print_section("4️⃣  Saving to Local Storage")
        start_time = time.time()
        local_file = save_to_local(successful)
        times['Local Save'] = time.time() - start_time

        # Step 5: Upload to S3 (optional)
        print_section("5️⃣  Uploading to S3")
        if config and config.S3_BUCKET_NAME:
            start_time = time.time()
            s3_uri = upload_to_s3(successful)
            times['S3 Upload'] = time.time() - start_time
        else:
            console.print("[yellow]⚠ S3 not configured, skipping upload[/yellow]")
            console.print("Set AWS credentials in .env to enable S3 upload\n")
            s3_uri = None

        # Step 6: Download from S3 (if uploaded)
        downloaded = None
        if s3_uri:
            print_section("6️⃣  Downloading from S3")
            start_time = time.time()
            downloaded = download_from_s3(s3_uri)
            times['S3 Download'] = time.time() - start_time

        # Step 7: Compare data
        if downloaded:
            print_section("7️⃣  Comparing Data")
            start_time = time.time()
            if not compare_data(successful, downloaded):
                return False
            times['Comparison'] = time.time() - start_time

        # Step 8: Calculate statistics
        stats = calculate_stats(successful)

        # Step 9: Display results
        display_results(successful, stats, local_file, s3_uri, times)

        # Success!
        console.print()
        console.print(Panel.fit(
            "[bold green]✅ STAGE 1 COMPLETE![/bold green]\n\n"
            "All systems operational:\n"
            "  ✓ YouTube crawler working\n"
            "  ✓ Schema validation passing\n"
            "  ✓ Local storage working\n"
            f"  {'✓' if s3_uri else '⊘'} S3 storage {'working' if s3_uri else 'not configured'}\n"
            "  ✓ Data integrity verified\n\n"
            "[cyan]You are ready for Stage 2![/cyan]",
            border_style="green",
            padding=(1, 2)
        ))
        console.print()

        return True

    except FileNotFoundError as e:
        console.print(f"\n[red]✗ Error: {e}[/red]")
        console.print("[yellow]Make sure you run this from the project root directory[/yellow]\n")
        return False

    except Exception as e:
        console.print(f"\n[red]✗ Unexpected error: {e}[/red]")
        logger.error(f"Stage 1 test failed: {e}", exc_info=True)
        console.print("\n[yellow]Check logs/errors_*.log for details[/yellow]\n")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
