"""
Database models package.

This package contains all SQLAlchemy ORM models for the application.
"""

# User/webapp models
from app.models.user import User
from app.models.traveler_profile import TravelerProfile
from app.models.itinerary import SavedItinerary
from app.models.favorite import Favorite
from app.models.collection import Collection

# Pipeline models (Stage 1-3 + Insights)
from app.models.video import Video, StageStatus
from app.models.transcript import Transcript
from app.models.video_traveler_profile import VideoTravelerProfile
from app.models.extracted_entity import ExtractedEntity, EntityType, Sentiment
from app.models.canonical_entity import CanonicalEntity
from app.models.entity_experience import EntityExperience
from app.models.insight import Insight, InsightMention, InsightRelatedEntity

__all__ = [
    # User/webapp models
    "User",
    "TravelerProfile",
    "SavedItinerary",
    "Favorite",
    "Collection",
    # Pipeline models
    "Video",
    "StageStatus",
    "Transcript",
    "VideoTravelerProfile",
    "ExtractedEntity",
    "EntityType",
    "Sentiment",
    "CanonicalEntity",
    "EntityExperience",
    "Insight",
    "InsightMention",
    "InsightRelatedEntity",
]
