#!/usr/bin/env python3
"""
Pipeline Statistics Tool

Unified tool for viewing statistics across all pipeline stages.

Usage:
    # Stage 3 (Deduplication) stats
    python cli/stats.py stage3

    # Insights pipeline stats
    python cli/stats.py insights

    # Stage 4 (Vector DB) stats
    python cli/stats.py stage4
    python cli/stats.py stage4 --detailed
    python cli/stats.py stage4 --json

Examples:
    # View canonical entities statistics
    ./crawl.sh stats stage3

    # View insights pipeline statistics
    ./crawl.sh stats insights

    # View vector database statistics
    ./crawl.sh stats stage4
"""

import sys
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, Any, List
from datetime import datetime

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal
from src.database.models import CanonicalEntity, Insight
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ============================================================================
# STAGE 3 STATISTICS
# ============================================================================

def calculate_stage3_stats(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate comprehensive Stage 3 statistics."""
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
                rating_bucket = int(avg_rating)
                stats['avg_rating_distribution'][rating_bucket] += 1

    # Calculate rates
    stats['avg_experiences_per_entity'] = stats['total_experiences'] / stats['total_entities'] if stats['total_entities'] > 0 else 0
    stats['geocoding_success_rate'] = stats['geocoded'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['deduplication_rate'] = (1 - stats['singleton_entities'] / stats['total_entities']) * 100 if stats['total_entities'] > 0 else 0

    return stats


def print_stage3_stats(stats: Dict[str, Any]) -> None:
    """Print Stage 3 statistics in formatted output."""
    print("\n" + "=" * 80)
    print("STAGE 3: CANONICAL ENTITIES STATISTICS")
    print("=" * 80)

    # Overall counts
    print("\n📊 OVERALL:")
    print(f"   Total Entities: {stats['total_entities']:,}")
    print(f"   Total Experiences: {stats['total_experiences']:,}")
    print(f"   Avg Experiences/Entity: {stats['avg_experiences_per_entity']:.2f}")

    # Entity types
    print("\n🏷️  BY TYPE:")
    for entity_type, count in stats['by_type'].most_common():
        percentage = count / stats['total_entities'] * 100
        print(f"   {entity_type.title():20s}: {count:4d} ({percentage:5.1f}%)")

    # Cities (top 10)
    print("\n🏙️  BY CITY (Top 10):")
    for city, count in stats['by_city'].most_common(10):
        percentage = count / stats['total_entities'] * 100
        print(f"   {city:20s}: {count:4d} ({percentage:5.1f}%)")

    # Deduplication
    print("\n🔗 DEDUPLICATION:")
    print(f"   Deduplicated Entities: {stats['deduplicated_entities']:,} (multiple experiences)")
    print(f"   Singleton Entities: {stats['singleton_entities']:,} (single experience)")
    print(f"   Deduplication Rate: {stats['deduplication_rate']:.1f}%")

    # Geolocation
    print("\n🌍 GEOLOCATION:")
    print(f"   Geocoded: {stats['geocoded']:,} ({stats['geocoding_success_rate']:.1f}%)")
    print(f"   Not Geocoded: {stats['not_geocoded']:,}")
    if stats['geocoding_providers']:
        print("\n   By Provider:")
        for provider, count in stats['geocoding_providers'].most_common():
            percentage = count / stats['geocoded'] * 100 if stats['geocoded'] > 0 else 0
            cost_indicator = "(FREE)" if provider == 'nominatim' else "(PAID)"
            print(f"      {provider.title():12s} {cost_indicator}: {count:4d} ({percentage:5.1f}%)")

    # Consensus
    print("\n⭐ CONSENSUS:")
    print(f"   Entities with Consensus: {stats['entities_with_consensus']:,}")
    if stats['avg_rating_distribution']:
        print("\n   Rating Distribution:")
        for rating in sorted(stats['avg_rating_distribution'].keys(), reverse=True):
            count = stats['avg_rating_distribution'][rating]
            percentage = count / stats['entities_with_consensus'] * 100 if stats['entities_with_consensus'] > 0 else 0
            stars = "⭐" * rating
            print(f"      {rating} {stars:10s}: {count:4d} ({percentage:5.1f}%)")

    print("\n" + "=" * 80)


# ============================================================================
# INSIGHTS STATISTICS
# ============================================================================

def calculate_insights_stats(insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate comprehensive insights pipeline statistics."""
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

        # Score distributions
        quality_bucket = int(quality * 5) / 5
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
            'content': insight.get('content', '')[:100]
        })

    # Calculate averages
    if stats['total_insights'] > 0:
        stats['avg_quality'] = quality_sum / stats['total_insights']
        stats['avg_freshness'] = freshness_sum / stats['total_insights']
        stats['avg_applicability'] = applicability_sum / stats['total_insights']

    # Sort top insights by mention count
    stats['top_insights'].sort(key=lambda x: x['mention_count'], reverse=True)
    stats['top_insights'] = stats['top_insights'][:20]

    # Convert unique_videos set to count
    stats['total_videos'] = len(stats['unique_videos'])
    del stats['unique_videos']

    # Calculate deduplication rate
    stats['deduplication_rate'] = (
        (1 - stats['singleton_insights'] / stats['total_insights']) * 100
        if stats['total_insights'] > 0 else 0
    )

    return stats


