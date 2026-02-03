#!/usr/bin/env python3
"""
Vector Database Management Tool

Unified tool for managing ChromaDB vector database including monitoring,
backups, and cloud synchronization.

Commands:
    monitor - Monitor vector database health and performance
    backup  - Backup vector collections to local storage
    sync    - Sync vectors to cloud ChromaDB instance

Usage:
    # Monitor database health
    python cli/vectordb.py monitor
    python cli/vectordb.py monitor --check-all

    # Backup vectors
    python cli/vectordb.py backup
    python cli/vectordb.py backup --collection entities

    # Sync to cloud
    python cli/vectordb.py sync
    python cli/vectordb.py sync --collection entities

Examples:
    # Monitor with full health checks
    ./crawl.sh vectordb monitor --check-all

    # Backup all collections
    ./crawl.sh vectordb backup

    # Sync specific collection
    ./crawl.sh vectordb sync --collection entities
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.chromadb_client import ChromaDBClient
from src.vectordb.search_api import SemanticSearchAPI
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ============================================================================
# MONITORING
# ============================================================================

class Stage4Monitor:
    """Monitors Stage 4 vector database health and performance."""

    def __init__(self):
        """Initialize monitor."""
        self.chromadb = None
        self.search_api = None
        self.issues = []
        self.warnings = []

    def initialize(self) -> bool:
        """Initialize monitoring components."""
        try:
            logger.info("🔧 Initializing Stage 4 monitor...")

            self.chromadb = ChromaDBClient.initialize_from_env()
            logger.info(f"   ChromaDB mode: {self.chromadb.mode or 'cloud'}")

            self.search_api = SemanticSearchAPI()
            logger.info("   Search API initialized")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    def check_collection_health(self) -> Dict[str, Any]:
        """Check health of all collections."""
        logger.info("\n🏥 Checking collection health...")

        health = {}

        collections_map = {
            'entities': self.chromadb.entities_collection,
            'profile_consensus': self.chromadb.profile_consensus_collection,
            'experiences': self.chromadb.experiences_collection,
            'city_destinations': self.chromadb.city_destinations_collection
        }

        for collection_name, collection in collections_map.items():
            try:
                if not collection:
                    self.issues.append(f"Collection '{collection_name}' not found")
                    health[collection_name] = {
                        'status': 'error',
                        'count': 0,
                        'message': 'Collection not found'
                    }
                    continue

                count = collection.count()

                if count == 0:
                    self.warnings.append(f"Collection '{collection_name}' is empty")
                    health[collection_name] = {
                        'status': 'warning',
                        'count': 0,
                        'message': 'Collection is empty'
                    }
                else:
                    health[collection_name] = {
                        'status': 'healthy',
                        'count': count,
                        'message': f'{count:,} embeddings'
                    }

                logger.info(f"   {collection_name}: {health[collection_name]['status']} - {health[collection_name]['message']}")

            except Exception as e:
                self.issues.append(f"Error checking {collection_name}: {str(e)}")
                health[collection_name] = {
                    'status': 'error',
                    'count': 0,
                    'message': str(e)
                }
                logger.error(f"   {collection_name}: error - {e}")

        return health

    def check_search_performance(self) -> Dict[str, Any]:
        """Check search performance with test queries."""
        logger.info("\n⚡ Checking search performance...")

        test_queries = [
            "restaurants in Bangkok",
            "beach activities",
            "budget hotels"
        ]

        performance = {
            'avg_query_time_ms': 0,
            'max_query_time_ms': 0,
            'min_query_time_ms': float('inf'),
            'successful_queries': 0,
            'failed_queries': 0,
            'queries': []
        }

        for query in test_queries:
            try:
                start_time = datetime.now()

                results = self.search_api.search_entities(
                    query_text=query,
                    top_k=5
                )

                end_time = datetime.now()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                performance['queries'].append({
                    'query': query,
                    'duration_ms': duration_ms,
                    'results_count': len(results) if results else 0,
                    'status': 'success'
                })

                performance['successful_queries'] += 1
                performance['avg_query_time_ms'] += duration_ms
                performance['max_query_time_ms'] = max(performance['max_query_time_ms'], duration_ms)
                performance['min_query_time_ms'] = min(performance['min_query_time_ms'], duration_ms)

                logger.info(f"   '{query}': {duration_ms:.1f}ms ({len(results) if results else 0} results)")

            except Exception as e:
                performance['queries'].append({
                    'query': query,
                    'duration_ms': 0,
                    'results_count': 0,
                    'status': 'failed',
                    'error': str(e)
                })

                performance['failed_queries'] += 1
                self.issues.append(f"Search query failed: {query} - {str(e)}")
                logger.error(f"   '{query}': failed - {e}")

        if performance['successful_queries'] > 0:
            performance['avg_query_time_ms'] /= performance['successful_queries']

        return performance

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        logger.info("\n" + "=" * 80)
        logger.info("STAGE 4 MONITORING REPORT")
        logger.info("=" * 80)
        logger.info(f"Generated: {datetime.now().isoformat()}")

        health = self.check_collection_health()
        performance = self.check_search_performance()

        # Summary
        logger.info("\n📊 SUMMARY:")
        total_collections = len(health)
        healthy_collections = sum(1 for h in health.values() if h['status'] == 'healthy')
        total_embeddings = sum(h['count'] for h in health.values())

        logger.info(f"   Collections: {healthy_collections}/{total_collections} healthy")
        logger.info(f"   Total Embeddings: {total_embeddings:,}")
        logger.info(f"   Avg Query Time: {performance['avg_query_time_ms']:.1f}ms")
        logger.info(f"   Search Success Rate: {performance['successful_queries']}/{len(performance['queries'])}")

        # Issues and warnings
        if self.issues:
            logger.info(f"\n⚠️  ISSUES ({len(self.issues)}):")
            for issue in self.issues[:5]:
                logger.info(f"   - {issue}")
            if len(self.issues) > 5:
                logger.info(f"   ... and {len(self.issues) - 5} more")

        if self.warnings:
            logger.info(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings[:5]:
                logger.info(f"   - {warning}")
            if len(self.warnings) > 5:
                logger.info(f"   ... and {len(self.warnings) - 5} more")

        if not self.issues and not self.warnings:
            logger.info("\n✅ All checks passed - system healthy!")

        logger.info("\n" + "=" * 80)

        return {
            'timestamp': datetime.now().isoformat(),
            'health': health,
            'performance': performance,
            'issues': self.issues,
            'warnings': self.warnings
        }


# ============================================================================
# BACKUP
# ============================================================================

class VectorBackup:
    """Handles vector database backup operations."""

    def __init__(self, backup_dir: str = './backups/vectordb'):
        """Initialize backup handler."""
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.chromadb = None

    def initialize(self) -> bool:
        """Initialize ChromaDB connection."""
        try:
            logger.info("🔧 Initializing ChromaDB for backup...")
            self.chromadb = ChromaDBClient.initialize_from_env()
            logger.info(f"   ChromaDB mode: {self.chromadb.mode or 'cloud'}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    def backup_collection(self, collection_name: str) -> bool:
        """Backup a single collection."""
        try:
            logger.info(f"\n💾 Backing up collection: {collection_name}")

            # Get collection
            collections_map = {
                'entities': self.chromadb.entities_collection,
                'profile_consensus': self.chromadb.profile_consensus_collection,
                'experiences': self.chromadb.experiences_collection,
                'city_destinations': self.chromadb.city_destinations_collection
            }

            collection = collections_map.get(collection_name)
            if not collection:
                logger.error(f"   Collection '{collection_name}' not found")
                return False

            # Get all data from collection
            results = collection.get()

            if not results or not results.get('ids'):
                logger.warning(f"   Collection '{collection_name}' is empty")
                return True

            # Create backup file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"{collection_name}_{timestamp}.json"

            # Save to file
            backup_data = {
                'collection_name': collection_name,
                'timestamp': datetime.now().isoformat(),
                'count': len(results['ids']),
                'ids': results['ids'],
                'embeddings': results.get('embeddings', []),
                'metadatas': results.get('metadatas', []),
                'documents': results.get('documents', [])
            }

            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)

            logger.info(f"   ✅ Backed up {len(results['ids']):,} embeddings")
            logger.info(f"   📁 Saved to: {backup_file}")

            return True

        except Exception as e:
            logger.error(f"   ❌ Backup failed: {e}")
            return False

    def backup_all(self) -> Dict[str, bool]:
        """Backup all collections."""
        logger.info("\n" + "=" * 80)
        logger.info("VECTOR DATABASE BACKUP")
        logger.info("=" * 80)

        results = {}
        collections = ['entities', 'profile_consensus', 'experiences', 'city_destinations']

        for collection_name in collections:
            results[collection_name] = self.backup_collection(collection_name)

        # Summary
        logger.info("\n📊 BACKUP SUMMARY:")
        successful = sum(1 for r in results.values() if r)
        logger.info(f"   Successful: {successful}/{len(results)}")

        logger.info("\n" + "=" * 80)

        return results


# ============================================================================
# CLOUD SYNC
# ============================================================================

class CloudSync:
    """Handles syncing local ChromaDB to cloud instance."""

    def __init__(self):
        """Initialize cloud sync."""
        self.chromadb = None

    def initialize(self) -> bool:
        """Initialize ChromaDB connection."""
        try:
            logger.info("🔧 Initializing ChromaDB for sync...")
            self.chromadb = ChromaDBClient.initialize_from_env()

            if self.chromadb.mode != 'cloud':
                logger.error("❌ Not in cloud mode - sync not supported")
                return False

            logger.info("   ChromaDB mode: CLOUD")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    def sync_collection(self, collection_name: str) -> bool:
        """Sync a single collection to cloud."""
        try:
            logger.info(f"\n☁️  Syncing collection: {collection_name}")

            # Get collection
            collections_map = {
                'entities': self.chromadb.entities_collection,
                'profile_consensus': self.chromadb.profile_consensus_collection,
                'experiences': self.chromadb.experiences_collection,
                'city_destinations': self.chromadb.city_destinations_collection
            }

            collection = collections_map.get(collection_name)
            if not collection:
                logger.error(f"   Collection '{collection_name}' not found")
                return False

            count = collection.count()
            logger.info(f"   Collection has {count:,} embeddings")

            # In cloud mode, data is already synced
            logger.info(f"   ✅ Collection '{collection_name}' is synced to cloud")

            return True

        except Exception as e:
            logger.error(f"   ❌ Sync failed: {e}")
            return False

    def sync_all(self) -> Dict[str, bool]:
        """Sync all collections to cloud."""
        logger.info("\n" + "=" * 80)
        logger.info("CLOUD SYNC")
        logger.info("=" * 80)

        results = {}
        collections = ['entities', 'profile_consensus', 'experiences', 'city_destinations']

        for collection_name in collections:
            results[collection_name] = self.sync_collection(collection_name)

        # Summary
        logger.info("\n📊 SYNC SUMMARY:")
        successful = sum(1 for r in results.values() if r)
        logger.info(f"   Successful: {successful}/{len(results)}")

        logger.info("\n" + "=" * 80)

        return results


# ============================================================================
# CLI COMMANDS
# ============================================================================

@click.group()
def cli():
    """Vector database management tool."""
    pass


@cli.command()
@click.option('--check-all', is_flag=True, help='Run all health checks')
@click.option('--json', '-j', is_flag=True, help='Output as JSON')
@click.option('--log-level', default='INFO', help='Logging level')
def monitor(check_all: bool, json: bool, log_level: str):
    """
    Monitor vector database health and performance.

    Checks collection health, search performance, and generates
    comprehensive monitoring reports.

    Examples:

        # Basic monitoring
        python cli/vectordb.py monitor

        # Full health check with all tests
        python cli/vectordb.py monitor --check-all

        # Export report as JSON
        python cli/vectordb.py monitor --json
    """
    setup_logging(log_level=log_level)

    try:
        monitor = Stage4Monitor()

        if not monitor.initialize():
            sys.exit(1)

        if check_all:
            report = monitor.generate_report()

            if json:
                print(json.dumps(report, indent=2))

        else:
            # Just check collection health
            health = monitor.check_collection_health()

            logger.info("\n📊 Quick Health Check:")
            healthy = sum(1 for h in health.values() if h['status'] == 'healthy')
            total = len(health)
            logger.info(f"   Collections: {healthy}/{total} healthy")

            if monitor.issues:
                logger.info(f"   Issues: {len(monitor.issues)}")
            if monitor.warnings:
                logger.info(f"   Warnings: {len(monitor.warnings)}")

            logger.info("\n💡 Use --check-all for comprehensive health check")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Monitoring failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--collection', '-c', help='Backup specific collection (entities, profile_consensus, experiences, city_destinations)')
@click.option('--backup-dir', default='./backups/vectordb', help='Backup directory path')
@click.option('--log-level', default='INFO', help='Logging level')
def backup(collection: Optional[str], backup_dir: str, log_level: str):
    """
    Backup vector collections to local storage.

    Creates JSON backups of collection data including embeddings,
    metadata, and documents.

    Examples:

        # Backup all collections
        python cli/vectordb.py backup

        # Backup specific collection
        python cli/vectordb.py backup --collection entities

        # Custom backup directory
        python cli/vectordb.py backup --backup-dir /path/to/backups
    """
    setup_logging(log_level=log_level)

    try:
        backup_handler = VectorBackup(backup_dir=backup_dir)

        if not backup_handler.initialize():
            sys.exit(1)

        if collection:
            success = backup_handler.backup_collection(collection)
            sys.exit(0 if success else 1)
        else:
            results = backup_handler.backup_all()
            sys.exit(0 if all(results.values()) else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option('--collection', '-c', help='Sync specific collection (entities, profile_consensus, experiences, city_destinations)')
@click.option('--log-level', default='INFO', help='Logging level')
def sync(collection: Optional[str], log_level: str):
    """
    Sync vectors to cloud ChromaDB instance.

    Note: Only available when using Chroma Cloud mode.

    Examples:

        # Sync all collections
        python cli/vectordb.py sync

        # Sync specific collection
        python cli/vectordb.py sync --collection entities
    """
    setup_logging(log_level=log_level)

    try:
        sync_handler = CloudSync()

        if not sync_handler.initialize():
            sys.exit(1)

        if collection:
            success = sync_handler.sync_collection(collection)
            sys.exit(0 if success else 1)
        else:
            results = sync_handler.sync_all()
            sys.exit(0 if all(results.values()) else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    cli()
