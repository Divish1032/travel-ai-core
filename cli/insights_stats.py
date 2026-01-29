#!/usr/bin/env python3
"""
Insights Pipeline Statistics Tool

Displays comprehensive statistics about insights pipeline:
- Insight counts by category and scope
- Quality, freshness, applicability scores
- Deduplication rate
- Video coverage
- Top insights by mentions

Usage:
    python cli/insights_stats.py
    ./crawl.sh insights-stats
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, Any, List

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.insights_storage import InsightsStorage
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


def calculate_insights_stats(insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate comprehensive insights pipeline statistics.

    Args:
        insights: List of canonical insights

    Returns:
        Dict with statistics
    """
    stats = {
        'total_insights': len(insights),
        'by_category': Counter(),
        'by_scope_type': Counter(),
        'by_destination': Counter(),
        'total_mentions': 0,
        'total_videos': 0,
        'unique_videos': set(),
        'avg_quality': 0.0,
        'avg_freshness': 0.0,
        'avg_applicability': 0.0,
        'quality_distribution': defaultdict(int),
        'freshness_distribution': defaultdict(int),
        'applicability_distribution': defaultdict(int),
        'top_insights': [],
        'deduplicated_insights': 0,
        'singleton_insights': 0,
    }

    if not insights:
        return stats

    quality_sum = 0.0
    freshness_sum = 0.0
    applicability_sum = 0.0

    for insight in insights:
        # Category
        category = insight.get('category', 'unknown')
        stats['by_category'][category] += 1

        # Scope
        scope = insight.get('scope', {})
        scope_type = scope.get('destination_type', 'unknown')
        stats['by_scope_type'][scope_type] += 1

        # Destination (for non-global scopes)
        if scope_type == 'country':
            destination = scope.get('country', 'unknown')
            stats['by_destination'][destination] += 1
        elif scope_type == 'region':
            destination = scope.get('region', 'unknown')
            stats['by_destination'][destination] += 1
        elif scope_type == 'city':
            city = scope.get('city', 'unknown')
            country = scope.get('country', '')
            destination = f"{city}, {country}" if country else city
            stats['by_destination'][destination] += 1

        # Mentions and videos
        mention_count = insight.get('mention_count', 1)
        stats['total_mentions'] += mention_count

        video_ids = insight.get('provenance', {}).get('source_video_ids', [])
        stats['unique_videos'].update(video_ids)

        # Deduplication
        if mention_count > 1:
            stats['deduplicated_insights'] += 1
        else:
            stats['singleton_insights'] += 1

        # Scores
        quality = insight.get('quality_score', 0.0)
        freshness = insight.get('freshness_score', 0.0)
        applicability = insight.get('applicability_score', 0.0)

        quality_sum += quality
        freshness_sum += freshness
        applicability_sum += applicability

        # Score distributions (bucketed 0.0-0.2, 0.2-0.4, etc.)
        quality_bucket = int(quality * 5) / 5  # Bucket to nearest 0.2
        freshness_bucket = int(freshness * 5) / 5
        applicability_bucket = int(applicability * 5) / 5

        stats['quality_distribution'][quality_bucket] += 1
        stats['freshness_distribution'][freshness_bucket] += 1
        stats['applicability_distribution'][applicability_bucket] += 1

        # Track for top insights
        stats['top_insights'].append({
            'title': insight.get('title', 'Untitled'),
            'category': category,
            'mention_count': mention_count,
            'quality_score': quality,
            'content': insight.get('content', '')[:100]  # First 100 chars
        })

    # Calculate averages
    if stats['total_insights'] > 0:
        stats['avg_quality'] = quality_sum / stats['total_insights']
        stats['avg_freshness'] = freshness_sum / stats['total_insights']
        stats['avg_applicability'] = applicability_sum / stats['total_insights']

    # Sort top insights by mention count
    stats['top_insights'].sort(key=lambda x: x['mention_count'], reverse=True)
    stats['top_insights'] = stats['top_insights'][:20]  # Keep top 20

    # Convert unique_videos set to count
    stats['total_videos'] = len(stats['unique_videos'])
    del stats['unique_videos']  # Remove set for serialization

    # Calculate deduplication rate
    stats['deduplication_rate'] = (
        (1 - stats['singleton_insights'] / stats['total_insights']) * 100
        if stats['total_insights'] > 0 else 0
    )

    return stats


