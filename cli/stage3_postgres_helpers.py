#!/usr/bin/env python3
"""
Helper functions for Stage 3 PostgreSQL operations.

Provides functions to load extracted entities from PostgreSQL and save canonical entities.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database.models import (
    Video,
    ExtractedEntity,
    CanonicalEntity,
    EntityExperience,
    StageStatus,
    EntityType
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def load_extracted_entities_from_postgres(
    db: Session,
    limit: Optional[int] = None,
    entity_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Load Stage 2 extracted entities from PostgreSQL.

    Args:
        db: Database session
        limit: Limit number of videos to load (for testing)
        entity_types: Filter by entity types (e.g., ['attraction', 'restaurant'])

    Returns:
        Dict with entities grouped by video and statistics
    """
    # Query videos with Stage 2 complete
    query = db.query(Video).filter(
        Video.stage_2_status == StageStatus.COMPLETE
    )

    if limit:
        query = query.limit(limit)

    videos = query.all()

    if not videos:
        logger.warning("No videos with Stage 2 complete found")
        return {
            'entities_by_video': {},
            'statistics': {
                'total_videos': 0,
                'total_entities': 0,
                'entities_by_type': {}
            }
        }

    # Load entities for these videos
    video_ids = [v.video_id for v in videos]

    entities_query = db.query(ExtractedEntity).filter(
        ExtractedEntity.video_id.in_(video_ids)
    )

    # Filter by entity types if specified
    if entity_types:
        entity_type_enums = []
        for et in entity_types:
            try:
                entity_type_enums.append(EntityType(et.lower()))
            except ValueError:
                logger.warning(f"Invalid entity type: {et}")

        if entity_type_enums:
            entities_query = entities_query.filter(
                ExtractedEntity.entity_type.in_(entity_type_enums)
            )

    entities = entities_query.all()

    # Group entities by video
    entities_by_video = {}
    entities_by_type = {}

    for entity in entities:
        video_id = entity.video_id

        if video_id not in entities_by_video:
            entities_by_video[video_id] = []

        # Convert ORM object to dict format expected by deduplication pipeline
        # Must match the nested format from stage3_loader.py:
        # {
        #   'original_name': str,
        #   'normalized_name': str,
        #   'original_location': str,
        #   'normalized_location': str,
        #   'entity': { ... nested entity data ... },
        #   'provenance': { ... }
        # }

        # Normalize name and location for deduplication
        entity_name = entity.entity_name or 'Unknown'
        location_str = entity.location or entity.city or 'Unknown'

        entity_dict = {
            # Deduplication uses these fields
            'original_name': entity_name,
            'normalized_name': entity_name.lower().strip(),
            'original_location': location_str,
            'normalized_location': location_str.lower().strip(),

            # Nested entity data (accessed as entity_data['entity']['field_name'])
            'entity': {
                'entity_id': entity.entity_id,
                'entity_name': entity_name,
                'entity_type': entity.entity_type.value,
                'location': location_str,
                'city': entity.city,
                'country': entity.country,
                'experience': entity.experience,
                'sentiment': entity.sentiment.value if entity.sentiment else None,
                'rating': entity.rating,
                'cost_mentioned': entity.cost_mentioned,
                'timestamp_start': entity.timestamp_start,
                'timestamp_end': entity.timestamp_end,
                'tags': entity.tags or [],
                'confidence_score': entity.confidence_score,
                'llm_model': entity.llm_model,
                'extracted_at': entity.extracted_at.isoformat() if entity.extracted_at else None,
                'context': entity.context
            },

            # Provenance for tracing back to source
            'provenance': {
                'source_video_id': entity.video_id,
                'content_id': entity.video_id,  # For metadata tracker compatibility
                'language': 'unknown',  # Not stored in current schema
                'processed_at': entity.created_at.isoformat() if entity.created_at else None,
                'traveler_profile': {}  # Not extracted yet at Stage 2
            }
        }

        entities_by_video[video_id].append(entity_dict)

        # Track by type
        entity_type = entity.entity_type.value
        entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1

    logger.info(f"Loaded {len(entities)} entities from {len(videos)} videos")

    return {
        'entities_by_video': entities_by_video,
        'statistics': {
            'total_videos': len(videos),
            'total_entities': len(entities),
            'entities_by_type': entities_by_type
        }
    }


