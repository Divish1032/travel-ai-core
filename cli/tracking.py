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


if __name__ == "__main__":
    cli()
