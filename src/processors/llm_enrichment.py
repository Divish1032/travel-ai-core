"""
LLM-Based Entity Enrichment

Provides temporal, logistics, and practical information for entities using LLM knowledge
when transcript data is not available.

Features:
- LLM knowledge enrichment for well-known places
- Provenance tracking (llm_inferred vs transcript_extracted vs hybrid)
- Merge logic for blending LLM data with real transcript data
- Confidence scoring based on entity popularity/fame
- Caching to avoid repeated LLM calls

Usage:
    from src.processors.llm_enrichment import enrich_entity_with_llm, merge_enrichment_data

    # Get LLM-based enrichment
    enrichment = enrich_entity_with_llm(entity)

    # Merge with existing transcript data
    merged = merge_enrichment_data(existing_data, new_transcript_data)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from src.utils.logging import get_logger
from src.utils.config import config

logger = get_logger(__name__)

# =============================================================================
# LLM Enrichment Cache
# =============================================================================

_ENRICHMENT_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_FILE_PATH = Path("data/llm_enrichment_cache.json")

# Cost tracking
_LLM_ENRICHMENT_TOKENS = 0
_LLM_ENRICHMENT_COST_USD = 0.0


def _get_cache_key(entity_name: str, entity_type: str, location: str) -> str:
    """Generate a unique cache key for an entity."""
    key_string = f"{entity_name.lower().strip()}|{entity_type.lower()}|{location.lower().strip()}"
    return hashlib.md5(key_string.encode()).hexdigest()


def _load_cache() -> Dict[str, Any]:
    """Load enrichment cache from disk."""
    global _ENRICHMENT_CACHE

    if _ENRICHMENT_CACHE:
        return _ENRICHMENT_CACHE

    if _CACHE_FILE_PATH.exists():
        try:
            with open(_CACHE_FILE_PATH, 'r', encoding='utf-8') as f:
                _ENRICHMENT_CACHE = json.load(f)
            logger.info(f"Loaded {len(_ENRICHMENT_CACHE)} cached enrichments")
        except Exception as e:
            logger.warning(f"Failed to load enrichment cache: {e}")
            _ENRICHMENT_CACHE = {}

    return _ENRICHMENT_CACHE


def _save_cache():
    """Save enrichment cache to disk."""
    try:
        _CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_ENRICHMENT_CACHE, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved {len(_ENRICHMENT_CACHE)} enrichments to cache")
    except Exception as e:
        logger.warning(f"Failed to save enrichment cache: {e}")


# =============================================================================
# Entity Popularity/Fame Detection
# =============================================================================

# Well-known Thai tourist destinations that LLM should have accurate knowledge about
FAMOUS_ENTITIES = {
    # Bangkok temples and landmarks
    'wat pho': 0.95,
    'wat arun': 0.95,
    'grand palace': 0.95,
    'wat phra kaew': 0.95,
    'chatuchak market': 0.90,
    'khao san road': 0.90,
    'jim thompson house': 0.85,
    'wat traimit': 0.85,
    'wat saket': 0.85,
    'golden mount': 0.85,
    'lumphini park': 0.85,
    'asiatique': 0.80,
    'icon siam': 0.80,
    'terminal 21': 0.80,
    'mbk center': 0.80,

    # Chiang Mai
    'doi suthep': 0.90,
    'wat phra that doi suthep': 0.90,
    'old city chiang mai': 0.85,
    'sunday walking street': 0.80,
    'elephant nature park': 0.85,
    'doi inthanon': 0.85,

    # Islands and beaches
    'phi phi islands': 0.95,
    'maya bay': 0.90,
    'phuket': 0.90,
    'patong beach': 0.85,
    'koh samui': 0.90,
    'koh phangan': 0.85,
    'koh tao': 0.85,
    'railay beach': 0.90,
    'krabi': 0.85,
    'koh lipe': 0.80,
    'similan islands': 0.85,

    # Nature and national parks
    'khao sok national park': 0.85,
    'erawan national park': 0.85,
    'erawan falls': 0.85,
    'khao yai national park': 0.85,
    'elephant hills': 0.80,

    # Historical sites
    'ayutthaya': 0.90,
    'sukhothai': 0.85,
    'bridge over river kwai': 0.85,

    # Other popular spots
    'floating market': 0.80,
    'damnoen saduak': 0.80,
    'amphawa floating market': 0.80,
    'tiger temple': 0.75,
    'white temple': 0.90,
    'wat rong khun': 0.90,
    'blue temple': 0.80,
    'pai': 0.80,
    'hua hin': 0.80,
}


def get_entity_fame_score(entity_name: str, entity_type: str) -> float:
    """
    Estimate how famous/well-known an entity is.

    Higher fame = more reliable LLM knowledge.

    Args:
        entity_name: Name of the entity
        entity_type: Type of entity (attraction, restaurant, etc.)

    Returns:
        Fame score from 0.0 to 1.0
    """
    name_lower = entity_name.lower().strip()

    # Check against known famous entities
    for famous_name, score in FAMOUS_ENTITIES.items():
        if famous_name in name_lower or name_lower in famous_name:
            return score

    # Heuristics for unknown entities
    fame_score = 0.5  # Base score

    # Boost for entity types that are typically documented
    if entity_type in ['attraction', 'destination']:
        fame_score += 0.1

    # Boost for names with "Wat" (Thai temples are well-documented)
    if 'wat ' in name_lower or name_lower.startswith('wat '):
        fame_score += 0.15

    # Boost for names with "National Park"
    if 'national park' in name_lower:
        fame_score += 0.15

    # Boost for names with "Island" or "Beach"
    if 'island' in name_lower or 'beach' in name_lower:
        fame_score += 0.1

    # Reduce for generic-sounding names
    generic_words = ['local', 'small', 'nice', 'good', 'cheap', 'nearby']
    if any(word in name_lower for word in generic_words):
        fame_score -= 0.2

    return max(0.3, min(0.85, fame_score))


# =============================================================================
# LLM Enrichment Prompt
# =============================================================================

LLM_ENRICHMENT_PROMPT = """You are a Thailand travel expert. Given a tourist entity, provide practical visiting information.

