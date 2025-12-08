#!/usr/bin/env python3
"""
Metadata Tracking CLI for Travel AI Pipeline

Command-line tools for viewing and managing pipeline metadata across all stages.

Usage:
    # Show pipeline overview
    python cli/tracking.py status

    # Show stage details
    python cli/tracking.py stage stage_1_crawl

    # List failed items
    python cli/tracking.py failed --stage stage_1_crawl

    # Retry failed items
    python cli/tracking.py retry stage_1_crawl

    # Show content details
    python cli/tracking.py info youtube_abc123

    # Export to CSV
    python cli/tracking.py export pipeline_status.csv
"""
import sys
import csv
from pathlib import Path
from typing import Optional

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


def get_tracker() -> MetadataTracker:
    """Initialize and return MetadataTracker instance."""
    try:
        storage = S3Storage()
        tracker = MetadataTracker(storage)
        return tracker
    except Exception as e:
        console.print(f"[red]✗ Error initializing tracker: {e}[/red]")
        console.print("[yellow]Make sure AWS credentials are configured in .env[/yellow]")
        sys.exit(1)


@click.group()
def cli():
    """Travel AI Pipeline Metadata Management"""
    setup_logging("INFO")


@cli.command()
def status():
    """
    Show pipeline overview with statistics for all stages.

    Example:
        python cli/tracking.py status
    """
    console.print()
    console.print(Panel.fit(
        "[bold blue]Travel AI Pipeline Status[/bold blue]",
        border_style="blue"
    ))
    console.print()

    tracker = get_tracker()

    # Overall summary
    total_items = len(tracker._cache)
    console.print(f"[cyan]Total Content Items: {total_items}[/cyan]\n")

    if total_items == 0:
        console.print("[yellow]No content items found in tracker[/yellow]\n")
        return

    # Create stage overview table
    table = Table(
        title="Pipeline Stage Overview",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )

    table.add_column("Stage", style="cyan", width=20)
    table.add_column("Not Started", justify="right", style="white")
    table.add_column("Pending", justify="right", style="yellow")
    table.add_column("Complete", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Avg Duration", justify="right", style="blue")

    # Get statistics for each stage
    for stage in tracker.STAGES:
        stats = tracker.get_stage_statistics(stage)

        # Format average duration
        if stats['avg_duration_seconds']:
            mins, secs = divmod(stats['avg_duration_seconds'], 60)
            if mins > 0:
                avg_duration = f"{int(mins)}m {int(secs)}s"
            else:
                avg_duration = f"{secs:.1f}s"
        else:
            avg_duration = "N/A"

        # Color code the stage name based on overall status
        stage_display = stage
        if stats['complete'] == stats['total']:
            stage_display = f"[green]{stage}[/green]"
        elif stats['failed'] > 0:
            stage_display = f"[red]{stage}[/red]"
        elif stats['pending'] > 0:
            stage_display = f"[yellow]{stage}[/yellow]"

        table.add_row(
            stage_display,
            str(stats['not_started']),
            str(stats['pending']),
            str(stats['complete']),
            str(stats['failed']),
            avg_duration
        )

    console.print(table)
    console.print()

    # Overall pipeline status summary
    pipeline_statuses = {}
    for content_data in tracker._cache.values():
        status = content_data['pipeline_status']
        pipeline_statuses[status] = pipeline_statuses.get(status, 0) + 1

    if pipeline_statuses:
        console.print("[cyan]Overall Pipeline Status Distribution:[/cyan]")
        for status, count in sorted(pipeline_statuses.items()):
            console.print(f"  {status}: {count}")
        console.print()


@cli.command()
@click.argument('stage')
def stage(stage: str):
    """
    Show detailed statistics for a specific stage.

    Example:
        python cli/tracking.py stage stage_1_crawl
    """
    console.print()
    console.print(Panel.fit(
        f"[bold blue]Stage Details: {stage}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    tracker = get_tracker()

    # Validate stage
    if stage not in tracker.STAGES:
        console.print(f"[red]✗ Invalid stage: {stage}[/red]")
        console.print(f"Valid stages: {', '.join(tracker.STAGES)}")
        return

    # Get statistics
    stats = tracker.get_stage_statistics(stage)

    # Display statistics
    stats_table = Table(title="Stage Statistics", box=box.ROUNDED, show_header=False)
    stats_table.add_column("Metric", style="cyan", width=25)
    stats_table.add_column("Value", style="green", width=20)

    stats_table.add_row("Total Items", str(stats['total']))
    stats_table.add_row("Not Started", str(stats['not_started']))
    stats_table.add_row("Pending", str(stats['pending']))
    stats_table.add_row("Complete", f"[green]{stats['complete']}[/green]")
    stats_table.add_row("Failed", f"[red]{stats['failed']}[/red]")

    if stats['avg_duration_seconds']:
        mins, secs = divmod(stats['avg_duration_seconds'], 60)
        duration_str = f"{int(mins)}m {secs:.1f}s" if mins > 0 else f"{secs:.1f}s"
        stats_table.add_row("Average Duration", duration_str)

    console.print(stats_table)
    console.print()

    # Show recent failures
    failures = []
    for content_id, content_data in tracker._cache.items():
        stage_data = content_data['stages'][stage]
        if stage_data['status'] == 'failed':
            failures.append({
                'content_id': content_id,
                'title': content_data.get('title', 'N/A'),
                'error': stage_data.get('error', 'Unknown'),
                'retry_count': stage_data.get('retry_count', 0)
            })

    if failures:
        console.print(f"[red]Recent Failures ({len(failures)}):[/red]\n")

        failures_table = Table(box=box.SIMPLE)
        failures_table.add_column("Content ID", style="cyan", width=20)
        failures_table.add_column("Title", style="white", width=30)
        failures_table.add_column("Retries", justify="right", style="yellow")
        failures_table.add_column("Error", style="red", width=40)

        # Show first 10 failures
        for failure in failures[:10]:
            title = failure['title'][:27] + "..." if failure['title'] and len(failure['title']) > 30 else failure['title']
            error = failure['error'][:37] + "..." if len(failure['error']) > 40 else failure['error']

            failures_table.add_row(
                failure['content_id'],
                title or "N/A",
                str(failure['retry_count']),
                error
            )

        console.print(failures_table)

        if len(failures) > 10:
            console.print(f"\n[dim]... and {len(failures) - 10} more failures[/dim]")

        console.print()


@cli.command()
@click.option('--stage', '-s', type=str, default=None,
              help='Filter by specific stage')
def failed(stage: Optional[str]):
    """
    List all failed items, optionally filtered by stage.

    Example:
        python cli/tracking.py failed
        python cli/tracking.py failed --stage stage_1_crawl
    """
    console.print()
    title = "Failed Items" if not stage else f"Failed Items - {stage}"
    console.print(Panel.fit(
        f"[bold red]{title}[/bold red]",
        border_style="red"
    ))
    console.print()

    tracker = get_tracker()

    # Validate stage if provided
    if stage and stage not in tracker.STAGES:
        console.print(f"[red]✗ Invalid stage: {stage}[/red]")
        console.print(f"Valid stages: {', '.join(tracker.STAGES)}")
        return

    # Collect failures
    failures = []
    for content_id, content_data in tracker._cache.items():
        if stage:
            # Filter by specific stage
            stage_data = content_data['stages'][stage]
            if stage_data['status'] == 'failed':
                failures.append({
                    'content_id': content_id,
                    'stage': stage,
                    'title': content_data.get('title', 'N/A'),
                    'error': stage_data.get('error', 'Unknown'),
                    'retry_count': stage_data.get('retry_count', 0),
                    'source_url': content_data.get('source_url', 'N/A')
                })
        else:
            # Check all stages
            for stage_name in tracker.STAGES:
                stage_data = content_data['stages'][stage_name]
                if stage_data['status'] == 'failed':
                    failures.append({
                        'content_id': content_id,
                        'stage': stage_name,
                        'title': content_data.get('title', 'N/A'),
                        'error': stage_data.get('error', 'Unknown'),
                        'retry_count': stage_data.get('retry_count', 0),
                        'source_url': content_data.get('source_url', 'N/A')
                    })

    if not failures:
        console.print("[green]✓ No failed items found[/green]\n")
        return

    console.print(f"[red]Found {len(failures)} failed items[/red]\n")

    # Display failures table
    table = Table(box=box.ROUNDED)
    table.add_column("Content ID", style="cyan", width=20)
    table.add_column("Stage", style="yellow", width=18)
    table.add_column("Title", style="white", width=25)
    table.add_column("Retries", justify="right", style="yellow")
    table.add_column("Error", style="red", width=35)

    for failure in failures[:20]:  # Show first 20
        title = failure['title'][:22] + "..." if failure['title'] and len(failure['title']) > 25 else failure['title']
        error = failure['error'][:32] + "..." if len(failure['error']) > 35 else failure['error']

        table.add_row(
            failure['content_id'],
            failure['stage'],
            title or "N/A",
            str(failure['retry_count']),
            error
        )

    console.print(table)

    if len(failures) > 20:
        console.print(f"\n[dim]... and {len(failures) - 20} more failures[/dim]")

    console.print()


@cli.command()
@click.argument('stage')
@click.option('--max-retries', '-m', type=int, default=3,
              help='Only reset items with retry_count < max_retries (default: 3)')
def retry(stage: str, max_retries: int):
    """
    Reset failed items to allow retry.

    Resets items where retry_count < max_retries back to "not_started" status.

    Example:
        python cli/tracking.py retry stage_1_crawl
        python cli/tracking.py retry stage_2_chunk --max-retries 5
    """
    console.print()
    console.print(Panel.fit(
        f"[bold yellow]Retry Failed Items - {stage}[/bold yellow]",
        border_style="yellow"
    ))
    console.print()

    tracker = get_tracker()

    # Validate stage
    if stage not in tracker.STAGES:
        console.print(f"[red]✗ Invalid stage: {stage}[/red]")
        console.print(f"Valid stages: {', '.join(tracker.STAGES)}")
        return

    # Find failed items eligible for retry
    eligible = []
    for content_id, content_data in tracker._cache.items():
        stage_data = content_data['stages'][stage]
        if stage_data['status'] == 'failed' and stage_data['retry_count'] < max_retries:
            eligible.append({
                'content_id': content_id,
                'retry_count': stage_data['retry_count'],
                'error': stage_data.get('error', 'Unknown')
            })

    if not eligible:
        console.print(f"[yellow]No eligible items found for retry in {stage}[/yellow]")
        console.print(f"(Items with retry_count < {max_retries})\n")
        return

    console.print(f"[cyan]Found {len(eligible)} items eligible for retry:[/cyan]\n")

    # Show items to be reset
    for item in eligible[:5]:  # Show first 5
        console.print(f"  - {item['content_id']} (retries: {item['retry_count']})")

    if len(eligible) > 5:
        console.print(f"  ... and {len(eligible) - 5} more")

    console.print()

    # Confirm
    if not click.confirm(f"Reset {len(eligible)} items to 'not_started'?"):
        console.print("[yellow]Cancelled[/yellow]\n")
        return

    # Reset items
    reset_count = 0
    for item in eligible:
        try:
            tracker.reset_stage(item['content_id'], stage)
            reset_count += 1
        except Exception as e:
            console.print(f"[red]✗ Failed to reset {item['content_id']}: {e}[/red]")

    console.print(f"\n[green]✓ Reset {reset_count} items to 'not_started'[/green]")
    console.print(f"[cyan]These items will be picked up on next processing run[/cyan]\n")


@cli.command()
@click.argument('content_id')
def info(content_id: str):
    """
    Show detailed information for a specific content item.

    Example:
        python cli/tracking.py info youtube_abc123
    """
    console.print()
    console.print(Panel.fit(
        f"[bold blue]Content Details: {content_id}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    tracker = get_tracker()

    # Check if exists
    if not tracker.content_exists(content_id):
        console.print(f"[red]✗ Content not found: {content_id}[/red]\n")
        return

    # Get info
    info = tracker.get_content_info(content_id)

    # Basic info table
    basic_table = Table(title="Basic Information", box=box.ROUNDED, show_header=False)
    basic_table.add_column("Field", style="cyan", width=20)
    basic_table.add_column("Value", style="green", width=50)

    basic_table.add_row("Content ID", info['content_id'])
    basic_table.add_row("Source", info['source'])
    basic_table.add_row("Title", info.get('title') or "N/A")
    basic_table.add_row("Source URL", info['source_url'])
    basic_table.add_row("Added At", info['added_at'])
    basic_table.add_row("Last Updated", info['last_updated'])
    basic_table.add_row("Pipeline Status", info['pipeline_status'])
    basic_table.add_row("Total Errors", str(info['total_error_count']))

    if info.get('tags'):
        basic_table.add_row("Tags", ", ".join(info['tags']))

    console.print(basic_table)
    console.print()

    # Stage details table
    stage_table = Table(title="Stage Status", box=box.ROUNDED)
    stage_table.add_column("Stage", style="cyan", width=20)
    stage_table.add_column("Status", style="white", width=12)
    stage_table.add_column("Duration", justify="right", style="blue", width=12)
    stage_table.add_column("Retries", justify="right", style="yellow", width=8)
    stage_table.add_column("Error", style="red", width=30)

    for stage_name in tracker.STAGES:
        stage_data = info['stages'][stage_name]
        status = stage_data['status']

        # Color code status
        if status == 'complete':
            status_display = f"[green]{status}[/green]"
        elif status == 'failed':
            status_display = f"[red]{status}[/red]"
        elif status == 'pending':
            status_display = f"[yellow]{status}[/yellow]"
        else:
            status_display = status

        # Format duration
        if stage_data['duration_seconds']:
            mins, secs = divmod(stage_data['duration_seconds'], 60)
            duration = f"{int(mins)}m {int(secs)}s" if mins > 0 else f"{secs:.1f}s"
        else:
            duration = "N/A"

        # Format error
        error = stage_data.get('error', '')
        if error:
            error = error[:27] + "..." if len(error) > 30 else error
        else:
            error = ""

        stage_table.add_row(
            stage_name,
            status_display,
            duration,
            str(stage_data['retry_count']),
            error
        )

    console.print(stage_table)
    console.print()

    # Show S3 paths if any
    has_s3_paths = False
    for stage_name in tracker.STAGES:
        stage_data = info['stages'][stage_name]
        if stage_data.get('s3_paths'):
            if not has_s3_paths:
                console.print("[cyan]S3 Output Paths:[/cyan]")
                has_s3_paths = True
            console.print(f"  {stage_name}:")
            for path in stage_data['s3_paths']:
                console.print(f"    - {path}")

    if has_s3_paths:
        console.print()


@cli.command()
@click.argument('csv_path')
@click.option('--stage', '-s', type=str, default=None,
              help='Export specific stage only')
def export(csv_path: str, stage: Optional[str]):
    """
    Export pipeline status to CSV file.

    Example:
        python cli/tracking.py export pipeline_status.csv
        python cli/tracking.py export stage1_status.csv --stage stage_1_crawl
    """
    console.print()
    console.print(Panel.fit(
        "[bold blue]Export Pipeline Status[/bold blue]",
        border_style="blue"
    ))
    console.print()

    tracker = get_tracker()

    # Validate stage if provided
    if stage and stage not in tracker.STAGES:
        console.print(f"[red]✗ Invalid stage: {stage}[/red]")
        console.print(f"Valid stages: {', '.join(tracker.STAGES)}")
        return

    # Prepare CSV data
    rows = []

    if stage:
        # Export specific stage
        console.print(f"[cyan]Exporting {stage} status...[/cyan]\n")

        for content_id, content_data in tracker._cache.items():
            stage_data = content_data['stages'][stage]
            rows.append({
                'content_id': content_id,
                'source': content_data['source'],
                'title': content_data.get('title', ''),
                'source_url': content_data['source_url'],
                'stage': stage,
                'status': stage_data['status'],
                'started_at': stage_data.get('started_at', ''),
                'completed_at': stage_data.get('completed_at', ''),
                'duration_seconds': stage_data.get('duration_seconds', ''),
                'retry_count': stage_data['retry_count'],
                'error': stage_data.get('error', ''),
                'added_at': content_data['added_at'],
                'pipeline_status': content_data['pipeline_status']
            })
    else:
        # Export all stages
        console.print("[cyan]Exporting all stages...[/cyan]\n")

        for content_id, content_data in tracker._cache.items():
            for stage_name in tracker.STAGES:
                stage_data = content_data['stages'][stage_name]
                rows.append({
                    'content_id': content_id,
                    'source': content_data['source'],
                    'title': content_data.get('title', ''),
                    'source_url': content_data['source_url'],
                    'stage': stage_name,
                    'status': stage_data['status'],
                    'started_at': stage_data.get('started_at', ''),
                    'completed_at': stage_data.get('completed_at', ''),
                    'duration_seconds': stage_data.get('duration_seconds', ''),
                    'retry_count': stage_data['retry_count'],
                    'error': stage_data.get('error', ''),
                    'added_at': content_data['added_at'],
                    'pipeline_status': content_data['pipeline_status']
                })

    # Write CSV
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

        console.print(f"[green]✓ Exported {len(rows)} rows to {csv_path}[/green]\n")

    except Exception as e:
        console.print(f"[red]✗ Export failed: {e}[/red]\n")
        sys.exit(1)


@cli.command()
def languages():
    """
    Show language distribution of transcripts in S3.

    Displays statistics about detected languages across all crawled videos.

    Example:
        python cli/tracking.py languages
    """
    setup_logging("INFO")

    console.print()
    console.print(Panel.fit(
        "[bold cyan]Language Distribution[/bold cyan]\n"
        "Transcript Languages in S3",
        border_style="cyan"
    ))
    console.print()

    try:
        tracker = get_tracker()

        # Count languages
        language_counts = {}
        total_videos = 0

        for content_id, content_data in tracker._cache.items():
            # Only count videos with completed stage 1
            stage_1 = content_data['stages']['stage_1_crawl']
            if stage_1['status'] == 'complete':
                # Get language from stage metadata (stored during crawl)
                stage_metadata = stage_1.get('metadata', {})
                language = stage_metadata.get('language', 'unknown')
                language_counts[language] = language_counts.get(language, 0) + 1
                total_videos += 1

        if not language_counts:
            console.print("[yellow]No completed transcripts found in S3[/yellow]\n")
            return

        # Sort by count (descending)
        sorted_languages = sorted(language_counts.items(), key=lambda x: x[1], reverse=True)

        # Language name mapping (ISO 639-1 codes)
        language_names = {
            'en': 'English',
            'hi': 'Hindi',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'it': 'Italian',
            'tr': 'Turkish',
            'vi': 'Vietnamese',
            'th': 'Thai',
            'pl': 'Polish',
            'nl': 'Dutch',
            'id': 'Indonesian',
            'sv': 'Swedish',
            'ro': 'Romanian',
            'unknown': 'Unknown'
        }

        # Create table
        table = Table(title=f"Language Distribution ({total_videos} videos)", box=box.ROUNDED)
        table.add_column("Language Code", style="cyan", width=15)
        table.add_column("Language Name", style="blue", width=20)
        table.add_column("Count", justify="right", style="green", width=10)
        table.add_column("Percentage", justify="right", style="yellow", width=12)

        for lang_code, count in sorted_languages:
            lang_name = language_names.get(lang_code, lang_code.upper())
            percentage = (count / total_videos) * 100
            table.add_row(
                lang_code,
                lang_name,
                str(count),
                f"{percentage:.1f}%"
            )

        console.print(table)
        console.print()

        # Summary stats
        console.print(f"[cyan]Total Videos:[/cyan] {total_videos}")
        console.print(f"[cyan]Unique Languages:[/cyan] {len(language_counts)}")
        console.print(f"[cyan]Most Common:[/cyan] {language_names.get(sorted_languages[0][0], sorted_languages[0][0])} ({sorted_languages[0][1]} videos)")
        console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"Language distribution error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument('content_id')
@click.option('--limit', '-l', type=int, default=None, help='Limit number of entities to display')
@click.option('--entity-type', '-t', type=str, default=None, help='Filter by entity type (e.g., restaurant, hotel, activity)')
@click.option('--sentiment', '-s', type=click.Choice(['positive', 'negative', 'neutral', 'mixed']), default=None, help='Filter by sentiment')
@click.option('--json', 'output_json', is_flag=True, help='Output raw JSON data')
def view_stage2(content_id: str, limit: Optional[int], entity_type: Optional[str], sentiment: Optional[str], output_json: bool):
    """
    View Stage 2 extracted entities for a specific video.

    Shows traveler profile and extracted entities (places, restaurants, activities)
    from the Stage 2 entity extraction output stored in S3.

    Examples:
        # View all entities for a video
        python cli/tracking.py view-stage2 youtube_abc123

        # View only restaurants
        python cli/tracking.py view-stage2 youtube_abc123 --entity-type restaurant

        # View first 10 positive entities
        python cli/tracking.py view-stage2 youtube_abc123 --limit 10 --sentiment positive

        # Export raw JSON
        python cli/tracking.py view-stage2 youtube_abc123 --json
    """
    import json

    setup_logging("INFO")

    console.print()
    console.print(Panel.fit(
        f"[bold blue]Stage 2 Extracted Data: {content_id}[/bold blue]",
        border_style="blue"
    ))
    console.print()

    try:
        tracker = get_tracker()
        storage = S3Storage()

        # Check if content exists
        if not tracker.content_exists(content_id):
            console.print(f"[red]✗ Content not found: {content_id}[/red]\n")
            return

        # Get content info
        info = tracker.get_content_info(content_id)
        stage2_data = info['stages'].get('stage_2_extract', {})

        # Check if Stage 2 is complete
        if stage2_data['status'] != 'complete':
            console.print(f"[yellow]⚠ Stage 2 status: {stage2_data['status']}[/yellow]")
            if stage2_data['status'] == 'not_started':
                console.print("[yellow]Run './crawl.sh process-stage2' to extract entities[/yellow]\n")
            elif stage2_data['status'] == 'failed':
                console.print(f"[red]Error: {stage2_data.get('error', 'Unknown error')}[/red]\n")
            return

        # Get S3 path
        s3_paths = stage2_data.get('s3_paths', [])
        if not s3_paths:
            console.print("[red]✗ No S3 paths found for Stage 2 data[/red]\n")
            return

        s3_path = s3_paths[0]  # First path is the extracted data
        console.print(f"[cyan]Loading from:[/cyan] {s3_path}\n")

        # Parse S3 path (format: s3://bucket/key)
        if not s3_path.startswith('s3://'):
            console.print(f"[red]✗ Invalid S3 path format: {s3_path}[/red]\n")
            return

        path_parts = s3_path.replace('s3://', '').split('/', 1)
        if len(path_parts) != 2:
            console.print(f"[red]✗ Invalid S3 path format: {s3_path}[/red]\n")
            return

        bucket_name = path_parts[0]
        s3_key = path_parts[1]

        # Download from S3
        try:
            response = storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
        except Exception as e:
            console.print(f"[red]✗ Failed to download from S3: {e}[/red]\n")
            return

        # Parse JSONL (first line contains the data)
        lines = content.strip().split('\n')
        if not lines:
            console.print("[red]✗ Empty file in S3[/red]\n")
            return

        data = json.loads(lines[0])

        # Output raw JSON if requested
        if output_json:
            console.print(json.dumps(data, indent=2))
            console.print()
            return

        # Extract traveler profile and entities
        traveler_profile = data.get('traveler_profile', {})
        entities = data.get('entities', [])

        # Display traveler profile
        profile_table = Table(title="Traveler Profile", box=box.ROUNDED, show_header=False)
        profile_table.add_column("Field", style="cyan", width=20)
        profile_table.add_column("Value", style="green", width=50)

        profile_table.add_row("Traveler Type", traveler_profile.get('traveler_type', 'unknown'))
        profile_table.add_row("Age Range", traveler_profile.get('age_range', 'unknown'))
        profile_table.add_row("Budget Tier", traveler_profile.get('budget_tier', 'unknown'))

        travel_style = traveler_profile.get('travel_style', [])
        if travel_style:
            profile_table.add_row("Travel Style", ", ".join(travel_style))

        confidence = traveler_profile.get('confidence_score', 0)
        profile_table.add_row("Confidence", f"{confidence:.2f}")

        console.print(profile_table)
        console.print()

        # Filter entities
        filtered_entities = entities
        if entity_type:
            filtered_entities = [e for e in filtered_entities if e.get('entity_type') == entity_type]
        if sentiment:
            filtered_entities = [e for e in filtered_entities if e.get('sentiment') == sentiment]
        if limit:
            filtered_entities = filtered_entities[:limit]

        # Display entities
        if not filtered_entities:
            console.print("[yellow]No entities found matching filters[/yellow]\n")
            return

        # Summary stats
        entity_types = {}
        sentiments = {'positive': 0, 'negative': 0, 'neutral': 0, 'mixed': 0}
        for entity in entities:
            entity_types[entity.get('entity_type', 'unknown')] = entity_types.get(entity.get('entity_type', 'unknown'), 0) + 1
            sentiments[entity.get('sentiment', 'neutral')] += 1

        # Stats table
        stats_table = Table(title="Entity Statistics", box=box.ROUNDED)
        stats_table.add_column("Metric", style="cyan", width=30)
        stats_table.add_column("Value", style="green", width=20)

        stats_table.add_row("Total Entities Extracted", str(len(entities)))
        stats_table.add_row("Entities Displayed", str(len(filtered_entities)))
        stats_table.add_row("Positive Sentiment", f"{sentiments['positive']} ({sentiments['positive']/len(entities)*100:.1f}%)")
        stats_table.add_row("Negative Sentiment", f"{sentiments['negative']} ({sentiments['negative']/len(entities)*100:.1f}%)")

        console.print(stats_table)
        console.print()

        # Entity type breakdown
        type_table = Table(title="Entity Types", box=box.ROUNDED)
        type_table.add_column("Type", style="cyan", width=20)
        type_table.add_column("Count", justify="right", style="green", width=10)
        type_table.add_column("Percentage", justify="right", style="yellow", width=12)

        for etype, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(entities)) * 100
            type_table.add_row(etype, str(count), f"{percentage:.1f}%")

        console.print(type_table)
        console.print()

        # Entities table
        entities_table = Table(title=f"Extracted Entities ({len(filtered_entities)} shown)", box=box.ROUNDED)
        entities_table.add_column("#", style="dim", width=4)
        entities_table.add_column("Name", style="cyan", width=25)
        entities_table.add_column("Type", style="blue", width=15)
        entities_table.add_column("Location", style="yellow", width=15)
        entities_table.add_column("Experience", style="white", width=40)
        entities_table.add_column("Sentiment", style="white", width=10)
        entities_table.add_column("Cost", style="green", width=15)

        for idx, entity in enumerate(filtered_entities, 1):
            # Color sentiment
            sentiment_value = entity.get('sentiment', 'neutral')
            if sentiment_value == 'positive':
                sentiment_display = f"[green]{sentiment_value}[/green]"
            elif sentiment_value == 'negative':
                sentiment_display = f"[red]{sentiment_value}[/red]"
            elif sentiment_value == 'mixed':
                sentiment_display = f"[yellow]{sentiment_value}[/yellow]"
            else:
                sentiment_display = sentiment_value

            # Truncate experience
            experience = entity.get('experience', '')
            if len(experience) > 80:
                experience = experience[:77] + "..."

            entities_table.add_row(
                str(idx),
                entity.get('entity_name', 'N/A'),
                entity.get('entity_type', 'unknown'),
                entity.get('location', 'N/A'),
                experience,
                sentiment_display,
                entity.get('cost_mentioned', 'N/A')
            )

        console.print(entities_table)
        console.print()

        # Show metadata
        metadata = stage2_data.get('metadata', {})
        console.print("[cyan]Processing Info:[/cyan]")
        console.print(f"  LLM Model: {metadata.get('llm_model', 'unknown')}")
        console.print(f"  Tokens Used: {metadata.get('tokens_used', 0):,}")
        console.print(f"  Cost: ${metadata.get('cost_usd', 0):.4f}")
        console.print(f"  Processing Time: {metadata.get('processing_time_seconds', 0):.1f}s")
        console.print(f"  Quality: {metadata.get('extraction_quality', 'unknown')}")
        console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"View Stage 2 error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option('--limit', '-l', type=int, default=10, help='Number of videos to list')
@click.option('--entity-type', '-t', type=str, default=None, help='Filter by entity type')
@click.option('--sort-by', type=click.Choice(['entities', 'cost', 'time', 'quality']), default='entities', help='Sort by metric')
def list_stage2(limit: int, entity_type: Optional[str], sort_by: str):
    """
    List all videos with Stage 2 data and their statistics.

    Shows a summary table of all processed videos with entity counts,
    costs, and quality metrics.

    Examples:
        # List top 10 videos by entity count
        python cli/tracking.py list-stage2

        # List top 20 by processing cost
        python cli/tracking.py list-stage2 --limit 20 --sort-by cost

        # List videos with restaurants
        python cli/tracking.py list-stage2 --entity-type restaurant
    """
    import json

    setup_logging("INFO")

    console.print()
    console.print(Panel.fit(
        "[bold blue]Stage 2 Processed Videos[/bold blue]",
        border_style="blue"
    ))
    console.print()

    try:
        tracker = get_tracker()
        storage = S3Storage()

        # Find all completed Stage 2 videos
        video_stats = []

        for content_id, content_data in tracker._cache.items():
            stage2_data = content_data['stages'].get('stage_2_extract', {})

            if stage2_data['status'] != 'complete':
                continue

            # Get metadata
            metadata = stage2_data.get('metadata', {})

            # If entity_type filter, need to load and check entities
            if entity_type:
                s3_paths = stage2_data.get('s3_paths', [])
                if not s3_paths:
                    continue

                s3_path = s3_paths[0]
                path_parts = s3_path.replace('s3://', '').split('/', 1)
                if len(path_parts) != 2:
                    continue

                bucket_name, s3_key = path_parts

                try:
                    response = storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
                    content = response['Body'].read().decode('utf-8')
                    data = json.loads(content.strip().split('\n')[0])
                    entities = data.get('entities', [])

                    # Filter by entity type
                    filtered_entities = [e for e in entities if e.get('entity_type') == entity_type]
                    if not filtered_entities:
                        continue

                    entity_count = len(filtered_entities)
                except Exception:
                    continue
            else:
                entity_count = metadata.get('entities_extracted', 0)

            video_stats.append({
                'content_id': content_id,
                'title': content_data.get('title', 'N/A')[:40],
                'entities': entity_count,
                'cost': metadata.get('cost_usd', 0),
                'time': metadata.get('processing_time_seconds', 0),
                'quality': metadata.get('extraction_quality', 'unknown'),
                'model': metadata.get('llm_model', 'unknown'),
                'tokens': metadata.get('tokens_used', 0)
            })

        if not video_stats:
            console.print("[yellow]No videos with completed Stage 2 found[/yellow]\n")
            return

        # Sort
        sort_key_map = {
            'entities': 'entities',
            'cost': 'cost',
            'time': 'time',
            'quality': 'quality'
        }
        video_stats.sort(key=lambda x: x[sort_key_map[sort_by]], reverse=True)

        # Limit
        video_stats = video_stats[:limit]

        # Display table
        table = Table(title=f"Stage 2 Processed Videos (Top {len(video_stats)})", box=box.ROUNDED)
        table.add_column("Video ID", style="cyan", width=20)
        table.add_column("Title", style="blue", width=42)
        table.add_column("Entities", justify="right", style="green", width=10)
        table.add_column("Quality", style="yellow", width=10)
        table.add_column("Cost", justify="right", style="magenta", width=10)
        table.add_column("Time", justify="right", style="white", width=8)

        total_entities = 0
        total_cost = 0
        total_tokens = 0

        for video in video_stats:
            # Truncate content_id for display
            display_id = video['content_id'].replace('youtube_', '')[:18]

            # Color quality
            quality = video['quality']
            if quality == 'high':
                quality_display = f"[green]{quality}[/green]"
            elif quality == 'medium':
                quality_display = f"[yellow]{quality}[/yellow]"
            elif quality == 'low':
                quality_display = f"[red]{quality}[/red]"
            else:
                quality_display = quality

            table.add_row(
                display_id,
                video['title'],
                str(video['entities']),
                quality_display,
                f"${video['cost']:.4f}",
                f"{video['time']:.1f}s"
            )

            total_entities += video['entities']
            total_cost += video['cost']
            total_tokens += video['tokens']

        console.print(table)
        console.print()

        # Summary
        console.print("[cyan]Summary:[/cyan]")
        console.print(f"  Total Videos: {len(video_stats)}")
        console.print(f"  Total Entities: {total_entities:,}")
        console.print(f"  Total Cost: ${total_cost:.4f}")
        console.print(f"  Total Tokens: {total_tokens:,}")
        console.print(f"  Avg Entities/Video: {total_entities/len(video_stats):.1f}")
        console.print(f"  Avg Cost/Video: ${total_cost/len(video_stats):.4f}")
        console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]\n")
        logger.error(f"List Stage 2 error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
