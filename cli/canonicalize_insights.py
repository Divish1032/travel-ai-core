#!/usr/bin/env python3
"""
Insights Canonicalization CLI - Phase 2C

Deduplicates and canonicalizes extracted insights to create the final canonical insights.

Pipeline Flow:
    1. Load all extracted insights from S3 (insights-pipeline/extracted/new/)
    2. Deduplicate insights (group similar insights together)
    3. Canonicalize groups (create consensus insights with IDs)
    4. Save canonical insights to S3 (insights-pipeline/canonical/)
    5. Create category and destination indexes

Usage:
    python cli/canonicalize_insights.py [--dry-run] [--log-level DEBUG]
    ./crawl.sh canonicalize-insights

Examples:
    # Run canonicalization
    python cli/canonicalize_insights.py

    # Dry run (preview what will be created)
    python cli/canonicalize_insights.py --dry-run

    # Debug mode
    python cli/canonicalize_insights.py --log-level DEBUG
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List
from collections import defaultdict

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.insights_storage import InsightsStorage
from src.storage.insight_registry import InsightRegistry
from src.processors.insight_deduplication import deduplicate_insights
from src.processors.insight_canonicalization import canonicalize_insight_groups
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# =============================================================================
# Load Extracted Insights
# =============================================================================

def load_all_extracted_insights(insights_storage: InsightsStorage) -> List[Dict[str, Any]]:
    """Load all extracted insights from S3."""
    logger.info("=" * 80)
    logger.info("LOADING EXTRACTED INSIGHTS")
    logger.info("=" * 80)

    try:
        insights = insights_storage.load_extracted_insights()
        logger.info(f"Loaded {len(insights)} extracted insights from S3")

        # Log category breakdown
        category_counts = defaultdict(int)
        for insight in insights:
            category = insight.get('category', 'unknown')
            category_counts[category] += 1

        logger.info("\nInsights by Category:")
        for category, count in sorted(category_counts.items()):
            logger.info(f"  {category}: {count}")

        return insights

    except Exception as e:
        logger.error(f"Failed to load extracted insights: {e}")
        raise


# =============================================================================
# Save Canonical Insights
# =============================================================================

def save_canonical_insights(
    insights_storage: InsightsStorage,
    canonical_insights: List[Dict[str, Any]],
    dedup_stats: Dict[str, Any],
    dry_run: bool = False
) -> Dict[str, Any]:
    """Save canonical insights to S3 with indexes."""
    logger.info("\n" + "=" * 80)
    logger.info("SAVING CANONICAL INSIGHTS")
    logger.info("=" * 80)

    if dry_run:
        logger.info("DRY RUN - No files will be saved")
        return {}

    try:
        processing_date = datetime.now(timezone.utc).strftime('%Y%m%d')
        results = insights_storage.save_canonical_insights(
            insights=canonical_insights,
            processing_date=processing_date,
            dedup_stats=dedup_stats
        )

        logger.info(f"\n✅ Saved canonical insights to S3:")
        logger.info(f"  Files saved: {len(results.get('files_saved', []))}")
        logger.info(f"  Main file: {results.get('insights_all_path', 'N/A')}")

        return results

    except Exception as e:
        logger.error(f"Failed to save canonical insights: {e}")
        raise


# =============================================================================
# Main CLI
# =============================================================================

@click.command()
@click.option('--dry-run', is_flag=True, help='Preview canonicalization without saving')
@click.option('--log-level', default='INFO', help='Logging level (DEBUG, INFO, WARNING, ERROR)')
def main(dry_run: bool, log_level: str):
    """
    Canonicalize extracted insights to create final canonical insights.

    This command:
    1. Loads all extracted insights from S3
    2. Deduplicates similar insights
    3. Canonicalizes groups into consensus insights
    4. Saves canonical insights with indexes
    """
    # Setup logging
    setup_logging(log_level)

    logger.info("=" * 80)
    logger.info("INSIGHTS CANONICALIZATION - Phase 2C")
    logger.info("=" * 80)
    logger.info(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 80)

    try:
        # Initialize storage
        s3_storage = S3Storage()
        insights_storage = InsightsStorage(s3_storage)
        insight_registry = InsightRegistry(s3_storage)

        # Step 1: Load extracted insights
        logger.info("\n📥 Step 1: Loading extracted insights...")
        extracted_insights = load_all_extracted_insights(insights_storage)

        if not extracted_insights:
            logger.warning("⚠️  No extracted insights found!")
            logger.info("\nTo extract insights, run:")
            logger.info("  ./crawl.sh process-insights")
            return

        # Step 2: Deduplicate insights
        logger.info("\n🔍 Step 2: Deduplicating insights...")
        dedup_groups, dedup_stats = deduplicate_insights(extracted_insights)

        # Step 3: Canonicalize groups
        logger.info("\n✨ Step 3: Canonicalizing insight groups...")
        canonical_insights = canonicalize_insight_groups(dedup_groups, insight_registry)

        if not canonical_insights:
            logger.error("❌ Canonicalization produced no insights!")
            return

        # Step 4: Save canonical insights
        if not dry_run:
            logger.info("\n💾 Step 4: Saving canonical insights to S3...")
            results = save_canonical_insights(insights_storage, canonical_insights, dedup_stats, dry_run=False)
        else:
            logger.info("\n💾 Step 4: SKIPPED (dry run)")
            results = {}

        # Final summary
        logger.info("\n" + "=" * 80)
        logger.info("CANONICALIZATION COMPLETE ✅")
        logger.info("=" * 80)
        logger.info(f"Extracted insights: {len(extracted_insights)}")
        logger.info(f"Dedup groups: {len(dedup_groups)}")
        logger.info(f"Canonical insights: {len(canonical_insights)}")

        if not dry_run:
            logger.info(f"\n📊 S3 Results:")
            logger.info(f"  Files saved: {len(results.get('files_saved', []))}")
            logger.info(f"  Main file: {results.get('insights_all_path', 'N/A')}")

        logger.info("\n" + "=" * 80)
        logger.info("NEXT STEPS")
        logger.info("=" * 80)
        logger.info("1. View insights statistics: ./crawl.sh insights-stats")
        logger.info("2. Explore insights in dashboard: ./crawl.sh dashboard")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Canonicalization interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n\n❌ Canonicalization failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
