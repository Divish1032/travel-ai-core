"""
Stage 2: Entity Extraction from YouTube Travel Vlogs

Extracts structured travel information from transcribed YouTube videos using LLMs.

Purpose:
    Takes raw YouTube video transcripts (Stage 1 output) and extracts:
    - Traveler Profile: Demographics, travel style, budget tier
    - Entity Experiences: Places visited, activities done, sentiment analysis

Input:
    - S3 Path: s3://bucket/raw/youtube/videos/YYYY-MM/batch_*.jsonl
    - Schema: YouTubeVideo (from Stage 1)
    - Fields Used:
        - source_id: Video ID
        - language: For language-specific prompts
        - transcript: Array of segments with text, start, duration
        - duration_seconds: Total video length
        - title, tags: Additional context

Processing:
    1. Load videos with pipeline_status="stage_2_pending" from MetadataTracker
    2. Combine transcript segments into coherent text
    3. Send to LLM (OpenAI/Anthropic) with structured extraction prompt
    4. Parse LLM response into TravelerProfile + EntityExperience objects
    5. Validate with Pydantic schemas
    6. Save to S3 as Stage2Output

Output:
    - S3 Path: s3://bucket/processed/youtube/extracted/YYYY-MM/extracted_*.jsonl
    - Schema: Stage2Output
        - metadata: source_id, language, processing_timestamp
        - traveler_profile: TravelerProfile object
        - entities: List[EntityExperience] objects

LLM Strategy:
    - Model: GPT-4 or Claude 3 Sonnet
    - Token limit: ~8k tokens per video (chunk if needed)
    - Prompt: System prompt + Few-shot examples + Transcript
    - Output format: Structured JSON matching Stage2Output schema
    - Cost estimation: $0.01 - $0.05 per video

Data Flow:
    MetadataTracker → Load pending videos
    ↓
    S3 raw/youtube/videos → Download JSONL
    ↓
    Combine transcript → Full text
    ↓
    LLM API → Extract entities
    ↓
    Validate → Pydantic schemas
    ↓
    S3 processed/youtube/extracted → Save
    ↓
    MetadataTracker → Mark stage_2 complete

Error Handling:
    - LLM API failures: Retry with exponential backoff
    - Parsing errors: Log and mark as failed
    - Cost tracking: Track tokens used per video
    - Progress: Save after each batch to minimize re-processing

Example Usage:
    from src.processors.stage2_extractor import extract_entities_batch
    from src.storage.s3 import S3Storage
    from src.utils.metadata_tracker import MetadataTracker

    # Initialize
    storage = S3Storage()
    tracker = MetadataTracker(storage)

    # Get pending videos
    pending = tracker.get_pending_content("stage_2_extract")

    # Process batch
    results = extract_entities_batch(
        content_ids=pending[:10],  # Process 10 videos
        tracker=tracker,
        llm_model="gpt-4",
        max_concurrent=3
    )

    print(f"Processed: {results['successful']}/{results['total']}")

TODO (Not Implemented):
    - [ ] LLM integration (OpenAI/Anthropic)
    - [ ] Transcript chunking for long videos
    - [ ] Language-specific prompts
    - [ ] Cost tracking
    - [ ] Batch processing
    - [ ] CLI command for running Stage 2
"""

from typing import List, Dict, Any, Optional, Literal, Tuple
from datetime import datetime, timezone
import re

from src.utils.schemas import Stage2Output, TravelerProfile, EntityExperience
from src.utils.llm_client import extract_with_llm
from src.processors.extraction_prompts import (
    format_single_pass_prompt,
    format_hierarchical_chunk_prompt,
    format_hierarchical_merge_prompt,
    format_profile_only_prompt,
    format_entities_only_prompt,
    format_entity_enrichment_prompt
)
from src.utils.logging import get_logger
import json

# Import rapidfuzz for fuzzy string matching (used in deduplication)
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    fuzz = None

# Try to import translator (optional due to httpx version conflicts)
try:
    from src.utils.translator import translate_transcript
    TRANSLATOR_AVAILABLE = True
except (ImportError, AttributeError) as e:
    TRANSLATOR_AVAILABLE = False
    # Define dummy function if translator unavailable
    def translate_transcript(*args, **kwargs):
        raise ImportError(
            "Translator not available due to dependency conflicts. "
            "googletrans requires httpx==0.13.3 but openai requires httpx>=0.23.0"
        )


logger = get_logger(__name__)


# =============================================================================
# Entity Type Mapping and Validation
# =============================================================================

def normalize_entity_type(entity_type: str, entity_name: str = "") -> str:
    """
    Map invalid or non-standard entity_types to valid schema values.

    This handles cases where the LLM returns types that don't match our schema,
    preventing data loss while maintaining schema compliance.

    Valid types: destination, restaurant, hotel, activity, attraction,
                 transportation, shopping, unknown

    Args:
        entity_type: The entity_type returned by LLM
        entity_name: Entity name for context-based mapping

    Returns:
        Valid entity_type from schema

    Examples:
        >>> normalize_entity_type('travel_style', 'Nightlife')
        'activity'
        >>> normalize_entity_type('food', 'Street Food')
        'restaurant'
        >>> normalize_entity_type('beach', 'Patong Beach')
        'destination'
    """
    # Valid types according to schema
    VALID_TYPES = {
        'destination', 'restaurant', 'hotel', 'activity',
        'attraction', 'transportation', 'shopping', 'unknown'
    }

    # Normalize input
    entity_type_lower = entity_type.lower().strip()
    entity_name_lower = entity_name.lower().strip()

    # If already valid, return as-is
    if entity_type_lower in VALID_TYPES:
        return entity_type_lower

    # Mapping rules for common invalid types
    TYPE_MAPPINGS = {
        # Travel style confused with entity type
        'travel_style': 'activity',

        # Food-related
        'food': 'restaurant',
        'food_category': 'restaurant',
        'dining': 'restaurant',
        'cuisine': 'restaurant',

        # Beach/Nature
        'beach': 'destination',
        'nature': 'destination',
        'park': 'attraction',

        # Activities
        'nightlife': 'activity',
        'entertainment': 'activity',
        'adventure': 'activity',
        'sport': 'activity',
        'sports': 'activity',

        # Transport variants
        'transport': 'transportation',
        'transit': 'transportation',
        'travel': 'transportation',

        # Accommodation variants
        'accommodation': 'hotel',
        'lodging': 'hotel',
        'hostel': 'hotel',

        # Shopping variants
        'market': 'shopping',
        'store': 'shopping',
        'mall': 'shopping',

        # Culture/Tourism
        'culture': 'attraction',
        'cultural': 'attraction',
        'monument': 'attraction',
        'temple': 'attraction',
        'museum': 'attraction',
        'landmark': 'attraction',

        # Nature/Wildlife
        'wildlife': 'attraction',
        'nature_spot': 'attraction',
        'scenic': 'attraction',
        'viewpoint': 'attraction',

        # Travel style tags (commonly confused)
        'foodie': 'restaurant',
        'adventure': 'activity',
        'relaxation': 'destination',
        'cultural': 'attraction',
    }

    # Try direct mapping
    if entity_type_lower in TYPE_MAPPINGS:
        mapped_type = TYPE_MAPPINGS[entity_type_lower]
        logger.debug(
            f"Mapped invalid entity_type '{entity_type}' -> '{mapped_type}' "
            f"for entity '{entity_name}'"
        )
        return mapped_type

    # Context-based mapping using entity name
    if entity_name_lower:
        # Food/Restaurant keywords
        if any(word in entity_name_lower for word in ['food', 'restaurant', 'cafe', 'bar', 'street food', 'dining']):
            logger.debug(f"Mapped '{entity_type}' -> 'restaurant' based on name '{entity_name}'")
            return 'restaurant'

        # Beach/Destination keywords
        if any(word in entity_name_lower for word in ['beach', 'island', 'bay', 'coast']):
            logger.debug(f"Mapped '{entity_type}' -> 'destination' based on name '{entity_name}'")
            return 'destination'

        # Activity keywords
        if any(word in entity_name_lower for word in ['nightlife', 'party', 'club', 'diving', 'snorkeling', 'hiking']):
            logger.debug(f"Mapped '{entity_type}' -> 'activity' based on name '{entity_name}'")
            return 'activity'

        # Attraction keywords
        if any(word in entity_name_lower for word in ['temple', 'palace', 'museum', 'monument', 'park']):
            logger.debug(f"Mapped '{entity_type}' -> 'attraction' based on name '{entity_name}'")
            return 'attraction'

    # Default fallback
    logger.warning(
        f"Unmapped entity_type '{entity_type}' for '{entity_name}', defaulting to 'unknown'"
    )
    return 'unknown'


# =============================================================================
# Entity Validation
# =============================================================================

