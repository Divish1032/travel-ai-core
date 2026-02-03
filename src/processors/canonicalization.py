"""
Stage 3 Canonicalization: Create Canonical Entities from Deduplicated Groups

Converts deduplicated entity groups into canonical entities with:
- Canonical name selection (most frequent/descriptive)
- Unique entity IDs
- Aliases extraction
- Attribute merging
- Provenance tracking

Usage:
    from src.processors.canonicalization import canonicalize_entity_group

    canonical = canonicalize_entity_group(
        group=entity_group,
        entity_id='attraction_bangkok_001'
    )

    print(canonical['canonical_name'])
    print(canonical['aliases'])
    print(canonical['total_mentions'])
"""

from typing import List, Dict, Any, Optional
from collections import Counter
import re

from src.utils.logging import get_logger
from src.storage.entity_registry import dedupe_experiences

logger = get_logger(__name__)


# =============================================================================
# Canonical Name Selection
# =============================================================================


def choose_canonical_name(entity_group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Choose the best canonical name from an entity group.

    Strategy:
    1. Pick most frequent name variant
    2. If tie: Pick longest/most descriptive
    3. If still tie: Pick first alphabetically

    Args:
        entity_group: List of entity dicts with 'original_name'

    Returns:
        Dict with:
            - canonical_name: str (selected name)
            - reasoning: str (explanation of selection)
            - frequency: int (how many times this name appeared)
            - alternatives: list (other name variants considered)

    Example:
        >>> group = [
        ...     {'original_name': 'Wat Pho'},
        ...     {'original_name': 'Wat Pho Temple'},
        ...     {'original_name': 'Wat Pho'}
        ... ]
        >>> result = choose_canonical_name(group)
        >>> result['canonical_name']
        'Wat Pho'
        >>> result['reasoning']
        'Most frequent (2 occurrences)'
    """
    if not entity_group:
        return {
            'canonical_name': 'Unknown',
            'reasoning': 'Empty entity group',
            'frequency': 0,
            'alternatives': []
        }

    # Count name frequencies
    name_counter = Counter()
    for entity in entity_group:
        name = entity.get('original_name', 'Unknown')
        name_counter[name] += 1

    # Get all unique names sorted by frequency
    names_by_freq = name_counter.most_common()

    if not names_by_freq:
        return {
            'canonical_name': 'Unknown',
            'reasoning': 'No valid names found',
            'frequency': 0,
            'alternatives': []
        }

    # Step 1: Get most frequent names
    max_freq = names_by_freq[0][1]
    top_candidates = [(name, freq) for name, freq in names_by_freq if freq == max_freq]

    if len(top_candidates) == 1:
        # Clear winner by frequency
        canonical_name = top_candidates[0][0]
        frequency = top_candidates[0][1]
        alternatives = [name for name, _ in names_by_freq[1:]]

        return {
            'canonical_name': canonical_name,
            'reasoning': f'Most frequent ({frequency} occurrence{"s" if frequency > 1 else ""})',
            'frequency': frequency,
            'alternatives': alternatives
        }

    # Step 2: Tie by frequency - pick longest/most descriptive
    top_names = [name for name, _ in top_candidates]
    longest_name = max(top_names, key=len)

    # Check if there are multiple names with same length
    max_length = len(longest_name)
    longest_candidates = [name for name in top_names if len(name) == max_length]

    if len(longest_candidates) == 1:
        # Winner by length
        canonical_name = longest_candidates[0]
        frequency = max_freq
        alternatives = [name for name in top_names if name != canonical_name]

        return {
            'canonical_name': canonical_name,
            'reasoning': f'Tied frequency ({frequency}x), chose longest/most descriptive',
            'frequency': frequency,
            'alternatives': alternatives
        }

    # Step 3: Still tied - pick first alphabetically
    canonical_name = min(longest_candidates)
    frequency = max_freq
    alternatives = [name for name in top_names if name != canonical_name]

    return {
        'canonical_name': canonical_name,
        'reasoning': f'Tied frequency ({frequency}x) and length, chose alphabetically first',
        'frequency': frequency,
        'alternatives': alternatives
    }


# =============================================================================
# Entity ID Generation
# =============================================================================


def parse_location(location: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Parse location string into city and country components.

    Args:
        location: Location string (e.g., "Bangkok, Thailand", "Thailand", "Phuket")

    Returns:
        Tuple of (city, country) where either can be None

    Examples:
        >>> parse_location("Bangkok, Thailand")
        ('Bangkok', 'Thailand')
        >>> parse_location("Thailand")
        (None, 'Thailand')
        >>> parse_location("Phuket")
        ('Phuket', None)
        >>> parse_location(None)
        (None, None)
    """
    if not location or not isinstance(location, str):
        return (None, None)

    location = location.strip()

    # Check for comma-separated format: "City, Country"
    if ',' in location:
        parts = [p.strip() for p in location.split(',')]
        if len(parts) == 2:
            city = parts[0] if parts[0] else None
            country = parts[1] if parts[1] else None
            return (city, country)
        elif len(parts) > 2:
            # Handle "City, Province, Country" -> use first and last
            city = parts[0] if parts[0] else None
            country = parts[-1] if parts[-1] else None
            return (city, country)

    # Single value - need to determine if it's city or country
    # Common country names (extend as needed)
    common_countries = {
        'thailand', 'vietnam', 'cambodia', 'laos', 'myanmar',
        'philippines', 'indonesia', 'malaysia', 'singapore',
        'india', 'china', 'japan', 'korea', 'taiwan',
        'usa', 'united states', 'uk', 'united kingdom',
        'france', 'spain', 'italy', 'germany', 'australia'
    }

    location_lower = location.lower()

    # If it matches a known country, treat as country only
    if location_lower in common_countries:
        return (None, location)

    # Otherwise, treat as city (more specific than country)
    return (location, None)


def normalize_city_name(city: Optional[str]) -> str:
    """
    Normalize city name for entity ID.

    Args:
        city: City name (e.g., "Bangkok, Thailand")

    Returns:
        Normalized city name (e.g., "bangkok")

    Examples:
        >>> normalize_city_name("Bangkok, Thailand")
        'bangkok'
        >>> normalize_city_name("Chiang Mai")
        'chiangmai'
        >>> normalize_city_name(None)
        'unknown'
    """
    if not city:
        return 'unknown'

    # Extract first part if comma-separated (e.g., "Bangkok, Thailand" -> "Bangkok")
    if ',' in city:
        city = city.split(',')[0].strip()

    # Lowercase
    normalized = city.lower()

    # Remove spaces and special characters
    normalized = re.sub(r'[^a-z0-9]', '', normalized)

    # Limit length to 15 characters
    normalized = normalized[:15]

    return normalized or 'unknown'


def generate_entity_id(
    entity_type: str,
    city: str,
    sequence: int
) -> str:
    """
    Generate unique entity ID.

    Format: {type}_{city}_{sequence:03d}

    Args:
        entity_type: Entity type (e.g., 'attraction', 'hotel', 'area')
        city: City name (will be normalized)
        sequence: Sequence number (e.g., 1, 2, 3)

    Returns:
        Entity ID string

    Examples:
        >>> generate_entity_id('attraction', 'Bangkok', 1)
        'attraction_bangkok_001'
        >>> generate_entity_id('hotel', 'Chiang Mai', 45)
        'hotel_chiangmai_045'
        >>> generate_entity_id('area', None, 7)
        'area_unknown_007'
    """
    # Normalize entity type (lowercase, no spaces)
    normalized_type = entity_type.lower().replace(' ', '_')

    # Normalize city
    normalized_city = normalize_city_name(city)

    # Format sequence with leading zeros (3 digits)
    formatted_sequence = f"{sequence:03d}"

    # Combine
    entity_id = f"{normalized_type}_{normalized_city}_{formatted_sequence}"

    return entity_id


# =============================================================================
# Alias Extraction
# =============================================================================


def extract_aliases(
    entity_group: List[Dict[str, Any]],
    canonical_name: str
) -> List[str]:
    """
    Extract all unique name variants except the canonical name.

    Args:
        entity_group: List of entity dicts
        canonical_name: The canonical name to exclude

    Returns:
        List of unique aliases sorted alphabetically

    Example:
        >>> group = [
        ...     {'original_name': 'Wat Pho'},
        ...     {'original_name': 'Wat Pho Temple'},
        ...     {'original_name': 'Wat Pho'},
        ...     {'original_name': 'Temple of Reclining Buddha'}
        ... ]
        >>> extract_aliases(group, 'Wat Pho')
        ['Temple of Reclining Buddha', 'Wat Pho Temple']
    """
    # Collect all unique names
    all_names = set()
    for entity in entity_group:
        name = entity.get('original_name', '').strip()
        if name and name != canonical_name:
            all_names.add(name)

    # Sort alphabetically
    aliases = sorted(all_names)

    return aliases


# =============================================================================
# Attribute Merging
# =============================================================================


def merge_attributes(entity_group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge attributes from all entities in group.

    Merges:
    - keywords (union, sorted by frequency)
    - travel_style (union, sorted by frequency)
    - cost_mentioned (most common value)
    - season_mentioned (union of all seasons)

    Args:
        entity_group: List of entity dicts

    Returns:
        Dict with merged attributes:
            - keywords: list (sorted by frequency)
            - travel_style: list (sorted by frequency)
            - cost_mentioned: str or None (most common)
            - season_mentioned: list (all unique seasons)

    Example:
        >>> group = [
        ...     {'entity': {'keywords': ['temple', 'buddha'], 'travel_style': ['cultural']}},
        ...     {'entity': {'keywords': ['temple', 'historic'], 'travel_style': ['cultural']}}
        ... ]
        >>> merge_attributes(group)
        {
            'keywords': ['temple', 'cultural', 'buddha', 'historic'],
            'travel_style': ['cultural'],
            'cost_mentioned': None,
            'season_mentioned': []
        }
    """
    # Counters for frequency-based merging
    keyword_counter = Counter()
    style_counter = Counter()
    cost_counter = Counter()
    seasons = set()

    for entity_data in entity_group:
        entity = entity_data.get('entity', {})

        # Keywords
        keywords = entity.get('keywords', [])
        if keywords:
            for kw in keywords:
                keyword_counter[kw] += 1

        # Travel style
        travel_styles = entity.get('travel_style', [])
        if travel_styles:
            for style in travel_styles:
                style_counter[style] += 1

        # Cost mentioned
        cost = entity.get('cost_mentioned')
        if cost:
            cost_counter[cost] += 1

        # Season mentioned
        season = entity.get('season_mentioned')
        if season:
            seasons.add(season)

    # Merge keywords (sorted by frequency)
    merged_keywords = [kw for kw, _ in keyword_counter.most_common()]

    # Merge travel styles (sorted by frequency)
    merged_styles = [style for style, _ in style_counter.most_common()]

    # Pick most common cost
    merged_cost = cost_counter.most_common(1)[0][0] if cost_counter else None

    # All unique seasons
    merged_seasons = sorted(seasons)

    return {
        'keywords': merged_keywords,
        'travel_style': merged_styles,
        'cost_mentioned': merged_cost,
        'season_mentioned': merged_seasons
    }


# =============================================================================
# Main Canonicalization Function
# =============================================================================


def canonicalize_entity_group(
    group: List[Dict[str, Any]],
    entity_id: str
) -> Dict[str, Any]:
    """
    Generate canonical entity from deduplicated entity group.

    Creates a canonical entity with:
    - Unique entity ID
    - Canonical name and aliases
    - Merged attributes
    - All experiences preserved
    - Source video IDs tracked
    - Total mentions calculated
    - Provenance metadata

    Args:
        group: List of entity dicts (from deduplication)
        entity_id: Pre-generated entity ID

    Returns:
        Canonical entity dict with structure:
        {
            'entity_id': str,
            'canonical_name': str,
            'aliases': list,
            'entity_type': str,
            'location': str,
            'normalized_location': str,
            'attributes': {
                'keywords': list,
                'travel_style': list,
                'cost_mentioned': str,
                'season_mentioned': list
            },
            'experiences': [
                {
                    'experience': str,
                    'source_video_id': str,
                    'traveler_profile': dict
                },
                ...
            ],
            'source_video_ids': list,
            'total_mentions': int,
            'provenance': {
                'canonical_name_selection': dict,
                'entities_merged': int,
                'merge_method': str,
                'original_entity_ids': list
            }
        }

    Example:
        >>> canonical = canonicalize_entity_group(group, 'attraction_bangkok_001')
        >>> canonical['canonical_name']
        'Wat Pho'
        >>> canonical['total_mentions']
        3
    """
    if not group:
        logger.warning(f"Empty entity group for {entity_id}")
        return None

    # Step 1: Choose canonical name
    name_selection = choose_canonical_name(group)
    canonical_name = name_selection['canonical_name']

    # Step 2: Extract aliases
    aliases = extract_aliases(group, canonical_name)

    # Step 3: Get entity type and location from first entity
    first_entity = group[0]
    entity_type = first_entity['entity']['entity_type']
    location = first_entity.get('original_location') or 'Unknown'
    normalized_location = first_entity.get('normalized_location') or 'unknown'

    # Parse location into city and country
    city, country = parse_location(location)

    # Step 4: Merge attributes
    merged_attrs = merge_attributes(group)

    # Step 5: Collect all experiences with provenance
    experiences = []
    source_video_ids = set()

    for entity_data in group:
        entity = entity_data['entity']
        provenance = entity_data['provenance']

        experience_text = entity.get('experience', '')
        source_video_id = provenance.get('source_video_id', 'unknown')
        content_id = provenance.get('content_id', f'youtube_{source_video_id}')
        traveler_profile = provenance.get('traveler_profile', {})

        if experience_text:
            experiences.append({
                'entity_id': entity.get('entity_id'),  # Original extracted entity ID for linking
                'experience': experience_text,
                'video_id': content_id,  # Use content_id for metadata tracker compatibility
                'source_video_id': source_video_id,  # Keep for reference
                'traveler_profile': traveler_profile,
                'language': provenance.get('language', 'unknown'),
                'processed_at': provenance.get('processed_at')
            })

            source_video_ids.add(source_video_id)

    # Step 5b: Deduplicate experiences (same video + same content = duplicate)
    experiences, duplicates_removed = dedupe_experiences(experiences)
    if duplicates_removed > 0:
        logger.debug(f"Removed {duplicates_removed} duplicate experiences for {canonical_name}")

    # Step 6: Build canonical entity
    canonical_entity = {
        'entity_id': entity_id,
        'canonical_name': canonical_name,
        'aliases': aliases,
        'entity_type': entity_type,
        'location': location,
        'normalized_location': normalized_location,
        'city': city,  # Parsed from location
        'country': country,  # Parsed from location

        # Merged attributes
        'attributes': merged_attrs,

        # All experiences preserved
        'experiences': experiences,

        # Metadata
        'source_video_ids': sorted(source_video_ids),
        'total_mentions': len(group),

        # Provenance
        'provenance': {
            'canonical_name_selection': name_selection,
            'entities_merged': len(group),
            'merge_method': 'stage3_deduplication',
            'original_entity_ids': [
                entity.get('provenance', {}).get('source_video_id', 'unknown')
                for entity in group
            ]
        }
    }

    return canonical_entity


# =============================================================================
# Batch Canonicalization
# =============================================================================


def canonicalize_all_groups(
    entity_groups: List[List[Dict[str, Any]]],
    singleton_entities: List[Dict[str, Any]],
    entity_type: str,
    starting_sequence: int = 1
) -> Dict[str, Any]:
    """
    Canonicalize all entity groups and singletons.

    Generates canonical entities for:
    1. All entity groups (deduplicated clusters)
    2. All singleton entities (no duplicates found)

    Args:
        entity_groups: List of entity groups from deduplication
        singleton_entities: List of singleton entities
        entity_type: Entity type (for ID generation)
        starting_sequence: Starting sequence number (default: 1)

    Returns:
        Dict with:
            - canonical_entities: list of canonical entities
            - statistics: dict with canonicalization stats

    Example:
        >>> result = canonicalize_all_groups(groups, singletons, 'attraction')
        >>> print(f"Generated {len(result['canonical_entities'])} canonical entities")
    """
    logger.info(f"Canonicalizing {len(entity_groups)} groups and {len(singleton_entities)} singletons...")

    canonical_entities = []
    sequence = starting_sequence

    # Canonicalize entity groups
    for group in entity_groups:
        if not group:
            continue

        # Get location from first entity for ID generation
        first_entity = group[0]
        location = first_entity.get('original_location', 'Unknown')

        # Generate entity ID
        entity_id = generate_entity_id(entity_type, location, sequence)
        sequence += 1

        # Canonicalize group
        canonical = canonicalize_entity_group(group, entity_id)

        if canonical:
            canonical_entities.append(canonical)

    # Canonicalize singleton entities (treat as 1-member groups)
    for singleton in singleton_entities:
        # Get location for ID generation
        location = singleton.get('original_location', 'Unknown')

        # Generate entity ID
        entity_id = generate_entity_id(entity_type, location, sequence)
        sequence += 1

        # Canonicalize singleton (as a 1-member group)
        canonical = canonicalize_entity_group([singleton], entity_id)

        if canonical:
            canonical_entities.append(canonical)

    # Calculate statistics
    total_mentions = sum(entity['total_mentions'] for entity in canonical_entities)
    avg_mentions = total_mentions / len(canonical_entities) if canonical_entities else 0

    # Count entities with multiple mentions (duplicates detected)
    entities_with_duplicates = sum(1 for entity in canonical_entities if entity['total_mentions'] > 1)

    # Count total aliases
    total_aliases = sum(len(entity['aliases']) for entity in canonical_entities)

    statistics = {
        'total_canonical_entities': len(canonical_entities),
        'entities_from_groups': len(entity_groups),
        'entities_from_singletons': len(singleton_entities),
        'total_mentions': total_mentions,
        'avg_mentions_per_entity': avg_mentions,
        'entities_with_duplicates': entities_with_duplicates,
        'total_aliases': total_aliases,
        'deduplication_rate': (entities_with_duplicates / len(canonical_entities) * 100) if canonical_entities else 0
    }

    logger.info("✅ Canonicalization complete:")
    logger.info(f"   Total canonical entities: {statistics['total_canonical_entities']}")
    logger.info(f"   From groups: {statistics['entities_from_groups']}")
    logger.info(f"   From singletons: {statistics['entities_from_singletons']}")
    logger.info(f"   Total mentions: {statistics['total_mentions']}")
    logger.info(f"   Entities with duplicates: {statistics['entities_with_duplicates']}")
    logger.info(f"   Total aliases: {statistics['total_aliases']}")
    logger.info(f"   Deduplication rate: {statistics['deduplication_rate']:.1f}%")

    return {
        'canonical_entities': canonical_entities,
        'statistics': statistics
    }


# =============================================================================
# Testing and Validation
# =============================================================================


def test_canonicalization_sample():
    """
    Test canonicalization with sample entity groups.

    Tests:
    1. Name selection (most frequent, longest, alphabetical)
    2. Entity ID generation
    3. Alias extraction
    4. Attribute merging
    5. Full canonicalization
    """
    logger.info("Testing canonicalization with sample entity groups...")

    # Sample entity group (duplicate "Blue Pool" entities)
    sample_group = [
        {
            'original_name': 'Blue Pool',
            'normalized_name': 'blue pool',
            'original_location': 'Krabi, Thailand',
            'normalized_location': 'krabi thailand',
            'entity': {
                'entity_name': 'Blue Pool',
                'entity_type': 'attraction',
                'location': 'Krabi, Thailand',
                'experience': 'Crystal clear blue water pool in the jungle. Beautiful natural attraction.',
                'keywords': ['nature', 'swimming', 'beautiful'],
                'travel_style': ['adventure', 'nature'],
                'cost_mentioned': 'budget-friendly',
                'season_mentioned': 'dry_season'
            },
            'provenance': {
                'source_video_id': 'video_001',
                'content_id': 'youtube_video_001',
                'language': 'en',
                'traveler_profile': {
                    'traveler_type': 'backpacker',
                    'budget_tier': 'budget'
                }
            }
        },
        {
            'original_name': 'Blue Pool Krabi',
            'normalized_name': 'blue pool krabi',
            'original_location': 'Krabi, Thailand',
            'normalized_location': 'krabi thailand',
            'entity': {
                'entity_name': 'Blue Pool Krabi',
                'entity_type': 'attraction',
                'location': 'Krabi, Thailand',
                'experience': 'Amazing natural pool with the most incredible blue color. Worth the trip!',
                'keywords': ['nature', 'swimming', 'instagram'],
                'travel_style': ['adventure'],
                'cost_mentioned': 'budget-friendly',
                'season_mentioned': None
            },
            'provenance': {
                'source_video_id': 'video_002',
                'content_id': 'youtube_video_002',
                'language': 'en',
                'traveler_profile': {
                    'traveler_type': 'solo_traveler',
                    'budget_tier': 'mid-range'
                }
            }
        },
        {
            'original_name': 'Blue Pool',
            'normalized_name': 'blue pool',
            'original_location': 'Krabi',
            'normalized_location': 'krabi',
            'entity': {
                'entity_name': 'Blue Pool',
                'entity_type': 'attraction',
                'location': 'Krabi',
                'experience': 'Hidden gem in Krabi. The water is unbelievably blue.',
                'keywords': ['hidden gem', 'nature'],
                'travel_style': ['nature'],
                'cost_mentioned': None,
                'season_mentioned': 'dry_season'
            },
            'provenance': {
                'source_video_id': 'video_003',
                'content_id': 'youtube_video_003',
                'language': 'en',
                'traveler_profile': {
                    'traveler_type': 'couple',
                    'budget_tier': 'budget'
                }
            }
        }
    ]

    # Test 1: Canonical name selection
    logger.info("\n--- Test 1: Canonical Name Selection ---")
    name_result = choose_canonical_name(sample_group)
    logger.info(f"Canonical name: {name_result['canonical_name']}")
    logger.info(f"Reasoning: {name_result['reasoning']}")
    logger.info(f"Frequency: {name_result['frequency']}")
    logger.info(f"Alternatives: {name_result['alternatives']}")

    # Test 2: Entity ID generation
    logger.info("\n--- Test 2: Entity ID Generation ---")
    entity_id = generate_entity_id('attraction', 'Krabi, Thailand', 1)
    logger.info(f"Generated ID: {entity_id}")

    # Test 3: Alias extraction
    logger.info("\n--- Test 3: Alias Extraction ---")
    aliases = extract_aliases(sample_group, name_result['canonical_name'])
    logger.info(f"Aliases: {aliases}")

    # Test 4: Attribute merging
    logger.info("\n--- Test 4: Attribute Merging ---")
    merged_attrs = merge_attributes(sample_group)
    logger.info(f"Merged keywords: {merged_attrs['keywords']}")
    logger.info(f"Merged travel styles: {merged_attrs['travel_style']}")
    logger.info(f"Merged cost: {merged_attrs['cost_mentioned']}")
    logger.info(f"Merged seasons: {merged_attrs['season_mentioned']}")

    # Test 5: Full canonicalization
    logger.info("\n--- Test 5: Full Canonicalization ---")
    canonical = canonicalize_entity_group(sample_group, entity_id)

    logger.info(f"Entity ID: {canonical['entity_id']}")
    logger.info(f"Canonical name: {canonical['canonical_name']}")
    logger.info(f"Aliases: {canonical['aliases']}")
    logger.info(f"Entity type: {canonical['entity_type']}")
    logger.info(f"Location: {canonical['location']}")
    logger.info(f"Total mentions: {canonical['total_mentions']}")
    logger.info(f"Source videos: {canonical['source_video_ids']}")
    logger.info(f"Keywords: {canonical['attributes']['keywords']}")
    logger.info(f"Experiences: {len(canonical['experiences'])} preserved")

    # Print sample experience
    if canonical['experiences']:
        logger.info("\nSample experience:")
        logger.info(f"  Text: {canonical['experiences'][0]['experience'][:80]}...")
        logger.info(f"  From: {canonical['experiences'][0]['source_video_id']}")

    logger.info("\n✅ Canonicalization test complete!")

    return canonical


if __name__ == '__main__':
    # Run tests
    test_canonicalization_sample()
