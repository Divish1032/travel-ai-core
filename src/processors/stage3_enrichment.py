"""
Stage 3 Entity Enrichment

Adds temporal, logistics, and computed fields to canonical entities.
These fields were removed from Stage 2 prompts (Phase 1 optimization) and
are now aggregated/computed in Stage 3.

Features:
- Temporal consensus aggregation (best_time, visit_duration, seasonal_notes)
- Logistics consensus aggregation (transport, accessibility, booking)
- Computed metrics (popularity_score, data_freshness, mention_trend)
- LLM-based enrichment fallback for well-known entities (NEW)
- Hybrid data merging (transcript + LLM knowledge)
- Spatial relationships (nearby entities, walkability - future)

Usage:
    from src.processors.stage3_enrichment import enrich_canonical_entity

    enriched = enrich_canonical_entity(canonical_entity)
"""

from typing import Dict, Any, List, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timezone
import re
from statistics import mean

from src.utils.logging import get_logger

logger = get_logger(__name__)

# LLM enrichment is optional - import only when needed
_LLM_ENRICHMENT_AVAILABLE = False
try:
    from src.processors.llm_enrichment import (
        enrich_entity_with_llm,
        merge_enrichment_data,
        get_entity_fame_score,
        get_llm_enrichment_stats
    )
    _LLM_ENRICHMENT_AVAILABLE = True
except ImportError:
    logger.debug("LLM enrichment module not available, using transcript-only enrichment")


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

    Extracts dates from experiences to determine how fresh the data is.
    Dates can be in multiple locations:
    - experiences[].processed_at (canonical entity structure)
    - experiences[].provenance.processed_at (legacy/alternate structure)
    - entity-level provenance.created_at

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

    # Extract dates from multiple possible locations
    dates = []

    for exp in experiences:
        processed_at = None

        # Try direct processed_at first (canonical entity structure)
        if 'processed_at' in exp:
            processed_at = exp.get('processed_at')

        # Try provenance.processed_at (legacy structure)
        if not processed_at:
            provenance = exp.get('provenance', {})
            processed_at = provenance.get('processed_at')

        # Try extraction_date
        if not processed_at:
            processed_at = exp.get('extraction_date')

        if processed_at:
            try:
                if isinstance(processed_at, str):
                    # Handle various ISO formats
                    date_str = processed_at.replace('Z', '+00:00')
                    # Handle case where there's no timezone
                    if '+' not in date_str and '-' not in date_str[-6:]:
                        date_str = date_str + '+00:00'
                    date = datetime.fromisoformat(date_str)
                elif isinstance(processed_at, datetime):
                    date = processed_at
                else:
                    continue
                dates.append(date)
            except Exception as e:
                logger.debug(f"Failed to parse date '{processed_at}': {e}")
                continue

    # Fallback: Try entity-level provenance
    if not dates:
        entity_provenance = canonical_entity.get('provenance', {})
        created_at = entity_provenance.get('created_at')
        if created_at:
            try:
                if isinstance(created_at, str):
                    date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    date = created_at
                dates.append(date)
            except:
                pass

    if not dates:
        # No dates found - return default with medium freshness score
        return {
            'most_recent_mention': None,
            'oldest_mention': None,
            'days_since_last_mention': None,
            'freshness_score': 0.5
        }

    most_recent = max(dates)
    oldest = min(dates)
    now = datetime.now(timezone.utc)

    # Ensure dates are timezone-aware for comparison
    if most_recent.tzinfo is None:
        most_recent = most_recent.replace(tzinfo=timezone.utc)

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
        'oldest_mention': oldest.strftime('%Y-%m-%d') if oldest.tzinfo else oldest.strftime('%Y-%m-%d'),
        'days_since_last_mention': days_since_last,
        'freshness_score': freshness_score
    }


# =============================================================================
# Multi-Signal Rating Calculation
# =============================================================================

