#!/usr/bin/env python3
"""
Stage 4 Statistics and Metrics

Displays comprehensive statistics for the Stage 4 vector database including:
- Collection sizes and embedding counts
- Cost and token usage
- Performance metrics
- Storage utilization

Usage:
    python stage4_stats.py
    python stage4_stats.py --detailed
    python stage4_stats.py --json

Author: TravelAI Team
Date: 2025-12-14
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.chromadb_client import ChromaDBClient
from src.utils.stage4_tracker import Stage4Tracker
from src.utils.logging import get_logger

logger = get_logger(__name__)


def format_bytes(bytes_count: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}min"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}hr"


def get_collection_stats(chromadb: ChromaDBClient) -> Dict[str, Any]:
    """
    Get statistics for all collections.

    Returns:
        Dictionary with collection statistics
    """
    stats = {}

    # Access collections directly as attributes
    collections_map = {
        'entities': chromadb.entities_collection,
        'profile_consensus': chromadb.profile_consensus_collection,
        'experiences': chromadb.experiences_collection
    }

    for collection_name, collection in collections_map.items():
        try:
            if collection:
                count = collection.count()

                # Estimate storage size (gte-large: 1024 dimensions * 4 bytes per float)
                embedding_size = count * 1024 * 4 if count > 0 else 0

                stats[collection_name] = {
                    'count': count,
                    'storage_bytes': embedding_size,
                    'storage_formatted': format_bytes(embedding_size)
                }
            else:
                stats[collection_name] = {
                    'count': 0,
                    'storage_bytes': 0,
                    'storage_formatted': '0 B'
                }
        except Exception as e:
            logger.warning(f"Error getting stats for {collection_name}: {e}")
            stats[collection_name] = {
                'count': 0,
                'storage_bytes': 0,
                'storage_formatted': '0 B',
                'error': str(e)
            }

    return stats


def display_stats(detailed: bool = False):
    """
    Display Stage 4 statistics.

    Args:
        detailed: Whether to show detailed statistics
    """
    try:
        logger.info("=" * 80)
        logger.info("STAGE 4 VECTOR DATABASE STATISTICS")
        logger.info("=" * 80)

        # Initialize ChromaDB
        logger.info("\n🔌 Connecting to ChromaDB...")
        chromadb = ChromaDBClient.initialize_from_env()

        mode = chromadb.mode or "local"
        logger.info(f"   Mode: {mode.upper()}")

        if mode == "cloud":
            logger.info(f"   Host: {chromadb.host or 'unknown'}")
        else:
            logger.info(f"   Path: {chromadb.persist_directory or './chroma_data'}")

        # Get collection stats
        logger.info("\n📊 Collection Statistics:")
        logger.info("=" * 80)

        collection_stats = get_collection_stats(chromadb)

        total_embeddings = 0
        total_storage = 0

        for name, stats in collection_stats.items():
            count = stats['count']
            storage = stats['storage_formatted']

            total_embeddings += count
            total_storage += stats['storage_bytes']

            logger.info(f"\n  {name.title()}:")
            logger.info(f"    Embeddings: {count:,}")
            logger.info(f"    Storage: {storage}")

            if 'error' in stats:
                logger.warning(f"    ⚠️  Error: {stats['error']}")

        logger.info(f"\n  Total:")
        logger.info(f"    Embeddings: {total_embeddings:,}")
        logger.info(f"    Storage: {format_bytes(total_storage)}")

        # Load Stage 4 tracker metrics (if available)
        logger.info("\n\n💰 Cost and Performance Metrics:")
        logger.info("=" * 80)

        try:
            tracker = Stage4Tracker()

            # Try to get stats if method exists
            if hasattr(tracker, 'get_stats'):
                stats = tracker.get_stats()

                logger.info("\n  Embedding Model:")
                logger.info(f"    Model: gte-large (1024 dimensions)")
                logger.info(f"    Cost: FREE (local inference)")

                logger.info("\n  Total Indexed:")
                logger.info(f"    Entities: {total_embeddings:,} vectors")
                logger.info(f"    Storage: {format_bytes(total_storage)}")
            else:
                logger.info("\n  Embedding Model:")
                logger.info(f"    Model: gte-large (1024 dimensions)")
                logger.info(f"    Cost: FREE (local inference)")

                logger.info("\n  Total Indexed:")
                logger.info(f"    Entities: {total_embeddings:,} vectors")
                logger.info(f"    Storage: {format_bytes(total_storage)}")

                logger.info("\n  Note: No historical tracking data available yet")
                logger.info("         Run process-stage4 to generate tracking reports")
        except Exception as e:
            logger.warning(f"Could not load tracker metrics: {e}")
            logger.info("\n  Embedding Model:")
            logger.info(f"    Model: gte-large (1024 dimensions)")
            logger.info(f"    Cost: FREE (local inference)")

        # Detailed stats if requested
        if detailed:
            logger.info("\n\n📈 Detailed Collection Breakdown:")
            logger.info("=" * 80)

            for name, stats in collection_stats.items():
                if stats['count'] > 0:
                    logger.info(f"\n  {name.replace('_', ' ').title()}:")
                    logger.info(f"    Vectors: {stats['count']:,}")
                    logger.info(f"    Storage: {stats['storage_formatted']}")
                    logger.info(f"    Avg size per vector: ~4 KB")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Statistics complete")
        logger.info("=" * 80 + "\n")

    except Exception as e:
        logger.error(f"❌ Error generating statistics: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def export_json():
    """Export statistics as JSON."""
    try:
        # Initialize ChromaDB
        chromadb = ChromaDBClient.initialize_from_env()

        # Get stats
        collection_stats = get_collection_stats(chromadb)
        chromadb_stats = chromadb.get_stats()

        # Build export
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'chromadb_mode': chromadb.mode or 'local',
            'chromadb_stats': chromadb_stats,
            'collections': collection_stats
        }

        print(json.dumps(export_data, indent=2))

    except Exception as e:
        logger.error(f"❌ Error exporting JSON: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Stage 4 Vector Database Statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic statistics
  python stage4_stats.py

  # Detailed statistics
  python stage4_stats.py --detailed

  # Export as JSON
  python stage4_stats.py --json
        """
    )

    parser.add_argument(
        '--detailed', '-d',
        action='store_true',
        help='Show detailed statistics'
    )

    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='Export statistics as JSON'
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

    # Execute
    if args.json:
        export_json()
    else:
        display_stats(detailed=args.detailed)


if __name__ == '__main__':
    main()
