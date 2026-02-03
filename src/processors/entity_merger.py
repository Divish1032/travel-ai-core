#!/usr/bin/env python3
"""
Entity Merger - Merge new experiences into existing canonical entities.

Provides intelligent merging of new Stage 2 data into existing canonical entities
while preserving history and recalculating scores.

Metadata Merge Strategy:
    - experiences: Append + dedupe by video_id + content hash
    - temporal_info: Re-aggregate from all experiences
    - logistics_info: Re-aggregate from all experiences
    - practical_tips: Merge with recency preference (newer wins)
    - coordinates: Keep highest confidence
    - popularity_score: Recalculate from merged data
    - data_freshness: Recalculate from all experience timestamps
    - enhanced_rating: Recalculate from all experiences

Usage:
    from src.processors.entity_merger import merge_entity_complete, EntityMerger

    # Complete merge with score recalculation
    updated_entity = merge_entity_complete(existing_entity, new_experiences)

    # Use EntityMerger for batch operations
    merger = EntityMerger(registry)
    merged, created, stats = merger.process_new_entities(new_entities, existing_entities)
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone
from collections import defaultdict
import copy

from src.utils.logging import get_logger
from src.storage.entity_registry import (
    EntityRegistry,
    dedupe_experiences,
    normalize_name
)

logger = get_logger(__name__)


# =============================================================================
# Experience Merging
# =============================================================================

def merge_entity_experiences(
    existing_entity: Dict[str, Any],
    new_experiences: List[Dict[str, Any]],
    new_video_ids: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    Merge new experiences into an existing canonical entity (experiences only).

    Args:
        existing_entity: Existing canonical entity dict
        new_experiences: List of new experience dicts to add
        new_video_ids: Set of new video IDs (optional, extracted from experiences if not provided)

    Returns:
        Updated canonical entity with merged experiences
    """
    # Deep copy to avoid mutating original
    updated = copy.deepcopy(existing_entity)

    # Extract video IDs from new experiences if not provided
    if new_video_ids is None:
        new_video_ids = set()
        for exp in new_experiences:
            vid = exp.get('source_video_id') or exp.get('video_id')
            if vid:
                new_video_ids.add(vid)

    # Add new experiences
    updated['experiences'] = list(updated.get('experiences', []))
    updated['experiences'].extend(new_experiences)

    # Deduplicate experiences
    updated['experiences'], dupes_removed = dedupe_experiences(updated['experiences'])

    # Update video IDs
    existing_vids = set(updated.get('source_video_ids', []))
    existing_vids.update(new_video_ids)
    updated['source_video_ids'] = sorted(existing_vids)

    # Update mention count
    updated['total_mentions'] = len(updated['experiences'])

    # Update provenance
    if 'provenance' not in updated:
        updated['provenance'] = {}

    updated['provenance']['last_merged_at'] = datetime.now(timezone.utc).isoformat()
    updated['provenance']['experiences_added'] = len(new_experiences) - dupes_removed
    updated['provenance']['duplicates_removed'] = dupes_removed

    logger.debug(
        f"Merged {len(new_experiences)} experiences into {existing_entity.get('canonical_name')}, "
        f"{dupes_removed} duplicates removed"
    )

    return updated


def merge_entity_complete(
    existing_entity: Dict[str, Any],
    new_experiences: List[Dict[str, Any]],
    new_video_ids: Optional[Set[str]] = None,
    recalculate_scores: bool = True
) -> Dict[str, Any]:
    """
    Complete merge of new experiences with full metadata recalculation.

    This is the main merge function that should be used for incremental processing.
    It merges experiences and then recalculates all derived fields.

    Args:
        existing_entity: Existing canonical entity dict
        new_experiences: List of new experience dicts to add
        new_video_ids: Set of new video IDs
        recalculate_scores: Whether to recalculate all scores (default: True)

    Returns:
        Updated canonical entity with merged experiences and recalculated scores
    """
    # First merge experiences
    updated = merge_entity_experiences(existing_entity, new_experiences, new_video_ids)

    if recalculate_scores:
        # Recalculate all derived fields from merged experiences
        updated = recalculate_all_scores(updated)

    return updated


# =============================================================================
# Metadata Merging
# =============================================================================

