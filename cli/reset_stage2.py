#!/usr/bin/env python3
"""
Reset Stage 2 Processing

Resets Stage 2 entity extraction and moves Stage 1 files back for reprocessing.

This script:
1. Deletes all Stage 2 extracted entities from stage2-extracted/ folders
2. Moves Stage 1 files from raw/stage2_processed/ back to raw/new/
3. Resets Stage 2 metadata in the tracker

Usage:
    # Dry run (shows what would be reset)
    python cli/reset_stage2.py --dry-run

    # Reset everything
    python cli/reset_stage2.py --all

    # Reset specific videos
    python cli/reset_stage2.py --video-ids abc123,xyz789

Examples:
    # Preview what will be reset
    ./crawl.sh reset-stage2 --dry-run

    # Reset all Stage 2 data
    ./crawl.sh reset-stage2 --all

    # Reset specific videos
    ./crawl.sh reset-stage2 --video-ids abc123,xyz789
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


def delete_stage2_s3_data(
    s3: S3Storage,
    video_ids: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Delete Stage 2 extracted entities from S3.

    Args:
        s3: S3Storage instance
        video_ids: Optional list of specific video IDs to delete. If None, deletes all.
        dry_run: If True, only show what would be deleted

    Returns:
        Dict with deletion results
    """
    logger.info("🗑️  Step 1: Deleting Stage 2 extracted entities...")

    # Prefixes to delete from
    prefixes = [
        'stage2-extracted/new/',
        'stage2-extracted/stage3_processed/'
    ]

    deleted_files = []
    failed_deletes = []

    try:
        for prefix in prefixes:
            # List all files in prefix
            response = s3.s3_client.list_objects_v2(
                Bucket=s3.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                logger.info(f"   No files found in {prefix}")
                continue

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
                logger.info(f"   No matching files in {prefix}")
                continue

            logger.info(f"   Found {len(files)} files to delete from {prefix}")

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
            logger.info(f"   ✅ Deleted {len(deleted_files)} files from stage2-extracted/")
        else:
            logger.info(f"   [DRY RUN] Would delete {len(deleted_files)} files")

        return {
            'deleted': len(deleted_files),
            'failed': len(failed_deletes),
            'files': deleted_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to delete Stage 2 data: {e}")
        return {
            'deleted': 0,
            'failed': 0,
            'error': str(e)
        }


def move_stage1_files_back(
    s3: S3Storage,
    video_ids: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Move Stage 1 files from stage2_processed back to new.

    Args:
        s3: S3Storage instance
        video_ids: Optional list of specific video IDs to move. If None, moves all.
        dry_run: If True, only show what would be moved

    Returns:
        Dict with move results
    """
    logger.info("📦 Step 2: Moving Stage 1 files back to new/...")

    source_prefix = 'raw/stage2_processed/'
    dest_prefix = 'raw/new/'
    moved_files = []
    failed_moves = []

    try:
        # List all files in raw/stage2_processed/
        response = s3.s3_client.list_objects_v2(
            Bucket=s3.bucket_name,
            Prefix=source_prefix
        )

        if 'Contents' not in response:
            logger.info("   No Stage 1 files found to move back")
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
                # Extract video_id from filename: youtube_video_{video_id}.jsonl
                for video_id in video_ids:
                    if f'youtube_video_{video_id}.jsonl' in filename:
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
            logger.info(f"   ✅ Moved {len(moved_files)} files back to raw/new/")
        else:
            logger.info(f"   [DRY RUN] Would move {len(moved_files)} files")

        return {
            'moved': len(moved_files),
            'failed': len(failed_moves),
            'files': moved_files
        }

    except Exception as e:
        logger.error(f"   ❌ Failed to move Stage 1 files: {e}")
        return {
            'moved': 0,
            'failed': 0,
            'error': str(e)
        }


def reset_stage2_metadata(
    tracker: MetadataTracker,
    s3: S3Storage,
    video_ids: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Reset Stage 2 metadata in the tracker.

    Args:
        tracker: MetadataTracker instance
        s3: S3Storage instance (for updating Stage 1 s3_paths)
        video_ids: Optional list of specific video IDs to reset. If None, resets all.
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    logger.info("📊 Step 3: Resetting Stage 2 metadata...")

    reset_count = 0
    failed_resets = []
    content_to_reset_ids = []

    try:
        # Get all content items
        all_items = tracker.get_all_items()

        # Filter content that has stage_2_extract status
        for content_id in all_items:
            content_info = tracker.get_content_info(content_id)
            if not content_info:
                continue

            stages = content_info.get('stages', {})

            # Check if Stage 2 exists for this content
            if 'stage_2_extract' in stages:
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
                        stage='stage_2_extract'
                    )

                    # IMPORTANT: Update Stage 1 s3_paths to point back to raw/new/
                    # When Stage 2 processes, it moves files from raw/new/ to raw/stage2_processed/
                    # When we reset, we move them back, so we need to update the s3_paths
                    if content_id in tracker._cache:
                        stage1_data = tracker._cache[content_id]['stages'].get('stage_1_crawl', {})
                        if stage1_data and 's3_paths' in stage1_data:
                            # Update s3_paths to point back to raw/new/
                            old_paths = stage1_data['s3_paths']
                            new_paths = []
                            for old_path in old_paths:
                                # Replace raw/stage2_processed/ with raw/new/
                                if 'raw/stage2_processed/' in old_path:
                                    new_path = old_path.replace('raw/stage2_processed/', 'raw/new/')
                                    new_paths.append(new_path)
                                    logger.debug(f"   Updated s3_path: {old_path} -> {new_path}")
                                else:
                                    new_paths.append(old_path)

                            tracker._cache[content_id]['stages']['stage_1_crawl']['s3_paths'] = new_paths

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


@click.command()
@click.option(
    '--all',
    'reset_all',
    is_flag=True,
    help='Reset all Stage 2 data (required if not using --video-ids)'
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
    Reset Stage 2 processing data.

    This command:
    1. Deletes all Stage 2 extracted entities from S3
    2. Moves Stage 1 files back to new/ for reprocessing
    3. Resets Stage 2 metadata in the tracker

    Examples:

        # Preview what will be reset
        python cli/reset_stage2.py --dry-run --all

        # Reset everything
        python cli/reset_stage2.py --all

        # Reset specific videos
        python cli/reset_stage2.py --video-ids abc123,xyz789

        # Dry run for specific videos
        python cli/reset_stage2.py --video-ids abc123,xyz789 --dry-run
    """
    # Setup logging
    setup_logging(log_level=log_level)

    # Validate arguments
    if not reset_all and not video_ids:
        logger.error("❌ Must specify either --all or --video-ids")
        logger.info("Usage:")
        logger.info("  Reset all: ./crawl.sh reset-stage2 --all")
        logger.info("  Reset specific: ./crawl.sh reset-stage2 --video-ids abc123,xyz789")
        sys.exit(1)

    # Parse video IDs
    video_id_list = None
    if video_ids:
        video_id_list = [vid.strip() for vid in video_ids.split(',')]
        logger.info(f"Resetting {len(video_id_list)} specific videos")
    else:
        logger.info("Resetting ALL Stage 2 data")

    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")

    logger.info("\n" + "=" * 80)
    logger.info("STAGE 2 RESET")
    logger.info("=" * 80)

    try:
        # Initialize S3 and tracker
        s3 = S3Storage()
        tracker = MetadataTracker(s3)

        # Step 1: Delete Stage 2 extracted entities
        s3_result = delete_stage2_s3_data(s3, video_ids=video_id_list, dry_run=dry_run)

        # Step 2: Move Stage 1 files back
        move_result = move_stage1_files_back(s3, video_ids=video_id_list, dry_run=dry_run)

        # Step 3: Reset metadata
        metadata_result = reset_stage2_metadata(tracker, s3, video_ids=video_id_list, dry_run=dry_run)

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("RESET SUMMARY")
        logger.info("=" * 80)

        if dry_run:
            logger.info("🔍 DRY RUN RESULTS:")
        else:
            logger.info("✅ RESET COMPLETE:")

        logger.info(f"\nStage 2 Extracted Entities:")
        logger.info(f"  Deleted: {s3_result['deleted']} files")
        if s3_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {s3_result['failed']} files")

        logger.info(f"\nStage 1 Files:")
        logger.info(f"  Moved back: {move_result['moved']} files")
        if move_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {move_result['failed']} files")

        logger.info(f"\nMetadata:")
        logger.info(f"  Reset: {metadata_result['reset']} videos")
        if metadata_result.get('failed', 0) > 0:
            logger.info(f"  Failed: {metadata_result['failed']} videos")

        logger.info("\n" + "=" * 80)

        if dry_run:
            logger.info("\n💡 This was a dry run. Run without --dry-run to actually reset.")
        else:
            logger.info("\n✅ Stage 2 has been reset. You can now run Stage 2 processing again.")
            logger.info("   Command: ./crawl.sh process-stage2")

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
