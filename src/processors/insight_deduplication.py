"""
Insights Deduplication: 3-Tier Matching System

Implements 3-tier deduplication for travel insights:
- Tier 1: Exact content match (hash-based, FREE)
- Tier 2: Semantic similarity with embeddings (>0.90 auto-merge)
- Tier 3: LLM verification for ambiguous cases (0.80-0.90 similarity)

Usage:
    from src.processors.insight_deduplication import deduplicate_insights

    # Load extracted insights from S3
    insights = insights_storage.load_extracted_insights()

    # Deduplicate
    groups, stats = deduplicate_insights(insights)

    # groups = {
    #     'group_abc123': [insight1, insight2, insight3],  # Duplicates
    #     'group_def456': [insight4, insight5],
    #     ...
    # }
"""

import sys
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
import numpy as np

# Add project root to path if running as main
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.embedding_client import EmbeddingClient
from src.utils.llm_client import extract_with_gemini
from src.storage.insight_registry import normalize_content, create_scope_key
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Tier 1: Exact Content Match (Hash-Based)
# =============================================================================

def create_insight_signature(insight: Dict[str, Any]) -> str:
    """
    Create unique signature for exact matching.

    Signature = MD5(normalized_content + category + scope_key)

    Args:
        insight: Insight dict with content, category, scope

    Returns:
        MD5 hash string

    Example:
        >>> insight = {
        ...     'content': 'Use Grab app for ride-hailing',
        ...     'category': 'services',
        ...     'scope': {'destination_type': 'region', 'region': 'Southeast Asia'}
        ... }
        >>> sig = create_insight_signature(insight)
        >>> len(sig)
        32
    """
    # Normalize content
    content = insight.get('content', '')
    normalized = normalize_content(content)

    # Get category
    category = insight.get('category', 'unknown')

    # Create scope key
    scope = insight.get('scope', {})
    scope_key = create_scope_key(scope)

    # Create signature
    signature_str = f"{category}||{scope_key}||{normalized}"
    return hashlib.md5(signature_str.encode()).hexdigest()


def group_exact_matches(insights: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group insights with exact content matches (Tier 1).

    Args:
        insights: List of insight dicts

    Returns:
        Dict mapping signature to list of matching insights
        {
            'abc123...': [insight1, insight2, insight3],
            'def456...': [insight4, insight5],
            ...
        }

    Example:
        >>> insights = [
        ...     {'content': 'Use Grab app', 'category': 'services', ...},
        ...     {'content': 'Use grab app', 'category': 'services', ...},  # Duplicate
        ...     {'content': 'Pack adapter', 'category': 'tips', ...}
        ... ]
        >>> groups = group_exact_matches(insights)
        >>> len(groups)  # 2 groups: 1 with 2 insights, 1 with 1 insight
        2
    """
    logger.info("Tier 1: Grouping exact content matches...")

    signature_groups = defaultdict(list)

    for insight in insights:
        signature = create_insight_signature(insight)
        signature_groups[signature].append(insight)

    # Filter to only groups with 2+ insights (actual duplicates)
    duplicate_groups = {
        sig: insights_list
        for sig, insights_list in signature_groups.items()
        if len(insights_list) > 1
    }

    # Count singletons (unique insights)
    singleton_count = sum(
        1 for insights_list in signature_groups.values()
        if len(insights_list) == 1
    )

    total_duplicates = sum(len(group) for group in duplicate_groups.values())

    logger.info(f"Tier 1 complete:")
    logger.info(f"  Total insights: {len(insights)}")
    logger.info(f"  Exact match groups: {len(duplicate_groups)}")
    logger.info(f"  Insights in groups: {total_duplicates}")
    logger.info(f"  Unique insights: {singleton_count}")

    return duplicate_groups


# =============================================================================
# Tier 2: Semantic Similarity (Embeddings)
# =============================================================================

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Similarity score (0.0-1.0)

    Example:
        >>> v1 = [1.0, 0.0, 0.0]
        >>> v2 = [1.0, 0.0, 0.0]
        >>> cosine_similarity(v1, v2)
        1.0
    """
    v1 = np.array(vec1)
    v2 = np.array(vec2)

    # Calculate cosine similarity
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)

    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0

    return float(dot_product / (norm_v1 * norm_v2))


