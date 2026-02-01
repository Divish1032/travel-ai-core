#!/usr/bin/env python3
"""
Migrate existing S3 data to PostgreSQL.

Backfills data from S3 storage to PostgreSQL tables:
- MetadataTracker → videos table
- Stage 2 entities → extracted_entities table
- Stage 3 canonical entities → canonical_entities table
- Insights → insights table

Usage:
    # Migrate everything
    python cli/migrate_s3_to_postgres.py

    # Migrate specific stages
    python cli/migrate_s3_to_postgres.py --stage 2
    python cli/migrate_s3_to_postgres.py --stage 3

    # Dry run (no writes)
    python cli/migrate_s3_to_postgres.py --dry-run

    # Limit number of items
    python cli/migrate_s3_to_postgres.py --limit 10
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from tqdm import tqdm
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.processors.stage3_loader import load_all_stage2_entities
from src.storage.stage3_storage import Stage3Storage
from src.utils.logging import get_logger, setup_logging

# Import models
from webapp.backend.app.database import Base
from webapp.backend.app.models import (
    Video, Transcript, VideoTravelerProfile,
    ExtractedEntity, CanonicalEntity, EntityExperience,
    Insight, InsightMention,
    StageStatus, EntityType, Sentiment
)
from webapp.backend.app.config import settings

logger = get_logger(__name__)


# =============================================================================
# Migration Functions
# =============================================================================

def migrate_metadata_tracker(
    db: Session,
    s3: S3Storage,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Migrate MetadataTracker from S3 to videos table.

    Args:
        db: Database session
        s3: S3Storage instance
        limit: Maximum number of videos to migrate
        dry_run: If True, don't write to database

    Returns:
        Statistics dict
    """
    logger.info("=" * 80)
    logger.info("STEP 1: Migrating MetadataTracker → videos table")
    logger.info("=" * 80)

    # Load metadata tracker from S3
    logger.info("Loading metadata tracker from S3...")
    tracker = MetadataTracker(s3_storage=s3)
    all_items = tracker.get_all_items()

    logger.info(f"Found {len(all_items)} videos in metadata tracker")

    if limit:
        all_items = dict(list(all_items.items())[:limit])
        logger.info(f"Limited to {len(all_items)} videos")

    stats = {
        'total': len(all_items),
        'inserted': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    # Migrate each video
    with tqdm(total=len(all_items), desc="Migrating videos") as pbar:
        for content_id, metadata in all_items.items():
            try:
                # Check if video already exists
                existing = db.query(Video).filter(Video.video_id == content_id).first()

                # Parse metadata
                stages = metadata.get('stages', {})
                content_metadata = metadata.get('content_metadata', {})

                # Stage 1 data
                stage1 = stages.get('stage_1_crawl', {})
                stage1_status = stage1.get('status', 'not_started')
                stage1_meta = stage1.get('metadata', {})

                # Stage 2 data
                stage2 = stages.get('stage_2_extract', {})
                stage2_status = stage2.get('status', 'not_started')
                stage2_meta = stage2.get('metadata', {})

                # Stage 3 data
                stage3 = stages.get('stage_3_deduplicate', {})
                stage3_status = stage3.get('status', 'not_started')
                stage3_meta = stage3.get('metadata', {})

                # Build video data
                video_data = {
                    'video_id': content_id,
                    'source': content_metadata.get('source', 'youtube'),
                    'source_url': content_metadata.get('url'),
                    'title': content_metadata.get('title'),
                    'description': content_metadata.get('description'),
                    'duration_seconds': content_metadata.get('duration_seconds'),
                    'language': content_metadata.get('language'),

                    # Stage 1
                    'stage_1_status': StageStatus(stage1_status) if stage1_status in ['not_started', 'pending', 'complete', 'failed'] else StageStatus.NOT_STARTED,
                    'stage_1_completed_at': _parse_timestamp(stage1.get('completed_at')),
                    'stage_1_error': stage1.get('error'),

                    # Stage 2
                    'stage_2_status': StageStatus(stage2_status) if stage2_status in ['not_started', 'pending', 'complete', 'failed'] else StageStatus.NOT_STARTED,
                    'stage_2_completed_at': _parse_timestamp(stage2.get('completed_at')),
                    'stage_2_error': stage2.get('error'),
                    'stage_2_entities_extracted': stage2_meta.get('entities_extracted', 0),
                    'stage_2_cost_usd': stage2_meta.get('cost_usd', 0.0),
                    'stage_2_llm_model': stage2_meta.get('llm_model'),
                    'stage_2_tokens_used': stage2_meta.get('tokens_used', 0),

                    # Stage 3
                    'stage_3_status': StageStatus(stage3_status) if stage3_status in ['not_started', 'pending', 'complete', 'failed'] else StageStatus.NOT_STARTED,
                    'stage_3_completed_at': _parse_timestamp(stage3.get('completed_at')),
                    'stage_3_error': stage3.get('error'),

                    # S3 paths
                    's3_raw_data_path': stage1.get('s3_paths', [None])[0],

                    # Quality
                    'extraction_quality': stage2_meta.get('extraction_quality'),
                }

                if not dry_run:
                    if existing:
                        # Update existing
                        for key, value in video_data.items():
                            if key != 'video_id':  # Don't update primary key
                                setattr(existing, key, value)
                        stats['updated'] += 1
                    else:
                        # Insert new
                        video = Video(**video_data)
                        db.add(video)
                        stats['inserted'] += 1

                    # Commit every 100 videos
                    if (stats['inserted'] + stats['updated']) % 100 == 0:
                        db.commit()

            except Exception as e:
                logger.error(f"Error migrating video {content_id}: {e}")
                stats['errors'] += 1

            finally:
                pbar.update(1)

    if not dry_run:
        db.commit()

    logger.info(f"\n✅ MetadataTracker migration complete:")
    logger.info(f"   Total: {stats['total']}")
    logger.info(f"   Inserted: {stats['inserted']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   Errors: {stats['errors']}")

    return stats


def migrate_stage2_entities(
    db: Session,
    s3: S3Storage,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Migrate Stage 2 entities from S3 to extracted_entities table.

    Args:
        db: Database session
        s3: S3Storage instance
        limit: Maximum number of videos to process
        dry_run: If True, don't write to database

    Returns:
        Statistics dict
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Migrating Stage 2 entities → extracted_entities table")
    logger.info("=" * 80)

    # Load Stage 2 entities from S3
    logger.info("Loading Stage 2 entities from S3...")
    load_result = load_all_stage2_entities(
        s3_storage=s3,
        prefix='stage2-extracted/new/',
        limit=limit,
        show_progress=True
    )

    all_entities = []
    for entity_type, entities in load_result['by_type'].items():
        all_entities.extend(entities)

    logger.info(f"Found {len(all_entities)} entities from {load_result['statistics']['total_videos']} videos")

    stats = {
        'total': len(all_entities),
        'inserted': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    # Migrate each entity
    with tqdm(total=len(all_entities), desc="Migrating entities") as pbar:
        for entity_data in all_entities:
            try:
                # Extract entity data
                entity_dict = entity_data.get('entity', {})
                provenance = entity_data.get('provenance', {})

                video_id = provenance.get('content_id') or provenance.get('source_video_id', '')
                entity_id = entity_dict.get('entity_id', f"{video_id}_entity_{stats['inserted']}")

                # Check if entity already exists
                existing = db.query(ExtractedEntity).filter(ExtractedEntity.entity_id == entity_id).first()

                # Map entity type
                entity_type_str = entity_dict.get('entity_type', 'unknown')
                try:
                    entity_type = EntityType(entity_type_str)
                except ValueError:
                    entity_type = EntityType.UNKNOWN

                # Map sentiment
                sentiment_str = entity_dict.get('sentiment')
                sentiment = None
                if sentiment_str:
                    try:
                        sentiment = Sentiment(sentiment_str)
                    except ValueError:
                        pass

                # Build entity data
                extracted_entity_data = {
                    'entity_id': entity_id,
                    'video_id': video_id,
                    'entity_type': entity_type,
                    'entity_name': entity_dict.get('entity_name', ''),
                    'location': entity_dict.get('location'),
                    'city': entity_data.get('normalized_location'),
                    'country': entity_dict.get('country'),
                    'experience': entity_dict.get('experience'),
                    'sentiment': sentiment,
                    'rating': entity_dict.get('rating'),
                    'cost_mentioned': entity_dict.get('cost_mentioned'),
                    'timestamp_start': entity_dict.get('timestamp_start'),
                    'timestamp_end': entity_dict.get('timestamp_end'),
                    'tags': entity_dict.get('tags', []),
                    'confidence_score': entity_dict.get('confidence_score'),
                    'llm_model': provenance.get('llm_model'),
                    'extracted_at': _parse_timestamp(provenance.get('processed_at')),
                    'context': {
                        'provenance': provenance,
                        'original_data': entity_dict
                    }
                }

                if not dry_run:
                    if existing:
                        # Update existing
                        for key, value in extracted_entity_data.items():
                            if key != 'entity_id':
                                setattr(existing, key, value)
                        stats['updated'] += 1
                    else:
                        # Insert new
                        extracted_entity = ExtractedEntity(**extracted_entity_data)
                        db.add(extracted_entity)
                        stats['inserted'] += 1

                    # Commit every 100 entities
                    if (stats['inserted'] + stats['updated']) % 100 == 0:
                        db.commit()

            except Exception as e:
                logger.error(f"Error migrating entity: {e}")
                stats['errors'] += 1

            finally:
                pbar.update(1)

    if not dry_run:
        db.commit()

    logger.info(f"\n✅ Stage 2 entity migration complete:")
    logger.info(f"   Total: {stats['total']}")
    logger.info(f"   Inserted: {stats['inserted']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   Errors: {stats['errors']}")

    return stats


def migrate_stage3_canonical_entities(
    db: Session,
    s3: S3Storage,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Migrate Stage 3 canonical entities from S3 to canonical_entities table.

    Args:
        db: Database session
        s3: S3Storage instance
        limit: Maximum number of entities to migrate
        dry_run: If True, don't write to database

    Returns:
        Statistics dict
    """
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Migrating Stage 3 canonical entities → canonical_entities table")
    logger.info("=" * 80)

    # Load Stage 3 entities from S3
    logger.info("Loading Stage 3 canonical entities from S3...")
    stage3_storage = Stage3Storage(s3)
    canonical_entities = stage3_storage.load_all_canonical_entities()

    logger.info(f"Found {len(canonical_entities)} canonical entities")

    if limit:
        canonical_entities = canonical_entities[:limit]
        logger.info(f"Limited to {len(canonical_entities)} entities")

    stats = {
        'total': len(canonical_entities),
        'inserted': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    # Migrate each canonical entity
    with tqdm(total=len(canonical_entities), desc="Migrating canonical entities") as pbar:
        for entity in canonical_entities:
            try:
                entity_id = entity.get('entity_id')

                # Check if entity already exists
                existing = db.query(CanonicalEntity).filter(CanonicalEntity.entity_id == entity_id).first()

                # Map entity type
                entity_type_str = entity.get('entity_type', 'unknown')
                try:
                    entity_type = EntityType(entity_type_str)
                except ValueError:
                    entity_type = EntityType.UNKNOWN

                # Extract coordinates
                coordinates = entity.get('coordinates', {})
                latitude = coordinates.get('lat') if coordinates else None
                longitude = coordinates.get('lon') if coordinates else None

                # Build canonical entity data
                canonical_entity_data = {
                    'entity_id': entity_id,
                    'canonical_name': entity.get('canonical_name', ''),
                    'aliases': entity.get('aliases', []),
                    'entity_type': entity_type,
                    'city': entity.get('city'),
                    'country': entity.get('country'),
                    'location_description': entity.get('location'),
                    'latitude': latitude,
                    'longitude': longitude,
                    'geocoded_at': _parse_timestamp(coordinates.get('geocoded_at')) if coordinates else None,
                    'geocoding_source': coordinates.get('source') if coordinates else None,
                    'total_mentions': entity.get('total_mentions', 1),
                    'confidence_score': entity.get('confidence_score'),
                    'source_video_count': len(entity.get('source_video_ids', [])),
                    'consensus': entity.get('consensus'),
                    'temporal_info': entity.get('temporal_info'),
                    'logistics_info': entity.get('logistics_info'),
                    'practical_tips': entity.get('practical_tips', []),
                    'popularity_score': entity.get('popularity_score'),
                    'freshness_score': entity.get('freshness_score'),
                    'fame_score': entity.get('fame_score'),
                    'first_seen_video_id': entity.get('source_video_ids', [None])[0],
                    'last_seen_video_id': entity.get('source_video_ids', [None])[-1],
                }

                if not dry_run:
                    if existing:
                        # Update existing
                        for key, value in canonical_entity_data.items():
                            if key != 'entity_id':
                                setattr(existing, key, value)
                        stats['updated'] += 1
                    else:
                        # Insert new
                        canonical_entity = CanonicalEntity(**canonical_entity_data)
                        db.add(canonical_entity)
                        stats['inserted'] += 1

                    # Commit every 100 entities
                    if (stats['inserted'] + stats['updated']) % 100 == 0:
                        db.commit()

            except Exception as e:
                logger.error(f"Error migrating canonical entity {entity.get('entity_id')}: {e}")
                stats['errors'] += 1

            finally:
                pbar.update(1)

    if not dry_run:
        db.commit()

    logger.info(f"\n✅ Stage 3 canonical entity migration complete:")
    logger.info(f"   Total: {stats['total']}")
    logger.info(f"   Inserted: {stats['inserted']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   Errors: {stats['errors']}")

    return stats


# =============================================================================
# Helper Functions
# =============================================================================

def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime object."""
    if not timestamp_str:
        return None

    try:
        # Try parsing ISO format
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except Exception:
        return None


# =============================================================================
# CLI Interface
# =============================================================================

@click.command()
@click.option('--stage', type=int, help='Migrate specific stage only (1, 2, or 3)')
@click.option('--limit', type=int, help='Limit number of items to migrate (for testing)')
@click.option('--dry-run', is_flag=True, help='Preview migration without writing to database')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), default='INFO')
def main(stage: Optional[int], limit: Optional[int], dry_run: bool, log_level: str):
    """
    Migrate S3 data to PostgreSQL.

    Migrates existing pipeline data from S3 storage to PostgreSQL:
    - MetadataTracker → videos table
    - Stage 2 entities → extracted_entities table
    - Stage 3 canonical entities → canonical_entities table

    Examples:
        # Migrate everything
        python cli/migrate_s3_to_postgres.py

        # Test migration with 10 videos
        python cli/migrate_s3_to_postgres.py --limit 10 --dry-run

        # Migrate only Stage 2
        python cli/migrate_s3_to_postgres.py --stage 2
    """
    setup_logging(log_level=log_level)

    click.echo("\n" + "="*80)
    click.echo("  S3 to PostgreSQL Migration")
    click.echo("="*80 + "\n")

    if dry_run:
        click.echo("🔍 DRY RUN MODE - No data will be written\n")

    # Initialize S3 and database
    logger.info("Initializing S3 storage...")
    s3 = S3Storage()

    logger.info("Connecting to PostgreSQL...")
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Run migrations
        all_stats = {}

        if stage is None or stage == 1:
            stats = migrate_metadata_tracker(db, s3, limit=limit, dry_run=dry_run)
            all_stats['metadata'] = stats

        if stage is None or stage == 2:
            stats = migrate_stage2_entities(db, s3, limit=limit, dry_run=dry_run)
            all_stats['stage2'] = stats

        if stage is None or stage == 3:
            stats = migrate_stage3_canonical_entities(db, s3, limit=limit, dry_run=dry_run)
            all_stats['stage3'] = stats

        # Print summary
        click.echo("\n" + "="*80)
        click.echo("  Migration Summary")
        click.echo("="*80 + "\n")

        total_inserted = sum(s.get('inserted', 0) for s in all_stats.values())
        total_updated = sum(s.get('updated', 0) for s in all_stats.values())
        total_errors = sum(s.get('errors', 0) for s in all_stats.values())

        click.echo(f"Total inserted: {total_inserted}")
        click.echo(f"Total updated: {total_updated}")
        click.echo(f"Total errors: {total_errors}")

        if dry_run:
            click.echo("\n🔍 DRY RUN COMPLETE - No data was written")
        else:
            click.echo("\n✅ MIGRATION COMPLETE")

        click.echo("\n" + "="*80 + "\n")

    except KeyboardInterrupt:
        click.echo("\n\n⚠️  Migration interrupted by user\n")
        db.rollback()
        sys.exit(1)

    except Exception as e:
        click.echo(f"\n❌ Migration failed: {e}\n")
        logger.error(f"Migration failed: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)

    finally:
        db.close()


if __name__ == "__main__":
    main()
