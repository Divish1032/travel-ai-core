"""
Pydantic schemas for itinerary endpoints.

Request and response models for saved itineraries API.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class ItineraryBase(BaseModel):
    """Base schema for itinerary with common fields."""

    title: Optional[str] = Field(None, max_length=255, description="Itinerary title")
    destination: str = Field(..., max_length=255, description="Destination name")
    duration_days: int = Field(..., gt=0, description="Trip duration in days")
    notes: Optional[str] = Field(None, description="User notes")


class ItineraryCreate(ItineraryBase):
    """Schema for creating a new itinerary."""

    itinerary_data: Dict[str, Any] = Field(..., description="Full itinerary JSON data from RAG")
    is_public: bool = Field(False, description="Whether itinerary is publicly shared")


class ItineraryUpdate(BaseModel):
    """Schema for updating an existing itinerary."""

    title: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    is_public: Optional[bool] = None
    itinerary_data: Optional[Dict[str, Any]] = None


class ItineraryResponse(ItineraryBase):
    """Schema for itinerary response."""

    id: UUID
    user_id: UUID
    itinerary_data: Dict[str, Any]
    is_public: bool
    share_token: Optional[str]
    share_expires_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ItineraryListResponse(BaseModel):
    """Schema for paginated itinerary list."""

    items: list[ItineraryResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ShareItineraryRequest(BaseModel):
    """Schema for sharing an itinerary."""

    expires_in_days: Optional[int] = Field(None, gt=0, le=365, description="Token expiration in days")


class ShareItineraryResponse(BaseModel):
    """Schema for share response."""

    share_token: str
    share_url: str
    expires_at: Optional[datetime]


class ExportFormat(str):
    """Supported export formats."""

    PDF = "pdf"
    JSON = "json"
    ICAL = "ical"


class ExportItineraryRequest(BaseModel):
    """Schema for exporting an itinerary."""

    format: str = Field(..., description="Export format (pdf, json, ical)")