def find_semantic_candidates(
    insights: List[Dict[str, Any]],
    embedding_client: EmbeddingClient,
    threshold: float = 0.80
) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
    """
    Find candidate duplicate insights using semantic similarity (Tier 2).

    Args:
        insights: List of insight dicts (singletons from Tier 1)
        embedding_client: EmbeddingClient instance for generating embeddings
        threshold: Minimum similarity score to consider (default: 0.80)

    Returns:
        List of (insight1, insight2, similarity_score) tuples

    Example:
        >>> insights = load_singleton_insights()
        >>> embedding_client = EmbeddingClient()
        >>> candidates = find_semantic_candidates(insights, embedding_client, threshold=0.85)
        >>> len(candidates)
        15
    """
    logger.info(f"Tier 2: Finding semantic candidates (threshold: {threshold:.2f})...")

    if len(insights) < 2:
        logger.info("Tier 2: Less than 2 insights, skipping")
        return []

    # Filter by category + scope (only compare within same category and scope)
    category_scope_groups = defaultdict(list)

    for insight in insights:
        category = insight.get('category', 'unknown')
        scope = insight.get('scope', {})
        scope_key = create_scope_key(scope)
        key = f"{category}||{scope_key}"
        category_scope_groups[key].append(insight)

    logger.debug(f"Tier 2: Grouped into {len(category_scope_groups)} category+scope groups")

    # Generate embeddings for all insights
    logger.info("Tier 2: Generating embeddings...")
    insight_embeddings = []

    for insight in insights:
        content = insight.get('content', '')
        if not content:
            continue

        try:
            embedding = embedding_client.embed_text(content, use_cache=True)
            insight_embeddings.append((insight, embedding))
        except Exception as e:
            logger.warning(f"Tier 2: Failed to embed insight: {e}")
            continue

    logger.info(f"Tier 2: Generated {len(insight_embeddings)} embeddings")

    # Find similar pairs within each category+scope group
    candidates = []

    for group_key, group_insights in category_scope_groups.items():
        if len(group_insights) < 2:
            continue

        # Get embeddings for this group
        group_data = [
            (insight, emb)
            for insight, emb in insight_embeddings
            if insight in group_insights
        ]

        # Compare all pairs in this group
        for i in range(len(group_data)):
            for j in range(i + 1, len(group_data)):
                insight1, emb1 = group_data[i]
                insight2, emb2 = group_data[j]

                similarity = cosine_similarity(emb1, emb2)

                if similarity >= threshold:
                    candidates.append((insight1, insight2, similarity))

    logger.info(f"Tier 2 complete:")
    logger.info(f"  Semantic candidates found: {len(candidates)}")
    logger.info(f"  Similarity threshold: {threshold:.2f}")

    # Sort by similarity (highest first)
    candidates.sort(key=lambda x: x[2], reverse=True)

    return candidates


