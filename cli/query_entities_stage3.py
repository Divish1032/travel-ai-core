#!/usr/bin/env python3
"""
Entity Query Tool

Unified tool for querying and viewing canonical entities from PostgreSQL.

Commands:
    show    - Show detailed information about a specific entity
    search  - Search entities by name, city, or type

Usage:
    # Show entity details
    python cli/query_entities_stage3.py show <entity_id>

    # Search entities
    python cli/query_entities_stage3.py search --query "Khao San"
    python cli/query_entities_stage3.py search --query "temple" --city "Bangkok"
    python cli/query_entities_stage3.py search --query "beach" --type attraction

Examples:
    # Show entity by ID
    ./crawl.sh query show ATT_001

    # Search for entities
    ./crawl.sh query search --query "restaurant" --city "Bangkok"
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import click
from rapidfuzz import fuzz

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal
from src.database.models import CanonicalEntity, EntityExperience
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ============================================================================
# SHOW ENTITY
# ============================================================================


def print_entity_details(entity: CanonicalEntity) -> None:
    """
    Print formatted entity details from PostgreSQL CanonicalEntity model.

    Args:
        entity: CanonicalEntity ORM model
    """
    print("\n" + "=" * 80)
    print(f"CANONICAL ENTITY: {entity.canonical_name or 'N/A'}")
    print("=" * 80)

    # Basic info
    print("\n📋 BASIC INFORMATION:")
    print(f"   Entity ID: {entity.entity_id}")
    print(f"   Canonical Name: {entity.canonical_name or 'N/A'}")
    print(
        f"   Entity Type: {entity.entity_type.value if entity.entity_type else 'N/A'}"
    )

    # Aliases
    if entity.aliases:
        print(f"   Aliases: {', '.join(entity.aliases)}")

    # Location
    print("\n📍 LOCATION:")
    print(f"   Location: {entity.location or 'N/A'}")

    # Coordinates
    if entity.lat and entity.lon:
        print("\n🌍 COORDINATES:")
        print(f"   Latitude: {entity.lat}")
        print(f"   Longitude: {entity.lon}")
        if entity.geocode_provider:
            print(f"   Provider: {entity.geocode_provider}")
        if entity.google_place_id:
            print(f"   Google Place ID: {entity.google_place_id}")

        # Map link
        print(
            f"   Google Maps: https://www.google.com/maps/search/?api=1&query={entity.lat},{entity.lon}"
        )
    else:
        print("\n🌍 COORDINATES: Not geocoded")

    # Consensus
    if entity.consensus:
        consensus = entity.consensus
        print("\n⭐ CONSENSUS DATA:")
        mention_count = consensus.get("mention_count", 0)
        print(f"   Mention Count: {mention_count}")

        avg_rating = consensus.get("avg_rating")
        if avg_rating:
            stars = "⭐" * int(avg_rating)
            print(f"   Avg Rating: {avg_rating:.2f} {stars}")

        # Traveler profile
        traveler_profile = consensus.get("traveler_profile", {})
        if traveler_profile:
            print("\n   Traveler Profile:")
            for profile_type, score in traveler_profile.items():
                print(f"      {profile_type.replace('_', ' ').title()}: {score:.2f}")

        # Best for
        best_for = consensus.get("best_for", [])
        if best_for:
            print(f"\n   Best For: {', '.join(best_for)}")

        # Themes
        themes = consensus.get("themes", [])
        if themes:
            print(f"\n   Themes: {', '.join(themes)}")
    else:
        print("\n⭐ CONSENSUS DATA: Not calculated")

    # Experiences
    db = SessionLocal()
    try:
        experiences = (
            db.query(EntityExperience)
            .filter(EntityExperience.canonical_entity_id == entity.id)
            .all()
        )

        print(f"\n💬 EXPERIENCES ({len(experiences)} mentions):")
        for i, exp in enumerate(experiences[:10], 1):  # Show first 10
            print(f"\n   {i}. {exp.entity_name or 'N/A'}")
            print(f"      Video: {exp.video_id or 'N/A'}")
            if exp.rating:
                print(f"      Rating: {exp.rating}/5")
            if exp.experience:
                description = exp.experience
                if len(description) > 100:
                    description = description[:97] + "..."
                print(f"      Experience: {description}")
            if exp.sentiment:
                print(f"      Sentiment: {exp.sentiment.value}")

        if len(experiences) > 10:
            print(f"\n   ... and {len(experiences) - 10} more experiences")
    finally:
        db.close()

    print("\n" + "=" * 80)


# ============================================================================
# SEARCH ENTITIES
# ============================================================================


def search_entities_in_db(
    query: str,
    city: Optional[str] = None,
    entity_type: Optional[str] = None,
    threshold: int = 60,
) -> List[Dict[str, Any]]:
    """
    Search entities from PostgreSQL with fuzzy matching.

    Args:
        query: Search query
        city: Filter by city (optional)
        entity_type: Filter by entity type (optional)
        threshold: Fuzzy match threshold (0-100, default: 60)

    Returns:
        List of matching entities with scores
    """
    db = SessionLocal()
    try:
        # Get all canonical entities from PostgreSQL
        entities_query = db.query(CanonicalEntity).all()

        results = []
        query_lower = query.lower()

        for entity in entities_query:
            # Filter by city
            if city:
                entity_location = entity.location or ""
                if city.lower() not in entity_location.lower():
                    continue

            # Filter by type
            if entity_type:
                entity_type_str = entity.entity_type.value if entity.entity_type else ""
                if entity_type_str.lower() != entity_type.lower():
                    continue

            # Fuzzy match on canonical name
            canonical_name = entity.canonical_name or ""
            name_score = fuzz.partial_ratio(query_lower, canonical_name.lower())

            # Check aliases
            alias_scores = []
            for alias in entity.aliases or []:
                alias_score = fuzz.partial_ratio(query_lower, alias.lower())
                alias_scores.append(alias_score)

            max_alias_score = max(alias_scores) if alias_scores else 0

            # Use best score
            best_score = max(name_score, max_alias_score)

            if best_score >= threshold:
                results.append(
                    {
                        "entity": entity,
                        "score": best_score,
                        "matched_field": "name"
                        if name_score >= max_alias_score
                        else "alias",
                    }
                )

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        return results
    finally:
        db.close()


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
        entity = result["entity"]
        score = result["score"]
        entity_id = entity.entity_id or "N/A"
        name = entity.canonical_name or "N/A"
        entity_type = entity.entity_type.value if entity.entity_type else "N/A"
        loc_str = entity.location or "N/A"

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

    print()


# ============================================================================
# CLI COMMANDS
# ============================================================================


@click.group()
def cli():
    """Entity query tool for canonical entities."""
    pass


@cli.command()
@click.argument("entity_id")
@click.option("--log-level", default="INFO", help="Logging level")
def show(entity_id: str, log_level: str):
    """
    Show detailed information about a specific entity.

    ENTITY_ID: The ID of the canonical entity to display

    Examples:

        # Show entity details
        python cli/query_entities_stage3.py show ATT_001

        # Using helper script
        ./crawl.sh query show ATT_001
    """
    setup_logging(log_level=log_level)

    try:
        logger.info(f"📦 Loading entity {entity_id} from PostgreSQL...")

        db = SessionLocal()
        entity = (
            db.query(CanonicalEntity)
            .filter(CanonicalEntity.entity_id == entity_id)
            .first()
        )

        if not entity:
            print(f"\n❌ Entity not found: {entity_id}")
            print("\nPossible reasons:")
            print("  1. Entity ID is incorrect")
            print("  2. Entity hasn't been created yet (run Stage 3)")
            print(
                "\nUse 'python cli/query_entities_stage3.py search --query <name>' to find entities"
            )
            db.close()
            sys.exit(1)

        logger.info("✅ Entity found")
        print_entity_details(entity)

        db.close()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Failed to load entity: {e}")
        logger.exception(e)
        sys.exit(1)


@cli.command()
@click.option("--query", "-q", required=True, help="Search query")
@click.option("--city", "-c", help="Filter by city")
@click.option(
    "--type",
    "-t",
    "entity_type",
    help="Filter by entity type (restaurant, hotel, attraction, etc.)",
)
@click.option(
    "--threshold", default=60, help="Fuzzy match threshold (0-100, default: 60)"
)
@click.option("--limit", "-l", default=20, help="Max results to display (default: 20)")
@click.option("--log-level", default="INFO", help="Logging level")
def search(
    query: str,
    city: Optional[str],
    entity_type: Optional[str],
    threshold: int,
    limit: int,
    log_level: str,
):
    """
    Search entities by name, city, or type with fuzzy matching.

    Examples:

        # Search by name
        python cli/query_entities_stage3.py search --query "Khao San"

        # Search with city filter
        python cli/query_entities_stage3.py search --query "temple" --city "Bangkok"

        # Search with type filter
        python cli/query_entities_stage3.py search --query "beach" --type attraction

        # Adjust fuzzy matching threshold
        python cli/query_entities_stage3.py search --query "restaurant" --threshold 80

        # Show more results
        python cli/query_entities_stage3.py search --query "hotel" --limit 50
    """
    setup_logging(log_level=log_level)

    try:
        logger.info(f"🔍 Searching for '{query}' in PostgreSQL...")

        if city:
            logger.info(f"   Filter: city = {city}")
        if entity_type:
            logger.info(f"   Filter: type = {entity_type}")

        results = search_entities_in_db(
            query=query, city=city, entity_type=entity_type, threshold=threshold
        )

        logger.info("✅ Search complete")

        print_search_results(results, limit=limit)

        # Show hint to view details
        if results:
            print(
                "💡 Tip: Use 'python cli/query_entities_stage3.py show <entity_id>' to view detailed information\n"
            )

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == "__main__":
    cli()