Entity: {entity_name}
Type: {entity_type}
Location: {location}

Provide ONLY factual, commonly-known information. If you're not confident about something, omit it.

Respond in this exact JSON format:
{{
    "temporal_info": {{
        "best_seasons": ["list of best months/seasons to visit, e.g., 'november-february', 'dry season'"],
        "best_times_of_day": ["e.g., 'early morning', 'sunset', 'evening'"],
        "typical_duration": "e.g., '2-3 hours', 'half day', 'full day'",
        "seasonal_notes": ["any seasonal considerations, e.g., 'crowded during Chinese New Year'"]
    }},
    "logistics_info": {{
        "transport_options": ["how to get there, e.g., 'BTS Saphan Taksin + boat', 'taxi from airport'"],
        "booking_required": true/false,
        "booking_notes": ["e.g., 'book 1 day ahead for weekends'"],
        "accessibility_features": ["e.g., 'wheelchair accessible', 'steep stairs'"]
    }},
    "practical_tips": {{
        "dress_code": "e.g., 'cover shoulders and knees for temples'",
        "entrance_fee": "e.g., '200 THB for foreigners'",
        "opening_hours": "e.g., '8:00 AM - 5:00 PM daily'"
    }},
    "known_ratings": {{
        "google_maps_rating": 4.5,
        "typical_rating_range": "4.0-4.8",
        "rating_confidence": 0.0-1.0,
        "review_volume": "high/medium/low",
        "notable_awards": ["e.g., 'UNESCO World Heritage Site', 'Michelin recommended'"]
    }},
    "confidence": 0.0-1.0
}}

IMPORTANT:
- Only include fields you're confident about
- For lesser-known places, include fewer fields
- confidence should reflect how sure you are (famous places = higher confidence)
- For known_ratings: only include if you're fairly certain about Google/TripAdvisor ratings
- rating_confidence should be high (0.8+) only for very famous places you're sure about
- Omit any field you're uncertain about rather than guessing"""


