"""
Stage 3 Entity Deduplication: Tier 1 & 2 Matching

Implements exact and fuzzy matching for entity deduplication:
- Tier 1: Exact matching (same normalized name, city, type)
- Tier 2: Fuzzy matching (similar names with similarity threshold)

Usage:
    from src.processors.deduplication import (
        exact_match,
        fuzzy_match,
        group_exact_matches,
        find_fuzzy_candidates
    )

    # Group exact duplicates
    exact_groups = group_exact_matches(entities)

    # Find fuzzy match candidates
    fuzzy_pairs = find_fuzzy_candidates(entities, threshold=0.80)
"""

from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import uuid

from rapidfuzz import fuzz
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Tier 1: Exact Matching
# =============================================================================


def exact_match(entity1: Dict[str, Any], entity2: Dict[str, Any]) -> bool:
    """
    Check if two entities are an exact match.

    Exact match criteria:
    - Same normalized name
    - Same normalized location (city)
    - Same entity_type

    Args:
        entity1: First entity dict (from stage3_loader)
        entity2: Second entity dict (from stage3_loader)

    Returns:
        True if entities match exactly, False otherwise

    Examples:
        >>> entity1 = {
        ...     'normalized_name': 'wat pho',
        ...     'normalized_location': 'bangkok',
        ...     'entity': {'entity_type': 'attraction'}
        ... }
        >>> entity2 = {
        ...     'normalized_name': 'wat pho',
        ...     'normalized_location': 'bangkok',
        ...     'entity': {'entity_type': 'attraction'}
        ... }
        >>> exact_match(entity1, entity2)
        True
    """
    # Extract fields for comparison
    name1 = entity1.get('normalized_name', '').strip().lower()
    name2 = entity2.get('normalized_name', '').strip().lower()

    location1 = entity1.get('normalized_location', '').strip().lower() if entity1.get('normalized_location') else ''
    location2 = entity2.get('normalized_location', '').strip().lower() if entity2.get('normalized_location') else ''

    type1 = entity1.get('entity', {}).get('entity_type', '').strip().lower()
    type2 = entity2.get('entity', {}).get('entity_type', '').strip().lower()

    # Check if all fields match
    if not name1 or not name2:
        return False

    return (
        name1 == name2 and
        location1 == location2 and
        type1 == type2
    )


