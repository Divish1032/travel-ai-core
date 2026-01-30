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
    3. Save extracted insights to S3 (insights-pipeline/extracted/new/)
    4. Track costs and progress
    5. Update metadata tracker

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

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

import click
from tqdm import tqdm

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.insights_storage import InsightsStorage
from src.storage.insight_registry import InsightRegistry
from src.utils.metadata_tracker import MetadataTracker
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
# Helper Functions
# =============================================================================

def find_videos_ready_for_insights(
    metadata_tracker: MetadataTracker,
    limit: Optional[int] = None
) -> List[str]:
    """
    Find videos that are ready for insights processing.

    Criteria:
    - Stage 3 (deduplicate) is complete
    - insights_pipeline is not yet processed or failed

    Args:
        metadata_tracker: MetadataTracker instance
        limit: Maximum number of videos to return

    Returns:
        List of video IDs ready for processing
    """
    all_videos = metadata_tracker.get_all_items()
    ready_videos = []

    for video_id, item in all_videos.items():
        # Get stages dict from item
        stages = item.get('stages', {})

        # Check Stage 3 complete
        stage3_status = stages.get('stage_3_deduplicate', {}).get('status')
        if stage3_status != 'complete':  # Fixed: 'complete' not 'completed'
            continue

        # Check insights_pipeline not processed
        insights_status = stages.get('insights_pipeline', {}).get('status')
        if insights_status in ['complete', 'completed', 'processing']:  # Handle both variants
            continue

        ready_videos.append(video_id)

        if limit and len(ready_videos) >= limit:
            break

    return ready_videos


def load_filtered_entities(
    s3_storage: S3Storage,
    video_id: str
) -> List[Dict[str, Any]]:
    """
    Load filtered entities for a video from S3.

    Filtered entities are stored at stage3-canonical/filtered/filtered_{type}_{timestamp}.jsonl

    Args:
        s3_storage: S3Storage instance
        video_id: Video source ID

    Returns:
        List of filtered entity dicts for this video
    """
    try:
        # List all filtered entity files
        prefix = 'stage3-canonical/filtered/'
        response = s3_storage.s3_client.list_objects_v2(
            Bucket=s3_storage.bucket_name,
            Prefix=prefix
        )

        if 'Contents' not in response:
            logger.debug(f"No filtered entities found for video {video_id}")
            return []

        # Load all filtered files and filter by video_id
        video_entities = []
        for obj in response['Contents']:
            s3_key = obj['Key']
            if not s3_key.endswith('.jsonl'):
                continue

            # Download and parse JSONL
            response = s3_storage.s3_client.get_object(
                Bucket=s3_storage.bucket_name,
                Key=s3_key
            )
            content = response['Body'].read().decode('utf-8')

            for line in content.strip().split('\n'):
                if not line:
                    continue
                entity = json.loads(line)

                # Check if entity belongs to this video
                if video_id in entity.get('source_video_ids', []):
                    # Only include insights candidates
                    if entity.get('insights_candidate', False):
                        video_entities.append(entity)

        logger.debug(f"Loaded {len(video_entities)} filtered entities for video {video_id}")
        return video_entities

    except Exception as e:
        logger.error(f"Failed to load filtered entities for video {video_id}: {e}")
        return []


