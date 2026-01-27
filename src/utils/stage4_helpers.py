#!/usr/bin/env python3
"""
Stage 4 Helper Utilities

Helper functions for extracting and normalizing Stage 3 enrichment data
for Stage 4 vector indexing. Handles parsing of temporal_info, logistics_info,
practical_tips, and geospatial data.

Features:
- Duration parsing and normalization
- Transport mode extraction
- Fee extraction and conversion
- Geohash generation
- Temporal data extraction
- Confidence score extraction
"""

import re
import pygeohash as pgh
from typing import List, Dict, Any, Optional, Tuple
from src.utils.logging import get_logger

logger = get_logger(__name__)


def extract_duration_hours(temporal_info: Dict[str, Any]) -> Tuple[Optional[float], float]:
    """
    Extract typical_duration and convert to hours (normalized).

    Args:
        temporal_info: temporal_info dict from Stage 3 entity

    Returns:
        Tuple of (duration_hours, confidence)

    Example:
        >>> temporal_info = {"typical_duration": "2-3 hours", "confidence": "high"}
        >>> extract_duration_hours(temporal_info)
        (2.5, 0.9)
    """
    if not temporal_info:
        return None, 0.0

    duration_str = temporal_info.get('typical_duration', '')
    confidence_str = temporal_info.get('confidence', 'low')

    # Map confidence
    confidence_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
    confidence = confidence_map.get(confidence_str, 0.3)

    if not duration_str or duration_str == 'unknown':
        return None, confidence

    duration_str = duration_str.lower()

    # Pattern: "X-Y hours", "X hours", "X minutes", "X days"

    # Days
    if 'day' in duration_str:
        match = re.search(r'(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)?\s*days?', duration_str)
        if match:
            min_days = float(match.group(1))
            max_days = float(match.group(2)) if match.group(2) else min_days
            avg_days = (min_days + max_days) / 2
            return avg_days * 24.0, confidence

        match = re.search(r'(\d+\.?\d*)\s*days?', duration_str)
        if match:
            return float(match.group(1)) * 24.0, confidence

    # Hours
    if 'hour' in duration_str:
        match = re.search(r'(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)?\s*hours?', duration_str)
        if match:
            min_hours = float(match.group(1))
            max_hours = float(match.group(2)) if match.group(2) else min_hours
            return (min_hours + max_hours) / 2, confidence

        match = re.search(r'(\d+\.?\d*)\s*hours?', duration_str)
        if match:
            return float(match.group(1)), confidence

    # Minutes
    if 'minute' in duration_str or 'min' in duration_str:
        match = re.search(r'(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)?\s*(?:minutes?|mins?)', duration_str)
        if match:
            min_mins = float(match.group(1))
            max_mins = float(match.group(2)) if match.group(2) else min_mins
            avg_mins = (min_mins + max_mins) / 2
            return avg_mins / 60.0, confidence

        match = re.search(r'(\d+\.?\d*)\s*(?:minutes?|mins?)', duration_str)
        if match:
            return float(match.group(1)) / 60.0, confidence

    # Half day / Full day
    if 'half day' in duration_str or 'half-day' in duration_str:
        return 4.0, confidence
    if 'full day' in duration_str or 'full-day' in duration_str:
        return 8.0, confidence

    return None, confidence


def extract_best_seasons(temporal_info: Dict[str, Any]) -> List[str]:
    """
    Extract best_seasons as list of strings.

    Args:
        temporal_info: temporal_info dict from Stage 3 entity

    Returns:
        List of season names

    Example:
        >>> temporal_info = {"best_seasons": ["winter", "spring"]}
        >>> extract_best_seasons(temporal_info)
        ['winter', 'spring']
    """
    if not temporal_info:
        return []

    seasons = temporal_info.get('best_seasons', [])
    if isinstance(seasons, list):
        return [s for s in seasons if s and s != 'unknown']
    elif isinstance(seasons, str):
        # Parse comma-separated string
        return [s.strip() for s in seasons.split(',') if s.strip() and s.strip() != 'unknown']

    return []