def auto_merge_high_similarity(
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
    auto_merge_threshold: float = 0.90
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Tuple[Dict[str, Any], Dict[str, Any], float]]]:
    """
    Auto-merge insights with very high similarity (>= threshold).

    Args:
        candidates: List of (insight1, insight2, similarity) tuples from Tier 2
        auto_merge_threshold: Threshold for auto-merging (default: 0.90)

    Returns:
        Tuple of (merged_groups, remaining_candidates):
        - merged_groups: Dict of auto-merged groups
        - remaining_candidates: Candidates below auto-merge threshold (for Tier 3)

    Example:
        >>> candidates = find_semantic_candidates(insights, embedding_client)
        >>> merged, remaining = auto_merge_high_similarity(candidates, threshold=0.90)
        >>> len(merged)  # Auto-merged groups
        10
        >>> len(remaining)  # Need LLM verification
        25
    """
    logger.info(f"Tier 2: Auto-merging high similarity pairs (>= {auto_merge_threshold:.2f})...")

    auto_merged_groups = {}
    remaining_for_llm = []

    # Track which insights have been merged
    merged_insight_ids = set()

    # Create mapping from insight to group
    insight_to_group = {}

    for insight1, insight2, similarity in candidates:
        if similarity >= auto_merge_threshold:
            # Auto-merge these insights
            id1 = id(insight1)  # Use object id as unique identifier
            id2 = id(insight2)

            # Check if either insight is already in a group
            group1 = insight_to_group.get(id1)
            group2 = insight_to_group.get(id2)

            if group1 and group2 and group1 != group2:
                # Merge two existing groups
                auto_merged_groups[group1].extend(auto_merged_groups[group2])
                # Update mapping for all insights in group2
                for insight in auto_merged_groups[group2]:
                    insight_to_group[id(insight)] = group1
                # Remove group2
                del auto_merged_groups[group2]

            elif group1:
                # Add insight2 to existing group1
                if insight2 not in auto_merged_groups[group1]:
                    auto_merged_groups[group1].append(insight2)
                insight_to_group[id2] = group1

            elif group2:
                # Add insight1 to existing group2
                if insight1 not in auto_merged_groups[group2]:
                    auto_merged_groups[group2].append(insight1)
                insight_to_group[id1] = group2

            else:
                # Create new group
                group_id = f"semantic_{len(auto_merged_groups)}"
                auto_merged_groups[group_id] = [insight1, insight2]
                insight_to_group[id1] = group_id
                insight_to_group[id2] = group_id

            merged_insight_ids.add(id1)
            merged_insight_ids.add(id2)

        else:
            # Below auto-merge threshold, needs LLM verification
            remaining_for_llm.append((insight1, insight2, similarity))

    total_auto_merged = sum(len(group) for group in auto_merged_groups.values())

    logger.info(f"Tier 2 auto-merge complete:")
    logger.info(f"  Auto-merged groups: {len(auto_merged_groups)}")
    logger.info(f"  Insights auto-merged: {total_auto_merged}")
    logger.info(f"  Remaining for LLM: {len(remaining_for_llm)}")

    return auto_merged_groups, remaining_for_llm


# =============================================================================
# Tier 3: LLM Verification (Ambiguous Cases)
# =============================================================================

def create_insight_verification_prompt(
    insight1: Dict[str, Any],
    insight2: Dict[str, Any],
    similarity_score: float
) -> str:
    """
    Create LLM prompt for insight match verification.

    Args:
        insight1: First insight dict
        insight2: Second insight dict
        similarity_score: Semantic similarity score

    Returns:
        Formatted prompt string
    """
    # Extract data
    content1 = insight1.get('content', 'N/A')
    title1 = insight1.get('title', 'N/A')
    category1 = insight1.get('category', 'unknown')
    scope1 = insight1.get('scope', {})
    scope_str1 = create_scope_key(scope1)

    content2 = insight2.get('content', 'N/A')
    title2 = insight2.get('title', 'N/A')
    category2 = insight2.get('category', 'unknown')
    scope2 = insight2.get('scope', {})
    scope_str2 = create_scope_key(scope2)

    prompt = f"""You are a travel insights matching expert. Determine if these two insights convey the SAME travel advice or information.

**Insight 1:**
- Title: {title1}
- Category: {category1}
- Scope: {scope_str1}
- Content: {content1}

**Insight 2:**
- Title: {title2}
- Category: {category2}
- Scope: {scope_str2}
- Content: {content2}

**Semantic Similarity:** {similarity_score:.2f} (from embeddings)

**Instructions:**
- Determine if these insights convey the SAME information (even if worded differently)
- Consider: paraphrasing, different wording, same advice
- Be strict: Similar but DIFFERENT advice should not match
  - Example: "Use Grab app" vs "Use Bolt app" → NOT the same (different apps)
  - Example: "Pack Type C adapter" vs "Bring power adapter" → SAME (same advice)
- Be flexible: Same insight with more/less detail should match
  - Example: "Get travel insurance" vs "Buy comprehensive travel insurance before trip" → SAME

**Answer ONLY with valid JSON (no markdown, no explanation outside JSON):**
{{
  "is_match": true,
  "confidence": 0.95,
  "reasoning": "Brief explanation of why they match or don't match"
}}

Response:"""

    return prompt


