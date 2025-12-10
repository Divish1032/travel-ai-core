#!/usr/bin/env python3
"""
Stage 3 Statistics Tool

Displays comprehensive statistics about Stage 3 canonical entities:
- Entity counts by city and type
- Deduplication rate
- Geolocation success rate
- Cost summary

Usage:
    python cli/stage3_stats.py
    ./crawl.sh stage3-stats
"""

import sys
from pathlib import Path
from collections import Counter
from typing import Dict, Any, List

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


def calculate_stage3_stats(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate comprehensive Stage 3 statistics.

    Args:
        entities: List of canonical entities

    Returns:
        Dict with statistics
    """
    stats = {
        'total_entities': len(entities),
        'by_type': Counter(),
        'by_city': Counter(),
        'geocoded': 0,
        'not_geocoded': 0,
        'geocoding_providers': Counter(),
        'deduplicated_entities': 0,
        'singleton_entities': 0,
        'total_experiences': 0,
        'avg_experiences_per_entity': 0,
        'entities_with_consensus': 0,
        'avg_rating_distribution': Counter(),
    }

    for entity in entities:
        # Entity type
        entity_type = entity.get('entity_type', 'unknown')
        stats['by_type'][entity_type] += 1

        # City
        location = entity.get('location')
        if isinstance(location, dict):
            city = location.get('city', 'unknown')
        elif isinstance(location, str):
            city = location
        else:
            city = 'unknown'
        stats['by_city'][city] += 1

        # Geolocation
        coordinates = entity.get('coordinates')
        if coordinates:
            stats['geocoded'] += 1
            provider = coordinates.get('provider', 'unknown')
            stats['geocoding_providers'][provider] += 1
        else:
            stats['not_geocoded'] += 1

        # Deduplication
        experiences = entity.get('experiences', [])
        stats['total_experiences'] += len(experiences)
        if len(experiences) > 1:
            stats['deduplicated_entities'] += 1
        else:
            stats['singleton_entities'] += 1

        # Consensus
        consensus = entity.get('consensus')
        if consensus:
            stats['entities_with_consensus'] += 1
            avg_rating = consensus.get('avg_rating')
            if avg_rating:
                # Bucket ratings
                rating_bucket = int(avg_rating)
                stats['avg_rating_distribution'][rating_bucket] += 1

    # Calculate rates
    stats['avg_experiences_per_entity'] = stats['total_experiences'] / stats['total_entities'] if stats['total_entities'] > 0 else 0
    stats['geocoding_success_rate'] = stats['geocoded'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['deduplication_rate'] = (1 - stats['singleton_entities'] / stats['total_entities']) * 100 if stats['total_entities'] > 0 else 0

    return stats


def print_stage3_stats(stats: Dict[str, Any]) -> None:
    """
    Print Stage 3 statistics in formatted output.

    Args:
        stats: Statistics dict from calculate_stage3_stats()
    """
    print("\n" + "=" * 80)
    print("STAGE 3 CANONICAL ENTITIES - STATISTICS")
    print("=" * 80)

    # Overall counts
    print(f"\n📊 OVERALL:")
    print(f"   Total Entities: {stats['total_entities']:,}")
    print(f"   Total Experiences: {stats['total_experiences']:,}")
    print(f"   Avg Experiences/Entity: {stats['avg_experiences_per_entity']:.2f}")

    # Entity types
    print(f"\n🏷️  BY TYPE:")
    for entity_type, count in stats['by_type'].most_common():
        percentage = count / stats['total_entities'] * 100
        print(f"   {entity_type.title():20s}: {count:4d} ({percentage:5.1f}%)")

    # Cities (top 10)
    print(f"\n🏙️  BY CITY (Top 10):")
    for city, count in stats['by_city'].most_common(10):
        percentage = count / stats['total_entities'] * 100
        print(f"   {city:20s}: {count:4d} ({percentage:5.1f}%)")

    # Deduplication
    print(f"\n🔗 DEDUPLICATION:")
    print(f"   Deduplicated Entities: {stats['deduplicated_entities']:,} (multiple experiences)")
    print(f"   Singleton Entities: {stats['singleton_entities']:,} (single experience)")
    print(f"   Deduplication Rate: {stats['deduplication_rate']:.1f}%")

    # Geolocation
    print(f"\n🌍 GEOLOCATION:")
    print(f"   Geocoded: {stats['geocoded']:,} ({stats['geocoding_success_rate']:.1f}%)")
    print(f"   Not Geocoded: {stats['not_geocoded']:,}")
    if stats['geocoding_providers']:
        print(f"\n   By Provider:")
        for provider, count in stats['geocoding_providers'].most_common():
            percentage = count / stats['geocoded'] * 100 if stats['geocoded'] > 0 else 0
            cost_indicator = "(FREE)" if provider == 'nominatim' else "(PAID)"
            print(f"      {provider.title():12s} {cost_indicator}: {count:4d} ({percentage:5.1f}%)")

    # Consensus
    print(f"\n⭐ CONSENSUS:")
    print(f"   Entities with Consensus: {stats['entities_with_consensus']:,}")
    if stats['avg_rating_distribution']:
        print(f"\n   Rating Distribution:")
        for rating in sorted(stats['avg_rating_distribution'].keys(), reverse=True):
            count = stats['avg_rating_distribution'][rating]
            percentage = count / stats['entities_with_consensus'] * 100 if stats['entities_with_consensus'] > 0 else 0
            stars = "⭐" * rating
            print(f"      {rating} {stars:10s}: {count:4d} ({percentage:5.1f}%)")

    print("\n" + "=" * 80)


@click.command()
@click.option('--log-level', default='INFO', help='Logging level (default: INFO)')
def main(log_level: str):
    """
    Display Stage 3 canonical entities statistics.

    Shows entity counts by type and city, deduplication rate,
    geolocation success rate, and consensus statistics.

    Examples:
        # Display statistics
        python cli/stage3_stats.py

        # With debug logging
        python cli/stage3_stats.py --log-level DEBUG
    """
    # Setup logging
    setup_logging(log_level=log_level)

    try:
        # Initialize S3
        logger.info("📦 Initializing S3...")
        s3 = S3Storage()
        storage = Stage3Storage(s3)

        # Load canonical entities
        logger.info("📥 Loading canonical entities...")
        entities = storage.load_all_canonical_entities()

        if not entities:
            logger.error("❌ No canonical entities found")
            logger.info("Run Stage 3 processing first: ./crawl.sh process-stage3")
            sys.exit(1)

        logger.info(f"✅ Loaded {len(entities)} canonical entities")

        # Calculate statistics
        logger.info("📊 Calculating statistics...")
        stats = calculate_stage3_stats(entities)

        # Print statistics
        print_stage3_stats(stats)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Failed to generate statistics: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
