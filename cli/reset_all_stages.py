#!/usr/bin/env python3
"""
Reset All Pipeline Data with Automatic Backup

This script provides a complete reset of the TravelAI pipeline with automatic backup:
1. Creates a timestamped backup folder in S3
2. Backs up all pipeline data (metadata, raw, stage2-extracted, stage3-audit, stage3-canonical)
   - stage3-canonical includes: entities, registry, and score_history subdirectories
3. Deletes ALL original data after successful backup (including metadata folder)
4. Fresh metadata will be created automatically on next pipeline run

Usage:
    python cli/reset_all_stages.py --backup            # Backup and reset (SAFE - creates backup)
    python cli/reset_all_stages.py --backup --dry-run  # Preview what will be backed up/reset
    python cli/reset_all_stages.py --force             # Reset WITHOUT backup (DANGEROUS!)
    python cli/reset_all_stages.py --backup-only       # Only backup, don't delete

Options:
    --backup         Create backup before reset (RECOMMENDED)
    --backup-only    Only create backup, don't delete data
    --force          Skip backup and reset immediately (DANGEROUS - NO RECOVERY!)
    --dry-run        Show what would be done without making changes
    --yes            Skip all confirmation prompts
    --keep-metadata  Don't delete metadata folder (preserve processing history)

Safety Features:
    - Requires explicit confirmation unless --yes flag is used
    - Creates timestamped backups by default
    - Validates backup completion before deletion
    - Provides detailed logs of all operations
    - Dry-run mode to preview changes

Example Workflow:
    # Safe reset with backup (RECOMMENDED)
    ./crawl.sh reset-all --backup

    # Preview what will happen
    ./crawl.sh reset-all --backup --dry-run

    # Backup only (no deletion)
    ./crawl.sh reset-all --backup-only

    # DANGEROUS: Reset without backup (not recommended)
    ./crawl.sh reset-all --force --yes
"""

import sys
import os
import json
import click
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import get_logger

logger = get_logger(__name__)


