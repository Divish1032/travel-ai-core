"""
User model for authentication and user management.

This model stores core user information synced from Firebase Authentication.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """
    User model representing authenticated users.

    This model syncs with Firebase Authentication and stores
    core user information and preferences.
    """

    __tablename__ = "users"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firebase integration
    firebase_uid = Column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
        comment="Firebase Authentication UID"
    )

    # User information
    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User email address"
    )
    display_name = Column(String(255), nullable=True, comment="User display name")
    photo_url = Column(String(512), nullable=True, comment="Profile photo URL")

    # User preferences (stored as JSON)
    preferences = Column(
        JSON,
        nullable=False,
        default=lambda: {
            "notifications_enabled": True,
            "email_notifications": True,
            "language": "en",
            "currency": "USD"
        },
        comment="User preferences and settings"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Account creation timestamp"
    )
    last_login = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last login timestamp"
    )

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the user account is active"
    )

    # Relationships
    traveler_profile = relationship(
        "TravelerProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    itineraries = relationship(
        "SavedItinerary",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    favorites = relationship(
        "Favorite",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    collections = relationship(
        "Collection",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # TODO: Uncomment these relationships as models are created in later phases
    # reviews = relationship(
    #     "UserReview",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )
    # trips = relationship(
    #     "Trip",
    #     back_populates="user",
    #     cascade="all, delete-orphan"
    # )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, email={self.email})>"
