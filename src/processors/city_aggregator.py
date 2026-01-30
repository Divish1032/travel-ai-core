#!/usr/bin/env python3
"""
City Aggregator for Stage 4

Aggregates entity-level data to city-level for Tier 1 destination selection.
This enables multi-day itinerary planning by providing city-level summaries
and metrics that can be searched semantically.

Features:
- Groups entities by city (from location field)
- Computes city-level metrics (entity counts, budget, seasons, vibes)
- Generates city summary text for embedding
- Calculates geographic center for each city
- Handles missing/malformed data gracefully

Architecture Context:
- Input: Stage 3 canonical entities (entity-level)
- Output: City-level aggregations with metrics
- Purpose: Enable Tier 1 city selection for multi-day trips
- Next Step: City embeddings indexed to ChromaDB (city_indexer.py)

Example:
    >>> from src.storage.stage3_storage import Stage3Storage
    >>> from src.storage.s3 import S3Storage
    >>>
    >>> # Load entities
    >>> s3 = S3Storage()
    >>> stage3 = Stage3Storage(s3)
    >>> entities = stage3.load_all_canonical_entities()
    >>>
    >>> # Aggregate to cities
    >>> aggregator = CityAggregator()
    >>> cities = aggregator.aggregate_cities(entities)
    >>>
    >>> # Example city output
    >>> cities[0]
    {
        'city_id': 'bangkok_thailand',
        'city': 'Bangkok',
        'country': 'Thailand',
        'entity_count': 245,
        'entity_types': {'restaurant': 89, 'attraction': 78, 'hotel': 45, ...},
        'budget_distribution': {'budget': 0.4, 'mid-range': 0.5, 'luxury': 0.1},
        'avg_rating': 4.3,
        'best_seasons': ['November', 'December', 'January', 'February'],
        'coordinates': {'lat': 13.7563, 'lon': 100.5018},
        'summary_text': 'Bangkok: vibrant nightlife, street food paradise...',
        'vibes': {...},  # Will be populated in Phase 2
        'recommended_days': '3-5'
    }
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from statistics import mean, median
import re

from src.utils.logging import get_logger
from src.rag.vibe_extractor import VibeExtractor

logger = get_logger(__name__)


class CityAggregator:
    """
    Aggregates entity-level data to city-level summaries.

    Processes canonical entities from Stage 3 and creates city-level
    aggregations suitable for semantic search and destination planning.
    """

    def __init__(self):
        """Initialize city aggregator."""
        # Budget level mappings
        self.budget_levels = {
            '$': 'budget',
            '$$': 'mid-range',
            '$$$': 'luxury',
            '$$$$': 'luxury'
        }

        # Initialize vibe extractor for city-level vibe aggregation (Phase 2)
        self.vibe_extractor = VibeExtractor(use_llm=False)

    def aggregate_cities(
        self,
        entities: List[Dict[str, Any]],
        min_entities_per_city: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Aggregate entities to city level.

        Groups entities by city and computes metrics for each city.
        Cities with fewer than min_entities_per_city are filtered out
        to ensure quality.

        Args:
            entities: List of canonical entities from Stage 3
            min_entities_per_city: Minimum entities required (default: 5)

        Returns:
            List of city aggregations with metrics

        Example:
            >>> aggregator = CityAggregator()
            >>> cities = aggregator.aggregate_cities(entities, min_entities_per_city=10)
            >>> len(cities)
            25
        """
        logger.info(f"🏙️  Aggregating {len(entities)} entities to city level...")

        # Group entities by city
        city_groups = self._group_by_city(entities)

        logger.info(f"Found {len(city_groups)} unique cities")

        # Aggregate each city
        city_aggregations = []
        cities_filtered = 0

        for city_key, city_entities in city_groups.items():
            # Filter out cities with too few entities
            if len(city_entities) < min_entities_per_city:
                cities_filtered += 1
                logger.debug(f"Skipping {city_key}: only {len(city_entities)} entities (min: {min_entities_per_city})")
                continue

            # Aggregate this city
            city_data = self._aggregate_city(city_key, city_entities)
            city_aggregations.append(city_data)

        # Sort by entity count (descending)
        city_aggregations.sort(key=lambda x: x['entity_count'], reverse=True)

        logger.info(f"✅ Created {len(city_aggregations)} city aggregations")
        if cities_filtered > 0:
            logger.info(f"   Filtered out {cities_filtered} cities with < {min_entities_per_city} entities")

        return city_aggregations

    def _group_by_city(
        self,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group entities by city.

        Handles both string and dict location formats.
        Extracts city and country from location field.

        Args:
            entities: List of canonical entities

        Returns:
            Dict mapping city_key (city_country) to list of entities
        """
        city_groups = defaultdict(list)

        for entity in entities:
            location = entity.get('location', 'Unknown')

            # Handle location being string or dict
            if isinstance(location, dict):
                city = location.get('city', 'Unknown')
                country = location.get('country', 'Unknown')
            elif isinstance(location, str):
                # Parse "City, Region, Country" format
                parts = location.split(', ')
                city = parts[0] if len(parts) > 0 else 'Unknown'
                country = parts[-1] if len(parts) > 1 else 'Unknown'
            else:
                city = 'Unknown'
                country = 'Unknown'

            # Skip unknown cities
            if city == 'Unknown':
                continue

            # Create city key: normalized city_country
            city_key = f"{city}_{country}".lower().replace(' ', '_')
            city_key = re.sub(r'[^a-z0-9_]', '', city_key)  # Remove special chars

            # Add entity with city/country metadata
            entity_with_location = entity.copy()
            entity_with_location['_city'] = city
            entity_with_location['_country'] = country

            city_groups[city_key].append(entity_with_location)

        return city_groups

    def _aggregate_city(
        self,
        city_key: str,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aggregate metrics for a single city.

        Computes:
        - Entity counts by type
        - Budget distribution
        - Average rating
        - Best seasons
        - Geographic center
        - City summary text

        Args:
            city_key: Unique city identifier (city_country)
            entities: List of entities in this city

        Returns:
            City aggregation dict with metrics
        """
        # Extract city and country from first entity
        city = entities[0].get('_city', 'Unknown')
        country = entities[0].get('_country', 'Unknown')

        # Entity counts by type
        entity_types = Counter()
        for entity in entities:
            entity_type = entity.get('entity_type', 'unknown')
            entity_types[entity_type] += 1

        # Budget distribution
        budget_dist = self._compute_budget_distribution(entities)

        # Average rating
        avg_rating = self._compute_average_rating(entities)

        # Best seasons (union of all entity best_seasons)
        best_seasons = self._compute_best_seasons(entities)

        # Geographic center
        coordinates = self._compute_geographic_center(entities)

        # Recommended days (heuristic based on entity count)
        recommended_days = self._estimate_recommended_days(len(entities))

        # Summary text for embedding
        summary_text = self._generate_summary_text(
            city=city,
            country=country,
            entity_count=len(entities),
            entity_types=dict(entity_types),
            budget_dist=budget_dist,
            avg_rating=avg_rating,
            best_seasons=best_seasons
        )

        # Vibes aggregation (Phase 2: 12D vibe system)
        vibes = self._aggregate_city_vibes(entities)

        return {
            'city_id': city_key,
            'city': city,
            'country': country,
            'entity_count': len(entities),
            'entity_types': dict(entity_types),
            'budget_distribution': budget_dist,
            'avg_rating': avg_rating,
            'best_seasons': best_seasons,
            'coordinates': coordinates,
            'summary_text': summary_text,
            'vibes': vibes,
            'recommended_days': recommended_days,
            'metadata': {
                'aggregated_at': None,  # Will be set by indexer
                'source_entity_count': len(entities)
            }
        }

    def _compute_budget_distribution(
        self,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Compute budget distribution for a city.

        Extracts price_level from entity attributes and aggregates.

        Args:
            entities: List of entities

        Returns:
            Dict with budget/mid-range/luxury percentages
        """
        budget_counts = Counter()
        total_with_price = 0

        for entity in entities:
            attributes = entity.get('attributes', {})
            price_level = attributes.get('price_level')

            if price_level:
                budget_category = self.budget_levels.get(price_level, 'mid-range')
                budget_counts[budget_category] += 1
                total_with_price += 1

        # Compute percentages
        if total_with_price == 0:
            return {'budget': 0.33, 'mid-range': 0.33, 'luxury': 0.33}

        return {
            'budget': budget_counts.get('budget', 0) / total_with_price,
            'mid-range': budget_counts.get('mid-range', 0) / total_with_price,
            'luxury': budget_counts.get('luxury', 0) / total_with_price
        }

    def _compute_average_rating(
        self,
        entities: List[Dict[str, Any]]
    ) -> Optional[float]:
        """
        Compute average rating across all entities in city.

        Uses enhanced_rating from consensus if available, else avg_rating.

        Args:
            entities: List of entities

        Returns:
            Average rating (0-5) or None if no ratings
        """
        ratings = []

        for entity in entities:
            consensus = entity.get('consensus', {})

            # Try enhanced_rating first (from all_travelers profile)
            all_travelers = consensus.get('all_travelers', {})
            rating = all_travelers.get('enhanced_rating') or all_travelers.get('avg_rating')

            if rating is not None:
                ratings.append(rating)

        if not ratings:
            return None

        return round(mean(ratings), 2)

    def _compute_best_seasons(
        self,
        entities: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Compute best seasons for visiting this city.

        Takes union of all entity temporal_info.best_seasons.
        Returns most common seasons (appearing in >20% of entities).

        Args:
            entities: List of entities

        Returns:
            List of season names (e.g., ['November', 'December', 'January'])
        """
        season_counts = Counter()
        total_with_seasons = 0

        for entity in entities:
            temporal_info = entity.get('temporal_info', {})
            best_seasons = temporal_info.get('best_seasons', [])

            if best_seasons:
                total_with_seasons += 1
                for season in best_seasons:
                    season_counts[season] += 1

        if total_with_seasons == 0:
            return []

        # Include seasons mentioned by at least 20% of entities
        threshold = max(1, int(total_with_seasons * 0.2))
        common_seasons = [
            season for season, count in season_counts.items()
            if count >= threshold
        ]

        # Sort by month order if possible
        month_order = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12
        }

        common_seasons.sort(key=lambda x: month_order.get(x, 99))

        return common_seasons

    def _compute_geographic_center(
        self,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Compute geographic center (centroid) of all entities in city.

        Averages latitude and longitude across all entities with coordinates.

        Args:
            entities: List of entities

        Returns:
            Dict with lat/lon or empty dict if no coordinates
        """
        lats = []
        lons = []

        for entity in entities:
            coordinates = entity.get('coordinates', {})
            lat = coordinates.get('lat')
            lon = coordinates.get('lon')

            if lat is not None and lon is not None:
                lats.append(lat)
                lons.append(lon)

        if not lats:
            return {}

        return {
            'lat': round(mean(lats), 6),
            'lon': round(mean(lons), 6)
        }

    def _estimate_recommended_days(self, entity_count: int) -> str:
        """
        Estimate recommended days for visiting city based on entity count.

        Heuristic:
        - < 20 entities: 1-2 days
        - 20-50 entities: 2-3 days
        - 50-100 entities: 3-4 days
        - 100-200 entities: 4-6 days
        - 200+ entities: 5-7 days

        Args:
            entity_count: Number of entities in city

        Returns:
            String like "3-4" indicating recommended days
        """
        if entity_count < 20:
            return "1-2"
        elif entity_count < 50:
            return "2-3"
        elif entity_count < 100:
            return "3-4"
        elif entity_count < 200:
            return "4-6"
        else:
            return "5-7"

    def _generate_summary_text(
        self,
        city: str,
        country: str,
        entity_count: int,
        entity_types: Dict[str, int],
        budget_dist: Dict[str, float],
        avg_rating: Optional[float],
        best_seasons: List[str]
    ) -> str:
        """
        Generate natural language summary for city embedding.

        Creates a semantic text representation of the city that captures:
        - Location and name
        - What's available (entity types and counts)
        - Budget profile
        - Quality (ratings)
        - When to visit

        This text will be embedded for semantic search.

        Args:
            city: City name
            country: Country name
            entity_count: Total entities
            entity_types: Dict of type -> count
            budget_dist: Dict of budget -> percentage
            avg_rating: Average rating (0-5)
            best_seasons: List of best seasons/months

        Returns:
            Natural language summary text

        Example:
            "Bangkok, Thailand: vibrant destination with 245 places including
            89 restaurants, 78 attractions, 45 hotels. Highly rated (4.3/5).
            Offers mix of budget (40%) and mid-range (50%) options.
            Best visited in November, December, January, February."
        """
        lines = []

        # Header
        lines.append(f"{city}, {country}:")

        # Entity counts
        if entity_count > 100:
            lines.append(f"vibrant destination with {entity_count} places")
        elif entity_count > 50:
            lines.append(f"popular destination with {entity_count} places")
        else:
            lines.append(f"destination with {entity_count} places")

        # Top entity types
        top_types = sorted(entity_types.items(), key=lambda x: x[1], reverse=True)[:3]
        type_str = ", ".join([f"{count} {etype}s" for etype, count in top_types])
        lines.append(f"including {type_str}.")

        # Rating
        if avg_rating:
            if avg_rating >= 4.5:
                lines.append(f"Exceptionally rated ({avg_rating}/5).")
            elif avg_rating >= 4.0:
                lines.append(f"Highly rated ({avg_rating}/5).")
            elif avg_rating >= 3.5:
                lines.append(f"Well rated ({avg_rating}/5).")

        # Budget profile
        dominant_budget = max(budget_dist.items(), key=lambda x: x[1])
        if dominant_budget[1] > 0.5:
            lines.append(f"Primarily {dominant_budget[0]} options.")
        else:
            # Mixed budget
            budget_parts = []
            for budget, pct in sorted(budget_dist.items(), key=lambda x: x[1], reverse=True):
                if pct > 0.2:
                    budget_parts.append(f"{budget} ({int(pct*100)}%)")
            if budget_parts:
                lines.append(f"Offers mix of {' and '.join(budget_parts[:2])} options.")

        # Best seasons
        if best_seasons:
            if len(best_seasons) <= 3:
                season_str = ", ".join(best_seasons)
            else:
                season_str = ", ".join(best_seasons[:4])
            lines.append(f"Best visited in {season_str}.")

        return " ".join(lines)

    def _aggregate_city_vibes(
        self,
        entities: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Aggregate 12D vibe vector for city from entity vibes.

        Averages vibe scores across all entities in the city to create
        a city-level vibe profile.

        Args:
            entities: List of entities in this city

        Returns:
            Dict with 12 vibe dimensions (0-1 scale)

        Example:
            >>> vibes = aggregator._aggregate_city_vibes(entities)
            >>> vibes
            {'nightlife': 0.7, 'food': 0.85, 'culture': 0.6, ...}
        """
        # Extract vibes from each entity
        entity_vibes_list = []

        for entity in entities:
            try:
                entity_vibes = self.vibe_extractor.extract_entity_vibes(entity, use_experiences=False)
                entity_vibes_list.append(entity_vibes)
            except Exception as e:
                logger.debug(f"Failed to extract vibes for entity {entity.get('entity_id')}: {e}")
                continue

        if not entity_vibes_list:
            # Return neutral vibes if extraction failed for all entities
            logger.warning("No entity vibes extracted, returning neutral vibes")
            return {dim: 0.0 for dim in self.vibe_extractor.VIBE_DIMENSIONS}

        # Average across all entities
        city_vibes = {}
        for dim in self.vibe_extractor.VIBE_DIMENSIONS:
            scores = [vibes.get(dim, 0.0) for vibes in entity_vibes_list]
            city_vibes[dim] = round(mean(scores), 3) if scores else 0.0

        return city_vibes
