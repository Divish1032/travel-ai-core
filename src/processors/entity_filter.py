"""
Entity Filtering for Stage 3 Processing

Filters out non-place entities from canonical entity list.
Non-place entities include:
- Apps and websites (booking platforms, ride-hailing)
- Generic transportation modes (without specifics)
- Packing items (travel adapters, chargers)
- Generic categories (street markets without location)
- Services (visa services, tour operators)
- Abstract concepts (visa requirements, guidelines)

These filtered entities are candidates for the Insights Pipeline.

Usage:
    from src.processors.entity_filter import filter_non_place_entities

    place_entities, filtered_entities, stats = filter_non_place_entities(
        canonical_entities
    )
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add project root to path if running as main
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Non-Place Entity Patterns
# =============================================================================

NON_PLACE_PATTERNS = {
    'apps_websites': [
        r'\b(app|application|website|platform|portal|site)\b',
        r'\b(12go|booking|agoda|grab|bolt|uber|gojek|klook)\b',
        r'\.(com|net|org|io|asia|travel)\b',
        r'\bonline\s+(booking|reservation|platform)\b',
    ],
    'generic_transport': [
        r'^(domestic flights?|international flights?)$',
        r'^(flights?|bus|train|ferry|taxi|tuk.?tuk)$',  # Without specifics
        r'^(public transport|transportation|local transport)$',
        r'^(metro|subway|skytrain|mrt|bts)$',  # Without city context
    ],
    'packing_items': [
        r'\b(travel adapter|power adapter|converter|charger)\b',
        r'\b(luggage|backpack|suitcase|bag)\b',
        r'\b(sunscreen|mosquito repellent|insect repellent)\b',
        r'\b(medication|first aid|toiletries)\b',
        r'\b(sim card|phone|electronics|gadget)\b',
    ],
    'generic_categories': [
        r'^(street markets?|local markets?|night markets?)$',  # Without specific name
        r'^(food stalls?|street food|local food)$',
        r'^(restaurants?|hotels?|resorts?|guesthouses?)$',  # Generic without name
        r'^(beaches?|temples?|attractions?)$',  # Generic without name
        r'^(shopping|dining|nightlife)$',
    ],
    'services': [
        r'\b(visa service|tour operator|travel agency)\b',
        r'\b(insurance|travel insurance)\b',
        r'\b(booking service|reservation system)\b',
        r'\b(currency exchange|money changer)\b',
        r'\b(tour guide|guided tour)\b',
    ],
    'abstract_concepts': [
        r'\b(visa requirements?|visa guidelines?|visa policy)\b',
        r'\b(entry requirements?|immigration)\b',
        r'\b(guidelines?|policy|policies|regulation)\b',
        r'\b(cost|price|budget|expense|pricing)$',
        r'\b(tips?|advice|information|knowledge|guide)$',
        r'^(how to|what to|when to|where to)',
        r'\b(requirements?|checklist)\b',
    ],
    'transportation_info': [
        r'\b(transportation cost|flight cost|ticket price)\b',
        r'\b(travel time|journey time|duration)\b',
        r'\b(route|itinerary)$',
    ]
}

# Entity types that should ALWAYS have specific locations
LOCATION_REQUIRED_TYPES = {
    'restaurant', 'hotel', 'attraction', 'destination',
    'shopping', 'activity'
}

# Suspicious city names (often from failed geocoding)
SUSPICIOUS_CITIES = {
    'ต.ทับช้าง',  # Random Thai district
    'unknown',
    'various',
    'multiple',
    '',
}


# =============================================================================
# Entity Classification Functions
# =============================================================================

def is_non_place_entity(entity: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Check if entity is NOT a physical place.

    Args:
        entity: Entity dictionary with canonical_name, location, etc.

    Returns:
        Tuple of (is_non_place: bool, reason: str)

    Examples:
        >>> is_non_place_entity({'canonical_name': 'Bolt app'})
        (True, 'matched_pattern:apps_websites')

        >>> is_non_place_entity({'canonical_name': 'Grand Palace'})
        (False, 'valid_place')
    """
    # Handle None values by using 'or' operator
    name = (entity.get('canonical_name') or '').lower()
    entity_type = entity.get('entity_type') or ''
    location = (entity.get('location') or '').lower()
    city = (entity.get('city') or '').lower()

    # Check 1: Match against non-place patterns
    for category, patterns in NON_PLACE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return True, f"matched_pattern:{category}"

    # Check 2: Generic single-word names for certain types
    if entity_type in LOCATION_REQUIRED_TYPES:
        # Single word without context is suspicious
        if len(name.split()) == 1 and len(name) < 15:
            return True, "generic_single_word"

    # Check 3: Suspicious city names (failed geocoding)
    if city.lower() in SUSPICIOUS_CITIES or city.startswith('ต.'):
        # If location is only country-level, likely not a specific place
        coords = entity.get('coordinates', {})
        confidence = coords.get('confidence', 0)

        if confidence < 0.90:
            return True, "poor_geocoding_suspicious_city"

    # Check 4: Generic descriptors
    generic_indicators = [
        'general', 'typical', 'average', 'various', 'common',
        'standard', 'normal', 'regular', 'basic'
    ]
    if any(word in name for word in generic_indicators):
        return True, "generic_descriptor"

    # Check 5: Informational/advisory names
    info_indicators = ['tips for', 'advice on', 'guide to', 'how to', 'information about']
    if any(phrase in name for phrase in info_indicators):
        return True, "informational_content"

    return False, "valid_place"