def _call_llm_for_enrichment(
    entity_name: str,
    entity_type: str,
    location: str
) -> Optional[Dict[str, Any]]:
    """
    Call LLM to get enrichment data for an entity.

    Args:
        entity_name: Name of the entity
        entity_type: Type of entity
        location: Location (city/area)

    Returns:
        Enrichment data dict or None if failed
    """
    global _LLM_ENRICHMENT_TOKENS, _LLM_ENRICHMENT_COST_USD

    try:
        import google.genai as genai

        # Create client with API key
        api_key = config.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY not configured, skipping LLM enrichment")
            return None

        client = genai.Client(api_key=api_key)

        # Build prompt
        prompt = LLM_ENRICHMENT_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            location=location or "Thailand"
        )

        # Configure generation settings
        generation_config = {
            "temperature": 0.3,  # Low temperature for factual responses
            "max_output_tokens": 1000,
            "response_mime_type": "application/json",  # Force JSON output
        }

        # Call LLM using the new API
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=generation_config
        )

        # Parse response
        if not response.text:
            logger.warning("Empty response from Gemini")
            return None

        response_text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks if present)
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        enrichment_data = json.loads(response_text)

        # Track tokens and cost
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            tokens = getattr(usage, 'total_token_count', 0)
            _LLM_ENRICHMENT_TOKENS += tokens
            # Gemini Flash Lite pricing: ~$0.075 per 1M tokens
            cost = tokens * 0.000000075
            _LLM_ENRICHMENT_COST_USD += cost
            logger.debug(f"LLM enrichment used {tokens} tokens (${cost:.6f})")

        return enrichment_data

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM enrichment response: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM enrichment call failed: {e}")
        return None


# =============================================================================
# Main Enrichment Function
# =============================================================================

def enrich_entity_with_llm(
    entity: Dict[str, Any],
    use_cache: bool = True,
    min_fame_score: float = 0.5
) -> Optional[Dict[str, Any]]:
    """
    Enrich an entity with LLM knowledge when transcript data is not available.

    Args:
        entity: Canonical entity dict with canonical_name, entity_type, location
        use_cache: Whether to use cached enrichment (default: True)
        min_fame_score: Minimum fame score to attempt LLM enrichment (default: 0.5)

    Returns:
        Enrichment data dict with provenance tracking, or None if not enrichable

    Example:
        >>> entity = {'canonical_name': 'Wat Pho', 'entity_type': 'attraction', 'location': 'Bangkok'}
        >>> enrichment = enrich_entity_with_llm(entity)
        >>> print(enrichment['temporal_info']['best_times_of_day'])
        ['early morning', 'late afternoon']
    """
    entity_name = entity.get('canonical_name', '')
    entity_type = entity.get('entity_type', 'unknown')

    # Get location as string
    location = entity.get('location', '')
    if isinstance(location, dict):
        location = location.get('city', '') or location.get('area', '')

    if not entity_name:
        return None

    # Check fame score - only enrich well-known entities
    fame_score = get_entity_fame_score(entity_name, entity_type)
    if fame_score < min_fame_score:
        logger.debug(f"Skipping LLM enrichment for '{entity_name}' (fame score {fame_score:.2f} < {min_fame_score})")
        return None

    # Check cache
    cache_key = _get_cache_key(entity_name, entity_type, location)
    cache = _load_cache()

    if use_cache and cache_key in cache:
        logger.debug(f"Using cached enrichment for '{entity_name}'")
        cached_data = cache[cache_key].copy()
        cached_data['_from_cache'] = True
        return cached_data

    # Call LLM
    logger.info(f"🧠 Enriching '{entity_name}' with LLM knowledge (fame={fame_score:.2f})")
    llm_response = _call_llm_for_enrichment(entity_name, entity_type, location)

    if not llm_response:
        return None

    # Build enrichment result with provenance
    now = datetime.now(timezone.utc).isoformat()

    result = {
        'temporal_info': llm_response.get('temporal_info', {}),
        'logistics_info': llm_response.get('logistics_info', {}),
        'practical_tips': llm_response.get('practical_tips', {}),

        # Provenance tracking
        'provenance': {
            'source': 'llm_inferred',
            'llm_model': 'gemini-2.0-flash-lite',
            'fame_score': fame_score,
            'llm_confidence': llm_response.get('confidence', 0.7),
            'enriched_at': now,
            'transcript_mentions': 0,  # No transcript data yet
            'last_transcript_update': None
        }
    }

    # Add confidence to temporal/logistics info
    llm_confidence = llm_response.get('confidence', 0.7)
    # Adjust confidence based on fame score
    adjusted_confidence = min(0.9, llm_confidence * fame_score)

    if result['temporal_info']:
        result['temporal_info']['confidence'] = adjusted_confidence
        result['temporal_info']['source'] = 'llm_inferred'

    if result['logistics_info']:
        result['logistics_info']['confidence'] = adjusted_confidence
        result['logistics_info']['source'] = 'llm_inferred'

    # Cache result
    cache[cache_key] = result
    _save_cache()

    return result


