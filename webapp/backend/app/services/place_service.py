"""
Place service for managing canonical entities.

Wraps the TravelAI SemanticSearchAPI to provide place browsing,
search, and recommendation functionality for the API.
"""

import math
from typing import List, Optional, Dict, Any, Tuple
from src.vectordb.search_api import SemanticSearchAPI, SearchResult as VectorSearchResult
from src.utils.schemas import CanonicalEntity
from pydantic import ValidationError

from app.schemas.place import (
    PlaceResponse,
    PlaceSummaryResponse,
    PlaceLocation,
    Coordinates,
    ConsensusData,
)


class PlaceService:
    """
    Service layer for place/entity operations.

    Wraps the TravelAI SemanticSearchAPI and provides methods
    for browsing, searching, and filtering canonical entities.
    """

    def __init__(self, search_api: Optional[SemanticSearchAPI] = None):
        """
        Initialize place service.

        Args:
            search_api: SemanticSearchAPI instance (auto-initializes if None)
        """
        if search_api is None:
            self.search_api = SemanticSearchAPI()
        else:
            self.search_api = search_api

    def _convert_to_place_response(self, entity_data: Dict[str, Any]) -> PlaceResponse:
        """Convert canonical entity dict to PlaceResponse."""
        # Extract location
        loc = entity_data.get("location", {})
        coords_data = loc.get("coordinates")
        coordinates = None
        if coords_data:
            coordinates = Coordinates(
                latitude=coords_data.get("latitude", 0.0),
                longitude=coords_data.get("longitude", 0.0),
                confidence=coords_data.get("confidence")
            )

        location = PlaceLocation(
            country=loc.get("country", "Unknown"),
            city=loc.get("city", "Unknown"),
            area=loc.get("area"),
            coordinates=coordinates
        )

        # Extract consensus
        consensus_raw = entity_data.get("consensus", {}).get("all_travelers", {})
        sentiment_dist = consensus_raw.get("sentiment_distribution", {})

        consensus = ConsensusData(
            mention_count=consensus_raw.get("mention_count", 0),
            sentiment_positive=sentiment_dist.get("positive", 0),
            sentiment_neutral=sentiment_dist.get("neutral", 0),
            sentiment_negative=sentiment_dist.get("negative", 0),
            avg_cost=consensus_raw.get("avg_cost"),
            avg_rating=consensus_raw.get("avg_rating"),
            common_themes=consensus_raw.get("common_themes", []),
            common_tips=consensus_raw.get("common_tips", []),
            common_warnings=consensus_raw.get("common_warnings", []),
            confidence=consensus_raw.get("confidence", 0.0)
        )

        return PlaceResponse(
            entity_id=entity_data["entity_id"],
            canonical_name=entity_data["canonical_name"],
            aliases=entity_data.get("aliases", []),
            entity_type=entity_data["entity_type"],
            location=location,
            attributes=entity_data.get("attributes", {}),
            consensus=consensus,
            total_mentions=entity_data.get("total_mentions", 0),
            best_for=entity_data.get("best_for", []),
            not_recommended_for=entity_data.get("not_recommended_for", []),
            confidence_score=entity_data.get("confidence_score", 0.0)
        )

    def _convert_to_place_summary(self, entity_data: Dict[str, Any]) -> PlaceSummaryResponse:
        """Convert canonical entity dict to PlaceSummaryResponse (lightweight)."""
        loc = entity_data.get("location", {})
        coords_data = loc.get("coordinates")
        coordinates = None
        if coords_data:
            coordinates = Coordinates(
                latitude=coords_data.get("latitude", 0.0),
                longitude=coords_data.get("longitude", 0.0),
                confidence=coords_data.get("confidence")
            )

        location = PlaceLocation(
            country=loc.get("country", "Unknown"),
            city=loc.get("city", "Unknown"),
            area=loc.get("area"),
            coordinates=coordinates
        )

        consensus_raw = entity_data.get("consensus", {}).get("all_travelers", {})

        return PlaceSummaryResponse(
            entity_id=entity_data["entity_id"],
            canonical_name=entity_data["canonical_name"],
            entity_type=entity_data["entity_type"],
            location=location,
            total_mentions=entity_data.get("total_mentions", 0),
            avg_rating=consensus_raw.get("avg_rating"),
            avg_cost=consensus_raw.get("avg_cost"),
            best_for=entity_data.get("best_for", [])
        )

    def get_place_by_id(self, entity_id: str) -> Optional[PlaceResponse]:
        """
        Get a single place by entity ID.

        Args:
            entity_id: Canonical entity ID

        Returns:
            PlaceResponse if found, None otherwise
        """
        # Use search with entity_id filter
        results = self.search_api.search_entities(
            query_text=entity_id,  # Query doesn't matter much here
            top_k=1,
            filters={"entity_id": entity_id}
        )

        if not results:
            return None

        # Get full entity data from first result
        entity_data = results[0].entity_data
        if not entity_data:
            return None

        return self._convert_to_place_response(entity_data)

    def browse_places(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Tuple[List[PlaceSummaryResponse], int]:
        """
        Browse places with filtering and pagination.

        Args:
            filters: Metadata filters (entity_type, city, country, etc.)
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Tuple of (list of places, total count)
        """
        # Calculate top_k for pagination
        # Note: This is a simplification - ideally we'd query the DB for count
        top_k = page * per_page

        # Dummy query to get all results (semantic search requires query text)
        # Using a generic query
        results = self.search_api.search_entities(
            query_text="travel",
            top_k=top_k,
            filters=filters or {}
        )

        # Calculate pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        paginated_results = results[start_idx:end_idx]

        # Convert to place summaries
        places = []
        for result in paginated_results:
            if result.entity_data:
                try:
                    place = self._convert_to_place_summary(result.entity_data)
                    places.append(place)
                except (KeyError, ValidationError) as e:
                    # Skip malformed entities
                    continue

        return places, len(results)

    def search_places(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 20
    ) -> List[Tuple[PlaceResponse, float]]:
        """
        Semantic search for places.

        Args:
            query: Natural language search query
            filters: Metadata filters
            top_k: Number of results

        Returns:
            List of (PlaceResponse, relevance_score) tuples
        """
        results = self.search_api.search_entities(
            query_text=query,
            top_k=top_k,
            filters=filters or {}
        )

        places_with_scores = []
        for result in results:
            if result.entity_data:
                try:
                    place = self._convert_to_place_response(result.entity_data)
                    # Convert distance to relevance score (0-1)
                    relevance = result.relevance_score / 100.0
                    places_with_scores.append((place, relevance))
                except (KeyError, ValidationError) as e:
                    continue

        return places_with_scores

    def find_nearby_places(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 10.0,
        entity_type: Optional[str] = None,
        limit: int = 20
    ) -> List[PlaceResponse]:
        """
        Find places near coordinates.

        Note: This is a simplified implementation. For production,
        you'd want to use geospatial indexing.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            radius_km: Search radius in kilometers
            entity_type: Optional entity type filter
            limit: Max results

        Returns:
            List of nearby places
        """
        # Build filters
        filters = {}
        if entity_type:
            filters["entity_type"] = entity_type

        # Get places (using generic search for now)
        # TODO: Implement proper geospatial search with haversine distance
        results = self.search_api.search_entities(
            query_text="nearby places",
            top_k=limit * 2,  # Get more to filter by distance
            filters=filters
        )

        nearby_places = []
        for result in results:
            if result.entity_data:
                try:
                    place = self._convert_to_place_response(result.entity_data)

                    # Check if place has coordinates
                    if place.location.coordinates:
                        # Calculate distance (simplified - not actual haversine)
                        # In production, use proper geospatial calculation
                        lat_diff = abs(place.location.coordinates.latitude - latitude)
                        lon_diff = abs(place.location.coordinates.longitude - longitude)

                        # Rough approximation: 1 degree ≈ 111km
                        distance_km = ((lat_diff ** 2 + lon_diff ** 2) ** 0.5) * 111

                        if distance_km <= radius_km:
                            nearby_places.append(place)

                            if len(nearby_places) >= limit:
                                break
                except (KeyError, ValidationError) as e:
                    continue

        return nearby_places


# Global instance (initialized lazily)
_place_service: Optional[PlaceService] = None


def get_place_service() -> PlaceService:
    """Get or create global PlaceService instance."""
    global _place_service
    if _place_service is None:
        _place_service = PlaceService()
    return _place_service