# Common city and country names that should NOT be extracted as entities
GENERIC_LOCATIONS = {
    # Major Asian cities
    "bangkok", "phuket", "chiang mai", "krabi", "pattaya", "hua hin", "koh samui",
    "hanoi", "ho chi minh city", "saigon", "da nang", "hoi an", "nha trang",
    "singapore", "kuala lumpur", "penang", "langkawi",
    "manila", "cebu", "boracay", "palawan",
    "jakarta", "bali", "denpasar", "ubud", "seminyak",
    "hong kong", "macau", "taipei", "tokyo", "osaka", "kyoto", "seoul", "busan",

    # Countries
    "thailand", "vietnam", "singapore", "malaysia", "philippines", "indonesia",
    "cambodia", "laos", "myanmar", "burma", "china", "japan", "korea", "india",

    # Regions
    "southeast asia", "northern thailand", "southern thailand", "central thailand",
    "isaan", "the north", "the south", "asia", "europe", "america",

    # Generic travel terms
    "city center", "downtown", "old town", "new town", "city", "town", "village"
}


def _is_generic_location(entity_name: str) -> bool:
    """
    Check if entity_name is a generic city/country name that shouldn't be an entity.

    Args:
        entity_name: The entity name to check

    Returns:
        True if it's a generic location (city/country), False if it's specific

    Examples:
        >>> _is_generic_location("Bangkok")
        True
        >>> _is_generic_location("Grand Palace")
        False
        >>> _is_generic_location("Wat Pho")
        False
        >>> _is_generic_location("Thailand")
        True
    """
    if not entity_name:
        return False

    # Normalize for comparison
    normalized = entity_name.lower().strip()

    # Direct match
    if normalized in GENERIC_LOCATIONS:
        return True

    # Check if it's just a city name without specifics
    # e.g., "Bangkok city" is generic, but "Bangkok Grand Palace" is specific
    words = normalized.split()
    if len(words) == 1 and normalized in GENERIC_LOCATIONS:
        return True

    # Check for "City of X" patterns
    if normalized.startswith("city of ") or normalized.endswith(" city"):
        core = normalized.replace("city of ", "").replace(" city", "").strip()
        if core in GENERIC_LOCATIONS:
            return True

    return False


def validate_entity_quality(entity: EntityExperience) -> bool:
    """
    Validate entity has proper confidence_score and meets quality requirements.

    Args:
        entity: EntityExperience object to validate

    Returns:
        True if entity passes validation, False otherwise

    Validation Rules:
        - confidence_score must be present and >= 0.1
        - confidence_score must be <= 1.0
        - Warns if confidence_score is suspiciously at 0.0 (bug indicator)
        - Rejects generic city/country names (should be specific places)

    Example:
        >>> entity = EntityExperience(
        ...     entity_name="Patong Beach",
        ...     entity_type="destination",
        ...     location="Phuket",
        ...     experience="Beautiful beach",
        ...     sentiment="positive",
        ...     confidence_score=0.8
        ... )
        >>> validate_entity_quality(entity)
        True
    """
    # Check confidence_score is valid
    if entity.confidence_score is None:
        logger.warning(f"Entity '{entity.entity_name}' missing confidence_score, rejecting")
        return False

    if entity.confidence_score < 0.1:
        if entity.confidence_score == 0.0:
            logger.error(
                f"Entity '{entity.entity_name}' has confidence_score=0.0 (BUG DETECTED - schema default issue). "
                f"This should never happen after fix. Rejecting entity."
            )
        else:
            logger.warning(
                f"Entity '{entity.entity_name}' has confidence_score={entity.confidence_score:.2f} < 0.1, rejecting"
            )
        return False

    if entity.confidence_score > 1.0:
        logger.warning(
            f"Entity '{entity.entity_name}' has confidence_score={entity.confidence_score:.2f} > 1.0, rejecting"
        )
        return False

    # Check if entity_name is a generic city or country (should be specific places)
    if _is_generic_location(entity.entity_name):
        logger.warning(
            f"Entity '{entity.entity_name}' is a generic city/country name (should be specific place), rejecting"
        )
        return False

    return True


def validate_traveler_profile_quality(profile: TravelerProfile) -> bool:
    """
    Validate traveler profile has proper confidence_score.

    Args:
        profile: TravelerProfile object to validate

    Returns:
        True if profile passes validation, False otherwise (will use default)

    Example:
        >>> profile = TravelerProfile(
        ...     traveler_type="solo",
        ...     budget_tier="budget",
        ...     confidence_score=0.7
        ... )
        >>> validate_traveler_profile_quality(profile)
        True
    """
    if profile.confidence_score is None:
        logger.warning("Traveler profile missing confidence_score")
        return False

    if profile.confidence_score < 0.1:
        if profile.confidence_score == 0.0:
            logger.error(
                f"Traveler profile has confidence_score=0.0 (BUG DETECTED - schema default issue). "
                f"This should never happen after fix."
            )
        logger.warning(f"Traveler profile confidence_score={profile.confidence_score:.2f} < 0.1")
        return False

    if profile.confidence_score > 1.0:
        logger.warning(f"Traveler profile confidence_score={profile.confidence_score:.2f} > 1.0")
        return False

    return True


# =============================================================================
# Video Classification Helpers
# =============================================================================

def classify_video_length(duration_seconds: float) -> Literal["short", "long"]:
    """
    Classify video length to determine extraction strategy.

    Args:
        duration_seconds: Video duration in seconds (from Stage 1 data)

    Returns:
        "short" if video is < 1200 seconds (20 minutes)
        "long" if video is >= 1200 seconds (20 minutes)

    Usage:
        This classification helps determine which extraction method to use:
        - short videos: Single-pass extraction (entire transcript in one LLM call)
        - long videos: Hierarchical extraction (chunk → extract → merge)

    Example:
        >>> classify_video_length(600)  # 10 minutes
        'short'
        >>> classify_video_length(1500)  # 25 minutes
        'long'
        >>> classify_video_length(1200)  # Exactly 20 minutes
        'long'
    """
    # Threshold: 20 minutes = 1200 seconds
    # Optimized for single-pass LLM extraction of typical travel vlog segments
    THRESHOLD_SECONDS = 1200

    if duration_seconds < THRESHOLD_SECONDS:
        return "short"
    else:
        return "long"


def calculate_word_count(transcript: List[Dict[str, Any]]) -> int:
    """
    Estimate word count from transcript segments.

    Args:
        transcript: List of transcript segments from Stage 1
            Format: [{"text": "...", "start": 0.0, "duration": 1.0}, ...]

    Returns:
        Total estimated word count across all segments

    Usage:
        Word count helps estimate token usage for LLM calls:
        - ~750 words ≈ 1000 tokens (English)
        - ~500 words ≈ 1000 tokens (Hindi/non-English)

        This can be used alongside video length to determine:
        - Whether to chunk the transcript
        - Expected token cost
        - Processing time estimates

    Example:
        >>> transcript = [
        ...     {"text": "Hello world", "start": 0.0, "duration": 1.0},
        ...     {"text": "How are you", "start": 1.0, "duration": 1.0}
        ... ]
        >>> calculate_word_count(transcript)
        5
    """
    if not transcript:
        return 0

    total_words = 0

    for segment in transcript:
        text = segment.get('text', '')
        if text and text.strip():
            # Split by whitespace and count non-empty tokens
            words = text.strip().split()
            total_words += len(words)

    return total_words


def estimate_tokens_from_transcript(
    transcript: List[Dict[str, Any]],
    language: str = "en"
) -> int:
    """
    Estimate token count for LLM processing.

    Args:
        transcript: List of transcript segments from Stage 1
        language: Language code (affects token estimation ratio)

    Returns:
        Estimated token count for the transcript

    Usage:
        Token estimates help:
        - Determine if chunking is needed (most LLMs have 8k-32k token limits)
        - Estimate API costs before processing
        - Plan batch sizes for concurrent processing

        Token estimation ratios (approximate):
        - English: 1 token ≈ 0.75 words (4 chars)
        - Hindi/Arabic: 1 token ≈ 0.5 words (2 chars)
        - Chinese/Japanese: 1 token ≈ 0.5-1 characters

    Example:
        >>> transcript = [{"text": "Hello world " * 100, "start": 0.0, "duration": 10.0}]
        >>> estimate_tokens_from_transcript(transcript, language="en")
        267  # ~200 words * 1.33 tokens/word
    """
    word_count = calculate_word_count(transcript)

    if word_count == 0:
        return 0

    # Token estimation ratios by language
    # Format: tokens per word (approximate)
    TOKEN_RATIOS = {
        "en": 1.33,  # English: ~0.75 words per token
        "es": 1.33,  # Spanish: similar to English
        "fr": 1.33,  # French: similar to English
        "de": 1.33,  # German: similar to English
        "hi": 2.0,   # Hindi: ~0.5 words per token (Devanagari script)
        "ar": 2.0,   # Arabic: ~0.5 words per token
        "zh-cn": 1.5,  # Chinese: ~0.5-1 char per token
        "ja": 1.5,   # Japanese: ~0.5-1 char per token
        "ko": 1.5,   # Korean: ~0.5-1 char per token
    }

    # Default to English ratio if language not found
    ratio = TOKEN_RATIOS.get(language, 1.33)

    estimated_tokens = int(word_count * ratio)

    return estimated_tokens


