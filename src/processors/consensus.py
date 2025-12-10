"""
Stage 3 Consensus: Calculate consensus metadata for canonical entities

Implements traveler profile bucketing and consensus calculation:
- Profile bucketing: Classify experiences into standard traveler profiles
- Sentiment distribution: Aggregate sentiment across experiences
- Cost information: Extract and normalize cost data
- Consensus scoring: Calculate agreement levels across sources

Usage:
    from src.processors.consensus import (
        classify_experience_profile,
        calculate_sentiment_distribution,
        extract_cost_info
    )

    # Classify experience profile
    experience = {
        'traveler_profile': {
            'traveler_type': 'solo',
            'budget_tier': 'budget',
            'travel_style': ['party', 'social']
        }
    }
    profile = classify_experience_profile(experience)
    # Returns: "solo_budget_party"

    # Calculate sentiment distribution
    experiences = [...]
    sentiment_dist = calculate_sentiment_distribution(experiences)
    # Returns: {'positive': 15, 'neutral': 3, 'negative': 1}

    # Extract cost information
    cost_info = extract_cost_info(experiences)
    # Returns: {'accommodation': {'min': 500, 'max': 1200, 'avg': 850}}
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
import re

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Profile Bucket Definitions
# =============================================================================

PROFILE_BUCKETS = {
    # Solo travelers
    "solo_budget_party": {
        "traveler_type": "solo",
        "budget_tier": "budget",
        "travel_style_includes": ["party", "social", "nightlife"]
    },
    "solo_budget_cultural": {
        "traveler_type": "solo",
        "budget_tier": "budget",
        "travel_style_includes": ["cultural", "history", "temples"]
    },
    "solo_budget_adventure": {
        "traveler_type": "solo",
        "budget_tier": "budget",
        "travel_style_includes": ["adventure", "hiking", "nature"]
    },
    "solo_midrange_adventure": {
        "traveler_type": "solo",
        "budget_tier": "mid-range",
        "travel_style_includes": ["adventure", "hiking", "nature"]
    },
    "solo_midrange_cultural": {
        "traveler_type": "solo",
        "budget_tier": "mid-range",
        "travel_style_includes": ["cultural", "history"]
    },
    "solo_luxury": {
        "traveler_type": "solo",
        "budget_tier": "luxury"
    },

    # Couples
    "couple_budget": {
        "traveler_type": "couple",
        "budget_tier": "budget"
    },
    "couple_midrange_romantic": {
        "traveler_type": "couple",
        "budget_tier": "mid-range",
        "travel_style_includes": ["romantic", "relaxed"]
    },
    "couple_midrange_adventure": {
        "traveler_type": "couple",
        "budget_tier": "mid-range",
        "travel_style_includes": ["adventure", "active"]
    },
    "couple_luxury": {
        "traveler_type": "couple",
        "budget_tier": "luxury"
    },

    # Families
    "family_budget": {
        "traveler_type": "family",
        "budget_tier": "budget"
    },
    "family_midrange": {
        "traveler_type": "family",
        "budget_tier": "mid-range"
    },
    "family_luxury": {
        "traveler_type": "family",
        "budget_tier": "luxury"
    },

    # Groups
    "group_party": {
        "traveler_type": "group",
        "travel_style_includes": ["party", "social", "nightlife"]
    },
    "group_adventure": {
        "traveler_type": "group",
        "travel_style_includes": ["adventure", "hiking"]
    },
    "group_cultural": {
        "traveler_type": "group",
        "travel_style_includes": ["cultural", "history"]
    },

    # Backpackers
    "backpacker_social": {
        "budget_tier": "budget",
        "travel_style_includes": ["social", "backpacker", "hostel"]
    },
    "backpacker_adventure": {
        "budget_tier": "budget",
        "travel_style_includes": ["adventure", "backpacker", "hiking"]
    },

    # Digital nomads
    "digital_nomad": {
        "traveler_type": "solo",
        "travel_style_includes": ["work", "remote", "digital nomad", "coworking"]
    }
}


# =============================================================================
# Profile Classification
# =============================================================================


def classify_experience_profile(experience: Dict[str, Any]) -> str:
    """
    Classify experience into a standard traveler profile bucket.

    Matches traveler_profile to predefined PROFILE_BUCKETS based on:
    - traveler_type (solo, couple, family, group)
    - budget_tier (budget, mid-range, luxury)
    - travel_style (list of style keywords)

    Args:
        experience: Experience dict with 'traveler_profile' key

    Returns:
        Profile bucket key (e.g., "solo_budget_party", "couple_luxury")
        If no match: "other_{type}_{budget}" or "other"

    Example:
        >>> exp = {
        ...     'traveler_profile': {
        ...         'traveler_type': 'solo',
        ...         'budget_tier': 'budget',
        ...         'travel_style': ['party', 'social', 'nightlife']
        ...     }
        ... }
        >>> classify_experience_profile(exp)
        'solo_budget_party'
    """
    traveler_profile = experience.get('traveler_profile', {})

    if not traveler_profile:
        return "other"

    traveler_type = traveler_profile.get('traveler_type', '').lower()
    budget_tier = traveler_profile.get('budget_tier', '').lower()
    travel_style = traveler_profile.get('travel_style', [])

    # Normalize travel_style to list of lowercase strings
    if isinstance(travel_style, str):
        travel_style = [travel_style]
    travel_style_lower = [style.lower() for style in travel_style]

    # Try to match to a profile bucket
    best_match = None
    best_score = 0

    for bucket_key, bucket_def in PROFILE_BUCKETS.items():
        score = 0

        # Check traveler_type match
        if 'traveler_type' in bucket_def:
            if bucket_def['traveler_type'] == traveler_type:
                score += 10
            else:
                continue  # Must match if specified

        # Check budget_tier match
        if 'budget_tier' in bucket_def:
            if bucket_def['budget_tier'] == budget_tier:
                score += 10
            else:
                continue  # Must match if specified

        # Check travel_style_includes
        if 'travel_style_includes' in bucket_def:
            required_styles = [s.lower() for s in bucket_def['travel_style_includes']]

            # Count how many required styles are present
            matches = sum(
                1 for req_style in required_styles
                if any(req_style in user_style for user_style in travel_style_lower)
            )

            if matches > 0:
                score += matches * 5
            else:
                continue  # Must have at least one matching style

        # Update best match
        if score > best_score:
            best_score = score
            best_match = bucket_key

    # Return best match or fallback
    if best_match:
        return best_match

    # Fallback: create generic profile key
    if traveler_type and budget_tier:
        return f"other_{traveler_type}_{budget_tier}"
    elif traveler_type:
        return f"other_{traveler_type}"
    elif budget_tier:
        return f"other_{budget_tier}"
    else:
        return "other"


# =============================================================================
# Sentiment Distribution
# =============================================================================


def calculate_sentiment_distribution(experiences: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Calculate sentiment distribution across experiences.

    Aggregates sentiment values from all experiences and returns counts.

    Args:
        experiences: List of experience dicts with 'experience' key containing
                    sentiment information

    Returns:
        Dict with sentiment counts:
        {
            'positive': int,
            'neutral': int,
            'negative': int,
            'mixed': int
        }

    Example:
        >>> experiences = [
        ...     {'experience': 'Great place!', 'traveler_profile': {...}},
        ...     {'experience': 'OK, nothing special', 'traveler_profile': {...}}
        ... ]
        >>> calculate_sentiment_distribution(experiences)
        {'positive': 1, 'neutral': 1, 'negative': 0, 'mixed': 0}
    """
    sentiment_counter = Counter()

    for exp in experiences:
        # Get sentiment from experience text (simple heuristic)
        # In practice, this would come from the entity extraction
        experience_text = exp.get('experience', '').lower()

        # Simple sentiment detection based on keywords
        # TODO: Replace with actual sentiment from entity extraction
        sentiment = _detect_sentiment_simple(experience_text)
        sentiment_counter[sentiment] += 1

    # Ensure all sentiments are present
    result = {
        'positive': sentiment_counter.get('positive', 0),
        'neutral': sentiment_counter.get('neutral', 0),
        'negative': sentiment_counter.get('negative', 0),
        'mixed': sentiment_counter.get('mixed', 0)
    }

    return result


