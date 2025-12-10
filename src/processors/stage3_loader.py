"""
Stage 3 Loader: Load and prepare Stage 2 entities for normalization.

Loads all Stage 2 extracted files from S3, extracts entities with full
provenance tracking, and prepares them for deduplication and normalization.

Usage:
    from src.processors.stage3_loader import load_all_stage2_entities

    entities = load_all_stage2_entities(
        s3_storage=s3,
        prefix='stage2-extracted/new/'
    )

    print(f"Loaded {entities['total_entities']} entities from {entities['total_videos']} videos")
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import re
from collections import defaultdict, Counter
from datetime import datetime

from src.storage.s3 import S3Storage
from src.utils.schemas import EntityExperience, TravelerProfile
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Text Normalization
# =============================================================================


def normalize_entity_text(text: str, preserve_original: bool = True) -> Dict[str, str]:
    """
    Normalize entity text for matching and deduplication.

    Normalization steps:
    1. Lowercase
    2. Strip extra whitespace
    3. Remove special characters (keep hyphens, apostrophes)
    4. Handle unicode properly
    5. Preserve original in metadata

    Args:
        text: Text to normalize
        preserve_original: If True, return both normalized and original

    Returns:
        Dict with 'normalized' and optionally 'original' keys

    Examples:
        >>> normalize_entity_text("Khao San Road ")
        {'normalized': 'khao san road', 'original': 'Khao San Road '}

        >>> normalize_entity_text("Café de L'Opéra")
        {'normalized': 'cafe de lopera', 'original': "Café de L'Opéra"}
    """
    if not text:
        return {'normalized': '', 'original': ''}

    original = text

    # Step 1: Strip leading/trailing whitespace
    normalized = text.strip()

    # Step 2: Lowercase
    normalized = normalized.lower()

    # Step 3: Normalize unicode (é → e, ñ → n, etc.)
    # Remove accents/diacritics
    import unicodedata
    normalized = unicodedata.normalize('NFKD', normalized)
    normalized = ''.join([c for c in normalized if not unicodedata.combining(c)])

    # Step 4: Remove special characters but keep hyphens, apostrophes, and spaces
    # Keep: letters, numbers, spaces, hyphens, apostrophes
    normalized = re.sub(r"[^a-z0-9\s\-']", '', normalized)

    # Step 5: Collapse multiple spaces into single space
    normalized = re.sub(r'\s+', ' ', normalized)

    # Step 6: Strip again after processing
    normalized = normalized.strip()

    result = {'normalized': normalized}
    if preserve_original:
        result['original'] = original.strip()

    return result


def normalize_location(location: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Normalize location string for matching.

    Args:
        location: Location string (e.g., "Bangkok, Thailand")

    Returns:
        Dict with 'normalized' and 'original' keys

    Examples:
        >>> normalize_location("Bangkok, Thailand")
        {'normalized': 'bangkok thailand', 'original': 'Bangkok, Thailand'}

        >>> normalize_location(None)
        {'normalized': None, 'original': None}
    """
    if not location:
        return {'normalized': None, 'original': None}

    # Remove commas and extra punctuation
    cleaned = re.sub(r'[,\.\-]', ' ', location)

    # Normalize text
    result = normalize_entity_text(cleaned)

    return result


# =============================================================================
# Entity Loading with Provenance
# =============================================================================


def load_stage2_file(
    s3_storage: S3Storage,
    s3_key: str,
    bucket_name: str
) -> Optional[Dict[str, Any]]:
    """
    Load a single Stage 2 file from S3.

    Args:
        s3_storage: S3Storage instance
        s3_key: S3 key for the file
        bucket_name: S3 bucket name

    Returns:
        Stage 2 data as dict, or None if load failed
    """
    try:
        response = s3_storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        data = json.loads(content.strip())
        return data

    except Exception as e:
        logger.error(f"Failed to load {s3_key}: {e}")
        return None


