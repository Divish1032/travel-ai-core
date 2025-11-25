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

from typing import List, Dict, Any, Optional, Literal
from datetime import datetime, timezone

from src.utils.schemas import Stage2Output, TravelerProfile, EntityExperience
from src.utils.llm_client import extract_with_gpt4o_mini
from src.processors.extraction_prompts import format_single_pass_prompt
from src.utils.logging import get_logger

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
# Video Classification Helpers
# =============================================================================

def classify_video_length(duration_seconds: float) -> Literal["short", "long"]:
    """
    Classify video length to determine extraction strategy.

    Args:
        duration_seconds: Video duration in seconds (from Stage 1 data)

    Returns:
        "short" if video is < 900 seconds (15 minutes)
        "long" if video is >= 900 seconds (15 minutes)

    Usage:
        This classification helps determine which extraction method to use:
        - short videos: Single-pass extraction (entire transcript in one LLM call)
        - long videos: Hierarchical extraction (chunk → extract → merge)

    Example:
        >>> classify_video_length(600)  # 10 minutes
        'short'
        >>> classify_video_length(1800)  # 30 minutes
        'long'
        >>> classify_video_length(900)  # Exactly 15 minutes
        'long'
    """
    # Threshold: 15 minutes = 900 seconds
    THRESHOLD_SECONDS = 900

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
# Video Processing Functions
# =============================================================================

def process_short_video(
    video_data: Dict[str, Any],
    raw_file_path: Optional[str] = None,
    translate_non_english: bool = True
) -> Optional[Stage2Output]:
    """
    Process a short video (< 15 min) using single-pass LLM extraction.

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
            transcript=transcript_text
        )

        logger.debug(f"Prompt length: {len(prompt)} chars")

        # Step 5: Call LLM for extraction
        logger.info(f"Calling LLM for entity extraction: {source_id}")

        llm_result = extract_with_gpt4o_mini(
            prompt=prompt,
            max_retries=3,
            temperature=0.1,
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

        logger.info(
            f"LLM extraction successful for {source_id}: "
            f"{tokens_used} tokens, ${cost_usd:.4f}"
        )

        # Step 6: Parse and validate with Pydantic schemas
        logger.debug(f"Validating extracted data for {source_id}")

        # Parse traveler profile
        try:
            traveler_profile_data = extracted_data.get('traveler_profile', {})
            traveler_profile = TravelerProfile(**traveler_profile_data)
        except Exception as e:
            logger.error(f"Failed to parse traveler profile for {source_id}: {e}")
            # Use default profile
            traveler_profile = TravelerProfile()

        # Parse entities
        entities = []
        entities_data = extracted_data.get('entities', [])

        for i, entity_data in enumerate(entities_data):
            try:
                entity = EntityExperience(**entity_data)
                entities.append(entity)
            except Exception as e:
                logger.warning(
                    f"Failed to parse entity {i+1} for {source_id}: {e}. "
                    f"Entity data: {entity_data}"
                )
                # Skip invalid entities
                continue

        logger.info(
            f"Parsed {len(entities)} valid entities for {source_id} "
            f"(skipped {len(entities_data) - len(entities)} invalid)"
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
            llm_model="gpt-4o-mini",
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
