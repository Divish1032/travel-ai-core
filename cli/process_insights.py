#!/usr/bin/env python3
"""
Insights Pipeline Processor - Pass 1 & Pass 2 Extraction

Processes videos through the Insights Pipeline to extract travel knowledge:
- Pass 1: Extract insights from filtered non-place entities (apps, services, tips)
- Pass 2: Extract insights from info-only videos (<5 entities)

Pipeline Flow:
    1. Find videos ready for insights processing (Stage 3 complete)
    2. For each video:
       a. Pass 1: Load filtered entities, extract insights
       b. Pass 2: Check entity count, extract from transcript if <5
    3. Save extracted insights to PostgreSQL
    4. Track costs and progress
    5. Update video status

Usage:
    python cli/process_insights.py [--limit N] [--pass {1,2,all}] [--log-level DEBUG]

Features:
    - Dual-pass extraction (entity enrichment + transcript extraction)
    - Gemini Flash 2.5 Lite (free tier) for cost-efficient extraction
    - Progress tracking with tqdm
    - Cost tracking for LLM calls
    - Validates insights against TravelInsight schema
    - Updates metadata tracker

Examples:
    # Process first 10 videos (both passes)
    python cli/process_insights.py --limit 10

    # Process all pending videos
    python cli/process_insights.py

    # Process only Pass 1 (filtered entities)
    python cli/process_insights.py --pass 1

    # Process only Pass 2 (info-only videos)
    python cli/process_insights.py --pass 2 --limit 50

    # Enable debug logging
    python cli/process_insights.py --limit 5 --log-level DEBUG

Cost Estimation:
    - Gemini Flash 2.5 Lite: FREE tier (15 req/min, 1M tokens/min, 1500 req/day)
    - Pass 1: ~$0.00 per entity (~200 entities total)
    - Pass 2: ~$0.00 per video (~30 videos total)
    - Full run: ~$0.00 (within free tier limits)
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict

import click
from tqdm import tqdm

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# PostgreSQL imports
from src.database import SessionLocal
from src.database.models import StageStatus

# Insights PostgreSQL helpers
from cli.insights_postgres_helpers import (
    find_videos_ready_for_insights_from_postgres,
    load_video_metadata_from_postgres,
    load_filtered_entities_from_postgres,
    count_place_entities_from_postgres,
    save_extracted_insights_to_postgres,
    update_video_insights_status
)

from src.processors.insights_extractor import (
    extract_insights_from_entity,
    extract_insights_from_transcript
)
from src.utils.logging import get_logger, setup_logging
from src.utils.cost_tracker import CostTracker

logger = get_logger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Pass 2 threshold: Videos with fewer entities are candidates for transcript extraction
PASS2_ENTITY_THRESHOLD = 5

# Maximum insights to extract per video (prevent explosion)
MAX_INSIGHTS_PER_VIDEO = 50

# LLM retry settings
MAX_RETRIES = 2


# =============================================================================
# Helper Functions (using PostgreSQL)
# =============================================================================
# All helper functions moved to cli/insights_postgres_helpers.py


def process_video_insights(
    video_id: str,
    db: Session,
    cost_tracker: CostTracker,
    pass_mode: str = 'all',
    max_retries: int = MAX_RETRIES
) -> Tuple[bool, Dict[str, Any]]:
    """
    Process insights for a single video (Pass 1 and/or Pass 2).

    Args:
        video_id: Video source ID
        db: Database session
        cost_tracker: CostTracker instance
        pass_mode: Which pass to run ('1', '2', or 'all')
        max_retries: Maximum LLM retry attempts

    Returns:
        Tuple of (success, stats_dict)
    """
    stats = {
        'video_id': video_id,
        'pass1_entities': 0,
        'pass1_insights': 0,
        'pass2_applicable': False,
        'pass2_insights': 0,
        'total_insights': 0,
        'cost_usd': 0.0,
        'tokens_used': {'input': 0, 'output': 0, 'total': 0}
    }

    all_insights = []

    # Load video metadata from PostgreSQL
    video_metadata = load_video_metadata_from_postgres(db, video_id)
    if not video_metadata:
        logger.error(f"Failed to load video metadata for {video_id}")
        return False, stats

    # Pass 1: Extract insights from filtered entities
    if pass_mode in ['1', 'all']:
        filtered_entities = load_filtered_entities_from_postgres(db, video_id)
        stats['pass1_entities'] = len(filtered_entities)

        if filtered_entities:
            logger.debug(f"Pass 1: Processing {len(filtered_entities)} filtered entities for {video_id}")

            for entity in filtered_entities:
                try:
                    insights, meta = extract_insights_from_entity(
                        entity,
                        video_metadata,
                        max_retries=max_retries
                    )

                    if insights:
                        all_insights.extend(insights)
                        stats['pass1_insights'] += len(insights)

                        # Track costs
                        if meta.get('cost_usd', 0) > 0:
                            cost_tracker.track_llm_call(
                                input_tokens=meta['tokens_used']['input'],
                                output_tokens=meta['tokens_used']['output'],
                                model=meta.get('model', 'gemini-2.5-flash-lite')
                            )
                            stats['cost_usd'] += meta['cost_usd']
                            stats['tokens_used']['input'] += meta['tokens_used']['input']
                            stats['tokens_used']['output'] += meta['tokens_used']['output']
                            stats['tokens_used']['total'] += meta['tokens_used']['total']

                except Exception as e:
                    logger.warning(
                        f"Pass 1: Failed to extract insights from entity "
                        f"'{entity.get('canonical_name')}' for {video_id}: {e}"
                    )
                    continue

    # Pass 2: Extract insights from transcript (if <5 entities)
    if pass_mode in ['2', 'all']:
        place_entity_count = count_place_entities_from_postgres(db, video_id)

        if place_entity_count < PASS2_ENTITY_THRESHOLD:
            stats['pass2_applicable'] = True
            logger.debug(
                f"Pass 2: Video {video_id} has {place_entity_count} entities "
                f"(threshold: {PASS2_ENTITY_THRESHOLD}) - extracting from transcript"
            )

            # Get transcript
            transcript = video_metadata.get('transcript', '')
            if transcript:
                try:
                    insights, meta = extract_insights_from_transcript(
                        transcript,
                        video_metadata,
                        max_retries=max_retries
                    )

                    if insights:
                        all_insights.extend(insights)
                        stats['pass2_insights'] = len(insights)

                        # Track costs
                        if meta.get('cost_usd', 0) > 0:
                            cost_tracker.track_llm_call(
                                input_tokens=meta['tokens_used']['input'],
                                output_tokens=meta['tokens_used']['output'],
                                model=meta.get('model', 'gemini-2.5-flash-lite')
                            )
                            stats['cost_usd'] += meta['cost_usd']
                            stats['tokens_used']['input'] += meta['tokens_used']['input']
                            stats['tokens_used']['output'] += meta['tokens_used']['output']
                            stats['tokens_used']['total'] += meta['tokens_used']['total']

                except Exception as e:
                    logger.warning(f"Pass 2: Failed to extract insights from transcript for {video_id}: {e}")
            else:
                logger.warning(f"Pass 2: No transcript found for {video_id}")

    # Limit insights per video
    if len(all_insights) > MAX_INSIGHTS_PER_VIDEO:
        logger.warning(
            f"Video {video_id} extracted {len(all_insights)} insights, "
            f"limiting to {MAX_INSIGHTS_PER_VIDEO}"
        )
        all_insights = all_insights[:MAX_INSIGHTS_PER_VIDEO]

    stats['total_insights'] = len(all_insights)

    # Save extracted insights to PostgreSQL
    if all_insights:
        try:
            extraction_pass = f"pass{pass_mode}" if pass_mode in ['1', '2'] else 'pass_all'

            insights_saved, mentions_saved = save_extracted_insights_to_postgres(
                db=db,
                video_id=video_id,
                insights=all_insights,
                extraction_pass=extraction_pass
            )

            logger.info(
                f"✓ Video {video_id}: Extracted {stats['total_insights']} insights "
                f"(Pass 1: {stats['pass1_insights']}, Pass 2: {stats['pass2_insights']}) "
                f"[Saved: {insights_saved} insights, {mentions_saved} mentions]"
            )

        except Exception as e:
            logger.error(f"Failed to save insights for video {video_id}: {e}")
            return False, stats
    else:
        logger.info(f"✓ Video {video_id}: No insights extracted")

    return True, stats


# =============================================================================
# Main CLI Command
# =============================================================================

@click.command()
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Maximum number of videos to process (default: all)'
)
@click.option(
    '--pass',
    'pass_mode',
    type=click.Choice(['1', '2', 'all']),
    default='all',
    help='Which pass to run: 1 (filtered entities), 2 (transcripts), or all (default: all)'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(limit: Optional[int], pass_mode: str, log_level: str):
    """
    Process insights pipeline (Pass 1 & Pass 2 extraction).

    Examples:

        # Process first 10 videos
        python cli/process_insights.py --limit 10

        # Process all pending videos
        python cli/process_insights.py

        # Process only Pass 1 (filtered entities)
        python cli/process_insights.py --pass 1

        # Process only Pass 2 (info-only videos)
        python cli/process_insights.py --pass 2
    """
    # Setup logging
    setup_logging(log_level=log_level)

    logger.info("=" * 80)
    logger.info("INSIGHTS PIPELINE - Pass 1 & Pass 2 Extraction")
    logger.info("=" * 80)
    logger.info(f"Pass mode: {pass_mode}")
    logger.info(f"Limit: {limit if limit else 'all videos'}")
    logger.info("")

    # Initialize database and tracking
    db = SessionLocal()
    try:
        cost_tracker = CostTracker()

        logger.info("✓ Initialized database and tracking")

        # Find videos ready for processing
        ready_videos = find_videos_ready_for_insights_from_postgres(db, limit=limit)

        if not ready_videos:
            logger.info("No videos ready for insights processing")
            logger.info("Criteria: Stage 3 complete, insights_pipeline not processed")
            return

        logger.info(f"Found {len(ready_videos)} videos ready for processing\n")

        # Process each video
        success_count = 0
        failed_videos = []
        video_stats = []

        logger.info("Processing videos...\n")

        with tqdm(total=len(ready_videos), desc="Extracting insights") as pbar:
            for video_id in ready_videos:
                # Mark as processing
                try:
                    update_video_insights_status(db, video_id, StageStatus.PENDING)
                except Exception as e:
                    logger.warning(f"Failed to mark {video_id} as processing: {e}")

                # Process video
                success, stats = process_video_insights(
                    video_id,
                    db,
                    cost_tracker,
                    pass_mode=pass_mode
                )

                video_stats.append(stats)

                if success:
                    success_count += 1

                    # Mark as completed
                    try:
                        update_video_insights_status(
                            db=db,
                            video_id=video_id,
                            status=StageStatus.COMPLETE,
                            insights_count=stats['total_insights']
                        )
                    except Exception as e:
                        logger.warning(f"Failed to mark {video_id} as completed: {e}")

                else:
                    failed_videos.append(video_id)

                    # Mark as failed
                    try:
                        update_video_insights_status(
                            db=db,
                            video_id=video_id,
                            status=StageStatus.FAILED,
                            error='Insights extraction failed'
                        )
                    except Exception as e:
                        logger.warning(f"Failed to mark {video_id} as failed: {e}")

                pbar.update(1)

        # Generate summary
        logger.info("\n" + "=" * 80)
        logger.info("INSIGHTS EXTRACTION SUMMARY")
        logger.info("=" * 80)

        logger.info(f"\nVideos Processed: {len(ready_videos)}")
        logger.info(f"  Success: {success_count}")
        logger.info(f"  Failed: {len(failed_videos)}")

        # Aggregate stats
        total_pass1_entities = sum(s['pass1_entities'] for s in video_stats)
        total_pass1_insights = sum(s['pass1_insights'] for s in video_stats)
        total_pass2_applicable = sum(1 for s in video_stats if s['pass2_applicable'])
        total_pass2_insights = sum(s['pass2_insights'] for s in video_stats)
        total_insights = sum(s['total_insights'] for s in video_stats)

        logger.info("\nInsights Extracted:")
        logger.info(f"  Pass 1 (filtered entities): {total_pass1_insights} insights from {total_pass1_entities} entities")
        logger.info(f"  Pass 2 (transcripts): {total_pass2_insights} insights from {total_pass2_applicable} videos")
        logger.info(f"  TOTAL: {total_insights} insights")

        # Cost report
        cost_report = cost_tracker.get_cost_report()
        logger.info("\nCost Report:")
        logger.info(f"  LLM calls: {cost_report['llm_costs']['total_calls']}")
        logger.info(f"  LLM tokens: {cost_report['llm_costs']['total_tokens']:,}")
        logger.info(f"  LLM cost: ${cost_report['llm_costs']['total_cost']:.6f}")
        logger.info(f"  TOTAL COST: ${cost_report['grand_total']:.6f}")

        if cost_report['grand_total'] == 0:
            logger.info("  (Free tier - Gemini Flash 2.5 Lite)")

        # Category distribution
        category_counts = defaultdict(int)
        for stats in video_stats:
            # Note: We don't have category breakdown yet, that's in Phase 2C
            pass

        # Failed videos
        if failed_videos:
            logger.info(f"\nFailed Videos ({len(failed_videos)}):")
            for video_id in failed_videos[:10]:  # Show first 10
                logger.info(f"  - {video_id}")
            if len(failed_videos) > 10:
                logger.info(f"  ... and {len(failed_videos) - 10} more")

        # Next steps
        logger.info("\n" + "=" * 80)
        logger.info("NEXT STEPS")
        logger.info("=" * 80)
        logger.info("1. Run canonicalization: python cli/canonicalize_insights.py")
        logger.info("2. Check insights statistics: python cli/insights_stats.py")

        logger.info("\n✅ Insights extraction complete!\n")

    finally:
        db.close()


if __name__ == '__main__':
    main()