def verify_insight_with_llm(
    insight1: Dict[str, Any],
    insight2: Dict[str, Any],
    similarity_score: float,
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Verify if two insights are the same using LLM (Tier 3).

    Args:
        insight1: First insight dict
        insight2: Second insight dict
        similarity_score: Semantic similarity score
        max_retries: Maximum retry attempts

    Returns:
        Dict with:
            - is_match: bool
            - confidence: float (0.0-1.0)
            - reasoning: str
            - tokens_used: dict
            - cost_usd: float
    """
    # Create verification prompt
    prompt = create_insight_verification_prompt(insight1, insight2, similarity_score)

    # Call LLM (Gemini Flash for cost efficiency)
    result = extract_with_gemini(
        prompt=prompt,
        max_retries=max_retries,
        temperature=0.1,  # Low temperature for consistent verification
        max_tokens=200
    )

    if not result['success']:
        logger.warning(f"Tier 3: LLM verification failed: {result.get('error')}")
        return {
            'is_match': False,
            'confidence': 0.0,
            'reasoning': f"Verification failed: {result.get('error')}",
            'tokens_used': result['tokens_used'],
            'cost_usd': result['cost_usd'],
            'error': True
        }

    # Parse LLM response
    try:
        data = result['data']
        is_match = data.get('is_match', False)
        confidence = data.get('confidence', 0.0)
        reasoning = data.get('reasoning', 'No reasoning provided')

        return {
            'is_match': is_match,
            'confidence': confidence,
            'reasoning': reasoning,
            'tokens_used': result['tokens_used'],
            'cost_usd': result['cost_usd'],
            'error': False
        }

    except Exception as e:
        logger.error(f"Tier 3: Failed to parse LLM response: {e}")
        return {
            'is_match': False,
            'confidence': 0.0,
            'reasoning': f"Parse error: {e}",
            'tokens_used': result['tokens_used'],
            'cost_usd': result['cost_usd'],
            'error': True
        }


def batch_verify_with_llm(
    candidates: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
    min_confidence: float = 0.7
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Batch verify ambiguous candidates with LLM (Tier 3).

    Args:
        candidates: List of (insight1, insight2, similarity) tuples
        min_confidence: Minimum LLM confidence to merge (default: 0.7)

    Returns:
        Dict of verified match groups

    Example:
        >>> remaining_candidates = auto_merge_high_similarity(candidates)[1]
        >>> verified_groups = batch_verify_with_llm(remaining_candidates)
        >>> len(verified_groups)
        12
    """
    logger.info(f"Tier 3: Verifying {len(candidates)} candidates with LLM...")

    if not candidates:
        logger.info("Tier 3: No candidates to verify")
        return {}

    verified_groups = {}
    insight_to_group = {}
    total_cost = 0.0
    total_tokens = 0
    match_count = 0

    for insight1, insight2, similarity in candidates:
        # Verify with LLM
        result = verify_insight_with_llm(insight1, insight2, similarity)

        # Track cost
        total_cost += result.get('cost_usd', 0.0)
        total_tokens += result.get('tokens_used', {}).get('total', 0)

        # Check if match
        if result['is_match'] and result['confidence'] >= min_confidence:
            match_count += 1

            # Merge insights
            id1 = id(insight1)
            id2 = id(insight2)

            group1 = insight_to_group.get(id1)
            group2 = insight_to_group.get(id2)

            if group1 and group2 and group1 != group2:
                # Merge two existing groups
                verified_groups[group1].extend(verified_groups[group2])
                for insight in verified_groups[group2]:
                    insight_to_group[id(insight)] = group1
                del verified_groups[group2]

            elif group1:
                # Add insight2 to group1
                if insight2 not in verified_groups[group1]:
                    verified_groups[group1].append(insight2)
                insight_to_group[id2] = group1

            elif group2:
                # Add insight1 to group2
                if insight1 not in verified_groups[group2]:
                    verified_groups[group2].append(insight1)
                insight_to_group[id1] = group2

            else:
                # Create new group
                group_id = f"llm_verified_{len(verified_groups)}"
                verified_groups[group_id] = [insight1, insight2]
                insight_to_group[id1] = group_id
                insight_to_group[id2] = group_id

            logger.debug(
                f"Tier 3: Match confirmed (confidence: {result['confidence']:.2f}): "
                f"{result['reasoning']}"
            )

    total_verified = sum(len(group) for group in verified_groups.values())

    logger.info(f"Tier 3 complete:")
    logger.info(f"  Candidates verified: {len(candidates)}")
    logger.info(f"  Matches confirmed: {match_count}")
    logger.info(f"  Verified groups: {len(verified_groups)}")
    logger.info(f"  Insights in groups: {total_verified}")
    logger.info(f"  LLM cost: ${total_cost:.6f}")
    logger.info(f"  LLM tokens: {total_tokens:,}")

    return verified_groups


# =============================================================================
# Main Deduplication Pipeline
# =============================================================================

def deduplicate_insights(
    insights: List[Dict[str, Any]],
    semantic_threshold: float = 0.80,
    auto_merge_threshold: float = 0.90,
    llm_confidence_threshold: float = 0.7
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Deduplicate insights using 3-tier system.

    Args:
        insights: List of insight dicts from extraction
        semantic_threshold: Minimum similarity for Tier 2 candidates (default: 0.80)
        auto_merge_threshold: Auto-merge threshold for Tier 2 (default: 0.90)
        llm_confidence_threshold: Min LLM confidence for Tier 3 (default: 0.7)

    Returns:
        Tuple of (all_groups, stats):
        - all_groups: Dict of all duplicate groups (Tier 1 + Tier 2 + Tier 3)
        - stats: Dict with deduplication statistics

    Example:
        >>> insights = insights_storage.load_extracted_insights()
        >>> groups, stats = deduplicate_insights(insights)
        >>> print(f"Found {len(groups)} duplicate groups")
        >>> print(f"Total cost: ${stats['total_cost']:.6f}")
    """
    logger.info("=" * 80)
    logger.info("INSIGHTS DEDUPLICATION - 3-Tier System")
    logger.info("=" * 80)
    logger.info(f"Input insights: {len(insights)}")
    logger.info("")

    # Tier 1: Exact content match (hash-based)
    tier1_groups = group_exact_matches(insights)

    # Get singletons (insights not in any Tier 1 group)
    insights_in_tier1 = set()
    for group in tier1_groups.values():
        for insight in group:
            insights_in_tier1.add(id(insight))

    singletons = [
        insight for insight in insights
        if id(insight) not in insights_in_tier1
    ]

    logger.info(f"\nSingletons for Tier 2/3: {len(singletons)}")

    # Tier 2: Semantic similarity with embeddings
    embedding_client = EmbeddingClient()
    semantic_candidates = find_semantic_candidates(
        singletons,
        embedding_client,
        threshold=semantic_threshold
    )

    # Auto-merge high similarity pairs
    tier2_groups, tier3_candidates = auto_merge_high_similarity(
        semantic_candidates,
        auto_merge_threshold=auto_merge_threshold
    )

    # Tier 3: LLM verification for ambiguous cases
    tier3_groups = batch_verify_with_llm(
        tier3_candidates,
        min_confidence=llm_confidence_threshold
    )

    # Combine all groups
    all_groups = {}
    all_groups.update(tier1_groups)
    all_groups.update(tier2_groups)
    all_groups.update(tier3_groups)

    # Calculate statistics
    total_in_groups = sum(len(group) for group in all_groups.values())
    total_unique = len(insights) - total_in_groups + len(all_groups)

    # Estimate cost (Tier 2 embeddings + Tier 3 LLM)
    # Embeddings are free with cached client, only LLM has cost
    tier3_cost = sum(
        verify_insight_with_llm(i1, i2, sim)['cost_usd']
        for i1, i2, sim in tier3_candidates[:1]  # Just estimate from first call
    ) * len(tier3_candidates) if tier3_candidates else 0.0

    stats = {
        'total_insights': len(insights),
        'tier1_groups': len(tier1_groups),
        'tier1_insights': sum(len(g) for g in tier1_groups.values()),
        'tier2_groups': len(tier2_groups),
        'tier2_insights': sum(len(g) for g in tier2_groups.values()),
        'tier3_candidates': len(tier3_candidates),
        'tier3_groups': len(tier3_groups),
        'tier3_insights': sum(len(g) for g in tier3_groups.values()),
        'total_groups': len(all_groups),
        'total_in_groups': total_in_groups,
        'estimated_unique': total_unique,
        'total_cost': tier3_cost
    }

    logger.info("\n" + "=" * 80)
    logger.info("DEDUPLICATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total insights: {stats['total_insights']}")
    logger.info(f"Tier 1 (exact): {stats['tier1_groups']} groups, {stats['tier1_insights']} insights")
    logger.info(f"Tier 2 (semantic): {stats['tier2_groups']} groups, {stats['tier2_insights']} insights")
    logger.info(f"Tier 3 (LLM): {stats['tier3_groups']} groups, {stats['tier3_insights']} insights")
    logger.info(f"Total groups: {stats['total_groups']}")
    logger.info(f"Estimated unique insights: {stats['estimated_unique']}")
    logger.info(f"Total cost: ${stats['total_cost']:.6f}")
    logger.info("=" * 80)

    return all_groups, stats


# =============================================================================
# Testing
# =============================================================================

def test_deduplication():
    """Test deduplication with sample insights."""
    from src.utils.logging import setup_logging
    setup_logging(log_level='DEBUG')

    logger.info("=== Testing Insights Deduplication ===\n")

    # Test data with duplicates
    test_insights = [
        {
            'content': 'Use Grab app for ride-hailing in Southeast Asia. Cheaper than taxis.',
            'title': 'Grab for rides',
            'category': 'services',
            'scope': {'destination_type': 'region', 'region': 'Southeast Asia'}
        },
        {
            'content': 'Use the Grab app to get around. Much cheaper than regular taxis.',
            'title': 'Grab app',
            'category': 'services',
            'scope': {'destination_type': 'region', 'region': 'Southeast Asia'}
        },
        {
            'content': 'Pack a Type C power adapter for European travel.',
            'title': 'Power adapter for Europe',
            'category': 'tips',
            'scope': {'destination_type': 'region', 'region': 'Europe'}
        },
        {
            'content': 'Pack a Type C power adapter for European travel.',  # Exact duplicate
            'title': 'Power adapter',
            'category': 'tips',
            'scope': {'destination_type': 'region', 'region': 'Europe'}
        },
        {
            'content': 'Bring a power adapter with Type C plug for Europe.',
            'title': 'Adapter for Europe',
            'category': 'tips',
            'scope': {'destination_type': 'region', 'region': 'Europe'}
        }
    ]

    # Run deduplication
    groups, stats = deduplicate_insights(test_insights)

    logger.info(f"\n✓ Found {len(groups)} duplicate groups")
    logger.info(f"  Original insights: {stats['total_insights']}")
    logger.info(f"  Estimated unique: {stats['estimated_unique']}")

    logger.info("\n✅ Deduplication test complete!")


if __name__ == '__main__':
    test_deduplication()
