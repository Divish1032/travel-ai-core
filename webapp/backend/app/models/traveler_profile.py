"""
Traveler Profile model for personalization.

This model stores user travel preferences and profile information
used for personalized recommendations and RAG functions.
"""

import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.database import Base


class TravelerProfile(Base):
    """
    Traveler Profile model for personalization.

    Stores travel preferences, style, and interests used by
    RAG functions for personalized recommendations.
    """

    __tablename__ = "traveler_profiles"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign key to User (one-to-one relationship)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        comment="Reference to user"
    )

    # Traveler type (solo, couple, family, group)
    traveler_type = Column(
        String(50),
        nullable=False,
        default="solo",
        comment="Type of traveler: solo, couple, family, group"
    )

    # Budget tier (budget, mid-range, luxury)
    budget_tier = Column(
        String(50),
        nullable=False,
        default="mid-range",
        comment="Budget preference: budget, mid-range, luxury"
    )

    # Travel style (array of strings)
    # Examples: ["party", "cultural", "adventure", "relaxation", "foodie"]
    travel_style = Column(
        ARRAY(String),
        nullable=False,
        default=list,
        comment="Travel style preferences (e.g., party, cultural, adventure)"
    )

    # Interests (array of strings)
    # Examples: ["food", "nightlife", "nature", "shopping", "history", "art"]
    interests = Column(
        ARRAY(String),
        nullable=False,
        default=list,
        comment="Travel interests (e.g., food, nightlife, nature)"
    )

    # Age range (optional)
    # Examples: "18-25", "26-35", "36-45", "46-60", "60+"
    age_range = Column(
        String(20),
        nullable=True,
        comment="Age range for age-specific recommendations"
    )

    # Relationship back to User
    user = relationship("User", back_populates="traveler_profile")

    def __repr__(self) -> str:
        """String representation of TravelerProfile."""
        return (
            f"<TravelerProfile(user_id={self.user_id}, "
            f"type={self.traveler_type}, budget={self.budget_tier})>"
        )
