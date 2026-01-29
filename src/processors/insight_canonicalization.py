"""
Insights Canonicalization: Create Canonical Insights from Deduplicated Groups

Converts deduplicated insight groups into canonical insights with:
- Consensus content selection (most comprehensive/descriptive)
- Unique insight IDs (from InsightRegistry)
- Aliases tracking
- Quality, freshness, and applicability scoring
- Aggregated provenance (all source videos)
- Merged mention counts

Usage:
    from src.processors.insight_canonicalization import canonicalize_insight_groups

    canonical_insights = canonicalize_insight_groups(
        dedup_groups=groups,
        insight_registry=registry
    )

    print(f"Created {len(canonical_insights)} canonical insights")
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime, timezone

# Add project root to path if running as main
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.insight_registry import InsightRegistry, content_hash
from src.utils.schemas import CanonicalInsight
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Consensus Content Selection
# =============================================================================

def choose_consensus_content(insight_group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Choose the best consensus content from an insight group.

    Strategy:
    1. Pick most comprehensive content (longest with most detail)
    2. If tie: Pick content with highest confidence score
    3. Track alternatives as aliases

    Args:
        insight_group: List of insight dicts with 'content', 'title', 'confidence_score'

    Returns:
        Dict with consensus_content, consensus_title, reasoning, alternatives, avg_confidence
    """
    if not insight_group:
        return {
            'consensus_content': 'Unknown',
            'consensus_title': 'Unknown',
            'reasoning': 'Empty insight group',
            'alternatives': [],
            'avg_confidence': 0.0
        }

    # Sort by content length (descending) then by confidence (descending)
    sorted_insights = sorted(
        insight_group,
        key=lambda x: (len(x.get('content', '')), x.get('confidence_score', 0.0)),
        reverse=True
    )

    # Select best insight
    best_insight = sorted_insights[0]
    consensus_content = best_insight.get('content', 'Unknown')
    consensus_title = best_insight.get('title', 'Unknown')
    best_confidence = best_insight.get('confidence_score', 0.0)

    # Calculate average confidence
    confidences = [i.get('confidence_score', 0.0) for i in insight_group]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Collect alternative contents
    alternatives = []
    for insight in insight_group:
        content = insight.get('content', '')
        if content != consensus_content and content not in alternatives:
            alternatives.append(content)

    # Reasoning
    if len(insight_group) == 1:
        reasoning = 'Single insight (no consensus needed)'
    elif len(consensus_content) > max(len(i.get('content', '')) for i in sorted_insights[1:]):
        reasoning = f'Most comprehensive ({len(consensus_content)} chars, conf: {best_confidence:.2f})'
    else:
        reasoning = f'Highest confidence (conf: {best_confidence:.2f})'

    return {
        'consensus_content': consensus_content,
        'consensus_title': consensus_title,
        'reasoning': reasoning,
        'alternatives': alternatives,
        'avg_confidence': avg_confidence
    }


# =============================================================================
# Quality Scoring
# =============================================================================

def calculate_quality_score(
    insight_group: List[Dict[str, Any]],
    consensus_content: str
) -> float:
    """Calculate quality score (0.0-1.0) based on content, confidence, mentions, completeness."""
    # Factor 1: Content length (50-200 chars)
    content_length = len(consensus_content)
    length_score = min(1.0, max(0.0, (content_length - 50) / 150))

    # Factor 2: Average confidence
    confidences = [i.get('confidence_score', 0.0) for i in insight_group]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    # Factor 3: Number of mentions
    mention_count = len(insight_group)
    mention_score = min(1.0, 0.5 + (mention_count - 1) * 0.125)

    # Factor 4: Completeness (has title and details)
    has_title = any(i.get('title') and len(i.get('title', '')) > 5 for i in insight_group)
    has_details = any(i.get('details') and len(i.get('details', '')) > 20 for i in insight_group)
    completeness_score = 0.5 + (0.25 if has_title else 0.0) + (0.25 if has_details else 0.0)

    # Weighted average
    quality_score = (
        length_score * 0.25 +
        avg_confidence * 0.35 +
        mention_score * 0.25 +
        completeness_score * 0.15
    )

    return round(quality_score, 3)