def print_insights_stats(stats: Dict[str, Any]) -> None:
    """Print insights statistics in formatted output."""
    print("\n" + "=" * 80)
    print("INSIGHTS PIPELINE STATISTICS")
    print("=" * 80)

    # Overall counts
    print("\n📊 OVERALL:")
    print(f"   Total Canonical Insights: {stats['total_insights']:,}")
    print(f"   Total Mentions: {stats['total_mentions']:,}")
    print(f"   Unique Source Videos: {stats['total_videos']:,}")
    print(f"   Avg Mentions/Insight: {stats['total_mentions'] / stats['total_insights']:.2f}" if stats['total_insights'] > 0 else "   Avg Mentions/Insight: 0.00")

    # By category
    print("\n🏷️  BY CATEGORY:")
    for category, count in stats['by_category'].most_common():
        percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
        print(f"   {category.title():15s}: {count:4d} ({percentage:5.1f}%)")

    # By scope type
    print("\n🌍 BY SCOPE:")
    scope_order = ['global', 'region', 'country', 'city', 'area', 'unknown']
    for scope_type in scope_order:
        if scope_type in stats['by_scope_type']:
            count = stats['by_scope_type'][scope_type]
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            print(f"   {scope_type.title():15s}: {count:4d} ({percentage:5.1f}%)")

    # By destination (top 10)
    if stats['by_destination']:
        print("\n🗺️  BY DESTINATION (Top 10):")
        for destination, count in stats['by_destination'].most_common(10):
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            print(f"   {destination:30s}: {count:4d} ({percentage:5.1f}%)")

    # Deduplication
    print("\n🔗 DEDUPLICATION:")
    print(f"   Deduplicated Insights: {stats['deduplicated_insights']:,} (multiple mentions)")
    print(f"   Singleton Insights: {stats['singleton_insights']:,} (single mention)")
    print(f"   Deduplication Rate: {stats['deduplication_rate']:.1f}%")

    # Quality scores
    print("\n⭐ QUALITY SCORES:")
    print(f"   Average Quality: {stats['avg_quality']:.3f}")
    print(f"   Average Freshness: {stats['avg_freshness']:.3f}")
    print(f"   Average Applicability: {stats['avg_applicability']:.3f}")

    # Quality distribution
    print("\n   Quality Distribution:")
    for score in [0.8, 0.6, 0.4, 0.2, 0.0]:
        count = stats['quality_distribution'].get(score, 0)
        if count > 0:
            percentage = count / stats['total_insights'] * 100 if stats['total_insights'] > 0 else 0
            bar = "█" * int(percentage / 2)
            print(f"   {score:.1f}-{score + 0.2:.1f}: {bar} {count:4d} ({percentage:5.1f}%)")

    # Top insights by mentions
    if stats['top_insights']:
        print("\n🔝 TOP INSIGHTS BY MENTIONS:")
        for i, insight in enumerate(stats['top_insights'][:10], 1):
            title = insight['title'] if insight['title'] and insight['title'] != 'N/A' else 'Untitled'
            print(f"   {i:2d}. {title[:50]:50s} ({insight['category']}, {insight['mention_count']} mentions)")
            if i <= 3:
                content = insight['content']
                print(f"       → {content[:80]}...")

    print("\n" + "=" * 80)