# Patterns to extract explicit ratings from transcript text
EXPLICIT_RATING_PATTERNS = [
    # X out of 10 patterns
    (r'(\d+(?:\.\d+)?)\s*(?:out of|/)\s*10', 10),
    (r"i(?:'d| would)?\s*(?:give|rate)\s*(?:it|this)?\s*(?:a|an)?\s*(\d+(?:\.\d+)?)\s*(?:out of|/)\s*10", 10),
    # X out of 5 patterns
    (r'(\d+(?:\.\d+)?)\s*(?:out of|/)\s*5\s*(?:stars?)?', 5),
    (r"i(?:'d| would)?\s*(?:give|rate)\s*(?:it|this)?\s*(?:a|an)?\s*(\d+(?:\.\d+)?)\s*(?:out of|/)\s*5", 5),
    # X stars patterns
    (r'(\d+(?:\.\d+)?)\s*stars?', 5),
    # Descriptive ratings
    (r'\b(five|5)\s*stars?\b', 5),
    (r'\b(four|4)\s*stars?\b', 5),
    (r'\b(three|3)\s*stars?\b', 5),
]

# Sentiment intensity words for enhanced sentiment scoring
STRONG_POSITIVE_WORDS = [
    'amazing', 'incredible', 'fantastic', 'outstanding', 'exceptional', 'perfect',
    'breathtaking', 'stunning', 'magnificent', 'spectacular', 'must-visit', 'must see',
    'best', 'favorite', 'favourite', 'loved', 'blown away', 'highly recommend'
]

MODERATE_POSITIVE_WORDS = [
    'great', 'good', 'nice', 'lovely', 'beautiful', 'enjoyed', 'recommend',
    'worth it', 'worthwhile', 'pleasant', 'wonderful'
]

STRONG_NEGATIVE_WORDS = [
    'terrible', 'awful', 'horrible', 'worst', 'disaster', 'avoid', 'waste of',
    'disappointed', 'disappointing', 'overrated', 'scam', 'rip-off', 'tourist trap'
]

MODERATE_NEGATIVE_WORDS = [
    'bad', 'not great', 'mediocre', 'underwhelming', 'crowded', 'overpriced',
    'skip', 'not worth'
]


def extract_explicit_ratings_from_text(text: str) -> List[float]:
    """
    Extract explicit numerical ratings from transcript text.

    Looks for patterns like:
    - "I'd give it 8/10"
    - "9 out of 10"
    - "4.5 stars"
    - "5 out of 5"

    Args:
        text: Experience text from transcript

    Returns:
        List of ratings normalized to 5-star scale
    """
    ratings = []
    text_lower = text.lower()

    for pattern, max_rating in EXPLICIT_RATING_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    value = float(match[0])
                elif match in ['five', 'four', 'three']:
                    value = {'five': 5, 'four': 4, 'three': 3}[match]
                else:
                    value = float(match)

                # Normalize to 5-star scale
                normalized = (value / max_rating) * 5.0
                # Clamp to valid range
                normalized = max(1.0, min(5.0, normalized))
                ratings.append(normalized)
            except (ValueError, IndexError):
                continue

    return ratings


