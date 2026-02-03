#!/usr/bin/env python3
"""
Stage 2 Batch Processor - Entity Extraction

Processes videos from Stage 1 (crawled & transcribed) through Stage 2 (entity extraction).

Usage:
    python cli/process_stage2.py [--limit N] [--force] [--log-level DEBUG]

Features:
    - Automatically finds videos ready for Stage 2 processing
    - Classifies videos as short (<20 min) or long (>=20 min)
    - Processes short videos with single-pass LLM extraction
    - Processes long videos with hierarchical chunked extraction (5-min chunks with 1-min overlap)
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
import uuid

import click
from tqdm import tqdm
from sqlalchemy.orm import Session

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.processors.stage2_extractor import (
    process_short_video,
    process_long_video,
    classify_video_length
)
from src.utils.config import config
from src.utils.logging import get_logger

# PostgreSQL imports (using core database module)
from src.database import SessionLocal
from src.database.models import (
    Video,
    ExtractedEntity,
    VideoTravelerProfile,
    StageStatus,
    EntityType,
    Sentiment
)

logger = get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def load_video_from_s3(s3_storage: S3Storage, s3_path: str) -> Optional[Dict[str, Any]]:
    """
    Load individual video data from S3 JSONL file.

    Args:
        s3_storage: S3Storage instance
        s3_path: S3 path to individual video file (e.g., "s3://bucket/raw/new/youtube_video_ABC123.jsonl")

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

        # Download individual file from S3
        logger.debug(f"Downloading from S3: {s3_key}")
        response = s3_storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')

        # Parse JSON (single video per file now)
        video_data = json.loads(content.strip())

        logger.debug(f"Loaded video: {video_data.get('source_id', 'unknown')}")
        return video_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON in {s3_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load video from {s3_path}: {e}")
        return None


def find_videos_for_stage2_from_postgres(
    db: Session,
    force: bool = False
) -> List[Video]:
    """
    Find videos ready for Stage 2 processing from PostgreSQL.

    Args:
        db: Database session
        force: If True, include videos that already have Stage 2 data

    Returns:
        List of Video ORM objects ready for processing
    """
    if force:
        # Include all videos with Stage 1 complete
        videos = db.query(Video).filter(
            Video.stage_1_status == StageStatus.COMPLETE
        ).all()
    else:
        # Only include videos not yet processed or incomplete in Stage 2
        videos = db.query(Video).filter(
            Video.stage_1_status == StageStatus.COMPLETE,
            Video.stage_2_status.in_([
                StageStatus.NOT_STARTED,
                StageStatus.PENDING,
                StageStatus.FAILED
            ])
        ).all()

    return videos


def find_videos_for_stage2(
    tracker: MetadataTracker,
    force: bool = False
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Find videos ready for Stage 2 processing (legacy S3 method).

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
            # Only include videos not yet processed or incomplete in Stage 2
            # pending = processing started but didn't complete (interrupted/crashed)
            if stage2_status in ['not_started', 'pending', 'failed']:
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


def save_stage2_to_postgres(
    db: Session,
    video_id: str,
    stage2_output,
    processing_time: float
) -> None:
    """
    Save Stage 2 extraction output to PostgreSQL.

    Args:
        db: Database session
        video_id: Video ID
        stage2_output: Stage2Output object from extraction
        processing_time: Processing time in seconds
    """
    # Update video record
    video = db.query(Video).filter(Video.video_id == video_id).first()
    if not video:
        logger.error(f"Video {video_id} not found in database")
        return

    # Update Stage 2 status
    video.stage_2_status = StageStatus.COMPLETE
    video.stage_2_completed_at = datetime.now(timezone.utc)
    video.stage_2_error = None
    video.stage_2_entities_extracted = len(stage2_output.entities)
    video.stage_2_cost_usd = stage2_output.cost_usd
    video.stage_2_llm_model = stage2_output.llm_model
    video.stage_2_tokens_used = stage2_output.tokens_used
    video.extraction_quality = stage2_output.extraction_quality
    video.updated_at = datetime.now(timezone.utc)

    # Save traveler profile
    if stage2_output.traveler_profile:
        # Check if profile already exists
        existing_profile = db.query(VideoTravelerProfile).filter(
            VideoTravelerProfile.video_id == video_id
        ).first()

        if existing_profile:
            # Update existing
            existing_profile.traveler_type = stage2_output.traveler_profile.traveler_type
            existing_profile.age_range = stage2_output.traveler_profile.age_range
            existing_profile.budget_tier = stage2_output.traveler_profile.budget_tier
            existing_profile.travel_style = stage2_output.traveler_profile.travel_style
            existing_profile.confidence_score = stage2_output.traveler_profile.confidence_score
            existing_profile.llm_model = stage2_output.llm_model
            existing_profile.extracted_at = datetime.now(timezone.utc)
        else:
            # Create new
            profile = VideoTravelerProfile(
                video_id=video_id,
                traveler_type=stage2_output.traveler_profile.traveler_type,
                age_range=stage2_output.traveler_profile.age_range,
                budget_tier=stage2_output.traveler_profile.budget_tier,
                travel_style=stage2_output.traveler_profile.travel_style,
                confidence_score=stage2_output.traveler_profile.confidence_score,
                llm_model=stage2_output.llm_model,
                extracted_at=datetime.now(timezone.utc)
            )
            db.add(profile)

    # Save extracted entities
    for entity in stage2_output.entities:
        # Generate unique entity_id
        entity_id = f"{video_id}_{uuid.uuid4().hex[:8]}"

        # Map entity type string to enum
        entity_type_str = entity.entity_type.lower()
        try:
            entity_type_enum = EntityType(entity_type_str)
        except ValueError:
            entity_type_enum = EntityType.UNKNOWN

        # Map sentiment string to enum
        sentiment_str = entity.sentiment.lower() if entity.sentiment else None
        try:
            sentiment_enum = Sentiment(sentiment_str) if sentiment_str else None
        except ValueError:
            sentiment_enum = None

        # Parse city and country from location
        city = None
        country = None
        if entity.location:
            parts = [p.strip() for p in entity.location.split(',')]
            if len(parts) >= 2:
                city = parts[0]
                country = parts[-1]
            elif len(parts) == 1:
                city = parts[0]

        # Create ExtractedEntity record
        extracted_entity = ExtractedEntity(
            entity_id=entity_id,
            video_id=video_id,
            entity_type=entity_type_enum,
            entity_name=entity.entity_name,
            location=entity.location,
            city=city,
            country=country,
            experience=entity.experience,
            sentiment=sentiment_enum,
            rating=entity.rating,
            cost_mentioned=entity.cost_mentioned,
            timestamp_start=entity.timestamp_start,
            timestamp_end=entity.timestamp_end,
            tags=entity.tags,
            confidence_score=entity.confidence_score,
            llm_model=stage2_output.llm_model,
            extracted_at=datetime.now(timezone.utc),
            context=entity.context,
            created_at=datetime.now(timezone.utc)
        )
        db.add(extracted_entity)

    # Commit all changes
    db.commit()
    logger.info(f"Saved Stage 2 data to PostgreSQL for {video_id}: {len(stage2_output.entities)} entities")


# =============================================================================
# Main Processing Function
# =============================================================================

def process_stage2_batch(
    limit: Optional[int] = None,
    force: bool = False,
    log_level: str = "INFO",
    provider: Optional[str] = None,
    use_semantic_chunking: bool = True,
    use_fuzzy_deduplication: bool = True
) -> Dict[str, Any]:
    """
    Process a batch of videos through Stage 2 entity extraction.

    Args:
        limit: Maximum number of videos to process (None = all)
        force: If True, reprocess videos that already have Stage 2 data
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        provider: LLM provider to use (openai or deepseek, default: from config)

    Returns:
        Summary dict with statistics
    """
    # Override provider if specified
    if provider:
        original_provider = config.LLM_PROVIDER
        config.LLM_PROVIDER = provider
        logger.info(f"Overriding LLM provider to: {provider}")
    else:
        original_provider = None

    # Set log level
    logger.info(f"Starting Stage 2 batch processing (limit={limit}, force={force}, provider={config.LLM_PROVIDER}, semantic_chunking={use_semantic_chunking}, fuzzy_dedup={use_fuzzy_deduplication})")

    # Validate API keys based on provider
    selected_provider = config.LLM_PROVIDER or "gemini"
    if selected_provider == "openai" and not config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set. Please add it to .env file.")
        logger.error("Get your API key from: https://platform.openai.com/api-keys")
        if original_provider:
            config.LLM_PROVIDER = original_provider
        return {
            'success': False,
            'error': 'OPENAI_API_KEY not configured'
        }
    elif selected_provider == "deepseek" and not config.DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not set. Please add it to .env file.")
        logger.error("Get your API key from: https://platform.deepseek.com/api_keys")
        if original_provider:
            config.LLM_PROVIDER = original_provider
        return {
            'success': False,
            'error': 'DEEPSEEK_API_KEY not configured'
        }
    elif selected_provider == "gemini" and not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set. Please add it to .env file.")
        logger.error("Get your API key from: https://aistudio.google.com/app/apikey")
        if original_provider:
            config.LLM_PROVIDER = original_provider
        return {
            'success': False,
            'error': 'GEMINI_API_KEY not configured'
        }

    # Initialize database and S3
    logger.info("Initializing PostgreSQL database and S3 storage...")
    db = SessionLocal()
    s3_storage = S3Storage()

    try:
        # Find videos ready for Stage 2 from PostgreSQL
        logger.info("Finding videos ready for Stage 2 processing from PostgreSQL...")
        ready_videos = find_videos_for_stage2_from_postgres(db, force=force)

        if not ready_videos:
            logger.warning("No videos found ready for Stage 2 processing")
            return {
                'success': True,
                'total_ready': 0,
                'processed': 0,
                'skipped': 0,
                'failed': 0,
                'total_cost_usd': 0.0,
                'total_tokens': 0,
                'short_videos': 0,
                'long_videos': 0,
                'avg_processing_time_seconds': 0.0
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
            for video in ready_videos:
                try:
                    # Extract video_id and source_id
                    video_id = video.video_id
                    source_id = video_id.replace("youtube_", "")

                    # Update progress bar description
                    pbar.set_description(f"Processing {source_id[:12]}...")

                    # Get Stage 1 S3 path
                    s3_path = video.s3_raw_data_path
                    if not s3_path:
                        logger.error(f"No Stage 1 S3 path found for {video_id}")
                        stats['failed'] += 1
                        pbar.update(1)
                        continue

                    # Load video data from S3 (individual file)
                    video_data = load_video_from_s3(s3_storage, s3_path)
                    if not video_data:
                        logger.error(f"Failed to load video data for {video_id}")
                        stats['failed'] += 1
                        pbar.update(1)
                        continue

                    # Classify video length
                    duration = video_data.get('duration_seconds', 0)

                    # Debug: Log the actual duration value
                    if duration == 0:
                        logger.warning(f"Video {source_id} has duration_seconds=0 or missing. Video data keys: {list(video_data.keys())}")

                    video_class = classify_video_length(duration)

                    # Mark Stage 2 as pending in database
                    video.stage_2_status = StageStatus.PENDING
                    video.updated_at = datetime.now(timezone.utc)
                    db.commit()

                    start_time = time.time()

                    if video_class == "long":
                        # Process long video with hierarchical chunking
                        logger.info(f"Processing long video {source_id} ({duration/60:.1f} min) with hierarchical extraction")
                        stats['long_videos'] += 1

                        stage2_output = process_long_video(
                            video_data=video_data,
                            raw_file_path=s3_path,
                            translate_non_english=True,
                            use_semantic_chunking=use_semantic_chunking,
                            use_fuzzy_deduplication=use_fuzzy_deduplication
                        )
                    else:
                        # Process short video with single-pass extraction
                        logger.info(f"Processing short video {source_id} ({duration/60:.1f} min)")
                        stats['short_videos'] += 1

                        stage2_output = process_short_video(
                            video_data=video_data,
                            raw_file_path=s3_path,
                            translate_non_english=True
                        )

                    processing_time = time.time() - start_time
                    stats['processing_times'].append(processing_time)

                    if not stage2_output:
                        logger.error(f"Stage 2 processing failed for {source_id}")

                        # Mark as failed in database
                        video.stage_2_status = StageStatus.FAILED
                        video.stage_2_error = "process_short_video() or process_long_video() returned None"
                        video.stage_2_completed_at = datetime.now(timezone.utc)
                        video.updated_at = datetime.now(timezone.utc)
                        db.commit()

                        stats['failed'] += 1
                        pbar.update(1)
                        continue

                    # Save output to PostgreSQL
                    logger.info(f"Saving Stage 2 output to PostgreSQL for {source_id}")

                    save_stage2_to_postgres(
                        db=db,
                        video_id=video_id,
                        stage2_output=stage2_output,
                        processing_time=processing_time
                    )

                    logger.info(f"Saved to PostgreSQL: {len(stage2_output.entities)} entities")

                    # Move raw file from raw/new/ to raw/stage2_processed/ (optional - keeps S3 organized)
                    try:
                        source_uri = s3_path  # Current location in raw/new/
                        # Extract filename from s3_path
                        filename = source_uri.split('/')[-1]
                        dest_uri = f"s3://{s3_storage.bucket_name}/raw/stage2_processed/{filename}"

                        logger.info(f"Moving raw file: {source_uri} -> {dest_uri}")
                        s3_storage.move_file(source_uri, dest_uri, delete_source=True)
                        logger.info("Raw file moved to stage2_processed/")

                        # Update video s3_raw_data_path to new location
                        video.s3_raw_data_path = dest_uri
                        db.commit()

                    except Exception as e:
                        logger.warning(f"Failed to move raw file (non-critical): {e}")
                        # Continue processing even if file movement fails

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
                    logger.error(f"Error processing {video_id}: {e}", exc_info=True)

                    # Mark as failed in database
                    try:
                        video.stage_2_status = StageStatus.FAILED
                        video.stage_2_error = str(e)[:1000]  # Truncate to fit TEXT field
                        video.stage_2_completed_at = datetime.now(timezone.utc)
                        video.updated_at = datetime.now(timezone.utc)
                        db.commit()
                    except Exception as db_error:
                        logger.error(f"Failed to update database: {db_error}")
                        db.rollback()

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

        # Add success flag and provider info
        stats['success'] = True
        stats['llm_provider'] = config.LLM_PROVIDER

        # Restore original provider if it was overridden
        if original_provider:
            config.LLM_PROVIDER = original_provider

        return stats

    finally:
        # Always close database session
        db.close()


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
@click.option(
    '--provider',
    type=click.Choice(['openai', 'deepseek', 'gemini'], case_sensitive=False),
    default=None,
    help='LLM provider to use (default: from .env LLM_PROVIDER)'
)
@click.option(
    '--semantic-chunking/--no-semantic-chunking',
    default=True,
    help='Use semantic chunking for long videos (split at topic boundaries instead of fixed 5-min)'
)
@click.option(
    '--fuzzy-dedup/--no-fuzzy-dedup',
    default=True,
    help='Use fuzzy matching for entity deduplication (requires rapidfuzz)'
)
def main(limit: Optional[int], force: bool, log_level: str, provider: Optional[str],
         semantic_chunking: bool, fuzzy_dedup: bool):
    """
    Process videos through Stage 2 entity extraction.

    Finds videos that completed Stage 1 (crawling & transcription) and
    processes them through Stage 2 (entity extraction with LLM).

    Examples:
        # Process first 5 videos with DeepSeek
        python cli/process_stage2.py --limit 5 --provider deepseek

        # Process all pending videos with OpenAI
        python cli/process_stage2.py --provider openai

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
            log_level=log_level,
            provider=provider,
            use_semantic_chunking=semantic_chunking,
            use_fuzzy_deduplication=fuzzy_dedup
        )

        # Print summary
        click.echo("\n" + "="*70)
        click.echo("  Processing Complete")
        click.echo("="*70)

        if not stats.get('success'):
            click.echo(f"\n❌ Error: {stats.get('error', 'Unknown error')}\n")
            sys.exit(1)

        click.echo(f"\nLLM Provider:           {stats.get('llm_provider', 'unknown')}")
        click.echo(f"Total videos ready:     {stats['total_ready']}")
        click.echo(f"Short videos (<20 min): {stats['short_videos']}")
        click.echo(f"Long videos (>=20 min): {stats['long_videos']}")
        click.echo(f"\n✅ Successfully processed:  {stats['processed']}")
        click.echo(f"⏭️  Skipped:                {stats['skipped']}")
        click.echo(f"❌ Failed:                 {stats['failed']}")

        if stats['processed'] > 0:
            click.echo(f"\n💰 Total cost:         ${stats['total_cost_usd']:.4f}")
            click.echo(f"🎫 Total tokens:       {stats['total_tokens']:,}")
            click.echo(f"⏱️  Avg processing time: {stats['avg_processing_time_seconds']:.1f}s per video")
            click.echo(f"💵 Avg cost per video: ${stats['total_cost_usd']/stats['processed']:.4f}")

            # Estimate cost for all 117 videos if only processing a subset
            if stats['total_ready'] > stats['processed']:
                estimated_total_cost = (stats['total_cost_usd'] / stats['processed']) * stats['total_ready']
                click.echo(f"\n📊 Estimated cost for all {stats['total_ready']} videos: ${estimated_total_cost:.2f}")

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