def extract_entities_with_provenance(
    stage2_data: Dict[str, Any],
    source_file_path: str
) -> List[Dict[str, Any]]:
    """
    Extract entities from Stage 2 data with full provenance tracking.

    Each entity is enriched with:
    - source_video_id
    - source_file_path
    - traveler_profile (complete)
    - normalized name and location
    - original entity data

    Args:
        stage2_data: Stage 2 output dict
        source_file_path: S3 path to source file

    Returns:
        List of entities with provenance metadata
    """
    entities_with_provenance = []

    source_id = stage2_data.get('source_id')
    content_id = stage2_data.get('content_id', f'youtube_{source_id}')
    traveler_profile = stage2_data.get('traveler_profile', {})
    language = stage2_data.get('language', 'unknown')
    processed_at = stage2_data.get('processed_at')

    entities = stage2_data.get('entities', [])

    for entity_data in entities:
        try:
            # Parse entity with Pydantic for validation
            entity = EntityExperience(**entity_data)

            # Normalize name and location
            normalized_name = normalize_entity_text(entity.entity_name)
            normalized_location = normalize_location(entity.location)

            # Create enriched entity with provenance
            enriched_entity = {
                # Original entity data
                'entity': entity.model_dump(),

                # Normalized for matching
                'normalized_name': normalized_name['normalized'],
                'original_name': normalized_name['original'],
                'normalized_location': normalized_location['normalized'],
                'original_location': normalized_location['original'],

                # Provenance
                'provenance': {
                    'source_video_id': source_id,
                    'content_id': content_id,
                    'source_file_path': source_file_path,
                    'language': language,
                    'processed_at': processed_at,
                    'traveler_profile': traveler_profile
                }
            }

            entities_with_provenance.append(enriched_entity)

        except Exception as e:
            logger.warning(
                f"Failed to parse entity from {source_id}: {e}. "
                f"Entity data: {entity_data}"
            )
            continue

    return entities_with_provenance


def load_all_stage2_entities(
    s3_storage: S3Storage,
    prefix: str = 'stage2-extracted/new/',
    bucket_name: Optional[str] = None,
    limit: Optional[int] = None,
    show_progress: bool = True
) -> Dict[str, Any]:
    """
    Load ALL Stage 2 entities from S3 with full provenance.

    This function:
    1. Lists all Stage 2 files in S3
    2. Loads each file and extracts entities
    3. Enriches entities with provenance metadata
    4. Groups entities by type
    5. Calculates statistics

    Args:
        s3_storage: S3Storage instance
        prefix: S3 prefix for Stage 2 files (default: 'stage2-extracted/new/')
        bucket_name: S3 bucket name (uses s3_storage.bucket_name if None)
        limit: Limit number of files to process (for testing)
        show_progress: Show progress bar if True

    Returns:
        Dict containing:
            - all_entities: List of all entities with provenance
            - by_type: Dict grouping entities by entity_type
            - by_location: Dict grouping entities by normalized location
            - by_video: Dict grouping entities by source video
            - statistics: Dict with stats (total_entities, total_videos, etc.)

    Example:
        >>> result = load_all_stage2_entities(s3_storage)
        >>> print(f"Loaded {result['statistics']['total_entities']} entities")
        >>> print(f"Entity types: {list(result['by_type'].keys())}")
    """
    if bucket_name is None:
        bucket_name = s3_storage.bucket_name

    logger.info(f"Loading Stage 2 entities from s3://{bucket_name}/{prefix}")

    # Step 1: List all Stage 2 files
    logger.info("Listing Stage 2 files...")
    response = s3_storage.s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if 'Contents' not in response:
        logger.warning(f"No Stage 2 files found at s3://{bucket_name}/{prefix}")
        return {
            'all_entities': [],
            'by_type': {},
            'by_location': {},
            'by_video': {},
            'statistics': {
                'total_entities': 0,
                'total_videos': 0,
                'entities_per_type': {},
                'entities_per_location': {},
                'load_errors': 0
            }
        }

    # Filter out directory markers
    files = [obj['Key'] for obj in response['Contents'] if obj['Key'] != prefix]

    if limit:
        files = files[:limit]
        logger.info(f"Limited to {limit} files for testing")

    logger.info(f"Found {len(files)} Stage 2 files to process")

    # Step 2: Load entities from each file
    all_entities = []
    by_type = defaultdict(list)
    by_location = defaultdict(list)
    by_video = {}
    load_errors = 0

    # Progress tracking
    if show_progress:
        try:
            from tqdm import tqdm
            file_iterator = tqdm(files, desc="Loading Stage 2 files", unit="file")
        except ImportError:
            file_iterator = files
            logger.info("Install tqdm for progress bars: pip install tqdm")
    else:
        file_iterator = files

    for s3_key in file_iterator:
        # Load Stage 2 file
        stage2_data = load_stage2_file(s3_storage, s3_key, bucket_name)

        if stage2_data is None:
            load_errors += 1
            continue

        # Extract entities with provenance
        source_file_path = f"s3://{bucket_name}/{s3_key}"
        entities_with_provenance = extract_entities_with_provenance(
            stage2_data,
            source_file_path
        )

        # Add to collections
        all_entities.extend(entities_with_provenance)

        # Group by type
        for entity_data in entities_with_provenance:
            entity_type = entity_data['entity']['entity_type']
            by_type[entity_type].append(entity_data)

        # Group by location
        for entity_data in entities_with_provenance:
            norm_location = entity_data['normalized_location']
            if norm_location:
                by_location[norm_location].append(entity_data)

        # Group by video
        source_id = stage2_data.get('source_id')
        content_id = stage2_data.get('content_id', f'youtube_{source_id}')
        if content_id:
            by_video[content_id] = {
                'entities': entities_with_provenance,
                'traveler_profile': stage2_data.get('traveler_profile', {}),
                'language': stage2_data.get('language', 'unknown'),
                'source_file_path': source_file_path,
                'source_id': source_id  # Keep source_id for reference
            }

    # Step 3: Calculate statistics
    logger.info("Calculating statistics...")

    # Entity counts per type
    entities_per_type = {
        entity_type: len(entities)
        for entity_type, entities in by_type.items()
    }

    # Entity counts per location (top 50)
    location_counts = Counter()
    for entity_data in all_entities:
        orig_location = entity_data['original_location']
        if orig_location:
            location_counts[orig_location] += 1

    entities_per_location = dict(location_counts.most_common(50))

    # Traveler profile distribution
    traveler_types = Counter()
    budget_tiers = Counter()
    travel_styles = Counter()

    for video_id, video_data in by_video.items():
        profile = video_data['traveler_profile']
        traveler_types[profile.get('traveler_type', 'unknown')] += 1
        budget_tiers[profile.get('budget_tier', 'unknown')] += 1

        # Count each style separately
        for style in profile.get('travel_style', []):
            travel_styles[style] += 1

    statistics = {
        'total_entities': len(all_entities),
        'total_videos': len(by_video),
        'total_files_processed': len(files),
        'load_errors': load_errors,
        'entities_per_type': entities_per_type,
        'entities_per_location': entities_per_location,
        'traveler_type_distribution': dict(traveler_types),
        'budget_tier_distribution': dict(budget_tiers),
        'travel_style_distribution': dict(travel_styles.most_common(20)),
        'avg_entities_per_video': len(all_entities) / len(by_video) if by_video else 0
    }

    logger.info(f"✅ Loaded {statistics['total_entities']} entities from {statistics['total_videos']} videos")
    logger.info(f"   Entity types: {list(entities_per_type.keys())}")
    logger.info(f"   Load errors: {load_errors}")

    return {
        'all_entities': all_entities,
        'by_type': dict(by_type),
        'by_location': dict(by_location),
        'by_video': by_video,
        'statistics': statistics
    }