def should_chunk_transcript(
    transcript: List[Dict[str, Any]],
    language: str = "en",
    max_tokens: int = 6000
) -> bool:
    """
    Determine if transcript should be chunked for LLM processing.

    Args:
        transcript: List of transcript segments from Stage 1
        language: Language code (affects token estimation)
        max_tokens: Maximum tokens for a single LLM call (default: 6000)
            Note: Most LLMs support 8k-32k tokens, but we leave headroom
            for system prompts, examples, and output tokens

    Returns:
        True if transcript should be chunked, False otherwise

    Usage:
        Use this before calling extract_entities_single() to determine
        if the video needs hierarchical extraction:

        if should_chunk_transcript(transcript, language):
            # Use hierarchical extraction (chunk → extract → merge)
            results = extract_entities_hierarchical(...)
        else:
            # Use single-pass extraction
            results = extract_entities_single(...)

    Example:
        >>> # Short transcript (~500 words)
        >>> should_chunk_transcript(short_transcript, "en", max_tokens=6000)
        False

        >>> # Long transcript (~10,000 words)
        >>> should_chunk_transcript(long_transcript, "en", max_tokens=6000)
        True
    """
    estimated_tokens = estimate_tokens_from_transcript(transcript, language)

    return estimated_tokens > max_tokens


# =============================================================================
# Tiered Processing (Cost Optimization)
# =============================================================================

# Quality thresholds for tiered processing
TIERED_MIN_ENTITIES_SHORT = 3  # Minimum entities for short video to be acceptable
TIERED_MIN_ENTITIES_LONG = 15  # Minimum entities for long video to be acceptable
TIERED_MIN_CONFIDENCE = 0.5  # Minimum profile confidence to be acceptable


def assess_extraction_quality_for_tiered(
    entities: List[EntityExperience],
    traveler_profile: TravelerProfile,
    is_long_video: bool = False
) -> Tuple[str, bool]:
    """
    Assess extraction quality to determine if escalation is needed.

    Args:
        entities: List of extracted entities
        traveler_profile: Extracted traveler profile
        is_long_video: Whether this is a long video (higher thresholds)

    Returns:
        Tuple of (quality_level, needs_escalation)
        - quality_level: "high", "medium", or "low"
        - needs_escalation: True if quality is too low and should retry with better model
    """
    entity_count = len(entities)
    confidence = traveler_profile.confidence_score

    # Thresholds based on video length
    min_entities = TIERED_MIN_ENTITIES_LONG if is_long_video else TIERED_MIN_ENTITIES_SHORT
    high_threshold = min_entities * 2

    # Determine quality level
    if entity_count >= high_threshold and confidence >= 0.7:
        quality = "high"
        needs_escalation = False
    elif entity_count >= min_entities and confidence >= TIERED_MIN_CONFIDENCE:
        quality = "medium"
        needs_escalation = False
    else:
        quality = "low"
        # Escalate if we got very few entities or very low confidence
        needs_escalation = entity_count < min_entities or confidence < 0.3

    return quality, needs_escalation


