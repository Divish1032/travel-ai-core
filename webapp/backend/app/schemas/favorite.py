"""
Pydantic schemas for favorite endpoints.

Request and response models for favorites API.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FavoriteCreate(BaseModel):
    """Schema for adding a favorite."""

    entity_id: str = Field(..., max_length=255, description="Canonical entity ID")
    notes: Optional[str] = Field(None, description="User notes about this favorite")


class FavoriteUpdate(BaseModel):
    """Schema for updating a favorite."""

    notes: Optional[str] = Field(None, description="Updated notes")


class FavoriteResponse(BaseModel):
    """Schema for favorite response."""

    id: UUID
    user_id: UUID
    entity_id: str
    notes: Optional[str]
    saved_at: datetime

    model_config = {"from_attributes": True}


class FavoriteListResponse(BaseModel):
    """Schema for paginated favorites list."""

    items: list[FavoriteResponse]
    total: int
    page: int
    per_page: int
    pages: int


class FavoriteCheckRequest(BaseModel):
    """Schema for bulk checking favorites."""

    entity_ids: list[str] = Field(..., description="List of entity IDs to check")


class FavoriteCheckResponse(BaseModel):
    """Schema for favorite check response."""

    favorited: dict[str, bool] = Field(..., description="Map of entity_id to favorited status")
