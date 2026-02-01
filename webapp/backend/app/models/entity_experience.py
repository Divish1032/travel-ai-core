"""
EntityExperience model - Junction table linking canonical to extracted entities.

Many-to-many relationship:
- One canonical entity has many experiences (from different videos)
- One extracted entity links to one canonical entity
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class EntityExperience(Base):
    """
    Links canonical entities to extracted entities (experiences).

    Tracks which extracted mentions contribute to each canonical entity.
    Preserves all experience data from original extraction.
    """
    __tablename__ = "entity_experiences"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    canonical_entity_id = Column(
        String(255),
        ForeignKey('canonical_entities.entity_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    extracted_entity_id = Column(
        String(255),
        ForeignKey('extracted_entities.entity_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    video_id = Column(
        String(255),
        ForeignKey('videos.video_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Experience-specific data (denormalized for performance)
    mention_count = Column(Integer, default=1)
    sentiment = Column(String(50), nullable=True)
    rating = Column(Float, nullable=True)

    # Context from this specific experience
    context = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    canonical_entity = relationship("CanonicalEntity", back_populates="experiences")
    extracted_entity = relationship("ExtractedEntity", back_populates="canonical_links")

    # Indexes
    __table_args__ = (
        # Unique constraint: one extracted entity per canonical entity
        Index('idx_unique_canonical_extracted', 'canonical_entity_id', 'extracted_entity_id', unique=True),
        Index('idx_experience_video', 'video_id'),
    )

    def __repr__(self):
        return f"<EntityExperience(canonical='{self.canonical_entity_id}', extracted='{self.extracted_entity_id}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'canonical_entity_id': self.canonical_entity_id,
            'extracted_entity_id': self.extracted_entity_id,
            'video_id': self.video_id,
            'mention_count': self.mention_count,
            'sentiment': self.sentiment,
            'rating': self.rating,
            'context': self.context,
        }
