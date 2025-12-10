#!/usr/bin/env python3
"""
Search Canonical Entities

Search for canonical entities by name, city, or type with fuzzy matching.

Usage:
    python cli/search_entities.py --query "Khao San"
    python cli/search_entities.py --query "temple" --city "Bangkok"
    ./crawl.sh search-entities --query "beach" --type attraction
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
from rapidfuzz import fuzz

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


def search_entities(
    entities: List[Dict[str, Any]],
    query: str,
    city: str = None,
    entity_type: str = None,
    threshold: int = 60
) -> List[Dict[str, Any]]:
    """
    Search entities with fuzzy matching.

    Args:
        entities: List of canonical entities
        query: Search query
        city: Filter by city (optional)
        entity_type: Filter by entity type (optional)
        threshold: Fuzzy match threshold (0-100, default: 60)

    Returns:
        List of matching entities with scores
    """
    results = []

    query_lower = query.lower()

    for entity in entities:
        # Filter by city
        if city:
            entity_location = entity.get('location')
            if isinstance(entity_location, dict):
                entity_city = entity_location.get('city', '').lower()
            elif isinstance(entity_location, str):
                entity_city = entity_location.lower()
            else:
                entity_city = ''

            if city.lower() not in entity_city:
                continue

        # Filter by type
        if entity_type:
            if entity.get('entity_type', '').lower() != entity_type.lower():
                continue

        # Fuzzy match on canonical name
        canonical_name = entity.get('canonical_name', '')
        name_score = fuzz.partial_ratio(query_lower, canonical_name.lower())

        # Check aliases
        alias_scores = []
        for alias in entity.get('aliases', []):
            alias_score = fuzz.partial_ratio(query_lower, alias.lower())
            alias_scores.append(alias_score)

        max_alias_score = max(alias_scores) if alias_scores else 0

        # Use best score
        best_score = max(name_score, max_alias_score)

        if best_score >= threshold:
            results.append({
                'entity': entity,
                'score': best_score,
                'matched_field': 'name' if name_score >= max_alias_score else 'alias'
            })

    # Sort by score descending
    results.sort(key=lambda x: x['score'], reverse=True)

    return results


def print_search_results(results: List[Dict[str, Any]], limit: int = 20) -> None:
    """
    Print search results in formatted table.

    Args:
        results: List of search results
        limit: Max results to display
    """
    if not results:
        print("\n❌ No entities found matching your search criteria")
        print("   Try:")
        print("   - Using a less specific query")
        print("   - Removing filters (--city, --type)")
        print("   - Using different keywords")
        return

    print(f"\n✅ Found {len(results)} matching entities")
    print(f"   Showing top {min(limit, len(results))} results:")
    print("\n" + "=" * 100)
    print(f"{'Score':<8} {'Entity ID':<15} {'Name':<30} {'Type':<15} {'Location':<30}")
    print("=" * 100)

    for result in results[:limit]:
        entity = result['entity']
        score = result['score']
        entity_id = entity.get('entity_id', 'N/A')
        name = entity.get('canonical_name', 'N/A')
        entity_type = entity.get('entity_type', 'N/A')

        location = entity.get('location')
        if isinstance(location, dict):
            loc_str = f"{location.get('area', '')}, {location.get('city', '')}"
        elif isinstance(location, str):
            loc_str = location
        else:
            loc_str = 'N/A'

        # Truncate long names
        if len(name) > 28:
            name = name[:25] + "..."
        if len(loc_str) > 28:
            loc_str = loc_str[:25] + "..."

        print(f"{score:<8} {entity_id:<15} {name:<30} {entity_type:<15} {loc_str:<30}")

    print("=" * 100)

    if len(results) > limit:
        print(f"\n... and {len(results) - limit} more results")
        print(f"Use --limit {len(results)} to see all results")


@click.command()
@click.option('--query', '-q', required=True, help='Search query')
@click.option('--city', '-c', help='Filter by city (e.g., Bangkok)')
@click.option('--type', '-t', 'entity_type', help='Filter by entity type (e.g., attraction)')
@click.option('--limit', '-l', default=20, help='Max results to display (default: 20)')
@click.option('--threshold', default=60, help='Fuzzy match threshold 0-100 (default: 60)')
@click.option('--log-level', default='INFO', help='Logging level (default: INFO)')
def main(query: str, city: str, entity_type: str, limit: int, threshold: int, log_level: str):
    """
    Search canonical entities with fuzzy matching.

    Searches entity names and aliases, with optional filters for city and type.

    Examples:
        # Search for "Khao San"
        python cli/search_entities.py --query "Khao San"

        # Search for temples in Bangkok
        python cli/search_entities.py --query "temple" --city "Bangkok"

        # Search for beaches
        python cli/search_entities.py --query "beach" --type attraction

        # More permissive matching
        python cli/search_entities.py --query "wat" --threshold 40
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

        # Search
        logger.info(f"🔍 Searching for: '{query}'")
        if city:
            logger.info(f"   City filter: {city}")
        if entity_type:
            logger.info(f"   Type filter: {entity_type}")

        results = search_entities(
            entities=entities,
            query=query,
            city=city,
            entity_type=entity_type,
            threshold=threshold
        )

        # Print results
        print_search_results(results, limit=limit)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