def calculate_freshness_score(insight_group: List[Dict[str, Any]]) -> float:
    """Calculate freshness score (0.0-1.0) based on extraction dates."""
    dates = []
    for insight in insight_group:
        provenance = insight.get('provenance', {})
        date_str = provenance.get('extraction_date')
        if date_str:
            try:
                date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                dates.append(date)
            except Exception:
                continue

    if not dates:
        return 0.5

    most_recent = max(dates)
    days_old = (datetime.now(timezone.utc) - most_recent).days

    # Freshness decay: 0-30 days = 1.0, 30-180 days = 0.8-0.5, 180+ = 0.5
    if days_old <= 30:
        freshness = 1.0
    elif days_old <= 180:
        freshness = 1.0 - (days_old - 30) / 300
    else:
        freshness = 0.5

    return round(freshness, 3)


def calculate_applicability_score(
    insight_group: List[Dict[str, Any]],
    scope: Dict[str, Any]
) -> float:
    """Calculate applicability score (0.0-1.0) based on scope and video diversity."""
    # Factor 1: Scope breadth
    dest_type = scope.get('destination_type', 'unknown')
    scope_scores = {
        'global': 1.0, 'region': 0.8, 'country': 0.6,
        'city': 0.4, 'area': 0.2, 'unknown': 0.3
    }
    scope_score = scope_scores.get(dest_type, 0.3)

    # Factor 2: Video diversity
    all_video_ids = set()
    for insight in insight_group:
        provenance = insight.get('provenance', {})
        video_ids = provenance.get('source_video_ids', [])
        all_video_ids.update(video_ids)

    video_count = len(all_video_ids)
    video_diversity_score = min(1.0, 0.5 + (video_count - 1) * 0.125)

    # Weighted average
    applicability = scope_score * 0.6 + video_diversity_score * 0.4

    return round(applicability, 3)


# =============================================================================
# Canonical Insight Creation
# =============================================================================

def canonicalize_insight_group(
    insight_group: List[Dict[str, Any]],
    insight_registry: InsightRegistry
) -> Dict[str, Any]:
    """Create a canonical insight from a deduplicated group."""
    if not insight_group:
        logger.warning("Empty insight group")
        return None

    # Get category and scope
    category = insight_group[0].get('category', 'unknown')
    scope = insight_group[0].get('scope', {})

    # Choose consensus content
    consensus = choose_consensus_content(insight_group)

    # Generate or find existing insight ID
    existing_id = None
    for insight in insight_group:
        if insight.get('insight_id') and insight['insight_id'].startswith('INS_'):
            existing_id = insight['insight_id']
            break

    if existing_id:
        insight_id = existing_id
    else:
        matching_id = insight_registry.find_matching_insight(
            content=consensus['consensus_content'],
            category=category,
            scope=scope
        )
        insight_id = matching_id if matching_id else insight_registry.generate_insight_id(category)

    # Collect all source video IDs
    all_video_ids = set()
    for insight in insight_group:
        provenance = insight.get('provenance', {})
        video_ids = provenance.get('source_video_ids', [])
        all_video_ids.update(video_ids)

    # Collect merged_from IDs
    merged_from = []
    for insight in insight_group:
        raw_id = content_hash(insight.get('content', ''), category, scope)
        merged_from.append(raw_id)

    # Calculate scores
    quality_score = calculate_quality_score(insight_group, consensus['consensus_content'])
    freshness_score = calculate_freshness_score(insight_group)
    applicability_score = calculate_applicability_score(insight_group, scope)

    # Aggregate tags
    all_tags = []
    for insight in insight_group:
        all_tags.extend(insight.get('tags', []))
    unique_tags = sorted(set(all_tags))

    # Get best title and details
    best_title = consensus['consensus_title']
    best_details = ''
    for insight in insight_group:
        details = insight.get('details', '')
        if len(details) > len(best_details):
            best_details = details

    # Get extraction method from first insight (should be same for all in group)
    extraction_method = insight_group[0].get('provenance', {}).get('extraction_method', 'entity_enrichment')

    # Get extracted timestamp (use earliest one)
    extracted_timestamps = []
    for insight in insight_group:
        provenance = insight.get('provenance', {})
        ts_str = provenance.get('extraction_date') or provenance.get('extracted_timestamp')
        if ts_str:
            try:
                extracted_timestamps.append(datetime.fromisoformat(ts_str.replace('Z', '+00:00')))
            except Exception:
                pass
    earliest_timestamp = min(extracted_timestamps) if extracted_timestamps else datetime.now(timezone.utc)

    # Build canonical insight (ensure all datetime fields are strings)
    canonical = {
        'insight_id': insight_id,
        'category': category,
        'content': consensus['consensus_content'],
        'title': best_title if best_title and best_title != 'N/A' else None,
        'scope': scope,
        'confidence_score': consensus['avg_confidence'],
        'mention_count': len(insight_group),
        'video_count': len(all_video_ids),
        'provenance': {
            'source_video_ids': sorted(list(all_video_ids)),
            'extraction_method': extraction_method,
            'extraction_date': earliest_timestamp.isoformat(),
            'extracted_timestamp': earliest_timestamp.isoformat(),
            'canonicalization_reasoning': consensus['reasoning']
        },
        'tags': unique_tags,
        'merged_from': merged_from,
        'consensus_content': consensus['consensus_content'],
        'aliases': consensus['alternatives'],
        'quality_score': quality_score,
        'freshness_score': freshness_score,
        'applicability_score': applicability_score
    }

    if best_details:
        canonical['details'] = best_details

    # Validate against CanonicalInsight schema
    try:
        validated = CanonicalInsight(**canonical)
        return validated.model_dump()
    except Exception as e:
        logger.error(f"Failed to validate canonical insight: {e}")
        return None