# ============================================================================
# STAGE 4 STATISTICS
# ============================================================================

def format_bytes(bytes_count: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} PB"


def get_stage4_collection_stats() -> Dict[str, Any]:
    """Get statistics for all ChromaDB collections."""
    from src.vectordb.chromadb_client import ChromaDBClient

    stats = {}
    chromadb = ChromaDBClient.initialize_from_env()

    collections_map = {
        'entities': chromadb.entities_collection,
        'profile_consensus': chromadb.profile_consensus_collection,
        'experiences': chromadb.experiences_collection,
        'city_destinations': chromadb.city_destinations_collection
    }

    for collection_name, collection in collections_map.items():
        try:
            if collection:
                count = collection.count()
                embedding_size = count * 1024 * 4 if count > 0 else 0

                stats[collection_name] = {
                    'count': count,
                    'storage_bytes': embedding_size,
                    'storage_formatted': format_bytes(embedding_size)
                }
            else:
                stats[collection_name] = {
                    'count': 0,
                    'storage_bytes': 0,
                    'storage_formatted': '0 B'
                }
        except Exception as e:
            logger.warning(f"Error getting stats for {collection_name}: {e}")
            stats[collection_name] = {
                'count': 0,
                'storage_bytes': 0,
                'storage_formatted': '0 B',
                'error': str(e)
            }

    return stats


def print_stage4_stats(detailed: bool = False):
    """Display Stage 4 statistics."""
    print("\n" + "=" * 80)
    print("STAGE 4: VECTOR DATABASE STATISTICS")
    print("=" * 80)

    print("\n🔌 ChromaDB Mode: CHROMA CLOUD")

    print("\n📊 Collection Statistics:")
    print("=" * 80)

    collection_stats = get_stage4_collection_stats()

    total_embeddings = 0
    total_storage = 0

    for name, stats in collection_stats.items():
        count = stats['count']
        storage = stats['storage_formatted']

        total_embeddings += count
        total_storage += stats['storage_bytes']

        print(f"\n  {name.replace('_', ' ').title()}:")
        print(f"    Embeddings: {count:,}")
        print(f"    Storage: {storage}")

        if 'error' in stats:
            print(f"    ⚠️  Error: {stats['error']}")

    print("\n  Total:")
    print(f"    Embeddings: {total_embeddings:,}")
    print(f"    Storage: {format_bytes(total_storage)}")

    print("\n\n💰 Cost and Performance:")
    print("=" * 80)
    print("\n  Embedding Model:")
    print("    Model: gte-large (1024 dimensions)")
    print("    Cost: FREE (local inference)")

    print("\n  Total Indexed:")
    print(f"    Entities: {total_embeddings:,} vectors")
    print(f"    Storage: {format_bytes(total_storage)}")

    if detailed:
        print("\n\n📈 Detailed Collection Breakdown:")
        print("=" * 80)

        for name, stats in collection_stats.items():
            if stats['count'] > 0:
                print(f"\n  {name.replace('_', ' ').title()}:")
                print(f"    Vectors: {stats['count']:,}")
                print(f"    Storage: {stats['storage_formatted']}")
                print("    Avg size per vector: ~4 KB")

    print("\n" + "=" * 80)


def export_stage4_json():
    """Export Stage 4 statistics as JSON."""
    from src.vectordb.chromadb_client import ChromaDBClient

    chromadb = ChromaDBClient.initialize_from_env()
    collection_stats = get_stage4_collection_stats()

    export_data = {
        'timestamp': datetime.now().isoformat(),
        'chromadb_mode': 'cloud',
        'collections': collection_stats
    }

    print(json.dumps(export_data, indent=2))


# ============================================================================
# CLI COMMANDS
# ============================================================================

@click.group()
def cli():
    """Pipeline statistics tool for all stages."""
    pass


