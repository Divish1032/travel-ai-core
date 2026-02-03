#!/usr/bin/env python3
"""
City Selector for Multi-Day Itinerary Planning

Implements Tier 1 city selection for multi-day trips using semantic search
on city embeddings. Enables intelligent city allocation and routing.

Features:
- Semantic search on city_destinations collection
- Smart city allocation based on trip duration
- Geographic optimization (minimize inter-city travel)
- Budget-aware filtering
- Seasonal filtering (best months to visit)
- Fallback strategies for insufficient data

Architecture Context:
- Input: Query parameters (days, vibes, budget, country, dates)
- Process: Query city_destinations, allocate days, optimize routing
- Output: City plan with day allocation
- Next Step: Entity retrieval per city (Tier 2 in retriever.py)

Example:
    >>> from src.vectordb import ChromaDBClient
    >>> from src.utils.embedding_client import EmbeddingClient
    >>>
    >>> chromadb = ChromaDBClient.initialize_from_env()
    >>> embedding_client = EmbeddingClient()
    >>> selector = CitySelector(chromadb, embedding_client)
    >>>
    >>> # Select cities for multi-day trip
    >>> plan = selector.select_cities(
    ...     query="nightlife and food",
    ...     total_days=10,
    ...     country="Thailand",
    ...     budget="mid-range"
    ... )
    >>> plan
    {
        'cities': [
            {'city': 'Bangkok', 'days': 4, 'priority': 1},
            {'city': 'Phuket', 'days': 4, 'priority': 2},
            {'city': 'Chiang Mai', 'days': 2, 'priority': 3}
        ],
        'travel_days': 2,  # Reserved for inter-city travel
        'total_days': 10
    }
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CityCandidate:
    """City candidate with relevance score."""
    city_id: str
    city: str
    country: str
    distance: float  # Semantic distance (lower = better match)
    entity_count: int
    avg_rating: float
    recommended_days: str  # e.g., "3-4"
    metadata: Dict[str, Any]


@dataclass
class CityPlan:
    """City allocation plan for multi-day trip."""
    cities: List[Dict[str, Any]]  # [{city, days, priority}, ...]
    travel_days: int
    total_days: int
    total_cities: int


class CitySelector:
    """
    Selects cities for multi-day itineraries using Tier 1 semantic search.

    Queries city_destinations collection and implements smart allocation
    algorithms to distribute days across cities.
    """

    def __init__(self, chromadb_client, embedding_client):
        """
        Initialize city selector.

        Args:
            chromadb_client: ChromaDBClient instance with city_destinations collection
            embedding_client: EmbeddingClient instance for query embedding
        """
        self.chromadb = chromadb_client
        self.embedding_client = embedding_client

        # Check if city_destinations collection exists
        if not hasattr(chromadb_client, 'city_destinations_collection'):
            raise RuntimeError("city_destinations collection not found in ChromaDB client")

        self.collection = chromadb_client.city_destinations_collection

    def select_cities(
        self,
        query: str,
        total_days: int,
        country: Optional[str] = None,
        budget: Optional[str] = None,
        max_cities: int = 4,
        min_days_per_city: int = 2
    ) -> CityPlan:
        """
        Select cities for multi-day trip using semantic search.

        Process:
        1. Build semantic query from user input
        2. Query city_destinations with filters
        3. Rank cities by relevance and quality
        4. Allocate days across top cities
        5. Reserve travel days for inter-city transit

        Args:
            query: Natural language query (e.g., "nightlife and food")
            total_days: Total trip duration in days
            country: Optional country filter
            budget: Optional budget filter (budget, mid-range, luxury)
            max_cities: Maximum cities to include (default: 4)
            min_days_per_city: Minimum days per city (default: 2)

        Returns:
            CityPlan with city allocations

        Example:
            >>> plan = selector.select_cities(
            ...     query="adventure and culture",
            ...     total_days=7,
            ...     country="Thailand",
            ...     budget="mid-range"
            ... )
            >>> len(plan.cities)
            2
        """
        logger.info(f"🏙️  Selecting cities for {total_days}-day trip...")
        logger.info(f"   Query: '{query}'")
        if country:
            logger.info(f"   Country: {country}")
        if budget:
            logger.info(f"   Budget: {budget}")

        # Step 1: Retrieve top city candidates
        candidates = self._retrieve_cities(
            query=query,
            country=country,
            budget=budget,
            top_k=10
        )

        if not candidates:
            logger.warning("⚠️  No cities found matching criteria")
            return self._empty_plan(total_days)

        logger.info(f"   Found {len(candidates)} candidate cities")

        # Step 2: Allocate days across cities
        plan = self._allocate_days(
            candidates=candidates,
            total_days=total_days,
            max_cities=max_cities,
            min_days_per_city=min_days_per_city
        )

        logger.info(f"✅ Selected {plan.total_cities} cities:")
        for city_data in plan.cities:
            logger.info(f"   - {city_data['city']}: {city_data['days']} days (priority {city_data['priority']})")
        if plan.travel_days > 0:
            logger.info(f"   - Travel: {plan.travel_days} days")

        return plan

    def _retrieve_cities(
        self,
        query: str,
        country: Optional[str] = None,
        budget: Optional[str] = None,
        top_k: int = 10
    ) -> List[CityCandidate]:
        """
        Retrieve top city candidates using semantic search.

        Args:
            query: Natural language query
            country: Optional country filter
            budget: Optional budget filter
            top_k: Number of top cities to retrieve

        Returns:
            List of CityCandidate objects
        """
        # Build where filter for metadata
        where_filter = {}

        if country:
            where_filter['country'] = country

        if budget:
            # Filter by dominant_budget
            where_filter['dominant_budget'] = budget

        # Query collection
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if where_filter else None
            )

            # Convert to CityCandidate objects
            candidates = []

            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]

                # Parse recommended_days (e.g., "3-4" -> (3, 4))
                rec_days_str = metadata.get('recommended_days', '2-3')

                candidate = CityCandidate(
                    city_id=results['ids'][0][i],
                    city=metadata.get('city', 'Unknown'),
                    country=metadata.get('country', 'Unknown'),
                    distance=results['distances'][0][i] if 'distances' in results else 0.0,
                    entity_count=metadata.get('entity_count', 0),
                    avg_rating=metadata.get('avg_rating', 0.0),
                    recommended_days=rec_days_str,
                    metadata=metadata
                )

                candidates.append(candidate)

            return candidates

        except Exception as e:
            logger.error(f"❌ Failed to retrieve cities: {e}")
            return []

    def _allocate_days(
        self,
        candidates: List[CityCandidate],
        total_days: int,
        max_cities: int = 4,
        min_days_per_city: int = 2
    ) -> CityPlan:
        """
        Allocate days across top city candidates.

        Strategy:
        1. Reserve travel days (1 day per city transition)
        2. Allocate remaining days based on:
           - Semantic relevance (distance score)
           - Entity count (more to see)
           - Recommended days (heuristic)
        3. Ensure min_days_per_city constraint
        4. Cap at max_cities

        Args:
            candidates: List of city candidates (sorted by relevance)
            total_days: Total trip duration
            max_cities: Maximum cities to include
            min_days_per_city: Minimum days per city

        Returns:
            CityPlan with allocations
        """
        # Edge case: very short trip
        if total_days < min_days_per_city:
            # Single city, all days
            return CityPlan(
                cities=[{
                    'city': candidates[0].city,
                    'city_id': candidates[0].city_id,
                    'days': total_days,
                    'priority': 1
                }],
                travel_days=0,
                total_days=total_days,
                total_cities=1
            )

        # Determine optimal number of cities
        # Heuristic: 1 city per 3 days (roughly)
        ideal_cities = max(1, min(max_cities, total_days // 3))

        # Reserve travel days (1 day per transition)
        travel_days = max(0, ideal_cities - 1)
        available_days = total_days - travel_days

        # Ensure we can meet min_days_per_city constraint
        max_feasible_cities = available_days // min_days_per_city
        num_cities = min(ideal_cities, max_feasible_cities, len(candidates))

        if num_cities == 0:
            # Can't fit any city with min_days constraint
            logger.warning(f"⚠️  Can't fit {min_days_per_city} days/city in {total_days} days")
            num_cities = 1
            travel_days = 0
            available_days = total_days

        # Select top N cities
        selected_cities = candidates[:num_cities]

        # Allocate days proportionally to:
        # - Semantic relevance (inverse of distance)
        # - Entity count
        # - Recommended days
        weights = []
        for city in selected_cities:
            # Relevance score (inverse distance, normalized)
            relevance = 1.0 / (1.0 + city.distance)

            # Entity count score (normalized)
            entity_score = min(1.0, city.entity_count / 100.0)

            # Recommended days score
            rec_days_parts = city.recommended_days.split('-')
            rec_days_avg = (int(rec_days_parts[0]) + int(rec_days_parts[-1])) / 2
            rec_days_score = min(1.0, rec_days_avg / 5.0)

            # Weighted combination
            weight = (
                0.5 * relevance +
                0.3 * entity_score +
                0.2 * rec_days_score
            )
            weights.append(weight)

        # Normalize weights
        total_weight = sum(weights)
        if total_weight == 0:
            # Fallback: equal weights
            weights = [1.0] * num_cities
            total_weight = num_cities

        # Allocate days proportionally
        allocations = []
        allocated_total = 0

        for i, (city, weight) in enumerate(zip(selected_cities, weights)):
            # Proportional allocation
            if i == num_cities - 1:
                # Last city gets remaining days
                days = available_days - allocated_total
            else:
                days = int(round((weight / total_weight) * available_days))

            # Ensure minimum
            days = max(min_days_per_city, days)

            allocations.append({
                'city': city.city,
                'city_id': city.city_id,
                'days': days,
                'priority': i + 1
            })

            allocated_total += days

        # Adjust if over-allocated (due to rounding + minimums)
        if allocated_total > available_days:
            excess = allocated_total - available_days

            # Remove excess from lower-priority cities
            for i in range(len(allocations) - 1, -1, -1):
                if allocations[i]['days'] > min_days_per_city:
                    reduction = min(excess, allocations[i]['days'] - min_days_per_city)
                    allocations[i]['days'] -= reduction
                    excess -= reduction

                    if excess == 0:
                        break

        return CityPlan(
            cities=allocations,
            travel_days=travel_days,
            total_days=total_days,
            total_cities=len(allocations)
        )

    def _empty_plan(self, total_days: int) -> CityPlan:
        """
        Return empty plan when no cities found.

        Args:
            total_days: Total trip duration

        Returns:
            Empty CityPlan
        """
        return CityPlan(
            cities=[],
            travel_days=0,
            total_days=total_days,
            total_cities=0
        )
