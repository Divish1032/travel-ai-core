"""
Insights Extractor - Pass 1 & Pass 2

Extracts travel insights (services, tips, logistics) from two sources:
1. Pass 1: Filtered non-place entities from Stage 3 (entity enrichment)
2. Pass 2: Info-only videos with <5 entities (transcript extraction)

Uses Gemini Flash 2.5 Lite for cost-efficient extraction.

Usage:
    from src.processors.insights_extractor import (
        extract_insights_from_entity,
        extract_insights_from_transcript
    )

    # Pass 1: Entity enrichment
    insights = extract_insights_from_entity(entity, video_metadata)

    # Pass 2: Transcript extraction
    insights = extract_insights_from_transcript(transcript, video_metadata)
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

# Add project root to path if running as main
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.llm_client import extract_with_gemini
from src.utils.schemas import TravelInsight
from src.processors.insight_prompts import format_pass1_prompt, format_pass2_prompt
from src.utils.logging import get_logger
from pydantic import ValidationError

logger = get_logger(__name__)


# =============================================================================
# Pass 1: Entity Enrichment (Filtered Entities)
# =============================================================================

def extract_insights_from_entity(
    entity: Dict[str, Any],
    video_metadata: Dict[str, Any],
    max_retries: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extract travel insights from a filtered non-place entity.

    Pass 1 takes entities that were filtered out of the main entity pipeline
    (apps, websites, packing items, etc.) and extracts reusable travel insights.

    Args:
        entity: Filtered entity dict with canonical_name, entity_type, filter_reason, etc.
        video_metadata: Video dict with title, description, duration, source_id
        max_retries: Maximum LLM retry attempts (default: 2)

    Returns:
        Tuple of (insights_list, extraction_metadata):
        - insights_list: List of insight dicts (validated against TravelInsight schema)
        - extraction_metadata: Dict with tokens, cost, success status

    Example:
        >>> entity = {
        ...     'canonical_name': '12goasia',
        ...     'entity_type': 'service',
        ...     'filter_reason': 'apps_websites',
        ...     'experiences': [{'experience': 'Book buses online'}]
        ... }
        >>> insights, meta = extract_insights_from_entity(entity, video_metadata)
        >>> len(insights)
        2
        >>> insights[0]['category']
        'services'
    """
    logger.debug(
        f"Pass 1: Extracting insights from entity '{entity.get('canonical_name', 'unknown')}'"
    )

    # Format prompt
    try:
        prompt = format_pass1_prompt(entity, video_metadata)
    except Exception as e:
        logger.error(f"Failed to format Pass 1 prompt: {e}")
        return [], {
            'success': False,
            'error': f'Prompt formatting failed: {e}',
            'tokens_used': {'input': 0, 'output': 0, 'total': 0},
            'cost_usd': 0.0
        }

    # Call LLM (Gemini Flash 2.5 Lite - free tier)
    result = extract_with_gemini(
        prompt=prompt,
        max_retries=max_retries,
        temperature=0.3,
        max_tokens=2000  # Smaller limit for entity enrichment
    )

    # Handle LLM failure
    if not result['success']:
        logger.warning(
            f"Pass 1 LLM extraction failed for entity '{entity.get('canonical_name')}': "
            f"{result.get('error', 'unknown error')}"
        )
        return [], {
            'success': False,
            'error': result.get('error', 'LLM extraction failed'),
            'tokens_used': result['tokens_used'],
            'cost_usd': result['cost_usd'],
            'model': result.get('model', 'unknown'),
            'provider': result.get('provider', 'unknown')
        }

    # Parse insights from LLM response
    raw_data = result['data']
    raw_insights = raw_data.get('insights', [])

    if not raw_insights:
        logger.debug(
            f"Pass 1: No insights extracted from entity '{entity.get('canonical_name')}'"
        )
        return [], {
            'success': True,
            'insights_extracted': 0,
            'tokens_used': result['tokens_used'],
            'cost_usd': result['cost_usd'],
            'model': result.get('model', 'unknown'),
            'provider': result.get('provider', 'unknown')
        }

    # Validate and enrich insights
    validated_insights = []
    for idx, raw_insight in enumerate(raw_insights):
        try:
            # Add provenance fields
            insight_with_provenance = {
                **raw_insight,
                'provenance': {
                    'source_video_ids': [video_metadata.get('source_id', 'unknown')],
                    'extraction_method': 'entity_enrichment',
                    'extraction_date': datetime.now(timezone.utc).isoformat(),
                    'source_entity_name': entity.get('canonical_name', 'unknown'),
                    'filter_reason': entity.get('filter_reason', 'unknown')
                },
                'mention_count': 1,
                'video_count': 1
            }

            # Validate against TravelInsight schema (skip insight_id for now)
            # We'll generate IDs during registration
            validated_insight = validate_insight_schema(insight_with_provenance)

            if validated_insight:
                validated_insights.append(validated_insight)
            else:
                logger.debug(
                    f"Pass 1: Insight {idx + 1} failed validation for entity "
                    f"'{entity.get('canonical_name')}'"
                )

        except Exception as e:
            logger.warning(
                f"Pass 1: Failed to validate insight {idx + 1} for entity "
                f"'{entity.get('canonical_name')}': {e}"
            )
            continue

    logger.info(
        f"Pass 1: Extracted {len(validated_insights)}/{len(raw_insights)} valid insights "
        f"from entity '{entity.get('canonical_name')}'"
    )

    return validated_insights, {
        'success': True,
        'insights_extracted': len(validated_insights),
        'insights_raw': len(raw_insights),
        'tokens_used': result['tokens_used'],
        'cost_usd': result['cost_usd'],
        'model': result.get('model', 'unknown'),
        'provider': result.get('provider', 'unknown')
    }


