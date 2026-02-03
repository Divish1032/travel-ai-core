#!/usr/bin/env python3
"""
Geolocation Module - FREE geocoding using Nominatim (OpenStreetMap)

Provides functions to geocode travel entities (attractions, destinations, etc.)
using the free Nominatim API from OpenStreetMap.

Features:
    - Single entity geocoding with rate limiting
    - Fallback query strategies for better match rates
    - Coordinate validation for Thailand
    - Batch processing with local JSON caching
    - Comprehensive error handling and logging

Usage:
    from src.processors.geolocation import batch_geocode_nominatim

    results = batch_geocode_nominatim(entities, cache_file='geocode_cache.json')

Rate Limits:
    Nominatim has a strict 1 request/second limit.
    This module enforces sleep(1) between all requests.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError, GeocoderUnavailable

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def is_missing_or_unknown(value: Optional[str]) -> bool:
    """Check if a value is missing or 'unknown' (case-insensitive)."""
    return not value or (isinstance(value, str) and value.lower() == 'unknown')


# =============================================================================
# Geographic Configuration (Global Scalability)
# =============================================================================

# Default country for geocoding (can be overridden per request)
# Set to None for fully global geocoding
DEFAULT_COUNTRY = "Thailand"  # Previously: 'Thailand'

# Geographic bounds for different regions (used for validation)
# Key: country/region name (lowercase), Value: bounds dict
REGION_BOUNDS = {
    'thailand': {
        'min_lat': 5.0,
        'max_lat': 21.0,
        'min_lon': 97.0,
        'max_lon': 106.0
    },
    'global': {
        'min_lat': -90.0,
        'max_lat': 90.0,
        'min_lon': -180.0,
        'max_lon': 180.0
    }
}

# City coordinate cache for validation (globally scalable)
# Can be extended for any country/city as needed
KNOWN_CITIES = {
    # Thailand
    'bangkok': {'lat': 13.7, 'lon': 100.5, 'country': 'thailand', 'tolerance': 1.0},
    'chiang mai': {'lat': 18.8, 'lon': 98.9, 'country': 'thailand', 'tolerance': 1.0},
    'phuket': {'lat': 7.9, 'lon': 98.4, 'country': 'thailand', 'tolerance': 1.0},
    'pattaya': {'lat': 12.9, 'lon': 100.9, 'country': 'thailand', 'tolerance': 0.5},
    'krabi': {'lat': 8.1, 'lon': 98.9, 'country': 'thailand', 'tolerance': 1.0},
    'koh samui': {'lat': 9.5, 'lon': 100.0, 'country': 'thailand', 'tolerance': 0.5},
    # Add more cities for other countries as needed
    'paris': {'lat': 48.8566, 'lon': 2.3522, 'country': 'france', 'tolerance': 0.5},
    'tokyo': {'lat': 35.6762, 'lon': 139.6503, 'country': 'japan', 'tolerance': 0.5},
    'new york': {'lat': 40.7128, 'lon': -74.0060, 'country': 'usa', 'tolerance': 0.5},
    'london': {'lat': 51.5074, 'lon': -0.1278, 'country': 'uk', 'tolerance': 0.5},
    'bali': {'lat': -8.4095, 'lon': 115.1889, 'country': 'indonesia', 'tolerance': 1.0},
}

# Legacy compatibility aliases
THAILAND_BOUNDS = REGION_BOUNDS['thailand']
THAILAND_CITIES = {k: v for k, v in KNOWN_CITIES.items() if v.get('country') == 'thailand'}


# =============================================================================
# Initialize Nominatim Client (Legacy - use Google Maps instead)
# =============================================================================

# Initialize with user agent (required by Nominatim)
# NOTE: Nominatim is being phased out in favor of Google Maps for accuracy
geolocator = Nominatim(
    user_agent="TravelAI-GlobalDestinations/2.0 (travel-ai-core)",
    timeout=10
)


# =============================================================================
# Function 1: Single Entity Geocoding
# =============================================================================

def geocode_nominatim(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Geocode a single entity using Nominatim (OpenStreetMap).

    Builds query from entity name, area, city and geocodes using Nominatim.
    Respects 1 request/second rate limit with sleep(1).

    Args:
        entity: Entity dict with 'canonical_name', 'location' (city, area)

    Returns:
        Dict with geocoding results:
        {
            'lat': float,
            'lon': float,
            'confidence': float (0-1),
            'display_name': str,
            'provider': 'nominatim'
        }
        Returns None if geocoding fails.

    Example:
        >>> entity = {
        ...     'canonical_name': 'Wat Pho',
        ...     'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}
        ... }
        >>> result = geocode_nominatim(entity)
        >>> print(result['lat'], result['lon'])
        13.746 100.493
    """
    try:
        # Build query from entity data
        name = entity.get('canonical_name', '')
        location = entity.get('location', {})
        area = location.get('area', '') if isinstance(location, dict) else ''
        city = location.get('city', '') if isinstance(location, dict) else ''

        if not name:
            logger.warning("Entity has no name, cannot geocode")
            return None

        # Build query: "{name}, {area}, {city}, {country}"
        # Country is optional for global scalability
        country = entity.get('country') or (location.get('country') if isinstance(location, dict) else None)

        query_parts = [name]
        if area:
            query_parts.append(area)
        if city:
            query_parts.append(city)
        if country:
            query_parts.append(country)
        elif DEFAULT_COUNTRY:
            query_parts.append(DEFAULT_COUNTRY)

        query = ', '.join(query_parts)
        logger.debug(f"Geocoding query: {query}")

        # Geocode with Nominatim
        # Rate limit: sleep BEFORE request to ensure 1 req/sec
        time.sleep(1)

        location_result = geolocator.geocode(
            query,
            exactly_one=True,
            addressdetails=True,
            language='en'
        )

        if not location_result:
            logger.debug(f"No results found for query: {query}")
            return None

        # Extract coordinates and metadata
        lat = location_result.latitude
        lon = location_result.longitude
        display_name = location_result.address

        # Calculate confidence based on address components
        # Higher confidence if address has more specific components
        raw_address = location_result.raw.get('address', {})
        confidence = 0.5  # Base confidence

        # Boost confidence for specific address types
        if raw_address.get('tourism'):
            confidence += 0.3
        elif raw_address.get('amenity'):
            confidence += 0.2
        elif raw_address.get('building'):
            confidence += 0.15

        # Boost if city matches
        if city.lower() in display_name.lower():
            confidence += 0.1

        # Cap at 1.0
        confidence = min(confidence, 1.0)

        result = {
            'lat': lat,
            'lon': lon,
            'confidence': confidence,
            'display_name': display_name,
            'provider': 'nominatim'
        }

        logger.debug(f"Geocoded '{name}' → ({lat:.4f}, {lon:.4f}) confidence={confidence:.2f}")
        return result

    except GeocoderTimedOut:
        logger.warning(f"Geocoding timed out for entity: {entity.get('canonical_name')}")
        return None

    except (GeocoderServiceError, GeocoderUnavailable) as e:
        logger.warning(f"Geocoder service error for entity {entity.get('canonical_name')}: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error geocoding entity {entity.get('canonical_name')}: {e}", exc_info=True)
        return None


