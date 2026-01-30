"""
User and TravelerProfile schemas for request/response validation.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ============= User Schemas =============

class UserPreferences(BaseModel):
    """User preferences schema."""

    notifications_enabled: bool = True
    email_notifications: bool = True
    language: str = "en"
    currency: str = "USD"


class UserBase(BaseModel):
    """Base user schema with common fields."""

    email: EmailStr
    display_name: Optional[str] = None


class UserResponse(BaseModel):
    """Response schema for user data."""

    id: UUID
    firebase_uid: str
    email: str
    display_name: Optional[str]
    photo_url: Optional[str]
    preferences: Dict[str, Any]
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    """Request schema for updating user information."""

    display_name: Optional[str] = Field(None, max_length=255)
    photo_url: Optional[str] = Field(None, max_length=512)


class UserPreferencesUpdateRequest(BaseModel):
    """Request schema for updating user preferences."""

    notifications_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    language: Optional[str] = Field(None, max_length=10)
    currency: Optional[str] = Field(None, max_length=10)


# ============= Traveler Profile Schemas =============

class TravelerProfileBase(BaseModel):
    """Base traveler profile schema."""

    traveler_type: str = Field(
        "solo",
        description="Type of traveler: solo, couple, family, group"
    )
    budget_tier: str = Field(
        "mid-range",
        description="Budget preference: budget, mid-range, luxury"
    )
    travel_style: List[str] = Field(
        default_factory=list,
        description="Travel style preferences (e.g., party, cultural, adventure)"
    )
    interests: List[str] = Field(
        default_factory=list,
        description="Travel interests (e.g., food, nightlife, nature)"
    )
    age_range: Optional[str] = Field(
        None,
        description="Age range (e.g., 18-25, 26-35, 36-45, 46-60, 60+)"
    )

    @field_validator("traveler_type")
    @classmethod
    def validate_traveler_type(cls, v: str) -> str:
        allowed = ["solo", "couple", "family", "group"]
        if v not in allowed:
            raise ValueError(f"traveler_type must be one of: {', '.join(allowed)}")
        return v

    @field_validator("budget_tier")
    @classmethod
    def validate_budget_tier(cls, v: str) -> str:
        allowed = ["budget", "mid-range", "luxury"]
        if v not in allowed:
            raise ValueError(f"budget_tier must be one of: {', '.join(allowed)}")
        return v


class TravelerProfileCreate(TravelerProfileBase):
    """Schema for creating a traveler profile."""
    pass


class TravelerProfileUpdate(BaseModel):
    """Schema for updating a traveler profile."""

    traveler_type: Optional[str] = None
    budget_tier: Optional[str] = None
    travel_style: Optional[List[str]] = None
    interests: Optional[List[str]] = None
    age_range: Optional[str] = None

    @field_validator("traveler_type")
    @classmethod
    def validate_traveler_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = ["solo", "couple", "family", "group"]
            if v not in allowed:
                raise ValueError(f"traveler_type must be one of: {', '.join(allowed)}")
        return v

    @field_validator("budget_tier")
    @classmethod
    def validate_budget_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = ["budget", "mid-range", "luxury"]
            if v not in allowed:
                raise ValueError(f"budget_tier must be one of: {', '.join(allowed)}")
        return v


class TravelerProfileResponse(TravelerProfileBase):
    """Response schema for traveler profile."""

    id: UUID
    user_id: UUID

    class Config:
        from_attributes = True


# ============= Combined Schemas =============

class UserWithProfileResponse(UserResponse):
    """User response with embedded traveler profile."""

    traveler_profile: Optional[TravelerProfileResponse] = None

    class Config:
        from_attributes = True


class UserStatsResponse(BaseModel):
    """User statistics response."""

    total_itineraries: int = 0
    total_favorites: int = 0
    total_collections: int = 0
    total_reviews: int = 0
    total_trips: int = 0
    account_age_days: int
