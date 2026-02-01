"""
Insight models for travel tips and recommendations.

Stores canonical insights extracted from filtered entities and info-only videos.
Supports full-text search and relationship tracking.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.database import Base


class Insight(Base):
    """
    Canonical travel insight (deduplicated).

    Extracted from filtered non-place entities (apps, services) and
    info-only videos with travel tips.
    """
    __tablename__ = "insights"

    # Primary key
    insight_id = Column(String(255), primary_key=True, index=True)  # e.g., 'thailand_services_001'

    # Classification
    category = Column(String(100), nullable=False, index=True)  # 'tips', 'services', 'logistics', 'packing'
    scope = Column(String(100), nullable=False, index=True)  # 'thailand', 'bangkok', 'asia', 'global'

    # Content
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(ARRAY(String), nullable=True)

    # Aggregates
    source_video_count = Column(Integer, default=1)
    total_mentions = Column(Integer, default=1)
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    mentions = relationship("InsightMention", back_populates="insight", cascade="all, delete-orphan")
    related_entities = relationship("InsightRelatedEntity", back_populates="insight", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index('idx_insight_category_scope', 'category', 'scope'),
        # Full-text search index (created in migration)
        # CREATE INDEX idx_insight_content_fts ON insights
        # USING GIN(to_tsvector('english', content));
    )

    def __repr__(self):
        return f"<Insight(insight_id='{self.insight_id}', category='{self.category}', scope='{self.scope}')>"

    def to_dict(self, include_mentions=False):
        """Convert to dictionary for API responses."""
        data = {
            'insight_id': self.insight_id,
            'category': self.category,
            'scope': self.scope,
            'title': self.title,
            'content': self.content,
            'tags': self.tags,
            'source_video_count': self.source_video_count,
            'total_mentions': self.total_mentions,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_mentions:
            data['mentions'] = [m.to_dict() for m in self.mentions]

        return data


class InsightMention(Base):
    """
    Individual mention of an insight from a video.

    Tracks raw insight extractions before deduplication.
    """
    __tablename__ = "insight_mentions"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    insight_id = Column(
        String(255),
        ForeignKey('insights.insight_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    video_id = Column(
        String(255),
        ForeignKey('videos.video_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Source tracking
    source_type = Column(String(50), nullable=True)  # 'filtered_entity', 'transcript'
    source_entity_id = Column(String(255), nullable=True)  # If from filtered entity
    context = Column(Text, nullable=True)  # Original text from video

    # Timestamps
    mentioned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    insight = relationship("Insight", back_populates="mentions")

    def __repr__(self):
        return f"<InsightMention(insight_id='{self.insight_id}', video_id='{self.video_id}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'insight_id': self.insight_id,
            'video_id': self.video_id,
            'source_type': self.source_type,
            'source_entity_id': self.source_entity_id,
            'context': self.context,
            'mentioned_at': self.mentioned_at.isoformat() if self.mentioned_at else None,
        }


class InsightRelatedEntity(Base):
    """
    Links insights to related canonical entities (many-to-many).

    Example: "Use Grab app" insight → links to Bangkok attractions
    """
    __tablename__ = "insight_related_entities"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    insight_id = Column(
        String(255),
        ForeignKey('insights.insight_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    entity_id = Column(
        String(255),
        ForeignKey('canonical_entities.entity_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Relationship type
    relationship_type = Column(String(50), nullable=True)  # 'mentioned_in', 'applicable_to'

    # Relationships
    insight = relationship("Insight", back_populates="related_entities")
    canonical_entity = relationship("CanonicalEntity", back_populates="related_insights")

    # Indexes
    __table_args__ = (
        Index('idx_insight_entity', 'insight_id', 'entity_id', unique=True),
    )

    def __repr__(self):
        return f"<InsightRelatedEntity(insight='{self.insight_id}', entity='{self.entity_id}')>"
