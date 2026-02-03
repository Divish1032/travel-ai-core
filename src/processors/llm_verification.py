"""
Stage 3 LLM Verification: Verify Entity Matches with LLM

Uses Gemini Flash (cheapest option) to verify if two entities are the same.
This is for Tier 4 matching - verifying ambiguous fuzzy/semantic matches.

Cost: ~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens
Example: Verifying 200 pairs costs ~$0.02

Usage:
    from src.processors.llm_verification import (
        verify_entity_match,
        batch_verify_matches
    )

    # Verify single match
    result = verify_entity_match(entity1, entity2, similarity_score=0.82)
    if result['is_match']:
        print(f"Match confirmed: {result['reasoning']}")

    # Batch verify multiple candidates
    verified = batch_verify_matches(fuzzy_candidates[:20])
"""

from typing import List, Dict, Any, Tuple
import json

from src.utils.llm_client import extract_with_llm
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Global Cost Tracking
# =============================================================================

_TOTAL_TOKENS_USED = 0
_TOTAL_COST_USD = 0.0


def get_verification_stats() -> Dict[str, Any]:
    """
    Get cumulative verification statistics.

    Returns:
        Dict with total_tokens_used and total_cost_usd
    """
    return {
        'total_tokens_used': _TOTAL_TOKENS_USED,
        'total_cost_usd': _TOTAL_COST_USD
    }


def reset_verification_stats() -> None:
    """Reset verification statistics."""
    global _TOTAL_TOKENS_USED, _TOTAL_COST_USD
    _TOTAL_TOKENS_USED = 0
    _TOTAL_COST_USD = 0.0


# =============================================================================
# Prompt Templates
# =============================================================================


def create_verification_prompt(
    entity1: Dict[str, Any],
    entity2: Dict[str, Any],
    similarity_score: float
) -> str:
    """
    Create LLM prompt for entity match verification.

    Args:
        entity1: First entity dict
        entity2: Second entity dict
        similarity_score: Similarity score from fuzzy/semantic matching

    Returns:
        Formatted prompt string
    """
    # Extract entity 1 data
    name1 = entity1.get('original_name', 'Unknown')
    type1 = entity1.get('entity', {}).get('entity_type', 'unknown')
    location1 = entity1.get('original_location') or 'Unknown'
    experience1 = entity1.get('entity', {}).get('experience', '')

    # Extract entity 2 data
    name2 = entity2.get('original_name', 'Unknown')
    type2 = entity2.get('entity', {}).get('entity_type', 'unknown')
    location2 = entity2.get('original_location') or 'Unknown'
    experience2 = entity2.get('entity', {}).get('experience', '')

    # Truncate experiences to keep prompt concise (max 200 chars each)
    context1 = experience1[:200] if experience1 else 'No additional context'
    context2 = experience2[:200] if experience2 else 'No additional context'

    prompt = f"""You are a travel entity matching expert. Determine if these two entities refer to the same place, activity, or thing.

**Entity 1:**
- Name: {name1}
- Type: {type1}
- Location: {location1}
- Context: {context1}

**Entity 2:**
- Name: {name2}
- Type: {type2}
- Location: {location2}
- Context: {context2}

**Similarity Score:** {similarity_score:.2f} (from text/semantic matching)

**Instructions:**
- Determine if these are the SAME entity (e.g., "Wat Pho" and "Wat Pho Temple" are the same)
- Consider: name variations, abbreviations, translations, common nicknames
- Be strict: "Railay Beach" and "Patong Beach" are NOT the same (different beaches)
- Be flexible: "Khao San Road" and "the backpacker street" might be the same if context matches

**Answer ONLY with valid JSON (no markdown, no explanation outside JSON):**
{{
  "is_match": true,
  "confidence": 0.95,
  "reasoning": "Brief explanation of why they match or don't match"
}}

Response:"""

    return prompt


# =============================================================================
# Single Entity Verification
# =============================================================================


