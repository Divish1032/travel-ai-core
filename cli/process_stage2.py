#!/usr/bin/env python3
"""
Stage 2 Batch Processor - Entity Extraction

Processes videos from Stage 1 (crawled & transcribed) through Stage 2 (entity extraction).

Usage:
    python cli/process_stage2.py [--limit N] [--force] [--log-level DEBUG]

Features:
    - Automatically finds videos ready for Stage 2 processing
    - Classifies videos as short (<15 min) or long (>=15 min)
    - Processes short videos with single-pass LLM extraction
    - Tracks progress with progress bar
    - Monitors costs and token usage
    - Updates metadata tracker in S3
    - Handles errors gracefully with retry logic

Examples:
    # Process first 5 videos (testing)
    python cli/process_stage2.py --limit 5

    # Process all pending videos
    python cli/process_stage2.py

    # Reprocess videos (override existing Stage 2 data)
    python cli/process_stage2.py --force --limit 10

    # Enable debug logging
    python cli/process_stage2.py --limit 1 --log-level DEBUG
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import click
from tqdm import tqdm

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.processors.stage2_extractor import (
    process_short_video,
    classify_video_length,
    calculate_word_count,
    estimate_tokens_from_transcript
)
from src.utils.config import config
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def load_video_from_s3(s3_storage: S3Storage, s3_path: str) -> Optional[Dict[str, Any]]:
    """
    Load video data from S3 JSONL file.

    Args:
        s3_storage: S3Storage instance
        s3_path: S3 path (e.g., "s3://bucket/path/to/file.jsonl")

    Returns:
        Video data dict, or None if loading failed
    """
    try:
        # Parse S3 path
        if not s3_path.startswith("s3://"):
            logger.error(f"Invalid S3 path format: {s3_path}")
            return None

        # Remove s3:// prefix and bucket name
        path_parts = s3_path.replace("s3://", "").split("/", 1)
        if len(path_parts) != 2:
            logger.error(f"Invalid S3 path format: {s3_path}")
            return None

        bucket_name = path_parts[0]
        s3_key = path_parts[1]

        # Download from S3
        logger.debug(f"Downloading from S3: {s3_key}")
        response = s3_storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')

        # Parse JSONL (may contain multiple videos, we want the first line)
        lines = content.strip().split('\n')
        if not lines:
            logger.error(f"Empty file: {s3_path}")
            return None

        # Parse first line as JSON
        video_data = json.loads(lines[0])

        logger.debug(f"Loaded video: {video_data.get('source_id', 'unknown')}")
        return video_data

    except Exception as e:
        logger.error(f"Failed to load video from {s3_path}: {e}")
        return None


def find_videos_for_stage2(
    tracker: MetadataTracker,
    force: bool = False
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Find videos ready for Stage 2 processing.

    Args:
        tracker: MetadataTracker instance
        force: If True, include videos that already have Stage 2 data

    Returns:
        List of (content_id, metadata) tuples ready for processing
    """
    all_items = tracker.get_all_items()
    ready_items = []

    for content_id, metadata in all_items.items():
        stages = metadata.get('stages', {})

        # Check if Stage 1 is complete
        stage1 = stages.get('stage_1_crawl', {})
        stage1_status = stage1.get('status', 'not_started')

        if stage1_status != 'complete':
            continue

        # Check Stage 2 status
        stage2 = stages.get('stage_2_extract', {})
        stage2_status = stage2.get('status', 'not_started')

        if force:
            # Include all Stage 1 complete videos
            ready_items.append((content_id, metadata))
        else:
            # Only include videos not yet processed in Stage 2
            if stage2_status in ['not_started', 'failed']:
                ready_items.append((content_id, metadata))

    return ready_items


def get_stage1_s3_path(metadata: Dict[str, Any]) -> Optional[str]:
    """
    Extract Stage 1 S3 path from metadata.

    Args:
        metadata: Video metadata dict

    Returns:
        S3 path to raw video data, or None if not found
    """
    stages = metadata.get('stages', {})
    stage1 = stages.get('stage_1_crawl', {})
    s3_paths = stage1.get('s3_paths', [])

    if not s3_paths:
        return None

    # Return first S3 path (raw video file)
    return s3_paths[0]


# =============================================================================
# Main Processing Function
# =============================================================================

