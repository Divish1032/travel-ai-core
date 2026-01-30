"""
Database models package.

This package contains all SQLAlchemy ORM models for the application.
"""

from app.models.user import User
from app.models.traveler_profile import TravelerProfile
from app.models.itinerary import SavedItinerary
from app.models.favorite import Favorite
from app.models.collection import Collection

__all__ = [
    "User",
    "TravelerProfile",
    "SavedItinerary",
    "Favorite",
    "Collection",
]