def verify_entity_match(
    entity1: Dict[str, Any],
    entity2: Dict[str, Any],
    similarity_score: float,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Verify if two entities are the same using LLM.

    Uses Gemini Flash by default, falls back to OpenAI/DeepSeek if needed.

    Args:
        entity1: First entity dict from stage3_loader
        entity2: Second entity dict from stage3_loader
        similarity_score: Similarity score from fuzzy/semantic matching
        max_retries: Maximum retry attempts

    Returns:
        Dict with:
            - is_match: bool (True if entities match)
            - confidence: float (0.0-1.0)
            - reasoning: str (explanation)
            - tokens_used: int
            - cost_usd: float

    Example:
        >>> result = verify_entity_match(entity1, entity2, similarity_score=0.82)
        >>> if result['is_match']:
        ...     print(f"Match confirmed: {result['reasoning']}")
    """
    global _TOTAL_TOKENS_USED, _TOTAL_COST_USD

    # Create verification prompt
    prompt = create_verification_prompt(entity1, entity2, similarity_score)

    # Call LLM with fallback
    llm_result = extract_with_llm(
        prompt=prompt,
        max_retries=max_retries,
        temperature=0.1,  # Low temperature for consistent verification
        max_tokens=200    # Short response expected
    )

    if not llm_result['success']:
        # LLM call failed
        logger.error(f"LLM verification failed: {llm_result.get('error', 'Unknown error')}")
        return {
            'is_match': False,
            'confidence': 0.0,
            'reasoning': f"Verification failed: {llm_result.get('error', 'Unknown error')}",
            'tokens_used': 0,
            'cost_usd': 0.0,
            'error': True
        }

    # Parse LLM response
    try:
        response_data = llm_result['data']

        # Check if already parsed as dict (extract_with_llm may return parsed data)
        if isinstance(response_data, dict):
            verification_data = response_data
        else:
            # It's a string, need to parse
            response_text = response_data

            # Try to extract JSON from response
            # Sometimes LLM adds markdown code blocks
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()

            # Parse JSON
            verification_data = json.loads(response_text)

        # Validate required fields
        is_match = verification_data.get('is_match', False)
        confidence = verification_data.get('confidence', 0.0)
        reasoning = verification_data.get('reasoning', 'No reasoning provided')

        # Update global stats
        tokens_used = llm_result['tokens_used']['total']
        cost_usd = llm_result['cost_usd']
        _TOTAL_TOKENS_USED += tokens_used
        _TOTAL_COST_USD += cost_usd

        return {
            'is_match': bool(is_match),
            'confidence': float(confidence),
            'reasoning': str(reasoning),
            'tokens_used': tokens_used,
            'cost_usd': cost_usd,
            'provider': llm_result.get('provider', 'unknown'),
            'model': llm_result.get('model', 'unknown')
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Raw response: {llm_result['data']}")
        return {
            'is_match': False,
            'confidence': 0.0,
            'reasoning': f"Failed to parse LLM response: {e}",
            'tokens_used': llm_result['tokens_used']['total'],
            'cost_usd': llm_result['cost_usd'],
            'error': True
        }

    except Exception as e:
        logger.error(f"Unexpected error in verification: {e}")
        return {
            'is_match': False,
            'confidence': 0.0,
            'reasoning': f"Verification error: {e}",
            'tokens_used': 0,
            'cost_usd': 0.0,
            'error': True
        }


# =============================================================================
# Batch Verification
# =============================================================================


def batch_verify_matches(
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
    confidence_threshold: float = 0.7,
    show_progress: bool = True
) -> List[Dict[str, Any]]:
    """
    Verify multiple entity match candidates using LLM.

    Processes candidates in batch, tracks costs, and filters by confidence.

    Args:
        candidates: List of (entity1, entity2, similarity_score) tuples
        confidence_threshold: Minimum confidence to consider a match
        show_progress: Show progress bar if True

    Returns:
        List of verified matches with metadata:
        [
            {
                'entity1': dict,
                'entity2': dict,
                'similarity_score': float,
                'is_match': bool,
                'confidence': float,
                'reasoning': str,
                'tokens_used': int,
                'cost_usd': float
            },
            ...
        ]

    Example:
        >>> fuzzy_candidates = find_fuzzy_candidates(entities, threshold=0.75)
        >>> verified = batch_verify_matches(fuzzy_candidates[:20])
        >>> print(f"Verified {len(verified)} matches")
        >>> print(f"Total cost: ${get_verification_stats()['total_cost_usd']:.4f}")
    """
    logger.info(f"Batch verifying {len(candidates)} entity match candidates...")

    # Progress tracking
    if show_progress:
        try:
            from tqdm import tqdm
            candidate_iterator = tqdm(candidates, desc="Verifying matches", unit="pair")
        except ImportError:
            candidate_iterator = candidates
            logger.info("Install tqdm for progress bars: pip install tqdm")
    else:
        candidate_iterator = candidates

    verified_matches = []
    successful_verifications = 0
    failed_verifications = 0
    confirmed_matches = 0

    for entity1, entity2, similarity_score in candidate_iterator:
        # Verify this pair
        result = verify_entity_match(entity1, entity2, similarity_score)

        # Check if verification succeeded
        if result.get('error', False):
            failed_verifications += 1
            continue

        successful_verifications += 1

        # Check if match is confirmed with sufficient confidence
        if result['is_match'] and result['confidence'] >= confidence_threshold:
            confirmed_matches += 1

            # Add to verified matches list
            verified_matches.append({
                'entity1': entity1,
                'entity2': entity2,
                'similarity_score': similarity_score,
                'is_match': result['is_match'],
                'confidence': result['confidence'],
                'reasoning': result['reasoning'],
                'tokens_used': result['tokens_used'],
                'cost_usd': result['cost_usd'],
                'provider': result.get('provider', 'unknown'),
                'model': result.get('model', 'unknown')
            })

    # Get cumulative stats
    stats = get_verification_stats()

    # Log results
    logger.info("✅ Batch verification complete:")
    logger.info(f"   Candidates processed: {len(candidates)}")
    logger.info(f"   Successful verifications: {successful_verifications}")
    logger.info(f"   Failed verifications: {failed_verifications}")
    logger.info(f"   Confirmed matches: {confirmed_matches}")
    logger.info(f"   Total tokens used: {stats['total_tokens_used']:,}")
    logger.info(f"   Total cost: ${stats['total_cost_usd']:.4f}")

    # Log examples of confirmed matches
    if verified_matches:
        logger.info("")
        logger.info("Top 5 confirmed matches:")
        for i, match in enumerate(verified_matches[:5], 1):
            name1 = match['entity1'].get('original_name', 'Unknown')
            name2 = match['entity2'].get('original_name', 'Unknown')
            conf = match['confidence']
            reason = match['reasoning']

            logger.info(f"   {i}. {name1} ~ {name2}")
            logger.info(f"      Confidence: {conf:.2f}, Reason: {reason}")

    return verified_matches


# =============================================================================
# Testing and Validation
# =============================================================================


def test_llm_verification_sample():
    """
    Test LLM verification with sample entity pairs.

    Tests known matches and non-matches to verify LLM accuracy.
    """
    logger.info("Testing LLM verification with sample entities...")

    # Reset stats
    reset_verification_stats()

    # Sample test pairs
    test_pairs = [
        # Pair 1: Should MATCH (same temple, name variation)
        (
            {
                'original_name': 'Wat Pho',
                'original_location': 'Bangkok',
                'entity': {
                    'entity_type': 'attraction',
                    'experience': 'Beautiful temple with reclining Buddha. Must-visit in Bangkok.'
                }
            },
            {
                'original_name': 'Wat Pho Temple',
                'original_location': 'Bangkok',
                'entity': {
                    'entity_type': 'attraction',
                    'experience': 'Famous temple known for the giant reclining Buddha statue.'
                }
            },
            0.95,  # High similarity
            True   # Expected match
        ),

        # Pair 2: Should NOT MATCH (different beaches)
        (
            {
                'original_name': 'Railay Beach',
                'original_location': 'Krabi',
                'entity': {
                    'entity_type': 'destination',
                    'experience': 'Stunning beach accessible only by boat. Great for rock climbing.'
                }
            },
            {
                'original_name': 'Patong Beach',
                'original_location': 'Phuket',
                'entity': {
                    'entity_type': 'destination',
                    'experience': 'Main tourist beach in Phuket with lots of hotels and nightlife.'
                }
            },
            0.65,  # Medium similarity (both beaches)
            False  # Expected non-match
        ),

        # Pair 3: Should MATCH (nickname vs full name)
        (
            {
                'original_name': 'The backpacker street',
                'original_location': 'Bangkok',
                'entity': {
                    'entity_type': 'destination',
                    'experience': 'Famous street with hostels, bars, and budget travelers.'
                }
            },
            {
                'original_name': 'Khao San Road',
                'original_location': 'Bangkok',
                'entity': {
                    'entity_type': 'destination',
                    'experience': 'Iconic backpacker hub with cheap accommodation and nightlife.'
                }
            },
            0.82,  # High similarity
            True   # Expected match
        )
    ]

    # Test each pair
    results = []
    for i, (e1, e2, sim, expected_match) in enumerate(test_pairs, 1):
        logger.info(f"\nTest {i}: {e1['original_name']} vs {e2['original_name']}")

        result = verify_entity_match(e1, e2, sim)

        correct = result['is_match'] == expected_match
        status = "✅ CORRECT" if correct else "❌ INCORRECT"

        logger.info(f"  Expected: {expected_match}, Got: {result['is_match']}, {status}")
        logger.info(f"  Confidence: {result['confidence']:.2f}")
        logger.info(f"  Reasoning: {result['reasoning']}")
        logger.info(f"  Cost: ${result['cost_usd']:.6f}")

        results.append({
            'test_id': i,
            'correct': correct,
            'result': result
        })

    # Calculate accuracy
    accuracy = sum(1 for r in results if r['correct']) / len(results)

    # Get final stats
    stats = get_verification_stats()

    logger.info("\n✅ LLM verification test complete!")
    logger.info(f"   Accuracy: {accuracy:.1%} ({sum(1 for r in results if r['correct'])}/{len(results)})")
    logger.info(f"   Total tokens: {stats['total_tokens_used']:,}")
    logger.info(f"   Total cost: ${stats['total_cost_usd']:.6f}")

    return results


if __name__ == '__main__':
    # Run tests
    test_llm_verification_sample()