# =============================================================================
# Entity Geocodability Check
# =============================================================================

# Patterns that indicate a generic/non-geocodable entity name
GENERIC_ENTITY_PATTERNS = [
    r'^(a |the |some |any )?bungalow(s)?\b',
    r'^(a |the |some |any )?hotel\b(?! [A-Z])',  # "hotel" without proper noun following
    r'^(a |the |some |any )?hostel\b(?! [A-Z])',
    r'^(a |the |some |any )?guesthouse\b(?! [A-Z])',
    r'^(a |the |some |any )?resort\b(?! [A-Z])',
    r'^(a |the |some |any )?restaurant\b(?! [A-Z])',
    r'^(a |the |some |any )?cafe\b(?! [A-Z])',
    r'^(a |the |some |any )?bar\b(?! [A-Z])',
    r'^(a |the |some |any )?shop\b(?! [A-Z])',
    r'^(a |the |some |any )?market\b(?! [A-Z])',
    r'^local\s+\w+',
    r'^small\s+\w+',
    r'^nice\s+\w+',
    r'^cheap\s+\w+',
    r'^good\s+\w+',
    r'^\w+\s+in\s+(the\s+)?(area|city|town|region)',
    r'^\w+\s+near\s+',
    r'^street\s+food',
    r'^food\s+stall',
    r'^night\s+market\b(?! [A-Z])',  # "night market" without proper name
    r'^day\s+trip\s+',
    r'^boat\s+trip\s+',
    r'^tour\s+(to|of|around)\s+',
    r'^(our|my|the)\s+(hotel|hostel|resort|airbnb|accommodation)',
]

# Compile patterns for efficiency
_GENERIC_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in GENERIC_ENTITY_PATTERNS]


