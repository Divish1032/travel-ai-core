"""
Stage 3 Entity Enrichment

Adds temporal, logistics, and computed fields to canonical entities.
These fields were removed from Stage 2 prompts (Phase 1 optimization) and
are now aggregated/computed in Stage 3.

Features:
- Temporal consensus aggregation (best_time, visit_duration, seasonal_notes)
- Logistics consensus aggregation (transport, accessibility, booking)
- Computed metrics (popularity_score, data_freshness, mention_trend)
- Spatial relationships (nearby entities, walkability - future)

Usage:
    from src.processors.stage3_enrichment import enrich_canonical_entity

    enriched = enrich_canonical_entity(canonical_entity)
"""

from typing import Dict, Any, List, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timezone
import re
from statistics import mean, mode

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Temporal Consensus Aggregation
# =============================================================================

def aggregate_temporal_info(experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate temporal information across all experiences.

    Extracts and consolidates:
    - best_time_to_visit (seasons, times of day)
    - visit_duration (typical time spent)
    - seasonal_notes (crowding, weather, closures)

    Args:
        experiences: List of EntityExperience dicts

    Returns:
        Dict with aggregated temporal information:
        {
            'best_seasons': ['november-february', 'shoulder_season'],
            'best_times_of_day': ['early_morning', 'sunset'],
            'typical_duration': '2-3 hours',
            'duration_range': {'min': '1 hour', 'max': '4 hours'},
            'seasonal_notes': ['crowded in summer', 'closed mondays'],
            'confidence': 0.8
        }
    """
    # Collectors
    seasons = []
    times_of_day = []
    durations = []
    seasonal_notes = []

    for exp in experiences:
        entity_data = exp.get('entity', {})

        # Collect best_time_to_visit
        if 'best_time_to_visit' in entity_data:
            best_times = entity_data['best_time_to_visit']
            if isinstance(best_times, list):
                seasons.extend(best_times)
            elif isinstance(best_times, str):
                seasons.append(best_times)

        # Collect time_of_day
        if 'time_of_day' in entity_data:
            time_of_day = entity_data['time_of_day']
            if time_of_day:
                times_of_day.append(time_of_day)

        # Collect visit_duration
        if 'visit_duration' in entity_data:
            duration = entity_data['visit_duration']
            if duration:
                durations.append(duration)

        # Collect seasonal_notes
        if 'seasonal_notes' in entity_data:
            notes = entity_data['seasonal_notes']
            if notes:
                seasonal_notes.append(notes)

    # Aggregate
    result = {}

    # Best seasons (most mentioned)
    if seasons:
        season_counts = Counter(seasons)
        result['best_seasons'] = [
            season for season, count in season_counts.most_common(3)
        ]

    # Best times of day (most mentioned)
    if times_of_day:
        time_counts = Counter(times_of_day)
        result['best_times_of_day'] = [
            time for time, count in time_counts.most_common(2)
        ]

    # Typical duration (most common)
    if durations:
        # Try to find most common duration
        duration_counts = Counter(durations)
        result['typical_duration'] = duration_counts.most_common(1)[0][0]

        # Add range if multiple durations
        if len(set(durations)) > 1:
            result['duration_range'] = {
                'min': min(durations, key=lambda d: _parse_duration_to_minutes(d)),
                'max': max(durations, key=lambda d: _parse_duration_to_minutes(d))
            }

    # Seasonal notes (unique notes)
    if seasonal_notes:
        unique_notes = list(set(seasonal_notes))
        result['seasonal_notes'] = unique_notes[:5]  # Top 5

    # Calculate confidence based on data availability
    fields_present = sum([
        bool(seasons),
        bool(times_of_day),
        bool(durations),
        bool(seasonal_notes)
    ])
    result['confidence'] = min(0.9, (fields_present / 4) * len(experiences) / 10)

    return result if result else None


def _parse_duration_to_minutes(duration_str: str) -> int:
    """
    Parse duration string to minutes for comparison.

    Examples:
        "2-3 hours" -> 150 (average)
        "half day" -> 240
        "30 minutes" -> 30
    """
    duration_lower = duration_str.lower()

    # Handle ranges
    if '-' in duration_lower:
        parts = duration_lower.split('-')
        try:
            low = int(re.search(r'\d+', parts[0]).group())
            high = int(re.search(r'\d+', parts[1]).group())
            avg = (low + high) / 2

            # Check unit
            if 'hour' in duration_lower:
                return int(avg * 60)
            else:
                return int(avg)
        except:
            pass

    # Handle specific patterns
    if 'half day' in duration_lower or '4-5 hour' in duration_lower:
        return 240
    if 'full day' in duration_lower or '6-8 hour' in duration_lower:
        return 420
    if 'quick' in duration_lower or '15-30 min' in duration_lower:
        return 20

    # Extract number
    match = re.search(r'(\d+)', duration_lower)
    if match:
        num = int(match.group(1))
        if 'hour' in duration_lower:
            return num * 60
        else:
            return num

    return 120  # Default 2 hours


# =============================================================================
# Logistics Consensus Aggregation
# =============================================================================

def aggregate_logistics_info(experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate logistics information across all experiences.

    Extracts and consolidates:
    - transport_access (how to get there)
    - accessibility (physical access)
    - booking_info (reservation requirements)

    Args:
        experiences: List of EntityExperience dicts

    Returns:
        Dict with aggregated logistics:
        {
            'transport_options': ['Metro line 4', 'Bus 15', 'Taxi 10 min'],
            'accessibility_features': ['wheelchair accessible', 'elevator available'],
            'booking_required': True,
            'booking_lead_time': '1 week ahead',
            'booking_notes': ['book online', 'walk-ins available after 2pm'],
            'confidence': 0.7
        }
    """
    # Collectors
    transport_mentions = []
    accessibility_mentions = []
    booking_mentions = []

    for exp in experiences:
        entity_data = exp.get('entity', {})

        # Collect transport_access
        if 'transport_access' in entity_data:
            transport = entity_data['transport_access']
            if transport:
                transport_mentions.append(transport)

        # Collect accessibility
        if 'accessibility' in entity_data:
            access = entity_data['accessibility']
            if access:
                accessibility_mentions.append(access)

        # Collect booking_info
        if 'booking_info' in entity_data:
            booking = entity_data['booking_info']
            if booking:
                booking_mentions.append(booking)

    result = {}

    # Transport options (unique mentions)
    if transport_mentions:
        result['transport_options'] = list(set(transport_mentions))[:5]

    # Accessibility features (unique mentions)
    if accessibility_mentions:
        result['accessibility_features'] = list(set(accessibility_mentions))[:5]

    # Booking information
    if booking_mentions:
        # Determine if booking is required
        booking_required_keywords = ['required', 'must book', 'advance booking', 'book ahead']
        booking_required = any(
            any(keyword in mention.lower() for keyword in booking_required_keywords)
            for mention in booking_mentions
        )
        result['booking_required'] = booking_required

        # Extract lead time
        lead_time_pattern = re.compile(r'(\d+)\s*(day|week|month)', re.IGNORECASE)
        for mention in booking_mentions:
            match = lead_time_pattern.search(mention)
            if match:
                result['booking_lead_time'] = f"{match.group(1)} {match.group(2)}s ahead"
                break

        result['booking_notes'] = list(set(booking_mentions))[:3]

    # Calculate confidence
    fields_present = sum([
        bool(transport_mentions),
        bool(accessibility_mentions),
        bool(booking_mentions)
    ])
    result['confidence'] = min(0.9, (fields_present / 3) * len(experiences) / 10)

    return result if result else None


# =============================================================================
# Computed Metrics
# =============================================================================

def calculate_popularity_score(canonical_entity: Dict[str, Any]) -> float:
    """
    Calculate popularity score based on mentions across videos.

    Normalized 0-1 score considering:
    - Total mentions
    - Unique source videos
    - Recency of mentions

    Args:
        canonical_entity: Canonical entity dict

    Returns:
        Popularity score (0.0-1.0)
    """
    total_mentions = canonical_entity.get('total_mentions', 0)

    # Get unique source videos
    experiences = canonical_entity.get('experiences', [])
    unique_videos = set()
    for exp in experiences:
        provenance = exp.get('provenance', {})
        video_id = provenance.get('source_video_id')
        if video_id:
            unique_videos.add(video_id)

    unique_video_count = len(unique_videos)

    # Simple popularity score: weighted combination
    # More mentions = more popular
    # More unique videos = more reliable
    mention_score = min(1.0, total_mentions / 20)  # Cap at 20 mentions = 1.0
    video_score = min(1.0, unique_video_count / 10)  # Cap at 10 videos = 1.0

    # Weighted: 60% mentions, 40% unique videos
    popularity = (0.6 * mention_score) + (0.4 * video_score)

    return round(popularity, 3)


def calculate_data_freshness(canonical_entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate data freshness metrics.

    Args:
        canonical_entity: Canonical entity dict

    Returns:
        Dict with freshness info:
        {
            'most_recent_mention': '2025-11-15',
            'oldest_mention': '2024-06-10',
            'days_since_last_mention': 45,
            'freshness_score': 0.85
        }
    """
    experiences = canonical_entity.get('experiences', [])

    if not experiences:
        return {
            'most_recent_mention': None,
            'oldest_mention': None,
            'days_since_last_mention': None,
            'freshness_score': 0.0
        }

    # Extract dates
    dates = []
    for exp in experiences:
        provenance = exp.get('provenance', {})
        processed_at = provenance.get('processed_at')
        if processed_at:
            try:
                if isinstance(processed_at, str):
                    date = datetime.fromisoformat(processed_at.replace('Z', '+00:00'))
                else:
                    date = processed_at
                dates.append(date)
            except:
                pass

    if not dates:
        return {
            'most_recent_mention': None,
            'oldest_mention': None,
            'days_since_last_mention': None,
            'freshness_score': 0.5
        }

    most_recent = max(dates)
    oldest = min(dates)
    now = datetime.now(timezone.utc)

    days_since_last = (now - most_recent).days

    # Freshness score: decays over time
    # 0-30 days = 1.0
    # 30-90 days = 0.8
    # 90-180 days = 0.6
    # 180-365 days = 0.4
    # 365+ days = 0.2
    if days_since_last <= 30:
        freshness_score = 1.0
    elif days_since_last <= 90:
        freshness_score = 0.8
    elif days_since_last <= 180:
        freshness_score = 0.6
    elif days_since_last <= 365:
        freshness_score = 0.4
    else:
        freshness_score = 0.2

    return {
        'most_recent_mention': most_recent.strftime('%Y-%m-%d'),
        'oldest_mention': oldest.strftime('%Y-%m-%d'),
        'days_since_last_mention': days_since_last,
        'freshness_score': freshness_score
    }


# =============================================================================
# Main Enrichment Function
# =============================================================================

def enrich_canonical_entity(canonical_entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add all enriched fields to a canonical entity.

    Adds:
    - temporal_info: Aggregated temporal data
    - logistics_info: Aggregated logistics data
    - popularity_score: Computed popularity
    - data_freshness: Recency metrics

    Args:
        canonical_entity: Canonical entity dict from Stage 3

    Returns:
        Enriched canonical entity with new fields
    """
    experiences = canonical_entity.get('experiences', [])

    if not experiences:
        logger.debug(f"Entity {canonical_entity.get('entity_id', 'unknown')} has no experiences, skipping enrichment")
        return canonical_entity

    # 1. Aggregate temporal information
    temporal_info = aggregate_temporal_info(experiences)
    if temporal_info:
        canonical_entity['temporal_info'] = temporal_info
        logger.debug(f"Added temporal_info with confidence {temporal_info.get('confidence', 0):.2f}")

    # 2. Aggregate logistics information
    logistics_info = aggregate_logistics_info(experiences)
    if logistics_info:
        canonical_entity['logistics_info'] = logistics_info
        logger.debug(f"Added logistics_info with confidence {logistics_info.get('confidence', 0):.2f}")

    # 3. Calculate popularity score
    popularity_score = calculate_popularity_score(canonical_entity)
    canonical_entity['popularity_score'] = popularity_score
    logger.debug(f"Calculated popularity_score: {popularity_score}")

    # 4. Calculate data freshness
    data_freshness = calculate_data_freshness(canonical_entity)
    canonical_entity['data_freshness'] = data_freshness
    logger.debug(f"Calculated data_freshness score: {data_freshness.get('freshness_score', 0)}")

    return canonical_entity


def batch_enrich_entities(canonical_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich multiple canonical entities in batch.

    Args:
        canonical_entities: List of canonical entity dicts

    Returns:
        List of enriched canonical entities
    """
    enriched = []

    for entity in canonical_entities:
        try:
            enriched_entity = enrich_canonical_entity(entity)
            enriched.append(enriched_entity)
        except Exception as e:
            logger.error(f"Failed to enrich entity {entity.get('entity_id', 'unknown')}: {e}")
            # Add un-enriched entity
            enriched.append(entity)

    logger.info(f"Enriched {len(enriched)} canonical entities")

    return enriched


# =============================================================================
# Statistics
# =============================================================================

def get_enrichment_statistics(canonical_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics about enrichment coverage.

    Args:
        canonical_entities: List of enriched canonical entities

    Returns:
        Dict with enrichment statistics
    """
    total = len(canonical_entities)

    with_temporal = sum(1 for e in canonical_entities if 'temporal_info' in e)
    with_logistics = sum(1 for e in canonical_entities if 'logistics_info' in e)
    with_popularity = sum(1 for e in canonical_entities if 'popularity_score' in e)
    with_freshness = sum(1 for e in canonical_entities if 'data_freshness' in e)

    # Average scores
    popularity_scores = [e.get('popularity_score', 0) for e in canonical_entities]
    freshness_scores = [e.get('data_freshness', {}).get('freshness_score', 0) for e in canonical_entities]

    return {
        'total_entities': total,
        'enrichment_coverage': {
            'temporal_info': {
                'count': with_temporal,
                'percentage': (with_temporal / total * 100) if total > 0 else 0
            },
            'logistics_info': {
                'count': with_logistics,
                'percentage': (with_logistics / total * 100) if total > 0 else 0
            },
            'popularity_score': {
                'count': with_popularity,
                'percentage': (with_popularity / total * 100) if total > 0 else 0
            },
            'data_freshness': {
                'count': with_freshness,
                'percentage': (with_freshness / total * 100) if total > 0 else 0
            }
        },
        'average_scores': {
            'popularity': round(mean(popularity_scores), 3) if popularity_scores else 0,
            'freshness': round(mean(freshness_scores), 3) if freshness_scores else 0
        }
    }
