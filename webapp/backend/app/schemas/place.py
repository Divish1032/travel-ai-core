"""
Pydantic schemas for places endpoints.

Request and response models for browsing and searching canonical entities.
"""

from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    """Geographic coordinates."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class PlaceLocation(BaseModel):
    """Place location information."""

    country: str
    city: str
    area: Optional[str] = None
    coordinates: Optional[Coordinates] = None


class ConsensusData(BaseModel):
    """Consensus information from multiple mentions."""

    mention_count: int = Field(..., ge=0)
    sentiment_positive: int = Field(0, ge=0, description="Positive sentiment count")
    sentiment_neutral: int = Field(0, ge=0, description="Neutral sentiment count")
    sentiment_negative: int = Field(0, ge=0, description="Negative sentiment count")
    avg_cost: Optional[str] = None
    avg_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    common_themes: List[str] = Field(default_factory=list)
    common_tips: List[str] = Field(default_factory=list)
    common_warnings: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


class PlaceResponse(BaseModel):
    """Detailed place/entity response."""

    entity_id: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    entity_type: Literal[
        "destination",
        "restaurant",
        "hotel",
        "activity",
        "attraction",
        "transportation",
        "shopping",
        "unknown"
    ]
    location: PlaceLocation
    attributes: Dict[str, Any] = Field(default_factory=dict)
    consensus: ConsensusData
    total_mentions: int
    best_for: List[str] = Field(default_factory=list, description="Traveler profiles this is best for")
    not_recommended_for: List[str] = Field(default_factory=list)
    confidence_score: float = Field(..., ge=0.0, le=1.0)

    model_config = {"from_attributes": True}


class PlaceSummaryResponse(BaseModel):
    """Lightweight place summary for list views."""

    entity_id: str
    canonical_name: str
    entity_type: str
    location: PlaceLocation
    total_mentions: int
    avg_rating: Optional[float] = None
    avg_cost: Optional[str] = None
    best_for: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PlaceListResponse(BaseModel):
    """Paginated list of places."""

    items: List[PlaceSummaryResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PlaceFilters(BaseModel):
    """Filters for browsing places."""

    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    city: Optional[str] = Field(None, description="Filter by city")
    country: Optional[str] = Field(None, description="Filter by country")
    budget_tier: Optional[str] = Field(None, description="Filter by budget (budget/mid-range/luxury)")
    traveler_type: Optional[str] = Field(None, description="Filter by traveler type (solo/couple/family/group)")
    min_mentions: Optional[int] = Field(None, ge=1, description="Minimum number of mentions")
    min_rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Minimum average rating")


class NearbyPlacesRequest(BaseModel):
    """Request for finding nearby places."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(10.0, gt=0, le=100, description="Search radius in kilometers")
    entity_type: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)
