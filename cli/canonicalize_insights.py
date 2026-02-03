#!/usr/bin/env python3
"""
Insights Canonicalization CLI - Phase 2C

Deduplicates and canonicalizes extracted insights to create the final canonical insights.

Pipeline Flow:
    1. Load all extracted insights from PostgreSQL
    2. Deduplicate insights (group similar insights together)
    3. Canonicalize groups (create consensus insights with IDs)
    4. Save canonical insights to PostgreSQL
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

# PostgreSQL imports
from src.database import SessionLocal

# Insights PostgreSQL helpers
from cli.insights_postgres_helpers import (
    load_extracted_insights_from_postgres,
    save_canonical_insights_to_postgres
)

from src.processors.insight_deduplication import deduplicate_insights
from src.processors.insight_canonicalization import canonicalize_insight_groups
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# =============================================================================
# Helper Functions (using PostgreSQL)
# =============================================================================
# All helper functions moved to cli/insights_postgres_helpers.py


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
    1. Loads all extracted insights from PostgreSQL
    2. Deduplicates similar insights
    3. Canonicalizes groups into consensus insights
    4. Saves canonical insights to PostgreSQL
    """
    # Setup logging
    setup_logging(log_level)

    logger.info("=" * 80)
    logger.info("INSIGHTS CANONICALIZATION - Phase 2C")
    logger.info("=" * 80)
    logger.info(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("=" * 80)

    db = SessionLocal()
    try:
        # Step 1: Load extracted insights
        logger.info("\n📥 Step 1: Loading extracted insights...")
        extracted_insights = load_extracted_insights_from_postgres(db)

        if not extracted_insights:
            logger.warning("⚠️  No extracted insights found!")
            logger.info("\nTo extract insights, run:")
            logger.info("  python cli/process_insights.py")
            return

        # Step 2: Deduplicate insights
        logger.info("\n🔍 Step 2: Deduplicating insights...")
        dedup_groups, dedup_stats = deduplicate_insights(extracted_insights)

        # Step 3: Canonicalize groups
        logger.info("\n✨ Step 3: Canonicalizing insight groups...")
        # Pass None for insight_registry - IDs will be generated in canonicalization
        canonical_insights = canonicalize_insight_groups(dedup_groups, insight_registry=None)

        if not canonical_insights:
            logger.error("❌ Canonicalization produced no insights!")
            return

        # Step 4: Save canonical insights
        if not dry_run:
            logger.info("\n💾 Step 4: Saving canonical insights to PostgreSQL...")
            results = save_canonical_insights_to_postgres(db, canonical_insights, dedup_stats)
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
            logger.info(f"\n📊 PostgreSQL Results:")
            logger.info(f"  Canonical insights saved: {results.get('canonical_saved', 0)}")
            logger.info(f"  Canonical insights updated: {results.get('canonical_updated', 0)}")
            logger.info(f"  Total: {results.get('total', 0)}")

        logger.info("\n" + "=" * 80)
        logger.info("NEXT STEPS")
        logger.info("=" * 80)
        logger.info("1. View insights statistics: python cli/insights_stats.py")
        logger.info("2. Explore insights in dashboard")
        logger.info("=" * 80)

    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Canonicalization interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"\n\n❌ Canonicalization failed: {e}", exc_info=True)
        sys.exit(1)

    finally:
        db.close()


if __name__ == '__main__':
    main()