def load_video_metadata(
    s3_storage: S3Storage,
    video_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load video metadata from Stage 1 S3.

    Args:
        s3_storage: S3Storage instance
        video_id: Video source ID (e.g., 'youtube_abc123')

    Returns:
        Video metadata dict, or None if not found
    """
    try:
        # video_id already has 'youtube_' prefix, so remove it for the filename
        # Expected: video_id = 'youtube_fliaO-KMgEI'
        # File: 'raw/stage2_processed/youtube_video_fliaO-KMgEI.jsonl'

        # Extract the actual ID without platform prefix
        if video_id.startswith('youtube_'):
            actual_id = video_id.replace('youtube_', '', 1)
        else:
            actual_id = video_id

        # Try raw/stage2_processed first (after Stage 2), then raw/new (before Stage 2)
        s3_keys = [
            f'raw/stage2_processed/youtube_video_{actual_id}.jsonl',
            f'raw/new/youtube_video_{actual_id}.jsonl'
        ]

        for s3_key in s3_keys:
            try:
                response = s3_storage.s3_client.get_object(
                    Bucket=s3_storage.bucket_name,
                    Key=s3_key
                )
                content = response['Body'].read().decode('utf-8')
                video_data = json.loads(content.strip())
                return video_data
            except s3_storage.s3_client.exceptions.NoSuchKey:
                continue

        logger.warning(f"Video metadata not found for {video_id} (tried keys: {s3_keys})")
        return None

    except Exception as e:
        logger.error(f"Failed to load video metadata for {video_id}: {e}")
        return None


def count_place_entities(
    s3_storage: S3Storage,
    video_id: str
) -> int:
    """
    Count number of place entities extracted for a video.

    Args:
        s3_storage: S3Storage instance
        video_id: Video source ID

    Returns:
        Number of place entities (not filtered)
    """
    try:
        # Load canonical entities
        prefix = 'stage3-canonical/entities/'
        response = s3_storage.s3_client.list_objects_v2(
            Bucket=s3_storage.bucket_name,
            Prefix=prefix
        )

        if 'Contents' not in response:
            return 0

        entity_count = 0
        for obj in response['Contents']:
            s3_key = obj['Key']
            if not s3_key.endswith('.jsonl') or 'entities_all' in s3_key:
                continue

            # Download and parse JSONL
            response = s3_storage.s3_client.get_object(
                Bucket=s3_storage.bucket_name,
                Key=s3_key
            )
            content = response['Body'].read().decode('utf-8')

            for line in content.strip().split('\n'):
                if not line:
                    continue
                entity = json.loads(line)

                # Check if entity belongs to this video
                if video_id in entity.get('source_video_ids', []):
                    entity_count += 1

        return entity_count

    except Exception as e:
        logger.error(f"Failed to count entities for video {video_id}: {e}")
        return 0


def process_video_insights(
    video_id: str,
    s3_storage: S3Storage,
    insights_storage: InsightsStorage,
    cost_tracker: CostTracker,
    pass_mode: str = 'all',
    max_retries: int = MAX_RETRIES
) -> Tuple[bool, Dict[str, Any]]:
    """
    Process insights for a single video (Pass 1 and/or Pass 2).

    Args:
        video_id: Video source ID
        s3_storage: S3Storage instance
        insights_storage: InsightsStorage instance
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

    # Load video metadata
    video_metadata = load_video_metadata(s3_storage, video_id)
    if not video_metadata:
        logger.error(f"Failed to load video metadata for {video_id}")
        return False, stats

    # Pass 1: Extract insights from filtered entities
    if pass_mode in ['1', 'all']:
        filtered_entities = load_filtered_entities(s3_storage, video_id)
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
        place_entity_count = count_place_entities(s3_storage, video_id)

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

    # Save extracted insights to S3
    if all_insights:
        try:
            processing_date = datetime.now(timezone.utc).strftime('%Y%m%d')
            extraction_pass = f"pass{pass_mode}" if pass_mode in ['1', '2'] else 'pass_all'

            insights_storage.save_extracted_insights(
                insights=all_insights,
                extraction_pass=extraction_pass,
                processing_date=processing_date
            )

            logger.info(
                f"✓ Video {video_id}: Extracted {stats['total_insights']} insights "
                f"(Pass 1: {stats['pass1_insights']}, Pass 2: {stats['pass2_insights']})"
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

    # Initialize storage and tracking
    try:
        s3_storage = S3Storage()
        insights_storage = InsightsStorage(s3_storage)
        insight_registry = InsightRegistry(s3_storage)
        metadata_tracker = MetadataTracker(s3_storage)
        cost_tracker = CostTracker()

        # Load insight registry
        insight_registry.load()

        logger.info("✓ Initialized storage and tracking")

    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Find videos ready for processing
    try:
        ready_videos = find_videos_ready_for_insights(metadata_tracker, limit=limit)

        if not ready_videos:
            logger.info("No videos ready for insights processing")
            logger.info("Criteria: Stage 3 complete, insights_pipeline not processed")
            return

        logger.info(f"Found {len(ready_videos)} videos ready for processing\n")

    except Exception as e:
        logger.error(f"Failed to find ready videos: {e}")
        sys.exit(1)

    # Process each video
    success_count = 0
    failed_videos = []
    video_stats = []

    logger.info("Processing videos...\n")

    with tqdm(total=len(ready_videos), desc="Extracting insights") as pbar:
        for video_id in ready_videos:
            # Mark as processing
            try:
                metadata_tracker.start_stage(video_id, 'insights_pipeline', save_to_s3=True)
            except Exception as e:
                logger.warning(f"Failed to mark {video_id} as processing: {e}")

            # Process video
            success, stats = process_video_insights(
                video_id,
                s3_storage,
                insights_storage,
                cost_tracker,
                pass_mode=pass_mode
            )

            video_stats.append(stats)

            if success:
                success_count += 1

                # Mark as completed
                try:
                    metadata_tracker.complete_stage(
                        content_id=video_id,
                        stage='insights_pipeline',
                        s3_paths=[],  # Insights are saved separately
                        metadata={'insights_extracted': stats['total_insights']},
                        save_to_s3=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to mark {video_id} as completed: {e}")

            else:
                failed_videos.append(video_id)

                # Mark as failed
                try:
                    metadata_tracker.fail_stage(
                        content_id=video_id,
                        stage='insights_pipeline',
                        error='Insights extraction failed',
                        save_to_s3=True
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

    logger.info(f"\nInsights Extracted:")
    logger.info(f"  Pass 1 (filtered entities): {total_pass1_insights} insights from {total_pass1_entities} entities")
    logger.info(f"  Pass 2 (transcripts): {total_pass2_insights} insights from {total_pass2_applicable} videos")
    logger.info(f"  TOTAL: {total_insights} insights")

    # Cost report
    cost_report = cost_tracker.get_cost_report()
    logger.info(f"\nCost Report:")
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
    logger.info("1. Run Phase 2C deduplication to merge similar insights")
    logger.info("2. Run Phase 2C canonicalization to create canonical insights")
    logger.info("3. Check insights statistics: ./crawl.sh insights-stats")

    logger.info("\n✅ Insights extraction complete!\n")


if __name__ == '__main__':
    main()