def process_stage2_batch(
    limit: Optional[int] = None,
    force: bool = False,
    log_level: str = "INFO"
) -> Dict[str, Any]:
    """
    Process a batch of videos through Stage 2 entity extraction.

    Args:
        limit: Maximum number of videos to process (None = all)
        force: If True, reprocess videos that already have Stage 2 data
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Summary dict with statistics
    """
    # Set log level
    logger.info(f"Starting Stage 2 batch processing (limit={limit}, force={force})")

    # Validate OpenAI API key
    if not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in environment. Please add it to .env file.")
        logger.error("Get your API key from: https://platform.openai.com/api-keys")
        return {
            'success': False,
            'error': 'OPENAI_API_KEY not configured'
        }

    # Initialize S3 and metadata tracker
    logger.info("Initializing S3 storage and metadata tracker...")
    s3_storage = S3Storage(bucket_name=config.S3_BUCKET_NAME)
    tracker = MetadataTracker(s3_storage=s3_storage)

    # Load metadata from S3
    logger.info("Loading metadata from S3...")
    tracker.load_from_s3()

    # Find videos ready for Stage 2
    logger.info("Finding videos ready for Stage 2 processing...")
    ready_videos = find_videos_for_stage2(tracker, force=force)

    if not ready_videos:
        logger.warning("No videos found ready for Stage 2 processing")
        return {
            'success': True,
            'total_ready': 0,
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'total_cost_usd': 0.0,
            'total_tokens': 0
        }

    # Apply limit
    if limit:
        ready_videos = ready_videos[:limit]
        logger.info(f"Limited to {limit} videos")

    logger.info(f"Found {len(ready_videos)} videos ready for Stage 2 processing")

    # Processing statistics
    stats = {
        'total_ready': len(ready_videos),
        'processed': 0,
        'skipped': 0,
        'failed': 0,
        'total_cost_usd': 0.0,
        'total_tokens': 0,
        'short_videos': 0,
        'long_videos': 0,
        'processing_times': []
    }

    # Process each video with progress bar
    logger.info(f"Processing {len(ready_videos)} videos...")

    with tqdm(total=len(ready_videos), desc="Stage 2 Processing", unit="video") as pbar:
        for content_id, metadata in ready_videos:
            try:
                # Extract source_id (remove "youtube_" prefix)
                source_id = content_id.replace("youtube_", "")

                # Update progress bar description
                pbar.set_description(f"Processing {source_id[:12]}...")

                # Get Stage 1 S3 path
                s3_path = get_stage1_s3_path(metadata)
                if not s3_path:
                    logger.error(f"No Stage 1 S3 path found for {content_id}")
                    stats['failed'] += 1
                    pbar.update(1)
                    continue

                # Load video data from S3
                video_data = load_video_from_s3(s3_storage, s3_path)
                if not video_data:
                    logger.error(f"Failed to load video data for {content_id}")
                    stats['failed'] += 1
                    pbar.update(1)
                    continue

                # Classify video length
                duration = video_data.get('duration_seconds', 0)
                video_class = classify_video_length(duration)

                if video_class == "long":
                    logger.info(
                        f"Skipping long video {source_id} "
                        f"({duration/60:.1f} min). Hierarchical extraction not yet implemented."
                    )
                    stats['skipped'] += 1
                    stats['long_videos'] += 1
                    pbar.update(1)
                    continue

                stats['short_videos'] += 1

                # Start Stage 2 in metadata tracker
                tracker.start_stage(stage_name="stage_2_extract", content_id=content_id)

                # Process with single-pass extraction
                logger.info(f"Processing short video {source_id} ({duration/60:.1f} min)")

                start_time = time.time()

                stage2_output = process_short_video(
                    video_data=video_data,
                    raw_file_path=s3_path,
                    translate_non_english=True
                )

                processing_time = time.time() - start_time
                stats['processing_times'].append(processing_time)

                if not stage2_output:
                    logger.error(f"Stage 2 processing failed for {source_id}")

                    # Mark as failed in tracker
                    tracker.fail_stage(
                        stage_name="stage_2_extract",
                        content_id=content_id,
                        error_message="process_short_video() returned None"
                    )
                    tracker.save_to_s3()

                    stats['failed'] += 1
                    pbar.update(1)
                    continue

                # Save output to S3
                logger.info(f"Saving Stage 2 output to S3 for {source_id}")

                processing_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                output_s3_path = s3_storage.save_stage2_output(
                    output=stage2_output,
                    processing_date=processing_date
                )

                logger.info(f"Saved to: {output_s3_path}")

                # Update metadata tracker
                tracker.complete_stage(
                    stage_name="stage_2_extract",
                    content_id=content_id,
                    s3_paths=[output_s3_path],
                    metadata={
                        'entities_extracted': len(stage2_output.entities),
                        'extraction_quality': stage2_output.extraction_quality,
                        'tokens_used': stage2_output.tokens_used,
                        'cost_usd': stage2_output.cost_usd,
                        'llm_model': stage2_output.llm_model,
                        'processing_time_seconds': round(processing_time, 2)
                    }
                )

                # Save to S3 after each video
                tracker.save_to_s3()

                # Update statistics
                stats['processed'] += 1
                stats['total_cost_usd'] += stage2_output.cost_usd
                stats['total_tokens'] += stage2_output.tokens_used

                # Update progress bar with cost info
                pbar.set_postfix({
                    'processed': stats['processed'],
                    'cost': f"${stats['total_cost_usd']:.4f}",
                    'tokens': f"{stats['total_tokens']:,}"
                })

                logger.info(
                    f"Successfully processed {source_id}: "
                    f"{len(stage2_output.entities)} entities, "
                    f"quality={stage2_output.extraction_quality}, "
                    f"cost=${stage2_output.cost_usd:.4f}, "
                    f"time={processing_time:.1f}s"
                )

            except Exception as e:
                logger.error(f"Error processing {content_id}: {e}", exc_info=True)

                # Mark as failed
                try:
                    tracker.fail_stage(
                        stage_name="stage_2_extract",
                        content_id=content_id,
                        error_message=str(e)
                    )
                    tracker.save_to_s3()
                except Exception as tracker_error:
                    logger.error(f"Failed to update tracker: {tracker_error}")

                stats['failed'] += 1

            finally:
                pbar.update(1)

    # Calculate average processing time
    if stats['processing_times']:
        avg_time = sum(stats['processing_times']) / len(stats['processing_times'])
        stats['avg_processing_time_seconds'] = round(avg_time, 2)
    else:
        stats['avg_processing_time_seconds'] = 0

    # Remove detailed processing times from final stats
    del stats['processing_times']

    # Add success flag
    stats['success'] = True

    return stats