def print_insights_stats(stats: Dict[str, Any]) -> None:
    """
    Print insights statistics in formatted output.

    Args:
        stats: Statistics dict from calculate_insights_stats()
    """
    print("\n" + "=" * 80)
    print("INSIGHTS PIPELINE - STATISTICS")
    print("=" * 80)

    # Overall counts
    print(f"\n📊 OVERALL:")
    print(f"   Total Canonical Insights: {stats['total_insights']:,}")
    print(f"   Total Mentions: {stats['total_mentions']:,}")
    print(f"   Unique Source Videos: {stats['total_videos']:,}")
    print(f"   Avg Mentions/Insight: {stats['total_mentions'] / stats['total_insights']:.2f}" if stats['total_insights'] > 0 else "   Avg Mentions/Insight: 0.00")

    # By category
    print(f"\n🏷️  BY CATEGORY:")
    for category, count in stats['by_category'].most_common():
        percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
        print(f"   {category.title():15s}: {count:4d} ({percentage:5.1f}%)")

    # By scope type
    print(f"\n🌍 BY SCOPE:")
    scope_order = ['global', 'region', 'country', 'city', 'area', 'unknown']
    for scope_type in scope_order:
        if scope_type in stats['by_scope_type']:
            count = stats['by_scope_type'][scope_type]
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            print(f"   {scope_type.title():15s}: {count:4d} ({percentage:5.1f}%)")

    # By destination (top 10)
    if stats['by_destination']:
        print(f"\n🗺️  BY DESTINATION (Top 10):")
        for destination, count in stats['by_destination'].most_common(10):
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            print(f"   {destination:30s}: {count:4d} ({percentage:5.1f}%)")

    # Deduplication
    print(f"\n🔗 DEDUPLICATION:")
    print(f"   Deduplicated Insights: {stats['deduplicated_insights']:,} (multiple mentions)")
    print(f"   Singleton Insights: {stats['singleton_insights']:,} (single mention)")
    print(f"   Deduplication Rate: {stats['deduplication_rate']:.1f}%")

    # Quality scores
    print(f"\n⭐ QUALITY SCORES:")
    print(f"   Average Quality: {stats['avg_quality']:.3f}")
    print(f"   Average Freshness: {stats['avg_freshness']:.3f}")
    print(f"   Average Applicability: {stats['avg_applicability']:.3f}")

    # Quality distribution
    print(f"\n   Quality Distribution:")
    for score in [0.8, 0.6, 0.4, 0.2, 0.0]:
        count = stats['quality_distribution'].get(score, 0)
        if count > 0:
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            bar = "█" * int(percentage / 2)
            print(f"   {score:.1f}-{score + 0.2:.1f}: {bar} {count:4d} ({percentage:5.1f}%)")

    # Top insights by mentions
    if stats['top_insights']:
        print(f"\n🔝 TOP INSIGHTS BY MENTIONS:")
        for i, insight in enumerate(stats['top_insights'][:10], 1):
            title = insight['title'] if insight['title'] and insight['title'] != 'N/A' else 'Untitled'
            print(f"   {i:2d}. {title[:50]:50s} ({insight['category']}, {insight['mention_count']} mentions)")
            if i <= 3:  # Show content for top 3
                content = insight['content']
                print(f"       → {content[:80]}...")

    print("\n" + "=" * 80)


@click.command()
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(log_level: str):
    """
    Display Insights Pipeline statistics.

    Examples:

        # Show insights statistics
        python cli/insights_stats.py

        # Using helper script
        ./crawl.sh insights-stats
    """
    # Setup logging
    setup_logging(log_level=log_level)

    logger.info("Loading insights data from S3...")

    try:
        # Initialize storage
        s3_storage = S3Storage()
        insights_storage = InsightsStorage(s3_storage)

        # Load canonical insights
        canonical_insights = insights_storage.load_all_canonical_insights()

        if not canonical_insights:
            print("\n⚠️  No canonical insights found!")
            print("\nPossible reasons:")
            print("  1. Insights haven't been extracted yet (run: ./crawl.sh process-insights)")
            print("  2. Insights haven't been deduplicated/canonicalized yet")
            print("  3. S3 bucket is empty")
            return

        logger.info(f"Loaded {len(canonical_insights)} canonical insights")

        # Calculate statistics
        stats = calculate_insights_stats(canonical_insights)

        # Print statistics
        print_insights_stats(stats)

    except Exception as e:
        logger.error(f"Failed to load insights: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