@cli.command()
@click.option('--log-level', default='INFO', help='Logging level')
def stage3(log_level: str):
    """
    Display Stage 3 canonical entities statistics.

    Shows entity counts by type and city, deduplication rate,
    geolocation success rate, and consensus statistics.
    """
    setup_logging(log_level=log_level)

    try:
        logger.info("📦 Connecting to PostgreSQL...")
        db = SessionLocal()

        logger.info("📥 Loading canonical entities from PostgreSQL...")
        canonical_entities = db.query(CanonicalEntity).all()

        if not canonical_entities:
            logger.error("❌ No canonical entities found in PostgreSQL")
            logger.info("Run Stage 3 processing first: ./crawl.sh process-stage3")
            db.close()
            sys.exit(1)

        logger.info(f"✅ Loaded {len(canonical_entities)} canonical entities")

        # Convert ORM models to dicts
        entities = []
        for entity in canonical_entities:
            entity_dict = {
                'entity_type': entity.entity_type.value if entity.entity_type else 'unknown',
                'location': entity.location or 'unknown',
                'coordinates': {
                    'lat': entity.lat,
                    'lon': entity.lon,
                    'provider': entity.geocode_provider
                } if entity.lat and entity.lon else None,
                'experiences': entity.experiences or [],
                'consensus': entity.consensus or {}
            }
            entities.append(entity_dict)

        db.close()

        # Calculate and print statistics
        logger.info("📊 Calculating statistics...")
        stats = calculate_stage3_stats(entities)
        print_stage3_stats(stats)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Failed to generate statistics: {e}")
        logger.exception(e)
        sys.exit(1)


@cli.command()
@click.option('--log-level', default='INFO', help='Logging level')
def insights(log_level: str):
    """
    Display Insights Pipeline statistics.

    Shows insight counts by category and scope, quality scores,
    deduplication rate, and top insights by mentions.
    """
    setup_logging(log_level=log_level)

    logger.info("Loading insights data from PostgreSQL...")

    db = None
    try:
        db = SessionLocal()

        insights_query = db.query(Insight).filter(Insight.is_canonical == True).all()

        if not insights_query:
            print("\n⚠️  No canonical insights found!")
            print("\nPossible reasons:")
            print("  1. Insights haven't been extracted yet (run: ./crawl.sh process-insights)")
            print("  2. Insights haven't been canonicalized yet (run: ./crawl.sh canonicalize-insights)")
            print("  3. PostgreSQL database is empty")
            return

        logger.info(f"Loaded {len(insights_query)} canonical insights")

        # Convert ORM models to dicts
        canonical_insights = []
        for insight in insights_query:
            insight_dict = {
                'category': insight.category,
                'subcategory': insight.subcategory,
                'insight_text': insight.insight_text,
                'scope': {
                    'destination_type': insight.destination,
                    'city': insight.destination if insight.destination not in ['general', 'global'] else None,
                    'country': None,
                    'region': None
                },
                'mention_count': insight.source_count or 1,
                'provenance': {
                    'source_video_ids': []
                },
                'quality_score': insight.confidence_score,
                'freshness_score': 0.8,
                'applicability_score': 0.8,
                'title': insight.insight_text[:50] if insight.insight_text else 'N/A'
            }
            canonical_insights.append(insight_dict)

        # Calculate and print statistics
        stats = calculate_insights_stats(canonical_insights)
        print_insights_stats(stats)

    except Exception as e:
        logger.error(f"Failed to load insights: {e}")
        sys.exit(1)
    finally:
        if db:
            db.close()


@cli.command()
@click.option('--detailed', '-d', is_flag=True, help='Show detailed statistics')
@click.option('--json', '-j', is_flag=True, help='Export statistics as JSON')
@click.option('--log-level', default='INFO', help='Logging level')
def stage4(detailed: bool, json: bool, log_level: str):
    """
    Display Stage 4 vector database statistics.

    Shows collection sizes, embedding counts, storage utilization,
    and cost metrics.
    """
    setup_logging(log_level=log_level)

    try:
        if json:
            export_stage4_json()
        else:
            print_stage4_stats(detailed=detailed)
    except Exception as e:
        logger.error(f"❌ Error generating statistics: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    cli()