def extract_best_times(temporal_info: Dict[str, Any]) -> List[str]:
    """
    Extract best_times_of_day as list of strings.

    Args:
        temporal_info: temporal_info dict from Stage 3 entity

    Returns:
        List of time period names

    Example:
        >>> temporal_info = {"best_times_of_day": ["morning", "afternoon"]}
        >>> extract_best_times(temporal_info)
        ['morning', 'afternoon']
    """
    if not temporal_info:
        return []

    times = temporal_info.get('best_times_of_day', [])
    if isinstance(times, list):
        return [t for t in times if t and t != 'unknown']
    elif isinstance(times, str):
        # Parse comma-separated string
        return [t.strip() for t in times.split(',') if t.strip() and t.strip() != 'unknown']

    return []


def extract_transport_modes(logistics_info: Dict[str, Any]) -> List[str]:
    """
    Extract transport_options as list of mode names.

    Args:
        logistics_info: logistics_info dict from Stage 3 entity

    Returns:
        List of transport mode names

    Example:
        >>> logistics_info = {"transport_options": ["BTS", "taxi", "walking"]}
        >>> extract_transport_modes(logistics_info)
        ['BTS', 'taxi', 'walking']
    """
    if not logistics_info:
        return []

    transport = logistics_info.get('transport_options', [])
    if isinstance(transport, list):
        return [t for t in transport if t and t != 'unknown']
    elif isinstance(transport, str):
        # Parse comma-separated string
        return [t.strip() for t in transport.split(',') if t.strip() and t.strip() != 'unknown']

    return []


def extract_booking_required(logistics_info: Dict[str, Any]) -> Tuple[bool, float]:
    """
    Extract booking_required as boolean with confidence.

    Args:
        logistics_info: logistics_info dict from Stage 3 entity

    Returns:
        Tuple of (booking_required, confidence)

    Example:
        >>> logistics_info = {"booking_required": "yes", "confidence": "high"}
        >>> extract_booking_required(logistics_info)
        (True, 0.9)
    """
    if not logistics_info:
        return False, 0.0

    booking_str = logistics_info.get('booking_required', 'unknown')
    confidence_str = logistics_info.get('confidence', 'low')

    # Map confidence
    confidence_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
    confidence = confidence_map.get(confidence_str, 0.3)

    if isinstance(booking_str, bool):
        return booking_str, confidence

    if isinstance(booking_str, str):
        booking_str = booking_str.lower()
        if booking_str in ['yes', 'required', 'true', 'recommended']:
            return True, confidence
        elif booking_str in ['no', 'not required', 'false', 'walk-in']:
            return False, confidence

    return False, confidence


def extract_wheelchair_accessible(logistics_info: Dict[str, Any]) -> Tuple[bool, float]:
    """
    Extract wheelchair_accessible as boolean with confidence.

    Args:
        logistics_info: logistics_info dict from Stage 3 entity

    Returns:
        Tuple of (accessible, confidence)

    Example:
        >>> logistics_info = {"accessibility": "wheelchair accessible", "confidence": "medium"}
        >>> extract_wheelchair_accessible(logistics_info)
        (True, 0.6)
    """
    if not logistics_info:
        return False, 0.0

    accessibility_str = logistics_info.get('accessibility', 'unknown')
    confidence_str = logistics_info.get('confidence', 'low')

    # Map confidence
    confidence_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
    confidence = confidence_map.get(confidence_str, 0.3)

    if isinstance(accessibility_str, bool):
        return accessibility_str, confidence

    if isinstance(accessibility_str, str):
        accessibility_str = accessibility_str.lower()
        if 'wheelchair' in accessibility_str and 'accessible' in accessibility_str:
            return True, confidence
        elif 'not accessible' in accessibility_str or 'no wheelchair' in accessibility_str:
            return False, confidence

    return False, confidence


