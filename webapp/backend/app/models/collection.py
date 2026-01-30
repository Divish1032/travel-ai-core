"""
Collection model.

User-created collections of places for organizing trip planning.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship

from app.database import Base


class Collection(Base):
    """
    User collection model.

    Allows users to organize places into named collections (e.g., "Tokyo Must-Visit",
    "Romantic Spots in Paris", "Budget Eats Bangkok").
    Collections can be private or public for sharing.
    """

    __tablename__ = "collections"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign key to user
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Collection metadata
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Array of entity IDs from canonical database
    # Example: ["bangkok_khao_san_road", "bangkok_wat_pho", ...]
    entity_ids = Column(ARRAY(String), nullable=False, default=list)

    # Sharing settings
    is_public = Column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user = relationship("User", back_populates="collections")

    def __repr__(self):
        return f"<Collection(id={self.id}, name={self.name}, user_id={self.user_id}, places={len(self.entity_ids)})>"