# =============================================================================
# Merge Logic for Hybrid Enrichment
# =============================================================================

def merge_enrichment_data(
    existing: Optional[Dict[str, Any]],
    new_transcript_data: Optional[Dict[str, Any]],
    transcript_weight: float = 1.0,
    llm_weight: float = 0.7
) -> Dict[str, Any]:
    """
    Merge existing enrichment data with new transcript-extracted data.

    Transcript data takes precedence over LLM-inferred data.

    Args:
        existing: Existing enrichment data (may be LLM-inferred or hybrid)
        new_transcript_data: New data extracted from transcripts
        transcript_weight: Weight for transcript data (default: 1.0)
        llm_weight: Weight for LLM data (default: 0.7)

    Returns:
        Merged enrichment data with updated provenance

    Example:
        >>> existing = {'temporal_info': {'best_seasons': ['november'], 'source': 'llm_inferred'}}
        >>> new_data = {'temporal_info': {'best_seasons': ['december', 'january']}}
        >>> merged = merge_enrichment_data(existing, new_data)
        >>> print(merged['temporal_info']['source'])
        'hybrid'
    """
    # If no existing data, just use new data
    if not existing:
        if new_transcript_data:
            # Mark as transcript_extracted
            result = new_transcript_data.copy()
            result['provenance'] = {
                'source': 'transcript_extracted',
                'transcript_mentions': 1,
                'last_transcript_update': datetime.now(timezone.utc).isoformat()
            }
            if 'temporal_info' in result and result['temporal_info']:
                result['temporal_info']['source'] = 'transcript_extracted'
            if 'logistics_info' in result and result['logistics_info']:
                result['logistics_info']['source'] = 'transcript_extracted'
            return result
        return {}

    # If no new data, return existing
    if not new_transcript_data:
        return existing

    # Merge the data
    merged = existing.copy()
    now = datetime.now(timezone.utc).isoformat()

    # Update provenance
    merged['provenance'] = merged.get('provenance', {}).copy()
    merged['provenance']['source'] = 'hybrid'
    merged['provenance']['transcript_mentions'] = merged['provenance'].get('transcript_mentions', 0) + 1
    merged['provenance']['last_transcript_update'] = now

    # Merge temporal_info
    if 'temporal_info' in new_transcript_data and new_transcript_data['temporal_info']:
        existing_temporal = merged.get('temporal_info', {})
        new_temporal = new_transcript_data['temporal_info']

        merged_temporal = _merge_info_dict(existing_temporal, new_temporal, transcript_weight, llm_weight)
        merged_temporal['source'] = 'hybrid'

        # Boost confidence when transcript confirms LLM
        existing_conf = existing_temporal.get('confidence', 0.5)
        merged_temporal['confidence'] = min(0.95, existing_conf + 0.15)

        merged['temporal_info'] = merged_temporal

    # Merge logistics_info
    if 'logistics_info' in new_transcript_data and new_transcript_data['logistics_info']:
        existing_logistics = merged.get('logistics_info', {})
        new_logistics = new_transcript_data['logistics_info']

        merged_logistics = _merge_info_dict(existing_logistics, new_logistics, transcript_weight, llm_weight)
        merged_logistics['source'] = 'hybrid'

        # Boost confidence
        existing_conf = existing_logistics.get('confidence', 0.5)
        merged_logistics['confidence'] = min(0.95, existing_conf + 0.15)

        merged['logistics_info'] = merged_logistics

    return merged


