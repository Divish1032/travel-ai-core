"""
Pydantic schemas for search endpoints.

Request and response models for semantic search and advanced filtering.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.schemas.place import PlaceResponse


class SearchRequest(BaseModel):
    """Basic search request."""

    query: str = Field(..., min_length=1, description="Search query text")
    limit: int = Field(10, ge=1, le=100, description="Number of results to return")


class SearchFilters(BaseModel):
    """Advanced search filters."""

    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    city: Optional[str] = Field(None, description="Filter by city")
    country: Optional[str] = Field(None, description="Filter by country")
    budget_tier: Optional[str] = Field(None, description="Filter by budget tier")
    traveler_type: Optional[str] = Field(None, description="Filter by traveler type")
    min_mentions: Optional[int] = Field(None, ge=1, description="Minimum mentions")
    min_rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Minimum rating")


class AdvancedSearchRequest(BaseModel):
    """Advanced search with filters and reranking."""

    query: str = Field(..., min_length=1, description="Search query")
    filters: Optional[SearchFilters] = Field(None, description="Search filters")
    rerank: bool = Field(False, description="Enable LLM reranking for better relevance")
    top_k: int = Field(20, ge=1, le=100, description="Initial retrieval count before reranking")
    limit: int = Field(10, ge=1, le=50, description="Final number of results")


class SearchResult(BaseModel):
    """Single search result with relevance score."""

    place: PlaceResponse
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Semantic similarity score")
    match_reason: Optional[str] = Field(None, description="Why this result matched (for advanced search)")


class SearchResponse(BaseModel):
    """Search results response."""

    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: Optional[float] = None


class SuggestionResponse(BaseModel):
    """Autocomplete suggestion response."""

    suggestions: List[str] = Field(..., description="List of autocomplete suggestions")
    popular_destinations: List[str] = Field(default_factory=list, description="Popular destination suggestions")


class SearchStats(BaseModel):
    """Search statistics and metadata."""

    total_entities: int = Field(..., description="Total entities in database")
    entities_by_type: Dict[str, int] = Field(default_factory=dict, description="Count by entity type")
    cities_available: List[str] = Field(default_factory=list, description="Available cities")
    countries_available: List[str] = Field(default_factory=list, description="Available countries")