def is_entity_geocodable(entity: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Check if an entity name is specific enough to geocode accurately.

    Generic names like "bungalow in resort" or "local restaurant" should not
    be geocoded as we don't know the exact location.

    Args:
        entity: Entity dict with 'canonical_name'

    Returns:
        Tuple of (is_geocodable, reason)
        - is_geocodable: True if entity can be geocoded accurately
        - reason: Explanation if not geocodable

    Example:
        >>> is_geocodable, reason = is_entity_geocodable({"canonical_name": "Wat Pho"})
        >>> print(is_geocodable)  # True

        >>> is_geocodable, reason = is_entity_geocodable({"canonical_name": "bungalow in resort"})
        >>> print(is_geocodable, reason)  # False, "Generic entity name"
    """
    name = entity.get('canonical_name', '').strip()

    if not name:
        return False, "Empty entity name"

    # Check if name is too short (likely generic)
    if len(name) < 4:
        return False, f"Name too short: '{name}'"

    # Check against generic patterns
    for pattern in _GENERIC_PATTERNS_COMPILED:
        if pattern.search(name):
            return False, f"Generic entity name pattern: '{name}'"

    # Check if name contains mostly common words without proper nouns
    words = name.split()
    if len(words) >= 2:
        # Check if first word is lowercase (likely generic description)
        if words[0][0].islower() and words[0] not in ['a', 'an', 'the']:
            return False, f"Likely generic description: '{name}'"

    return True, "OK"


# =============================================================================
# Function 2: Geocoding with Fallback Queries
# =============================================================================

def geocode_with_fallback_queries(
    entity: Dict[str, Any],
    skip_city_fallback: bool = True
) -> Optional[Tuple[Dict[str, Any], str]]:
    """
    Geocode entity with multiple fallback query variations.

    Tries progressively simpler queries to improve match rate:
    1. "{name}, {area}, {city}, Thailand"
    2. "{name}, {city}, Thailand"
    3. "{city}, Thailand" (city-level fallback - DISABLED by default)

    IMPORTANT: City-level fallback is disabled by default to prevent
    assigning city-center coordinates to entities we can't precisely locate.
    Better to have no coordinates than wrong coordinates.

    Args:
        entity: Entity dict with 'canonical_name', 'location'
        skip_city_fallback: If True, skip city-only fallback (default: True)

    Returns:
        Tuple of (result_dict, query_type) if successful, None if all queries fail.
        query_type is one of: 'full', 'no_area', 'city_only', 'skipped_generic'

    Example:
        >>> result, query_type = geocode_with_fallback_queries(entity)
        >>> print(f"Matched using {query_type} query")
        Matched using full query
    """
    name = entity.get('canonical_name', '')
    location = entity.get('location')

    # Step 0: Check if entity is geocodable (not a generic description)
    is_geocodable, reason = is_entity_geocodable(entity)
    if not is_geocodable:
        logger.info(f"⏭️  Skipping geocoding for '{name}': {reason}")
        return None

    # Handle location field being either a dict or string
    if isinstance(location, dict):
        area = location.get('area', '')
        city = location.get('city', '')
    elif isinstance(location, str):
        # Location is a string like "Bangkok" - treat it as city
        city = location
        area = ''
    else:
        city = ''
        area = ''

    if not name or not city:
        logger.warning(f"Entity missing name or city, cannot geocode: {entity.get('entity_id')}")
        return None

    # Get country for query (global scalability)
    country = entity.get('country') or (location.get('country') if isinstance(location, dict) else None)
    country_suffix = f", {country}" if country else (f", {DEFAULT_COUNTRY}" if DEFAULT_COUNTRY else "")

    # Strategy 1: Full query with area
    if area:
        query = f"{name}, {area}, {city}{country_suffix}"
        logger.debug(f"Trying full query: {query}")

        try:
            time.sleep(1)
            location_result = geolocator.geocode(query, exactly_one=True, addressdetails=True, language='en')

            if location_result:
                result = {
                    'lat': location_result.latitude,
                    'lon': location_result.longitude,
                    'confidence': 0.9,  # High confidence for full match
                    'display_name': location_result.address,
                    'provider': 'nominatim'
                }
                logger.info(f"✅ Geocoded '{name}' using full query → ({result['lat']:.4f}, {result['lon']:.4f})")
                return (result, 'full')

        except Exception as e:
            logger.debug(f"Full query failed: {e}")

    # Strategy 2: Query without area
    query = f"{name}, {city}{country_suffix}"
    logger.debug(f"Trying no-area query: {query}")

    try:
        time.sleep(1)
        location_result = geolocator.geocode(query, exactly_one=True, addressdetails=True, language='en')

        if location_result:
            result = {
                'lat': location_result.latitude,
                'lon': location_result.longitude,
                'confidence': 0.7,  # Medium confidence
                'display_name': location_result.address,
                'provider': 'nominatim'
            }
            logger.info(f"✅ Geocoded '{name}' using no-area query → ({result['lat']:.4f}, {result['lon']:.4f})")
            return (result, 'no_area')

    except Exception as e:
        logger.debug(f"No-area query failed: {e}")

    # Strategy 3: City-level fallback (DISABLED by default)
    # This prevents assigning city-center coordinates when we can't find the actual place
    if not skip_city_fallback:
        query = f"{city}{country_suffix}"
        logger.debug(f"Trying city-only query: {query}")

        try:
            time.sleep(1)
            location_result = geolocator.geocode(query, exactly_one=True, addressdetails=True, language='en')

            if location_result:
                result = {
                    'lat': location_result.latitude,
                    'lon': location_result.longitude,
                    'confidence': 0.3,  # Low confidence (city-level only)
                    'display_name': location_result.address,
                    'provider': 'nominatim',
                    'is_city_center': True  # Flag that this is city-center, not exact location
                }
                logger.warning(f"⚠️  Geocoded '{name}' using city-only fallback → ({result['lat']:.4f}, {result['lon']:.4f})")
                return (result, 'city_only')

        except Exception as e:
            logger.debug(f"City-only query failed: {e}")
    else:
        logger.info(f"⏭️  Skipping city-only fallback for '{name}' (would be inaccurate)")

    # All strategies failed (or city-only was skipped)
    logger.warning(f"⚠️  Could not geocode entity accurately: {name}")
    return None


# =============================================================================
# Function 3: Coordinate Validation
# =============================================================================

def validate_coordinates(
    lat: float,
    lon: float,
    expected_city: Optional[str] = None,
    region: Optional[str] = None
) -> bool:
    """
    Validate that coordinates are valid and optionally near expected city.

    Globally scalable validation:
    1. Coordinates are within valid global bounds (-90 to 90 lat, -180 to 180 lon)
    2. If region provided, check against region-specific bounds
    3. If expected_city provided, coordinates are roughly near that city

    Args:
        lat: Latitude
        lon: Longitude
        expected_city: Optional city name for rough validation
        region: Optional region name (e.g., 'thailand', 'global') for bounds checking

    Returns:
        True if coordinates are valid, False otherwise

    Example:
        >>> validate_coordinates(13.7, 100.5, 'Bangkok', 'thailand')
        True
        >>> validate_coordinates(48.8566, 2.3522, 'Paris')  # Paris coords
        True
    """
    # Basic global bounds check
    if not (-90 <= lat <= 90):
        logger.warning(f"Latitude {lat} outside valid bounds (-90 to 90)")
        return False

    if not (-180 <= lon <= 180):
        logger.warning(f"Longitude {lon} outside valid bounds (-180 to 180)")
        return False

    # Region-specific bounds check (optional)
    if region and region.lower() in REGION_BOUNDS:
        bounds = REGION_BOUNDS[region.lower()]
        if not (bounds['min_lat'] <= lat <= bounds['max_lat']):
            logger.warning(f"Latitude {lat} outside {region} bounds ({bounds['min_lat']}-{bounds['max_lat']})")
            return False
        if not (bounds['min_lon'] <= lon <= bounds['max_lon']):
            logger.warning(f"Longitude {lon} outside {region} bounds ({bounds['min_lon']}-{bounds['max_lon']})")
            return False

    # If expected city provided, do rough validation
    if expected_city:
        city_key = expected_city.lower().strip()

        if city_key in KNOWN_CITIES:
            city_coords = KNOWN_CITIES[city_key]
            city_lat = city_coords['lat']
            city_lon = city_coords['lon']
            tolerance = city_coords.get('tolerance', 1.0)

            lat_diff = abs(lat - city_lat)
            lon_diff = abs(lon - city_lon)

            if lat_diff > tolerance or lon_diff > tolerance:
                logger.warning(
                    f"Coordinates ({lat:.4f}, {lon:.4f}) far from expected {expected_city} "
                    f"({city_lat}, {city_lon}). Diff: lat={lat_diff:.2f}, lon={lon_diff:.2f}, tolerance={tolerance}"
                )
                return False

            logger.debug(f"Coordinates validated near {expected_city}")
        else:
            logger.debug(f"City '{expected_city}' not in validation database, skipping city check")

    return True


# =============================================================================
# Function 4: Batch Geocoding with Caching
# =============================================================================

def batch_geocode_nominatim(
    entities: List[Dict[str, Any]],
    cache_file: str = 'data/geocode_cache.json',
    use_fallback: bool = True,
    validate: bool = True
) -> Dict[str, Any]:
    """
    Batch geocode entities with local JSON caching and rate limiting.

    Processes entities one by one (respects 1 req/sec rate limit).
    Caches results to local JSON file to avoid re-geocoding.
    Tracks success rate and returns detailed statistics.

    Args:
        entities: List of entity dicts to geocode
        cache_file: Path to local JSON cache file (default: 'data/geocode_cache.json')
        use_fallback: Use fallback query strategies (default: True)
        validate: Validate coordinates are in Thailand (default: True)

    Returns:
        Dict with:
        {
            'results': {entity_id: coordinates_dict},
            'statistics': {
                'total_entities': int,
                'cached': int,
                'geocoded': int,
                'failed': int,
                'success_rate': float,
                'cache_hit_rate': float
            }
        }

    Example:
        >>> results = batch_geocode_nominatim(entities, cache_file='cache.json')
        >>> print(f"Success rate: {results['statistics']['success_rate']:.1f}%")
        Success rate: 85.5%
    """
    logger.info(f"🌍 Starting batch geocoding for {len(entities)} entities")

    # Load cache
    cache_path = Path(cache_file)
    cache = {}

    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logger.info(f"📦 Loaded {len(cache)} cached geocoding results from {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to load cache file {cache_file}: {e}")
            cache = {}
    else:
        logger.info("No cache file found, starting fresh")
        cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Track statistics
    stats = {
        'total_entities': len(entities),
        'cached': 0,
        'geocoded': 0,
        'failed': 0,
        'validation_failed': 0
    }

    results = {}

    # Process each entity
    for i, entity in enumerate(entities, 1):
        entity_id = entity.get('entity_id', f'unknown_{i}')
        entity_name = entity.get('canonical_name', 'Unknown')

        logger.info(f"[{i}/{len(entities)}] Processing: {entity_name} (ID: {entity_id})")

        # Check cache first
        if entity_id in cache:
            logger.info("  ✅ Found in cache")
            results[entity_id] = cache[entity_id]
            stats['cached'] += 1
            continue

        # Geocode
        geocode_result = None
        query_type = None

        if use_fallback:
            # Use fallback strategy
            fallback_result = geocode_with_fallback_queries(entity)
            if fallback_result:
                geocode_result, query_type = fallback_result
        else:
            # Use simple geocoding
            geocode_result = geocode_nominatim(entity)
            query_type = 'simple'

        if geocode_result:
            # Validate coordinates
            if validate:
                location = entity.get('location')
                if isinstance(location, dict):
                    city = location.get('city')
                elif isinstance(location, str):
                    city = location
                else:
                    city = None

                is_valid = validate_coordinates(
                    geocode_result['lat'],
                    geocode_result['lon'],
                    expected_city=city
                )

                if not is_valid:
                    logger.warning(f"  ❌ Coordinates validation failed for {entity_name}")
                    stats['validation_failed'] += 1
                    stats['failed'] += 1
                    continue

            # Add metadata
            geocode_result['query_type'] = query_type
            geocode_result['geocoded_at'] = datetime.now(timezone.utc).isoformat()

            results[entity_id] = geocode_result
            cache[entity_id] = geocode_result
            stats['geocoded'] += 1

            logger.info(f"  ✅ Geocoded → ({geocode_result['lat']:.4f}, {geocode_result['lon']:.4f})")
        else:
            logger.error(f"  ❌ Geocoding failed for {entity_name}")
            stats['failed'] += 1

    # Calculate rates
    stats['success_rate'] = (stats['cached'] + stats['geocoded']) / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['cache_hit_rate'] = stats['cached'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0

    # Save updated cache
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Saved {len(cache)} geocoding results to cache: {cache_file}")
    except Exception as e:
        logger.error(f"Failed to save cache file: {e}")

    # Summary
    logger.info("=" * 80)
    logger.info("BATCH GEOCODING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total entities: {stats['total_entities']}")
    logger.info(f"Cached results: {stats['cached']}")
    logger.info(f"Newly geocoded: {stats['geocoded']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Validation failed: {stats['validation_failed']}")
    logger.info(f"Success rate: {stats['success_rate']:.1f}%")
    logger.info(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")
    logger.info("=" * 80)

    return {
        'results': results,
        'statistics': stats
    }


# =============================================================================
# Google Maps Geocoding (Fallback Option)
# =============================================================================

# Global cost tracking for Google Maps API
_GOOGLE_MAPS_REQUESTS = 0
_GOOGLE_MAPS_COST_USD = 0.0

# Google Maps client (lazy initialization)
_gmaps_client = None


def get_google_maps_client():
    """
    Get or initialize Google Maps client.

    Requires GOOGLE_MAPS_API_KEY in environment.

    Returns:
        googlemaps.Client or None if API key not configured
    """
    global _gmaps_client

    if _gmaps_client is not None:
        return _gmaps_client

    try:
        import googlemaps
        import os
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv('GOOGLE_MAPS_API_KEY')

        if not api_key or api_key == 'your_google_maps_api_key_here':
            logger.warning("Google Maps API key not configured. Set GOOGLE_MAPS_API_KEY in .env")
            return None

        _gmaps_client = googlemaps.Client(key=api_key)
        logger.info("✅ Google Maps client initialized")
        return _gmaps_client

    except ImportError:
        logger.warning("googlemaps library not installed. Run: pip install googlemaps")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Google Maps client: {e}")
        return None


def get_google_maps_cost_stats() -> Dict[str, Any]:
    """
    Get Google Maps API usage statistics.

    Returns:
        Dict with total_requests and total_cost_usd
    """
    return {
        'total_requests': _GOOGLE_MAPS_REQUESTS,
        'total_cost_usd': _GOOGLE_MAPS_COST_USD
    }


def reset_google_maps_cost_stats() -> None:
    """Reset Google Maps cost statistics."""
    global _GOOGLE_MAPS_REQUESTS, _GOOGLE_MAPS_COST_USD
    _GOOGLE_MAPS_REQUESTS = 0
    _GOOGLE_MAPS_COST_USD = 0.0


def geocode_google(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Geocode a single entity using Google Maps Geocoding API.

    Google Maps is very accurate but costs $5 per 1000 requests.
    Use as fallback when Nominatim fails or has low confidence.

    Args:
        entity: Entity dict with 'canonical_name', 'location'

    Returns:
        Dict with geocoding results:
        {
            'lat': float,
            'lon': float,
            'confidence': 0.95,  # Google is very accurate
            'place_id': str,  # IMPORTANT for Stage 5!
            'formatted_address': str,
            'provider': 'google'
        }
        Returns None if geocoding fails.

    Example:
        >>> entity = {'canonical_name': 'Wat Pho', 'location': {'city': 'Bangkok'}}
        >>> result = geocode_google(entity)
        >>> print(result['place_id'])  # For Stage 5 enrichment
        ChIJ...
    """
    global _GOOGLE_MAPS_REQUESTS, _GOOGLE_MAPS_COST_USD

    gmaps = get_google_maps_client()
    if not gmaps:
        logger.warning("Google Maps client not available")
        return None

    try:
        # Build query
        name = entity.get('canonical_name', '')
        location = entity.get('location')

        # Handle location field being either a dict or string
        if isinstance(location, dict):
            area = location.get('area', '')
            city = location.get('city', '')
        elif isinstance(location, str):
            # Location is a string like "Bangkok" - treat it as city
            city = location
            area = ''
        else:
            city = ''
            area = ''

        if not name:
            logger.warning("Entity has no name, cannot geocode")
            return None

        # Build query: "{name}, {area}, {city}, {country}"
        # Country is optional for global scalability
        country = entity.get('country') or (location.get('country') if isinstance(location, dict) else None)

        query_parts = [name]
        if area:
            query_parts.append(area)
        if city:
            query_parts.append(city)
        if country:
            query_parts.append(country)
        elif DEFAULT_COUNTRY:
            query_parts.append(DEFAULT_COUNTRY)

        query = ', '.join(query_parts)
        logger.debug(f"Google Maps query: {query}")

        # Geocode with Google Maps
        # No need for rate limiting - Google allows 50 req/sec
        geocode_results = gmaps.geocode(query)

        if not geocode_results or len(geocode_results) == 0:
            logger.debug(f"No results found for query: {query}")
            return None

        # Get first result (best match)
        result = geocode_results[0]

        # Extract data
        geometry = result.get('geometry', {})
        location_data = geometry.get('location', {})
        lat = location_data.get('lat')
        lon = location_data.get('lng')

        if lat is None or lon is None:
            logger.warning("Google Maps result missing coordinates")
            return None

        place_id = result.get('place_id', '')
        formatted_address = result.get('formatted_address', '')

        # Google Maps is very accurate - high confidence
        confidence = 0.95

        # Update cost tracking
        # $5 per 1000 requests = $0.005 per request
        _GOOGLE_MAPS_REQUESTS += 1
        _GOOGLE_MAPS_COST_USD += 0.005

        geocode_result = {
            'lat': lat,
            'lon': lon,
            'confidence': confidence,
            'place_id': place_id,
            'formatted_address': formatted_address,
            'provider': 'google'
        }

        logger.debug(f"Google geocoded '{name}' → ({lat:.4f}, {lon:.4f}) place_id={place_id}")
        return geocode_result

    except Exception as e:
        logger.error(f"Google Maps geocoding error for {entity.get('canonical_name')}: {e}")
        return None


# =============================================================================
# Reverse Geocoding (Coordinates → City/Country)
# =============================================================================

def reverse_geocode_google(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Reverse geocode coordinates to get city, country, and address info.

    Uses Google Maps Reverse Geocoding API ($5 per 1000 requests).

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Dict with location info:
        {
            'city': str,
            'country': str,
            'country_code': str,
            'state': str,
            'formatted_address': str,
            'place_id': str,
            'provider': 'google_reverse'
        }
        Returns None if reverse geocoding fails.

    Example:
        >>> result = reverse_geocode_google(13.7563, 100.5018)
        >>> print(f"{result['city']}, {result['country']}")
        Bangkok, Thailand
    """
    global _GOOGLE_MAPS_REQUESTS, _GOOGLE_MAPS_COST_USD

    gmaps = get_google_maps_client()
    if not gmaps:
        logger.warning("Google Maps client not available for reverse geocoding")
        return None

    try:
        # Reverse geocode with Google Maps
        results = gmaps.reverse_geocode((lat, lon), language='en')

        if not results:
            logger.warning(f"No reverse geocoding results for ({lat}, {lon})")
            return None

        # Parse the first result
        result = results[0]
        address_components = result.get('address_components', [])

        # Extract city, country, state from address components
        city = None
        country = None
        country_code = None
        state = None

        for component in address_components:
            types = component.get('types', [])

            # City - try multiple possible types
            if not city:
                if 'locality' in types:
                    city = component.get('long_name')
                elif 'administrative_area_level_2' in types:
                    city = component.get('long_name')
                elif 'sublocality_level_1' in types:
                    city = component.get('long_name')

            # Country
            if 'country' in types:
                country = component.get('long_name')
                country_code = component.get('short_name')

            # State/Province
            if 'administrative_area_level_1' in types:
                state = component.get('long_name')

        # Track API usage
        _GOOGLE_MAPS_REQUESTS += 1
        _GOOGLE_MAPS_COST_USD += 0.005

        reverse_result = {
            'city': city,
            'country': country,
            'country_code': country_code,
            'state': state,
            'formatted_address': result.get('formatted_address'),
            'place_id': result.get('place_id'),
            'provider': 'google_reverse'
        }

        logger.debug(f"Reverse geocoded ({lat:.4f}, {lon:.4f}) → {city}, {country}")
        return reverse_result

    except Exception as e:
        logger.error(f"Google Maps reverse geocoding error for ({lat}, {lon}): {e}")
        return None


def fill_missing_location_from_coordinates(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill in missing city/country fields using reverse geocoding from coordinates.

    This is a FALLBACK when entity has GPS coordinates but no city/country info.

    Args:
        entity: Entity dict with 'coordinates' but potentially missing 'city'/'country'

    Returns:
        Updated entity dict with filled city/country if reverse geocoding succeeds

    Example:
        >>> entity = {'coordinates': {'lat': 13.75, 'lon': 100.50}, 'city': None}
        >>> updated = fill_missing_location_from_coordinates(entity)
        >>> print(updated['city'])
        Bangkok
    """
    # Check if we have coordinates
    coords = entity.get('coordinates', {})
    lat = coords.get('lat') or coords.get('latitude')
    lon = coords.get('lon') or coords.get('longitude')

    if not lat or not lon:
        return entity

    # Check if city/country already filled (case-insensitive comparison)
    city = entity.get('city')
    country = entity.get('country')

    # If both are filled with valid values, nothing to do
    if not is_missing_or_unknown(city) and not is_missing_or_unknown(country):
        return entity

    # Reverse geocode to get location info
    logger.debug(f"Reverse geocoding to fill missing city/country for {entity.get('canonical_name', 'unknown')}")
    reverse_result = reverse_geocode_google(lat, lon)

    if not reverse_result:
        return entity

    # Fill in missing fields
    if is_missing_or_unknown(city):
        if reverse_result.get('city'):
            entity['city'] = reverse_result['city']
            logger.info(f"✅ Filled city from reverse geocoding: {reverse_result['city']}")

    if is_missing_or_unknown(country):
        if reverse_result.get('country'):
            entity['country'] = reverse_result['country']
            logger.info(f"✅ Filled country from reverse geocoding: {reverse_result['country']}")

    # Also update location dict if it exists
    if 'location' in entity and isinstance(entity['location'], dict):
        loc_city = entity['location'].get('city')
        loc_country = entity['location'].get('country')
        if is_missing_or_unknown(loc_city):
            entity['location']['city'] = reverse_result.get('city')
        if is_missing_or_unknown(loc_country):
            entity['location']['country'] = reverse_result.get('country')

    # Add reverse geocoding provenance
    entity['reverse_geocode_info'] = {
        'state': reverse_result.get('state'),
        'formatted_address': reverse_result.get('formatted_address'),
        'place_id': reverse_result.get('place_id'),
        'provider': 'google_reverse'
    }

    return entity


def batch_fill_missing_locations(entities: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Batch fill missing city/country for entities that have coordinates but no location.

    Args:
        entities: List of entities with coordinates

    Returns:
        Tuple of (updated_entities, stats)
        stats: {'total': int, 'filled': int, 'already_had': int, 'failed': int}
    """
    stats = {
        'total': len(entities),
        'filled': 0,
        'already_had': 0,
        'no_coordinates': 0,
        'failed': 0
    }

    updated = []

    for entity in entities:
        # Check if coordinates exist
        coords = entity.get('coordinates', {})
        lat = coords.get('lat') or coords.get('latitude')
        lon = coords.get('lon') or coords.get('longitude')

        if not lat or not lon:
            stats['no_coordinates'] += 1
            updated.append(entity)
            continue

        # Check if already has city/country (case-insensitive)
        city = entity.get('city')
        country = entity.get('country')

        if not is_missing_or_unknown(city) and not is_missing_or_unknown(country):
            stats['already_had'] += 1
            updated.append(entity)
            continue

        # Try to fill
        try:
            updated_entity = fill_missing_location_from_coordinates(entity)

            # Check if we successfully filled (case-insensitive)
            new_city = updated_entity.get('city')
            new_country = updated_entity.get('country')

            if not is_missing_or_unknown(new_city) or not is_missing_or_unknown(new_country):
                stats['filled'] += 1
            else:
                stats['failed'] += 1

            updated.append(updated_entity)

        except Exception as e:
            logger.error(f"Failed to reverse geocode {entity.get('canonical_name')}: {e}")
            stats['failed'] += 1
            updated.append(entity)

    logger.info("📍 Reverse geocoding batch complete:")
    logger.info(f"   Total: {stats['total']}")
    logger.info(f"   Already had city/country: {stats['already_had']}")
    logger.info(f"   Filled via reverse geocode: {stats['filled']}")
    logger.info(f"   No coordinates: {stats['no_coordinates']}")
    logger.info(f"   Failed: {stats['failed']}")

    return updated, stats


# =============================================================================
# Google Maps Only Geocoding (Simplified - No Nominatim)
# =============================================================================

def geocode_google_only(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Geocode entity using ONLY Google Maps API.

    This is the simplified geocoding function that doesn't use Nominatim.
    More accurate and consistent, but costs $5 per 1000 requests.

    Args:
        entity: Entity dict with 'canonical_name', 'location'

    Returns:
        Geocoding result dict or None

    Example:
        >>> entity = {'canonical_name': 'Eiffel Tower', 'location': {'city': 'Paris'}}
        >>> result = geocode_google_only(entity)
    """
    name = entity.get('canonical_name', 'Unknown')

    # Check if entity is geocodable
    is_geocodable_flag, reason = is_entity_geocodable(entity)
    if not is_geocodable_flag:
        logger.info(f"⏭️  Skipping geocoding for '{name}': {reason}")
        return None

    # Use Google Maps directly
    return geocode_google(entity)


def batch_geocode_google_only(
    entities: List[Dict[str, Any]],
    cache_file: Optional[str] = 'data/geocode_cache_google.json',
    fill_missing_locations: bool = True
) -> Dict[str, Any]:
    """
    Batch geocode entities using ONLY Google Maps API.

    This is the simplified batch geocoding function that:
    1. Uses Google Maps exclusively (no Nominatim)
    2. Optionally fills missing city/country via reverse geocoding
    3. Caches results locally for cost optimization

    Args:
        entities: List of entities to geocode
        cache_file: Path to cache file (None to disable caching)
        fill_missing_locations: If True, reverse geocode to fill missing city/country

    Returns:
        Dict with:
        {
            'results': {entity_id: coordinates_dict},
            'statistics': {
                'total_entities': int,
                'cached': int,
                'geocoded': int,
                'skipped_generic': int,
                'failed': int,
                'reverse_geocoded': int,
                'success_rate': float,
                'google_cost_usd': float
            }
        }
    """
    # Load cache
    cache = {}
    if cache_file:
        try:
            cache_path = Path(cache_file)
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    cache = json.load(f)
                logger.info(f"📂 Loaded {len(cache)} cached geocoding results")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")

    results = {}
    stats = {
        'total_entities': len(entities),
        'cached': 0,
        'geocoded': 0,
        'skipped_generic': 0,
        'failed': 0,
        'reverse_geocoded': 0,
        'google_cost_usd': 0.0
    }

    # Track Google cost for this batch
    google_cost_before = _GOOGLE_MAPS_COST_USD

    for entity in entities:
        entity_id = entity.get('entity_id')
        name = entity.get('canonical_name', 'Unknown')

        if not entity_id:
            logger.warning(f"Entity missing entity_id, skipping: {name}")
            stats['failed'] += 1
            continue

        # Check cache first
        if entity_id in cache:
            results[entity_id] = cache[entity_id]
            stats['cached'] += 1
            logger.debug(f"📦 Using cached result for '{name}'")
            continue

        # Check if geocodable
        is_geocodable_flag, reason = is_entity_geocodable(entity)
        if not is_geocodable_flag:
            stats['skipped_generic'] += 1
            continue

        # Geocode with Google Maps
        geocode_result = geocode_google(entity)

        if geocode_result:
            results[entity_id] = geocode_result
            cache[entity_id] = geocode_result
            stats['geocoded'] += 1
        else:
            stats['failed'] += 1

    # Save cache
    if cache_file and cache:
        try:
            cache_path = Path(cache_file)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w') as f:
                json.dump(cache, f)
            logger.info(f"💾 Saved {len(cache)} geocoding results to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    # Fill missing locations via reverse geocoding if requested
    if fill_missing_locations:
        entities_needing_reverse = []
        for entity in entities:
            entity_id = entity.get('entity_id')
            if entity_id in results:
                # Entity has coordinates - check if it needs reverse geocoding (case-insensitive)
                city = entity.get('city')
                country = entity.get('country')
                if is_missing_or_unknown(city) or is_missing_or_unknown(country):
                    # Add coordinates to entity for reverse geocoding
                    entity['coordinates'] = results[entity_id]
                    entities_needing_reverse.append(entity)

        if entities_needing_reverse:
            logger.info(f"🔄 Reverse geocoding {len(entities_needing_reverse)} entities with missing city/country...")
            _, reverse_stats = batch_fill_missing_locations(entities_needing_reverse)
            stats['reverse_geocoded'] = reverse_stats['filled']

    # Calculate stats
    stats['success_rate'] = (
        (stats['cached'] + stats['geocoded']) / stats['total_entities'] * 100
        if stats['total_entities'] > 0 else 0
    )
    stats['google_cost_usd'] = _GOOGLE_MAPS_COST_USD - google_cost_before

    # Log summary
    logger.info("\n📍 Google Maps Geocoding Complete:")
    logger.info(f"   Total entities: {stats['total_entities']}")
    logger.info(f"   From cache: {stats['cached']}")
    logger.info(f"   Geocoded (new): {stats['geocoded']}")
    logger.info(f"   Skipped (generic): {stats['skipped_generic']}")
    logger.info(f"   Failed: {stats['failed']}")
    logger.info(f"   Success rate: {stats['success_rate']:.1f}%")
    logger.info(f"   💰 Google Maps cost: ${stats['google_cost_usd']:.4f}")
    if stats['reverse_geocoded'] > 0:
        logger.info(f"   Reverse geocoded: {stats['reverse_geocoded']}")

    return {
        'results': results,
        'statistics': stats
    }


# =============================================================================
# Hybrid Geocoding Strategy (Nominatim + Google Fallback)
# =============================================================================

def geocode_hybrid(
    entity: Dict[str, Any],
    nominatim_confidence_threshold: float = 0.8,
    use_nominatim_fallback: bool = True,
    skip_city_fallback: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Hybrid geocoding: Try Nominatim first (FREE), fallback to Google if needed.

    Strategy:
    0. Check if entity is geocodable (not a generic description)
    1. Try Nominatim with fallback queries
    2. If confidence >= threshold: use Nominatim result (FREE!)
    3. Else: fallback to Google Maps (accurate but costs $0.005)
    4. Validate result is in expected region
    5. If both fail or validation fails: return None

    Args:
        entity: Entity dict to geocode
        nominatim_confidence_threshold: Min confidence to accept Nominatim (default: 0.8)
        use_nominatim_fallback: Use Nominatim fallback queries (default: True)
        skip_city_fallback: Skip city-center fallback to avoid inaccurate coords (default: True)

    Returns:
        Geocoding result dict with provider='nominatim' or 'google'
        Returns None if entity is not geocodable or both providers fail

    Example:
        >>> entity = {'canonical_name': 'Wat Pho', 'location': {'city': 'Bangkok'}}
        >>> result = geocode_hybrid(entity, nominatim_confidence_threshold=0.8)
        >>> print(f"Provider: {result['provider']}, Confidence: {result['confidence']}")
        Provider: nominatim, Confidence: 0.9
    """
    name = entity.get('canonical_name', 'Unknown')

    # Step 0: Check if entity is geocodable
    is_geocodable_flag, reason = is_entity_geocodable(entity)
    if not is_geocodable_flag:
        logger.info(f"⏭️  Skipping geocoding for '{name}': {reason}")
        return None

    # Try Nominatim first (FREE)
    nominatim_result = None

    if use_nominatim_fallback:
        fallback_result = geocode_with_fallback_queries(entity, skip_city_fallback=skip_city_fallback)
        if fallback_result:
            nominatim_result, query_type = fallback_result
            nominatim_result['query_type'] = query_type
    else:
        nominatim_result = geocode_nominatim(entity)
        if nominatim_result:
            nominatim_result['query_type'] = 'simple'

    # Check Nominatim confidence
    if nominatim_result and nominatim_result['confidence'] >= nominatim_confidence_threshold:
        logger.info(f"✅ Using Nominatim result (FREE, confidence={nominatim_result['confidence']:.2f})")
        return nominatim_result

    # Nominatim failed or low confidence - try Google Maps fallback
    logger.info("⚠️  Nominatim confidence too low or failed, trying Google Maps fallback...")

    google_result = geocode_google(entity)

    if google_result:
        logger.info(f"✅ Using Google Maps result (PAID $0.005, confidence={google_result['confidence']:.2f})")
        return google_result

    # Both failed
    if nominatim_result:
        # Return low-confidence Nominatim result as last resort
        logger.warning("⚠️  Google Maps failed, returning low-confidence Nominatim result")
        return nominatim_result

    logger.error("❌ Both Nominatim and Google Maps failed")
    return None


def batch_geocode_hybrid(
    entities: List[Dict[str, Any]],
    cache_file: Optional[str] = 'data/geocode_cache_hybrid.json',
    nominatim_confidence_threshold: float = 0.8,
    validate: bool = True,
    skip_city_fallback: bool = True
) -> Dict[str, Any]:
    """
    Batch geocode entities using hybrid strategy (Nominatim + Google fallback).

    Processes entities one by one with intelligent fallback:
    0. Check if entity is geocodable (skip generic names)
    1. Check cache first
    2. Try Nominatim (FREE, 1 req/sec)
    3. If confidence < threshold: fallback to Google ($0.005, 50 req/sec)
    4. Validate coordinates in expected region
    5. Cache all results

    IMPORTANT: Generic entity names (e.g., "bungalow in resort") are skipped
    to avoid assigning inaccurate coordinates.

    Args:
        entities: List of entity dicts to geocode
        cache_file: Path to cache file (default: 'data/geocode_cache_hybrid.json')
        nominatim_confidence_threshold: Min confidence for Nominatim (default: 0.8)
        validate: Validate coordinates in Thailand (default: True)
        skip_city_fallback: Skip city-center fallback to avoid inaccurate coords (default: True)

    Returns:
        Dict with:
        {
            'results': {entity_id: coordinates_dict},
            'statistics': {
                'total_entities': int,
                'cached': int,
                'nominatim': int,
                'google': int,
                'skipped_generic': int,
                'failed': int,
                'success_rate': float,
                'google_cost_usd': float
            }
        }

    Example:
        >>> results = batch_geocode_hybrid(entities, cache_file='cache.json')
        >>> print(f"Google cost: ${results['statistics']['google_cost_usd']:.2f}")
        Google cost: $0.03
    """
    logger.info(f"🌍 Starting hybrid batch geocoding for {len(entities)} entities")

    # Load cache (skip if cache_file is None)
    cache_path = Path(cache_file) if cache_file else None
    cache = {}

    if cache_path:
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                logger.info(f"📦 Loaded {len(cache)} cached results from {cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                cache = {}
        else:
            logger.info("No cache found, starting fresh")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        logger.info("🔄 Cache disabled - processing all entities fresh")

    # Track statistics
    stats = {
        'total_entities': len(entities),
        'cached': 0,
        'nominatim': 0,
        'google': 0,
        'skipped_generic': 0,
        'failed': 0,
        'validation_failed': 0
    }

    # Reset Google cost tracking for this batch
    google_requests_before = _GOOGLE_MAPS_REQUESTS
    google_cost_before = _GOOGLE_MAPS_COST_USD

    results = {}

    # Process each entity
    for i, entity in enumerate(entities, 1):
        entity_id = entity.get('entity_id', f'unknown_{i}')
        entity_name = entity.get('canonical_name', 'Unknown')

        logger.info(f"[{i}/{len(entities)}] Processing: {entity_name} (ID: {entity_id})")

        # Check cache
        if entity_id in cache:
            logger.info("  ✅ Found in cache")
            results[entity_id] = cache[entity_id]
            stats['cached'] += 1
            continue

        # Check if entity is geocodable before attempting
        is_geocodable_flag, reason = is_entity_geocodable(entity)
        if not is_geocodable_flag:
            logger.info(f"  ⏭️  Skipping: {reason}")
            stats['skipped_generic'] += 1
            continue

        # Geocode with hybrid strategy
        geocode_result = geocode_hybrid(
            entity,
            nominatim_confidence_threshold=nominatim_confidence_threshold,
            use_nominatim_fallback=True,
            skip_city_fallback=skip_city_fallback
        )

        if geocode_result:
            # Validate coordinates
            if validate:
                location = entity.get('location')
                if isinstance(location, dict):
                    city = location.get('city')
                elif isinstance(location, str):
                    city = location
                else:
                    city = None

                is_valid = validate_coordinates(
                    geocode_result['lat'],
                    geocode_result['lon'],
                    expected_city=city
                )

                if not is_valid:
                    logger.warning("  ❌ Coordinates validation failed")
                    stats['validation_failed'] += 1
                    stats['failed'] += 1
                    continue

            # Add metadata
            geocode_result['geocoded_at'] = datetime.now(timezone.utc).isoformat()

            results[entity_id] = geocode_result
            cache[entity_id] = geocode_result

            # Track provider
            provider = geocode_result['provider']
            if provider == 'nominatim':
                stats['nominatim'] += 1
            elif provider == 'google':
                stats['google'] += 1

            logger.info(f"  ✅ Geocoded with {provider} → ({geocode_result['lat']:.4f}, {geocode_result['lon']:.4f})")
        else:
            logger.error("  ❌ Geocoding failed")
            stats['failed'] += 1

    # Calculate rates and costs
    stats['success_rate'] = (stats['cached'] + stats['nominatim'] + stats['google']) / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['cache_hit_rate'] = stats['cached'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['google_requests_this_batch'] = _GOOGLE_MAPS_REQUESTS - google_requests_before
    stats['google_cost_usd'] = _GOOGLE_MAPS_COST_USD - google_cost_before

    # Save cache (skip if cache disabled)
    if cache_path:
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Saved {len(cache)} results to cache: {cache_file}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    else:
        logger.info("💨 Cache disabled - results not persisted")

    # Summary
    logger.info("=" * 80)
    logger.info("HYBRID BATCH GEOCODING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total entities: {stats['total_entities']}")
    logger.info(f"Cached results: {stats['cached']}")
    logger.info(f"Nominatim (FREE): {stats['nominatim']}")
    logger.info(f"Google Maps (PAID): {stats['google']}")
    logger.info(f"Skipped (generic names): {stats['skipped_generic']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Validation failed: {stats['validation_failed']}")
    logger.info(f"Success rate: {stats['success_rate']:.1f}%")
    logger.info(f"Cache hit rate: {stats['cache_hit_rate']:.1f}%")
    logger.info(f"💰 Google Maps cost this batch: ${stats['google_cost_usd']:.4f}")
    logger.info(f"💰 Google Maps total cost: ${_GOOGLE_MAPS_COST_USD:.4f}")
    logger.info("=" * 80)

    return {
        'results': results,
        'statistics': stats
    }


# =============================================================================
# Test Function
# =============================================================================

def test_geocoding_with_sample_entities():
    """
    Test geocoding with 10 sample Thai travel entities.

    Tests the complete geocoding pipeline with real queries.
    """
    logger.info("=" * 80)
    logger.info("GEOLOCATION TEST - 10 Sample Entities")
    logger.info("=" * 80)

    # Sample entities from different Thai cities
    sample_entities = [
        {
            'entity_id': 'ATT_001',
            'canonical_name': 'Wat Pho',
            'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}
        },
        {
            'entity_id': 'ATT_002',
            'canonical_name': 'Grand Palace',
            'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}
        },
        {
            'entity_id': 'ATT_003',
            'canonical_name': 'Doi Suthep',
            'location': {'city': 'Chiang Mai', 'area': 'Doi Suthep'}
        },
        {
            'entity_id': 'ATT_004',
            'canonical_name': 'Patong Beach',
            'location': {'city': 'Phuket', 'area': 'Patong'}
        },
        {
            'entity_id': 'ATT_005',
            'canonical_name': 'Railay Beach',
            'location': {'city': 'Krabi', 'area': 'Ao Nang'}
        },
        {
            'entity_id': 'ATT_006',
            'canonical_name': 'Khao San Road',
            'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}
        },
        {
            'entity_id': 'ATT_007',
            'canonical_name': 'Phi Phi Islands',
            'location': {'city': 'Krabi', 'area': ''}
        },
        {
            'entity_id': 'ATT_008',
            'canonical_name': 'Night Bazaar',
            'location': {'city': 'Chiang Mai', 'area': 'Chang Khlan'}
        },
        {
            'entity_id': 'ATT_009',
            'canonical_name': 'Ayutthaya Historical Park',
            'location': {'city': 'Ayutthaya', 'area': ''}
        },
        {
            'entity_id': 'ATT_010',
            'canonical_name': 'Chatuchak Market',
            'location': {'city': 'Bangkok', 'area': 'Chatuchak'}
        }
    ]

    # Test batch geocoding
    results = batch_geocode_nominatim(
        entities=sample_entities,
        cache_file='data/test_geocode_cache.json',
        use_fallback=True,
        validate=True
    )

    # Display results
    logger.info("\n📍 Geocoding Results:")
    logger.info("=" * 80)

    for entity in sample_entities:
        entity_id = entity['entity_id']
        name = entity['canonical_name']

        if entity_id in results['results']:
            coords = results['results'][entity_id]
            logger.info(f"✅ {name}")
            logger.info(f"   Coordinates: ({coords['lat']:.4f}, {coords['lon']:.4f})")
            logger.info(f"   Confidence: {coords['confidence']:.2f}")
            logger.info(f"   Query type: {coords.get('query_type', 'N/A')}")
        else:
            logger.info(f"❌ {name} - FAILED")

    logger.info("=" * 80)
    logger.info("Test complete!")

    return results


def test_hybrid_geocoding():
    """
    Test hybrid geocoding strategy with 20 sample entities.

    Tests Nominatim + Google Maps fallback with varied confidence scenarios.
    """
    logger.info("=" * 80)
    logger.info("HYBRID GEOCODING TEST - 20 Sample Entities")
    logger.info("=" * 80)

    # Sample entities - mix of well-known and obscure places
    sample_entities = [
        # Well-known (should work with Nominatim)
        {'entity_id': 'ATT_001', 'canonical_name': 'Wat Pho', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
        {'entity_id': 'ATT_002', 'canonical_name': 'Grand Palace', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
        {'entity_id': 'ATT_003', 'canonical_name': 'Doi Suthep', 'location': {'city': 'Chiang Mai', 'area': 'Doi Suthep'}},
        {'entity_id': 'ATT_004', 'canonical_name': 'Patong Beach', 'location': {'city': 'Phuket', 'area': 'Patong'}},
        {'entity_id': 'ATT_005', 'canonical_name': 'Khao San Road', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
        {'entity_id': 'ATT_006', 'canonical_name': 'Phi Phi Islands', 'location': {'city': 'Krabi', 'area': ''}},
        {'entity_id': 'ATT_007', 'canonical_name': 'Railay Beach', 'location': {'city': 'Krabi', 'area': 'Ao Nang'}},
        {'entity_id': 'ATT_008', 'canonical_name': 'Chatuchak Market', 'location': {'city': 'Bangkok', 'area': 'Chatuchak'}},
        {'entity_id': 'ATT_009', 'canonical_name': 'Ayutthaya Historical Park', 'location': {'city': 'Ayutthaya', 'area': ''}},
        {'entity_id': 'ATT_010', 'canonical_name': 'Night Bazaar', 'location': {'city': 'Chiang Mai', 'area': 'Chang Khlan'}},

        # More obscure (may require Google fallback)
        {'entity_id': 'ATT_011', 'canonical_name': 'Lumpini Park', 'location': {'city': 'Bangkok', 'area': 'Pathum Wan'}},
        {'entity_id': 'ATT_012', 'canonical_name': 'Tiger Kingdom', 'location': {'city': 'Chiang Mai', 'area': 'Mae Rim'}},
        {'entity_id': 'ATT_013', 'canonical_name': 'Maya Bay', 'location': {'city': 'Krabi', 'area': 'Phi Phi'}},
        {'entity_id': 'ATT_014', 'canonical_name': 'Walking Street', 'location': {'city': 'Pattaya', 'area': ''}},
        {'entity_id': 'ATT_015', 'canonical_name': 'Asiatique Night Market', 'location': {'city': 'Bangkok', 'area': 'Bang Kho Laem'}},
        {'entity_id': 'ATT_016', 'canonical_name': 'Sticky Waterfalls', 'location': {'city': 'Chiang Mai', 'area': 'Mae Taeng'}},
        {'entity_id': 'ATT_017', 'canonical_name': 'James Bond Island', 'location': {'city': 'Phuket', 'area': 'Phang Nga'}},
        {'entity_id': 'ATT_018', 'canonical_name': 'Khao Yai National Park', 'location': {'city': 'Nakhon Ratchasima', 'area': ''}},
        {'entity_id': 'ATT_019', 'canonical_name': 'Erawan Waterfalls', 'location': {'city': 'Kanchanaburi', 'area': ''}},
        {'entity_id': 'ATT_020', 'canonical_name': 'Full Moon Party Beach', 'location': {'city': 'Koh Phangan', 'area': 'Haad Rin'}},
    ]

    # Test hybrid geocoding
    results = batch_geocode_hybrid(
        entities=sample_entities,
        cache_file='data/test_geocode_cache_hybrid.json',
        nominatim_confidence_threshold=0.8,
        validate=True
    )

    # Display results
    logger.info("\n📍 Hybrid Geocoding Results:")
    logger.info("=" * 80)

    for entity in sample_entities:
        entity_id = entity['entity_id']
        name = entity['canonical_name']

        if entity_id in results['results']:
            coords = results['results'][entity_id]
            provider = coords.get('provider', 'unknown')
            provider_emoji = "🆓" if provider == 'nominatim' else "💳"

            logger.info(f"{provider_emoji} {name}")
            logger.info(f"   Coordinates: ({coords['lat']:.4f}, {coords['lon']:.4f})")
            logger.info(f"   Provider: {provider} (confidence: {coords['confidence']:.2f})")
            if provider == 'google' and 'place_id' in coords:
                logger.info(f"   Place ID: {coords['place_id']}")
        else:
            logger.info(f"❌ {name} - FAILED")

    logger.info("=" * 80)
    logger.info("Test complete!")

    # Show cost summary
    stats = results['statistics']
    logger.info("\n💰 Cost Analysis:")
    logger.info(f"   Nominatim (FREE): {stats['nominatim']} entities")
    logger.info(f"   Google Maps (PAID): {stats['google']} entities")
    logger.info(f"   Cached: {stats['cached']} entities")
    logger.info(f"   Google cost this batch: ${stats['google_cost_usd']:.4f}")

    return results


if __name__ == '__main__':
    # Run tests
    # test_geocoding_with_sample_entities()  # Nominatim only
    test_hybrid_geocoding()  # Hybrid strategy (Nominatim + Google fallback)
