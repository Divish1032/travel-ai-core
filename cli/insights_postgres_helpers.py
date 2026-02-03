#!/usr/bin/env python3
"""
PostgreSQL helper functions for insights pipeline.

Provides database operations for:
- Loading videos ready for insights processing
- Loading filtered entities and transcripts
- Saving extracted insights
- Saving canonical insights
- Loading existing insights
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import (
    Video,
    CanonicalEntity,
    Transcript,
    Insight,
    InsightMention,
    InsightRelatedEntity,
    StageStatus,
    EntityType
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Query Videos for Insights Processing
# =============================================================================

def find_videos_ready_for_insights_from_postgres(
    db: Session,
    limit: Optional[int] = None
) -> List[str]:
    """
    Find videos ready for insights processing from PostgreSQL.

    Criteria:
    - Stage 3 is complete
    - insights_status is not 'complete'

    Args:
        db: Database session
        limit: Maximum number of videos to return

    Returns:
        List of video IDs ready for insights processing
    """
    query = db.query(Video.video_id).filter(
        Video.stage_3_status == StageStatus.COMPLETE,
        Video.insights_status.in_([
            StageStatus.NOT_STARTED,
            StageStatus.PENDING,
            StageStatus.FAILED
        ])
    )

    if limit:
        query = query.limit(limit)

    video_ids = [row[0] for row in query.all()]

    logger.debug(f"Found {len(video_ids)} videos ready for insights processing")
    return video_ids


# =============================================================================
# Load Video Data
# =============================================================================

def load_video_metadata_from_postgres(
    db: Session,
    video_id: str
) -> Optional[Dict[str, Any]]:
    """
    Load video metadata and transcript from PostgreSQL.

    Args:
        db: Database session
        video_id: Video ID

    Returns:
        Video metadata dict with transcript, or None if not found
    """
    video = db.query(Video).filter(Video.video_id == video_id).first()

    if not video:
        logger.warning(f"Video {video_id} not found in database")
        return None

    # Load transcript
    transcript_text = ""
    transcripts = db.query(Transcript).filter(
        Transcript.video_id == video_id
    ).order_by(Transcript.segment_index).all()

    if transcripts:
        transcript_text = " ".join([t.text for t in transcripts if t.text])

    # Build metadata dict compatible with existing code
    video_metadata = {
        'video_id': video.video_id,
        'source': 'youtube',
        'title': video.title or '',
        'description': video.description or '',
        'transcript': transcript_text,
        'duration_seconds': video.duration_seconds,
        'published_at': video.published_at.isoformat() if video.published_at else None,
        'channel_title': video.channel_title or '',
        'view_count': video.view_count or 0,
        'like_count': video.like_count or 0,
        'comment_count': video.comment_count or 0,
    }

    return video_metadata


def load_filtered_entities_from_postgres(
    db: Session,
    video_id: str
) -> List[Dict[str, Any]]:
    """
    Load filtered entities (non-place entities) for insights from PostgreSQL.

    Filters for entity types that are insights candidates:
    - APP, SERVICE, GEAR, TRANSPORT, etc. (non-place entities)

    Args:
        db: Database session
        video_id: Video ID

    Returns:
        List of filtered entity dicts
    """
    # Non-place entity types that are insights candidates
    insights_entity_types = [
        EntityType.APP,
        EntityType.SERVICE,
        EntityType.GEAR,
        EntityType.TRANSPORT,
        EntityType.TIP,
        EntityType.WARNING,
        EntityType.HACK,
        EntityType.OTHER
    ]

    entities = db.query(CanonicalEntity).filter(
        CanonicalEntity.source_video_ids.contains([video_id]),
        CanonicalEntity.entity_type.in_(insights_entity_types)
    ).all()

    # Convert to dict format
    filtered_entities = []
    for entity in entities:
        entity_dict = {
            'canonical_id': entity.canonical_id,
            'canonical_name': entity.canonical_name,
            'entity_type': entity.entity_type.value if entity.entity_type else None,
            'description': entity.description,
            'category': entity.category,
            'tags': entity.tags or [],
            'source_video_ids': entity.source_video_ids or [],
            'consensus': entity.consensus or {},
            'insights_candidate': True  # By definition, these are insights candidates
        }
        filtered_entities.append(entity_dict)

    logger.debug(f"Loaded {len(filtered_entities)} filtered entities for video {video_id}")
    return filtered_entities


def count_place_entities_from_postgres(
    db: Session,
    video_id: str
) -> int:
    """
    Count number of place entities for a video.

    Args:
        db: Database session
        video_id: Video ID

    Returns:
        Number of place entities
    """
    place_entity_types = [
        EntityType.ATTRACTION,
        EntityType.RESTAURANT,
        EntityType.HOTEL,
        EntityType.BAR,
        EntityType.CAFE,
        EntityType.SHOP,
        EntityType.VIEWPOINT,
        EntityType.BEACH,
        EntityType.PARK
    ]

    count = db.query(func.count(CanonicalEntity.canonical_id)).filter(
        CanonicalEntity.source_video_ids.contains([video_id]),
        CanonicalEntity.entity_type.in_(place_entity_types)
    ).scalar()

    return count or 0


# =============================================================================
# Save Insights to PostgreSQL
# =============================================================================

def save_extracted_insights_to_postgres(
    db: Session,
    video_id: str,
    insights: List[Dict[str, Any]],
    extraction_pass: str = 'all'
) -> Tuple[int, int]:
    """
    Save extracted insights to PostgreSQL.

    Args:
        db: Database session
        video_id: Video ID that insights were extracted from
        insights: List of insight dicts
        extraction_pass: Which pass extracted these ('pass1', 'pass2', 'pass_all')

    Returns:
        Tuple of (insights_saved, mentions_saved)
    """
    insights_saved = 0
    mentions_saved = 0

    for insight_data in insights:
        try:
            # Generate insight ID if not present
            if 'insight_id' not in insight_data:
                insight_data['insight_id'] = f"insight_{uuid.uuid4().hex[:12]}"

            # Create Insight record
            insight = Insight(
                insight_id=insight_data['insight_id'],
                category=insight_data.get('category', 'general'),
                subcategory=insight_data.get('subcategory'),
                insight_text=insight_data.get('insight_text', ''),
                destination=insight_data.get('destination', 'general'),
                entity_name=insight_data.get('entity_name'),
                entity_type=insight_data.get('entity_type'),
                context=insight_data.get('context', {}),
                tags=insight_data.get('tags', []),
                applicability=insight_data.get('applicability', {}),
                source_count=1,  # Initial source count
                confidence_score=insight_data.get('confidence_score', 0.8),
                is_canonical=False,  # Extracted insights are not canonical yet
                created_at=datetime.now(timezone.utc)
            )

            db.add(insight)
            insights_saved += 1

            # Create InsightMention (link to video)
            mention = InsightMention(
                insight_id=insight_data['insight_id'],
                video_id=video_id,
                mentioned_at=datetime.now(timezone.utc)
            )
            db.add(mention)
            mentions_saved += 1

            # If insight references entities, create InsightRelatedEntity records
            related_entities = insight_data.get('related_entities', [])
            if isinstance(related_entities, list):
                for entity_id in related_entities:
                    if entity_id:
                        related_entity = InsightRelatedEntity(
                            insight_id=insight_data['insight_id'],
                            entity_id=entity_id
                        )
                        db.add(related_entity)

        except Exception as e:
            logger.error(f"Failed to save insight {insight_data.get('insight_id')}: {e}")
            continue

    db.commit()

    logger.debug(
        f"Saved {insights_saved} insights and {mentions_saved} mentions "
        f"for video {video_id} (pass: {extraction_pass})"
    )

    return insights_saved, mentions_saved


def update_video_insights_status(
    db: Session,
    video_id: str,
    status: StageStatus,
    insights_count: int = 0,
    error: Optional[str] = None
) -> None:
    """
    Update video insights processing status.

    Args:
        db: Database session
        video_id: Video ID
        status: New status
        insights_count: Number of insights extracted
        error: Error message if failed
    """
    video = db.query(Video).filter(Video.video_id == video_id).first()

    if not video:
        logger.warning(f"Video {video_id} not found, cannot update insights status")
        return

    video.insights_status = status
    video.updated_at = datetime.now(timezone.utc)

    if status == StageStatus.COMPLETE:
        video.insights_completed_at = datetime.now(timezone.utc)

    db.commit()

    logger.debug(f"Updated video {video_id} insights status to {status.value}")


# =============================================================================
# Load Insights for Canonicalization
# =============================================================================

def load_extracted_insights_from_postgres(
    db: Session
) -> List[Dict[str, Any]]:
    """
    Load all extracted (non-canonical) insights from PostgreSQL.

    Args:
        db: Database session

    Returns:
        List of insight dicts
    """
    insights = db.query(Insight).filter(
        Insight.is_canonical == False
    ).all()

    # Convert to dict format
    insights_list = []
    for insight in insights:
        insight_dict = {
            'insight_id': insight.insight_id,
            'category': insight.category,
            'subcategory': insight.subcategory,
            'insight_text': insight.insight_text,
            'destination': insight.destination,
            'entity_name': insight.entity_name,
            'entity_type': insight.entity_type,
            'context': insight.context or {},
            'tags': insight.tags or [],
            'applicability': insight.applicability or {},
            'source_count': insight.source_count,
            'confidence_score': insight.confidence_score,
            'created_at': insight.created_at.isoformat() if insight.created_at else None
        }
        insights_list.append(insight_dict)

    logger.info(f"Loaded {len(insights_list)} extracted insights from PostgreSQL")
    return insights_list


def save_canonical_insights_to_postgres(
    db: Session,
    canonical_insights: List[Dict[str, Any]],
    dedup_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Save canonical insights to PostgreSQL.

    Updates existing insights to mark them as canonical.

    Args:
        db: Database session
        canonical_insights: List of canonical insight dicts
        dedup_stats: Deduplication statistics

    Returns:
        Results dict with counts
    """
    canonical_saved = 0
    canonical_updated = 0

    for canonical_data in canonical_insights:
        try:
            canonical_id = canonical_data.get('canonical_id')
            if not canonical_id:
                logger.warning(f"Canonical insight missing ID: {canonical_data.get('insight_text', '')[:50]}")
                continue

            # Check if insight exists
            existing = db.query(Insight).filter(
                Insight.insight_id == canonical_id
            ).first()

            if existing:
                # Update existing insight to mark as canonical
                existing.is_canonical = True
                existing.insight_text = canonical_data.get('insight_text', existing.insight_text)
                existing.source_count = canonical_data.get('source_count', 1)
                existing.confidence_score = canonical_data.get('confidence_score', 0.8)
                existing.tags = canonical_data.get('tags', [])
                existing.context = canonical_data.get('consensus', {})
                canonical_updated += 1
            else:
                # Create new canonical insight
                insight = Insight(
                    insight_id=canonical_id,
                    category=canonical_data.get('category', 'general'),
                    subcategory=canonical_data.get('subcategory'),
                    insight_text=canonical_data.get('insight_text', ''),
                    destination=canonical_data.get('destination', 'general'),
                    entity_name=canonical_data.get('entity_name'),
                    entity_type=canonical_data.get('entity_type'),
                    context=canonical_data.get('consensus', {}),
                    tags=canonical_data.get('tags', []),
                    applicability=canonical_data.get('applicability', {}),
                    source_count=canonical_data.get('source_count', 1),
                    confidence_score=canonical_data.get('confidence_score', 0.8),
                    is_canonical=True,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(insight)
                canonical_saved += 1

                # Add video mentions
                source_video_ids = canonical_data.get('source_video_ids', [])
                for video_id in source_video_ids:
                    mention = InsightMention(
                        insight_id=canonical_id,
                        video_id=video_id,
                        mentioned_at=datetime.now(timezone.utc)
                    )
                    db.add(mention)

        except Exception as e:
            logger.error(f"Failed to save canonical insight {canonical_data.get('canonical_id')}: {e}")
            continue

    db.commit()

    results = {
        'canonical_saved': canonical_saved,
        'canonical_updated': canonical_updated,
        'total': canonical_saved + canonical_updated
    }

    logger.info(
        f"Saved {canonical_saved} new canonical insights, "
        f"updated {canonical_updated} existing insights"
    )

    return results
