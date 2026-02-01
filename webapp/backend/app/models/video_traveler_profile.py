"""
VideoTravelerProfile model for traveler profile extracted from videos (Stage 2).

Different from TravelerProfile (user preferences):
- TravelerProfile: User's own travel preferences (for personalization)
- VideoTravelerProfile: Travel profile extracted from video vlogger (for entity matching)
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.database import Base


class VideoTravelerProfile(Base):
    """
    Traveler profile extracted from video content (Stage 2).

    Represents the vlogger's demographics and travel style.
    Used for entity profiling and consensus building.

    One-to-one with Video (one video → one profile).
    """
    __tablename__ = "video_traveler_profiles"

    # Primary key
    video_id = Column(
        String(255),
        ForeignKey('videos.video_id', ondelete='CASCADE'),
        primary_key=True,
        index=True
    )

    # Demographics
    traveler_type = Column(String(50), nullable=True)  # 'solo', 'couple', 'family', 'group', 'unknown'
    age_range = Column(String(20), nullable=True)  # '18-25', '26-35', '36-50', '50+', 'unknown'
    budget_tier = Column(String(50), nullable=True)  # 'budget', 'mid-range', 'luxury', 'unknown'

    # Preferences
    travel_style = Column(ARRAY(String), nullable=True)  # ['adventure', 'relaxation', 'cultural', 'foodie']

    # Extraction metadata
    confidence_score = Column(Float, nullable=True)  # LLM confidence (0.1-1.0)
    llm_model = Column(String(100), nullable=True)

    # Timestamps
    extracted_at = Column(datetime, default=datetime.utcnow, nullable=False)

    # Relationships
    video = relationship("Video", back_populates="traveler_profile")

    def __repr__(self):
        return f"<VideoTravelerProfile(video_id='{self.video_id}', type='{self.traveler_type}', budget='{self.budget_tier}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'video_id': self.video_id,
            'traveler_type': self.traveler_type,
            'age_range': self.age_range,
            'budget_tier': self.budget_tier,
            'travel_style': self.travel_style,
            'confidence_score': self.confidence_score,
        }
