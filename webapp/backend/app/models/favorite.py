"""
Favorite places model.

Tracks user's favorite places/entities from the canonical database.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Favorite(Base):
    """
    User favorite places model.

    Links users to their favorited places from the canonical entities database.
    Each user can favorite a place only once (enforced by unique constraint).
    """

    __tablename__ = "favorites"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign key to user
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Entity ID from canonical database (e.g., "bangkok_khao_san_road")
    entity_id = Column(String(255), nullable=False, index=True)

    # Optional user notes about this favorite
    notes = Column(Text, nullable=True)

    # Timestamp when favorited
    saved_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    # Relationships
    user = relationship("User", back_populates="favorites")

    # Constraints
    __table_args__ = (
        UniqueConstraint("user_id", "entity_id", name="uq_user_entity_favorite"),
    )

    def __repr__(self):
        return f"<Favorite(id={self.id}, user_id={self.user_id}, entity_id={self.entity_id})>"
