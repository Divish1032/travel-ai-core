#!/usr/bin/env python3
"""
Entity Registry - Persistent storage for canonical entity tracking.

Maintains stable entity IDs across Stage 3 runs and enables incremental processing
by tracking which entities exist and their metadata.

Features:
    - Stable entity ID generation and persistence
    - Name-based index for fast entity matching
    - Alias tracking for fuzzy matching
    - Processed video tracking to avoid reprocessing
    - S3 + local cache for performance

Usage:
    from src.storage.entity_registry import EntityRegistry

    registry = EntityRegistry(s3_storage)

    # Find existing entity
    entity_id = registry.find_matching_entity("Wat Pho", "Bangkok", "attraction")

    # Register new entity
    entity_id = registry.register_new_entity(entity_dict)

    # Check if video already processed
    if registry.is_video_processed("youtube_abc123"):
        skip...
"""

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict

from src.storage.s3 import S3Storage
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

REGISTRY_VERSION = "1.0"
REGISTRY_S3_KEY = "stage3-canonical/registry/entity_registry.json"
PROCESSED_VIDEOS_S3_KEY = "stage3-canonical/registry/processed_videos.json"
LOCAL_CACHE_DIR = Path("cache/registry")

# Fuzzy matching threshold for alias matching
ALIAS_MATCH_THRESHOLD = 0.90


# =============================================================================
# Name Normalization
# =============================================================================

def normalize_name(name: str) -> str:
    """
    Normalize entity name for matching.

    - Lowercase
    - Remove special characters
    - Collapse whitespace
    - Remove common prefixes/suffixes
    """
    if not name:
        return ""

    # Lowercase
    normalized = name.lower().strip()

    # Remove special characters except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)

    # Remove common prefixes/suffixes
    prefixes = ['the ', 'a ', 'an ']
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]

    return normalized.strip()


def create_signature(name: str, city: str, entity_type: str) -> str:
    """
    Create a unique signature for entity matching.

    Format: normalized_name||normalized_city||entity_type
    """
    norm_name = normalize_name(name)
    norm_city = normalize_name(city) if city else "unknown"
    norm_type = entity_type.lower() if entity_type else "unknown"

    return f"{norm_name}||{norm_city}||{norm_type}"


def normalize_city_for_id(city: str) -> str:
    """Normalize city name for use in entity IDs."""
    if not city:
        return "unknown"

    # Lowercase and remove special chars
    normalized = re.sub(r'[^\w]', '_', city.lower())
    # Remove multiple underscores
    normalized = re.sub(r'_+', '_', normalized)
    # Remove leading/trailing underscores
    return normalized.strip('_') or "unknown"


# =============================================================================
# Entity Registry Class
# =============================================================================

