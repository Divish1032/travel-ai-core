#!/usr/bin/env python3
"""
Reset Stage 4 Vector Database

Deletes ChromaDB collections and Stage 4 metadata files.
Supports Chroma Cloud deployments only.

Usage:
    python reset_stage4.py --all                    # Reset everything
    python reset_stage4.py --collections all        # Reset all collections only
    python reset_stage4.py --collections entities   # Reset entities collection only
    python reset_stage4.py --metadata               # Reset metadata files only
    python reset_stage4.py --all --dry-run          # Preview what will be reset

Examples:
    # Reset everything with confirmation
    python reset_stage4.py --all

    # Reset specific collection
    python reset_stage4.py --collections entities,profiles

    # Preview reset without making changes
    python reset_stage4.py --all --dry-run

    # Force reset without confirmation (dangerous!)
    python reset_stage4.py --all --force
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging import get_logger
from src.vectordb import ChromaDBClient
from src.utils.config import config

logger = get_logger(__name__)


class Stage4Resetter:
    """Handle Stage 4 vector database and metadata reset operations."""

    def __init__(self, dry_run: bool = False, force: bool = False):
        """
        Initialize Stage 4 resetter.

        Args:
            dry_run: If True, only show what would be reset without making changes
            force: If True, skip confirmation prompts
        """
        self.dry_run = dry_run
        self.force = force
        self.chromadb_client: Optional[ChromaDBClient] = None
        self.metadata_dir = Path("stage4-vectors/metadata")

    def initialize_chromadb(self) -> bool:
        """
        Initialize ChromaDB client.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔌 Connecting to ChromaDB...")
            self.chromadb_client = ChromaDBClient.initialize_from_env()

            # Chroma Cloud mode only
            logger.info(f"   Mode: CHROMA CLOUD")

            # Always cloud mode now
            if False:
                db_path = self.chromadb_client.persist_directory or "./chroma_data"
                logger.info(f"   Path: {db_path}")

            # Show current stats
            self.chromadb_client.print_stats()

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to ChromaDB: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, int]:
        """
        Get current vector counts for all collections.

        Returns:
            Dict mapping collection name to vector count
        """
        stats = {}

        try:
            if self.chromadb_client.entities_collection:
                stats['entities'] = self.chromadb_client.entities_collection.count()
            else:
                stats['entities'] = 0

            if self.chromadb_client.profile_consensus_collection:
                stats['profile_consensus'] = self.chromadb_client.profile_consensus_collection.count()
            else:
                stats['profile_consensus'] = 0

            if self.chromadb_client.experiences_collection:
                stats['experiences'] = self.chromadb_client.experiences_collection.count()
            else:
                stats['experiences'] = 0

        except Exception as e:
            logger.error(f"❌ Failed to get collection stats: {e}")

        return stats

    def get_metadata_files(self) -> List[Path]:
        """
        Get list of all Stage 4 metadata files.

        Returns:
            List of metadata file paths
        """
        if not self.metadata_dir.exists():
            return []

        metadata_files = []
        for file in self.metadata_dir.glob("*.json"):
            metadata_files.append(file)

        return sorted(metadata_files)

    def reset_collection(self, collection_name: str) -> bool:
        """
        Reset a specific ChromaDB collection.

        Args:
            collection_name: Name of collection to reset

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.dry_run:
                logger.info(f"   [DRY-RUN] Would delete collection: {collection_name}")
                return True

            logger.info(f"   🗑️  Deleting collection: {collection_name}")

            # Delete collection
            self.chromadb_client.client.delete_collection(collection_name)

            # Recreate empty collection
            logger.info(f"   ✅ Creating fresh empty collection: {collection_name}")

            if collection_name == 'entities':
                self.chromadb_client.entities_collection = self.chromadb_client.client.get_or_create_collection(
                    name='entities',
                    metadata={"hnsw:space": "cosine"}
                )
            elif collection_name == 'profile_consensus':
                self.chromadb_client.profile_consensus_collection = self.chromadb_client.client.get_or_create_collection(
                    name='profile_consensus',
                    metadata={"hnsw:space": "cosine"}
                )
            elif collection_name == 'experiences':
                self.chromadb_client.experiences_collection = self.chromadb_client.client.get_or_create_collection(
                    name='experiences',
                    metadata={"hnsw:space": "cosine"}
                )

            logger.info(f"   ✅ Collection reset complete: {collection_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to reset collection {collection_name}: {e}")
            return False

    def reset_metadata_files(self) -> bool:
        """
        Delete all Stage 4 metadata files.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            metadata_files = self.get_metadata_files()

            if not metadata_files:
                logger.info("   No metadata files to delete")
                return True

            logger.info(f"   Found {len(metadata_files)} metadata files")

            for file in metadata_files:
                if self.dry_run:
                    logger.info(f"   [DRY-RUN] Would delete: {file.name}")
                else:
                    logger.info(f"   🗑️  Deleting: {file.name}")
                    file.unlink()

            if not self.dry_run:
                logger.info(f"   ✅ Deleted {len(metadata_files)} metadata files")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to reset metadata files: {e}")
            return False

    def show_reset_summary(
        self,
        collections_to_reset: List[str],
        reset_metadata: bool
    ) -> None:
        """
        Show summary of what will be reset.

        Args:
            collections_to_reset: List of collection names to reset
            reset_metadata: Whether to reset metadata files
        """
        logger.info("\n" + "=" * 80)
        logger.info("📋 RESET SUMMARY")
        logger.info("=" * 80)

        # Current state
        stats = self.get_collection_stats()
        total_vectors = sum(stats.values())

        logger.info("\n📊 Current State:")
        logger.info(f"   Entities:          {stats.get('entities', 0):6,} vectors")
        logger.info(f"   Profile Consensus: {stats.get('profile_consensus', 0):6,} vectors")
        logger.info(f"   Experiences:       {stats.get('experiences', 0):6,} vectors")
        logger.info(f"   {'─' * 40}")
        logger.info(f"   Total:             {total_vectors:6,} vectors")

        # Metadata files
        metadata_files = self.get_metadata_files()
        logger.info(f"\n📁 Metadata Files: {len(metadata_files)}")
        if metadata_files:
            for file in metadata_files[:5]:
                logger.info(f"   - {file.name}")
            if len(metadata_files) > 5:
                logger.info(f"   ... and {len(metadata_files) - 5} more")

        # What will be reset
        logger.info("\n🔄 Will Reset:")
        if collections_to_reset:
            logger.info(f"   Collections:")
            for collection in collections_to_reset:
                count = stats.get(collection, 0)
                logger.info(f"   - {collection:20s} ({count:,} vectors)")
        else:
            logger.info(f"   Collections: None")

        if reset_metadata:
            logger.info(f"   Metadata: {len(metadata_files)} files")
        else:
            logger.info(f"   Metadata: None")

        logger.info("=" * 80)

    def confirm_reset(self) -> bool:
        """
        Ask user to confirm reset operation.

        Returns:
            bool: True if confirmed, False otherwise
        """
        if self.force:
            logger.warning("⚠️  Force mode enabled - skipping confirmation")
            return True

        if self.dry_run:
            logger.info("\n🔍 DRY-RUN MODE - No changes will be made")
            return True

        logger.warning("\n⚠️  WARNING: This will permanently delete vector data!")
        response = input("\nType 'yes' to confirm reset: ")

        return response.lower() == 'yes'

    def execute_reset(
        self,
        collections: Optional[List[str]] = None,
        reset_metadata: bool = False,
        reset_all: bool = False
    ) -> bool:
        """
        Execute the reset operation.

        Args:
            collections: List of collection names to reset (or None)
            reset_metadata: Whether to reset metadata files
            reset_all: Whether to reset everything

        Returns:
            bool: True if successful, False otherwise
        """
        # Determine what to reset
        collections_to_reset = []

        if reset_all:
            collections_to_reset = ['entities', 'profile_consensus', 'experiences']
            reset_metadata = True
        elif collections:
            # Parse collection names
            if 'all' in collections:
                collections_to_reset = ['entities', 'profile_consensus', 'experiences']
            else:
                # Map short names to full names
                name_map = {
                    'entities': 'entities',
                    'entity': 'entities',
                    'profiles': 'profile_consensus',
                    'profile': 'profile_consensus',
                    'profile_consensus': 'profile_consensus',
                    'experiences': 'experiences',
                    'experience': 'experiences',
                    'exp': 'experiences'
                }

                for collection in collections:
                    full_name = name_map.get(collection.lower())
                    if full_name:
                        collections_to_reset.append(full_name)
                    else:
                        logger.error(f"❌ Unknown collection: {collection}")
                        return False

        if not collections_to_reset and not reset_metadata:
            logger.error("❌ Nothing to reset. Use --all, --collections, or --metadata")
            return False

        # Show summary
        self.show_reset_summary(collections_to_reset, reset_metadata)

        # Confirm
        if not self.confirm_reset():
            logger.info("❌ Reset cancelled by user")
            return False

        # Execute reset
        logger.info("\n" + "=" * 80)
        logger.info("🔄 EXECUTING RESET")
        logger.info("=" * 80)

        success = True

        # Reset collections
        if collections_to_reset:
            logger.info(f"\n🗑️  Resetting {len(collections_to_reset)} collections...")

            for collection_name in collections_to_reset:
                if not self.reset_collection(collection_name):
                    success = False

        # Reset metadata
        if reset_metadata:
            logger.info(f"\n🗑️  Resetting metadata files...")
            if not self.reset_metadata_files():
                success = False

        # Final status
        logger.info("\n" + "=" * 80)
        if success:
            if self.dry_run:
                logger.info("✅ DRY-RUN COMPLETE - No changes were made")
            else:
                logger.info("✅ RESET COMPLETE")

                # Show new state
                if collections_to_reset:
                    logger.info("\n📊 New State:")
                    new_stats = self.get_collection_stats()
                    logger.info(f"   Entities:          {new_stats.get('entities', 0):6,} vectors")
                    logger.info(f"   Profile Consensus: {new_stats.get('profile_consensus', 0):6,} vectors")
                    logger.info(f"   Experiences:       {new_stats.get('experiences', 0):6,} vectors")
        else:
            logger.error("❌ RESET FAILED - Some operations encountered errors")

        logger.info("=" * 80)

        return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reset Stage 4 Vector Database and Metadata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset everything (collections + metadata)
  python reset_stage4.py --all

  # Reset specific collections
  python reset_stage4.py --collections entities,profiles

  # Reset only metadata files
  python reset_stage4.py --metadata

  # Preview reset without making changes
  python reset_stage4.py --all --dry-run

  # Force reset without confirmation
  python reset_stage4.py --all --force
        """
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Reset all collections and metadata'
    )

    parser.add_argument(
        '--collections',
        type=str,
        help='Comma-separated list of collections to reset (entities,profiles,experiences) or "all"'
    )

    parser.add_argument(
        '--metadata',
        action='store_true',
        help='Reset metadata files only'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be reset without making changes'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompt (dangerous!)'
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

    # Banner
    logger.info("=" * 80)
    logger.info("🔄 STAGE 4 VECTOR DATABASE RESET")
    logger.info("=" * 80)

    if args.dry_run:
        logger.info("🔍 DRY-RUN MODE ENABLED")

    # Parse collections
    collections = None
    if args.collections:
        collections = [c.strip() for c in args.collections.split(',')]

    # Create resetter
    resetter = Stage4Resetter(dry_run=args.dry_run, force=args.force)

    # Initialize ChromaDB
    if not resetter.initialize_chromadb():
        logger.error("❌ Failed to initialize ChromaDB")
        sys.exit(1)

    # Execute reset
    success = resetter.execute_reset(
        collections=collections,
        reset_metadata=args.metadata or args.all,
        reset_all=args.all
    )

    # Exit
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