def _merge_info_dict(
    existing: Dict[str, Any],
    new: Dict[str, Any],
    new_weight: float,
    existing_weight: float
) -> Dict[str, Any]:
    """
    Merge two info dictionaries (temporal or logistics).

    For lists: combine unique values, prioritize new data
    For strings: prefer new data if available
    For booleans: prefer new data
    """
    merged = existing.copy()

    for key, new_value in new.items():
        if key in ['confidence', 'source']:
            continue  # Handle separately

        existing_value = merged.get(key)

        if new_value is None:
            continue

        if isinstance(new_value, list):
            if isinstance(existing_value, list):
                # Combine lists, new values first
                combined = list(new_value)
                for item in existing_value:
                    if item not in combined:
                        combined.append(item)
                merged[key] = combined[:5]  # Limit to 5 items
            else:
                merged[key] = new_value

        elif isinstance(new_value, bool):
            # Prefer transcript data for booleans
            merged[key] = new_value

        elif isinstance(new_value, str):
            # Prefer transcript data for strings if non-empty
            if new_value.strip():
                merged[key] = new_value

        else:
            # For other types, prefer new data
            merged[key] = new_value

    return merged


# =============================================================================
# Batch Enrichment
# =============================================================================

def batch_enrich_with_llm(
    entities: List[Dict[str, Any]],
    use_cache: bool = True,
    min_fame_score: float = 0.5,
    max_entities: int = 100
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Enrich multiple entities with LLM knowledge.

    Args:
        entities: List of canonical entity dicts
        use_cache: Whether to use cached enrichment
        min_fame_score: Minimum fame score to attempt enrichment
        max_entities: Maximum entities to enrich in one batch (cost control)

    Returns:
        Tuple of (enriched_entities, statistics)
    """
    stats = {
        'total_entities': len(entities),
        'enriched': 0,
        'from_cache': 0,
        'skipped_low_fame': 0,
        'failed': 0,
        'tokens_used': 0,
        'cost_usd': 0.0
    }

    global _LLM_ENRICHMENT_TOKENS, _LLM_ENRICHMENT_COST_USD
    tokens_before = _LLM_ENRICHMENT_TOKENS
    cost_before = _LLM_ENRICHMENT_COST_USD

    enriched_entities = []
    enriched_count = 0

    for entity in entities:
        entity_copy = entity.copy()

        # Check if already has good temporal/logistics data from transcripts
        existing_temporal = entity.get('temporal_info', {})
        existing_logistics = entity.get('logistics_info', {})

        has_good_temporal = (
            existing_temporal and
            existing_temporal.get('confidence', 0) > 0.5 and
            existing_temporal.get('source') != 'llm_inferred'
        )
        has_good_logistics = (
            existing_logistics and
            existing_logistics.get('confidence', 0) > 0.5 and
            existing_logistics.get('source') != 'llm_inferred'
        )

        # Skip if already has good data
        if has_good_temporal and has_good_logistics:
            enriched_entities.append(entity_copy)
            continue

        # Check cost limit
        if enriched_count >= max_entities:
            enriched_entities.append(entity_copy)
            continue

        # Get LLM enrichment
        enrichment = enrich_entity_with_llm(
            entity,
            use_cache=use_cache,
            min_fame_score=min_fame_score
        )

        if enrichment:
            # Check if from cache
            if enrichment.get('_from_cache'):
                stats['from_cache'] += 1
            else:
                enriched_count += 1

            stats['enriched'] += 1

            # Merge with existing data
            if has_good_temporal:
                # Keep existing temporal, add LLM logistics
                if 'logistics_info' in enrichment:
                    entity_copy['logistics_info'] = enrichment['logistics_info']
            elif has_good_logistics:
                # Keep existing logistics, add LLM temporal
                if 'temporal_info' in enrichment:
                    entity_copy['temporal_info'] = enrichment['temporal_info']
            else:
                # Add both
                if 'temporal_info' in enrichment:
                    entity_copy['temporal_info'] = enrichment['temporal_info']
                if 'logistics_info' in enrichment:
                    entity_copy['logistics_info'] = enrichment['logistics_info']

            # Add practical tips if available
            if 'practical_tips' in enrichment:
                entity_copy['practical_tips'] = enrichment['practical_tips']

            # Update provenance
            entity_copy['enrichment_provenance'] = enrichment.get('provenance', {})
        else:
            # Check why enrichment failed
            fame_score = get_entity_fame_score(
                entity.get('canonical_name', ''),
                entity.get('entity_type', '')
            )
            if fame_score < min_fame_score:
                stats['skipped_low_fame'] += 1
            else:
                stats['failed'] += 1

        enriched_entities.append(entity_copy)

    # Calculate token/cost stats
    stats['tokens_used'] = _LLM_ENRICHMENT_TOKENS - tokens_before
    stats['cost_usd'] = _LLM_ENRICHMENT_COST_USD - cost_before

    logger.info(f"✨ LLM Enrichment complete:")
    logger.info(f"   Enriched: {stats['enriched']}/{stats['total_entities']}")
    logger.info(f"   From cache: {stats['from_cache']}")
    logger.info(f"   Skipped (low fame): {stats['skipped_low_fame']}")
    logger.info(f"   Failed: {stats['failed']}")
    logger.info(f"   Tokens used: {stats['tokens_used']}")
    logger.info(f"   Cost: ${stats['cost_usd']:.4f}")

    return enriched_entities, stats


# =============================================================================
# Statistics and Cost Tracking
# =============================================================================

def get_llm_enrichment_stats() -> Dict[str, Any]:
    """Get LLM enrichment statistics."""
    return {
        'total_tokens_used': _LLM_ENRICHMENT_TOKENS,
        'total_cost_usd': _LLM_ENRICHMENT_COST_USD,
        'cache_size': len(_ENRICHMENT_CACHE)
    }


def reset_llm_enrichment_stats():
    """Reset LLM enrichment statistics."""
    global _LLM_ENRICHMENT_TOKENS, _LLM_ENRICHMENT_COST_USD
    _LLM_ENRICHMENT_TOKENS = 0
    _LLM_ENRICHMENT_COST_USD = 0.0


# =============================================================================
# Testing
# =============================================================================

def test_llm_enrichment():
    """Test LLM enrichment with sample entities."""
    logger.info("=" * 80)
    logger.info("LLM ENRICHMENT TEST")
    logger.info("=" * 80)

    test_entities = [
        {
            'canonical_name': 'Wat Pho',
            'entity_type': 'attraction',
            'location': 'Bangkok'
        },
        {
            'canonical_name': 'Phi Phi Islands',
            'entity_type': 'destination',
            'location': 'Krabi'
        },
        {
            'canonical_name': 'some local restaurant',
            'entity_type': 'restaurant',
            'location': 'Bangkok'
        }
    ]

    for entity in test_entities:
        logger.info(f"\nTesting: {entity['canonical_name']}")

        # Get fame score
        fame = get_entity_fame_score(entity['canonical_name'], entity['entity_type'])
        logger.info(f"  Fame score: {fame:.2f}")

        # Get enrichment
        enrichment = enrich_entity_with_llm(entity, use_cache=False, min_fame_score=0.5)

        if enrichment:
            logger.info(f"  ✅ Got enrichment:")
            if 'temporal_info' in enrichment:
                logger.info(f"     Temporal: {enrichment['temporal_info']}")
            if 'logistics_info' in enrichment:
                logger.info(f"     Logistics: {enrichment['logistics_info']}")
            if 'provenance' in enrichment:
                logger.info(f"     Provenance: {enrichment['provenance']}")
        else:
            logger.info(f"  ⏭️  Skipped (low fame or error)")

    # Print stats
    stats = get_llm_enrichment_stats()
    logger.info(f"\nStats: {stats}")


if __name__ == '__main__':
    test_llm_enrichment()