def canonicalize_insight_groups(
    dedup_groups: Dict[str, List[Dict[str, Any]]],
    insight_registry: InsightRegistry
) -> List[Dict[str, Any]]:
    """Convert all deduplicated groups to canonical insights."""
    logger.info("=" * 80)
    logger.info("INSIGHTS CANONICALIZATION")
    logger.info("=" * 80)
    logger.info(f"Input groups: {len(dedup_groups)}")

    canonical_insights = []
    failed_count = 0

    for group_id, insight_group in dedup_groups.items():
        try:
            canonical = canonicalize_insight_group(insight_group, insight_registry)

            if canonical:
                canonical_insights.append(canonical)
                insight_registry.register_new_insight(canonical, generate_id=False)
            else:
                failed_count += 1

        except Exception as e:
            failed_count += 1
            logger.error(f"Error canonicalizing group {group_id}: {e}")
            continue

    # Statistics
    total_mentions = sum(i['mention_count'] for i in canonical_insights)
    total_videos = len(set(
        vid
        for i in canonical_insights
        for vid in i['provenance']['source_video_ids']
    ))

    avg_quality = sum(i['quality_score'] for i in canonical_insights) / len(canonical_insights) if canonical_insights else 0.0
    avg_freshness = sum(i['freshness_score'] for i in canonical_insights) / len(canonical_insights) if canonical_insights else 0.0
    avg_applicability = sum(i['applicability_score'] for i in canonical_insights) / len(canonical_insights) if canonical_insights else 0.0

    # Category breakdown
    category_counts = defaultdict(int)
    for insight in canonical_insights:
        category_counts[insight['category']] += 1

    logger.info("\n" + "=" * 80)
    logger.info("CANONICALIZATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Canonical insights: {len(canonical_insights)}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total mentions: {total_mentions}")
    logger.info(f"Unique videos: {total_videos}")
    logger.info(f"\nAverage Scores:")
    logger.info(f"  Quality: {avg_quality:.3f}")
    logger.info(f"  Freshness: {avg_freshness:.3f}")
    logger.info(f"  Applicability: {avg_applicability:.3f}")
    logger.info(f"\nBy Category:")
    for category, count in sorted(category_counts.items()):
        logger.info(f"  {category}: {count}")
    logger.info("=" * 80)

    return canonical_insights