# =============================================================================
# CLI Interface
# =============================================================================

@click.command()
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Maximum number of videos to process (default: all)'
)
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Reprocess videos that already have Stage 2 data'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(limit: Optional[int], force: bool, log_level: str):
    """
    Process videos through Stage 2 entity extraction.

    Finds videos that completed Stage 1 (crawling & transcription) and
    processes them through Stage 2 (entity extraction with LLM).

    Examples:
        # Process first 5 videos
        python cli/process_stage2.py --limit 5

        # Process all pending videos
        python cli/process_stage2.py

        # Reprocess with debug logging
        python cli/process_stage2.py --force --limit 1 --log-level DEBUG
    """
    try:
        # Print banner
        click.echo("\n" + "="*70)
        click.echo("  Stage 2 Batch Processor - Entity Extraction")
        click.echo("="*70 + "\n")

        # Run processing
        stats = process_stage2_batch(
            limit=limit,
            force=force,
            log_level=log_level
        )

        # Print summary
        click.echo("\n" + "="*70)
        click.echo("  Processing Complete")
        click.echo("="*70)

        if not stats.get('success'):
            click.echo(f"\n❌ Error: {stats.get('error', 'Unknown error')}\n")
            sys.exit(1)

        click.echo(f"\nTotal videos ready:     {stats['total_ready']}")
        click.echo(f"Short videos:           {stats['short_videos']}")
        click.echo(f"Long videos (skipped):  {stats['long_videos']}")
        click.echo(f"\n✅ Successfully processed:  {stats['processed']}")
        click.echo(f"⏭️  Skipped:                {stats['skipped']}")
        click.echo(f"❌ Failed:                 {stats['failed']}")

        if stats['processed'] > 0:
            click.echo(f"\n💰 Total cost:         ${stats['total_cost_usd']:.4f}")
            click.echo(f"🎫 Total tokens:       {stats['total_tokens']:,}")
            click.echo(f"⏱️  Avg processing time: {stats['avg_processing_time_seconds']:.1f}s per video")
            click.echo(f"💵 Avg cost per video: ${stats['total_cost_usd']/stats['processed']:.4f}")

        click.echo("\n" + "="*70 + "\n")

        # Exit with appropriate code
        if stats['failed'] > 0:
            click.echo(f"⚠️  Warning: {stats['failed']} video(s) failed. Check logs for details.\n")
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        click.echo("\n\n⚠️  Processing interrupted by user.\n")
        sys.exit(130)

    except Exception as e:
        click.echo(f"\n❌ Fatal error: {e}\n")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
