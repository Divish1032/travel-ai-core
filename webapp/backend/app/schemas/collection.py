"""
Pydantic schemas for collection endpoints.

Request and response models for collections API.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class CollectionBase(BaseModel):
    """Base schema for collection with common fields."""

    name: str = Field(..., max_length=255, description="Collection name")
    description: Optional[str] = Field(None, description="Collection description")
    is_public: bool = Field(False, description="Whether collection is public")


class CollectionCreate(CollectionBase):
    """Schema for creating a new collection."""

    entity_ids: list[str] = Field(default_factory=list, description="Initial entity IDs")


class CollectionUpdate(BaseModel):
    """Schema for updating a collection."""

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_public: Optional[bool] = None


class CollectionResponse(CollectionBase):
    """Schema for collection response."""

    id: UUID
    user_id: UUID
    entity_ids: list[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class CollectionListResponse(BaseModel):
    """Schema for paginated collections list."""

    items: list[CollectionResponse]
    total: int
    page: int
    per_page: int
    pages: int


class AddPlaceToCollectionRequest(BaseModel):
    """Schema for adding a place to collection."""

    entity_id: str = Field(..., description="Entity ID to add")


class RemovePlaceFromCollectionRequest(BaseModel):
    """Schema for removing a place from collection."""

    entity_id: str = Field(..., description="Entity ID to remove")
