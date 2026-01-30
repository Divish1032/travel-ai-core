"""
Places router.

Provides endpoints for browsing and discovering canonical travel entities (places).
"""

import math
from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import Optional

from app.schemas.place import (
    PlaceResponse,
    PlaceListResponse,
    NearbyPlacesRequest,
)
from app.services.place_service import get_place_service, PlaceService
from app.dependencies import get_current_user_optional
from app.models.user import User


router = APIRouter(prefix="/places", tags=["Places"])


@router.get("", response_model=PlaceListResponse)
async def browse_places(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    city: Optional[str] = Query(None, description="Filter by city"),
    country: Optional[str] = Query(None, description="Filter by country"),
    budget_tier: Optional[str] = Query(None, description="Filter by budget (budget/mid-range/luxury)"),
    traveler_type: Optional[str] = Query(None, description="Filter by traveler type"),
    min_mentions: Optional[int] = Query(None, ge=1, description="Minimum mentions"),
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Browse places with filtering and pagination.

    Returns a list of canonical travel entities (restaurants, attractions, hotels, etc.)
    from the TravelAI database with optional filtering.

    Authentication optional - results personalized if authenticated.

    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 20, max 100)
        entity_type: Filter by type (restaurant, hotel, attraction, etc.)
        city: Filter by city name
        country: Filter by country name
        budget_tier: Filter by budget tier (budget, mid-range, luxury)
        traveler_type: Filter by traveler type (solo, couple, family, group)
        min_mentions: Minimum number of video mentions

    Returns:
        Paginated list of places
    """
    # Build filters
    filters = {}
    if entity_type:
        filters["entity_type"] = entity_type
    if city:
        filters["city"] = city
    if country:
        filters["country"] = country
    if min_mentions:
        filters["total_mentions"] = {"$gte": min_mentions}

    # TODO: Implement budget_tier and traveler_type filtering
    # These would require querying the consensus data

    # Get places
    places, total = place_service.browse_places(
        filters=filters if filters else None,
        page=page,
        per_page=per_page
    )

    return PlaceListResponse(
        items=places,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total > 0 else 0
    )


@router.get("/{entity_id}", response_model=PlaceResponse)
async def get_place(
    entity_id: str,
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Get detailed information about a specific place.

    Returns full details including location, consensus data from multiple mentions,
    common themes, tips, warnings, and traveler profiles it's best for.

    Authentication optional.

    Args:
        entity_id: Canonical entity ID

    Returns:
        Full place details

    Raises:
        404: Place not found
    """
    place = place_service.get_place_by_id(entity_id)

    if not place:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Place with ID '{entity_id}' not found"
        )

    return place


@router.post("/nearby", response_model=PlaceListResponse)
async def find_nearby_places(
    request: NearbyPlacesRequest,
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Find places near geographic coordinates.

    Uses geospatial search to find places within a specified radius.

    Authentication optional.

    Args:
        request: Coordinates, radius, and filters

    Returns:
        List of nearby places
    """
    places = place_service.find_nearby_places(
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        entity_type=request.entity_type,
        limit=request.limit
    )

    return PlaceListResponse(
        items=[place for place in places],  # Convert to summaries if needed
        total=len(places),
        page=1,
        per_page=request.limit,
        pages=1
    )


@router.get("/trending", response_model=PlaceListResponse)
async def get_trending_places(
    city: Optional[str] = Query(None, description="Filter by city"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    user: User = Depends(get_current_user_optional),
    place_service: PlaceService = Depends(get_place_service)
):
    """
    Get trending/popular places.

    Returns places sorted by popularity (mention count and ratings).

    Authentication optional - personalized if authenticated.

    Query params:
        city: Optional city filter
        entity_type: Optional entity type filter
        limit: Number of results

    Returns:
        List of trending places
    """
    # Build filters
    filters = {}
    if city:
        filters["city"] = city
    if entity_type:
        filters["entity_type"] = entity_type

    # Use search to get places, then sort by mentions
    # (Simplified implementation - in production, would use dedicated trending algorithm)
    results = place_service.search_places(
        query="popular trending places",
        filters=filters if filters else None,
        top_k=limit
    )

    # Extract places and sort by mention count
    places = [place for place, score in results]
    places_sorted = sorted(places, key=lambda p: p.total_mentions, reverse=True)[:limit]

    # Convert to summaries for list response
    from app.schemas.place import PlaceSummaryResponse
    summaries = [
        PlaceSummaryResponse(
            entity_id=p.entity_id,
            canonical_name=p.canonical_name,
            entity_type=p.entity_type,
            location=p.location,
            total_mentions=p.total_mentions,
            avg_rating=p.consensus.avg_rating,
            avg_cost=p.consensus.avg_cost,
            best_for=p.best_for
        )
        for p in places_sorted
    ]

    return PlaceListResponse(
        items=summaries,
        total=len(summaries),
        page=1,
        per_page=limit,
        pages=1
    )
