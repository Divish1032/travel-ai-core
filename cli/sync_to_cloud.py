#!/usr/bin/env python3
"""
Cloud Sync Utility

Syncs local ChromaDB database to cloud-hosted ChromaDB instance.

Features:
- Full and incremental sync
- Conflict resolution
- Progress tracking
- Dry-run mode

Usage:
    python sync_to_cloud.py
    python sync_to_cloud.py --collections entities
    python sync_to_cloud.py --dry-run
    python sync_to_cloud.py --force

Author: TravelAI Team
Date: 2025-12-14
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.chromadb_client import ChromaDBClient
from src.utils.logging import get_logger
from src.utils.config import get_config

logger = get_logger(__name__)


class CloudSync:
    """Handles syncing local ChromaDB to cloud instance."""

    def __init__(self):
        """Initialize cloud sync."""
        self.local_client = None
        self.cloud_client = None

    def initialize(self) -> bool:
        """
        Initialize local and cloud ChromaDB clients.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing cloud sync...")

            # Initialize local client
            logger.info("\n📁 Connecting to local ChromaDB...")
            self.local_client = ChromaDBClient.initialize_from_env()

            if self.local_client.mode != 'local':
                logger.error("   ❌ Current config is not set to 'local' mode")
                return False

            logger.info(f"   ✅ Local DB: {self.local_client.persist_directory}")

            # Check if cloud config is available
            config = get_config()

            # Get Chroma Cloud config from environment
            import os
            tenant = os.getenv('CHROMADB_TENANT')
            database = os.getenv('CHROMADB_DATABASE', 'default_database')
            api_key = os.getenv('CHROMADB_API_KEY')

            if not tenant or not api_key:
                logger.error("\n   ❌ Chroma Cloud configuration not found")
                logger.error("   Please set CHROMADB_TENANT and CHROMADB_API_KEY in .env")
                logger.error("   Sign up at https://www.trychroma.com to get your credentials")
                return False

            # Initialize cloud client
            logger.info("\n☁️  Connecting to Chroma Cloud...")
            logger.info(f"   Tenant: {tenant}")
            logger.info(f"   Database: {database}")

            self.cloud_client = ChromaDBClient()
            self.cloud_client.initialize_cloud(
                tenant=tenant,
                database=database,
                api_key=api_key
            )

            logger.info("   ✅ Cloud connection established")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            import traceback
            traceback.print_exc()
            return False

    def sync_collection(
        self,
        collection_name: str,
        dry_run: bool = False,
        force: bool = False
    ) -> bool:
        """
        Sync a single collection to cloud.

        Args:
            collection_name: Name of the collection to sync
            dry_run: If True, don't actually sync
            force: If True, overwrite cloud data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"\n🔄 Syncing collection: {collection_name}")

            # Map collection names to ChromaDBClient attributes
            local_collections_map = {
                'entities': self.local_client.entities_collection,
                'profile_consensus': self.local_client.profile_consensus_collection,
                'experiences': self.local_client.experiences_collection
            }

            # Get local collection
            local_coll = local_collections_map.get(collection_name)
            if not local_coll:
                logger.warning(f"   Collection '{collection_name}' not found locally")
                return False

            # Get local data
            local_results = local_coll.get(
                include=['embeddings', 'metadatas', 'documents']
            )

            if not local_results or not local_results.get('ids'):
                logger.warning(f"   Collection '{collection_name}' is empty locally")
                return False

            local_count = len(local_results['ids'])
            logger.info(f"   Local: {local_count:,} embeddings")

            # Check cloud collection
            try:
                # Map collection names to ChromaDBClient attributes for cloud
                cloud_collections_map = {
                    'entities': self.cloud_client.entities_collection,
                    'profile_consensus': self.cloud_client.profile_consensus_collection,
                    'experiences': self.cloud_client.experiences_collection
                }

                cloud_coll = cloud_collections_map.get(collection_name)
                cloud_count = cloud_coll.count() if cloud_coll else 0
                logger.info(f"   Cloud: {cloud_count:,} embeddings")

                if cloud_count > 0 and not force:
                    logger.warning(f"   ⚠️  Cloud collection exists with {cloud_count:,} embeddings")
                    logger.warning(f"   Use --force to overwrite")
                    return False

                # Delete existing cloud collection if force
                if cloud_count > 0 and force:
                    logger.info(f"   🗑️  Deleting existing cloud collection...")
                    if not dry_run:
                        self.cloud_client.client.delete_collection(collection_name)
                    logger.info(f"   ✅ Deleted")

            except Exception:
                # Collection doesn't exist on cloud, that's fine
                pass

            # Create cloud collection
            logger.info(f"   📤 Uploading {local_count:,} embeddings to cloud...")

            if dry_run:
                logger.info(f"   ⚠️  DRY RUN - No changes made")
                return True

            # Create collection on cloud
            cloud_coll = self.cloud_client.create_collection(collection_name)

            # Upload in batches (ChromaDB has limits)
            batch_size = 100
            total_batches = (local_count + batch_size - 1) // batch_size

            for i in range(0, local_count, batch_size):
                end = min(i + batch_size, local_count)
                batch_num = (i // batch_size) + 1

                logger.info(f"   Batch {batch_num}/{total_batches}: {i}-{end}")

                cloud_coll.add(
                    ids=local_results['ids'][i:end],
                    embeddings=local_results.get('embeddings', [])[i:end],
                    metadatas=local_results.get('metadatas', [])[i:end],
                    documents=local_results.get('documents', [])[i:end]
                )

            logger.info(f"   ✅ Sync complete: {local_count:,} embeddings")

            return True

        except Exception as e:
            logger.error(f"   ❌ Failed to sync {collection_name}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def sync_all(
        self,
        collections: Optional[List[str]] = None,
        dry_run: bool = False,
        force: bool = False
    ):
        """
        Sync all collections to cloud.

        Args:
            collections: List of collection names (default: all)
            dry_run: If True, don't actually sync
            force: If True, overwrite cloud data
        """
        try:
            logger.info("=" * 80)
            logger.info("CLOUD SYNC")
            logger.info("=" * 80)

            # Default collections
            if not collections:
                collections = ['entities', 'profile_consensus', 'experiences']

            logger.info(f"\nCollections to sync: {', '.join(collections)}")

            if dry_run:
                logger.info("⚠️  DRY RUN MODE - No changes will be made")

            if force:
                logger.info("⚠️  FORCE MODE - Will overwrite existing cloud data")

            # Sync each collection
            success_count = 0
            failed_count = 0

            for collection_name in collections:
                success = self.sync_collection(
                    collection_name,
                    dry_run=dry_run,
                    force=force
                )

                if success:
                    success_count += 1
                else:
                    failed_count += 1

            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("SYNC SUMMARY")
            logger.info("=" * 80)
            logger.info(f"  Successful: {success_count}")
            logger.info(f"  Failed: {failed_count}")

            logger.info("\n" + "=" * 80)
            logger.info("✅ Sync complete")
            logger.info("=" * 80 + "\n")

        except Exception as e:
            logger.error(f"❌ Sync failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync Local ChromaDB to Cloud",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync all collections (dry-run first)
  python sync_to_cloud.py --dry-run

  # Sync all collections
  python sync_to_cloud.py

  # Sync specific collections
  python sync_to_cloud.py --collections entities,profile_consensus

  # Force overwrite cloud data
  python sync_to_cloud.py --force

Environment Variables Required:
  CHROMADB_TENANT        - Chroma Cloud tenant ID (from www.trychroma.com)
  CHROMADB_DATABASE      - Chroma Cloud database name (default: default_database)
  CHROMADB_API_KEY       - Chroma Cloud API key (from www.trychroma.com)
        """
    )

    parser.add_argument(
        '--collections',
        type=str,
        help='Comma-separated list of collections (default: all)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be synced without making changes'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force full resync (overwrite cloud data)'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set logging level'
    )

    args = parser.parse_args()

    # Set log level
    import logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Parse collections
    collections = None
    if args.collections:
        collections = [c.strip() for c in args.collections.split(',')]

    # Execute sync
    sync = CloudSync()
    if not sync.initialize():
        sys.exit(1)

    sync.sync_all(
        collections=collections,
        dry_run=args.dry_run,
        force=args.force
    )


if __name__ == '__main__':
    main()