def calculate_enhanced_sentiment_rating(text: str) -> Tuple[float, float]:
    """
    Calculate rating based on sentiment intensity, not just binary sentiment.

    Args:
        text: Experience text

    Returns:
        Tuple of (rating, confidence)
        - rating: 1.0-5.0 scale
        - confidence: 0.0-1.0 based on strength of signals
    """
    text_lower = text.lower()

    strong_positive_count = sum(1 for word in STRONG_POSITIVE_WORDS if word in text_lower)
    moderate_positive_count = sum(1 for word in MODERATE_POSITIVE_WORDS if word in text_lower)
    strong_negative_count = sum(1 for word in STRONG_NEGATIVE_WORDS if word in text_lower)
    moderate_negative_count = sum(1 for word in MODERATE_NEGATIVE_WORDS if word in text_lower)

    total_signals = (strong_positive_count + moderate_positive_count +
                     strong_negative_count + moderate_negative_count)

    if total_signals == 0:
        return 3.0, 0.2  # Neutral with low confidence

    # Calculate weighted score
    # Strong signals have more weight
    positive_score = (strong_positive_count * 2.0) + (moderate_positive_count * 1.0)
    negative_score = (strong_negative_count * 2.0) + (moderate_negative_count * 1.0)

    # Net sentiment
    net_sentiment = positive_score - negative_score
    max_possible = total_signals * 2.0  # If all signals were strong

    # Normalize to 1-5 scale
    # net_sentiment ranges from -max_possible to +max_possible
    # Map to 1-5 where 0 = 3
    if max_possible > 0:
        normalized = (net_sentiment / max_possible)  # -1 to +1
        rating = 3.0 + (normalized * 2.0)  # 1 to 5
        rating = max(1.0, min(5.0, rating))
    else:
        rating = 3.0

    # Confidence based on signal count
    confidence = min(1.0, total_signals / 5.0)  # Max confidence at 5+ signals

    return rating, confidence