def group_exact_matches(entities: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group entities with exact matches together.

    Creates groups where all entities in a group are exact matches.
    Preserves all provenance information for each entity.

    Args:
        entities: List of entity dicts from stage3_loader

    Returns:
        Dict mapping group_id to list of matching entities
        {
            'group_abc123': [entity1, entity2, entity3],
            'group_def456': [entity4, entity5],
            ...
        }

    Example:
        >>> entities = load_all_stage2_entities(s3)['all_entities']
        >>> groups = group_exact_matches(entities)
        >>> print(f"Found {len(groups)} exact match groups")
    """
    logger.info("Starting exact match grouping...")

    # Create signature for each entity (normalized_name + location + type)
    entity_signatures = {}

    for entity in entities:
        name = entity.get('normalized_name', '').strip().lower()
        location = entity.get('normalized_location', '').strip().lower() if entity.get('normalized_location') else ''
        entity_type = entity.get('entity', {}).get('entity_type', '').strip().lower()

        if not name:
            continue

        # Create unique signature
        signature = f"{name}||{location}||{entity_type}"

        if signature not in entity_signatures:
            entity_signatures[signature] = []

        entity_signatures[signature].append(entity)

    # Create groups only for signatures with multiple entities
    exact_match_groups = {}
    singleton_count = 0

    for signature, matching_entities in entity_signatures.items():
        if len(matching_entities) > 1:
            # Multiple entities match - create a group
            group_id = f"exact_{uuid.uuid4().hex[:12]}"
            exact_match_groups[group_id] = matching_entities
        else:
            # Only one entity with this signature - singleton
            singleton_count += 1

    # Log statistics
    total_entities_in_groups = sum(len(group) for group in exact_match_groups.values())

    logger.info("✅ Exact matching complete:")
    logger.info(f"   Total entities: {len(entities)}")
    logger.info(f"   Exact match groups: {len(exact_match_groups)}")
    logger.info(f"   Entities in groups: {total_entities_in_groups}")
    logger.info(f"   Singleton entities: {singleton_count}")
    logger.info(f"   Avg entities per group: {total_entities_in_groups / len(exact_match_groups) if exact_match_groups else 0:.1f}")

    # Log examples of top groups
    if exact_match_groups:
        logger.info("")
        logger.info("Top 5 exact match groups:")
        sorted_groups = sorted(
            exact_match_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:5]

        for i, (group_id, group_entities) in enumerate(sorted_groups, 1):
            first_entity = group_entities[0]
            name = first_entity.get('original_name', 'Unknown')
            location = first_entity.get('original_location', 'Unknown')
            entity_type = first_entity.get('entity', {}).get('entity_type', 'unknown')

            logger.info(
                f"   {i}. {name} ({location}) [{entity_type}] - "
                f"{len(group_entities)} matches"
            )

    return exact_match_groups


# =============================================================================
# Tier 2: Fuzzy Matching
# =============================================================================


def fuzzy_match(
    entity1: Dict[str, Any],
    entity2: Dict[str, Any],
    name_similarity_threshold: float = 0.0
) -> float:
    """
    Calculate fuzzy similarity score between two entities.

    Uses Levenshtein distance (via rapidfuzz) to calculate similarity.
    Only compares entities with same city and entity_type.
    Applies length penalty for very different name lengths.

    Args:
        entity1: First entity dict
        entity2: Second entity dict
        name_similarity_threshold: Minimum threshold to check (optimization)

    Returns:
        Similarity score from 0.0 to 1.0
        Returns 0.0 if entities are from different cities/types

    Examples:
        >>> entity1 = {
        ...     'normalized_name': 'wat pho temple',
        ...     'normalized_location': 'bangkok',
        ...     'entity': {'entity_type': 'attraction'}
        ... }
        >>> entity2 = {
        ...     'normalized_name': 'wat pho',
        ...     'normalized_location': 'bangkok',
        ...     'entity': {'entity_type': 'attraction'}
        ... }
        >>> similarity = fuzzy_match(entity1, entity2)
        >>> print(f"Similarity: {similarity:.2f}")
    """
    # Must have same location and type for fuzzy matching
    location1 = entity1.get('normalized_location', '').strip().lower() if entity1.get('normalized_location') else ''
    location2 = entity2.get('normalized_location', '').strip().lower() if entity2.get('normalized_location') else ''

    type1 = entity1.get('entity', {}).get('entity_type', '').strip().lower()
    type2 = entity2.get('entity', {}).get('entity_type', '').strip().lower()

    # Different location or type = no match
    if location1 != location2 or type1 != type2:
        return 0.0

    # Extract normalized names
    name1 = entity1.get('normalized_name', '').strip().lower()
    name2 = entity2.get('normalized_name', '').strip().lower()

    if not name1 or not name2:
        return 0.0

    # If names are identical, return 1.0
    if name1 == name2:
        return 1.0

    # Calculate Levenshtein similarity using rapidfuzz
    # fuzz.ratio returns 0-100, we convert to 0.0-1.0
    base_similarity = fuzz.ratio(name1, name2) / 100.0

    # Apply length penalty
    # If one name is much longer/shorter than the other, reduce similarity
    len1, len2 = len(name1), len(name2)
    length_ratio = min(len1, len2) / max(len1, len2)

    # Length penalty: if one is 2x longer, apply 0.8x penalty
    # e.g., "temple" vs "temple of the golden buddha" should score lower
    length_penalty = 0.7 + (0.3 * length_ratio)  # Ranges from 0.7 to 1.0

    # Final similarity with length penalty
    final_similarity = base_similarity * length_penalty

    return final_similarity


def find_fuzzy_candidates(
    entities: List[Dict[str, Any]],
    threshold: float = 0.80,
    exclude_exact_matches: bool = True
) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
    """
    Find entity pairs with fuzzy similarity above threshold.

    Compares entities within same city and entity_type.
    Optionally filters out pairs that are already exact matches.

    Args:
        entities: List of entity dicts from stage3_loader
        threshold: Minimum similarity score (0.0-1.0)
        exclude_exact_matches: If True, filter out exact matches

    Returns:
        List of tuples: [(entity1, entity2, similarity_score), ...]
        Sorted by similarity score (highest first)

    Example:
        >>> entities = load_all_stage2_entities(s3)['all_entities']
        >>> fuzzy_pairs = find_fuzzy_candidates(entities, threshold=0.80)
        >>> print(f"Found {len(fuzzy_pairs)} fuzzy match candidates")
        >>> for e1, e2, score in fuzzy_pairs[:5]:
        ...     print(f"{e1['original_name']} ~ {e2['original_name']}: {score:.2f}")
    """
    logger.info(f"Finding fuzzy match candidates (threshold={threshold:.2f})...")

    # Step 1: Group entities by (location, type) for efficient comparison
    location_type_groups = defaultdict(list)

    for entity in entities:
        location = entity.get('normalized_location', '').strip().lower() if entity.get('normalized_location') else ''
        entity_type = entity.get('entity', {}).get('entity_type', '').strip().lower()

        key = f"{location}||{entity_type}"
        location_type_groups[key].append(entity)

    logger.info(f"   Grouped into {len(location_type_groups)} location-type combinations")

    # Step 2: Get exact match signatures (if we want to exclude them)
    exact_match_signatures = set()
    if exclude_exact_matches:
        for entity in entities:
            name = entity.get('normalized_name', '').strip().lower()
            location = entity.get('normalized_location', '').strip().lower() if entity.get('normalized_location') else ''
            entity_type = entity.get('entity', {}).get('entity_type', '').strip().lower()

            if name:
                signature = f"{name}||{location}||{entity_type}"
                exact_match_signatures.add(signature)

    # Step 3: Compare entities within each group
    fuzzy_candidates = []
    total_comparisons = 0

    for key, group_entities in location_type_groups.items():
        if len(group_entities) < 2:
            continue  # No pairs to compare

        # Compare all pairs within this group
        for i in range(len(group_entities)):
            for j in range(i + 1, len(group_entities)):
                entity1 = group_entities[i]
                entity2 = group_entities[j]

                total_comparisons += 1

                # Skip if exact match (if excluding)
                if exclude_exact_matches and exact_match(entity1, entity2):
                    continue

                # Calculate similarity
                similarity = fuzzy_match(entity1, entity2)

                if similarity >= threshold:
                    fuzzy_candidates.append((entity1, entity2, similarity))

    # Sort by similarity (highest first)
    fuzzy_candidates.sort(key=lambda x: x[2], reverse=True)

    # Log statistics
    logger.info("✅ Fuzzy matching complete:")
    logger.info(f"   Total comparisons: {total_comparisons:,}")
    logger.info(f"   Fuzzy candidates found: {len(fuzzy_candidates)}")
    logger.info(f"   Threshold: {threshold:.2f}")

    # Log examples
    if fuzzy_candidates:
        logger.info("")
        logger.info("Top 10 fuzzy match candidates:")
        for i, (e1, e2, score) in enumerate(fuzzy_candidates[:10], 1):
            name1 = e1.get('original_name', 'Unknown')
            name2 = e2.get('original_name', 'Unknown')
            location = e1.get('original_location', 'Unknown')
            entity_type = e1.get('entity', {}).get('entity_type', 'unknown')

            logger.info(
                f"   {i}. [{entity_type}] {name1} ~ {name2} "
                f"({location}) - {score:.2f}"
            )
    else:
        logger.info("   No fuzzy candidates found above threshold")

    return fuzzy_candidates


# =============================================================================
# Helper Functions
# =============================================================================


def print_deduplication_summary(
    exact_groups: Dict[str, List[Dict[str, Any]]],
    fuzzy_candidates: List[Tuple[Dict[str, Any], Dict[str, Any], float]],
    total_entities: int
) -> None:
    """
    Print a formatted summary of deduplication results.

    Args:
        exact_groups: Result from group_exact_matches()
        fuzzy_candidates: Result from find_fuzzy_candidates()
        total_entities: Total number of entities processed
    """
    print('=' * 80)
    print('DEDUPLICATION SUMMARY (Tier 1 & 2)')
    print('=' * 80)
    print()

    # Overall stats
    print('OVERALL STATISTICS:')
    print('-' * 80)
    print(f"Total entities:              {total_entities:,}")
    print(f"Exact match groups:          {len(exact_groups)}")

    entities_in_exact_groups = sum(len(group) for group in exact_groups.values())
    print(f"Entities in exact groups:    {entities_in_exact_groups:,}")

    singleton_entities = total_entities - entities_in_exact_groups
    print(f"Singleton entities:          {singleton_entities:,}")
    print(f"Fuzzy match candidates:      {len(fuzzy_candidates)}")
    print()

    # Exact match group distribution
    if exact_groups:
        print('EXACT MATCH GROUPS (Top 10):')
        print('-' * 80)

        sorted_groups = sorted(
            exact_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]

        for i, (group_id, group_entities) in enumerate(sorted_groups, 1):
            first = group_entities[0]
            name = first.get('original_name', 'Unknown')
            location = first.get('original_location') or 'Unknown'
            entity_type = first.get('entity', {}).get('entity_type', 'unknown')

            print(f"  {i:2d}. {name:40s} [{entity_type:12s}] ({location:20s}) - {len(group_entities):3d} matches")
        print()

    # Fuzzy candidates
    if fuzzy_candidates:
        print('FUZZY MATCH CANDIDATES (Top 10):')
        print('-' * 80)

        for i, (e1, e2, score) in enumerate(fuzzy_candidates[:10], 1):
            name1 = e1.get('original_name', 'Unknown')
            name2 = e2.get('original_name', 'Unknown')
            location = e1.get('original_location') or 'Unknown'
            entity_type = e1.get('entity', {}).get('entity_type', 'unknown')

            print(f"  {i:2d}. [{entity_type:12s}] ({location:20s}) - {score:.2f}")
            print(f"      A: {name1}")
            print(f"      B: {name2}")
            print()

    print('=' * 80)


# =============================================================================
# Comprehensive Deduplication Orchestration (All 4 Tiers)
# =============================================================================


def deduplicate_entities(
    entities: List[Dict[str, Any]],
    entity_type: Optional[str] = None,
    auto_match_threshold: float = 0.90,
    llm_verify_threshold: float = 0.80,
    semantic_threshold: float = 0.87,
    llm_confidence_threshold: float = 0.70,
    save_audit_trail: bool = True,
    s3_storage: Optional[Any] = None,
    audit_s3_prefix: str = 'stage3-audit/'
) -> Dict[str, Any]:
    """
    Comprehensive entity deduplication using all 4 tiers.

    Orchestrates:
    - Tier 1: Exact matching (auto-match)
    - Tier 2: Fuzzy matching (>=0.90 auto-match, 0.80-0.89 LLM verify)
    - Tier 3: Semantic matching (>=0.87 LLM verify)
    - Tier 4: LLM verification for ambiguous cases

    Args:
        entities: List of entity dicts from stage3_loader
        entity_type: Optional filter by entity_type (e.g., 'attraction', 'restaurant')
        auto_match_threshold: Fuzzy threshold for auto-matching (default: 0.90)
        llm_verify_threshold: Fuzzy threshold for LLM verification (default: 0.80)
        semantic_threshold: Semantic threshold for LLM verification (default: 0.87)
        llm_confidence_threshold: Minimum LLM confidence to accept match (default: 0.70)
        save_audit_trail: If True, save audit trail to S3
        s3_storage: S3Storage instance (required if save_audit_trail=True)
        audit_s3_prefix: S3 prefix for audit trail files

    Returns:
        Dict containing:
            - entity_groups: {group_id: [entity1, entity2, ...]}
            - singleton_entities: [entities with no matches]
            - deduplication_stats: Statistics dict
            - audit_trail: List of match decisions

    Example:
        >>> from src.storage.s3 import S3Storage
        >>> from src.processors.stage3_loader import load_all_stage2_entities
        >>>
        >>> s3 = S3Storage()
        >>> result = load_all_stage2_entities(s3)
        >>>
        >>> # Deduplicate attractions only
        >>> attractions = [e for e in result['all_entities'] if e['entity']['entity_type'] == 'attraction']
        >>> dedup_result = deduplicate_entities(attractions, entity_type='attraction', s3_storage=s3)
        >>>
        >>> print(f"Input: {dedup_result['deduplication_stats']['total_input']} entities")
        >>> print(f"Groups: {dedup_result['deduplication_stats']['total_groups']}")
        >>> print(f"Singletons: {dedup_result['deduplication_stats']['singletons']}")
    """
    import json
    import uuid
    from datetime import datetime, timezone

    # Import tier modules
    from src.processors.embeddings import find_semantic_candidates
    from src.processors.llm_verification import batch_verify_matches

    logger.info("="*80)
    logger.info("COMPREHENSIVE ENTITY DEDUPLICATION")
    logger.info("="*80)

    # Filter by entity_type if specified
    if entity_type:
        entities = [e for e in entities if e.get('entity', {}).get('entity_type') == entity_type]
        logger.info(f"Filtered to {len(entities)} entities of type '{entity_type}'")
    else:
        logger.info(f"Processing {len(entities)} entities (all types)")

    if len(entities) == 0:
        logger.warning("No entities to deduplicate")
        return {
            'entity_groups': {},
            'singleton_entities': [],
            'deduplication_stats': {
                'total_input': 0,
                'total_groups': 0,
                'exact_matches': 0,
                'fuzzy_matches': 0,
                'semantic_matches': 0,
                'llm_verified': 0,
                'llm_rejected': 0,
                'singletons': 0,
                'deduplication_rate': 0.0
            },
            'audit_trail': []
        }

    # Initialize tracking
    entity_groups = {}  # {group_id: [entity1, entity2, ...]}
    entity_to_group = {}  # {entity_id: group_id}
    audit_trail = []
    stats = {
        'total_input': len(entities),
        'exact_matches': 0,
        'fuzzy_auto_matches': 0,
        'fuzzy_llm_verified': 0,
        'fuzzy_llm_rejected': 0,
        'semantic_llm_verified': 0,
        'semantic_llm_rejected': 0,
        'llm_verifications_total': 0
    }

    # Assign unique IDs to entities for tracking
    for i, entity in enumerate(entities):
        entity['_temp_id'] = i

    # =========================================================================
    # TIER 1: EXACT MATCHING
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("TIER 1: EXACT MATCHING")
    logger.info("="*80)

    exact_groups = group_exact_matches(entities)

    # Convert exact match groups to entity_groups format
    for group_id, group_entities in exact_groups.items():
        entity_groups[group_id] = group_entities
        for entity in group_entities:
            entity_to_group[entity['_temp_id']] = group_id

        # Add to audit trail
        entity_ids = [e['_temp_id'] for e in group_entities]
        audit_trail.append({
            'entity_ids': entity_ids,
            'entity_names': [e.get('original_name', 'Unknown') for e in group_entities],
            'method': 'exact',
            'tier': 1,
            'confidence': 1.0,
            'reasoning': 'Exact match (same normalized name, location, type)'
        })

    stats['exact_matches'] = sum(len(group) for group in exact_groups.values())

    logger.info(f"✅ Tier 1 complete: {len(exact_groups)} groups, {stats['exact_matches']} entities matched")

    # Get unmatched entities for next tiers
    unmatched_entities = [e for e in entities if e['_temp_id'] not in entity_to_group]
    logger.info(f"   Unmatched entities remaining: {len(unmatched_entities)}")

    # =========================================================================
    # TIER 2: FUZZY MATCHING
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("TIER 2: FUZZY MATCHING")
    logger.info("="*80)

    if len(unmatched_entities) > 1:
        # Find all fuzzy candidates above llm_verify_threshold
        fuzzy_candidates = find_fuzzy_candidates(
            unmatched_entities,
            threshold=llm_verify_threshold,
            exclude_exact_matches=True
        )

        # Split into auto-match and LLM-verify
        fuzzy_auto = [(e1, e2, score) for e1, e2, score in fuzzy_candidates if score >= auto_match_threshold]
        fuzzy_llm = [(e1, e2, score) for e1, e2, score in fuzzy_candidates if llm_verify_threshold <= score < auto_match_threshold]

        logger.info(f"   Fuzzy candidates (>={llm_verify_threshold:.2f}): {len(fuzzy_candidates)}")
        logger.info(f"   Auto-match (>={auto_match_threshold:.2f}): {len(fuzzy_auto)}")
        logger.info(f"   LLM-verify ({llm_verify_threshold:.2f}-{auto_match_threshold:.2f}): {len(fuzzy_llm)}")

        # Auto-match high-confidence fuzzy matches
        for e1, e2, score in fuzzy_auto:
            # Check if either entity is already in a group
            id1, id2 = e1['_temp_id'], e2['_temp_id']

            if id1 in entity_to_group and id2 in entity_to_group:
                # Both already in groups - skip (shouldn't happen with proper filtering)
                continue
            elif id1 in entity_to_group:
                # Add e2 to e1's group
                group_id = entity_to_group[id1]
                entity_groups[group_id].append(e2)
                entity_to_group[id2] = group_id
            elif id2 in entity_to_group:
                # Add e1 to e2's group
                group_id = entity_to_group[id2]
                entity_groups[group_id].append(e1)
                entity_to_group[id1] = group_id
            else:
                # Neither in a group - create new group
                group_id = f"fuzzy_auto_{uuid.uuid4().hex[:12]}"
                entity_groups[group_id] = [e1, e2]
                entity_to_group[id1] = group_id
                entity_to_group[id2] = group_id

            # Add to audit trail
            audit_trail.append({
                'entity_ids': [id1, id2],
                'entity_names': [e1.get('original_name'), e2.get('original_name')],
                'method': 'fuzzy_auto',
                'tier': 2,
                'confidence': score,
                'reasoning': 'High fuzzy similarity (auto-match)'
            })

            stats['fuzzy_auto_matches'] += 1

        # LLM-verify ambiguous fuzzy matches
        if len(fuzzy_llm) > 0:
            logger.info(f"\n   LLM-verifying {len(fuzzy_llm)} ambiguous fuzzy matches...")
            verified_fuzzy = batch_verify_matches(
                fuzzy_llm,
                confidence_threshold=llm_confidence_threshold,
                show_progress=True
            )

            stats['llm_verifications_total'] += len(fuzzy_llm)

            for match in verified_fuzzy:
                e1, e2 = match['entity1'], match['entity2']
                id1, id2 = e1['_temp_id'], e2['_temp_id']

                if match['is_match'] and match['confidence'] >= llm_confidence_threshold:
                    # LLM confirmed match
                    if id1 in entity_to_group and id2 in entity_to_group:
                        continue
                    elif id1 in entity_to_group:
                        group_id = entity_to_group[id1]
                        entity_groups[group_id].append(e2)
                        entity_to_group[id2] = group_id
                    elif id2 in entity_to_group:
                        group_id = entity_to_group[id2]
                        entity_groups[group_id].append(e1)
                        entity_to_group[id1] = group_id
                    else:
                        group_id = f"fuzzy_llm_{uuid.uuid4().hex[:12]}"
                        entity_groups[group_id] = [e1, e2]
                        entity_to_group[id1] = group_id
                        entity_to_group[id2] = group_id

                    stats['fuzzy_llm_verified'] += 1

                    audit_trail.append({
                        'entity_ids': [id1, id2],
                        'entity_names': [e1.get('original_name'), e2.get('original_name')],
                        'method': 'fuzzy_llm_verified',
                        'tier': 2,
                        'confidence': match['confidence'],
                        'fuzzy_score': match['similarity_score'],
                        'reasoning': match['reasoning']
                    })
                else:
                    # LLM rejected match
                    stats['fuzzy_llm_rejected'] += 1

                    audit_trail.append({
                        'entity_ids': [id1, id2],
                        'entity_names': [e1.get('original_name'), e2.get('original_name')],
                        'method': 'fuzzy_llm_rejected',
                        'tier': 2,
                        'confidence': match['confidence'],
                        'fuzzy_score': match['similarity_score'],
                        'reasoning': match['reasoning']
                    })

        logger.info("✅ Tier 2 complete:")
        logger.info(f"   Auto-matched: {stats['fuzzy_auto_matches']}")
        logger.info(f"   LLM-verified: {stats['fuzzy_llm_verified']}")
        logger.info(f"   LLM-rejected: {stats['fuzzy_llm_rejected']}")

    # Update unmatched entities
    unmatched_entities = [e for e in entities if e['_temp_id'] not in entity_to_group]
    logger.info(f"   Unmatched entities remaining: {len(unmatched_entities)}")

    # =========================================================================
    # TIER 3: SEMANTIC MATCHING
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("TIER 3: SEMANTIC MATCHING")
    logger.info("="*80)

    if len(unmatched_entities) > 1:
        # Get excluded pairs (already matched entities)
        excluded_pairs = []
        for group_entities in entity_groups.values():
            for i in range(len(group_entities)):
                for j in range(i + 1, len(group_entities)):
                    name1 = group_entities[i].get('normalized_name', '')
                    name2 = group_entities[j].get('normalized_name', '')
                    excluded_pairs.append((name1, name2))

        # Find semantic candidates
        semantic_candidates = find_semantic_candidates(
            unmatched_entities,
            threshold=semantic_threshold,
            exclude_matched_pairs=excluded_pairs,
            show_progress=True
        )

        logger.info(f"   Semantic candidates (>={semantic_threshold:.2f}): {len(semantic_candidates)}")

        # LLM-verify all semantic matches (semantic is less reliable than fuzzy)
        if len(semantic_candidates) > 0:
            logger.info(f"\n   LLM-verifying {len(semantic_candidates)} semantic matches...")
            verified_semantic = batch_verify_matches(
                semantic_candidates,
                confidence_threshold=llm_confidence_threshold,
                show_progress=True
            )

            stats['llm_verifications_total'] += len(semantic_candidates)

            for match in verified_semantic:
                e1, e2 = match['entity1'], match['entity2']
                id1, id2 = e1['_temp_id'], e2['_temp_id']

                if match['is_match'] and match['confidence'] >= llm_confidence_threshold:
                    # LLM confirmed match
                    if id1 in entity_to_group and id2 in entity_to_group:
                        continue
                    elif id1 in entity_to_group:
                        group_id = entity_to_group[id1]
                        entity_groups[group_id].append(e2)
                        entity_to_group[id2] = group_id
                    elif id2 in entity_to_group:
                        group_id = entity_to_group[id2]
                        entity_groups[group_id].append(e1)
                        entity_to_group[id1] = group_id
                    else:
                        group_id = f"semantic_{uuid.uuid4().hex[:12]}"
                        entity_groups[group_id] = [e1, e2]
                        entity_to_group[id1] = group_id
                        entity_to_group[id2] = group_id

                    stats['semantic_llm_verified'] += 1

                    audit_trail.append({
                        'entity_ids': [id1, id2],
                        'entity_names': [e1.get('original_name'), e2.get('original_name')],
                        'method': 'semantic_llm_verified',
                        'tier': 3,
                        'confidence': match['confidence'],
                        'semantic_score': match['similarity_score'],
                        'reasoning': match['reasoning']
                    })
                else:
                    # LLM rejected match
                    stats['semantic_llm_rejected'] += 1

                    audit_trail.append({
                        'entity_ids': [id1, id2],
                        'entity_names': [e1.get('original_name'), e2.get('original_name')],
                        'method': 'semantic_llm_rejected',
                        'tier': 3,
                        'confidence': match['confidence'],
                        'semantic_score': match['similarity_score'],
                        'reasoning': match['reasoning']
                    })

        logger.info("✅ Tier 3 complete:")
        logger.info(f"   LLM-verified: {stats['semantic_llm_verified']}")
        logger.info(f"   LLM-rejected: {stats['semantic_llm_rejected']}")

    # Get final singletons
    singleton_entities = [e for e in entities if e['_temp_id'] not in entity_to_group]

    # =========================================================================
    # FINAL STATISTICS
    # =========================================================================
    logger.info("\n" + "="*80)
    logger.info("DEDUPLICATION COMPLETE")
    logger.info("="*80)

    total_groups = len(entity_groups)
    total_singletons = len(singleton_entities)
    total_matched = sum(len(group) for group in entity_groups.values())
    deduplication_rate = (total_matched / len(entities)) * 100 if len(entities) > 0 else 0.0

    deduplication_stats = {
        'total_input': len(entities),
        'total_groups': total_groups,
        'exact_matches': stats['exact_matches'],
        'fuzzy_matches': stats['fuzzy_auto_matches'] + stats['fuzzy_llm_verified'],
        'fuzzy_auto_matches': stats['fuzzy_auto_matches'],
        'fuzzy_llm_verified': stats['fuzzy_llm_verified'],
        'fuzzy_llm_rejected': stats['fuzzy_llm_rejected'],
        'semantic_matches': stats['semantic_llm_verified'],
        'semantic_llm_verified': stats['semantic_llm_verified'],
        'semantic_llm_rejected': stats['semantic_llm_rejected'],
        'llm_verified_total': stats['fuzzy_llm_verified'] + stats['semantic_llm_verified'],
        'llm_rejected_total': stats['fuzzy_llm_rejected'] + stats['semantic_llm_rejected'],
        'llm_verifications_total': stats['llm_verifications_total'],
        'singletons': total_singletons,
        'deduplication_rate': deduplication_rate
    }

    logger.info(f"Input: {deduplication_stats['total_input']} entities")
    logger.info(f"Groups: {deduplication_stats['total_groups']}")
    logger.info(f"  - Exact matches: {deduplication_stats['exact_matches']} entities")
    logger.info(f"  - Fuzzy matches: {deduplication_stats['fuzzy_matches']} entities")
    logger.info(f"    - Auto: {deduplication_stats['fuzzy_auto_matches']}")
    logger.info(f"    - LLM verified: {deduplication_stats['fuzzy_llm_verified']}")
    logger.info(f"  - Semantic matches: {deduplication_stats['semantic_matches']} entities")
    logger.info(f"Singletons: {deduplication_stats['singletons']}")
    logger.info(f"Deduplication rate: {deduplication_stats['deduplication_rate']:.1f}%")
    logger.info(f"LLM verifications: {deduplication_stats['llm_verifications_total']}")
    logger.info(f"  - Confirmed: {deduplication_stats['llm_verified_total']}")
    logger.info(f"  - Rejected: {deduplication_stats['llm_rejected_total']}")

    # =========================================================================
    # SAVE AUDIT TRAIL
    # =========================================================================
    if save_audit_trail and s3_storage:
        logger.info("\n" + "="*80)
        logger.info("SAVING AUDIT TRAIL")
        logger.info("="*80)

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        entity_type_str = entity_type or 'all'
        audit_filename = f"deduplication_audit_{entity_type_str}_{timestamp}.json"
        audit_s3_key = f"{audit_s3_prefix}{audit_filename}"

        audit_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'entity_type': entity_type,
            'deduplication_stats': deduplication_stats,
            'audit_trail': audit_trail
        }

        try:
            audit_json = json.dumps(audit_data, indent=2)
            s3_storage.s3_client.put_object(
                Bucket=s3_storage.bucket_name,
                Key=audit_s3_key,
                Body=audit_json.encode('utf-8'),
                ContentType='application/json'
            )
            logger.info(f"✅ Audit trail saved to: s3://{s3_storage.bucket_name}/{audit_s3_key}")
        except Exception as e:
            logger.error(f"Failed to save audit trail to S3: {e}")

    # Clean up temp IDs
    for entity in entities:
        if '_temp_id' in entity:
            del entity['_temp_id']

    return {
        'entity_groups': entity_groups,
        'singleton_entities': singleton_entities,
        'deduplication_stats': deduplication_stats,
        'audit_trail': audit_trail
    }


# =============================================================================
# Testing and Validation
# =============================================================================


def test_deduplication_sample():
    """
    Test deduplication functions with sample entities.

    Can be run standalone to verify matching logic.
    """
    logger.info("Testing deduplication with sample entities...")

    # Create sample entities
    sample_entities = [
        {
            'normalized_name': 'wat pho',
            'original_name': 'Wat Pho',
            'normalized_location': 'bangkok',
            'original_location': 'Bangkok',
            'entity': {'entity_type': 'attraction'},
            'provenance': {'source_video_id': 'video1'}
        },
        {
            'normalized_name': 'wat pho',
            'original_name': 'Wat Pho Temple',
            'normalized_location': 'bangkok',
            'original_location': 'Bangkok',
            'entity': {'entity_type': 'attraction'},
            'provenance': {'source_video_id': 'video2'}
        },
        {
            'normalized_name': 'wat pho temple',
            'original_name': 'Wat Pho Temple',
            'normalized_location': 'bangkok',
            'original_location': 'Bangkok',
            'entity': {'entity_type': 'attraction'},
            'provenance': {'source_video_id': 'video3'}
        },
        {
            'normalized_name': 'grand palace',
            'original_name': 'Grand Palace',
            'normalized_location': 'bangkok',
            'original_location': 'Bangkok',
            'entity': {'entity_type': 'attraction'},
            'provenance': {'source_video_id': 'video4'}
        },
        {
            'normalized_name': 'the grand palace',
            'original_name': 'The Grand Palace',
            'normalized_location': 'bangkok',
            'original_location': 'Bangkok',
            'entity': {'entity_type': 'attraction'},
            'provenance': {'source_video_id': 'video5'}
        },
    ]

    # Test exact matching
    logger.info("\nTesting exact_match():")
    is_exact = exact_match(sample_entities[0], sample_entities[1])
    logger.info(f"  'Wat Pho' vs 'Wat Pho Temple': {is_exact} (expected: True)")

    is_exact = exact_match(sample_entities[0], sample_entities[2])
    logger.info(f"  'Wat Pho' vs 'Wat Pho Temple' (different normalized): {is_exact} (expected: False)")

    # Test fuzzy matching
    logger.info("\nTesting fuzzy_match():")
    similarity = fuzzy_match(sample_entities[0], sample_entities[2])
    logger.info(f"  'wat pho' vs 'wat pho temple': {similarity:.2f}")

    similarity = fuzzy_match(sample_entities[3], sample_entities[4])
    logger.info(f"  'grand palace' vs 'the grand palace': {similarity:.2f}")

    # Test grouping
    logger.info("\nTesting group_exact_matches():")
    groups = group_exact_matches(sample_entities)

    # Test fuzzy candidates
    logger.info("\nTesting find_fuzzy_candidates():")
    fuzzy_pairs = find_fuzzy_candidates(sample_entities, threshold=0.75)

    logger.info("\n✅ Deduplication test complete!")


if __name__ == '__main__':
    # Run tests
    test_deduplication_sample()