def print_load_summary(result: Dict[str, Any]) -> None:
    """
    Print a formatted summary of loaded entities.

    Args:
        result: Result dict from load_all_stage2_entities()
    """
    stats = result['statistics']

    print('=' * 80)
    print('STAGE 2 ENTITIES LOAD SUMMARY')
    print('=' * 80)
    print()

    print('OVERALL STATISTICS:')
    print('-' * 80)
    print(f"Total entities loaded:     {stats['total_entities']:,}")
    print(f"Total videos processed:    {stats['total_videos']}")
    print(f"Total files processed:     {stats['total_files_processed']}")
    print(f"Load errors:               {stats['load_errors']}")
    print(f"Avg entities per video:    {stats['avg_entities_per_video']:.1f}")
    print()

    print('ENTITIES BY TYPE:')
    print('-' * 80)
    for entity_type, count in sorted(
        stats['entities_per_type'].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        percentage = (count / stats['total_entities']) * 100
        print(f"  {entity_type:20s}: {count:5,} ({percentage:5.1f}%)")
    print()

    print('TOP 10 LOCATIONS:')
    print('-' * 80)
    top_locations = sorted(
        stats['entities_per_location'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    for location, count in top_locations:
        print(f"  {location:30s}: {count:4,} entities")
    print()

    print('TRAVELER PROFILES:')
    print('-' * 80)
    print("Traveler Types:")
    for traveler_type, count in sorted(
        stats['traveler_type_distribution'].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        print(f"  {traveler_type:15s}: {count:3} videos")

    print()
    print("Budget Tiers:")
    for budget_tier, count in sorted(
        stats['budget_tier_distribution'].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        print(f"  {budget_tier:15s}: {count:3} videos")

    print()
    print("Travel Styles (top 10):")
    top_styles = sorted(
        stats['travel_style_distribution'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    for style, count in top_styles:
        print(f"  {style:15s}: {count:3} videos")

    print()
    print('=' * 80)