class StageResetManager:
    """
    Manages complete pipeline reset with automatic backup.
    """

    def __init__(self, s3_storage: S3Storage, tracker: MetadataTracker):
        self.s3 = s3_storage
        self.tracker = tracker
        self.backup_timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        # S3 prefixes for each stage (backup entire folders)
        # Note: stage3-canonical/ includes registry/ and score_history/ subdirectories
        self.stage_prefixes = {
            'metadata': 'metadata/',
            'raw': 'raw/',
            'stage2_extracted': 'stage2-extracted/',
            'stage3_audit': 'stage3-audit/',
            'stage3_canonical': 'stage3-canonical/',
        }

        # Backup prefix
        self.backup_prefix = f'backups/{self.backup_timestamp}/'

    def count_objects(self, prefix: str) -> int:
        """Count number of objects with given prefix."""
        try:
            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=prefix,
                MaxKeys=1000
            )
            count = response.get('KeyCount', 0)

            # If there are more than 1000 objects, count them all
            if response.get('IsTruncated', False):
                paginator = self.s3.s3_client.get_paginator('list_objects_v2')
                total = 0
                for page in paginator.paginate(Bucket=self.s3.bucket_name, Prefix=prefix):
                    total += page.get('KeyCount', 0)
                return total

            return count
        except Exception as e:
            logger.error(f"Error counting objects for {prefix}: {e}")
            return 0

    def list_all_objects(self, prefix: str) -> List[str]:
        """List all S3 object keys with given prefix."""
        keys = []
        try:
            paginator = self.s3.s3_client.get_paginator('list_objects_v2')

            for page in paginator.paginate(Bucket=self.s3.bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    keys.extend([obj['Key'] for obj in page['Contents']])

            logger.info(f"Found {len(keys)} objects with prefix: {prefix}")
            return keys

        except Exception as e:
            logger.error(f"Error listing objects for {prefix}: {e}")
            return []

    def backup_objects(self, source_prefix: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Backup all objects from source prefix to backup location.

        Returns dict with backup stats.
        """
        logger.info(f"🔍 Scanning objects in: {source_prefix}")

        # List all source objects
        source_keys = self.list_all_objects(source_prefix)

        if not source_keys:
            logger.warning(f"⚠️  No objects found at {source_prefix}")
            return {
                'source_prefix': source_prefix,
                'total_objects': 0,
                'backed_up': 0,
                'failed': 0,
                'skipped': 0
            }

        logger.info(f"📦 Found {len(source_keys)} objects to backup")

        backed_up = 0
        failed = 0

        for i, source_key in enumerate(source_keys, 1):
            # Calculate backup key (preserve structure)
            relative_key = source_key[len(source_prefix):] if source_key.startswith(source_prefix) else source_key
            backup_key = f"{self.backup_prefix}{source_prefix}{relative_key}"

            if dry_run:
                logger.debug(f"[DRY RUN] Would copy: {source_key} → {backup_key}")
                backed_up += 1
                continue

            try:
                # Copy object to backup location
                copy_source = {'Bucket': self.s3.bucket_name, 'Key': source_key}

                self.s3.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.s3.bucket_name,
                    Key=backup_key,
                    MetadataDirective='COPY'
                )

                backed_up += 1

                if i % 100 == 0:
                    logger.info(f"   Backed up {i}/{len(source_keys)} objects...")

            except Exception as e:
                logger.error(f"   Failed to backup {source_key}: {e}")
                failed += 1

        result = {
            'source_prefix': source_prefix,
            'total_objects': len(source_keys),
            'backed_up': backed_up,
            'failed': failed,
            'skipped': len(source_keys) - backed_up - failed
        }

        if not dry_run:
            logger.info(f"✅ Backup complete: {backed_up}/{len(source_keys)} objects backed up")
            if failed > 0:
                logger.warning(f"⚠️  {failed} objects failed to backup")

        return result

    def delete_objects(self, prefix: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Delete all objects with given prefix.

        Returns dict with deletion stats.
        """
        logger.info(f"🗑️  Deleting objects from: {prefix}")

        # List all objects to delete
        keys_to_delete = self.list_all_objects(prefix)

        if not keys_to_delete:
            logger.info(f"✅ No objects to delete at {prefix}")
            return {
                'prefix': prefix,
                'total_objects': 0,
                'deleted': 0,
                'failed': 0
            }

        logger.info(f"📦 Found {len(keys_to_delete)} objects to delete")

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {len(keys_to_delete)} objects")
            return {
                'prefix': prefix,
                'total_objects': len(keys_to_delete),
                'deleted': len(keys_to_delete),  # Would be deleted
                'failed': 0
            }

        deleted = 0
        failed = 0

        # Delete in batches of 1000 (S3 limit)
        batch_size = 1000
        for i in range(0, len(keys_to_delete), batch_size):
            batch = keys_to_delete[i:i + batch_size]

            try:
                # Prepare delete request
                objects_to_delete = [{'Key': key} for key in batch]

                response = self.s3.s3_client.delete_objects(
                    Bucket=self.s3.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )

                deleted += len(response.get('Deleted', []))
                failed += len(response.get('Errors', []))

                logger.info(f"   Deleted {deleted}/{len(keys_to_delete)} objects...")

            except Exception as e:
                logger.error(f"   Failed to delete batch: {e}")
                failed += len(batch)

        result = {
            'prefix': prefix,
            'total_objects': len(keys_to_delete),
            'deleted': deleted,
            'failed': failed
        }

        logger.info(f"✅ Deletion complete: {deleted}/{len(keys_to_delete)} objects deleted")
        if failed > 0:
            logger.warning(f"⚠️  {failed} objects failed to delete")

        return result

    def reset_metadata_tracker(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Reset metadata tracker for all stages.

        Returns dict with reset stats.
        """
        logger.info("🔄 Resetting metadata tracker...")

        if dry_run:
            # Count how many videos would be affected
            all_items = self.tracker.get_all_items()
            video_count = len(all_items)
            logger.info(f"[DRY RUN] Would reset metadata for {video_count} videos to not_started state")
            return {
                'reset': True,
                'videos_affected': video_count
            }

        # Get all content metadata
        try:
            all_items = self.tracker.get_all_items()
            video_count = len(all_items)

            logger.info(f"📊 Found {video_count} videos in metadata tracker")

            # Reset all stages for all videos
            for content_id in list(all_items.keys()):
                # Reset each stage to not_started
                for stage_name in ['stage_1_crawl', 'stage_2_extract', 'stage_3_deduplicate']:
                    try:
                        self.tracker.reset_stage(content_id=content_id, stage=stage_name)
                        logger.debug(f"Reset {stage_name} for {content_id}")
                    except Exception as e:
                        logger.warning(f"Failed to reset {stage_name} for {content_id}: {e}")

            logger.info(f"✅ Reset metadata for {video_count} videos")

            return {
                'reset': True,
                'videos_affected': video_count
            }

        except Exception as e:
            logger.error(f"❌ Failed to reset metadata: {e}")
            return {
                'reset': False,
                'error': str(e)
            }

    def create_backup_manifest(self, backup_results: Dict[str, Any], dry_run: bool = False):
        """Create a manifest file describing the backup."""
        manifest = {
            'backup_timestamp': self.backup_timestamp,
            'backup_prefix': self.backup_prefix,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'dry_run': dry_run,
            'stages_backed_up': list(backup_results.keys()),
            'backup_details': backup_results,
            'total_objects_backed_up': sum(r.get('backed_up', 0) for r in backup_results.values()),
            'total_objects_failed': sum(r.get('failed', 0) for r in backup_results.values())
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would create backup manifest at: {self.backup_prefix}manifest.json")
            logger.info(f"[DRY RUN] Manifest content: {json.dumps(manifest, indent=2)}")
            return

        try:
            manifest_key = f"{self.backup_prefix}manifest.json"

            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=manifest_key,
                Body=json.dumps(manifest, indent=2),
                ContentType='application/json'
            )

            logger.info(f"✅ Backup manifest created: s3://{self.s3.bucket_name}/{manifest_key}")

        except Exception as e:
            logger.error(f"⚠️  Failed to create backup manifest: {e}")


def reset_all_stages(
    backup: bool = True,
    backup_only: bool = False,
    force: bool = False,
    dry_run: bool = False,
    keep_metadata: bool = False,
    skip_confirmation: bool = False
):
    """
    Complete reset of Stages 1, 2, and 3 with optional backup.
    """
    logger.info("=" * 80)
    logger.info("🔄 TravelAI Pipeline Complete Reset")
    logger.info("=" * 80)

    # Initialize
    s3 = S3Storage()
    tracker = MetadataTracker(s3)
    manager = StageResetManager(s3, tracker)

    # Show summary of what will be affected
    logger.info("\n📊 Scanning S3 bucket...")

    stage_counts = {}
    for stage_name, prefix in manager.stage_prefixes.items():
        count = manager.count_objects(prefix)
        stage_counts[stage_name] = count
        logger.info(f"   {stage_name}: {count} objects at {prefix}")

    total_objects = sum(stage_counts.values())

    if total_objects == 0:
        logger.warning("⚠️  No objects found. Nothing to reset.")
        return

    logger.info(f"\n📦 Total objects: {total_objects}")

    # Show mode
    if dry_run:
        logger.info("\n🔍 DRY RUN MODE - No changes will be made")

    if backup:
        logger.info(f"\n💾 Backup location: s3://{s3.bucket_name}/{manager.backup_prefix}")

    if force and not backup:
        logger.warning("\n⚠️  FORCE MODE - NO BACKUP WILL BE CREATED!")
        logger.warning("⚠️  DATA WILL BE PERMANENTLY DELETED!")

    # Confirmation
    if not skip_confirmation and not dry_run:
        logger.info("\n" + "=" * 80)
        if backup and not backup_only:
            logger.info("This will:")
            logger.info("  1. Create backup of all pipeline data (metadata, raw, stage2-extracted, stage3-audit, stage3-canonical)")
            if keep_metadata:
                logger.info("  2. Delete pipeline data after backup (KEEPING metadata folder)")
                logger.info("  3. Processing history will be preserved")
            else:
                logger.info("  2. Delete ALL original data after backup (including metadata folder)")
                logger.info("  3. Fresh metadata will be created on next pipeline run")
        elif backup_only:
            logger.info("This will:")
            logger.info("  1. Create backup of all pipeline data (metadata, raw, stage2-extracted, stage3-audit, stage3-canonical)")
            logger.info("  2. Keep original data intact (backup only)")
        elif force:
            if keep_metadata:
                logger.info("⚠️  This will PERMANENTLY DELETE pipeline data (KEEPING metadata) WITHOUT BACKUP!")
            else:
                logger.info("⚠️  This will PERMANENTLY DELETE all pipeline data (including metadata) WITHOUT BACKUP!")

        logger.info("=" * 80)

        response = input("\nType 'yes' to confirm: ").strip().lower()
        if response != 'yes':
            logger.info("❌ Reset cancelled")
            return

    # Step 1: Backup (if requested)
    backup_results = {}

    if backup or backup_only:
        logger.info("\n" + "=" * 80)
        logger.info("📦 Step 1: Creating Backup")
        logger.info("=" * 80)

        for stage_name, prefix in manager.stage_prefixes.items():
            logger.info(f"\n🔄 Backing up {stage_name}...")
            result = manager.backup_objects(prefix, dry_run=dry_run)
            backup_results[stage_name] = result

        # Create backup manifest
        manager.create_backup_manifest(backup_results, dry_run=dry_run)

        total_backed_up = sum(r.get('backed_up', 0) for r in backup_results.values())
        total_failed = sum(r.get('failed', 0) for r in backup_results.values())

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ Backup Summary: {total_backed_up}/{total_objects} objects backed up")
        if total_failed > 0:
            logger.warning(f"⚠️  {total_failed} objects failed to backup")
        logger.info("=" * 80)

        if total_failed > 0 and not force:
            logger.error("\n❌ Backup had failures. Aborting deletion for safety.")
            logger.error("Use --force to delete anyway (not recommended)")
            return

    # Stop if backup-only mode
    if backup_only:
        logger.info("\n✅ Backup complete. Original data preserved (--backup-only mode)")
        return

    # Step 2: Delete original data
    if not backup_only:
        logger.info("\n" + "=" * 80)
        logger.info("🗑️  Step 2: Deleting Original Data")
        logger.info("=" * 80)

        deletion_results = {}

        for stage_name, prefix in manager.stage_prefixes.items():
            # Skip metadata deletion if --keep-metadata flag is set
            if stage_name == 'metadata' and keep_metadata:
                logger.info(f"\n⏭️  Skipping {stage_name} deletion (--keep-metadata flag)")
                continue

            logger.info(f"\n🔄 Deleting {stage_name}...")
            result = manager.delete_objects(prefix, dry_run=dry_run)
            deletion_results[stage_name] = result

        total_deleted = sum(r.get('deleted', 0) for r in deletion_results.values())
        total_del_failed = sum(r.get('failed', 0) for r in deletion_results.values())

        logger.info("\n" + "=" * 80)
        logger.info(f"✅ Deletion Summary: {total_deleted}/{total_objects} objects deleted")
        if total_del_failed > 0:
            logger.warning(f"⚠️  {total_del_failed} objects failed to delete")
        logger.info("=" * 80)

    # Step 3: Metadata status
    if not backup_only:
        logger.info("\n" + "=" * 80)
        logger.info("🔄 Step 3: Metadata Status")
        logger.info("=" * 80)

        if keep_metadata:
            if dry_run:
                logger.info("[DRY RUN] Metadata folder will be preserved (--keep-metadata)")
                logger.info("[DRY RUN] Existing metadata tracker will remain intact")
            else:
                logger.info("✅ Metadata folder preserved (backed up to backup location)")
                logger.info("💡 Existing processing history maintained")
        else:
            if dry_run:
                logger.info("[DRY RUN] Metadata folder will be deleted (backed up first)")
                logger.info("[DRY RUN] Fresh metadata will be created on next pipeline run")
            else:
                logger.info("✅ Metadata folder deleted (backed up to backup location)")
                logger.info("💡 Fresh metadata will be created automatically on next pipeline run")

    # Final summary
    logger.info("\n" + "=" * 80)
    if dry_run:
        logger.info("🔍 DRY RUN COMPLETE - No changes were made")
    elif backup_only:
        logger.info("✅ BACKUP COMPLETE")
        logger.info(f"📦 Backup location: s3://{s3.bucket_name}/{manager.backup_prefix}")
    else:
        logger.info("✅ RESET COMPLETE")
        if backup:
            logger.info(f"📦 Backup saved to: s3://{s3.bucket_name}/{manager.backup_prefix}")
        logger.info("🔄 All stages reset to initial state")
        logger.info("💡 You can now re-run the pipeline from scratch")
    logger.info("=" * 80)


@click.command()
@click.option('--backup', is_flag=True, default=False, help='Create backup before reset (RECOMMENDED)')
@click.option('--backup-only', is_flag=True, default=False, help='Only backup, do not delete')
@click.option('--force', is_flag=True, default=False, help='Reset WITHOUT backup (DANGEROUS!)')
@click.option('--dry-run', is_flag=True, default=False, help='Show what would be done without making changes')
@click.option('--yes', is_flag=True, default=False, help='Skip confirmation prompts')
@click.option('--keep-metadata', is_flag=True, default=False, help='Do not delete metadata folder (preserve processing history)')
def main(backup, backup_only, force, dry_run, yes, keep_metadata):
    """
    Reset all stages (1, 2, 3) with automatic backup.

    RECOMMENDED: Use --backup flag to create a backup before reset.

    Examples:
        # Safe reset with backup
        python cli/reset_all_stages.py --backup

        # Preview what will happen
        python cli/reset_all_stages.py --backup --dry-run

        # Backup only (no deletion)
        python cli/reset_all_stages.py --backup-only

        # DANGEROUS: Reset without backup
        python cli/reset_all_stages.py --force --yes
    """
    # Validate flags
    if backup_only and force:
        click.echo("Error: Cannot use --backup-only and --force together")
        sys.exit(1)

    if not backup and not force:
        click.echo("Error: Must specify either --backup or --force")
        click.echo("  --backup: Create backup before reset (RECOMMENDED)")
        click.echo("  --force:  Reset without backup (DANGEROUS!)")
        sys.exit(1)

    try:
        reset_all_stages(
            backup=backup or backup_only,
            backup_only=backup_only,
            force=force,
            dry_run=dry_run,
            keep_metadata=keep_metadata,
            skip_confirmation=yes
        )

    except KeyboardInterrupt:
        logger.info("\n❌ Reset cancelled by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n❌ Reset failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
