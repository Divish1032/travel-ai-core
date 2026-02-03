"""
ExtractedEntity model for Stage 2 entity extraction output.

Stores raw entities extracted from video transcripts before deduplication.
One-to-many relationship: one video → many extracted entities.
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, Text, DateTime, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
import enum

from app.database import Base


class EntityType(str, enum.Enum):
    """Entity type enum matching Stage 2 extraction schema."""
    DESTINATION = "destination"
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    ACTIVITY = "activity"
    ATTRACTION = "attraction"
    TRANSPORTATION = "transportation"
    SHOPPING = "shopping"
    UNKNOWN = "unknown"


class Sentiment(str, enum.Enum):
    """Sentiment enum."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class ExtractedEntity(Base):
    """
    Individual entity extracted from video (Stage 2 output).

    Raw entities before deduplication and canonicalization.
    Maps to EntityExperience from Stage 2 extraction.
    """
    __tablename__ = "extracted_entities"

    # Primary key
    entity_id = Column(String(255), primary_key=True, index=True)  # e.g., 'youtube_abc123_entity_001'

    # Foreign key
    video_id = Column(String(255), ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False, index=True)

    # Entity classification
    entity_type = Column(SQLEnum(EntityType), nullable=False, index=True)

    # Core attributes
    entity_name = Column(String(500), nullable=False, index=True)
    location = Column(String(500), nullable=True)  # Original location string
    city = Column(String(255), nullable=True, index=True)  # Normalized city
    country = Column(String(255), nullable=True)  # Normalized country

    # Experience data
    experience = Column(Text, nullable=True)  # Experience description
    sentiment = Column(SQLEnum(Sentiment), nullable=True, index=True)
    rating = Column(Float, nullable=True)  # 1.0-5.0
    cost_mentioned = Column(String(100), nullable=True)  # e.g., "200 THB", "$50"

    # Temporal data
    timestamp_start = Column(Float, nullable=True)  # Video timestamp (seconds)
    timestamp_end = Column(Float, nullable=True)

    # Metadata
    tags = Column(ARRAY(String), nullable=True)  # Array of tags
    confidence_score = Column(Float, nullable=True)  # LLM confidence (0.0-1.0)

    # LLM extraction metadata
    llm_model = Column(String(100), nullable=True)
    extracted_at = Column(DateTime, nullable=True)

    # Additional context (flexible JSONB)
    context = Column(JSONB, nullable=True)  # Extra metadata from extraction

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    video = relationship("Video", back_populates="extracted_entities")
    # Link to canonical entity via entity_experiences table
    canonical_links = relationship("EntityExperience", back_populates="extracted_entity", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        # Composite index for deduplication queries
        Index('idx_entity_name_type', 'entity_name', 'entity_type'),
        Index('idx_entity_name_city_type', 'entity_name', 'city', 'entity_type'),
    )

    def __repr__(self):
        return f"<ExtractedEntity(entity_id='{self.entity_id}', name='{self.entity_name}', type='{self.entity_type.value}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'entity_id': self.entity_id,
            'video_id': self.video_id,
            'entity_type': self.entity_type.value if self.entity_type else None,
            'entity_name': self.entity_name,
            'location': self.location,
            'city': self.city,
            'country': self.country,
            'experience': self.experience,
            'sentiment': self.sentiment.value if self.sentiment else None,
            'rating': self.rating,
            'cost_mentioned': self.cost_mentioned,
            'timestamp_start': self.timestamp_start,
            'timestamp_end': self.timestamp_end,
            'tags': self.tags,
            'confidence_score': self.confidence_score,
            'context': self.context,
        }
