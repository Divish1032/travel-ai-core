#!/usr/bin/env python3
"""
Reset Stage 3 Processing

Resets Stage 3 canonical entities and moves Stage 2 files back for reprocessing.

This script:
1. Deletes all Stage 3 canonical entities from stage3-canonical/entities/
2. Moves Stage 2 files from stage2-extracted/stage3_extracted/ back to stage2-extracted/new/
3. Resets Stage 3 metadata in the tracker
4. Deletes entity registry (which tracks entity IDs and processed videos)
5. Deletes score history (which tracks entity score evolution)

Usage:
    # Dry run (shows what would be reset)
    python cli/reset_stage3.py --dry-run --all

    # Reset everything
    python cli/reset_stage3.py --all

    # Reset specific videos
    python cli/reset_stage3.py --video-ids abc123,xyz789

Examples:
    # Preview what will be reset
    ./crawl.sh reset-stage3 --dry-run --all

    # Reset all Stage 3 data
    ./crawl.sh reset-stage3 --all

    # Reset specific videos
    ./crawl.sh reset-stage3 --video-ids abc123,xyz789
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


def reset_stage3_s3_data(
    s3: S3Storage,
    dry_run: bool = False
) -> dict:
    """
    Delete all Stage 3 canonical entities from S3.

    Args:
        s3: S3Storage instance
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("🗑️  Step 1: Deleting Stage 3 canonical entities...")

    prefix = 'stage3-canonical/entities/'
    deleted_files = []
    failed_deletes = []

    try:
        # List all files in stage3-canonical/entities/
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=prefix
        )

        if 'Contents' not in response:
            logger.info("   No Stage 3 files found to delete")
            return {
                'deleted': 0,
                'failed': 0,
                'files': []
            }

        files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]

        logger.info(f"   Found {len(files)} files to delete")

        for s3_key in files:
            filename = s3_key.split('/')[-1]

            if dry_run:
                logger.info(f"   [DRY RUN] Would delete: {filename}")
                deleted_files.append(filename)
            else:
                try:
                    s3.s3_client.delete_object(
                        Bucket=s3.bucket_name,
                        Key=s3_key
                    )
                    logger.debug(f"   Deleted: {filename}")
                    deleted_files.append(filename)
                except Exception as e:
                    logger.error(f"   Failed to delete {filename}: {e}")
                    failed_deletes.append(filename)

        if not dry_run:
            logger.info(f"   ✅ Deleted {len(deleted_files)} files from stage3-canonical/entities/")
        else:
            logger.info(f"   [DRY RUN] Would delete {len(deleted_files)} files")

        return {
            'deleted': len(deleted_files),
            'failed': len(failed_deletes),
            'files': deleted_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to delete Stage 3 data: {e}")
        return {
            'deleted': 0,
            'failed': 0,
            'error': str(e)
        }


def move_stage2_files_back(
    s3: S3Storage,
    video_ids: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Move Stage 2 files from stage3_extracted back to new.

    Args:
        s3: S3Storage instance
        video_ids: Optional list of specific video IDs to move. If None, moves all.
        dry_run: If True, only show what would be moved

    Returns:
        Dict with move results
    """
    logger.info("📦 Step 2: Moving Stage 2 files back to new/...")

    source_prefix = 'stage2-extracted/stage3_extracted/'
    dest_prefix = 'stage2-extracted/new/'
    moved_files = []
    failed_moves = []

    try:
        # List all files in stage2-extracted/stage3_extracted/
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=source_prefix
        )

        if 'Contents' not in response:
            logger.info("   No Stage 2 files found to move back")
            return {
                'moved': 0,
                'failed': 0,
                'files': []
            }

        files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]

        # Filter by video_ids if specified
        if video_ids:
            filtered_files = []
            for s3_key in files:
                filename = s3_key.split('/')[-1]
                # Extract video_id from filename: youtube_video_{video_id}_extracted.jsonl
                for video_id in video_ids:
                    if f'youtube_video_{video_id}_extracted.jsonl' in filename:
                        filtered_files.append(s3_key)
                        break
            files = filtered_files

        if not files:
            logger.info("   No matching files found to move")
            return {
                'moved': 0,
                'failed': 0,
                'files': []
            }

        logger.info(f"   Found {len(files)} files to move back")

        for source_key in files:
            filename = source_key.split('/')[-1]
            dest_key = dest_prefix + filename

            if dry_run:
                logger.info(f"   [DRY RUN] Would move: {filename}")
                moved_files.append(filename)
            else:
                try:
                    # Copy to destination
                    s3.s3_client.copy_object(
                        CopySource={'Bucket': s3.bucket_name, 'Key': source_key},
                        Bucket=s3.bucket_name,
                        Key=dest_key
                    )

                    # Delete source
                    s3.s3_client.delete_object(
                        Bucket=s3.bucket_name,
                        Key=source_key
                    )

                    logger.debug(f"   Moved: {filename}")
                    moved_files.append(filename)
                except Exception as e:
                    logger.error(f"   Failed to move {filename}: {e}")
                    failed_moves.append(filename)

        if not dry_run:
            logger.info(f"   ✅ Moved {len(moved_files)} files back to stage2-extracted/new/")
        else:
            logger.info(f"   [DRY RUN] Would move {len(moved_files)} files")

        return {
            'moved': len(moved_files),
            'failed': len(failed_moves),
            'files': moved_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to move Stage 2 files: {e}")
        return {
            'moved': 0,
            'failed': 0,
            'error': str(e)
        }


def reset_stage3_metadata(
    tracker: MetadataTracker,
    video_ids: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Reset Stage 3 metadata in the tracker.

    Args:
        tracker: MetadataTracker instance
        video_ids: Optional list of specific video IDs to reset. If None, resets all.
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    logger.info("📊 Step 3: Resetting Stage 3 metadata...")

    reset_count = 0
    failed_resets = []
    content_to_reset_ids = []

    try:
        # Get all content items
        all_items = tracker.get_all_items()

        # Filter content that has stage_3_deduplicate status
        for content_id in all_items:
            content_info = tracker.get_content_info(content_id)
            if not content_info:
                continue

            stages = content_info.get('stages', {})

            # Check if Stage 3 exists for this content
            if 'stage_3_deduplicate' in stages:
                # If video_ids specified, filter by those
                if video_ids:
                    if any(vid in content_id for vid in video_ids):
                        content_to_reset_ids.append(content_id)
                else:
                    content_to_reset_ids.append(content_id)

        logger.info(f"   Found {len(content_to_reset_ids)} videos to reset metadata")

        for content_id in content_to_reset_ids:
            if dry_run:
                logger.info(f"   [DRY RUN] Would reset: {content_id}")
                reset_count += 1
            else:
                try:
                    # Use the reset_stage method from MetadataTracker
                    tracker.reset_stage(
                        content_id=content_id,
                        stage='stage_3_deduplicate'
                    )
                    logger.debug(f"   Reset: {content_id}")
                    reset_count += 1
                except Exception as e:
                    logger.error(f"   Failed to reset {content_id}: {e}")
                    failed_resets.append(content_id)

        if not dry_run:
            # Save metadata (batch save at the end)
            tracker.save_to_s3()
            logger.info(f"   ✅ Reset metadata for {reset_count} videos")
        else:
            logger.info(f"   [DRY RUN] Would reset {reset_count} videos")

        return {
            'reset': reset_count,
            'failed': len(failed_resets),
            'videos': content_to_reset_ids
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to reset metadata: {e}")
        return {
            'reset': 0,
            'failed': 0,
            'error': str(e)
        }


def reset_entity_registry(
    s3: S3Storage,
    dry_run: bool = False
) -> dict:
    """
    Delete entity registry from S3.

    The entity registry tracks entity IDs and processed videos.
    Must be reset when resetting Stage 3 to avoid stale tracking data.

    Args:
        s3: S3Storage instance
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("🗂️  Step 4: Resetting entity registry...")

    # Registry files are stored in stage3-canonical/registry/
    prefix = 'stage3-canonical/registry/'
    deleted_files = []

    try:
        # List all files in registry/
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=prefix
        )

        if 'Contents' not in response:
            logger.info("   No entity registry found to delete")
            return {
                'deleted': 0,
                'files': []
            }

        files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]

        logger.info(f"   Found {len(files)} registry files to delete")

        for s3_key in files:
            filename = s3_key.split('/')[-1]

            if dry_run:
                logger.info(f"   [DRY RUN] Would delete: {filename}")
                deleted_files.append(filename)
            else:
                try:
                    s3.s3_client.delete_object(
                        Bucket=s3.bucket_name,
                        Key=s3_key
                    )
                    logger.debug(f"   Deleted: {filename}")
                    deleted_files.append(filename)
                except Exception as e:
                    logger.error(f"   Failed to delete {filename}: {e}")

        if not dry_run:
            logger.info(f"   ✅ Deleted {len(deleted_files)} registry files")
        else:
            logger.info(f"   [DRY RUN] Would delete {len(deleted_files)} registry files")

        return {
            'deleted': len(deleted_files),
            'files': deleted_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to delete entity registry: {e}")
        return {
            'deleted': 0,
            'error': str(e)
        }


def reset_score_history(
    s3: S3Storage,
    dry_run: bool = False
) -> dict:
    """
    Delete score history from S3.

    Score history tracks entity score evolution over time.
    Must be reset when resetting Stage 3 to avoid stale score data.

    Args:
        s3: S3Storage instance
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("📈 Step 5: Resetting score history...")

    # Score history files are stored in stage3-canonical/score_history/
    prefix = 'stage3-canonical/score_history/'
    deleted_files = []

    try:
        # List all files in score-history/
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=prefix
        )

        if 'Contents' not in response:
            logger.info("   No score history found to delete")
            return {
                'deleted': 0,
                'files': []
            }

        files = [obj['Key'] for obj in response['Contents'] if not obj['Key'].endswith('/')]

        logger.info(f"   Found {len(files)} score history files to delete")

        for s3_key in files:
            filename = s3_key.split('/')[-1]

            if dry_run:
                logger.info(f"   [DRY RUN] Would delete: {filename}")
                deleted_files.append(filename)
            else:
                try:
                    s3.s3_client.delete_object(
                        Bucket=s3.bucket_name,
                        Key=s3_key
                    )
                    logger.debug(f"   Deleted: {filename}")
                    deleted_files.append(filename)
                except Exception as e:
                    logger.error(f"   Failed to delete {filename}: {e}")

        if not dry_run:
            logger.info(f"   ✅ Deleted {len(deleted_files)} score history files")
        else:
            logger.info(f"   [DRY RUN] Would delete {len(deleted_files)} score history files")

        return {
            'deleted': len(deleted_files),
            'files': deleted_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to delete score history: {e}")
        return {
            'deleted': 0,
            'error': str(e)
        }


@click.command()
@click.option(
    '--all',
    'reset_all',
    is_flag=True,
    help='Reset all Stage 3 data (required if not using --video-ids)'
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
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(reset_all: bool, video_ids: str, dry_run: bool, log_level: str):
    """
    Reset Stage 3 processing data.

    This command:
    1. Deletes all Stage 3 canonical entities from S3
    2. Moves Stage 2 files back to new/ for reprocessing
    3. Resets Stage 3 metadata in the tracker
    4. Deletes entity registry (tracks entity IDs and processed videos)
    5. Deletes score history (tracks entity score evolution)

    Examples:

        # Preview what will be reset
        python cli/reset_stage3.py --dry-run --all

        # Reset everything
        python cli/reset_stage3.py --all

        # Reset specific videos
        python cli/reset_stage3.py --video-ids abc123,xyz789

        # Dry run for specific videos
        python cli/reset_stage3.py --video-ids abc123,xyz789 --dry-run
    """
    # Setup logging
    setup_logging(log_level=log_level)

    # Validate arguments
    if not reset_all and not video_ids:
        logger.error("❌ Must specify either --all or --video-ids")
        logger.info("Usage:")
        logger.info("  Reset all: ./crawl.sh reset-stage3 --all")
        logger.info("  Reset specific: ./crawl.sh reset-stage3 --video-ids abc123,xyz789")
        sys.exit(1)

    # Parse video IDs
    video_id_list = None
    if video_ids:
        video_id_list = [vid.strip() for vid in video_ids.split(',')]
        logger.info(f"Resetting {len(video_id_list)} specific videos")
    else:
        logger.info("Resetting ALL Stage 3 data")

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")

    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3 RESET")
    logger.info("=" * 80)

    try:
        # Initialize S3 and tracker
        s3 = S3Storage()
        tracker = MetadataTracker(s3)

        # Step 1: Delete Stage 3 canonical entities
        if reset_all or not video_ids:
            # Only delete all Stage 3 data if resetting all
            s3_result = reset_stage3_s3_data(s3, dry_run=dry_run)
        else:
            # If resetting specific videos, don't delete Stage 3 data
            # (it contains data from multiple videos)
            logger.info("🗑️  Step 1: Skipping Stage 3 deletion (resetting specific videos)")
            logger.info("   Stage 3 canonical entities contain data from multiple videos")
            logger.info("   Run with --all to delete all Stage 3 data")
            s3_result = {'deleted': 0, 'failed': 0, 'files': []}

        # Step 2: Move Stage 2 files back
        move_result = move_stage2_files_back(s3, video_ids=video_id_list, dry_run=dry_run)

        # Step 3: Reset metadata
        metadata_result = reset_stage3_metadata(tracker, video_ids=video_id_list, dry_run=dry_run)

        # Step 4: Reset entity registry (only if resetting all)
        if reset_all or not video_ids:
            registry_result = reset_entity_registry(s3, dry_run=dry_run)
        else:
            logger.info("🗂️  Step 4: Skipping entity registry reset (resetting specific videos)")
            logger.info("   Entity registry contains data from multiple videos")
            logger.info("   Run with --all to reset the entire registry")
            registry_result = {'deleted': 0, 'files': []}

        # Step 5: Reset score history (only if resetting all)
        if reset_all or not video_ids:
            score_history_result = reset_score_history(s3, dry_run=dry_run)
        else:
            logger.info("📈 Step 5: Skipping score history reset (resetting specific videos)")
            logger.info("   Score history contains data from multiple videos")
            logger.info("   Run with --all to reset all score history")
            score_history_result = {'deleted': 0, 'files': []}

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("RESET SUMMARY")
        logger.info("=" * 80)

        if dry_run:
            logger.info("🔍 DRY RUN RESULTS:")
        else:
            logger.info("✅ RESET COMPLETE:")

        logger.info(f"\nStage 3 Canonical Entities:")
        logger.info(f"  Deleted: {s3_result['deleted']} files")
        if s3_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {s3_result['failed']} files")

        logger.info(f"\nStage 2 Files:")
        logger.info(f"  Moved back: {move_result['moved']} files")
        if move_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {move_result['failed']} files")

        logger.info(f"\nMetadata:")
        logger.info(f"  Reset: {metadata_result['reset']} videos")
        if metadata_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {metadata_result['failed']} videos")

        logger.info(f"\nEntity Registry:")
        logger.info(f"  Deleted: {registry_result['deleted']} files")

        logger.info(f"\nScore History:")
        logger.info(f"  Deleted: {score_history_result['deleted']} files")

        logger.info("\n" + "=" * 80)

        if dry_run:
            logger.info("\n💡 This was a dry run. Run without --dry-run to actually reset.")
        else:
            logger.info("\n✅ Stage 3 has been reset. You can now run Stage 3 processing again.")
            logger.info("   Command: ./crawl.sh process-stage3")

        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrupted by user")
        sys.exit(130)

    except Exception as e:
        logger.error(f"❌ Reset failed: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
