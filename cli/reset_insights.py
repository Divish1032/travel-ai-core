#!/usr/bin/env python3
"""
Reset Insights Pipeline Processing

Resets insights pipeline data and metadata for reprocessing.

This script:
1. Deletes extracted insights from insights-pipeline/extracted/
2. Deletes canonical insights from insights-pipeline/canonical/
3. Deletes insight registry (tracks insight IDs and processed videos)
4. Resets insights_pipeline metadata in the tracker
5. Optionally moves files to processed/ instead of deleting

Usage:
    # Dry run (shows what would be reset)
    python cli/reset_insights.py --dry-run --all

    # Reset everything
    python cli/reset_insights.py --all

    # Reset specific videos
    python cli/reset_insights.py --video-ids abc123,xyz789

Examples:
    # Preview what will be reset
    ./crawl.sh reset-insights --dry-run --all

    # Reset all insights data
    ./crawl.sh reset-insights --all

    # Reset specific videos
    ./crawl.sh reset-insights --video-ids abc123,xyz789
"""

import sys
from pathlib import Path
from typing import List, Optional

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


def reset_insights_s3_data(
    s3: S3Storage,
    dry_run: bool = False
) -> dict:
    """
    Delete all insights data from S3.

    Args:
        s3: S3Storage instance
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("🗑️  Step 1: Deleting insights pipeline data...")

    prefixes = [
        'insights-pipeline/extracted/new/',
        'insights-pipeline/extracted/processed/',
        'insights-pipeline/canonical/',
        'insights-pipeline/filtered/'
    ]

    total_deleted = 0
    total_failed = 0
    deleted_by_prefix = {}

    for prefix in prefixes:
        try:
            response = s3.s3_client.list_objects_v2(
                Bucket=s3.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                logger.info(f"   No files found in {prefix}")
                deleted_by_prefix[prefix] = 0
                continue

            files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]

            logger.info(f"   Found {len(files)} files in {prefix}")

            deleted_count = 0
            for s3_key in files:
                filename = s3_key.split('/')[-1]

                if dry_run:
                    logger.debug(f"   [DRY RUN] Would delete: {filename}")
                    deleted_count += 1
                else:
                    try:
                        s3.s3_client.delete_object(
                            Bucket=s3.bucket_name,
                            Key=s3_key
                        )
                        logger.debug(f"   ✓ Deleted: {filename}")
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"   ✗ Failed to delete {filename}: {e}")
                        total_failed += 1

            deleted_by_prefix[prefix] = deleted_count
            total_deleted += deleted_count

        except Exception as e:
            logger.error(f"   Failed to process {prefix}: {e}")
            total_failed += 1

    logger.info(f"   Total files deleted: {total_deleted}")
    if total_failed > 0:
        logger.warning(f"   Failed deletions: {total_failed}")

    return {
        'deleted': total_deleted,
        'failed': total_failed,
        'by_prefix': deleted_by_prefix
    }


def reset_insight_registry(
    s3: S3Storage,
    dry_run: bool = False
) -> dict:
    """
    Delete insight registry from S3.

    Args:
        s3: S3Storage instance
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("🗑️  Step 2: Deleting insight registry...")

    registry_key = 'insights-pipeline/registry/insight_registry.json'

    try:
        # Check if registry exists
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=registry_key,
            MaxKeys=1
        )

        if 'Contents' not in response:
            logger.info("   No insight registry found")
            return {'deleted': 0, 'failed': 0}

        if dry_run:
            logger.info(f"   [DRY RUN] Would delete: {registry_key}")
            return {'deleted': 1, 'failed': 0}
        else:
            s3.s3_client.delete_object(
                Bucket=s3.bucket_name,
                Key=registry_key
            )
            logger.info(f"   ✓ Deleted: {registry_key}")
            return {'deleted': 1, 'failed': 0}

    except Exception as e:
        logger.error(f"   Failed to delete registry: {e}")
        return {'deleted': 0, 'failed': 1}