def calculate_multi_signal_rating(
    canonical_entity: Dict[str, Any],
    llm_enrichment: Optional[Dict[str, Any]] = None,
    sentiment_based_rating: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calculate entity rating using multiple signals.

    Combines:
    1. Explicit transcript ratings ("I'd rate it 8/10")
    2. Enhanced sentiment analysis (intensity-aware)
    3. LLM known ratings (Google Maps, TripAdvisor)
    4. Existing consensus sentiment rating

    Args:
        canonical_entity: Canonical entity dict
        llm_enrichment: Optional LLM enrichment data with known_ratings
        sentiment_based_rating: Optional existing sentiment-based rating from consensus

    Returns:
        Dict with:
        {
            'rating': 4.2,           # Final weighted rating (1-5)
            'confidence': 0.75,       # Overall confidence
            'source_breakdown': {
                'explicit_transcript': {'rating': 4.5, 'weight': 0.4, 'count': 2},
                'sentiment_enhanced': {'rating': 4.0, 'weight': 0.3, 'confidence': 0.6},
                'llm_known': {'rating': 4.3, 'weight': 0.2, 'confidence': 0.8},
                'consensus_sentiment': {'rating': 3.8, 'weight': 0.1}
            }
        }
    """
    experiences = canonical_entity.get('experiences', [])
    source_breakdown = {}
    weighted_ratings = []

    # 1. Extract explicit ratings from transcripts (highest weight)
    explicit_ratings = []
    for exp in experiences:
        exp_text = exp.get('experience', '')
        ratings = extract_explicit_ratings_from_text(exp_text)
        explicit_ratings.extend(ratings)

    if explicit_ratings:
        explicit_avg = sum(explicit_ratings) / len(explicit_ratings)
        # Weight: 0.4 base + 0.1 bonus for multiple explicit ratings
        explicit_weight = min(0.5, 0.4 + (len(explicit_ratings) - 1) * 0.05)
        weighted_ratings.append((explicit_avg, explicit_weight))
        source_breakdown['explicit_transcript'] = {
            'rating': round(explicit_avg, 2),
            'weight': explicit_weight,
            'count': len(explicit_ratings)
        }

    # 2. Enhanced sentiment analysis (medium weight)
    sentiment_ratings = []
    sentiment_confidences = []
    for exp in experiences:
        exp_text = exp.get('experience', '')
        if exp_text:
            rating, confidence = calculate_enhanced_sentiment_rating(exp_text)
            sentiment_ratings.append(rating)
            sentiment_confidences.append(confidence)

    if sentiment_ratings:
        sentiment_avg = sum(sentiment_ratings) / len(sentiment_ratings)
        sentiment_conf = sum(sentiment_confidences) / len(sentiment_confidences)
        # Weight based on confidence
        sentiment_weight = 0.3 * sentiment_conf
        if sentiment_weight > 0:
            weighted_ratings.append((sentiment_avg, sentiment_weight))
            source_breakdown['sentiment_enhanced'] = {
                'rating': round(sentiment_avg, 2),
                'weight': round(sentiment_weight, 2),
                'confidence': round(sentiment_conf, 2)
            }

    # 3. LLM known ratings (medium-low weight for famous places)
    if llm_enrichment and 'known_ratings' in llm_enrichment:
        known_ratings = llm_enrichment['known_ratings']
        llm_rating = known_ratings.get('google_maps_rating')
        llm_confidence = known_ratings.get('rating_confidence', 0.5)

        if llm_rating and llm_confidence > 0.3:
            # Weight based on confidence (max 0.25 for highly confident)
            llm_weight = 0.25 * llm_confidence
            weighted_ratings.append((llm_rating, llm_weight))
            source_breakdown['llm_known'] = {
                'rating': round(llm_rating, 2),
                'weight': round(llm_weight, 2),
                'confidence': round(llm_confidence, 2),
                'review_volume': known_ratings.get('review_volume')
            }

    # 4. Existing consensus sentiment rating (lowest weight - fallback)
    if sentiment_based_rating and sentiment_based_rating > 0:
        consensus_weight = 0.15
        # Reduce weight if we have better signals
        if weighted_ratings:
            consensus_weight = 0.1
        weighted_ratings.append((sentiment_based_rating, consensus_weight))
        source_breakdown['consensus_sentiment'] = {
            'rating': round(sentiment_based_rating, 2),
            'weight': consensus_weight
        }

    # Calculate final weighted rating
    if weighted_ratings:
        total_weight = sum(w for _, w in weighted_ratings)
        if total_weight > 0:
            final_rating = sum(r * w for r, w in weighted_ratings) / total_weight
        else:
            final_rating = 3.0
    else:
        # No signals - default to neutral
        final_rating = 3.0

    # Calculate overall confidence
    # Higher if we have multiple agreeing signals
    if len(weighted_ratings) >= 3:
        confidence = 0.9
    elif len(weighted_ratings) == 2:
        confidence = 0.7
    elif len(weighted_ratings) == 1:
        confidence = 0.5
    else:
        confidence = 0.2

    # Boost confidence if signals agree (low variance)
    if len(weighted_ratings) >= 2:
        ratings_only = [r for r, _ in weighted_ratings]
        rating_variance = max(ratings_only) - min(ratings_only)
        if rating_variance < 0.5:
            confidence = min(1.0, confidence + 0.1)
        elif rating_variance > 1.5:
            confidence = max(0.3, confidence - 0.1)

    return {
        'rating': round(final_rating, 2),
        'confidence': round(confidence, 2),
        'source_breakdown': source_breakdown,
        'signal_count': len(weighted_ratings)
    }


# =============================================================================
# Main Enrichment Function
# =============================================================================

def enrich_canonical_entity(
    canonical_entity: Dict[str, Any],
    use_llm_fallback: bool = True,
    min_fame_score: float = 0.5,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Add all enriched fields to a canonical entity.

    Uses a hybrid approach:
    1. First, try to aggregate temporal/logistics from transcript experiences
    2. If transcript data is sparse/missing, fallback to LLM knowledge enrichment
    3. Merge LLM data with transcript data when both are available

    Adds:
    - temporal_info: Aggregated temporal data (transcript + LLM hybrid)
    - logistics_info: Aggregated logistics data (transcript + LLM hybrid)
    - practical_tips: LLM-inferred practical information (dress code, fees, hours)
    - popularity_score: Computed popularity
    - data_freshness: Recency metrics
    - enrichment_provenance: Source tracking (transcript_extracted/llm_inferred/hybrid)

    Args:
        canonical_entity: Canonical entity dict from Stage 3
        use_llm_fallback: Whether to use LLM enrichment when transcript data is sparse
        min_fame_score: Minimum entity fame score to attempt LLM enrichment (0.0-1.0)

    Returns:
        Enriched canonical entity with new fields
    """
    entity_name = canonical_entity.get('canonical_name', 'unknown')
    experiences = canonical_entity.get('experiences', [])

    # 1. Try to aggregate temporal information from transcripts
    temporal_info = aggregate_temporal_info(experiences) if experiences else None
    has_good_temporal = (
        temporal_info and
        temporal_info.get('confidence', 0) > 0.3 and
        len(temporal_info) > 1  # More than just 'confidence' key
    )

    if has_good_temporal:
        temporal_info['source'] = 'transcript_extracted'
        canonical_entity['temporal_info'] = temporal_info
        logger.debug(f"Added temporal_info from transcript with confidence {temporal_info.get('confidence', 0):.2f}")

    # 2. Try to aggregate logistics information from transcripts
    logistics_info = aggregate_logistics_info(experiences) if experiences else None
    has_good_logistics = (
        logistics_info and
        logistics_info.get('confidence', 0) > 0.3 and
        len(logistics_info) > 1  # More than just 'confidence' key
    )

    if has_good_logistics:
        logistics_info['source'] = 'transcript_extracted'
        canonical_entity['logistics_info'] = logistics_info
        logger.debug(f"Added logistics_info from transcript with confidence {logistics_info.get('confidence', 0):.2f}")

    # 3. LLM Fallback: If transcript data is sparse/missing, use LLM knowledge
    needs_llm_enrichment = (not has_good_temporal or not has_good_logistics)
    llm_enrichment = None  # Initialize for later use in rating calculation

    if needs_llm_enrichment and use_llm_fallback and _LLM_ENRICHMENT_AVAILABLE:
        try:
            llm_enrichment = enrich_entity_with_llm(
                canonical_entity,
                use_cache=use_cache,
                min_fame_score=min_fame_score
            )

            if llm_enrichment:
                # Merge LLM data with existing transcript data
                if not has_good_temporal and 'temporal_info' in llm_enrichment:
                    if temporal_info:
                        # Merge: transcript takes precedence
                        merged_temporal = merge_enrichment_data(
                            llm_enrichment,
                            {'temporal_info': temporal_info}
                        ).get('temporal_info', llm_enrichment['temporal_info'])
                        canonical_entity['temporal_info'] = merged_temporal
                    else:
                        canonical_entity['temporal_info'] = llm_enrichment['temporal_info']
                    logger.debug(f"Added temporal_info from LLM for '{entity_name}'")

                if not has_good_logistics and 'logistics_info' in llm_enrichment:
                    if logistics_info:
                        # Merge: transcript takes precedence
                        merged_logistics = merge_enrichment_data(
                            llm_enrichment,
                            {'logistics_info': logistics_info}
                        ).get('logistics_info', llm_enrichment['logistics_info'])
                        canonical_entity['logistics_info'] = merged_logistics
                    else:
                        canonical_entity['logistics_info'] = llm_enrichment['logistics_info']
                    logger.debug(f"Added logistics_info from LLM for '{entity_name}'")

                # Add practical tips (LLM only)
                if 'practical_tips' in llm_enrichment:
                    canonical_entity['practical_tips'] = llm_enrichment['practical_tips']

                # Track enrichment provenance
                canonical_entity['enrichment_provenance'] = llm_enrichment.get('provenance', {
                    'source': 'llm_inferred',
                    'transcript_mentions': len(experiences)
                })

        except Exception as e:
            logger.warning(f"LLM enrichment failed for '{entity_name}': {e}")

    # 4. Ensure temporal/logistics have at least empty structure with confidence
    if 'temporal_info' not in canonical_entity:
        canonical_entity['temporal_info'] = {'confidence': 0.0, 'source': 'none'}
    if 'logistics_info' not in canonical_entity:
        canonical_entity['logistics_info'] = {'confidence': 0.0, 'source': 'none'}

    # 5. Calculate popularity score
    popularity_score = calculate_popularity_score(canonical_entity)
    canonical_entity['popularity_score'] = popularity_score
    logger.debug(f"Calculated popularity_score: {popularity_score}")

    # 6. Calculate data freshness
    data_freshness = calculate_data_freshness(canonical_entity)
    canonical_entity['data_freshness'] = data_freshness
    logger.debug(f"Calculated data_freshness score: {data_freshness.get('freshness_score', 0)}")

    # 7. Calculate multi-signal rating
    # Get existing consensus sentiment rating if available
    consensus = canonical_entity.get('consensus', {})
    sentiment_based_rating = consensus.get('avg_rating')

    enhanced_rating = calculate_multi_signal_rating(
        canonical_entity,
        llm_enrichment=llm_enrichment,
        sentiment_based_rating=sentiment_based_rating
    )
    canonical_entity['enhanced_rating'] = enhanced_rating
    logger.debug(f"Calculated enhanced_rating: {enhanced_rating.get('rating', 0)} (confidence: {enhanced_rating.get('confidence', 0)})")

    return canonical_entity


def batch_enrich_entities(
    canonical_entities: List[Dict[str, Any]],
    use_llm_fallback: bool = True,
    min_fame_score: float = 0.5,
    max_llm_enrichments: int = 100,
    use_cache: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Enrich multiple canonical entities in batch.

    Uses hybrid approach:
    1. Aggregate temporal/logistics from transcript experiences
    2. Fallback to LLM enrichment for well-known entities without transcript data
    3. Track statistics on enrichment sources

    Args:
        canonical_entities: List of canonical entity dicts
        use_llm_fallback: Whether to use LLM enrichment when transcript data is sparse
        min_fame_score: Minimum entity fame score to attempt LLM enrichment
        max_llm_enrichments: Maximum number of LLM enrichment calls (cost control)

    Returns:
        Tuple of (enriched_entities, statistics)
    """
    enriched = []
    llm_enrichment_count = 0

    stats = {
        'total_entities': len(canonical_entities),
        'transcript_temporal': 0,
        'transcript_logistics': 0,
        'llm_temporal': 0,
        'llm_logistics': 0,
        'hybrid_temporal': 0,
        'hybrid_logistics': 0,
        'no_temporal': 0,
        'no_logistics': 0,
        'llm_tokens_used': 0,
        'llm_cost_usd': 0.0
    }

    for entity in canonical_entities:
        try:
            # Check if we've hit LLM limit
            should_use_llm = use_llm_fallback and llm_enrichment_count < max_llm_enrichments

            enriched_entity = enrich_canonical_entity(
                entity,
                use_llm_fallback=should_use_llm,
                min_fame_score=min_fame_score,
                use_cache=use_cache
            )

            # Track enrichment sources
            temporal = enriched_entity.get('temporal_info', {})
            logistics = enriched_entity.get('logistics_info', {})

            temporal_source = temporal.get('source', 'none')
            logistics_source = logistics.get('source', 'none')

            if temporal_source == 'transcript_extracted':
                stats['transcript_temporal'] += 1
            elif temporal_source == 'llm_inferred':
                stats['llm_temporal'] += 1
                llm_enrichment_count += 1
            elif temporal_source == 'hybrid':
                stats['hybrid_temporal'] += 1
                llm_enrichment_count += 1
            else:
                stats['no_temporal'] += 1

            if logistics_source == 'transcript_extracted':
                stats['transcript_logistics'] += 1
            elif logistics_source == 'llm_inferred':
                stats['llm_logistics'] += 1
            elif logistics_source == 'hybrid':
                stats['hybrid_logistics'] += 1
            else:
                stats['no_logistics'] += 1

            enriched.append(enriched_entity)

        except Exception as e:
            logger.error(f"Failed to enrich entity {entity.get('entity_id', 'unknown')}: {e}")
            enriched.append(entity)

    # Get LLM enrichment stats if available
    if _LLM_ENRICHMENT_AVAILABLE:
        try:
            llm_stats = get_llm_enrichment_stats()
            stats['llm_tokens_used'] = llm_stats.get('total_tokens_used', 0)
            stats['llm_cost_usd'] = llm_stats.get('total_cost_usd', 0.0)
        except Exception:
            pass

    # Log summary
    logger.info("✨ Batch enrichment complete:")
    logger.info(f"   Total entities: {stats['total_entities']}")
    logger.info(f"   Temporal - Transcript: {stats['transcript_temporal']}, LLM: {stats['llm_temporal']}, Hybrid: {stats['hybrid_temporal']}, None: {stats['no_temporal']}")
    logger.info(f"   Logistics - Transcript: {stats['transcript_logistics']}, LLM: {stats['llm_logistics']}, Hybrid: {stats['hybrid_logistics']}, None: {stats['no_logistics']}")
    if stats['llm_cost_usd'] > 0:
        logger.info(f"   LLM cost: ${stats['llm_cost_usd']:.4f}")

    return enriched, stats


# =============================================================================
# Statistics
# =============================================================================

def get_enrichment_statistics(canonical_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics about enrichment coverage.

    Args:
        canonical_entities: List of enriched canonical entities

    Returns:
        Dict with enrichment statistics including source breakdown
    """
    total = len(canonical_entities)

    with_temporal = sum(1 for e in canonical_entities if 'temporal_info' in e)
    with_logistics = sum(1 for e in canonical_entities if 'logistics_info' in e)
    with_popularity = sum(1 for e in canonical_entities if 'popularity_score' in e)
    with_freshness = sum(1 for e in canonical_entities if 'data_freshness' in e)
    with_practical_tips = sum(1 for e in canonical_entities if 'practical_tips' in e)

    # Source breakdown for temporal/logistics
    temporal_sources = defaultdict(int)
    logistics_sources = defaultdict(int)

    for entity in canonical_entities:
        temporal = entity.get('temporal_info', {})
        logistics = entity.get('logistics_info', {})

        temporal_source = temporal.get('source', 'none')
        logistics_source = logistics.get('source', 'none')

        temporal_sources[temporal_source] += 1
        logistics_sources[logistics_source] += 1

    # Average scores
    popularity_scores = [e.get('popularity_score', 0) for e in canonical_entities]
    freshness_scores = [e.get('data_freshness', {}).get('freshness_score', 0) for e in canonical_entities]

    # Average confidence for temporal/logistics
    temporal_confidences = [
        e.get('temporal_info', {}).get('confidence', 0)
        for e in canonical_entities
        if e.get('temporal_info', {}).get('confidence', 0) > 0
    ]
    logistics_confidences = [
        e.get('logistics_info', {}).get('confidence', 0)
        for e in canonical_entities
        if e.get('logistics_info', {}).get('confidence', 0) > 0
    ]

    return {
        'total_entities': total,
        'enrichment_coverage': {
            'temporal_info': {
                'count': with_temporal,
                'percentage': (with_temporal / total * 100) if total > 0 else 0,
                'sources': dict(temporal_sources),
                'avg_confidence': round(mean(temporal_confidences), 3) if temporal_confidences else 0
            },
            'logistics_info': {
                'count': with_logistics,
                'percentage': (with_logistics / total * 100) if total > 0 else 0,
                'sources': dict(logistics_sources),
                'avg_confidence': round(mean(logistics_confidences), 3) if logistics_confidences else 0
            },
            'practical_tips': {
                'count': with_practical_tips,
                'percentage': (with_practical_tips / total * 100) if total > 0 else 0
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
