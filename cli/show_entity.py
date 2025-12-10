#!/usr/bin/env python3
"""
Show Canonical Entity Details

Displays complete information about a canonical entity including:
- Entity details (name, type, location, coordinates)
- Consensus data (ratings, themes, best_for)
- Experiences (all mentions from source videos)
- Provenance (source videos, Stage 2 entities)

Usage:
    python cli/show_entity.py <entity_id>
    ./crawl.sh show-entity <entity_id>
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.utils.logging import get_logger, setup_logging
from src.utils.metadata_tracker import MetadataTracker

logger = get_logger(__name__)


def find_entity(entities: list, entity_id: str) -> Optional[Dict[str, Any]]:
    """
    Find entity by ID in list.

    Args:
        entities: List of canonical entities
        entity_id: Entity ID to find

    Returns:
        Entity dict if found, None otherwise
    """
    for entity in entities:
        if entity.get('entity_id') == entity_id:
            return entity
    return None


def print_entity_details(entity: Dict[str, Any], tracker: MetadataTracker) -> None:
    """
    Print formatted entity details.

    Args:
        entity: Canonical entity dict
        tracker: MetadataTracker instance for provenance
    """
    entity_id = entity.get('entity_id')

    print("\n" + "=" * 80)
    print(f"CANONICAL ENTITY: {entity.get('canonical_name', 'N/A')}")
    print("=" * 80)

    # Basic info
    print(f"\n📋 BASIC INFORMATION:")
    print(f"   Entity ID: {entity_id}")
    print(f"   Canonical Name: {entity.get('canonical_name', 'N/A')}")
    print(f"   Entity Type: {entity.get('entity_type', 'N/A')}")

    # Aliases
    aliases = entity.get('aliases', [])
    if aliases:
        print(f"   Aliases: {', '.join(aliases)}")

    # Location
    print(f"\n📍 LOCATION:")
    location = entity.get('location')
    if isinstance(location, dict):
        print(f"   City: {location.get('city', 'N/A')}")
        print(f"   Area: {location.get('area', 'N/A')}")
    elif isinstance(location, str):
        print(f"   Location: {location}")
    else:
        print(f"   Location: N/A")

    # Coordinates
    coordinates = entity.get('coordinates')
    if coordinates:
        print(f"\n🌍 COORDINATES:")
        print(f"   Latitude: {coordinates.get('lat')}")
        print(f"   Longitude: {coordinates.get('lon')}")
        print(f"   Provider: {coordinates.get('provider', 'N/A')}")
        print(f"   Confidence: {coordinates.get('confidence', 'N/A')}")
        if coordinates.get('place_id'):
            print(f"   Google Place ID: {coordinates.get('place_id')}")

        # Map link
        lat = coordinates.get('lat')
        lon = coordinates.get('lon')
        if lat and lon:
            print(f"   Google Maps: https://www.google.com/maps/search/?api=1&query={lat},{lon}")
    else:
        print(f"\n🌍 COORDINATES: Not geocoded")

    # Consensus
    consensus = entity.get('consensus')
    if consensus:
        print(f"\n⭐ CONSENSUS DATA:")
        print(f"   Mention Count: {consensus.get('mention_count', 0)}")

        avg_rating = consensus.get('avg_rating')
        if avg_rating:
            stars = "⭐" * int(avg_rating)
            print(f"   Avg Rating: {avg_rating:.2f} {stars}")

        # Traveler profile
        traveler_profile = consensus.get('traveler_profile', {})
        if traveler_profile:
            print(f"\n   Traveler Profile:")
            for profile_type, score in traveler_profile.items():
                print(f"      {profile_type.replace('_', ' ').title()}: {score:.2f}")

        # Best for
        best_for = consensus.get('best_for', [])
        if best_for:
            print(f"\n   Best For: {', '.join(best_for)}")

        # Themes
        themes = consensus.get('themes', [])
        if themes:
            print(f"\n   Themes: {', '.join(themes)}")
    else:
        print(f"\n⭐ CONSENSUS DATA: Not calculated")

    # Experiences
    experiences = entity.get('experiences', [])
    print(f"\n💬 EXPERIENCES ({len(experiences)} mentions):")
    for i, exp in enumerate(experiences[:10], 1):  # Show first 10
        print(f"\n   {i}. {exp.get('name', 'N/A')}")
        print(f"      Video: {exp.get('video_id', 'N/A')}")
        if exp.get('rating'):
            print(f"      Rating: {exp.get('rating')}/5")
        description = exp.get('description', '')
        if description:
            # Truncate long descriptions
            if len(description) > 100:
                description = description[:97] + "..."
            print(f"      Description: {description}")

    if len(experiences) > 10:
        print(f"\n   ... and {len(experiences) - 10} more experiences")

    # Provenance
    try:
        print(f"\n🔍 PROVENANCE:")
        provenance = tracker.get_entity_provenance(entity_id)

        print(f"   Source Videos: {provenance['total_source_videos']}")
        print(f"   Stage 2 Entities: {provenance['total_stage2_entities']}")
        print(f"   Deduplication Method: {provenance['deduplication_method']}")
        print(f"   Avg Contribution: {provenance['average_contribution_per_video']:.2f} entities/video")

        print(f"\n   Source Videos Details:")
        for video in provenance['source_videos'][:5]:  # Show first 5
            print(f"      • {video['title']}")
            print(f"        Video ID: {video['content_id']}")
            print(f"        Contributed: {video['contribution_count']} Stage 2 entities")

        if len(provenance['source_videos']) > 5:
            print(f"      ... and {len(provenance['source_videos']) - 5} more videos")

    except ValueError as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 80)


@click.command()
@click.argument('entity_id')
@click.option('--json-output', is_flag=True, help='Output as JSON instead of formatted text')
@click.option('--log-level', default='INFO', help='Logging level (default: INFO)')
def main(entity_id: str, json_output: bool, log_level: str):
    """
    Display complete canonical entity details.

    ENTITY_ID: The canonical entity ID (e.g., ATT_001)

    Examples:
        # Display entity details
        python cli/show_entity.py ATT_001

        # Output as JSON
        python cli/show_entity.py ATT_001 --json-output
    """
    # Setup logging
    setup_logging(log_level=log_level)

    try:
        # Initialize S3
        logger.info("📦 Initializing S3...")
        s3 = S3Storage()
        storage = Stage3Storage(s3)
        tracker = MetadataTracker(s3)

        # Load canonical entities
        logger.info("📥 Loading canonical entities...")
        entities = storage.load_all_canonical_entities()

        if not entities:
            logger.error("❌ No canonical entities found")
            logger.info("Run Stage 3 processing first: ./crawl.sh process-stage3")
            sys.exit(1)

        # Find entity
        entity = find_entity(entities, entity_id)

        if not entity:
            logger.error(f"❌ Entity '{entity_id}' not found")
            logger.info(f"Available entities: {len(entities)}")
            logger.info("Use 'search-entities' to find entities")
            sys.exit(1)

        # Output
        if json_output:
            # Add provenance to entity
            try:
                provenance = tracker.get_entity_provenance(entity_id)
                entity['provenance'] = provenance
            except ValueError:
                entity['provenance'] = None

            print(json.dumps(entity, indent=2, ensure_ascii=False))
        else:
            print_entity_details(entity, tracker)

        sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Failed to show entity: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
