"""
Search router.

Provides semantic search capabilities over canonical travel entities.
"""

import time
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    AdvancedSearchRequest,
    SuggestionResponse,
)
from app.services.place_service import get_place_service, PlaceService
from app.dependencies import get_current_user_optional
from app.models.user import User


router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    city: Optional[str] = Query(None, description="Filter by city"),
    country: Optional[str] = Query(None, description="Filter by country"),
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Semantic search for places using natural language.

    Uses vector embeddings to find places matching the search query semantically,
    not just keyword matching. Supports filtering by location and type.

    Authentication optional - personalized if authenticated.

    Examples:
        - "romantic restaurants with rooftop views"
        - "budget hotels near beach"
        - "family-friendly activities"
        - "best street food"

    Query params:
        q: Search query text
        limit: Number of results (default 10, max 100)
        entity_type: Filter by type (restaurant, hotel, etc.)
        city: Filter by city
        country: Filter by country

    Returns:
        Search results with relevance scores
    """
    start_time = time.time()

    # Build filters
    filters = {}
    if entity_type:
        filters["entity_type"] = entity_type
    if city:
        filters["city"] = city
    if country:
        filters["country"] = country

    # Perform semantic search
    places_with_scores = place_service.search_places(
        query=q,
        filters=filters if filters else None,
        top_k=limit
    )

    # Convert to search results
    search_results = [
        SearchResult(
            place=place,
            relevance_score=score
        )
        for place, score in places_with_scores
    ]

    search_time_ms = (time.time() - start_time) * 1000

    return SearchResponse(
        query=q,
        results=search_results,
        total_results=len(search_results),
        search_time_ms=search_time_ms
    )


@router.post("/advanced", response_model=SearchResponse)
async def advanced_search(
    request: AdvancedSearchRequest,
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Advanced semantic search with filters and reranking.

    Provides more control over search with:
    - Multiple filter criteria
    - Optional LLM reranking for better relevance
    - Configurable retrieval parameters

    Authentication optional - personalized if authenticated.

    Args:
        request: Advanced search parameters with filters

    Returns:
        Search results with relevance scores
    """
    start_time = time.time()

    # Build filters from request
    filters = {}
    if request.filters:
        if request.filters.entity_type:
            filters["entity_type"] = request.filters.entity_type
        if request.filters.city:
            filters["city"] = request.filters.city
        if request.filters.country:
            filters["country"] = request.filters.country
        if request.filters.min_mentions:
            filters["total_mentions"] = {"$gte": request.filters.min_mentions}

    # Perform search with top_k for initial retrieval
    places_with_scores = place_service.search_places(
        query=request.query,
        filters=filters if filters else None,
        top_k=request.top_k
    )

    # TODO: Implement LLM reranking if request.rerank is True
    # For now, just use vector search results

    # Apply final limit
    places_with_scores = places_with_scores[:request.limit]

    # Convert to search results
    search_results = [
        SearchResult(
            place=place,
            relevance_score=score,
            match_reason=None  # TODO: Add reasoning from reranking
        )
        for place, score in places_with_scores
    ]

    search_time_ms = (time.time() - start_time) * 1000

    return SearchResponse(
        query=request.query,
        results=search_results,
        total_results=len(search_results),
        search_time_ms=search_time_ms
    )


@router.get("/suggestions", response_model=SuggestionResponse)
async def get_suggestions(
    q: str = Query("", description="Partial query for autocomplete"),
    limit: int = Query(5, ge=1, le=20, description="Number of suggestions"),
    user: User = Depends(get_current_user_optional)
):
    """
    Get autocomplete suggestions for search.

    Returns suggested search queries and popular destinations
    based on partial input.

    Authentication optional.

    Query params:
        q: Partial search query
        limit: Number of suggestions

    Returns:
        List of suggestions
    """
    # TODO: Implement actual autocomplete logic
    # For now, return some popular suggestions

    popular_destinations = [
        "Bangkok",
        "Tokyo",
        "Paris",
        "New York",
        "Barcelona",
        "Rome",
        "Dubai",
        "London",
        "Singapore",
        "Istanbul"
    ]

    suggestions = []
    if q:
        # Simple prefix matching for demo
        suggestions = [dest for dest in popular_destinations if q.lower() in dest.lower()][:limit]
    else:
        suggestions = popular_destinations[:limit]

    return SuggestionResponse(
        suggestions=suggestions,
        popular_destinations=popular_destinations[:limit]
    )