def extract_with_tiered_processing(
    prompt: str,
    is_long_video: bool = False,
    cheap_provider: str = "gemini",
    capable_provider: str = "gemini",
    cheap_model_override: Optional[str] = None,
    capable_model_override: Optional[str] = None,
    max_retries: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Tiered LLM extraction: Try cheap model first, escalate if quality is low.

    This strategy can reduce costs by 40-60% by using cheaper models for
    "easy" extractions and only escalating to capable models when needed.

    Tier 1 (Cheap): Gemini Flash Lite / DeepSeek
    Tier 2 (Capable): Gemini Pro / GPT-4o-mini

    Args:
        prompt: Full extraction prompt
        is_long_video: Whether processing a long video (affects thresholds)
        cheap_provider: Provider for tier 1 (default: "gemini")
        capable_provider: Provider for tier 2 (default: "gemini")
        cheap_model_override: Override model for cheap tier
        capable_model_override: Override model for capable tier
        max_retries: Max retries per tier
        temperature: LLM temperature
        max_tokens: Max output tokens

    Returns:
        Dict with extraction results including:
        - success: bool
        - data: parsed JSON
        - tokens_used: dict
        - cost_usd: float
        - tier_used: "cheap" or "capable"
        - escalated: bool (True if escalated from cheap to capable)

    Example:
        >>> result = extract_with_tiered_processing(prompt, is_long_video=False)
        >>> if result['success']:
        ...     print(f"Used tier: {result['tier_used']}, cost: ${result['cost_usd']:.4f}")
    """
    from src.utils.llm_client import extract_with_llm
    from src.utils.config import config

    total_cost = 0.0
    total_tokens = {"input": 0, "output": 0, "total": 0}

    # Tier 1: Try with cheap model
    logger.info(f"Tiered extraction: Starting with cheap model ({cheap_provider})")

    tier1_result = extract_with_llm(
        prompt=prompt,
        provider=cheap_provider,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=max_tokens
    )

    total_cost += tier1_result.get('cost_usd', 0)
    tier1_tokens = tier1_result.get('tokens_used', {})
    total_tokens['input'] += tier1_tokens.get('input', 0)
    total_tokens['output'] += tier1_tokens.get('output', 0)
    total_tokens['total'] += tier1_tokens.get('total', 0)

    # Check if tier 1 succeeded
    if tier1_result['success']:
        data = tier1_result['data']

        # Parse entities and profile to assess quality
        entities_data = data.get('entities', [])
        profile_data = data.get('traveler_profile', {})

        entity_count = len(entities_data)
        profile_confidence = profile_data.get('confidence_score', 0.3)

        # Quick quality check
        min_entities = TIERED_MIN_ENTITIES_LONG if is_long_video else TIERED_MIN_ENTITIES_SHORT

        if entity_count >= min_entities and profile_confidence >= TIERED_MIN_CONFIDENCE:
            # Quality is acceptable, return tier 1 result
            logger.info(
                f"Tiered extraction: Cheap model sufficient "
                f"({entity_count} entities, confidence={profile_confidence:.2f})"
            )
            return {
                "success": True,
                "data": data,
                "tokens_used": total_tokens,
                "cost_usd": total_cost,
                "model": tier1_result.get('model', 'unknown'),
                "provider": tier1_result.get('provider', cheap_provider),
                "tier_used": "cheap",
                "escalated": False,
                "error": None
            }
        else:
            logger.info(
                f"Tiered extraction: Quality too low "
                f"({entity_count} entities < {min_entities}, confidence={profile_confidence:.2f}), escalating..."
            )
    else:
        logger.warning(f"Tiered extraction: Cheap model failed, escalating...")

    # Tier 2: Escalate to capable model
    logger.info(f"Tiered extraction: Escalating to capable model ({capable_provider})")

    # Use a more capable model configuration
    tier2_result = extract_with_llm(
        prompt=prompt,
        provider=capable_provider,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=max_tokens
    )

    total_cost += tier2_result.get('cost_usd', 0)
    tier2_tokens = tier2_result.get('tokens_used', {})
    total_tokens['input'] += tier2_tokens.get('input', 0)
    total_tokens['output'] += tier2_tokens.get('output', 0)
    total_tokens['total'] += tier2_tokens.get('total', 0)

    if tier2_result['success']:
        logger.info(
            f"Tiered extraction: Capable model succeeded "
            f"(total cost: ${total_cost:.4f})"
        )
        return {
            "success": True,
            "data": tier2_result['data'],
            "tokens_used": total_tokens,
            "cost_usd": total_cost,
            "model": tier2_result.get('model', 'unknown'),
            "provider": tier2_result.get('provider', capable_provider),
            "tier_used": "capable",
            "escalated": True,
            "error": None
        }
    else:
        logger.error(f"Tiered extraction: Both tiers failed")
        return {
            "success": False,
            "data": tier1_result.get('data'),  # Return tier 1 data if any
            "tokens_used": total_tokens,
            "cost_usd": total_cost,
            "model": tier2_result.get('model', 'unknown'),
            "provider": tier2_result.get('provider', capable_provider),
            "tier_used": "failed",
            "escalated": True,
            "error": tier2_result.get('error', 'Both tiers failed')
        }


# =============================================================================
# Split Prompt Extraction (Improved Accuracy)
# =============================================================================

def extract_with_split_prompts(
    title: str,
    duration_minutes: float,
    language: str,
    transcript_text: str,
    enable_enrichment: bool = False,
    provider: Optional[str] = None,
    max_retries: int = 3,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    description: str = "",
    tags: list = None,
    view_count: int = 0
) -> Dict[str, Any]:
    """
    Extract using split prompts for improved accuracy.

    This approach uses separate, focused prompts for each task:
    1. Profile extraction (focused on traveler characteristics)
    2. Entity extraction (focused on places, activities, etc.)
    3. (Optional) Entity enrichment (adds missing practical details)

    Benefits:
    - Clearer instructions for each task
    - Better accuracy per task
    - Can use different models/temperatures per task

    Trade-offs:
    - 2-3x more API calls
    - Higher total latency
    - Slightly higher cost (but better results)

    Args:
        title: Video title
        duration_minutes: Video duration in minutes
        language: Language code
        transcript_text: Combined transcript text
        enable_enrichment: Run optional enrichment pass (default: False)
        provider: LLM provider (default: from config)
        max_retries: Max retries per call
        temperature: LLM temperature
        max_tokens: Max output tokens

    Returns:
        Dict with combined results:
        {
            "success": bool,
            "traveler_profile": {...},
            "entities": [...],
            "tokens_used": dict,
            "cost_usd": float,
            "passes_completed": int
        }
    """
    total_cost = 0.0
    total_tokens = {"input": 0, "output": 0, "total": 0}
    passes_completed = 0

    # Pass 1: Extract traveler profile
    logger.info("Split extraction: Pass 1 - Traveler profile")
    profile_prompt = format_profile_only_prompt(
        title=title,
        duration_minutes=duration_minutes,
        language=language,
        transcript=transcript_text,
        description=description,
        tags=tags,
        view_count=view_count
    )

    profile_result = extract_with_llm(
        prompt=profile_prompt,
        provider=provider,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=1000  # Profile is small
    )

    total_cost += profile_result.get('cost_usd', 0)
    profile_tokens = profile_result.get('tokens_used', {})
    total_tokens['input'] += profile_tokens.get('input', 0)
    total_tokens['output'] += profile_tokens.get('output', 0)
    total_tokens['total'] += profile_tokens.get('total', 0)

    if not profile_result['success']:
        logger.error("Split extraction: Profile extraction failed")
        return {
            "success": False,
            "traveler_profile": None,
            "entities": [],
            "tokens_used": total_tokens,
            "cost_usd": total_cost,
            "passes_completed": 0,
            "error": profile_result.get('error')
        }

    traveler_profile = profile_result['data'].get('traveler_profile', {})
    passes_completed = 1
    logger.info(f"Split extraction: Profile extracted (confidence={traveler_profile.get('confidence_score', 0):.2f})")

    # Pass 2: Extract entities
    logger.info("Split extraction: Pass 2 - Entities")
    entities_prompt = format_entities_only_prompt(
        title=title,
        duration_minutes=duration_minutes,
        language=language,
        transcript=transcript_text,
        description=description,
        tags=tags,
        view_count=view_count
    )

    entities_result = extract_with_llm(
        prompt=entities_prompt,
        provider=provider,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=max_tokens
    )

    total_cost += entities_result.get('cost_usd', 0)
    entities_tokens = entities_result.get('tokens_used', {})
    total_tokens['input'] += entities_tokens.get('input', 0)
    total_tokens['output'] += entities_tokens.get('output', 0)
    total_tokens['total'] += entities_tokens.get('total', 0)

    if not entities_result['success']:
        logger.error("Split extraction: Entity extraction failed")
        return {
            "success": False,
            "traveler_profile": traveler_profile,
            "entities": [],
            "tokens_used": total_tokens,
            "cost_usd": total_cost,
            "passes_completed": 1,
            "error": entities_result.get('error')
        }

    entities = entities_result['data'].get('entities', [])
    passes_completed = 2
    logger.info(f"Split extraction: {len(entities)} entities extracted")

    # Pass 3 (Optional): Enrich entities
    if enable_enrichment and entities:
        logger.info("Split extraction: Pass 3 - Entity enrichment")

        enrichment_prompt = format_entity_enrichment_prompt(
            title=title,
            duration_minutes=duration_minutes,
            language=language,
            entities_json=json.dumps(entities, indent=2),
            transcript=transcript_text,
            description=description,
            tags=tags,
            view_count=view_count
        )

        enrichment_result = extract_with_llm(
            prompt=enrichment_prompt,
            provider=provider,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens=max_tokens
        )

        total_cost += enrichment_result.get('cost_usd', 0)
        enrichment_tokens = enrichment_result.get('tokens_used', {})
        total_tokens['input'] += enrichment_tokens.get('input', 0)
        total_tokens['output'] += enrichment_tokens.get('output', 0)
        total_tokens['total'] += enrichment_tokens.get('total', 0)

        if enrichment_result['success']:
            enriched_entities = enrichment_result['data'].get('entities', entities)
            entities = enriched_entities
            passes_completed = 3
            logger.info(f"Split extraction: Entities enriched")
        else:
            logger.warning("Split extraction: Enrichment failed, using unenriched entities")

    logger.info(
        f"Split extraction complete: {passes_completed} passes, "
        f"{len(entities)} entities, ${total_cost:.4f}"
    )

    return {
        "success": True,
        "traveler_profile": traveler_profile,
        "entities": entities,
        "tokens_used": total_tokens,
        "cost_usd": total_cost,
        "passes_completed": passes_completed,
        "provider": entities_result.get('provider', provider),
        "model": entities_result.get('model', 'unknown'),
        "error": None
    }


# =============================================================================
# Video Processing Functions
# =============================================================================

def process_short_video(
    video_data: Dict[str, Any],
    raw_file_path: Optional[str] = None,
    translate_non_english: bool = True
) -> Optional[Stage2Output]:
    """
    Process a short video (< 20 min) using single-pass LLM extraction.

    Args:
        video_data: Video data from Stage 1 with fields:
            - source_id: Video ID (required)
            - title: Video title (required)
            - duration_seconds: Duration in seconds (required)
            - language: Language code (required)
            - transcript: List of segments (required)
        raw_file_path: S3 path to raw JSONL file (for provenance)
        translate_non_english: If True, translate non-English to English

    Returns:
        Stage2Output object with extracted data, or None if extraction failed

    Raises:
        ValueError: If required fields are missing
        Exception: Other extraction errors (logged but not raised)

    Example:
        >>> video = {
        ...     "source_id": "abc123",
        ...     "title": "Phuket Travel Guide",
        ...     "duration_seconds": 750,
        ...     "language": "en",
        ...     "transcript": [{"text": "...", "start": 0.0, "duration": 1.0}]
        ... }
        >>> result = process_short_video(video)
        >>> if result:
        ...     print(f"Extracted {len(result.entities)} entities")
    """
    try:
        # Step 1: Validate required fields
        logger.info(f"Processing short video: {video_data.get('source_id', 'unknown')}")

        required_fields = ['source_id', 'title', 'duration_seconds', 'language', 'transcript']
        missing_fields = [f for f in required_fields if f not in video_data]

        if missing_fields:
            raise ValueError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        source_id = video_data['source_id']
        title = video_data['title']
        duration_seconds = video_data['duration_seconds']
        language = video_data['language']
        transcript = video_data['transcript']

        # Extract metadata (optional fields)
        description = video_data.get('description', '')
        metadata = video_data.get('metadata', {})
        tags = metadata.get('tags', []) if isinstance(metadata, dict) else []
        view_count = metadata.get('view_count', 0) if isinstance(metadata, dict) else 0

        if not transcript:
            logger.warning(f"Empty transcript for video {source_id}")
            return None

        # Step 2: Translate transcript if non-English
        working_transcript = transcript
        working_language = language

        if translate_non_english and language != 'en':
            if not TRANSLATOR_AVAILABLE:
                logger.warning(
                    f"Translation requested but translator unavailable. "
                    f"Proceeding with original {language} transcript for {source_id}"
                )
            else:
                logger.info(f"Translating {language} transcript to English for {source_id}")
                try:
                    translated = translate_transcript(
                        transcript=transcript,
                        source_lang=language,
                        preserve_original=True
                    )
                    working_transcript = translated
                    working_language = 'en'
                    logger.info(f"Translation complete for {source_id}")
                except Exception as e:
                    logger.error(f"Translation failed for {source_id}: {e}")
                    # Continue with original transcript
                    logger.info(f"Proceeding with original {language} transcript")

        # Step 3: Combine transcript segments into text
        transcript_text = "\n".join([
            f"[{seg['start']:.1f}s] {seg['text']}"
            for seg in working_transcript
        ])

        logger.debug(
            f"Combined transcript: {len(transcript_text)} chars, "
            f"{len(working_transcript)} segments"
        )

        # Step 4: Build prompt using template
        prompt = format_single_pass_prompt(
            title=title,
            duration_minutes=duration_seconds / 60,
            language=working_language,
            transcript=transcript_text,
            description=description,
            tags=tags,
            view_count=view_count
        )

        logger.debug(f"Prompt length: {len(prompt)} chars")

        # Step 5: Call LLM for extraction
        logger.info(f"Calling LLM for entity extraction: {source_id}")

        llm_result = extract_with_llm(
            prompt=prompt,
            max_retries=3,
            temperature=0.3,
            max_tokens=4000
        )

        if not llm_result['success']:
            logger.error(
                f"LLM extraction failed for {source_id}: {llm_result.get('error', 'Unknown error')}"
            )
            return None

        extracted_data = llm_result['data']
        tokens_used = llm_result['tokens_used']['total']
        cost_usd = llm_result['cost_usd']
        llm_provider = llm_result.get('provider', 'unknown')
        llm_model = llm_result.get('model', 'unknown')

        logger.info(
            f"LLM extraction successful for {source_id}: "
            f"{tokens_used} tokens, ${cost_usd:.4f}"
        )

        # Step 6: Parse and validate with Pydantic schemas
        logger.debug(f"Validating extracted data for {source_id}")

        # Parse traveler profile with validation
        try:
            traveler_profile_data = extracted_data.get('traveler_profile', {})
            traveler_profile = TravelerProfile(**traveler_profile_data)

            # Validate profile quality
            if not validate_traveler_profile_quality(traveler_profile):
                logger.warning(f"Traveler profile failed validation for {source_id}, using default")
                traveler_profile = TravelerProfile(confidence_score=0.1)
        except Exception as e:
            logger.error(f"Failed to parse traveler profile for {source_id}: {e}")
            # Use default profile with minimum confidence
            traveler_profile = TravelerProfile(confidence_score=0.1)

        # Parse entities with validation
        entities = []
        entities_data = extracted_data.get('entities', [])
        rejected_count = 0

        for i, entity_data in enumerate(entities_data):
            try:
                # Normalize entity_type to valid schema value
                if 'entity_type' in entity_data:
                    original_type = entity_data['entity_type']
                    normalized_type = normalize_entity_type(
                        entity_type=original_type,
                        entity_name=entity_data.get('entity_name', '')
                    )
                    if original_type != normalized_type:
                        logger.info(
                            f"Entity {i+1} '{entity_data.get('entity_name', 'unknown')}': "
                            f"entity_type '{original_type}' -> '{normalized_type}'"
                        )
                        entity_data['entity_type'] = normalized_type

                # Truncate cost_mentioned if it exceeds max length (100 chars)
                if 'cost_mentioned' in entity_data and entity_data['cost_mentioned']:
                    if len(entity_data['cost_mentioned']) > 100:
                        entity_data['cost_mentioned'] = entity_data['cost_mentioned'][:97] + "..."
                        logger.debug(f"Truncated long cost_mentioned for entity {i+1}")

                entity = EntityExperience(**entity_data)

                # Validate quality score
                if not validate_entity_quality(entity):
                    rejected_count += 1
                    logger.warning(f"Rejected entity {i+1}/{len(entities_data)}: {entity.entity_name}")
                    continue

                entities.append(entity)
            except Exception as e:
                logger.warning(
                    f"Failed to parse entity {i+1} for {source_id}: {e}. "
                    f"Entity data: {entity_data}"
                )
                rejected_count += 1
                # Skip invalid entities
                continue

        logger.info(
            f"Parsed {len(entities)} valid entities for {source_id} "
            f"(rejected {rejected_count}/{len(entities_data)} due to validation failures)"
        )

        # Step 7: Create Stage2Output with provenance metadata
        content_id = f"youtube_{source_id}"

        # Determine extraction quality based on entities and confidence
        if len(entities) >= 5 and traveler_profile.confidence_score >= 0.7:
            extraction_quality = "high"
        elif len(entities) >= 2 and traveler_profile.confidence_score >= 0.5:
            extraction_quality = "medium"
        else:
            extraction_quality = "low"

        # Build processing notes
        processing_notes = []
        if language != 'en' and working_language == 'en':
            processing_notes.append(f"Translated from {language} to English")
        if len(entities) != len(entities_data):
            processing_notes.append(
                f"Skipped {len(entities_data) - len(entities)} invalid entities"
            )

        stage2_output = Stage2Output(
            content_id=content_id,
            source_id=source_id,
            language=language,  # Original language
            processed_at=datetime.now(timezone.utc),
            llm_model=f"{llm_provider}:{llm_model}",  # e.g., "deepseek:deepseek-chat"
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            traveler_profile=traveler_profile,
            entities=entities,
            extraction_quality=extraction_quality,
            processing_notes=" | ".join(processing_notes) if processing_notes else None
        )

        # Add provenance if available
        if raw_file_path:
            logger.debug(f"Adding provenance: {raw_file_path}")

        logger.info(
            f"Successfully processed {source_id}: "
            f"{len(entities)} entities, quality={extraction_quality}"
        )

        return stage2_output

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise

    except Exception as e:
        logger.error(
            f"Unexpected error processing video {video_data.get('source_id', 'unknown')}: {e}",
            exc_info=True
        )
        return None


# =============================================================================
# Transcript Chunking Helpers
# =============================================================================

def split_transcript_into_chunks(
    transcript: List[Dict[str, Any]],
    chunk_duration_seconds: float = 300,  # 5 minutes
    overlap_seconds: float = 60  # 1 minute
) -> List[List[Dict[str, Any]]]:
    """
    Split transcript into overlapping time-based chunks.

    Args:
        transcript: List of transcript segments from Stage 1
            Format: [{"text": "...", "start": 0.0, "duration": 1.0}, ...]
        chunk_duration_seconds: Duration of each chunk (default: 300s = 5 min)
        overlap_seconds: Overlap between chunks (default: 60s = 1 min)

    Returns:
        List of transcript chunks, where each chunk is a list of segments

    Example:
        >>> transcript = [
        ...     {"text": "Hello", "start": 0.0, "duration": 5.0},
        ...     {"text": "World", "start": 5.0, "duration": 5.0},
        ...     {"text": "Foo", "start": 300.0, "duration": 5.0}
        ... ]
        >>> chunks = split_transcript_into_chunks(transcript, chunk_duration_seconds=300, overlap_seconds=60)
        >>> len(chunks)
        2
        >>> # Chunk 1: 0-300s, Chunk 2: 240-540s (with 60s overlap)
    """
    if not transcript:
        return []

    chunks = []

    # Calculate total duration
    last_segment = transcript[-1]
    total_duration = last_segment['start'] + last_segment.get('duration', 0)

    # Calculate chunk boundaries
    chunk_start = 0.0

    while chunk_start < total_duration:
        chunk_end = chunk_start + chunk_duration_seconds

        # Collect segments in this chunk
        chunk_segments = []
        for segment in transcript:
            seg_start = segment['start']
            seg_end = seg_start + segment.get('duration', 0)

            # Include segment if it overlaps with chunk time range
            if seg_start < chunk_end and seg_end > chunk_start:
                chunk_segments.append(segment)

        if chunk_segments:
            chunks.append(chunk_segments)

        # Move to next chunk (with overlap)
        chunk_start += (chunk_duration_seconds - overlap_seconds)

    return chunks


# =============================================================================
# Semantic Chunking (Improved - Topic Boundary Detection)
# =============================================================================

# Patterns that indicate topic shifts in travel vlogs
TOPIC_SHIFT_PATTERNS = [
    # Day/time markers
    r"\b(day\s*\d+|day\s+one|day\s+two|day\s+three|first\s+day|second\s+day|third\s+day)\b",
    r"\b(next\s+day|the\s+following\s+day|the\s+next\s+morning|that\s+evening)\b",
    r"\b(in\s+the\s+morning|in\s+the\s+afternoon|in\s+the\s+evening|at\s+night)\b",

    # Location transitions
    r"\b(now\s+let'?s?\s+(go|head|move|visit|check\s+out|explore))\b",
    r"\b(moving\s+on\s+to|heading\s+to|next\s+stop|next\s+up|off\s+to)\b",
    r"\b(we\s+(arrived|got|reached|made\s+it)\s+(at|to|in))\b",
    r"\b(after\s+that|from\s+there|then\s+we)\b",

    # Topic markers
    r"\b(for\s+(food|accommodation|hotels?|restaurants?|activities|transport))\b",
    r"\b(when\s+it\s+comes\s+to|speaking\s+of|talking\s+about|as\s+for)\b",
    r"\b(one\s+thing\s+(to|you\s+should)|tip\s+number|my\s+(top|best)\s+tip)\b",

    # Section markers common in vlogs
    r"\b(okay\s+so|alright\s+so|so\s+anyway|anyway|moving\s+on)\b",
    r"\b(let\s+me\s+(show|tell|take)\s+you)\b",
]

# Compile patterns for efficiency
COMPILED_TOPIC_PATTERNS = [re.compile(p, re.IGNORECASE) for p in TOPIC_SHIFT_PATTERNS]


def detect_topic_shift(text: str) -> bool:
    """
    Detect if text contains a topic shift indicator.

    Args:
        text: Text segment to check

    Returns:
        True if text contains a topic shift pattern
    """
    for pattern in COMPILED_TOPIC_PATTERNS:
        if pattern.search(text):
            return True
    return False


def split_transcript_semantically(
    transcript: List[Dict[str, Any]],
    min_chunk_duration_seconds: float = 120,  # Minimum 2 minutes
    max_chunk_duration_seconds: float = 420,  # Maximum 7 minutes
    target_chunk_duration_seconds: float = 300,  # Target 5 minutes
    overlap_segments: int = 3  # Number of segments to overlap
) -> List[List[Dict[str, Any]]]:
    """
    Split transcript into semantic chunks based on topic boundaries.

    This improved chunking strategy:
    1. Identifies natural topic shifts (day changes, location changes, topic markers)
    2. Respects minimum/maximum chunk sizes
    3. Falls back to time-based splitting if no topic shifts detected
    4. Adds small overlap to prevent entity loss at boundaries

    Args:
        transcript: List of transcript segments from Stage 1
        min_chunk_duration_seconds: Minimum chunk duration (default: 120s = 2 min)
        max_chunk_duration_seconds: Maximum chunk duration (default: 420s = 7 min)
        target_chunk_duration_seconds: Target chunk duration (default: 300s = 5 min)
        overlap_segments: Number of segments to overlap between chunks (default: 3)

    Returns:
        List of transcript chunks, where each chunk is a list of segments

    Example:
        >>> chunks = split_transcript_semantically(transcript)
        >>> for i, chunk in enumerate(chunks):
        ...     print(f"Chunk {i+1}: {len(chunk)} segments")
    """
    if not transcript:
        return []

    chunks = []
    current_chunk = []
    current_chunk_start = 0.0
    current_chunk_duration = 0.0

    for i, segment in enumerate(transcript):
        seg_start = segment.get('start', 0.0)
        seg_duration = segment.get('duration', 0.0)
        seg_text = segment.get('text', '')

        # Calculate time since chunk start
        if current_chunk:
            current_chunk_duration = seg_start - current_chunk_start

        # Check if we should start a new chunk
        should_split = False
        split_reason = None

        # Rule 1: Don't split if chunk is too small
        if current_chunk_duration < min_chunk_duration_seconds:
            should_split = False

        # Rule 2: Force split if chunk is too large
        elif current_chunk_duration >= max_chunk_duration_seconds:
            should_split = True
            split_reason = "max_duration"

        # Rule 3: Split at topic boundaries if chunk is past minimum size
        elif current_chunk_duration >= min_chunk_duration_seconds:
            if detect_topic_shift(seg_text):
                should_split = True
                split_reason = "topic_shift"

        # Rule 4: Split at target duration if no topic shift found
        elif current_chunk_duration >= target_chunk_duration_seconds:
            # Look ahead for nearby topic shift
            lookahead_window = 5  # segments
            topic_shift_nearby = False
            for j in range(i, min(i + lookahead_window, len(transcript))):
                if detect_topic_shift(transcript[j].get('text', '')):
                    topic_shift_nearby = True
                    break

            if not topic_shift_nearby:
                should_split = True
                split_reason = "target_duration"

        # Execute split if needed
        if should_split and current_chunk:
            chunks.append(current_chunk)
            logger.debug(
                f"Created chunk {len(chunks)}: {len(current_chunk)} segments, "
                f"{current_chunk_duration:.1f}s, reason={split_reason}"
            )

            # Start new chunk with overlap from previous
            if overlap_segments > 0 and len(current_chunk) > overlap_segments:
                current_chunk = current_chunk[-overlap_segments:]
                current_chunk_start = current_chunk[0].get('start', seg_start)
            else:
                current_chunk = []
                current_chunk_start = seg_start

        # Add segment to current chunk
        current_chunk.append(segment)
        if not current_chunk_start:
            current_chunk_start = seg_start

    # Add final chunk if non-empty
    if current_chunk:
        chunks.append(current_chunk)
        logger.debug(f"Created final chunk {len(chunks)}: {len(current_chunk)} segments")

    # Log summary
    total_duration = transcript[-1].get('start', 0) + transcript[-1].get('duration', 0) if transcript else 0
    logger.info(
        f"Semantic chunking: {len(transcript)} segments ({total_duration:.0f}s) -> "
        f"{len(chunks)} chunks"
    )

    return chunks


# =============================================================================
# Fuzzy Deduplication Helpers
# =============================================================================

def calculate_entity_similarity(
    e1: EntityExperience,
    e2: EntityExperience,
    name_weight: float = 0.7,
    location_weight: float = 0.3
) -> float:
    """
    Calculate similarity score between two entities using fuzzy matching.

    Args:
        e1: First entity
        e2: Second entity
        name_weight: Weight for name similarity (default: 0.7)
        location_weight: Weight for location similarity (default: 0.3)

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not RAPIDFUZZ_AVAILABLE:
        # Fallback to exact matching
        name_match = e1.entity_name.lower().strip() == e2.entity_name.lower().strip()
        loc1 = (e1.location or "").lower().strip()
        loc2 = (e2.location or "").lower().strip()
        loc_match = loc1 == loc2 or not loc1 or not loc2
        return 1.0 if name_match and loc_match else 0.0

    # Calculate name similarity using rapidfuzz
    name1 = e1.entity_name.lower().strip()
    name2 = e2.entity_name.lower().strip()

    # Use token_sort_ratio for better handling of word order variations
    # "Big Buddha Temple" vs "Temple of Big Buddha"
    name_sim = fuzz.token_sort_ratio(name1, name2) / 100.0

    # Also check if one name contains the other (substring match)
    if name1 in name2 or name2 in name1:
        name_sim = max(name_sim, 0.85)

    # Calculate location similarity
    loc1 = (e1.location or "").lower().strip()
    loc2 = (e2.location or "").lower().strip()

    if not loc1 or not loc2:
        # If either location is missing, only use name similarity
        location_sim = 1.0 if not loc1 and not loc2 else 0.8
    else:
        location_sim = fuzz.token_sort_ratio(loc1, loc2) / 100.0
        # Boost if one location contains the other
        if loc1 in loc2 or loc2 in loc1:
            location_sim = max(location_sim, 0.9)

    # Weighted average
    return (name_sim * name_weight) + (location_sim * location_weight)


def are_entities_similar(
    e1: EntityExperience,
    e2: EntityExperience,
    similarity_threshold: float = 0.75
) -> bool:
    """
    Check if two entities are similar enough to be considered duplicates.

    Uses fuzzy matching to handle:
    - Typos: "Patong Beach" vs "Patong Beech"
    - Variations: "Big Buddha" vs "The Big Buddha Temple"
    - Abbreviations: "Wat Chalong" vs "Wat Chalong Temple"

    Args:
        e1: First entity
        e2: Second entity
        similarity_threshold: Minimum similarity to consider as duplicate (default: 0.75)

    Returns:
        True if entities are similar enough to merge

    Example:
        >>> e1 = EntityExperience(entity_name="Patong Beach", ...)
        >>> e2 = EntityExperience(entity_name="Patong", ...)
        >>> are_entities_similar(e1, e2)
        True
    """
    # Quick check: same entity type required (or at least compatible)
    if e1.entity_type != e2.entity_type:
        # Allow some type flexibility (e.g., attraction and destination)
        compatible_types = [
            {'destination', 'attraction'},
            {'restaurant', 'shopping'},  # Food markets
        ]
        types = {e1.entity_type, e2.entity_type}
        if not any(types <= compat for compat in compatible_types):
            return False

    return calculate_entity_similarity(e1, e2) >= similarity_threshold


def merge_duplicate_entities(
    entities: List[EntityExperience],
    use_fuzzy_matching: bool = True,
    similarity_threshold: float = 0.75
) -> List[EntityExperience]:
    """
    Merge duplicate entities based on name and location.

    Deduplication strategy:
    - Group by similarity (fuzzy matching if enabled, else exact match)
    - For duplicates:
        - Combine experiences: "Experience 1. Experience 2."
        - Keep highest confidence_score
        - Keep earliest timestamp_start
        - If sentiments differ, use "mixed"
        - Combine cost_mentioned if different

    Args:
        entities: List of EntityExperience objects (possibly with duplicates)
        use_fuzzy_matching: Enable fuzzy matching for similarity (default: True)
        similarity_threshold: Minimum similarity for fuzzy matching (default: 0.75)

    Returns:
        Deduplicated list of EntityExperience objects

    Example:
        >>> entity1 = EntityExperience(entity_name="Patong Beach", location="Phuket", ...)
        >>> entity2 = EntityExperience(entity_name="Patong", location="Phuket", ...)
        >>> merged = merge_duplicate_entities([entity1, entity2])
        >>> len(merged)
        1  # Merged due to fuzzy matching
    """
    if not entities:
        return []

    # Use fuzzy matching if available and enabled
    if use_fuzzy_matching and RAPIDFUZZ_AVAILABLE:
        return _merge_entities_fuzzy(entities, similarity_threshold)
    else:
        return _merge_entities_exact(entities)


def _merge_entity_group(group: List[EntityExperience]) -> EntityExperience:
    """
    Merge a group of similar entities into one.

    Args:
        group: List of similar EntityExperience objects

    Returns:
        Single merged EntityExperience
    """
    if len(group) == 1:
        return group[0]

    # Use entity with highest confidence as base
    group_sorted = sorted(group, key=lambda e: -e.confidence_score)
    base = group_sorted[0]

    # Combine experiences
    experiences = []
    for ent in group:
        if ent.experience and ent.experience.strip():
            experiences.append(ent.experience.strip())

    # Remove duplicate experiences (case insensitive)
    unique_experiences = []
    seen = set()
    for exp in experiences:
        exp_lower = exp.lower()
        if exp_lower not in seen:
            unique_experiences.append(exp)
            seen.add(exp_lower)

    combined_experience = ". ".join(unique_experiences)

    # Keep highest confidence
    max_confidence = max(ent.confidence_score for ent in group)

    # Keep earliest timestamp
    timestamps = [ent.timestamp_start for ent in group if ent.timestamp_start is not None]
    earliest_timestamp = min(timestamps) if timestamps else None

    # Determine sentiment
    sentiments = set(ent.sentiment for ent in group)
    if len(sentiments) == 1:
        final_sentiment = group[0].sentiment
    else:
        final_sentiment = "mixed"

    # Combine costs
    costs = [ent.cost_mentioned for ent in group if ent.cost_mentioned]
    unique_costs = list(dict.fromkeys(costs))  # Preserve order, remove duplicates
    combined_cost = ", ".join(unique_costs) if unique_costs else None

    # Truncate if combined cost exceeds 100 chars
    if combined_cost and len(combined_cost) > 100:
        combined_cost = combined_cost[:97] + "..."

    # Create merged entity (removed temporal/logistics fields - now in Stage 3)
    merged = EntityExperience(
        entity_name=base.entity_name,  # Keep name from highest confidence entity
        entity_type=base.entity_type,
        location=base.location or next((e.location for e in group if e.location), None),
        experience=combined_experience[:2000],  # Limit to 2000 chars
        sentiment=final_sentiment,
        cost_mentioned=combined_cost,
        timestamp_start=earliest_timestamp,
        confidence_score=max_confidence
    )

    return merged


def _merge_entities_exact(entities: List[EntityExperience]) -> List[EntityExperience]:
    """
    Merge entities using exact string matching (original implementation).
    """
    # Group entities by (name, location) key
    entity_groups: Dict[tuple, List[EntityExperience]] = {}

    for entity in entities:
        # Create case-insensitive key
        name_key = entity.entity_name.lower().strip()
        location_key = (entity.location or "").lower().strip()
        key = (name_key, location_key)

        if key not in entity_groups:
            entity_groups[key] = []
        entity_groups[key].append(entity)

    # Merge duplicates in each group
    merged_entities = []

    for key, group in entity_groups.items():
        if len(group) == 1:
            merged_entities.append(group[0])
        else:
            logger.debug(f"Exact match: Merging {len(group)} duplicates for '{key[0]}'")
            merged_entities.append(_merge_entity_group(group))

    # Sort by timestamp (if available) then by confidence
    def sort_key(ent):
        timestamp = ent.timestamp_start if ent.timestamp_start is not None else float('inf')
        return (timestamp, -ent.confidence_score)

    merged_entities.sort(key=sort_key)

    logger.info(
        f"Exact deduplication: {len(entities)} -> {len(merged_entities)} entities "
        f"(removed {len(entities) - len(merged_entities)} duplicates)"
    )

    return merged_entities


def _merge_entities_fuzzy(
    entities: List[EntityExperience],
    similarity_threshold: float = 0.75
) -> List[EntityExperience]:
    """
    Merge entities using fuzzy string matching for better deduplication.

    Uses Union-Find algorithm for efficient clustering of similar entities.
    """
    if not entities:
        return []

    n = len(entities)

    # Union-Find data structure for clustering
    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Compare all pairs and union similar entities
    # O(n^2) but acceptable for typical entity counts (<200)
    fuzzy_matches = 0
    for i in range(n):
        for j in range(i + 1, n):
            if are_entities_similar(entities[i], entities[j], similarity_threshold):
                union(i, j)
                fuzzy_matches += 1

    # Group entities by their root parent
    groups: Dict[int, List[EntityExperience]] = {}
    for i, entity in enumerate(entities):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(entity)

    # Merge each group
    merged_entities = []
    for root, group in groups.items():
        if len(group) == 1:
            merged_entities.append(group[0])
        else:
            logger.debug(
                f"Fuzzy match: Merging {len(group)} entities: "
                f"{[e.entity_name for e in group]}"
            )
            merged_entities.append(_merge_entity_group(group))

    # Sort by timestamp (if available) then by confidence
    def sort_key(ent):
        timestamp = ent.timestamp_start if ent.timestamp_start is not None else float('inf')
        return (timestamp, -ent.confidence_score)

    merged_entities.sort(key=sort_key)

    logger.info(
        f"Fuzzy deduplication: {len(entities)} -> {len(merged_entities)} entities "
        f"(found {fuzzy_matches} fuzzy matches, removed {len(entities) - len(merged_entities)} duplicates)"
    )

    return merged_entities


# =============================================================================
# Long Video Processing
# =============================================================================

def process_long_video(
    video_data: Dict[str, Any],
    raw_file_path: Optional[str] = None,
    translate_non_english: bool = True,
    use_semantic_chunking: bool = True,
    use_fuzzy_deduplication: bool = True
) -> Optional[Stage2Output]:
    """
    Process a long video (>= 20 min) using hierarchical chunked LLM extraction.

    Strategy:
        1. Split transcript into chunks (semantic or time-based)
        2. Extract entities from each chunk separately using HIERARCHICAL_CHUNK_PROMPT
        3. Extract traveler profile from first chunk
        4. Merge all chunk results and deduplicate entities (fuzzy or exact)
        5. Return combined Stage2Output

    Args:
        video_data: Video data from Stage 1 with fields:
            - source_id: Video ID (required)
            - title: Video title (required)
            - duration_seconds: Duration in seconds (required)
            - language: Language code (required)
            - transcript: List of segments (required)
        raw_file_path: S3 path to raw JSONL file (for provenance)
        translate_non_english: If True, translate non-English to English
        use_semantic_chunking: Use semantic topic boundaries for chunking (default: True)
        use_fuzzy_deduplication: Use fuzzy matching for entity deduplication (default: True)

    Returns:
        Stage2Output object with merged data, or None if extraction failed

    Raises:
        ValueError: If required fields are missing
        Exception: Other extraction errors (logged but not raised)

    Example:
        >>> video = {
        ...     "source_id": "abc123",
        ...     "title": "Thailand 2-Week Itinerary",
        ...     "duration_seconds": 2400,  # 40 minutes
        ...     "language": "en",
        ...     "transcript": [{"text": "...", "start": 0.0, "duration": 1.0}, ...]
        ... }
        >>> result = process_long_video(video)
        >>> if result:
        ...     print(f"Extracted {len(result.entities)} entities from {len(chunks)} chunks")
    """
    try:
        # Step 1: Validate required fields
        logger.info(f"Processing long video: {video_data.get('source_id', 'unknown')}")

        required_fields = ['source_id', 'title', 'duration_seconds', 'language', 'transcript']
        missing_fields = [f for f in required_fields if f not in video_data]

        if missing_fields:
            raise ValueError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        source_id = video_data['source_id']
        title = video_data['title']
        duration_seconds = video_data['duration_seconds']
        language = video_data['language']
        transcript = video_data['transcript']

        # Extract metadata (optional fields)
        description = video_data.get('description', '')
        metadata = video_data.get('metadata', {})
        tags = metadata.get('tags', []) if isinstance(metadata, dict) else []
        view_count = metadata.get('view_count', 0) if isinstance(metadata, dict) else 0

        if not transcript:
            logger.warning(f"Empty transcript for video {source_id}")
            return None

        # Step 2: Translate transcript if non-English
        working_transcript = transcript
        working_language = language

        if translate_non_english and language != 'en':
            if not TRANSLATOR_AVAILABLE:
                logger.warning(
                    f"Translation requested but translator unavailable. "
                    f"Proceeding with original {language} transcript for {source_id}"
                )
            else:
                logger.info(f"Translating {language} transcript to English for {source_id}")
                try:
                    translated = translate_transcript(
                        transcript=transcript,
                        source_lang=language,
                        preserve_original=True
                    )
                    working_transcript = translated
                    working_language = 'en'
                    logger.info(f"Translation complete for {source_id}")
                except Exception as e:
                    logger.error(f"Translation failed for {source_id}: {e}")
                    logger.info(f"Proceeding with original {language} transcript")

        # Step 3: Split transcript into chunks
        if use_semantic_chunking:
            logger.info(f"Using semantic chunking (topic boundary detection)")
            chunks = split_transcript_semantically(
                transcript=working_transcript,
                min_chunk_duration_seconds=120,  # 2 min minimum
                max_chunk_duration_seconds=420,  # 7 min maximum
                target_chunk_duration_seconds=300,  # 5 min target
                overlap_segments=3
            )
        else:
            logger.info(f"Using time-based chunking (5-min chunks with 1-min overlap)")
            chunks = split_transcript_into_chunks(
                transcript=working_transcript,
                chunk_duration_seconds=300,  # 5 minutes
                overlap_seconds=60  # 1 minute
            )

        logger.info(f"Split into {len(chunks)} chunks")

        if not chunks:
            logger.warning(f"No chunks created for {source_id}")
            return None

        # Step 4: Process each chunk
        all_entities = []
        traveler_profile_signals = []
        total_tokens = 0
        total_cost = 0.0

        for i, chunk_segments in enumerate(chunks):
            chunk_num = i + 1
            logger.info(f"Processing chunk {chunk_num}/{len(chunks)}")

            # Combine chunk segments into text
            chunk_text = "\n".join([
                f"[{seg['start']:.1f}s] {seg['text']}"
                for seg in chunk_segments
            ])

            # Build chunk prompt
            prompt = format_hierarchical_chunk_prompt(
                title=title,
                duration_minutes=duration_seconds / 60,
                language=working_language,
                transcript_chunk=chunk_text,
                chunk_number=chunk_num,
                total_chunks=len(chunks),
                description=description,
                tags=tags,
                view_count=view_count
            )

            # Call LLM for chunk extraction
            llm_result = extract_with_llm(
                prompt=prompt,
                max_retries=3,
                temperature=0.3,
                max_tokens=4000
            )

            if not llm_result['success']:
                logger.error(
                    f"LLM extraction failed for chunk {chunk_num}/{len(chunks)}: "
                    f"{llm_result.get('error', 'Unknown error')}"
                )
                continue  # Skip failed chunk

            chunk_data = llm_result['data']
            total_tokens += llm_result['tokens_used']['total']
            total_cost += llm_result['cost_usd']

            # Extract traveler profile signals from chunk (especially first chunk)
            if 'traveler_profile_signals' in chunk_data:
                traveler_profile_signals.append(chunk_data['traveler_profile_signals'])

            # Extract entities from chunk with validation
            chunk_entities = chunk_data.get('entities', [])
            chunk_rejected = 0

            for entity_data in chunk_entities:
                try:
                    # Normalize entity_type to valid schema value
                    if 'entity_type' in entity_data:
                        original_type = entity_data['entity_type']
                        normalized_type = normalize_entity_type(
                            entity_type=original_type,
                            entity_name=entity_data.get('entity_name', '')
                        )
                        if original_type != normalized_type:
                            logger.info(
                                f"Chunk {chunk_num} entity '{entity_data.get('entity_name', 'unknown')}': "
                                f"entity_type '{original_type}' -> '{normalized_type}'"
                            )
                            entity_data['entity_type'] = normalized_type

                    # Truncate cost_mentioned if it exceeds max length (100 chars)
                    if 'cost_mentioned' in entity_data and entity_data['cost_mentioned']:
                        if len(entity_data['cost_mentioned']) > 100:
                            entity_data['cost_mentioned'] = entity_data['cost_mentioned'][:97] + "..."
                            logger.debug(f"Truncated long cost_mentioned in chunk {chunk_num}")

                    entity = EntityExperience(**entity_data)

                    # Validate quality score
                    if not validate_entity_quality(entity):
                        chunk_rejected += 1
                        logger.debug(f"Rejected entity in chunk {chunk_num}: {entity.entity_name}")
                        continue

                    all_entities.append(entity)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse entity in chunk {chunk_num}: {e}. "
                        f"Entity data: {entity_data}"
                    )
                    chunk_rejected += 1
                    continue

            valid_entities_in_chunk = len(chunk_entities) - chunk_rejected
            logger.info(
                f"Chunk {chunk_num} complete: {valid_entities_in_chunk} valid entities "
                f"(rejected {chunk_rejected}), {llm_result['tokens_used']['total']} tokens"
            )

        # Step 5: Merge traveler profile from signals with validation
        logger.info(f"Merging traveler profile from {len(traveler_profile_signals)} chunks")

        # Simple merging strategy: use first chunk's signals with highest confidence
        if traveler_profile_signals:
            # Use first chunk as base (most representative)
            base_profile = traveler_profile_signals[0]

            try:
                traveler_profile = TravelerProfile(**base_profile)

                # Validate profile quality
                if not validate_traveler_profile_quality(traveler_profile):
                    logger.warning("Merged traveler profile failed validation, using default")
                    traveler_profile = TravelerProfile(confidence_score=0.1)
            except Exception as e:
                logger.error(f"Failed to parse traveler profile: {e}")
                traveler_profile = TravelerProfile(confidence_score=0.1)
        else:
            traveler_profile = TravelerProfile(confidence_score=0.1)

        # Step 6: Deduplicate entities
        dedup_method = "fuzzy" if use_fuzzy_deduplication else "exact"
        logger.info(f"Deduplicating {len(all_entities)} entities using {dedup_method} matching")
        merged_entities = merge_duplicate_entities(
            all_entities,
            use_fuzzy_matching=use_fuzzy_deduplication,
            similarity_threshold=0.75
        )

        logger.info(
            f"After deduplication: {len(merged_entities)} unique entities "
            f"(removed {len(all_entities) - len(merged_entities)} duplicates)"
        )

        # Step 7: Determine extraction quality
        if len(merged_entities) >= 40 and traveler_profile.confidence_score >= 0.7:
            extraction_quality = "high"
        elif len(merged_entities) >= 20 and traveler_profile.confidence_score >= 0.5:
            extraction_quality = "medium"
        else:
            extraction_quality = "low"

        # Step 8: Build processing notes
        processing_notes = []
        chunking_method = "semantic" if use_semantic_chunking else "time-based"
        processing_notes.append(f"Hierarchical extraction: {len(chunks)} {chunking_method} chunks")
        if language != 'en' and working_language == 'en':
            processing_notes.append(f"Translated from {language} to English")
        if len(merged_entities) != len(all_entities):
            processing_notes.append(
                f"Deduplicated ({dedup_method}): {len(all_entities)} → {len(merged_entities)} entities"
            )

        # Step 9: Create Stage2Output
        content_id = f"youtube_{source_id}"

        # Get LLM provider from last successful call
        llm_provider = llm_result.get('provider', 'unknown')
        llm_model = llm_result.get('model', 'unknown')

        stage2_output = Stage2Output(
            content_id=content_id,
            source_id=source_id,
            language=language,
            processed_at=datetime.now(timezone.utc),
            llm_model=f"{llm_provider}:{llm_model}",
            tokens_used=total_tokens,
            cost_usd=total_cost,
            traveler_profile=traveler_profile,
            entities=merged_entities,
            extraction_quality=extraction_quality,
            processing_notes=" | ".join(processing_notes)
        )

        logger.info(
            f"Successfully processed long video {source_id}: "
            f"{len(merged_entities)} entities from {len(chunks)} chunks, "
            f"{total_tokens} tokens, ${total_cost:.4f}, quality={extraction_quality}"
        )

        return stage2_output

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise

    except Exception as e:
        logger.error(
            f"Unexpected error processing long video {video_data.get('source_id', 'unknown')}: {e}",
            exc_info=True
        )
        return None