def _detect_sentiment_simple(text: str) -> str:
    """
    Simple sentiment detection based on keywords.

    This is a placeholder - in production, sentiment should come from
    the entity extraction in Stage 2.

    Args:
        text: Experience text

    Returns:
        Sentiment: "positive", "negative", "neutral", or "mixed"
    """
    text_lower = text.lower()

    # Positive keywords
    positive_words = [
        'great', 'amazing', 'beautiful', 'love', 'best', 'wonderful',
        'fantastic', 'excellent', 'perfect', 'awesome', 'stunning',
        'incredible', 'must-visit', 'highly recommend', 'worth it'
    ]

    # Negative keywords
    negative_words = [
        'bad', 'terrible', 'worst', 'awful', 'disappointing', 'avoid',
        'waste', 'boring', 'overrated', 'crowded', 'dirty', 'expensive',
        'not worth', 'skip', 'underwhelming'
    ]

    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)

    if positive_count > 0 and negative_count > 0:
        return 'mixed'
    elif positive_count > negative_count:
        return 'positive'
    elif negative_count > positive_count:
        return 'negative'
    else:
        return 'neutral'


# =============================================================================
# Cost Information Extraction
# =============================================================================


def extract_cost_info(experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract and aggregate cost information from experiences.

    Parses cost mentions, normalizes currencies, and calculates ranges.

    Args:
        experiences: List of experience dicts

    Returns:
        Dict with cost information:
        {
            'overall': {
                'min': float,
                'max': float,
                'avg': float,
                'currency': str,
                'count': int
            },
            'by_type': {
                'accommodation': {...},
                'food': {...},
                'activity': {...}
            },
            'mentions': [list of raw cost strings]
        }

    Example:
        >>> experiences = [
        ...     {'experience': 'Hotel was 1000 baht', 'traveler_profile': {...}},
        ...     {'experience': 'Dinner cost 200 baht', 'traveler_profile': {...}}
        ... ]
        >>> cost_info = extract_cost_info(experiences)
        >>> cost_info['overall']['min']
        200
    """
    cost_mentions = []
    cost_values = []

    # Cost patterns
    # Matches: "500 baht", "$50", "1000 THB", "free", "expensive"
    cost_pattern = re.compile(
        r'(\d+[\d,]*\.?\d*)\s*(baht|thb|usd|dollar|euro|eur|\$|฿|€)',
        re.IGNORECASE
    )

    for exp in experiences:
        experience_text = exp.get('experience', '')

        # Find all cost mentions
        matches = cost_pattern.findall(experience_text)

        for amount_str, currency in matches:
            # Clean amount
            amount_str = amount_str.replace(',', '')

            try:
                amount = float(amount_str)

                # Normalize currency
                currency_lower = currency.lower()
                if currency_lower in ['baht', 'thb', '฿']:
                    normalized_currency = 'THB'
                elif currency_lower in ['usd', 'dollar', '$']:
                    normalized_currency = 'USD'
                    amount *= 35  # Convert to THB (approximate)
                elif currency_lower in ['euro', 'eur', '€']:
                    normalized_currency = 'EUR'
                    amount *= 38  # Convert to THB (approximate)
                else:
                    normalized_currency = 'THB'

                cost_mentions.append({
                    'amount': amount,
                    'currency': normalized_currency,
                    'original': f"{amount_str} {currency}"
                })
                cost_values.append(amount)

            except ValueError:
                continue

    # Calculate statistics
    if cost_values:
        result = {
            'overall': {
                'min': min(cost_values),
                'max': max(cost_values),
                'avg': sum(cost_values) / len(cost_values),
                'currency': 'THB',
                'count': len(cost_values)
            },
            'mentions': [m['original'] for m in cost_mentions]
        }
    else:
        result = {
            'overall': {
                'min': None,
                'max': None,
                'avg': None,
                'currency': 'THB',
                'count': 0
            },
            'mentions': []
        }

    return result


# =============================================================================
# Consensus Calculation
# =============================================================================


def calculate_consensus_metadata(canonical_entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate consensus metadata for a canonical entity.

    Aggregates information from all experiences:
    - Profile distribution (which traveler types visited)
    - Sentiment distribution (overall opinion)
    - Cost information (price ranges)
    - Consensus score (agreement level)

    Args:
        canonical_entity: Canonical entity dict from canonicalization

    Returns:
        Dict with consensus metadata:
        {
            'profile_distribution': {...},
            'sentiment_distribution': {...},
            'cost_info': {...},
            'consensus_score': float,
            'total_sources': int
        }

    Example:
        >>> canonical = {
        ...     'entity_id': 'attraction_bangkok_001',
        ...     'canonical_name': 'Wat Pho',
        ...     'experiences': [...]
        ... }
        >>> consensus = calculate_consensus_metadata(canonical)
        >>> consensus['profile_distribution']
        {'solo_budget_party': 5, 'couple_midrange': 3, ...}
    """
    experiences = canonical_entity.get('experiences', [])

    if not experiences:
        return {
            'profile_distribution': {},
            'sentiment_distribution': {'positive': 0, 'neutral': 0, 'negative': 0, 'mixed': 0},
            'cost_info': {'overall': {'min': None, 'max': None, 'avg': None, 'count': 0}},
            'consensus_score': 0.0,
            'total_sources': 0
        }

    # 1. Profile distribution
    profile_counter = Counter()
    for exp in experiences:
        profile = classify_experience_profile(exp)
        profile_counter[profile] += 1

    profile_distribution = dict(profile_counter.most_common())

    # 2. Sentiment distribution
    sentiment_distribution = calculate_sentiment_distribution(experiences)

    # 3. Cost information
    cost_info = extract_cost_info(experiences)

    # 4. Consensus score (0.0-1.0)
    # Higher score = more agreement across sources
    total_sources = len(experiences)

    # Calculate agreement based on sentiment
    sentiment_counts = list(sentiment_distribution.values())
    max_sentiment = max(sentiment_counts) if sentiment_counts else 0
    sentiment_consensus = max_sentiment / total_sources if total_sources > 0 else 0

    # Calculate agreement based on profiles
    profile_counts = list(profile_counter.values())
    max_profile = max(profile_counts) if profile_counts else 0
    profile_consensus = max_profile / total_sources if total_sources > 0 else 0

    # Average consensus
    consensus_score = (sentiment_consensus + profile_consensus) / 2

    return {
        'profile_distribution': profile_distribution,
        'sentiment_distribution': sentiment_distribution,
        'cost_info': cost_info,
        'consensus_score': consensus_score,
        'total_sources': total_sources,
        'dominant_profile': profile_counter.most_common(1)[0][0] if profile_counter else None,
        'dominant_sentiment': max(sentiment_distribution.items(), key=lambda x: x[1])[0]
    }


# =============================================================================
# Batch Consensus Calculation
# =============================================================================


def calculate_consensus_for_all(
    canonical_entities: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Calculate consensus metadata for all canonical entities.

    Args:
        canonical_entities: List of canonical entity dicts

    Returns:
        List of canonical entities with added 'consensus' field

    Example:
        >>> canonical_entities = [...]
        >>> enriched = calculate_consensus_for_all(canonical_entities)
        >>> enriched[0]['consensus']['consensus_score']
        0.85
    """
    logger.info(f"Calculating consensus metadata for {len(canonical_entities)} entities...")

    enriched_entities = []

    for entity in canonical_entities:
        # Calculate consensus
        consensus = calculate_consensus_metadata(entity)

        # Add consensus to entity
        enriched_entity = entity.copy()
        enriched_entity['consensus'] = consensus

        enriched_entities.append(enriched_entity)

    logger.info(f"✅ Consensus calculation complete for {len(enriched_entities)} entities")

    return enriched_entities


# =============================================================================
# Experience Aggregation by Profile
# =============================================================================


def aggregate_experiences_by_profile(experiences: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Group experiences by profile bucket and calculate consensus metrics.

    For each profile:
    - mention_count: Number of experiences from this profile
    - avg_rating: Average rating (inferred from sentiment)
    - sentiment_dist: Sentiment distribution
    - common_themes: Most frequent keywords
    - avg_cost: Average cost mentioned
    - confidence_score: Based on mention count

    Args:
        experiences: List of experience dicts

    Returns:
        Dict mapping profile keys to consensus metrics:
        {
            'solo_budget_party': {
                'mention_count': 5,
                'avg_rating': 4.2,
                'sentiment_dist': {'positive': 4, 'neutral': 1},
                'common_themes': ['nightlife', 'social', 'bars'],
                'avg_cost': 500.0,
                'confidence_score': 0.8
            },
            ...
        }

    Example:
        >>> experiences = [...]
        >>> profile_metrics = aggregate_experiences_by_profile(experiences)
        >>> profile_metrics['solo_budget_party']['avg_rating']
        4.2
    """
    # Group by profile
    profile_groups = defaultdict(list)

    for exp in experiences:
        profile = classify_experience_profile(exp)
        profile_groups[profile].append(exp)

    # Calculate metrics for each profile
    profile_metrics = {}

    for profile_key, profile_exps in profile_groups.items():
        # Mention count
        mention_count = len(profile_exps)

        # Calculate rating from sentiment
        sentiment_to_rating = {
            'positive': 5,
            'neutral': 3,
            'negative': 1,
            'mixed': 3
        }

        ratings = []
        sentiment_counter = Counter()

        for exp in profile_exps:
            exp_text = exp.get('experience', '').lower()
            sentiment = _detect_sentiment_simple(exp_text)
            sentiment_counter[sentiment] += 1
            ratings.append(sentiment_to_rating[sentiment])

        avg_rating = sum(ratings) / len(ratings) if ratings else 3.0

        # Extract common themes (use LLM for high-confidence profiles with 5+ mentions)
        if mention_count >= 5:
            # Use LLM for better theme quality
            try:
                common_themes = extract_themes_with_llm(profile_exps, max_themes=5)
            except Exception as e:
                logger.warning(f"LLM theme extraction failed for profile {profile_key}, falling back to keyword extraction: {e}")
                common_themes = extract_common_themes(profile_exps, top_n=5)
        else:
            # Use simple keyword extraction for low mention counts
            common_themes = extract_common_themes(profile_exps, top_n=5)

        # Calculate average cost
        costs = []
        for exp in profile_exps:
            exp_text = exp.get('experience', '')
            # Extract costs from text
            cost_pattern = re.compile(r'(\d+[\d,]*\.?\d*)\s*(baht|thb)', re.IGNORECASE)
            matches = cost_pattern.findall(exp_text)

            for amount_str, _ in matches:
                try:
                    amount = float(amount_str.replace(',', ''))
                    costs.append(amount)
                except ValueError:
                    continue

        avg_cost = sum(costs) / len(costs) if costs else None

        # Confidence score (based on mention count)
        # More mentions = higher confidence
        confidence_score = min(mention_count / 10.0, 1.0)  # Cap at 1.0

        profile_metrics[profile_key] = {
            'mention_count': mention_count,
            'avg_rating': avg_rating,
            'sentiment_dist': dict(sentiment_counter),
            'common_themes': common_themes,
            'avg_cost': avg_cost,
            'confidence_score': confidence_score
        }

    return profile_metrics


def extract_common_themes(experiences: List[Dict[str, Any]], top_n: int = 5) -> List[str]:
    """
    Extract common themes from experiences using keyword frequency.

    Extracts meaningful keywords, filters out stopwords, and returns top N.

    Args:
        experiences: List of experience dicts
        top_n: Number of top themes to return

    Returns:
        List of common theme keywords sorted by frequency

    Example:
        >>> experiences = [
        ...     {'experience': 'Great nightlife and social atmosphere'},
        ...     {'experience': 'Amazing nightlife scene with lots of bars'}
        ... ]
        >>> extract_common_themes(experiences, top_n=3)
        ['nightlife', 'social', 'bars']
    """
    # Stopwords to filter out
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'is', 'was', 'are', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
        'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'my', 'your',
        'his', 'her', 'its', 'our', 'their', 'very', 'really', 'just', 'so',
        'too', 'also', 'here', 'there', 'where', 'when', 'how', 'what', 'who'
    }

    # Collect all words
    word_counter = Counter()

    for exp in experiences:
        exp_text = exp.get('experience', '').lower()

        # Split into words
        words = re.findall(r'\b[a-z]{3,}\b', exp_text)

        for word in words:
            if word not in stopwords:
                word_counter[word] += 1

    # Return top N
    common_themes = [word for word, _ in word_counter.most_common(top_n)]

    return common_themes


# =============================================================================
# LLM-Based Theme Extraction (Optional Enhancement)
# =============================================================================

# Global cost tracking for LLM theme extraction
_THEME_EXTRACTION_TOKENS = 0
_THEME_EXTRACTION_COST = 0.0


def get_theme_extraction_stats() -> Dict[str, Any]:
    """
    Get cumulative theme extraction statistics.

    Returns:
        Dict with total_tokens_used and total_cost_usd
    """
    return {
        'total_tokens_used': _THEME_EXTRACTION_TOKENS,
        'total_cost_usd': _THEME_EXTRACTION_COST
    }


def reset_theme_extraction_stats() -> None:
    """Reset theme extraction statistics."""
    global _THEME_EXTRACTION_TOKENS, _THEME_EXTRACTION_COST
    _THEME_EXTRACTION_TOKENS = 0
    _THEME_EXTRACTION_COST = 0.0


def extract_themes_with_llm(
    experiences: List[Dict[str, Any]],
    max_themes: int = 5,
    max_retries: int = 3
) -> List[str]:
    """
    Extract themes from experiences using LLM (Gemini Flash).

    Only use for entities with 5+ experiences. Uses cheap Gemini Flash
    to extract high-quality themes that capture the essence of the entity.

    Args:
        experiences: List of experience dicts
        max_themes: Maximum number of themes to extract (3-5 recommended)
        max_retries: Maximum retry attempts

    Returns:
        List of theme keywords

    Example:
        >>> experiences = [
        ...     {'experience': 'Amazing nightlife with great bars and clubs'},
        ...     {'experience': 'Perfect for party lovers, cheap drinks'},
        ...     {'experience': 'Social atmosphere, met lots of backpackers'},
        ...     {'experience': 'Late night street food is incredible'},
        ...     {'experience': 'Best party destination in Thailand'}
        ... ]
        >>> themes = extract_themes_with_llm(experiences, max_themes=5)
        >>> themes
        ['nightlife', 'party', 'social', 'budget-friendly', 'backpacker']
    """
    global _THEME_EXTRACTION_TOKENS, _THEME_EXTRACTION_COST

    from src.utils.llm_client import extract_with_llm
    import json

    # Take up to 10 experiences for theme extraction (avoid huge prompts)
    sample_experiences = experiences[:10]

    # Build experience list
    experience_lines = []
    for i, exp in enumerate(sample_experiences, 1):
        exp_text = exp.get('experience', '').strip()
        if exp_text:
            # Truncate long experiences to keep prompt concise
            if len(exp_text) > 200:
                exp_text = exp_text[:200] + '...'
            experience_lines.append(f"{i}. {exp_text}")

    experiences_text = '\n'.join(experience_lines)

    # Create prompt
    prompt = f"""Summarize the common themes from these traveler experiences:

{experiences_text}

Extract {max_themes} key themes or keywords that capture the essence of this place/activity.
Focus on:
- What makes it unique or notable
- Who would enjoy it (e.g., families, backpackers, luxury travelers)
- Main activities or experiences
- Atmosphere or vibe

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "themes": ["theme1", "theme2", "theme3", ...]
}}

Response:"""

    # Call LLM
    llm_result = extract_with_llm(
        prompt=prompt,
        max_retries=max_retries,
        temperature=0.3,  # Some creativity, but not too much
        max_tokens=150     # Short response expected
    )

    if not llm_result['success']:
        logger.warning(f"LLM theme extraction failed: {llm_result.get('error', 'Unknown error')}")
        # Fallback to keyword extraction
        return extract_common_themes(experiences, top_n=max_themes)

    # Parse LLM response
    try:
        response_data = llm_result['data']

        # Check if already parsed as dict
        if isinstance(response_data, dict):
            themes_data = response_data
        else:
            # It's a string, need to parse
            response_text = response_data

            # Try to extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            # Parse JSON
            themes_data = json.loads(response_text)

        # Extract themes
        themes = themes_data.get('themes', [])

        # Validate and clean themes
        cleaned_themes = []
        for theme in themes[:max_themes]:
            if isinstance(theme, str) and theme.strip():
                cleaned_themes.append(theme.strip().lower())

        # Update global stats
        tokens_used = llm_result['tokens_used']['total']
        cost_usd = llm_result['cost_usd']
        _THEME_EXTRACTION_TOKENS += tokens_used
        _THEME_EXTRACTION_COST += cost_usd

        logger.debug(f"LLM extracted {len(cleaned_themes)} themes (tokens: {tokens_used}, cost: ${cost_usd:.6f})")

        return cleaned_themes if cleaned_themes else extract_common_themes(experiences, top_n=max_themes)

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM theme response as JSON: {e}")
        # Fallback to keyword extraction
        return extract_common_themes(experiences, top_n=max_themes)

    except Exception as e:
        logger.warning(f"Unexpected error in LLM theme extraction: {e}")
        # Fallback to keyword extraction
        return extract_common_themes(experiences, top_n=max_themes)


def batch_extract_themes_with_llm(
    entity_groups: List[Tuple[str, List[Dict[str, Any]]]],
    max_themes: int = 5,
    batch_size: int = 5
) -> Dict[str, List[str]]:
    """
    Batch extract themes for multiple entity groups using LLM.

    Processes multiple entities in batches to reduce API calls.

    Args:
        entity_groups: List of (group_id, experiences) tuples
        max_themes: Maximum themes per entity
        batch_size: Number of entities to process per LLM call

    Returns:
        Dict mapping group_id to list of themes

    Example:
        >>> groups = [
        ...     ('attraction_1', [exp1, exp2, exp3, ...]),
        ...     ('attraction_2', [exp4, exp5, exp6, ...])
        ... ]
        >>> themes_dict = batch_extract_themes_with_llm(groups, max_themes=5)
        >>> themes_dict['attraction_1']
        ['nightlife', 'party', 'social', 'budget-friendly', 'backpacker']
    """
    global _THEME_EXTRACTION_TOKENS, _THEME_EXTRACTION_COST

    from src.utils.llm_client import extract_with_llm
    import json

    results = {}

    # Process in batches
    for batch_start in range(0, len(entity_groups), batch_size):
        batch = entity_groups[batch_start:batch_start + batch_size]

        # Build batch prompt
        batch_prompts = []
        for group_id, experiences in batch:
            # Take up to 5 experiences per entity
            sample_experiences = experiences[:5]
            exp_texts = []
            for exp in sample_experiences:
                exp_text = exp.get('experience', '').strip()
                if exp_text:
                    if len(exp_text) > 150:
                        exp_text = exp_text[:150] + '...'
                    exp_texts.append(exp_text)

            batch_prompts.append({
                'entity_id': group_id,
                'experiences': exp_texts
            })

        # Create batch prompt
        prompt = f"""Extract key themes for each entity based on traveler experiences.

For each entity, extract {max_themes} themes that capture its essence.

Entities:
"""
        for i, item in enumerate(batch_prompts, 1):
            prompt += f"\n{i}. Entity ID: {item['entity_id']}\n"
            prompt += "   Experiences:\n"
            for exp in item['experiences']:
                prompt += f"   - {exp}\n"

        prompt += f"""
Return ONLY valid JSON (no markdown):
{{
  "entities": [
    {{
      "entity_id": "...",
      "themes": ["theme1", "theme2", ...]
    }},
    ...
  ]
}}

Response:"""

        # Call LLM
        llm_result = extract_with_llm(
            prompt=prompt,
            max_retries=3,
            temperature=0.3,
            max_tokens=500  # Larger for batch
        )

        if not llm_result['success']:
            logger.warning(f"Batch LLM theme extraction failed for batch {batch_start}: {llm_result.get('error')}")
            # Fallback to individual extraction
            for group_id, experiences in batch:
                results[group_id] = extract_common_themes(experiences, top_n=max_themes)
            continue

        # Parse response
        try:
            response_data = llm_result['data']

            if isinstance(response_data, dict):
                batch_data = response_data
            else:
                response_text = response_data
                if '```json' in response_text:
                    json_start = response_text.find('```json') + 7
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()
                elif '```' in response_text:
                    json_start = response_text.find('```') + 3
                    json_end = response_text.find('```', json_start)
                    response_text = response_text[json_start:json_end].strip()

                batch_data = json.loads(response_text)

            # Extract themes for each entity
            for entity_result in batch_data.get('entities', []):
                entity_id = entity_result.get('entity_id')
                themes = entity_result.get('themes', [])

                if entity_id:
                    cleaned_themes = [t.strip().lower() for t in themes[:max_themes] if isinstance(t, str) and t.strip()]
                    results[entity_id] = cleaned_themes

            # Update stats
            tokens_used = llm_result['tokens_used']['total']
            cost_usd = llm_result['cost_usd']
            _THEME_EXTRACTION_TOKENS += tokens_used
            _THEME_EXTRACTION_COST += cost_usd

            logger.debug(f"Batch extracted themes for {len(batch)} entities (tokens: {tokens_used}, cost: ${cost_usd:.6f})")

        except Exception as e:
            logger.warning(f"Failed to parse batch theme response: {e}")
            # Fallback to individual extraction
            for group_id, experiences in batch:
                results[group_id] = extract_common_themes(experiences, top_n=max_themes)

    return results


# =============================================================================
# Best For / Not Recommended
# =============================================================================


def determine_best_for(
    profile_metrics: Dict[str, Any],
    rating_threshold: float = 4.0,
    min_mentions: int = 2
) -> List[str]:
    """
    Determine which profiles this entity is best for.

    Selects profiles with high ratings and sufficient mentions.

    Args:
        profile_metrics: Output from aggregate_experiences_by_profile()
        rating_threshold: Minimum avg_rating to be considered "best for"
        min_mentions: Minimum mentions required

    Returns:
        List of profile keys sorted by avg_rating descending

    Example:
        >>> profile_metrics = {...}
        >>> best_for = determine_best_for(profile_metrics, threshold=4.0)
        >>> best_for
        ['solo_budget_party', 'backpacker_social']
    """
    best_profiles = []

    for profile_key, metrics in profile_metrics.items():
        if metrics['avg_rating'] >= rating_threshold and metrics['mention_count'] >= min_mentions:
            best_profiles.append((profile_key, metrics['avg_rating']))

    # Sort by rating descending
    best_profiles.sort(key=lambda x: x[1], reverse=True)

    return [profile_key for profile_key, _ in best_profiles]


def determine_not_recommended(
    profile_metrics: Dict[str, Any],
    rating_threshold: float = 3.0,
    min_mentions: int = 2
) -> List[str]:
    """
    Determine which profiles this entity is NOT recommended for.

    Selects profiles with low ratings and sufficient mentions.

    Args:
        profile_metrics: Output from aggregate_experiences_by_profile()
        rating_threshold: Maximum avg_rating to be considered "not recommended"
        min_mentions: Minimum mentions required

    Returns:
        List of profile keys sorted by avg_rating ascending

    Example:
        >>> profile_metrics = {...}
        >>> not_recommended = determine_not_recommended(profile_metrics, threshold=3.0)
        >>> not_recommended
        ['family_budget', 'couple_luxury']
    """
    not_recommended_profiles = []

    for profile_key, metrics in profile_metrics.items():
        if metrics['avg_rating'] < rating_threshold and metrics['mention_count'] >= min_mentions:
            not_recommended_profiles.append((profile_key, metrics['avg_rating']))

    # Sort by rating ascending (worst first)
    not_recommended_profiles.sort(key=lambda x: x[1])

    return [profile_key for profile_key, _ in not_recommended_profiles]


# =============================================================================
# Complete Entity Consensus
# =============================================================================


def build_entity_consensus(canonical_entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build complete consensus data for a canonical entity.

    Takes a canonical entity and adds comprehensive consensus section with:
    - Profile-specific metrics
    - Overall rating (weighted by mentions)
    - Best for / not recommended for lists
    - Common themes across all experiences
    - Cost information

    Args:
        canonical_entity: Canonical entity dict from canonicalization

    Returns:
        Enriched canonical entity with 'consensus' field

    Example:
        >>> canonical = {...}
        >>> enriched = build_entity_consensus(canonical)
        >>> enriched['consensus']['overall_rating']
        4.3
        >>> enriched['consensus']['best_for']
        ['solo_budget_party', 'backpacker_social']
    """
    experiences = canonical_entity.get('experiences', [])

    if not experiences:
        # No experiences - return empty consensus
        canonical_entity['consensus'] = {
            'avg_rating': None,  # Fixed: was 'overall_rating'
            'mention_count': 0,  # Fixed: was 'total_mentions'
            'themes': [],  # Fixed: was 'common_themes'
            'profile_metrics': {},
            'best_for': [],
            'not_recommended_for': [],
            'cost_info': None,
            'sentiment_distribution': {'positive': 0, 'neutral': 0, 'negative': 0, 'mixed': 0}
        }
        return canonical_entity

    # 1. Aggregate by profile
    profile_metrics = aggregate_experiences_by_profile(experiences)

    # 2. Calculate overall rating (weighted by mentions)
    total_weighted_rating = 0
    total_mentions = 0

    for profile_key, metrics in profile_metrics.items():
        total_weighted_rating += metrics['avg_rating'] * metrics['mention_count']
        total_mentions += metrics['mention_count']

    overall_rating = total_weighted_rating / total_mentions if total_mentions > 0 else 3.0

    # 3. Determine best for / not recommended
    best_for = determine_best_for(profile_metrics, rating_threshold=4.0, min_mentions=2)
    not_recommended_for = determine_not_recommended(profile_metrics, rating_threshold=3.0, min_mentions=2)

    # 4. Extract common themes across all (use LLM for 5+ experiences)
    if len(experiences) >= 5:
        # Use LLM for better theme quality
        try:
            common_themes = extract_themes_with_llm(experiences, max_themes=10)
        except Exception as e:
            logger.warning(f"LLM theme extraction failed for entity, falling back to keyword extraction: {e}")
            common_themes = extract_common_themes(experiences, top_n=10)
    else:
        # Use simple keyword extraction for low experience counts
        common_themes = extract_common_themes(experiences, top_n=10)

    # 5. Get cost info
    cost_info = extract_cost_info(experiences)

    # 6. Get sentiment distribution
    sentiment_distribution = calculate_sentiment_distribution(experiences)

    # 7. Build consensus dict
    consensus = {
        'avg_rating': round(overall_rating, 2),  # Fixed: was 'overall_rating'
        'mention_count': total_mentions,  # Fixed: was 'total_mentions'
        'themes': common_themes,  # Fixed: was 'common_themes'
        'profile_metrics': profile_metrics,
        'best_for': best_for,
        'not_recommended_for': not_recommended_for,
        'cost_info': cost_info,
        'sentiment_distribution': sentiment_distribution
    }

    # Add to canonical entity
    canonical_entity['consensus'] = consensus

    return canonical_entity


# =============================================================================
# Testing and Validation
# =============================================================================


def test_profile_classification():
    """
    Test profile classification with sample experiences.

    Tests various traveler profile combinations to verify bucket matching.
    """
    logger.info("Testing profile classification...")

    test_cases = [
        # Solo budget party
        (
            {
                'traveler_profile': {
                    'traveler_type': 'solo',
                    'budget_tier': 'budget',
                    'travel_style': ['party', 'social', 'nightlife']
                }
            },
            'solo_budget_party'
        ),

        # Couple luxury
        (
            {
                'traveler_profile': {
                    'traveler_type': 'couple',
                    'budget_tier': 'luxury',
                    'travel_style': []
                }
            },
            'couple_luxury'
        ),

        # Family mid-range
        (
            {
                'traveler_profile': {
                    'traveler_type': 'family',
                    'budget_tier': 'mid-range',
                    'travel_style': ['relaxed']
                }
            },
            'family_midrange'
        ),

        # Backpacker social
        (
            {
                'traveler_profile': {
                    'traveler_type': 'solo',
                    'budget_tier': 'budget',
                    'travel_style': ['social', 'backpacker', 'hostel']
                }
            },
            'backpacker_social'
        ),

        # Digital nomad
        (
            {
                'traveler_profile': {
                    'traveler_type': 'solo',
                    'budget_tier': 'mid-range',
                    'travel_style': ['work', 'remote', 'coworking']
                }
            },
            'digital_nomad'
        ),

        # Unknown profile (fallback)
        (
            {
                'traveler_profile': {
                    'traveler_type': 'unknown',
                    'budget_tier': 'unknown',
                    'travel_style': []
                }
            },
            'other_unknown_unknown'
        )
    ]

    results = []
    for i, (experience, expected) in enumerate(test_cases, 1):
        result = classify_experience_profile(experience)
        correct = result == expected

        status = "✅ PASS" if correct else "❌ FAIL"

        logger.info(f"\nTest {i}: {status}")
        logger.info(f"  Input: {experience['traveler_profile']}")
        logger.info(f"  Expected: {expected}")
        logger.info(f"  Got: {result}")

        results.append(correct)

    # Summary
    passed = sum(results)
    total = len(results)
    logger.info(f"\n✅ Profile classification test complete: {passed}/{total} passed")

    return results


def test_consensus_calculation():
    """
    Test consensus calculation with sample canonical entity.

    Tests sentiment distribution, cost extraction, and consensus scoring.
    """
    logger.info("\nTesting consensus calculation...")

    # Sample canonical entity
    canonical_entity = {
        'entity_id': 'attraction_bangkok_001',
        'canonical_name': 'Wat Pho',
        'experiences': [
            {
                'experience': 'Amazing temple! Entry fee was 200 baht. Must visit!',
                'traveler_profile': {
                    'traveler_type': 'solo',
                    'budget_tier': 'budget',
                    'travel_style': ['cultural', 'history']
                }
            },
            {
                'experience': 'Beautiful reclining Buddha. Cost 200 baht to enter. Highly recommend.',
                'traveler_profile': {
                    'traveler_type': 'couple',
                    'budget_tier': 'mid-range',
                    'travel_style': ['cultural', 'sightseeing']
                }
            },
            {
                'experience': 'Great temple but very crowded. Entry was 200 baht.',
                'traveler_profile': {
                    'traveler_type': 'solo',
                    'budget_tier': 'budget',
                    'travel_style': ['cultural']
                }
            }
        ]
    }

    consensus = calculate_consensus_metadata(canonical_entity)

    logger.info("\n--- Consensus Metadata ---")
    logger.info(f"Profile distribution: {consensus['profile_distribution']}")
    logger.info(f"Sentiment distribution: {consensus['sentiment_distribution']}")
    logger.info(f"Cost info: {consensus['cost_info']['overall']}")
    logger.info(f"Consensus score: {consensus['consensus_score']:.2f}")
    logger.info(f"Total sources: {consensus['total_sources']}")
    logger.info(f"Dominant profile: {consensus['dominant_profile']}")
    logger.info(f"Dominant sentiment: {consensus['dominant_sentiment']}")

    # Verify results
    assert consensus['total_sources'] == 3, "Should have 3 sources"
    assert consensus['cost_info']['overall']['min'] == 200, "Min cost should be 200"
    assert consensus['cost_info']['overall']['max'] == 200, "Max cost should be 200"

    logger.info("\n✅ Consensus calculation test complete!")

    return consensus


def test_llm_theme_extraction():
    """
    Test LLM-based theme extraction with sample experiences.

    Verifies that LLM can extract meaningful themes from experiences.
    """
    logger.info("\n" + "=" * 80)
    logger.info("Testing LLM theme extraction...")
    logger.info("=" * 80)

    # Reset stats
    reset_theme_extraction_stats()

    # Sample experiences - nightlife/party themed
    experiences = [
        {'experience': 'Amazing nightlife with great bars and clubs on Khao San Road'},
        {'experience': 'Perfect for party lovers, cheap drinks and social atmosphere'},
        {'experience': 'Met lots of backpackers, very social vibe'},
        {'experience': 'Late night street food is incredible, party until sunrise'},
        {'experience': 'Best party destination in Bangkok, young crowd'}
    ]

    logger.info(f"\n📝 Sample experiences ({len(experiences)}):")
    for i, exp in enumerate(experiences, 1):
        logger.info(f"  {i}. {exp['experience']}")

    # Extract themes with LLM
    logger.info("\n🤖 Extracting themes with LLM...")
    themes = extract_themes_with_llm(experiences, max_themes=5)

    logger.info(f"\n✅ Extracted {len(themes)} themes:")
    for i, theme in enumerate(themes, 1):
        logger.info(f"  {i}. {theme}")

    # Get stats
    stats = get_theme_extraction_stats()
    logger.info(f"\n💰 Cost stats:")
    logger.info(f"   Total tokens: {stats['total_tokens_used']:,}")
    logger.info(f"   Total cost: ${stats['total_cost_usd']:.6f}")

    # Verify results
    assert len(themes) > 0, "Should extract at least 1 theme"
    assert len(themes) <= 5, "Should not exceed max_themes"

    logger.info("\n✅ LLM theme extraction test complete!")

    return themes


if __name__ == '__main__':
    # Run tests
    test_profile_classification()
    test_consensus_calculation()
    # Uncomment to test LLM theme extraction (requires API key)
    # test_llm_theme_extraction()