def reset_insights_metadata(
    metadata_tracker: MetadataTracker,
    video_ids: Optional[List[str]] = None,
    reset_all: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Reset insights_pipeline metadata status.

    Args:
        metadata_tracker: MetadataTracker instance
        video_ids: Optional list of specific video IDs to reset
        reset_all: If True, reset all videos
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    logger.info("🗑️  Step 3: Resetting insights_pipeline metadata...")

    if not reset_all and not video_ids:
        logger.warning("   No videos specified to reset")
        return {'reset': 0, 'failed': 0}

    all_videos = metadata_tracker.get_all_items()

    if reset_all:
        videos_to_reset = list(all_videos.keys())
    else:
        videos_to_reset = video_ids

    reset_count = 0
    failed_count = 0

    for video_id in videos_to_reset:
        if video_id not in all_videos:
            logger.warning(f"   Video {video_id} not found in metadata")
            failed_count += 1
            continue

        stages = all_videos[video_id]
        if 'insights_pipeline' not in stages:
            logger.debug(f"   Video {video_id} has no insights_pipeline metadata")
            continue

        if dry_run:
            logger.info(f"   [DRY RUN] Would reset: {video_id}")
            reset_count += 1
        else:
            try:
                # Reset insights_pipeline status to None
                metadata_tracker.metadata[video_id]['insights_pipeline'] = None
                reset_count += 1
                logger.debug(f"   ✓ Reset: {video_id}")
            except Exception as e:
                logger.error(f"   ✗ Failed to reset {video_id}: {e}")
                failed_count += 1

    if not dry_run and reset_count > 0:
        try:
            metadata_tracker.save()
            logger.info(f"   ✓ Saved metadata tracker")
        except Exception as e:
            logger.error(f"   ✗ Failed to save metadata: {e}")
            failed_count += 1

    logger.info(f"   Videos reset: {reset_count}")
    if failed_count > 0:
        logger.warning(f"   Failed resets: {failed_count}")

    return {'reset': reset_count, 'failed': failed_count}


@click.command()
@click.option(
    '--all',
    'reset_all',
    is_flag=True,
    help='Reset all insights data (required if --video-ids not specified)'
)
@click.option(
    '--video-ids',
    type=str,
    help='Comma-separated list of video IDs to reset (e.g., abc123,xyz789)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be reset without actually resetting'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(
    reset_all: bool,
    video_ids: Optional[str],
    dry_run: bool,
    log_level: str
):
    """
    Reset Insights Pipeline processing.

    Examples:

        # Preview what will be reset
        python cli/reset_insights.py --dry-run --all

        # Reset all insights data
        python cli/reset_insights.py --all

        # Reset specific videos
        python cli/reset_insights.py --video-ids abc123,xyz789
    """
    # Setup logging
    setup_logging(log_level=log_level)

    logger.info("=" * 80)
    logger.info("RESET INSIGHTS PIPELINE")
    logger.info("=" * 80)

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made\n")
    else:
        logger.warning("⚠️  WARNING: This will delete insights data!\n")

    # Validate inputs
    if not reset_all and not video_ids:
        logger.error("Error: Must specify either --all or --video-ids")
        logger.info("Run 'python cli/reset_insights.py --help' for usage")
        sys.exit(1)

    # Parse video IDs
    video_id_list = None
    if video_ids:
        video_id_list = [vid.strip() for vid in video_ids.split(',')]
        logger.info(f"Resetting {len(video_id_list)} specific videos\n")
    elif reset_all:
        logger.info("Resetting ALL insights data\n")

    # Confirm if not dry run
    if not dry_run:
        logger.warning("⚠️  This action cannot be undone!")
        response = input("Continue? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Reset cancelled")
            return

    # Initialize services
    try:
        s3_storage = S3Storage()
        metadata_tracker = MetadataTracker(s3_storage)
        logger.info("✓ Initialized storage and tracking\n")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Step 1: Delete S3 data
    s3_results = reset_insights_s3_data(s3_storage, dry_run=dry_run)

    # Step 2: Delete insight registry
    registry_results = reset_insight_registry(s3_storage, dry_run=dry_run)

    # Step 3: Reset metadata
    metadata_results = reset_insights_metadata(
        metadata_tracker,
        video_ids=video_id_list,
        reset_all=reset_all,
        dry_run=dry_run
    )

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("RESET SUMMARY")
    logger.info("=" * 80)

    logger.info(f"\nS3 Data:")
    logger.info(f"  Files deleted: {s3_results['deleted']}")
    if s3_results.get('by_prefix'):
        for prefix, count in s3_results['by_prefix'].items():
            short_prefix = prefix.replace('insights-pipeline/', '')
            logger.info(f"    - {short_prefix}: {count}")

    logger.info(f"\nInsight Registry:")
    logger.info(f"  Registry deleted: {'Yes' if registry_results['deleted'] > 0 else 'No'}")

    logger.info(f"\nMetadata:")
    logger.info(f"  Videos reset: {metadata_results['reset']}")

    total_failed = (
        s3_results['failed'] +
        registry_results['failed'] +
        metadata_results['failed']
    )

    if total_failed > 0:
        logger.warning(f"\n⚠️  Total failures: {total_failed}")

    if dry_run:
        logger.info("\n🔍 This was a dry run - no changes were made")
        logger.info("Run without --dry-run to actually reset")
    else:
        logger.info("\n✅ Reset complete!")
        logger.info("\nNext steps:")
        logger.info("1. Run: ./crawl.sh process-insights")
        logger.info("2. Insights will be re-extracted and processed")

    logger.info("=" * 80)


if __name__ == '__main__':
    main()