def validate_entity_quality(entity: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate entity is a high-quality place entity.

    Args:
        entity: Entity dictionary

    Returns:
        Tuple of (is_valid: bool, warnings: List[str])

    Quality Checks:
        1. Valid coordinates with good confidence (>0.85)
        2. Specific city/location (not generic)
        3. Not a generic category name
        4. Has experiences
        5. Reasonable formatted address
    """
    warnings = []

    # Check 1: Valid coordinates with good confidence
    coords = entity.get('coordinates', {})
    confidence = coords.get('confidence', 0)
    if confidence < 0.85:
        warnings.append(f"low_geocoding_confidence:{confidence:.2f}")

    # Check 2: Specific city/location
    city = (entity.get('city') or '').lower()
    if not city or city in SUSPICIOUS_CITIES or len(city) < 3:
        warnings.append(f"missing_or_invalid_city:{city}")

    # Check 3: Not a generic category
    name = (entity.get('canonical_name') or '').lower()
    generic_words = ['general', 'various', 'typical', 'common', 'average']
    if any(word in name for word in generic_words):
        warnings.append("generic_name_pattern")

    # Check 4: Has experiences
    exp_count = entity.get('experience_count', 0)
    if exp_count == 0:
        warnings.append("no_experiences")

    # Check 5: Formatted address is reasonable
    formatted_addr = (coords.get('formatted_address') or '')
    if not formatted_addr or len(formatted_addr) < 15:
        warnings.append("poor_formatted_address")

    # Check 6: Country is present
    country = entity.get('country') or ''
    if not country or country.lower() == 'unknown':
        warnings.append("missing_country")

    # Entity is invalid if it has critical warnings
    critical_keywords = ['missing', 'invalid', 'no_experiences', 'generic']
    critical_warnings = [
        w for w in warnings
        if any(keyword in w.lower() for keyword in critical_keywords)
    ]

    is_valid = len(critical_warnings) == 0

    return is_valid, warnings


# =============================================================================
# Main Filtering Function
# =============================================================================

def filter_non_place_entities(
    entities: List[Dict[str, Any]],
    enable_quality_validation: bool = True
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Filter out non-place entities from canonical entities list.

    This function:
    1. Identifies non-place entities (apps, services, generic categories)
    2. Optionally validates quality of remaining place entities
    3. Returns separated lists and statistics

    Args:
        entities: List of canonical entity dictionaries
        enable_quality_validation: If True, also validate place entity quality

    Returns:
        Tuple of:
        - place_entities: Valid place entities
        - filtered_entities: Non-place entities (for insights pipeline)
        - stats: Filtering statistics dictionary

    Example:
        >>> entities = [
        ...     {'canonical_name': 'Grand Palace', 'entity_type': 'attraction'},
        ...     {'canonical_name': 'Bolt app', 'entity_type': 'transportation'},
        ... ]
        >>> places, filtered, stats = filter_non_place_entities(entities)
        >>> len(places)
        1
        >>> stats['filtered_out']
        1
    """
    place_entities = []
    filtered_entities = []

    stats = {
        'total_input': len(entities),
        'places_kept': 0,
        'filtered_out': 0,
        'quality_warnings': 0,
        'filter_reasons': {},
        'quality_issues': {}
    }

    logger.info(f"Filtering {len(entities)} entities to remove non-place entities...")

    for entity in entities:
        entity_name = entity.get('canonical_name', 'Unknown')

        # Step 1: Check if it's a non-place entity
        is_non_place, reason = is_non_place_entity(entity)

        if is_non_place:
            # Filter out - this is not a place
            filtered_entities.append({
                **entity,
                'filter_reason': reason,
                'insights_candidate': True
            })
            stats['filtered_out'] += 1
            stats['filter_reasons'][reason] = stats['filter_reasons'].get(reason, 0) + 1

            logger.debug(f"   Filtered: {entity_name} (reason: {reason})")
        else:
            # Step 2: Validate quality of place entities
            if enable_quality_validation:
                is_valid, warnings = validate_entity_quality(entity)

                if not is_valid:
                    # Quality too low - filter out
                    filtered_entities.append({
                        **entity,
                        'filter_reason': 'quality_validation_failed',
                        'quality_warnings': warnings,
                        'insights_candidate': False
                    })
                    stats['filtered_out'] += 1
                    stats['filter_reasons']['quality_validation_failed'] = \
                        stats['filter_reasons'].get('quality_validation_failed', 0) + 1

                    for warning in warnings:
                        stats['quality_issues'][warning] = \
                            stats['quality_issues'].get(warning, 0) + 1

                    logger.debug(f"   Quality filtered: {entity_name} (warnings: {warnings})")
                elif warnings:
                    # Has warnings but still valid
                    place_entities.append({
                        **entity,
                        'quality_warnings': warnings
                    })
                    stats['places_kept'] += 1
                    stats['quality_warnings'] += 1
                else:
                    # Perfect - no warnings
                    place_entities.append(entity)
                    stats['places_kept'] += 1
            else:
                # Quality validation disabled
                place_entities.append(entity)
                stats['places_kept'] += 1

    # Calculate percentages
    if stats['total_input'] > 0:
        stats['filter_rate'] = (stats['filtered_out'] / stats['total_input']) * 100
        stats['keep_rate'] = (stats['places_kept'] / stats['total_input']) * 100

    logger.info("✅ Filtering complete:")
    logger.info(f"   Kept: {stats['places_kept']} place entities ({stats.get('keep_rate', 0):.1f}%)")
    logger.info(f"   Filtered: {stats['filtered_out']} non-place entities ({stats.get('filter_rate', 0):.1f}%)")
    if stats['quality_warnings'] > 0:
        logger.info(f"   Quality warnings: {stats['quality_warnings']} entities")

    # Log top filter reasons
    if stats['filter_reasons']:
        logger.info("   Top filter reasons:")
        for reason, count in sorted(stats['filter_reasons'].items(),
                                    key=lambda x: x[1], reverse=True)[:5]:
            logger.info(f"      - {reason}: {count}")

    return place_entities, filtered_entities, stats


# =============================================================================
# Helper Functions
# =============================================================================

def get_insights_candidates(filtered_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract entities that are candidates for insights pipeline.

    Excludes entities that failed quality validation (not useful for insights either).

    Args:
        filtered_entities: List of filtered entity dictionaries

    Returns:
        List of entities suitable for insights pipeline
    """
    return [
        entity for entity in filtered_entities
        if entity.get('insights_candidate', False)
    ]


def log_filter_statistics(stats: Dict[str, Any]) -> None:
    """
    Log detailed filtering statistics.

    Args:
        stats: Statistics dictionary from filter_non_place_entities()
    """
    logger.info("\n" + "=" * 60)
    logger.info("ENTITY FILTERING STATISTICS")
    logger.info("=" * 60)
    logger.info(f"Total input entities: {stats['total_input']}")
    logger.info(f"Place entities kept: {stats['places_kept']} ({stats.get('keep_rate', 0):.1f}%)")
    logger.info(f"Non-place entities filtered: {stats['filtered_out']} ({stats.get('filter_rate', 0):.1f}%)")

    if stats.get('quality_warnings', 0) > 0:
        logger.info(f"\nQuality Warnings: {stats['quality_warnings']} entities")
        if stats.get('quality_issues'):
            logger.info("Quality Issues Breakdown:")
            for issue, count in sorted(stats['quality_issues'].items(),
                                       key=lambda x: x[1], reverse=True):
                logger.info(f"  • {issue}: {count}")

    if stats.get('filter_reasons'):
        logger.info("\nFilter Reasons Breakdown:")
        for reason, count in sorted(stats['filter_reasons'].items(),
                                    key=lambda x: x[1], reverse=True):
            logger.info(f"  • {reason}: {count}")

    logger.info("=" * 60 + "\n")


# =============================================================================
# Testing
# =============================================================================

def test_entity_filter():
    """Test entity filtering with sample entities."""

    test_entities = [
        # Valid place
        {
            'canonical_name': 'Grand Palace',
            'entity_type': 'attraction',
            'city': 'Bangkok',
            'country': 'Thailand',
            'coordinates': {'confidence': 0.95, 'formatted_address': 'Grand Palace, Bangkok, Thailand'},
            'experience_count': 5
        },
        # App (should be filtered)
        {
            'canonical_name': 'Bolt app',
            'entity_type': 'transportation',
            'city': 'ต.ทับช้าง',
            'coordinates': {'confidence': 0.85},
            'experience_count': 1
        },
        # Generic transport (should be filtered)
        {
            'canonical_name': 'Domestic flights',
            'entity_type': 'transportation',
            'city': 'ต.ทับช้าง',
            'coordinates': {'confidence': 0.80},
            'experience_count': 1
        },
        # Packing item (should be filtered)
        {
            'canonical_name': 'Travel adapter',
            'entity_type': 'shopping',
            'city': 'unknown',
            'coordinates': {'confidence': 0.70},
            'experience_count': 1
        }
    ]

    places, filtered, stats = filter_non_place_entities(test_entities)

    assert len(places) == 1, f"Expected 1 place, got {len(places)}"
    assert len(filtered) == 3, f"Expected 3 filtered, got {len(filtered)}"
    assert stats['places_kept'] == 1
    assert stats['filtered_out'] == 3

    logger.info("✅ Entity filter tests passed!")


if __name__ == '__main__':
    import sys
    from pathlib import Path
    # Add project root to path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.utils.logging import setup_logging
    setup_logging(log_level='DEBUG')

    test_entity_filter()
