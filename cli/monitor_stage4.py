#!/usr/bin/env python3
"""
Stage 4 Monitoring and Health Checks

Comprehensive monitoring for the Stage 4 vector database including:
- Health checks
- Performance metrics
- Collection sizes
- Search performance
- Alert generation
- Daily reports

Usage:
    python monitor_stage4.py
    python monitor_stage4.py --check-all
    python monitor_stage4.py --alert-email admin@example.com
    python monitor_stage4.py --generate-report

Author: TravelAI Team
Date: 2025-12-14
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.chromadb_client import ChromaDBClient
from src.vectordb.search_api import SemanticSearchAPI
from src.utils.stage4_tracker import Stage4Tracker
from src.utils.logging import get_logger

logger = get_logger(__name__)


class Stage4Monitor:
    """Monitors Stage 4 vector database health and performance."""

    def __init__(self):
        """Initialize monitor."""
        self.chromadb = None
        self.search_api = None
        self.tracker = None
        self.issues = []
        self.warnings = []

    def initialize(self) -> bool:
        """
        Initialize monitoring components.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing Stage 4 monitor...")

            # Initialize ChromaDB
            self.chromadb = ChromaDBClient.initialize_from_env()
            logger.info(f"   ChromaDB mode: {self.chromadb.mode or 'local'}")

            # Initialize search API
            self.search_api = SemanticSearchAPI()
            logger.info("   Search API initialized")

            # Initialize tracker
            self.tracker = Stage4Tracker()
            logger.info("   Tracker initialized")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    def check_collection_health(self) -> Dict[str, Any]:
        """
        Check health of all collections.

        Returns:
            Dictionary with health status
        """
        logger.info("\n🏥 Checking collection health...")

        health = {}

        # Map collection names to ChromaDBClient attributes
        collections_map = {
            'entities': self.chromadb.entities_collection,
            'profile_consensus': self.chromadb.profile_consensus_collection,
            'experiences': self.chromadb.experiences_collection
        }

        for collection_name in ['entities', 'profile_consensus', 'experiences']:
            try:
                collection = collections_map.get(collection_name)

                if not collection:
                    self.issues.append(f"Collection '{collection_name}' not found")
                    health[collection_name] = {
                        'status': 'error',
                        'count': 0,
                        'message': 'Collection not found'
                    }
                    continue

                count = collection.count()

                # Check if collection is empty
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
        """
        Check search performance with test queries.

        Returns:
            Dictionary with performance metrics
        """
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

                # Execute search
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

        # Calculate average
        if performance['successful_queries'] > 0:
            performance['avg_query_time_ms'] /= performance['successful_queries']

        # Check for performance issues
        if performance['avg_query_time_ms'] > 1000:
            self.warnings.append(f"Average query time is high: {performance['avg_query_time_ms']:.1f}ms")

        if performance['failed_queries'] > 0:
            self.issues.append(f"{performance['failed_queries']} search queries failed")

        return performance

    def check_storage_utilization(self) -> Dict[str, Any]:
        """
        Check storage utilization.

        Returns:
            Dictionary with storage metrics
        """
        logger.info("\n💾 Checking storage utilization...")

        storage = {
            'total_embeddings': 0,
            'estimated_size_bytes': 0,
            'collections': {}
        }

        # Map collection names to ChromaDBClient attributes
        collections_map = {
            'entities': self.chromadb.entities_collection,
            'profile_consensus': self.chromadb.profile_consensus_collection,
            'experiences': self.chromadb.experiences_collection
        }

        for collection_name in ['entities', 'profile_consensus', 'experiences']:
            try:
                collection = collections_map.get(collection_name)

                if collection:
                    count = collection.count()
                    # Estimate: 1024 dimensions * 4 bytes per float (gte-large)
                    size_bytes = count * 1024 * 4

                    storage['collections'][collection_name] = {
                        'count': count,
                        'size_bytes': size_bytes
                    }

                    storage['total_embeddings'] += count
                    storage['estimated_size_bytes'] += size_bytes

            except Exception as e:
                logger.error(f"   Error checking {collection_name}: {e}")

        # Format sizes
        total_mb = storage['estimated_size_bytes'] / (1024 * 1024)
        total_gb = total_mb / 1024

        storage['estimated_size_mb'] = total_mb
        storage['estimated_size_gb'] = total_gb

        logger.info(f"   Total embeddings: {storage['total_embeddings']:,}")
        logger.info(f"   Estimated size: {total_mb:.2f} MB ({total_gb:.3f} GB)")

        return storage

    def generate_daily_report(self) -> Dict[str, Any]:
        """
        Generate daily monitoring report.

        Returns:
            Dictionary with report data
        """
        logger.info("\n📊 Generating daily report...")

        report = {
            'timestamp': datetime.now().isoformat(),
            'collection_health': self.check_collection_health(),
            'search_performance': self.check_search_performance(),
            'storage_utilization': self.check_storage_utilization(),
            'issues': self.issues,
            'warnings': self.warnings
        }

        # Get tracker data (gracefully handle if method doesn't exist)
        try:
            if hasattr(self.tracker, 'get_latest_report'):
                latest_session = self.tracker.get_latest_report()
                if latest_session:
                    report['latest_session'] = latest_session
        except Exception as e:
            logger.debug(f"Could not get tracker report: {e}")

        return report

    def monitor(
        self,
        check_all: bool = False,
        generate_report: bool = False,
        alert_email: Optional[str] = None
    ):
        """
        Run monitoring checks.

        Args:
            check_all: Whether to run all checks
            generate_report: Whether to generate a report
            alert_email: Email to send alerts to
        """
        try:
            logger.info("=" * 80)
            logger.info("STAGE 4 MONITORING")
            logger.info("=" * 80)

            # Run checks
            health = self.check_collection_health()

            if check_all:
                performance = self.check_search_performance()
                storage = self.check_storage_utilization()

            # Generate report if requested
            if generate_report:
                report = self.generate_daily_report()

                # Save report
                report_path = Path("stage4-vectors/monitoring/reports")
                report_path.mkdir(parents=True, exist_ok=True)

                filename = f"monitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                filepath = report_path / filename

                with open(filepath, 'w') as f:
                    json.dump(report, f, indent=2)

                logger.info(f"\n📄 Report saved: {filepath}")

            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("MONITORING SUMMARY")
            logger.info("=" * 80)

            logger.info(f"\n  Issues: {len(self.issues)}")
            if self.issues:
                for issue in self.issues:
                    logger.error(f"    ❌ {issue}")

            logger.info(f"\n  Warnings: {len(self.warnings)}")
            if self.warnings:
                for warning in self.warnings:
                    logger.warning(f"    ⚠️  {warning}")

            # Overall status
            if self.issues:
                logger.error("\n❌ System has CRITICAL issues")
                status_code = 2
            elif self.warnings:
                logger.warning("\n⚠️  System has warnings")
                status_code = 1
            else:
                logger.info("\n✅ System is healthy")
                status_code = 0

            # Send alert if email provided
            if alert_email and (self.issues or self.warnings):
                logger.info(f"\n📧 Alert email would be sent to: {alert_email}")
                logger.info("   (Email sending not implemented - integrate with your email service)")

            logger.info("\n" + "=" * 80)
            sys.exit(status_code)

        except Exception as e:
            logger.error(f"❌ Monitoring failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(3)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor Stage 4 Vector Database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic health check
  python monitor_stage4.py

  # Comprehensive check
  python monitor_stage4.py --check-all

  # Generate daily report
  python monitor_stage4.py --generate-report

  # With email alerts
  python monitor_stage4.py --check-all --alert-email admin@example.com

Exit Codes:
  0 - System healthy
  1 - System has warnings
  2 - System has critical issues
  3 - Monitoring failed
        """
    )

    parser.add_argument(
        '--check-all',
        action='store_true',
        help='Run all health checks including performance tests'
    )

    parser.add_argument(
        '--generate-report',
        action='store_true',
        help='Generate and save monitoring report'
    )

    parser.add_argument(
        '--alert-email',
        type=str,
        help='Email address to send alerts to'
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

    # Execute monitoring
    monitor = Stage4Monitor()
    if not monitor.initialize():
        sys.exit(3)

    monitor.monitor(
        check_all=args.check_all,
        generate_report=args.generate_report,
        alert_email=args.alert_email
    )


if __name__ == '__main__':
    main()