class EntityRegistry:
    """
    Persistent registry for tracking canonical entities across Stage 3 runs.

    Provides:
    - Stable entity ID generation
    - Fast entity lookup by name/city/type
    - Alias-based matching
    - Processed video tracking
    """

    def __init__(self, s3_storage: Optional[S3Storage] = None, local_only: bool = False):
        """
        Initialize the entity registry.

        Args:
            s3_storage: S3Storage instance for persistence
            local_only: If True, only use local cache (for testing)
        """
        self.s3 = s3_storage
        self.local_only = local_only

        # Registry data structures
        self.entities: Dict[str, Dict[str, Any]] = {}  # entity_id -> metadata
        self.name_index: Dict[str, str] = {}  # signature -> entity_id
        self.alias_index: Dict[str, str] = {}  # alias_signature -> entity_id
        self.next_sequence: Dict[str, int] = defaultdict(int)  # type_city -> next_seq

        # Processed videos tracking
        self.processed_videos: Dict[str, Dict[str, Any]] = {}

        # State tracking
        self._loaded = False
        self._modified = False

        # Ensure local cache directory exists
        LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Loading and Saving
    # -------------------------------------------------------------------------

    def load(self) -> bool:
        """
        Load registry from S3 (with local cache fallback).

        Returns:
            True if loaded successfully, False if no existing registry
        """
        if self._loaded:
            return True

        logger.info("Loading entity registry...")

        # Try S3 first
        if self.s3 and not self.local_only:
            try:
                registry_data = self._load_from_s3(REGISTRY_S3_KEY)
                if registry_data:
                    self._parse_registry_data(registry_data)
                    self._loaded = True
                    logger.info(f"Loaded registry from S3: {len(self.entities)} entities")

                    # Load processed videos
                    videos_data = self._load_from_s3(PROCESSED_VIDEOS_S3_KEY)
                    if videos_data:
                        self.processed_videos = videos_data.get('processed_videos', {})
                        logger.info(f"Loaded {len(self.processed_videos)} processed videos")

                    # Save to local cache
                    self._save_local_cache(registry_data)
                    return True
            except Exception as e:
                logger.warning(f"Failed to load from S3: {e}")

        # Try local cache
        local_path = LOCAL_CACHE_DIR / "entity_registry.json"
        if local_path.exists():
            try:
                with open(local_path, 'r') as f:
                    registry_data = json.load(f)
                self._parse_registry_data(registry_data)
                self._loaded = True
                logger.info(f"Loaded registry from local cache: {len(self.entities)} entities")
                return True
            except Exception as e:
                logger.warning(f"Failed to load from local cache: {e}")

        # No existing registry - start fresh
        logger.info("No existing registry found, starting fresh")
        self._loaded = True
        return False

    def save(self) -> bool:
        """
        Save registry to S3 and local cache.

        Returns:
            True if saved successfully
        """
        if not self._modified:
            logger.debug("Registry not modified, skipping save")
            return True

        logger.info(f"Saving entity registry: {len(self.entities)} entities...")

        registry_data = self._build_registry_data()

        # Save to local cache first
        self._save_local_cache(registry_data)

        # Save to S3
        if self.s3 and not self.local_only:
            try:
                self._save_to_s3(REGISTRY_S3_KEY, registry_data)

                # Save processed videos
                videos_data = {
                    'version': REGISTRY_VERSION,
                    'last_updated': datetime.now(timezone.utc).isoformat(),
                    'processed_videos': self.processed_videos
                }
                self._save_to_s3(PROCESSED_VIDEOS_S3_KEY, videos_data)

                logger.info("Registry saved to S3")
            except Exception as e:
                logger.error(f"Failed to save to S3: {e}")
                return False

        self._modified = False
        return True

    def _load_from_s3(self, key: str) -> Optional[Dict]:
        """Load JSON from S3."""
        try:
            response = self.s3.s3_client.get_object(
                Bucket=self.s3.bucket_name,
                Key=key
            )
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except self.s3.s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.debug(f"S3 load error for {key}: {e}")
            return None

    def _save_to_s3(self, key: str, data: Dict) -> None:
        """Save JSON to S3."""
        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=key,
            Body=json.dumps(data, indent=2, default=str),
            ContentType='application/json'
        )

    def _save_local_cache(self, registry_data: Dict) -> None:
        """Save to local cache file."""
        try:
            local_path = LOCAL_CACHE_DIR / "entity_registry.json"
            with open(local_path, 'w') as f:
                json.dump(registry_data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save local cache: {e}")

    def _parse_registry_data(self, data: Dict) -> None:
        """Parse loaded registry data into internal structures."""
        self.entities = data.get('entities', {})
        self.name_index = data.get('name_index', {})
        self.alias_index = data.get('alias_index', {})
        self.next_sequence = defaultdict(int, data.get('next_sequence', {}))

    def _build_registry_data(self) -> Dict:
        """Build registry data for saving."""
        return {
            'registry_version': REGISTRY_VERSION,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'entity_count': len(self.entities),
            'entities': self.entities,
            'name_index': self.name_index,
            'alias_index': self.alias_index,
            'next_sequence': dict(self.next_sequence)
        }

    # -------------------------------------------------------------------------
    # Entity Lookup
    # -------------------------------------------------------------------------

    def find_matching_entity(
        self,
        name: str,
        city: str,
        entity_type: str,
        aliases: Optional[List[str]] = None,
        allow_type_mismatch: bool = False
    ) -> Optional[str]:
        """
        Find an existing entity that matches the given name/city/type.

        Matching strategy:
        1. Exact signature match (name + city + type)
        2. Alias signature match
        3. Reverse alias match (new name matches existing alias)
        4. If allow_type_mismatch: Match by name+city only (ignoring type)

        Args:
            name: Entity name
            city: City/location
            entity_type: Entity type (attraction, restaurant, etc.)
            aliases: Optional list of aliases to also check
            allow_type_mismatch: If True, match across entity types

        Returns:
            entity_id if found, None otherwise
        """
        if not self._loaded:
            self.load()

        # 1. Exact signature match
        signature = create_signature(name, city, entity_type)
        if signature in self.name_index:
            entity_id = self.name_index[signature]
            logger.debug(f"Exact match found: {name} -> {entity_id}")
            return entity_id

        # 2. Check if name matches any existing alias
        if signature in self.alias_index:
            entity_id = self.alias_index[signature]
            logger.debug(f"Alias match found: {name} -> {entity_id}")
            return entity_id

        # 3. Check if any provided aliases match existing entities
        if aliases:
            for alias in aliases:
                alias_sig = create_signature(alias, city, entity_type)

                # Check primary name index
                if alias_sig in self.name_index:
                    entity_id = self.name_index[alias_sig]
                    logger.debug(f"Alias-to-primary match: {alias} -> {entity_id}")
                    return entity_id

                # Check alias index
                if alias_sig in self.alias_index:
                    entity_id = self.alias_index[alias_sig]
                    logger.debug(f"Alias-to-alias match: {alias} -> {entity_id}")
                    return entity_id

        # 4. Type-flexible matching (search by name+city across all types)
        if allow_type_mismatch:
            norm_name = normalize_name(name)
            norm_city = normalize_name(city) if city else "unknown"

            for entity_id, metadata in self.entities.items():
                existing_name = normalize_name(metadata.get('canonical_name', ''))
                existing_city = normalize_name(metadata.get('city', 'unknown'))

                if existing_name == norm_name and existing_city == norm_city:
                    existing_type = metadata.get('entity_type')
                    logger.warning(
                        f"Type-flexible match found: {name} ({entity_type}) "
                        f"-> {entity_id} ({existing_type})"
                    )
                    return entity_id

        return None

    def get_entity_metadata(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a registered entity."""
        return self.entities.get(entity_id)

    # -------------------------------------------------------------------------
    # Entity Registration
    # -------------------------------------------------------------------------

    def register_new_entity(self, entity: Dict[str, Any]) -> str:
        """
        Register a new canonical entity and generate stable ID.

        Args:
            entity: Canonical entity dict with at least:
                - canonical_name
                - entity_type
                - city (optional)
                - aliases (optional)
                - source_video_ids (optional)

        Returns:
            Generated entity_id
        """
        if not self._loaded:
            self.load()

        name = entity.get('canonical_name', 'unknown')
        entity_type = entity.get('entity_type', 'unknown')
        city = entity.get('city') or entity.get('location') or 'unknown'
        aliases = entity.get('aliases', [])
        source_video_ids = entity.get('source_video_ids', [])

        # Generate entity ID
        entity_id = self._generate_entity_id(entity_type, city)

        # Create signature
        signature = create_signature(name, city, entity_type)

        # Store in registry
        self.entities[entity_id] = {
            'canonical_name': name,
            'entity_type': entity_type,
            'city': city,
            'aliases': aliases,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'source_video_ids': list(source_video_ids),
            'experience_count': len(entity.get('experiences', [])),
            'name_signature': signature
        }

        # Update indexes
        self.name_index[signature] = entity_id

        # Index aliases
        for alias in aliases:
            alias_sig = create_signature(alias, city, entity_type)
            if alias_sig != signature:  # Don't duplicate primary
                self.alias_index[alias_sig] = entity_id

        self._modified = True
        logger.debug(f"Registered new entity: {name} -> {entity_id}")

        return entity_id

    def update_entity_metadata(
        self,
        entity_id: str,
        new_aliases: Optional[List[str]] = None,
        new_video_ids: Optional[List[str]] = None,
        experience_count: Optional[int] = None
    ) -> bool:
        """
        Update metadata for an existing entity.

        Args:
            entity_id: Entity ID to update
            new_aliases: New aliases to add
            new_video_ids: New source video IDs to add
            experience_count: Updated experience count

        Returns:
            True if updated successfully
        """
        if entity_id not in self.entities:
            logger.warning(f"Entity not found in registry: {entity_id}")
            return False

        entity_meta = self.entities[entity_id]
        city = entity_meta.get('city', 'unknown')
        entity_type = entity_meta.get('entity_type', 'unknown')

        # Add new aliases
        if new_aliases:
            existing_aliases = set(entity_meta.get('aliases', []))
            for alias in new_aliases:
                if alias not in existing_aliases:
                    existing_aliases.add(alias)
                    # Add to alias index
                    alias_sig = create_signature(alias, city, entity_type)
                    self.alias_index[alias_sig] = entity_id
            entity_meta['aliases'] = list(existing_aliases)

        # Add new video IDs
        if new_video_ids:
            existing_videos = set(entity_meta.get('source_video_ids', []))
            existing_videos.update(new_video_ids)
            entity_meta['source_video_ids'] = list(existing_videos)

        # Update experience count
        if experience_count is not None:
            entity_meta['experience_count'] = experience_count

        entity_meta['last_updated'] = datetime.now(timezone.utc).isoformat()
        self._modified = True

        return True

    def change_entity_type(
        self,
        entity_id: str,
        new_entity_type: str
    ) -> bool:
        """
        Change the entity type for an existing entity.

        This handles re-indexing the entity with the new type while preserving
        all other metadata.

        Args:
            entity_id: Entity ID to update
            new_entity_type: New entity type (e.g., "destination" instead of "attraction")

        Returns:
            True if successful

        Example:
            registry.change_entity_type("attraction_bangkok_001", "destination")
        """
        if entity_id not in self.entities:
            logger.warning(f"Entity not found in registry: {entity_id}")
            return False

        entity_meta = self.entities[entity_id]
        old_type = entity_meta.get('entity_type')
        canonical_name = entity_meta.get('canonical_name')
        city = entity_meta.get('city', 'unknown')
        aliases = entity_meta.get('aliases', [])

        if old_type == new_entity_type:
            logger.debug(f"Entity {entity_id} already has type {new_entity_type}")
            return True

        logger.info(f"Changing entity type: {entity_id} ({canonical_name}) "
                   f"from {old_type} -> {new_entity_type}")

        # Remove old signatures from indexes
        old_signature = create_signature(canonical_name, city, old_type)
        if old_signature in self.name_index:
            del self.name_index[old_signature]

        for alias in aliases:
            old_alias_sig = create_signature(alias, city, old_type)
            if old_alias_sig in self.alias_index:
                del self.alias_index[old_alias_sig]

        # Update entity metadata
        entity_meta['entity_type'] = new_entity_type
        entity_meta['last_updated'] = datetime.now(timezone.utc).isoformat()

        # Create new signatures and re-index
        new_signature = create_signature(canonical_name, city, new_entity_type)
        entity_meta['name_signature'] = new_signature
        self.name_index[new_signature] = entity_id

        for alias in aliases:
            new_alias_sig = create_signature(alias, city, new_entity_type)
            if new_alias_sig != new_signature:
                self.alias_index[new_alias_sig] = entity_id

        self._modified = True

        logger.info(f"Successfully changed entity type for {entity_id}")

        return True

    def _generate_entity_id(self, entity_type: str, city: str) -> str:
        """Generate a unique, stable entity ID."""
        norm_type = entity_type.lower() if entity_type else 'unknown'
        norm_city = normalize_city_for_id(city)

        key = f"{norm_type}_{norm_city}"
        seq = self.next_sequence[key]
        self.next_sequence[key] = seq + 1

        return f"{norm_type}_{norm_city}_{seq:03d}"

    # -------------------------------------------------------------------------
    # Processed Videos Tracking
    # -------------------------------------------------------------------------

    def is_video_processed(self, video_id: str) -> bool:
        """Check if a video has already been processed."""
        if not self._loaded:
            self.load()
        return video_id in self.processed_videos

    def get_unprocessed_videos(self, video_ids: List[str]) -> List[str]:
        """Filter list to only unprocessed videos."""
        if not self._loaded:
            self.load()
        return [vid for vid in video_ids if vid not in self.processed_videos]

    def mark_video_processed(
        self,
        video_id: str,
        run_id: str,
        entity_ids: List[str]
    ) -> None:
        """
        Mark a video as processed.

        Args:
            video_id: Video ID that was processed
            run_id: Stage 3 run identifier
            entity_ids: Entity IDs created/updated from this video
        """
        self.processed_videos[video_id] = {
            'processed_at': datetime.now(timezone.utc).isoformat(),
            'run_id': run_id,
            'entity_ids': entity_ids
        }
        self._modified = True

    def get_processed_video_info(self, video_id: str) -> Optional[Dict]:
        """Get processing info for a video."""
        return self.processed_videos.get(video_id)

    # -------------------------------------------------------------------------
    # Bulk Operations
    # -------------------------------------------------------------------------

    def build_from_existing_entities(
        self,
        canonical_entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build registry from existing canonical entities.

        Use this to initialize the registry from current Stage 3 output.

        Args:
            canonical_entities: List of existing canonical entities

        Returns:
            Stats about the import
        """
        logger.info(f"Building registry from {len(canonical_entities)} existing entities...")

        stats = {
            'total': len(canonical_entities),
            'registered': 0,
            'skipped_no_name': 0,
            'aliases_indexed': 0
        }

        # Group by type+city to determine sequence numbers
        type_city_max: Dict[str, int] = defaultdict(int)

        for entity in canonical_entities:
            entity_id = entity.get('entity_id', '')
            name = entity.get('canonical_name')
            entity_type = entity.get('entity_type', 'unknown')
            city = entity.get('city') or entity.get('location') or 'unknown'

            if not name:
                stats['skipped_no_name'] += 1
                continue

            # Parse existing ID to get sequence number
            # Format: type_city_NNN
            parts = entity_id.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                seq = int(parts[1])
                key = parts[0]  # type_city
                type_city_max[key] = max(type_city_max[key], seq + 1)

            # Create signature
            signature = create_signature(name, city, entity_type)

            # Store entity metadata
            self.entities[entity_id] = {
                'canonical_name': name,
                'entity_type': entity_type,
                'city': city,
                'aliases': entity.get('aliases', []),
                'created_at': entity.get('provenance', {}).get('created_at',
                    datetime.now(timezone.utc).isoformat()),
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'source_video_ids': entity.get('source_video_ids', []),
                'experience_count': len(entity.get('experiences', [])),
                'name_signature': signature
            }

            # Index primary name
            self.name_index[signature] = entity_id

            # Index aliases
            for alias in entity.get('aliases', []):
                alias_sig = create_signature(alias, city, entity_type)
                if alias_sig != signature:
                    self.alias_index[alias_sig] = entity_id
                    stats['aliases_indexed'] += 1

            # Track processed videos
            for video_id in entity.get('source_video_ids', []):
                if video_id not in self.processed_videos:
                    self.processed_videos[video_id] = {
                        'processed_at': datetime.now(timezone.utc).isoformat(),
                        'run_id': 'initial_import',
                        'entity_ids': [entity_id]
                    }
                else:
                    # Add entity to existing video record
                    existing_entities = self.processed_videos[video_id].get('entity_ids', [])
                    if entity_id not in existing_entities:
                        existing_entities.append(entity_id)

            stats['registered'] += 1

        # Set sequence numbers
        self.next_sequence = defaultdict(int, type_city_max)

        self._modified = True
        self._loaded = True

        logger.info(f"Registry built: {stats['registered']} entities, "
                   f"{stats['aliases_indexed']} aliases indexed")

        return stats

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            'total_entities': len(self.entities),
            'total_signatures': len(self.name_index),
            'total_aliases': len(self.alias_index),
            'total_processed_videos': len(self.processed_videos),
            'entity_types': self._count_by_type(),
            'cities': self._count_by_city()
        }

    def _count_by_type(self) -> Dict[str, int]:
        """Count entities by type."""
        counts: Dict[str, int] = defaultdict(int)
        for meta in self.entities.values():
            counts[meta.get('entity_type', 'unknown')] += 1
        return dict(counts)

    def _count_by_city(self) -> Dict[str, int]:
        """Count entities by city."""
        counts: Dict[str, int] = defaultdict(int)
        for meta in self.entities.values():
            counts[meta.get('city', 'unknown')] += 1
        return dict(counts)


# =============================================================================
# Experience Deduplication
# =============================================================================

def hash_experience(experience: Dict[str, Any]) -> str:
    """
    Create a hash for an experience to detect duplicates.

    Uses video_id + content hash for uniqueness.
    """
    video_id = experience.get('source_video_id') or experience.get('video_id') or ''
    content = experience.get('experience', '')

    # Create content hash (first 500 chars to handle minor variations)
    content_normalized = content.lower().strip()[:500]
    content_hash = hashlib.md5(content_normalized.encode()).hexdigest()[:12]

    return f"{video_id}_{content_hash}"


def dedupe_experiences(experiences: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Remove duplicate experiences based on video_id + content hash.

    Args:
        experiences: List of experience dicts

    Returns:
        Tuple of (deduplicated experiences, count of duplicates removed)
    """
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []
    duplicates = 0

    for exp in experiences:
        exp_hash = hash_experience(exp)

        if exp_hash not in seen:
            seen.add(exp_hash)
            unique.append(exp)
        else:
            duplicates += 1

    if duplicates > 0:
        logger.debug(f"Removed {duplicates} duplicate experiences")

    return unique, duplicates


# =============================================================================
# Testing
# =============================================================================

def test_entity_registry():
    """Test entity registry functionality."""
    logger.info("=" * 80)
    logger.info("ENTITY REGISTRY TEST")
    logger.info("=" * 80)

    # Create registry in local-only mode for testing
    registry = EntityRegistry(local_only=True)

    # Test entity registration
    entity1 = {
        'canonical_name': 'Wat Pho',
        'entity_type': 'attraction',
        'city': 'Bangkok',
        'aliases': ['Wat Phra Chetuphon', 'Temple of Reclining Buddha'],
        'source_video_ids': ['youtube_abc123'],
        'experiences': [{'experience': 'Amazing temple!'}]
    }

    entity_id1 = registry.register_new_entity(entity1)
    logger.info(f"Registered: {entity1['canonical_name']} -> {entity_id1}")

    # Test exact match
    match = registry.find_matching_entity('Wat Pho', 'Bangkok', 'attraction')
    assert match == entity_id1, f"Expected {entity_id1}, got {match}"
    logger.info(f"Exact match: Wat Pho -> {match}")

    # Test alias match
    match = registry.find_matching_entity('Wat Phra Chetuphon', 'Bangkok', 'attraction')
    assert match == entity_id1, f"Expected {entity_id1}, got {match}"
    logger.info(f"Alias match: Wat Phra Chetuphon -> {match}")

    # Test no match
    match = registry.find_matching_entity('Grand Palace', 'Bangkok', 'attraction')
    assert match is None, f"Expected None, got {match}"
    logger.info(f"No match: Grand Palace -> {match}")

    # Test video processing
    registry.mark_video_processed('youtube_abc123', 'test_run', [entity_id1])
    assert registry.is_video_processed('youtube_abc123')
    assert not registry.is_video_processed('youtube_xyz789')
    logger.info("Video processing tracking works")

    # Test experience deduplication
    experiences = [
        {'source_video_id': 'v1', 'experience': 'Great place!'},
        {'source_video_id': 'v1', 'experience': 'Great place!'},  # Duplicate
        {'source_video_id': 'v2', 'experience': 'Great place!'},  # Same content, diff video
        {'source_video_id': 'v1', 'experience': 'Different experience'},
    ]

    deduped, removed = dedupe_experiences(experiences)
    assert len(deduped) == 3, f"Expected 3, got {len(deduped)}"
    assert removed == 1, f"Expected 1 duplicate, got {removed}"
    logger.info(f"Experience deduplication: {len(experiences)} -> {len(deduped)}")

    # Print stats
    stats = registry.get_stats()
    logger.info(f"Registry stats: {json.dumps(stats, indent=2)}")

    logger.info("=" * 80)
    logger.info("ALL TESTS PASSED")
    logger.info("=" * 80)


if __name__ == '__main__':
    test_entity_registry()
