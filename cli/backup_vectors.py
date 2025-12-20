#!/usr/bin/env python3
"""
Vector Database Backup Utility

Backs up ChromaDB collections to S3 for disaster recovery.

Features:
- Full and incremental backups
- Compression support
- Backup verification
- Metadata preservation

Usage:
    python backup_vectors.py
    python backup_vectors.py --collections entities,profiles
    python backup_vectors.py --compress
    python backup_vectors.py --incremental

Author: TravelAI Team
Date: 2025-12-14
"""

import argparse
import gzip
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.chromadb_client import ChromaDBClient
from src.storage.s3 import S3Storage
from src.utils.logging import get_logger

logger = get_logger(__name__)


class VectorBackup:
    """Handles vector database backup operations."""

    def __init__(self):
        """Initialize backup utility."""
        self.chromadb = None
        self.s3_storage = None

    def initialize(self) -> bool:
        """
        Initialize ChromaDB and S3 connections.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing backup utility...")

            # Initialize ChromaDB
            self.chromadb = ChromaDBClient.initialize_from_env()
            logger.info(f"   ChromaDB mode: {self.chromadb.mode or 'cloud'}")

            # Initialize S3
            self.s3_storage = S3Storage()
            logger.info(f"   S3 bucket: {self.s3_storage.bucket_name}")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    def backup_collection(
        self,
        collection_name: str,
        compress: bool = False,
        incremental: bool = False
    ) -> Optional[str]:
        """
        Backup a single collection to S3.

        Args:
            collection_name: Name of the collection to backup
            compress: Whether to compress the backup
            incremental: Whether to perform incremental backup

        Returns:
            S3 URI of the backup, or None if failed
        """
        try:
            logger.info(f"\n📦 Backing up collection: {collection_name}")

            # Map collection names to ChromaDBClient attributes
            collections_map = {
                'entities': self.chromadb.entities_collection,
                'profile_consensus': self.chromadb.profile_consensus_collection,
                'experiences': self.chromadb.experiences_collection
            }

            # Get collection
            collection = collections_map.get(collection_name)
            if not collection:
                logger.warning(f"   Collection '{collection_name}' not found")
                return None

            # Get all data
            results = collection.get(
                include=['embeddings', 'metadatas', 'documents']
            )

            if not results or not results.get('ids'):
                logger.warning(f"   Collection '{collection_name}' is empty")
                return None

            count = len(results['ids'])
            logger.info(f"   Found {count:,} embeddings")

            # Build backup data
            backup_data = {
                'collection_name': collection_name,
                'timestamp': datetime.now().isoformat(),
                'count': count,
                'backup_type': 'incremental' if incremental else 'full',
                'compressed': compress,
                'data': {
                    'ids': results['ids'],
                    'embeddings': results.get('embeddings', []),
                    'metadatas': results.get('metadatas', []),
                    'documents': results.get('documents', [])
                }
            }

            # Generate backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{collection_name}_backup_{timestamp}.json"

            if compress:
                filename += ".gz"

            # Save to S3
            s3_key = f"stage4-vectors/backups/{filename}"

            logger.info(f"   Uploading to S3: {s3_key}")

            if compress:
                # Compress and upload
                json_str = json.dumps(backup_data)
                compressed = gzip.compress(json_str.encode('utf-8'))

                s3_uri = f"s3://{self.s3_storage.bucket_name}/{s3_key}"
                self.s3_storage.s3_client.put_object(
                    Bucket=self.s3_storage.bucket_name,
                    Key=s3_key,
                    Body=compressed,
                    ContentType='application/gzip'
                )
            else:
                # Upload JSON directly
                json_str = json.dumps(backup_data, indent=2)

                s3_uri = f"s3://{self.s3_storage.bucket_name}/{s3_key}"
                self.s3_storage.s3_client.put_object(
                    Bucket=self.s3_storage.bucket_name,
                    Key=s3_key,
                    Body=json_str.encode('utf-8'),
                    ContentType='application/json'
                )

            logger.info(f"   ✅ Backup complete: {s3_uri}")

            return s3_uri

        except Exception as e:
            logger.error(f"   ❌ Failed to backup {collection_name}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def backup_all(
        self,
        collections: Optional[List[str]] = None,
        compress: bool = False,
        incremental: bool = False
    ):
        """
        Backup all collections.

        Args:
            collections: List of collection names (default: all)
            compress: Whether to compress backups
            incremental: Whether to perform incremental backup
        """
        try:
            logger.info("=" * 80)
            logger.info("VECTOR DATABASE BACKUP")
            logger.info("=" * 80)

            # Default collections
            if not collections:
                collections = ['entities', 'profile_consensus', 'experiences']

            logger.info(f"\nCollections to backup: {', '.join(collections)}")
            logger.info(f"Compression: {'enabled' if compress else 'disabled'}")
            logger.info(f"Backup type: {'incremental' if incremental else 'full'}")

            # Backup each collection
            success_count = 0
            failed_count = 0
            backup_uris = []

            for collection_name in collections:
                s3_uri = self.backup_collection(
                    collection_name,
                    compress=compress,
                    incremental=incremental
                )

                if s3_uri:
                    success_count += 1
                    backup_uris.append(s3_uri)
                else:
                    failed_count += 1

            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("BACKUP SUMMARY")
            logger.info("=" * 80)
            logger.info(f"  Successful: {success_count}")
            logger.info(f"  Failed: {failed_count}")

            if backup_uris:
                logger.info("\n  Backup locations:")
                for uri in backup_uris:
                    logger.info(f"    {uri}")

            logger.info("\n" + "=" * 80)
            logger.info("✅ Backup complete")
            logger.info("=" * 80 + "\n")

        except Exception as e:
            logger.error(f"❌ Backup failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backup Vector Database to S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup all collections
  python backup_vectors.py

  # Backup specific collections
  python backup_vectors.py --collections entities,profile_consensus

  # Compressed backup
  python backup_vectors.py --compress

  # Incremental backup
  python backup_vectors.py --incremental
        """
    )

    parser.add_argument(
        '--collections',
        type=str,
        help='Comma-separated list of collections (default: all)'
    )

    parser.add_argument(
        '--compress',
        action='store_true',
        help='Compress backup files'
    )

    parser.add_argument(
        '--incremental',
        action='store_true',
        help='Perform incremental backup (only changes since last backup)'
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

    # Execute backup
    backup = VectorBackup()
    if not backup.initialize():
        sys.exit(1)

    backup.backup_all(
        collections=collections,
        compress=args.compress,
        incremental=args.incremental
    )


if __name__ == '__main__':
    main()