def load_existing_canonical_entities(
    db: Session,
    entity_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Load existing canonical entities from PostgreSQL for incremental mode.

    Args:
        db: Database session
        entity_types: Filter by entity types

    Returns:
        List of canonical entities as dicts
    """
    query = db.query(CanonicalEntity)

    if entity_types:
        entity_type_enums = []
        for et in entity_types:
            try:
                entity_type_enums.append(EntityType(et.lower()))
            except ValueError:
                logger.warning(f"Invalid entity type: {et}")

        if entity_type_enums:
            query = query.filter(CanonicalEntity.entity_type.in_(entity_type_enums))

    entities = query.all()

    canonical_entities = []
    for entity in entities:
        entity_dict = {
            'entity_id': entity.entity_id,
            'canonical_name': entity.canonical_name,
            'aliases': entity.aliases or [],
            'entity_type': entity.entity_type.value,
            'city': entity.city,
            'country': entity.country,
            'location_description': entity.location_description,
            'latitude': entity.latitude,
            'longitude': entity.longitude,
            'geocoded_at': entity.geocoded_at.isoformat() if entity.geocoded_at else None,
            'geocoding_source': entity.geocoding_source,
            'total_mentions': entity.total_mentions,
            'confidence_score': entity.confidence_score,
            'source_video_count': entity.source_video_count,
            'consensus': entity.consensus,
            'temporal_info': entity.temporal_info,
            'logistics_info': entity.logistics_info,
            'practical_tips': entity.practical_tips or [],
            'popularity_score': entity.popularity_score,
            'freshness_score': entity.freshness_score,
            'fame_score': entity.fame_score,
            'first_seen_video_id': entity.first_seen_video_id,
            'last_seen_video_id': entity.last_seen_video_id,
            'created_at': entity.created_at.isoformat() if entity.created_at else None,
            'updated_at': entity.updated_at.isoformat() if entity.updated_at else None
        }
        canonical_entities.append(entity_dict)

    logger.info(f"Loaded {len(canonical_entities)} existing canonical entities")
    return canonical_entities


def save_canonical_entities_to_postgres(
    db: Session,
    canonical_entities: List[Dict[str, Any]],
    video_ids: List[str]
) -> Dict[str, Any]:
    """
    Save canonical entities to PostgreSQL.

    Args:
        db: Database session
        canonical_entities: List of canonical entity dicts
        video_ids: List of video IDs that were processed

    Returns:
        Dict with save statistics
    """
    saved_count = 0
    updated_count = 0
    experience_count = 0

    for entity in canonical_entities:
        entity_id = entity.get('entity_id')

        # Check if entity already exists
        existing = db.query(CanonicalEntity).filter(
            CanonicalEntity.entity_id == entity_id
        ).first()

        # Map entity type
        entity_type_str = entity.get('entity_type', 'unknown')
        try:
            entity_type_enum = EntityType(entity_type_str.lower())
        except ValueError:
            entity_type_enum = EntityType.UNKNOWN

        if existing:
            # Update existing entity
            existing.canonical_name = entity.get('canonical_name')
            existing.aliases = entity.get('aliases', [])
            existing.entity_type = entity_type_enum
            existing.city = entity.get('city')
            existing.country = entity.get('country')
            existing.location_description = entity.get('location_description')
            existing.latitude = entity.get('latitude')
            existing.longitude = entity.get('longitude')
            existing.total_mentions = entity.get('total_mentions', 1)
            existing.confidence_score = entity.get('confidence_score')
            existing.source_video_count = entity.get('source_video_count', 1)
            existing.consensus = entity.get('consensus')
            existing.temporal_info = entity.get('temporal_info')
            existing.logistics_info = entity.get('logistics_info')
            existing.practical_tips = entity.get('practical_tips', [])
            existing.popularity_score = entity.get('popularity_score')
            existing.freshness_score = entity.get('freshness_score')
            existing.fame_score = entity.get('fame_score')
            existing.last_seen_video_id = entity.get('last_seen_video_id')
            existing.updated_at = datetime.now(timezone.utc)

            updated_count += 1
        else:
            # Create new entity
            new_entity = CanonicalEntity(
                entity_id=entity_id,
                canonical_name=entity.get('canonical_name'),
                aliases=entity.get('aliases', []),
                entity_type=entity_type_enum,
                city=entity.get('city'),
                country=entity.get('country'),
                location_description=entity.get('location_description'),
                latitude=entity.get('latitude'),
                longitude=entity.get('longitude'),
                geocoded_at=datetime.fromisoformat(entity['geocoded_at']) if entity.get('geocoded_at') else None,
                geocoding_source=entity.get('geocoding_source'),
                total_mentions=entity.get('total_mentions', 1),
                confidence_score=entity.get('confidence_score'),
                source_video_count=entity.get('source_video_count', 1),
                consensus=entity.get('consensus'),
                temporal_info=entity.get('temporal_info'),
                logistics_info=entity.get('logistics_info'),
                practical_tips=entity.get('practical_tips', []),
                popularity_score=entity.get('popularity_score'),
                freshness_score=entity.get('freshness_score'),
                fame_score=entity.get('fame_score'),
                first_seen_video_id=entity.get('first_seen_video_id'),
                last_seen_video_id=entity.get('last_seen_video_id'),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(new_entity)
            saved_count += 1

        # Create entity experiences (links between canonical and extracted entities)
        experiences = entity.get('experiences', [])
        for exp in experiences:
            extracted_entity_id = exp.get('entity_id')

            # Check if experience already exists
            existing_exp = db.query(EntityExperience).filter(
                EntityExperience.canonical_entity_id == entity_id,
                EntityExperience.extracted_entity_id == extracted_entity_id
            ).first()

            if not existing_exp:
                new_experience = EntityExperience(
                    canonical_entity_id=entity_id,
                    extracted_entity_id=extracted_entity_id,
                    video_id=exp.get('video_id'),
                    mention_count=1,
                    sentiment=exp.get('sentiment'),
                    rating=exp.get('rating'),
                    context=exp.get('context'),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(new_experience)
                experience_count += 1

    # Update videos to mark Stage 3 complete
    for video_id in video_ids:
        video = db.query(Video).filter(Video.video_id == video_id).first()
        if video:
            video.stage_3_status = StageStatus.COMPLETE
            video.stage_3_completed_at = datetime.now(timezone.utc)
            video.stage_3_error = None
            video.updated_at = datetime.now(timezone.utc)

    # Commit all changes
    db.commit()

    logger.info(f"Saved {saved_count} new canonical entities, updated {updated_count}, created {experience_count} experiences")

    return {
        'saved': saved_count,
        'updated': updated_count,
        'experiences': experience_count,
        'total': saved_count + updated_count
    }