# =============================================================================
# Pass 2: Transcript Extraction (Info-Only Videos)
# =============================================================================

def extract_insights_from_transcript(
    transcript: str,
    video_metadata: Dict[str, Any],
    chunk_size: int = 4000,
    max_retries: int = 2
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extract travel insights from video transcript (info-only videos with <5 entities).

    Pass 2 processes transcripts from videos that have very few place entities
    but contain valuable travel tips, service recommendations, logistics advice, etc.

    Args:
        transcript: Full video transcript text
        video_metadata: Video dict with title, description, duration, source_id
        chunk_size: Word count per chunk for long transcripts (default: 4000)
        max_retries: Maximum LLM retry attempts (default: 2)

    Returns:
        Tuple of (insights_list, extraction_metadata):
        - insights_list: List of insight dicts (validated against TravelInsight schema)
        - extraction_metadata: Dict with tokens, cost, success status

    Example:
        >>> transcript = "Top 10 tips for traveling Thailand: 1. Download Grab app..."
        >>> insights, meta = extract_insights_from_transcript(transcript, video_metadata)
        >>> len(insights)
        10
        >>> insights[0]['category']
        'services'
    """
    logger.debug(
        f"Pass 2: Extracting insights from transcript for video "
        f"'{video_metadata.get('source_id', 'unknown')}'"
    )

    # Split transcript into chunks if needed
    chunks = chunk_transcript(transcript, chunk_size=chunk_size)

    logger.debug(f"Pass 2: Processing {len(chunks)} transcript chunks")

    all_insights = []
    total_tokens = {'input': 0, 'output': 0, 'total': 0}
    total_cost = 0.0
    chunk_successes = 0

    # Process each chunk
    for chunk_idx, chunk_text in enumerate(chunks):
        logger.debug(f"Pass 2: Processing chunk {chunk_idx + 1}/{len(chunks)}")

        # Format prompt
        try:
            prompt = format_pass2_prompt(chunk_text, video_metadata)
        except Exception as e:
            logger.error(f"Pass 2: Failed to format prompt for chunk {chunk_idx + 1}: {e}")
            continue

        # Call LLM (Gemini Flash 2.5 Lite - free tier)
        result = extract_with_gemini(
            prompt=prompt,
            max_retries=max_retries,
            temperature=0.3,
            max_tokens=4000  # Larger limit for transcript extraction
        )

        # Handle LLM failure
        if not result['success']:
            logger.warning(
                f"Pass 2: LLM extraction failed for chunk {chunk_idx + 1}: "
                f"{result.get('error', 'unknown error')}"
            )
            continue

        # Aggregate token usage
        total_tokens['input'] += result['tokens_used']['input']
        total_tokens['output'] += result['tokens_used']['output']
        total_tokens['total'] += result['tokens_used']['total']
        total_cost += result['cost_usd']
        chunk_successes += 1

        # Parse insights from LLM response
        raw_data = result['data']
        raw_insights = raw_data.get('insights', [])

        if not raw_insights:
            logger.debug(f"Pass 2: No insights extracted from chunk {chunk_idx + 1}")
            continue

        # Validate and enrich insights
        for idx, raw_insight in enumerate(raw_insights):
            try:
                # Add provenance fields
                insight_with_provenance = {
                    **raw_insight,
                    'provenance': {
                        'source_video_ids': [video_metadata.get('source_id', 'unknown')],
                        'extraction_method': 'transcript_extraction',
                        'extraction_date': datetime.now(timezone.utc).isoformat(),
                        'chunk_index': chunk_idx,
                        'total_chunks': len(chunks)
                    },
                    'mention_count': 1,
                    'video_count': 1
                }

                # Validate against TravelInsight schema
                validated_insight = validate_insight_schema(insight_with_provenance)

                if validated_insight:
                    all_insights.append(validated_insight)
                else:
                    logger.debug(
                        f"Pass 2: Insight {idx + 1} from chunk {chunk_idx + 1} failed validation"
                    )

            except Exception as e:
                logger.warning(
                    f"Pass 2: Failed to validate insight {idx + 1} from chunk {chunk_idx + 1}: {e}"
                )
                continue

    # Deduplicate insights within same video (exact content match)
    deduplicated_insights = deduplicate_insights_within_video(all_insights)

    logger.info(
        f"Pass 2: Extracted {len(deduplicated_insights)} unique insights "
        f"(from {len(all_insights)} raw) for video '{video_metadata.get('source_id')}'"
    )

    return deduplicated_insights, {
        'success': chunk_successes > 0,
        'chunks_processed': chunk_successes,
        'chunks_total': len(chunks),
        'insights_extracted': len(deduplicated_insights),
        'insights_raw': len(all_insights),
        'tokens_used': total_tokens,
        'cost_usd': total_cost,
        'model': result.get('model', 'unknown') if chunk_successes > 0 else 'unknown',
        'provider': result.get('provider', 'unknown') if chunk_successes > 0 else 'unknown'
    }


# =============================================================================
# Helper Functions
# =============================================================================

def validate_insight_schema(
    insight_dict: Dict[str, Any],
    require_id: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Validate insight against TravelInsight schema.

    Args:
        insight_dict: Raw insight dict from LLM
        require_id: If True, require insight_id field (default: False)

    Returns:
        Validated insight dict, or None if validation fails

    Note:
        We don't require insight_id during extraction because IDs are generated
        during registration in the InsightRegistry.
    """
    try:
        # Create temporary ID for validation if not required
        if not require_id and 'insight_id' not in insight_dict:
            insight_dict['insight_id'] = 'INS_TMP_000'

        # Validate with Pydantic
        validated = TravelInsight(**insight_dict)

        # Convert back to dict
        return validated.model_dump()

    except ValidationError as e:
        logger.debug(f"Insight validation failed: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected validation error: {e}")
        return None


def chunk_transcript(
    transcript: str,
    chunk_size: int = 4000,
    overlap: int = 200
) -> List[str]:
    """
    Split transcript into overlapping chunks by word count.

    Args:
        transcript: Full transcript text
        chunk_size: Target words per chunk (default: 4000)
        overlap: Word overlap between chunks (default: 200)

    Returns:
        List of transcript chunks

    Example:
        >>> transcript = "word " * 10000
        >>> chunks = chunk_transcript(transcript, chunk_size=4000)
        >>> len(chunks)
        3
    """
    words = transcript.split()
    total_words = len(words)

    # If transcript fits in one chunk, return as-is
    if total_words <= chunk_size:
        return [transcript]

    chunks = []
    start_idx = 0

    while start_idx < total_words:
        # Get chunk words
        end_idx = min(start_idx + chunk_size, total_words)
        chunk_words = words[start_idx:end_idx]
        chunks.append(' '.join(chunk_words))

        # Move to next chunk with overlap
        if end_idx >= total_words:
            break
        start_idx = end_idx - overlap

    logger.debug(
        f"Split transcript into {len(chunks)} chunks "
        f"({total_words} words, {chunk_size} words/chunk, {overlap} overlap)"
    )

    return chunks


def deduplicate_insights_within_video(
    insights: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Remove duplicate insights within same video (exact content match).

    This is a simple deduplication based on normalized content + category + scope.
    The full 3-tier deduplication happens later in Phase 2C.

    Args:
        insights: List of insight dicts from same video

    Returns:
        Deduplicated list of insights

    Example:
        >>> insights = [
        ...     {'content': 'Use Grab app', 'category': 'services', ...},
        ...     {'content': 'Use grab app', 'category': 'services', ...},  # Duplicate
        ...     {'content': 'Pack adapter', 'category': 'tips', ...}
        ... ]
        >>> deduped = deduplicate_insights_within_video(insights)
        >>> len(deduped)
        2
    """
    seen_signatures = set()
    deduplicated = []

    for insight in insights:
        # Create signature: normalized content + category + scope
        content = insight.get('content', '').lower().strip()
        category = insight.get('category', 'unknown')
        scope = insight.get('scope', {})
        scope_str = json.dumps(scope, sort_keys=True)

        signature = f"{category}||{scope_str}||{content}"

        if signature not in seen_signatures:
            seen_signatures.add(signature)
            deduplicated.append(insight)

    removed_count = len(insights) - len(deduplicated)
    if removed_count > 0:
        logger.debug(f"Removed {removed_count} duplicate insights within video")

    return deduplicated


# =============================================================================
# Testing
# =============================================================================

def test_insights_extractor():
    """Test insights extraction with sample data."""
    from src.utils.logging import setup_logging
    setup_logging(log_level='DEBUG')

    logger.info("=== Testing Insights Extractor ===\n")

    # Test Pass 1: Entity enrichment
    logger.info("Test 1: Pass 1 Entity Enrichment")
    test_entity = {
        'canonical_name': 'Grab app',
        'entity_type': 'service',
        'filter_reason': 'apps_websites',
        'city': 'Bangkok',
        'country': 'Thailand',
        'experiences': [{
            'experience': 'Use Grab for ride-hailing. Cheaper than taxis and easy to use.'
        }]
    }

    test_video_metadata = {
        'source_id': 'test_video_001',
        'title': '10 Essential Thailand Travel Tips',
        'description': 'Everything you need to know before visiting Thailand',
        'duration': 600,
        'tags': ['thailand', 'travel', 'tips']
    }

    insights, meta = extract_insights_from_entity(test_entity, test_video_metadata)

    logger.info(f"✓ Extracted {len(insights)} insights from entity")
    logger.info(f"  Tokens: {meta['tokens_used']['total']}")
    logger.info(f"  Cost: ${meta['cost_usd']:.6f}")

    if insights:
        logger.info(f"  Sample insight: {insights[0].get('title', 'N/A')}")
        logger.info(f"  Category: {insights[0].get('category', 'N/A')}")

    # Test Pass 2: Transcript extraction
    logger.info("\nTest 2: Pass 2 Transcript Extraction")
    test_transcript = """
    Here are my top 5 tips for traveling Thailand:

    1. Download the Grab app for ride-hailing. It's way cheaper than taxis and very reliable.

    2. Make sure to pack a Type C power adapter. Thailand uses 220V electricity.

    3. Get a local SIM card at the airport. It's super cheap, like 300 baht for 30 days.

    4. Remember to remove your shoes before entering temples. It's very important culturally.

    5. Avoid taxis at the airport that don't use the meter. Common scam for tourists.
    """

    insights, meta = extract_insights_from_transcript(test_transcript, test_video_metadata)

    logger.info(f"✓ Extracted {len(insights)} insights from transcript")
    logger.info(f"  Tokens: {meta['tokens_used']['total']}")
    logger.info(f"  Cost: ${meta['cost_usd']:.6f}")

    if insights:
        logger.info(f"  Sample insight: {insights[0].get('title', 'N/A')}")
        logger.info(f"  Category: {insights[0].get('category', 'N/A')}")

    logger.info("\n✅ Insights extractor tests complete!")


if __name__ == '__main__':
    test_insights_extractor()
