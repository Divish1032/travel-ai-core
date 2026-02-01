"""
CanonicalEntity model for Stage 3 deduplicated and enriched entities.

Stores canonical (normalized) entities after deduplication and consensus building.
One canonical entity can have mentions from multiple videos.
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy import Enum as SQLEnum

from app.database import Base
from app.models.extracted_entity import EntityType


class CanonicalEntity(Base):
    """
    Canonical (deduplicated and enriched) entity from Stage 3.

    Represents a unique real-world place mentioned across multiple videos.
    Contains consensus data, enrichment, and geocoding.
    """
    __tablename__ = "canonical_entities"

    # Primary key (stable across runs via EntityRegistry)
    entity_id = Column(String(255), primary_key=True, index=True)  # e.g., 'attraction_bangkok_001'

    # Canonical attributes
    canonical_name = Column(String(500), nullable=False, index=True)
    aliases = Column(ARRAY(String), nullable=True)  # Alternative names
    entity_type = Column(SQLEnum(EntityType), nullable=False, index=True)

    # Location
    city = Column(String(255), nullable=True, index=True)
    country = Column(String(255), nullable=True, index=True)
    location_description = Column(Text, nullable=True)

    # Geolocation
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geocoded_at = Column(DateTime, nullable=True)
    geocoding_source = Column(String(50), nullable=True)  # 'google_maps', 'nominatim'

    # Aggregate statistics
    total_mentions = Column(Integer, default=1)
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0
    source_video_count = Column(Integer, default=1)  # How many videos mention this

    # Consensus data (LLM-generated, stored as JSONB)
    # Structure: {
    #   avg_rating: float,
    #   avg_cost: str,
    #   themes: [str],
    #   best_for: [str],
    #   top_experiences: [str],
    #   traveler_profiles: [{profile_key, count, avg_rating, sentiment_distribution}]
    # }
    consensus = Column(JSONB, nullable=True)

    # Enrichment data (Hybrid: transcript + LLM)
    # Structure: {
    #   opening_hours: str,
    #   best_time_to_visit: str,
    #   seasonal_info: str,
    #   source: 'transcript_extracted' | 'llm_inferred' | 'hybrid',
    #   confidence: float
    # }
    temporal_info = Column(JSONB, nullable=True)

    # Structure: {
    #   typical_duration: str,
    #   cost_range: str,
    #   booking_required: bool,
    #   accessibility: str,
    #   source: str,
    #   confidence: float
    # }
    logistics_info = Column(JSONB, nullable=True)

    # Structure: [str] - Array of practical tips
    practical_tips = Column(ARRAY(String), nullable=True)

    # Computed scores
    popularity_score = Column(Float, nullable=True, index=True)  # Based on mentions + recency
    freshness_score = Column(Float, nullable=True)  # Recency of mentions
    fame_score = Column(Float, nullable=True, index=True)  # Combination of popularity + confidence

    # Registry tracking
    first_seen_video_id = Column(String(255), nullable=True)
    last_seen_video_id = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    # Link to extracted entities via entity_experiences table
    experiences = relationship("EntityExperience", back_populates="canonical_entity", cascade="all, delete-orphan")

    # Link to insights
    related_insights = relationship("InsightRelatedEntity", back_populates="canonical_entity", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        # Composite index for common queries
        Index('idx_canonical_city_type', 'city', 'entity_type'),
        Index('idx_canonical_coordinates', 'latitude', 'longitude'),
        # Full-text search index (created in migration)
        # CREATE INDEX idx_canonical_name_fts ON canonical_entities
        # USING GIN(to_tsvector('english', canonical_name));
    )

    def __repr__(self):
        return f"<CanonicalEntity(entity_id='{self.entity_id}', name='{self.canonical_name}', city='{self.city}')>"

    def to_dict(self, include_experiences=False):
        """Convert to dictionary for API responses."""
        data = {
            'entity_id': self.entity_id,
            'canonical_name': self.canonical_name,
            'aliases': self.aliases,
            'entity_type': self.entity_type.value if self.entity_type else None,
            'city': self.city,
            'country': self.country,
            'location_description': self.location_description,
            'coordinates': {
                'lat': self.latitude,
                'lon': self.longitude,
                'source': self.geocoding_source,
            } if self.latitude and self.longitude else None,
            'total_mentions': self.total_mentions,
            'confidence_score': self.confidence_score,
            'source_video_count': self.source_video_count,
            'consensus': self.consensus,
            'temporal_info': self.temporal_info,
            'logistics_info': self.logistics_info,
            'practical_tips': self.practical_tips,
            'popularity_score': self.popularity_score,
            'freshness_score': self.freshness_score,
            'fame_score': self.fame_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_experiences:
            data['experiences'] = [exp.to_dict() for exp in self.experiences]

        return data