def extract_entrance_fee(practical_tips: Dict[str, Any]) -> Tuple[Optional[int], float]:
    """
    Extract entrance_fee and convert to THB (integer).

    Args:
        practical_tips: practical_tips dict from Stage 3 entity

    Returns:
        Tuple of (fee_thb, confidence)

    Example:
        >>> practical_tips = {"entrance_fee": "500 THB", "confidence": "high"}
        >>> extract_entrance_fee(practical_tips)
        (500, 0.9)
    """
    if not practical_tips:
        return None, 0.0

    fee_str = practical_tips.get('entrance_fee', '')
    confidence_str = practical_tips.get('confidence', 'low')

    # Map confidence
    confidence_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
    confidence = confidence_map.get(confidence_str, 0.3)

    if not fee_str or fee_str.lower() in ['free', 'unknown', 'n/a']:
        if fee_str.lower() == 'free':
            return 0, confidence
        return None, confidence

    if isinstance(fee_str, (int, float)):
        return int(fee_str), confidence

    # Parse string like "500 THB", "500-700 THB", "$15", etc.
    fee_str = str(fee_str).lower()

    # THB
    match = re.search(r'(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)?\s*(?:thb|baht)', fee_str)
    if match:
        min_fee = float(match.group(1))
        max_fee = float(match.group(2)) if match.group(2) else min_fee
        avg_fee = (min_fee + max_fee) / 2
        return int(avg_fee), confidence

    # USD (convert to THB, ~35 THB per USD)
    match = re.search(r'\$\s*(\d+\.?\d*)\s*-?\s*(\d+\.?\d*)?', fee_str)
    if match:
        min_usd = float(match.group(1))
        max_usd = float(match.group(2)) if match.group(2) else min_usd
        avg_usd = (min_usd + max_usd) / 2
        return int(avg_usd * 35), confidence

    # Just a number
    match = re.search(r'(\d+\.?\d*)', fee_str)
    if match:
        return int(float(match.group(1))), confidence

    return None, confidence


def generate_geohash(lat: float, lon: float, precision: int = 7) -> str:
    """
    Generate geohash from coordinates for spatial indexing.

    Args:
        lat: Latitude
        lon: Longitude
        precision: Geohash precision (default: 7, ~150m)

    Returns:
        Geohash string

    Example:
        >>> generate_geohash(13.7563, 100.5018)
        'w4rqqh8'
    """
    try:
        return pgh.encode(lat, lon, precision=precision)
    except Exception as e:
        logger.warning(f"Failed to generate geohash for ({lat}, {lon}): {e}")
        return ""


def generate_geohash_region(lat: float, lon: float, precision: int = 4) -> str:
    """
    Generate region-level geohash (lower precision for broader area search).

    Args:
        lat: Latitude
        lon: Longitude
        precision: Geohash precision (default: 4, ~20km)

    Returns:
        Geohash string

    Example:
        >>> generate_geohash_region(13.7563, 100.5018)
        'w4rq'
    """
    try:
        return pgh.encode(lat, lon, precision=precision)
    except Exception as e:
        logger.warning(f"Failed to generate region geohash for ({lat}, {lon}): {e}")
        return ""


def extract_enhanced_rating(consensus: Dict[str, Any]) -> Tuple[Optional[float], float]:
    """
    Extract enhanced_rating and confidence from consensus.

    Falls back to avg_rating if enhanced_rating not available.

    Args:
        consensus: consensus dict from Stage 3 entity

    Returns:
        Tuple of (rating, confidence)

    Example:
        >>> consensus = {"enhanced_rating": 4.8, "confidence": "high"}
        >>> extract_enhanced_rating(consensus)
        (4.8, 0.9)
    """
    if not consensus:
        return None, 0.0

    # Try enhanced_rating first
    enhanced_rating = consensus.get('enhanced_rating')
    if enhanced_rating is not None:
        # Check for confidence in enhanced_rating_metadata
        metadata = consensus.get('enhanced_rating_metadata', {})
        confidence_str = metadata.get('confidence', 'medium')

        confidence_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
        confidence = confidence_map.get(confidence_str, 0.6)

        return float(enhanced_rating), confidence

    # Fallback to avg_rating
    avg_rating = consensus.get('avg_rating')
    if avg_rating is not None:
        # Lower confidence for fallback
        return float(avg_rating), 0.5

    return None, 0.0