def extract_entities_batch(
    content_ids: List[str],
    tracker: Any,
    llm_model: str = "gpt-4",
    max_concurrent: int = 3
) -> Dict[str, Any]:
    """
    Extract entities from a batch of videos using LLM.

    Args:
        content_ids: List of content_ids to process
        tracker: MetadataTracker instance
        llm_model: LLM model to use (gpt-4, claude-3-sonnet, etc.)
        max_concurrent: Maximum concurrent LLM requests

    Returns:
        Dict with processing results:
            {
                "total": 10,
                "successful": 8,
                "failed": 2,
                "tokens_used": 125000,
                "cost_usd": 3.75,
                "duration_seconds": 45.2
            }

    Raises:
        NotImplementedError: Stage 2 not yet implemented
    """
    raise NotImplementedError(
        "Stage 2 entity extraction is not yet implemented. "
        "This is a placeholder for future development."
    )


def extract_entities_single(
    content_id: str,
    transcript_text: str,
    language: str,
    llm_model: str = "gpt-4"
) -> Optional[Dict[str, Any]]:
    """
    Extract entities from a single video transcript using LLM.

    Args:
        content_id: Content ID (e.g., "youtube_abc123")
        transcript_text: Full transcript text
        language: Language code (e.g., "en", "hi", "es")
        llm_model: LLM model to use

    Returns:
        Dict containing Stage2Output data, or None if extraction failed

    Raises:
        NotImplementedError: Stage 2 not yet implemented
    """
    raise NotImplementedError(
        "Stage 2 entity extraction is not yet implemented. "
        "This is a placeholder for future development."
    )
