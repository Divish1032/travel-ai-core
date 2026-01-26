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
# Thailand Geographic Bounds
# =============================================================================

THAILAND_BOUNDS = {
    'min_lat': 5.0,
    'max_lat': 21.0,
    'min_lon': 97.0,
    'max_lon': 106.0
}

# Approximate city coordinates for validation
THAILAND_CITIES = {
    'bangkok': {'lat': 13.7, 'lon': 100.5, 'tolerance': 1.0},
    'chiang mai': {'lat': 18.8, 'lon': 98.9, 'tolerance': 1.0},
    'phuket': {'lat': 7.9, 'lon': 98.4, 'tolerance': 1.0},
    'pattaya': {'lat': 12.9, 'lon': 100.9, 'tolerance': 0.5},
    'krabi': {'lat': 8.1, 'lon': 98.9, 'tolerance': 1.0},
    'koh samui': {'lat': 9.5, 'lon': 100.0, 'tolerance': 0.5},
    'ayutthaya': {'lat': 14.4, 'lon': 100.6, 'tolerance': 0.5},
    'hua hin': {'lat': 12.6, 'lon': 99.9, 'tolerance': 0.5},
    'koh phangan': {'lat': 9.7, 'lon': 100.0, 'tolerance': 0.3},
    'pai': {'lat': 19.4, 'lon': 98.4, 'tolerance': 0.3}
}


# =============================================================================
# Initialize Nominatim Client
# =============================================================================

# Initialize with user agent (required by Nominatim)
geolocator = Nominatim(
    user_agent="TravelAI-ThailandDestinations/1.0 (educational-project)",
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

        # Build query: "{name}, {area}, {city}, Thailand"
        query_parts = [name]
        if area:
            query_parts.append(area)
        if city:
            query_parts.append(city)
        query_parts.append('Thailand')

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

    # Strategy 1: Full query with area
    if area:
        query = f"{name}, {area}, {city}, Thailand"
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
    query = f"{name}, {city}, Thailand"
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
        query = f"{city}, Thailand"
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
    expected_city: Optional[str] = None
) -> bool:
    """
    Validate that coordinates are within Thailand and optionally near expected city.

    Checks:
    1. Coordinates are within Thailand bounding box (lat 5-21, lon 97-106)
    2. If expected_city provided, coordinates are roughly near that city

    Args:
        lat: Latitude
        lon: Longitude
        expected_city: Optional city name for rough validation

    Returns:
        True if coordinates are valid, False otherwise

    Example:
        >>> validate_coordinates(13.7, 100.5, 'Bangkok')
        True
        >>> validate_coordinates(40.7, -74.0, 'Bangkok')  # New York coords
        False
    """
    # Check Thailand bounding box
    if not (THAILAND_BOUNDS['min_lat'] <= lat <= THAILAND_BOUNDS['max_lat']):
        logger.warning(f"Latitude {lat} outside Thailand bounds ({THAILAND_BOUNDS['min_lat']}-{THAILAND_BOUNDS['max_lat']})")
        return False

    if not (THAILAND_BOUNDS['min_lon'] <= lon <= THAILAND_BOUNDS['max_lon']):
        logger.warning(f"Longitude {lon} outside Thailand bounds ({THAILAND_BOUNDS['min_lon']}-{THAILAND_BOUNDS['max_lon']})")
        return False

    # If expected city provided, do rough validation
    if expected_city:
        city_key = expected_city.lower().strip()

        if city_key in THAILAND_CITIES:
            city_coords = THAILAND_CITIES[city_key]
            city_lat = city_coords['lat']
            city_lon = city_coords['lon']
            tolerance = city_coords['tolerance']

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
        logger.info(f"No cache file found, starting fresh")
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
            logger.info(f"  ✅ Found in cache")
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

        # Build query: "{name}, {area}, {city}, Thailand"
        query_parts = [name]
        if area:
            query_parts.append(area)
        if city:
            query_parts.append(city)
        query_parts.append('Thailand')

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
            logger.warning(f"Google Maps result missing coordinates")
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
    logger.info(f"⚠️  Nominatim confidence too low or failed, trying Google Maps fallback...")

    google_result = geocode_google(entity)

    if google_result:
        logger.info(f"✅ Using Google Maps result (PAID $0.005, confidence={google_result['confidence']:.2f})")
        return google_result

    # Both failed
    if nominatim_result:
        # Return low-confidence Nominatim result as last resort
        logger.warning(f"⚠️  Google Maps failed, returning low-confidence Nominatim result")
        return nominatim_result

    logger.error(f"❌ Both Nominatim and Google Maps failed")
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
            logger.info(f"No cache found, starting fresh")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        logger.info(f"🔄 Cache disabled - processing all entities fresh")

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
            logger.info(f"  ✅ Found in cache")
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
                    logger.warning(f"  ❌ Coordinates validation failed")
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
            logger.error(f"  ❌ Geocoding failed")
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