def extract_popularity_score(entity: Dict[str, Any]) -> Optional[float]:
    """
    Extract popularity_score from entity.

    Args:
        entity: Stage 3 canonical entity

    Returns:
        Popularity score (0.0-1.0) or None

    Example:
        >>> entity = {"popularity_score": 0.85}
        >>> extract_popularity_score(entity)
        0.85
    """
    score = entity.get('popularity_score')
    if score is not None and isinstance(score, (int, float)):
        return float(score)
    return None


def extract_freshness_score(entity: Dict[str, Any]) -> Optional[float]:
    """
    Extract freshness_score from entity.

    Args:
        entity: Stage 3 canonical entity

    Returns:
        Freshness score (0.0-1.0) or None

    Example:
        >>> entity = {"freshness_score": 0.92}
        >>> extract_freshness_score(entity)
        0.92
    """
    score = entity.get('freshness_score')
    if score is not None and isinstance(score, (int, float)):
        return float(score)
    return None


def get_s3_key(entity: Dict[str, Any]) -> str:
    """
    Generate S3 key for full entity retrieval.

    Args:
        entity: Stage 3 canonical entity

    Returns:
        S3 key path

    Example:
        >>> entity = {"entity_id": "restaurant_bangkok_001"}
        >>> get_s3_key(entity)
        'stage3/canonical-entities/restaurant_bangkok_001.json'
    """
    entity_id = entity.get('entity_id', 'unknown')
    return f"stage3/canonical-entities/{entity_id}.json"


if __name__ == '__main__':
    """
    Test helper functions with sample data.
    """
    logger.info("=" * 80)
    logger.info("TESTING STAGE 4 HELPER FUNCTIONS")
    logger.info("=" * 80)

    # Test 1: Duration extraction
    logger.info("\n📏 Test 1: Duration Extraction")
    test_cases = [
        {"typical_duration": "2-3 hours", "confidence": "high"},
        {"typical_duration": "45 minutes", "confidence": "medium"},
        {"typical_duration": "half day", "confidence": "low"},
        {"typical_duration": "1-2 days", "confidence": "high"},
    ]
    for case in test_cases:
        hours, conf = extract_duration_hours(case)
        logger.info(f"  {case['typical_duration']:20s} → {hours} hours (confidence: {conf})")

    # Test 2: Fee extraction
    logger.info("\n💰 Test 2: Entrance Fee Extraction")
    test_cases = [
        {"entrance_fee": "500 THB", "confidence": "high"},
        {"entrance_fee": "free", "confidence": "high"},
        {"entrance_fee": "$15", "confidence": "medium"},
        {"entrance_fee": "200-300 baht", "confidence": "low"},
    ]
    for case in test_cases:
        fee, conf = extract_entrance_fee(case)
        logger.info(f"  {case['entrance_fee']:20s} → {fee} THB (confidence: {conf})")

    # Test 3: Geohash generation
    logger.info("\n🗺️  Test 3: Geohash Generation")
    coords = [
        (13.7563, 100.5018, "Bangkok"),
        (18.7883, 98.9853, "Chiang Mai"),
        (7.8804, 98.3923, "Phuket"),
    ]
    for lat, lon, name in coords:
        geohash = generate_geohash(lat, lon)
        region = generate_geohash_region(lat, lon)
        logger.info(f"  {name:15s} ({lat:.4f}, {lon:.4f}) → geohash: {geohash}, region: {region}")

    # Test 4: Transport modes
    logger.info("\n🚗 Test 4: Transport Mode Extraction")
    test_cases = [
        {"transport_options": ["BTS", "taxi", "walking"]},
        {"transport_options": "MRT, bus, tuk-tuk"},
    ]
    for case in test_cases:
        modes = extract_transport_modes(case)
        logger.info(f"  {case['transport_options']} → {modes}")

    # Test 5: Booking required
    logger.info("\n📅 Test 5: Booking Required Extraction")
    test_cases = [
        {"booking_required": "yes", "confidence": "high"},
        {"booking_required": "no", "confidence": "medium"},
        {"booking_required": "recommended", "confidence": "high"},
    ]
    for case in test_cases:
        required, conf = extract_booking_required(case)
        logger.info(f"  {case['booking_required']:15s} → {required} (confidence: {conf})")

    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL TESTS COMPLETED")
    logger.info("=" * 80)