def merge_temporal_info(
    existing: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Merge temporal info with union of values and recalculated confidence.

    Args:
        existing: Existing temporal_info dict
        new: New temporal_info dict

    Returns:
        Merged temporal_info dict
    """
    if not existing and not new:
        return None
    if not existing:
        return copy.deepcopy(new)
    if not new:
        return copy.deepcopy(existing)

    merged = {}

    # Merge list fields with union (dedupe)
    list_fields = ['best_seasons', 'best_times_of_day', 'recommended_duration']
    for field in list_fields:
        existing_vals = set(existing.get(field, []) or [])
        new_vals = set(new.get(field, []) or [])
        merged_vals = existing_vals.union(new_vals)
        if merged_vals:
            merged[field] = sorted(merged_vals)

    # Keep typical_duration - prefer existing if set, else new
    if existing.get('typical_duration'):
        merged['typical_duration'] = existing['typical_duration']
    elif new.get('typical_duration'):
        merged['typical_duration'] = new['typical_duration']

    # Average confidence
    existing_conf = existing.get('confidence', 0.5)
    new_conf = new.get('confidence', 0.5)
    merged['confidence'] = round((existing_conf + new_conf) / 2, 3)

    # Source becomes 'merged'
    existing_source = existing.get('source', 'unknown')
    new_source = new.get('source', 'unknown')
    if existing_source == new_source:
        merged['source'] = existing_source
    else:
        merged['source'] = 'merged'

    return merged if merged else None


def merge_logistics_info(
    existing: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Merge logistics info with union of transport options.

    Args:
        existing: Existing logistics_info dict
        new: New logistics_info dict

    Returns:
        Merged logistics_info dict
    """
    if not existing and not new:
        return None
    if not existing:
        return copy.deepcopy(new)
    if not new:
        return copy.deepcopy(existing)

    merged = {}

    # Merge list fields with union
    list_fields = ['transport_options', 'accessibility_features', 'nearby_landmarks']
    for field in list_fields:
        existing_vals = existing.get(field, []) or []
        new_vals = new.get(field, []) or []
        # Use list to preserve order, dedupe manually
        seen = set()
        merged_list = []
        for val in existing_vals + new_vals:
            val_lower = val.lower() if isinstance(val, str) else str(val)
            if val_lower not in seen:
                seen.add(val_lower)
                merged_list.append(val)
        if merged_list:
            merged[field] = merged_list

    # Boolean fields - True if any is True
    if existing.get('booking_required') or new.get('booking_required'):
        merged['booking_required'] = True
    else:
        merged['booking_required'] = False

    # Average confidence
    existing_conf = existing.get('confidence', 0.5)
    new_conf = new.get('confidence', 0.5)
    merged['confidence'] = round((existing_conf + new_conf) / 2, 3)

    # Source becomes 'merged'
    merged['source'] = 'merged'

    return merged if merged else None


def merge_practical_tips(
    existing: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Merge practical tips with recency preference (newer values win for conflicts).

    This handles fields like entrance_fee, opening_hours, dress_code that may
    change over time - newer information should take precedence.

    Args:
        existing: Existing practical_tips dict
        new: New practical_tips dict

    Returns:
        Merged practical_tips dict
    """
    if not existing and not new:
        return None
    if not existing:
        return copy.deepcopy(new)
    if not new:
        return copy.deepcopy(existing)

    # Start with existing, overlay new values (newer wins)
    merged = copy.deepcopy(existing)

    for key, value in new.items():
        if value is not None and value != '':
            # New value takes precedence (assumed to be more recent)
            merged[key] = value

    return merged if merged else None


def merge_coordinates(
    existing: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Merge coordinates, preferring higher confidence.

    Args:
        existing: Existing coordinates dict
        new: New coordinates dict

    Returns:
        Best coordinates based on confidence
    """
    if not existing:
        return copy.deepcopy(new) if new else None
    if not new:
        return copy.deepcopy(existing)

    existing_conf = existing.get('confidence', 0)
    new_conf = new.get('confidence', 0)

    # Return the one with higher confidence
    if new_conf > existing_conf:
        return copy.deepcopy(new)
    return copy.deepcopy(existing)


def merge_enrichment_provenance(
    existing: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]],
    merge_timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merge enrichment provenance, tracking merge history.

    Args:
        existing: Existing enrichment_provenance dict
        new: New enrichment_provenance dict
        merge_timestamp: Timestamp of the merge

    Returns:
        Updated enrichment_provenance dict
    """
    if merge_timestamp is None:
        merge_timestamp = datetime.now(timezone.utc).isoformat()

    merged = copy.deepcopy(existing) if existing else {}

    # Update with new values if present
    if new:
        if new.get('fame_score'):
            # Average fame scores
            existing_fame = merged.get('fame_score', 0.5)
            new_fame = new.get('fame_score', 0.5)
            merged['fame_score'] = round((existing_fame + new_fame) / 2, 2)

        if new.get('llm_confidence'):
            existing_conf = merged.get('llm_confidence', 0.5)
            new_conf = new.get('llm_confidence', 0.5)
            merged['llm_confidence'] = round((existing_conf + new_conf) / 2, 2)

        # Update transcript mentions (sum)
        merged['transcript_mentions'] = (
            merged.get('transcript_mentions', 0) +
            new.get('transcript_mentions', 0)
        )

        # Update last transcript update
        if new.get('last_transcript_update'):
            merged['last_transcript_update'] = new['last_transcript_update']

    # Track merge
    merged['source'] = 'merged'
    merged['last_merged_at'] = merge_timestamp
    merged['merge_count'] = merged.get('merge_count', 0) + 1

    return merged


def merge_aliases(
    existing_aliases: List[str],
    new_aliases: List[str],
    canonical_name: str
) -> List[str]:
    """
    Merge alias lists, avoiding duplicates and the canonical name.

    Args:
        existing_aliases: Current alias list
        new_aliases: New aliases to add
        canonical_name: The canonical name (should not be in aliases)

    Returns:
        Merged and deduplicated alias list
    """
    all_aliases = set()

    # Normalize canonical name for comparison
    norm_canonical = normalize_name(canonical_name)

    for alias in (existing_aliases or []) + (new_aliases or []):
        if alias:
            norm_alias = normalize_name(alias)
            if norm_alias and norm_alias != norm_canonical:
                all_aliases.add(alias)

    return sorted(all_aliases)


def merge_attributes(
    existing_attrs: Dict[str, Any],
    new_attrs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Merge entity attributes with union strategy for lists.

    Args:
        existing_attrs: Existing attributes dict
        new_attrs: New attributes to merge

    Returns:
        Merged attributes dict
    """
    merged = copy.deepcopy(existing_attrs) if existing_attrs else {}

    for key, value in (new_attrs or {}).items():
        if key not in merged or merged[key] is None:
            merged[key] = value
        elif isinstance(value, list) and isinstance(merged[key], list):
            # Union for lists (case-insensitive dedup)
            existing_lower = {str(v).lower() for v in merged[key]}
            for v in value:
                if str(v).lower() not in existing_lower:
                    merged[key].append(v)
                    existing_lower.add(str(v).lower())
        # For non-list values, keep existing (first wins for attributes)

    return merged


# =============================================================================
# Score Recalculation
# =============================================================================

def recalculate_all_scores(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recalculate all derived scores and aggregated fields from experiences.

    This function re-runs all the score calculations that depend on experience data.
    Should be called after merging new experiences.

    Args:
        entity: Canonical entity with merged experiences

    Returns:
        Entity with recalculated scores
    """
    # Import here to avoid circular imports
    from src.processors.stage3_enrichment import (
        calculate_popularity_score,
        calculate_data_freshness,
        calculate_multi_signal_rating,
        aggregate_temporal_info,
        aggregate_logistics_info
    )

    updated = copy.deepcopy(entity)
    experiences = updated.get('experiences', [])

    if not experiences:
        return updated

    # Recalculate popularity score
    try:
        updated['popularity_score'] = calculate_popularity_score(updated)
    except Exception as e:
        logger.warning(f"Failed to recalculate popularity_score: {e}")

    # Recalculate data freshness
    try:
        updated['data_freshness'] = calculate_data_freshness(updated)
    except Exception as e:
        logger.warning(f"Failed to recalculate data_freshness: {e}")

    # Recalculate enhanced rating
    try:
        updated['enhanced_rating'] = calculate_multi_signal_rating(updated)
    except Exception as e:
        logger.warning(f"Failed to recalculate enhanced_rating: {e}")

    # Re-aggregate temporal info from experiences
    try:
        new_temporal = aggregate_temporal_info(experiences)
        if new_temporal:
            updated['temporal_info'] = merge_temporal_info(
                updated.get('temporal_info'),
                new_temporal
            )
    except Exception as e:
        logger.warning(f"Failed to re-aggregate temporal_info: {e}")

    # Re-aggregate logistics info from experiences
    try:
        new_logistics = aggregate_logistics_info(experiences)
        if new_logistics:
            updated['logistics_info'] = merge_logistics_info(
                updated.get('logistics_info'),
                new_logistics
            )
    except Exception as e:
        logger.warning(f"Failed to re-aggregate logistics_info: {e}")

    # Update enrichment provenance
    updated['enrichment_provenance'] = merge_enrichment_provenance(
        updated.get('enrichment_provenance'),
        {'transcript_mentions': len(experiences)},
        datetime.now(timezone.utc).isoformat()
    )

    logger.debug(f"Recalculated scores for {updated.get('canonical_name')}")

    return updated


# =============================================================================
# Full Entity Merge (for incremental processing)
# =============================================================================

def merge_canonical_entities(
    existing: Dict[str, Any],
    new_entity: Dict[str, Any],
    recalculate_scores: bool = True
) -> Dict[str, Any]:
    """
    Merge two canonical entities completely.

    This is used when a new canonical entity (from new batch) matches an existing one.

    Args:
        existing: Existing canonical entity
        new_entity: New canonical entity to merge in
        recalculate_scores: Whether to recalculate all scores

    Returns:
        Merged canonical entity
    """
    updated = copy.deepcopy(existing)

    # Merge experiences
    new_experiences = new_entity.get('experiences', [])
    if new_experiences:
        updated['experiences'] = list(updated.get('experiences', []))
        updated['experiences'].extend(new_experiences)
        updated['experiences'], _ = dedupe_experiences(updated['experiences'])

    # Merge video IDs
    existing_vids = set(updated.get('source_video_ids', []))
    new_vids = set(new_entity.get('source_video_ids', []))
    updated['source_video_ids'] = sorted(existing_vids.union(new_vids))

    # Update total mentions
    updated['total_mentions'] = len(updated['experiences'])

    # Merge aliases
    updated['aliases'] = merge_aliases(
        updated.get('aliases', []),
        new_entity.get('aliases', []),
        updated.get('canonical_name', '')
    )

    # Merge attributes
    updated['attributes'] = merge_attributes(
        updated.get('attributes', {}),
        new_entity.get('attributes', {})
    )

    # Merge temporal info
    updated['temporal_info'] = merge_temporal_info(
        updated.get('temporal_info'),
        new_entity.get('temporal_info')
    )

    # Merge logistics info
    updated['logistics_info'] = merge_logistics_info(
        updated.get('logistics_info'),
        new_entity.get('logistics_info')
    )

    # Merge practical tips (newer wins)
    updated['practical_tips'] = merge_practical_tips(
        updated.get('practical_tips'),
        new_entity.get('practical_tips')
    )

    # Merge coordinates (higher confidence wins)
    updated['coordinates'] = merge_coordinates(
        updated.get('coordinates'),
        new_entity.get('coordinates')
    )

    # Keep reverse_geocode_info from existing unless coordinates changed
    # (Would need geocoding to update, so keep existing)

    # Update provenance
    if 'provenance' not in updated:
        updated['provenance'] = {}
    updated['provenance']['last_merged_at'] = datetime.now(timezone.utc).isoformat()
    updated['provenance']['merge_count'] = updated['provenance'].get('merge_count', 0) + 1

    # Recalculate scores if requested
    if recalculate_scores:
        updated = recalculate_all_scores(updated)

    logger.debug(f"Merged canonical entities: {updated.get('canonical_name')}")

    return updated


# =============================================================================
# Entity Merger Class
# =============================================================================

class EntityMerger:
    """
    Handles merging of new Stage 2 entities with existing canonical entities.

    Provides batch processing capabilities for incremental Stage 3 runs.
    """

    def __init__(self, registry: EntityRegistry):
        """
        Initialize the entity merger.

        Args:
            registry: EntityRegistry instance for entity lookup
        """
        self.registry = registry
        self.stats = {
            'total_new': 0,
            'matched_existing': 0,
            'created_new': 0,
            'experiences_merged': 0,
            'duplicates_removed': 0,
            'scores_recalculated': 0
        }

    def process_new_entities(
        self,
        new_entities: List[Dict[str, Any]],
        existing_entities: Dict[str, Dict[str, Any]],
        recalculate_scores: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process new Stage 2 entities, merging with existing or creating new.

        Args:
            new_entities: List of new Stage 2 entity dicts (with provenance)
            existing_entities: Dict of existing canonical entities keyed by entity_id
            recalculate_scores: Whether to recalculate scores after merge

        Returns:
            Tuple of:
            - updated_entities: Existing entities that were updated
            - new_canonical: Newly created canonical entities
            - stats: Processing statistics
        """
        self.stats = {
            'total_new': len(new_entities),
            'matched_existing': 0,
            'created_new': 0,
            'experiences_merged': 0,
            'duplicates_removed': 0,
            'scores_recalculated': 0
        }

        # Group new entities by match status
        matched_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        unmatched: List[Dict[str, Any]] = []

        for entity_data in new_entities:
            entity = entity_data.get('entity', entity_data)
            provenance = entity_data.get('provenance', {})

            name = entity.get('name') or entity.get('canonical_name')
            entity_type = entity.get('entity_type', 'unknown')
            city = entity.get('city') or entity.get('location') or 'unknown'
            aliases = entity.get('aliases', [])

            # Try to find matching existing entity
            matched_id = self.registry.find_matching_entity(
                name=name,
                city=city,
                entity_type=entity_type,
                aliases=aliases
            )

            if matched_id and matched_id in existing_entities:
                matched_groups[matched_id].append(entity_data)
                self.stats['matched_existing'] += 1
            else:
                unmatched.append(entity_data)

        # Merge matched entities
        updated_entities = []
        for entity_id, group in matched_groups.items():
            existing = existing_entities[entity_id]
            updated = self._merge_group_into_entity(existing, group, recalculate_scores)
            updated_entities.append(updated)

            # Update registry metadata
            new_aliases = []
            new_video_ids = []
            for entity_data in group:
                entity = entity_data.get('entity', entity_data)
                new_aliases.extend(entity.get('aliases', []))
                provenance = entity_data.get('provenance', {})
                vid = provenance.get('source_video_id')
                if vid:
                    new_video_ids.append(vid)

            self.registry.update_entity_metadata(
                entity_id=entity_id,
                new_aliases=new_aliases,
                new_video_ids=new_video_ids,
                experience_count=len(updated.get('experiences', []))
            )

            if recalculate_scores:
                self.stats['scores_recalculated'] += 1

        # Unmatched entities should go through normal deduplication
        self.stats['created_new'] = len(unmatched)

        logger.info(
            f"Entity merge complete: {self.stats['matched_existing']} merged, "
            f"{self.stats['created_new']} new, "
            f"{self.stats['scores_recalculated']} scores recalculated"
        )

        return updated_entities, unmatched, self.stats

    def _merge_group_into_entity(
        self,
        existing: Dict[str, Any],
        new_entity_group: List[Dict[str, Any]],
        recalculate_scores: bool = True
    ) -> Dict[str, Any]:
        """
        Merge a group of new entities into an existing canonical entity.

        Args:
            existing: Existing canonical entity
            new_entity_group: List of new entity dicts to merge
            recalculate_scores: Whether to recalculate scores

        Returns:
            Updated canonical entity
        """
        # Collect all new experiences
        new_experiences = []
        new_aliases = []
        new_video_ids = set()

        for entity_data in new_entity_group:
            entity = entity_data.get('entity', entity_data)
            provenance = entity_data.get('provenance', {})

            # Extract experience
            experience_text = entity.get('experience', '')
            source_video_id = provenance.get('source_video_id', 'unknown')

            if experience_text:
                new_experiences.append({
                    'experience': experience_text,
                    'video_id': provenance.get('content_id', f'youtube_{source_video_id}'),
                    'source_video_id': source_video_id,
                    'traveler_profile': provenance.get('traveler_profile', {}),
                    'language': provenance.get('language', 'unknown'),
                    'processed_at': provenance.get('processed_at')
                })
                new_video_ids.add(source_video_id)

            # Collect aliases
            new_aliases.extend(entity.get('aliases', []))

            # Also add entity name as potential alias
            name = entity.get('name') or entity.get('canonical_name')
            if name and name != existing.get('canonical_name'):
                new_aliases.append(name)

        # Perform complete merge with score recalculation
        updated = merge_entity_complete(
            existing,
            new_experiences,
            new_video_ids,
            recalculate_scores=recalculate_scores
        )

        # Merge aliases
        updated['aliases'] = merge_aliases(
            existing.get('aliases', []),
            new_aliases,
            existing.get('canonical_name', '')
        )

        # Track stats
        self.stats['experiences_merged'] += len(new_experiences)

        return updated


# =============================================================================
# Utility Functions
# =============================================================================

def build_existing_entities_dict(
    canonical_entities: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Build a dictionary of canonical entities keyed by entity_id.

    Args:
        canonical_entities: List of canonical entity dicts

    Returns:
        Dict mapping entity_id to entity dict
    """
    return {
        entity.get('entity_id'): entity
        for entity in canonical_entities
        if entity.get('entity_id')
    }


# =============================================================================
# Testing
# =============================================================================

def test_entity_merger():
    """Test entity merging functionality."""
    logger.info("=" * 80)
    logger.info("ENTITY MERGER TEST")
    logger.info("=" * 80)

    # Create test existing entity
    existing = {
        'entity_id': 'attraction_bangkok_001',
        'canonical_name': 'Wat Pho',
        'aliases': ['Wat Phra Chetuphon'],
        'entity_type': 'attraction',
        'city': 'Bangkok',
        'country': 'Thailand',
        'experiences': [
            {
                'experience': 'Amazing temple with golden Buddha.',
                'source_video_id': 'video1',
                'video_id': 'youtube_video1',
                'processed_at': '2026-01-20T10:00:00Z'
            }
        ],
        'source_video_ids': ['video1'],
        'total_mentions': 1,
        'temporal_info': {
            'best_seasons': ['November to February'],
            'confidence': 0.8,
            'source': 'transcript_extracted'
        },
        'practical_tips': {
            'entrance_fee': '100 THB',
            'opening_hours': '8:00 AM - 5:00 PM'
        }
    }

    # Create new experiences to merge
    new_experiences = [
        {
            'experience': 'Beautiful reclining Buddha, must see!',
            'source_video_id': 'video2',
            'video_id': 'youtube_video2',
            'processed_at': '2026-01-25T10:00:00Z'
        },
        {
            'experience': 'Amazing temple with golden Buddha.',  # Duplicate content
            'source_video_id': 'video1',  # Same video
            'video_id': 'youtube_video1',
            'processed_at': '2026-01-20T10:00:00Z'
        }
    ]

    # Test basic merge
    updated = merge_entity_experiences(existing, new_experiences)

    assert len(updated['experiences']) == 2, f"Expected 2 experiences, got {len(updated['experiences'])}"
    assert 'video2' in updated['source_video_ids'], "video2 should be in source_video_ids"
    assert updated['total_mentions'] == 2, f"Expected 2 mentions, got {updated['total_mentions']}"

    logger.info(f"✅ Basic merge: {len(updated['experiences'])} experiences")

    # Test temporal info merge
    new_temporal = {
        'best_seasons': ['March to May'],
        'typical_duration': 'half day',
        'confidence': 0.9,
        'source': 'llm_inferred'
    }
    merged_temporal = merge_temporal_info(existing['temporal_info'], new_temporal)
    assert 'November to February' in merged_temporal['best_seasons']
    assert 'March to May' in merged_temporal['best_seasons']
    assert merged_temporal['source'] == 'merged'
    logger.info(f"✅ Temporal merge: {merged_temporal['best_seasons']}")

    # Test practical tips merge (newer wins)
    new_tips = {
        'entrance_fee': '200 THB',  # Updated price
        'dress_code': 'Modest attire'  # New field
    }
    merged_tips = merge_practical_tips(existing['practical_tips'], new_tips)
    assert merged_tips['entrance_fee'] == '200 THB', "New price should win"
    assert merged_tips['opening_hours'] == '8:00 AM - 5:00 PM', "Existing should be kept"
    assert merged_tips['dress_code'] == 'Modest attire', "New field should be added"
    logger.info(f"✅ Practical tips merge: entrance_fee={merged_tips['entrance_fee']}")

    # Test alias merging
    merged_aliases = merge_aliases(
        ['Wat Phra Chetuphon'],
        ['Temple of Reclining Buddha', 'Wat Pho'],  # 'Wat Pho' should be excluded
        'Wat Pho'
    )
    assert 'Wat Pho' not in merged_aliases, "Canonical name should not be in aliases"
    assert 'Temple of Reclining Buddha' in merged_aliases
    logger.info(f"✅ Alias merge: {merged_aliases}")

    logger.info("=" * 80)
    logger.info("ALL TESTS PASSED")
    logger.info("=" * 80)


if __name__ == '__main__':
    test_entity_merger()
