#!/usr/bin/env python3
"""
Stage 3 Batch Processor - Complete Pipeline

Processes entities from Stage 2 (extracted) through Stage 3 (canonical entities with consensus + geocoding).

Pipeline Steps:
    1. Load Stage 2 entities from S3
    2. Deduplicate using 4-tier matching (exact, fuzzy, semantic, LLM verification)
    3. Canonicalize entity groups into single entities
    4a. Filter non-place entities (apps, services, generic categories)
    4b. Merge with existing entities (incremental mode)
    5. Calculate consensus data (ratings, profiles, themes with LLM)
    6. Enrich with temporal and logistics info
    7. Geocode entities (Google Maps with caching)
    8. Save canonical entities to S3
    9. Track costs and generate comprehensive summary

Usage:
    python cli/process_stage3.py [--limit N] [--entity-types TYPE1,TYPE2] [--log-level DEBUG]

Features:
    - 4-tier deduplication with LLM verification
    - LLM-based theme extraction (Gemini Flash)
    - Hybrid geocoding (Nominatim + Google Maps fallback)
    - Comprehensive cost tracking (LLM + geocoding)
    - Progress bars and detailed logging
    - S3 storage with multiple formats

Examples:
    # Process first 10 videos (testing)
    python cli/process_stage3.py --limit 10

    # Process all videos
    python cli/process_stage3.py

    # Process only attractions
    python cli/process_stage3.py --entity-types attraction

    # Process attractions and destinations
    python cli/process_stage3.py --entity-types attraction,destination

    # Enable debug logging
    python cli/process_stage3.py --limit 5 --log-level DEBUG

Cost Estimation:
    - LLM theme extraction: ~$0.000026 per entity (Gemini Flash)
    - Google Maps geocoding: $0.005 per entity (only if Nominatim fails)
    - Nominatim geocoding: FREE
    - Typical 1000 entities: ~$0.03 (mostly FREE with Nominatim)
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

import click
from sqlalchemy.orm import Session

from src.storage.stage3_storage import Stage3Storage

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
# Stage3Storage removed - using PostgreSQL only
from src.storage.entity_registry import EntityRegistry, dedupe_experiences
from src.storage.score_history import ScoreHistory
from src.processors.stage3_loader import load_all_stage2_entities
from src.processors.deduplication import deduplicate_entities
from src.processors.canonicalization import canonicalize_all_groups
from src.processors.entity_filter import filter_non_place_entities, log_filter_statistics
from src.processors.consensus import build_entity_consensus
from src.processors.entity_merger import merge_entity_complete
from src.utils.logging import get_logger, setup_logging
from src.utils.metadata_tracker import MetadataTracker
from src.utils.cost_tracker import CostTracker

# PostgreSQL imports (using core database module)
from src.database import SessionLocal
from cli.stage3_postgres_helpers import (
    load_extracted_entities_from_postgres,
    load_existing_canonical_entities,
    save_canonical_entities_to_postgres
)

logger = get_logger(__name__)


# =============================================================================
# Configuration Constants
# =============================================================================

# Deduplication thresholds
AUTO_MATCH_THRESHOLD = 0.90
LLM_VERIFY_THRESHOLD = 0.80
SEMANTIC_THRESHOLD = 0.85
LLM_CONFIDENCE_THRESHOLD = 0.7

# Geocoding thresholds
NOMINATIM_CONFIDENCE_THRESHOLD = 0.8
GEOCODING_MIN_SUCCESS_RATE = 50.0  # Warn if below this %

# Quality gates
MIN_ENTITIES_RATIO = 0.1  # Warn if canonical < 10% of input
MIN_TEMPORAL_COVERAGE = 30.0  # Warn if temporal info < 30%
MAX_RETRIES = 3  # Max retries for failed operations

# Performance settings
CONSENSUS_PARALLEL_WORKERS = 4
CONSENSUS_MIN_CONFIDENCE = 0.7  # Only run LLM theme extraction for high-confidence entities
CONSENSUS_MIN_EXPERIENCES = 3  # Require at least 3 experiences for theme extraction


# =============================================================================
# Helper Functions
# =============================================================================

def validate_coordinates(coords: Dict[str, Any]) -> bool:
    """
    Validate that coordinates are within valid ranges.

    Args:
        coords: Coordinates dictionary with latitude and longitude

    Returns:
        True if valid, False otherwise
    """
    if not coords:
        return False

    lat = coords.get('lat')
    lon = coords.get('lon')

    if lat is None or lon is None:
        return False

    try:
        lat = float(lat)
        lon = float(lon)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, TypeError):
        return False


def build_consensus_with_retry(entity: Dict[str, Any], max_retries: int = MAX_RETRIES) -> Dict[str, Any]:
    """
    Build consensus with retry logic for LLM failures.

    Args:
        entity: Entity to build consensus for
        max_retries: Maximum number of retry attempts

    Returns:
        Entity with consensus data
    """
    for attempt in range(max_retries):
        try:
            # Only run theme extraction for high-quality entities
            confidence = entity.get('confidence_score', 0)
            num_experiences = len(entity.get('experiences', []))

            if confidence >= CONSENSUS_MIN_CONFIDENCE and num_experiences >= CONSENSUS_MIN_EXPERIENCES:
                return build_entity_consensus(entity)
            else:
                # Skip LLM theme extraction for low-quality entities
                logger.debug(f"Skipping theme extraction for {entity.get('entity_id')} (confidence={confidence}, experiences={num_experiences})")
                return entity

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Consensus building failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Consensus building failed after {max_retries} attempts: {e}")
                # Return entity without consensus
                return entity

    return entity


def process_consensus_parallel(entities: List[Dict[str, Any]], max_workers: int = CONSENSUS_PARALLEL_WORKERS) -> List[Dict[str, Any]]:
    """
    Process consensus building in parallel for better performance.

    Args:
        entities: List of entities to process
        max_workers: Number of parallel workers

    Returns:
        List of entities with consensus data
    """
    if not entities:
        return []

    entities_with_consensus = []

    # Use ThreadPoolExecutor for I/O-bound LLM calls
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_entity = {
            executor.submit(build_consensus_with_retry, entity): entity
            for entity in entities
        }

        # Collect results as they complete
        for future in as_completed(future_to_entity):
            try:
                result = future.result()
                entities_with_consensus.append(result)
            except Exception as e:
                entity = future_to_entity[future]
                logger.error(f"Failed to process consensus for {entity.get('entity_id')}: {e}")
                # Add entity without consensus
                entities_with_consensus.append(entity)

    return entities_with_consensus


def validate_quality_gates(
    total_canonical_entities: int,
    total_input_entities: int,
    geocode_stats: Dict[str, Any],
    enrichment_stats: Dict[str, Any]
) -> List[str]:
    """
    Validate quality gates and return warnings.

    Args:
        total_canonical_entities: Number of canonical entities
        total_input_entities: Number of input entities
        geocode_stats: Geocoding statistics
        enrichment_stats: Enrichment statistics

    Returns:
        List of warning messages
    """
    warnings = []

    # Check entity count ratio
    if total_input_entities > 0:
        ratio = total_canonical_entities / total_input_entities
        if ratio < MIN_ENTITIES_RATIO:
            warnings.append(
                f"Very high deduplication rate ({(1-ratio)*100:.1f}%). "
                f"Only {total_canonical_entities} canonical entities from {total_input_entities} inputs. "
                "Verify deduplication thresholds are not too aggressive."
            )

    # Check if any entities were processed
    if total_canonical_entities == 0:
        warnings.append("No canonical entities generated - pipeline may have failed")

    # Check geocoding success rate
    success_rate = geocode_stats.get('success_rate', 0)
    if success_rate < GEOCODING_MIN_SUCCESS_RATE:
        warnings.append(
            f"Geocoding success rate very low: {success_rate:.1f}%. "
            "Consider investigating geocoding API issues."
        )

    # Check temporal info coverage
    temporal_coverage = enrichment_stats.get('enrichment_coverage', {}).get('temporal_info', {}).get('percentage', 0)
    if temporal_coverage < MIN_TEMPORAL_COVERAGE:
        warnings.append(
            f"Low temporal info coverage: {temporal_coverage:.1f}%. "
            "Review Stage 2 extraction quality."
        )

    return warnings


# =============================================================================
# S3 Save Function
# =============================================================================

# save_canonical_entities_to_s3 function removed - using PostgreSQL only


# =============================================================================
# Main Processing Function
# =============================================================================

def process_stage3(
    limit: Optional[int] = None,
    entity_types: Optional[List[str]] = None,
    mode: str = 'incremental',
    save_to_s3: bool = True,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Process Stage 3 pipeline: Load → Deduplicate → Canonicalize → Consensus.

    Args:
        limit: Limit number of videos to load (for testing)
        entity_types: List of entity types to process (default: all)
        mode: Processing mode - 'full' or 'incremental' (default: 'incremental')
        save_to_s3: Save canonical entities to S3 (default: True)
        use_cache: Use caches for LLM enrichment and geocoding (default: True)

    Returns:
        Dict with processing results

    Processing Modes:
        - 'full': Reprocess all Stage 2 entities from scratch
        - 'incremental': Load existing canonical entities, merge new data
    """
    # Track overall pipeline time
    pipeline_start = time.time()

    logger.info("=" * 80)
    logger.info("STAGE 3 PIPELINE: CANONICAL ENTITIES WITH CONSENSUS")
    logger.info("=" * 80)

    # Initialize cost tracker
    cost_tracker = CostTracker()
    logger.info("💰 Cost tracking initialized")

    # Initialize S3
    logger.info("\n📦 Step 1: Initializing S3...")
    s3 = S3Storage()

    # Initialize entity registry and load existing entities (for incremental mode)
    registry = EntityRegistry(s3_storage=s3)
    existing_entities_by_type: Dict[str, Dict[str, Dict[str, Any]]] = {}
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    if mode == 'incremental':
        logger.info("\n📋 Step 1b: Loading entity registry and existing canonical entities...")

        # Load or create registry
        registry_loaded = registry.load()

        if registry_loaded:
            logger.info(f"   Loaded registry with {len(registry.entities)} existing entities")
        else:
            logger.info("   No existing registry found, will build from existing canonical entities")

        # Load existing canonical entities from S3
        storage = Stage3Storage(s3)
        existing_canonical = storage.load_all_canonical_entities()

        if existing_canonical:
            logger.info(f"   Loaded {len(existing_canonical)} existing canonical entities")

            # Group by entity type
            for entity in existing_canonical:
                entity_type = entity.get('entity_type', 'unknown')
                if entity_type not in existing_entities_by_type:
                    existing_entities_by_type[entity_type] = {}
                existing_entities_by_type[entity_type][entity.get('entity_id')] = entity

            # Build registry from existing entities if not loaded
            if not registry_loaded:
                logger.info("   Building registry from existing entities...")
                import_stats = registry.build_from_existing_entities(existing_canonical)
                logger.info(f"   Registry built: {import_stats['registered']} entities registered")
        else:
            logger.info("   No existing canonical entities found, starting fresh")

        # Show registry stats
        reg_stats = registry.get_stats()
        logger.info(f"   Registry stats: {reg_stats['total_entities']} entities, "
                   f"{reg_stats['total_processed_videos']} processed videos")
    else:
        logger.info("\n📋 Mode: FULL reprocessing - ignoring existing entities")

    # Load Stage 2 entities from PostgreSQL
    logger.info(f"\n📥 Step 2: Loading Stage 2 entities from PostgreSQL{f' (limit: {limit} videos)' if limit else ''}...")

    # Initialize PostgreSQL session
    db = SessionLocal()

    try:
        load_result = load_extracted_entities_from_postgres(
            db=db,
            limit=limit,
            entity_types=entity_types
        )

        total_entities = load_result['statistics']['total_entities']
        total_videos = load_result['statistics']['total_videos']
        logger.info(f"✅ Loaded {total_entities} entities from {total_videos} videos")

        # Convert entities_by_video to by_type format for compatibility with existing pipeline
        # NOTE: Entities from PostgreSQL now have nested structure:
        # {
        #   'original_name': str,
        #   'normalized_name': str,
        #   'original_location': str,
        #   'normalized_location': str,
        #   'entity': { 'entity_type': str, ... },  # Nested!
        #   'provenance': { ... }  # Already set in loader
        # }
        by_type: Dict[str, List] = {}
        for video_id, entities in load_result['entities_by_video'].items():
            for entity in entities:
                # Get entity_type from nested entity dict
                entity_type = entity['entity']['entity_type']
                if entity_type not in by_type:
                    by_type[entity_type] = []

                # Provenance is already set in stage3_postgres_helpers.py
                by_type[entity_type].append(entity)

        # Update load_result with by_type format
        load_result['by_type'] = by_type

    except Exception as e:
        logger.error(f"Failed to load entities from PostgreSQL: {e}")
        db.close()
        raise

    # Incremental mode: Filter to only new (unprocessed) videos
    incremental_stats = {
        'total_videos_loaded': total_videos,
        'videos_already_processed': 0,
        'videos_to_process': total_videos,
        'entities_skipped': 0,
        'entities_to_process': total_entities,
        'entities_merged': 0,
        'entities_created': 0
    }

    if mode == 'incremental' and registry.processed_videos:
        logger.info("\n🔍 Step 2b: Filtering to new videos only...")

        # Filter entities by video - keep only unprocessed videos
        filtered_by_type: Dict[str, List] = {}
        videos_seen = set()
        videos_skipped = set()

        for entity_type, entities in load_result['by_type'].items():
            filtered_entities = []
            for entity_data in entities:
                # Get video ID from provenance
                provenance = entity_data.get('provenance', {})
                video_id = provenance.get('source_video_id') or provenance.get('content_id', '')

                videos_seen.add(video_id)

                if registry.is_video_processed(video_id):
                    videos_skipped.add(video_id)
                    incremental_stats['entities_skipped'] += 1
                else:
                    filtered_entities.append(entity_data)

            filtered_by_type[entity_type] = filtered_entities

        # Update load_result with filtered entities
        load_result['by_type'] = filtered_by_type

        # Recalculate totals
        total_entities = sum(len(entities) for entities in filtered_by_type.values())
        total_videos = len(videos_seen - videos_skipped)

        incremental_stats['videos_already_processed'] = len(videos_skipped)
        incremental_stats['videos_to_process'] = total_videos
        incremental_stats['entities_to_process'] = total_entities

        logger.info(f"   Videos already processed: {len(videos_skipped)}")
        logger.info(f"   Videos to process: {total_videos}")
        logger.info(f"   Entities to process: {total_entities}")

        if total_entities == 0:
            logger.info("\n✅ No new entities to process. All videos already processed.")
            return {
                'mode': 'incremental',
                'status': 'no_new_data',
                'incremental_stats': incremental_stats
            }

    # Determine which entity types to process
    available_types = list(load_result['by_type'].keys())
    if entity_types:
        types_to_process = [t for t in entity_types if t in available_types]
        if not types_to_process:
            logger.error(f"❌ None of the specified types {entity_types} are available. Available types: {available_types}")
            return {'error': 'No matching entity types found'}
    else:
        types_to_process = available_types

    logger.info(f"\n🔍 Processing entity types: {types_to_process}")

    # Process each entity type
    all_results = {}
    total_canonical_entities = 0
    total_consensus_calculated = 0

    for entity_type in types_to_process:
        entities = load_result['by_type'][entity_type]
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Processing {entity_type.upper()}: {len(entities)} entities")
        logger.info(f"{'=' * 80}")

        if len(entities) < 1:
            logger.warning(f"⚠️  No entities to process for type '{entity_type}'. Skipping.")
            continue

        # Deduplicate with error handling and timing
        logger.info(f"\n🔗 Step 3: Deduplicating {entity_type}s...")
        dedup_start = time.time()

        try:
            dedup_result = deduplicate_entities(
                entities=entities,
                entity_type=entity_type,
                auto_match_threshold=AUTO_MATCH_THRESHOLD,
                llm_verify_threshold=LLM_VERIFY_THRESHOLD,
                semantic_threshold=SEMANTIC_THRESHOLD,
                llm_confidence_threshold=LLM_CONFIDENCE_THRESHOLD,
                save_audit_trail=True,
                s3_storage=s3
            )

            entity_groups = dedup_result['entity_groups']
            singleton_entities = dedup_result['singleton_entities']
            dedup_stats = dedup_result['deduplication_stats']

            dedup_duration = time.time() - dedup_start

            logger.info(f"✅ Deduplication complete in {dedup_duration:.2f}s:")
            logger.info(f"   Input: {dedup_stats['total_input']} entities")
            logger.info(f"   Groups: {dedup_stats['total_groups']}")
            logger.info(f"   Singletons: {dedup_stats['singletons']}")
            logger.info(f"   Deduplication rate: {dedup_stats['deduplication_rate']:.1f}%")

            # Structured logging for monitoring
            logger.info(
                "deduplication_complete",
                extra={
                    'entity_type': entity_type,
                    'input_count': dedup_stats['total_input'],
                    'output_groups': dedup_stats['total_groups'],
                    'duration_seconds': dedup_duration,
                    'dedup_rate': dedup_stats['deduplication_rate']
                }
            )

        except Exception as e:
            logger.error(f"❌ Deduplication failed for {entity_type}: {e}", exc_info=True)
            logger.warning(f"Skipping {entity_type} and continuing with next entity type...")
            continue

        # Canonicalize with error handling and timing
        logger.info(f"\n✨ Step 4: Canonicalizing {entity_type}s...")
        canon_start = time.time()

        try:
            entity_groups_list = list(entity_groups.values())

            canon_result = canonicalize_all_groups(
                entity_groups=entity_groups_list,
                singleton_entities=singleton_entities,
                entity_type=entity_type,
                starting_sequence=1
            )

            canonical_entities = canon_result['canonical_entities']
            canon_stats = canon_result['statistics']

            canon_duration = time.time() - canon_start

            logger.info(f"✅ Canonicalization complete in {canon_duration:.2f}s:")
            logger.info(f"   Total canonical entities: {canon_stats['total_canonical_entities']}")
            logger.info(f"   From groups: {canon_stats['entities_from_groups']}")
            logger.info(f"   From singletons: {canon_stats['entities_from_singletons']}")
            logger.info(f"   Total mentions: {canon_stats['total_mentions']}")

            # Validate that we have entities
            if not canonical_entities:
                logger.error(f"❌ No canonical entities generated for {entity_type}")
                continue

        except Exception as e:
            logger.error(f"❌ Canonicalization failed for {entity_type}: {e}", exc_info=True)
            logger.warning(f"Skipping {entity_type} and continuing with next entity type...")
            continue

        # Filter non-place entities (apps, services, generic categories)
        logger.info(f"\n🔍 Step 4a: Filtering non-place entities for {entity_type}s...")
        filter_start = time.time()

        try:
            # NOTE: Quality validation disabled because geocoding happens later in Step 6
            # We only use pattern matching to filter non-places at this stage
            place_entities, filtered_entities, filter_stats = filter_non_place_entities(
                entities=canonical_entities,
                enable_quality_validation=False  # Geocoding hasn't happened yet!
            )

            filter_duration = time.time() - filter_start

            # Log filtering results
            logger.info(f"✅ Entity filtering complete in {filter_duration:.2f}s")
            log_filter_statistics(filter_stats)

            # Save filtered entities for insights pipeline (future use)
            if filtered_entities and save_to_s3:
                try:
                    filtered_path = f'stage3-canonical/filtered/filtered_{entity_type}_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.jsonl'
                    filtered_json = '\n'.join(json.dumps(e, default=str) for e in filtered_entities)
                    s3.s3_client.put_object(
                        Bucket=s3.bucket_name,
                        Key=filtered_path,
                        Body=filtered_json,
                        ContentType='application/jsonl'
                    )
                    logger.info(f"💾 Saved {len(filtered_entities)} filtered entities to {filtered_path}")
                except Exception as e:
                    logger.warning(f"Failed to save filtered entities: {e}")

            # Use only place entities for rest of pipeline
            canonical_entities = place_entities

            if not canonical_entities:
                logger.warning(f"⚠️  No place entities remaining after filtering for {entity_type}")
                logger.info(f"   All {filter_stats['total_input']} entities were filtered as non-places")
                continue

        except Exception as e:
            logger.error(f"❌ Entity filtering failed for {entity_type}: {e}", exc_info=True)
            logger.warning(f"Continuing with unfiltered entities...")

        # Incremental mode: Merge with existing entities
        if mode == 'incremental':
            logger.info(f"\n🔄 Step 4b: Merging with existing {entity_type}s...")
            merge_start = time.time()

            existing_type_entities = existing_entities_by_type.get(entity_type, {})
            merged_count = 0
            new_count = 0
            unchanged_count = 0

            final_canonical_entities = []
            processed_entity_ids = set()  # Track which existing entities we've touched

            for new_entity in canonical_entities:
                # Try to find matching existing entity via registry
                name = new_entity.get('canonical_name')
                city = new_entity.get('city') or new_entity.get('location') or 'unknown'
                aliases = new_entity.get('aliases', [])

                matched_id = registry.find_matching_entity(
                    name=name,
                    city=city,
                    entity_type=entity_type,
                    aliases=aliases
                )

                if matched_id and matched_id in existing_type_entities:
                    # Merge new experiences into existing entity with score recalculation
                    existing = existing_type_entities[matched_id]
                    merged_entity = merge_entity_complete(
                        existing_entity=existing,
                        new_experiences=new_entity.get('experiences', []),
                        new_video_ids=set(new_entity.get('source_video_ids', [])),
                        recalculate_scores=True  # Recalculate all derived scores
                    )

                    # Update aliases
                    existing_aliases = set(merged_entity.get('aliases', []))
                    for alias in aliases:
                        if alias != name:
                            existing_aliases.add(alias)
                    merged_entity['aliases'] = sorted(existing_aliases)

                    # Keep the existing entity ID
                    final_canonical_entities.append(merged_entity)
                    merged_count += 1
                    processed_entity_ids.add(matched_id)

                    # Update registry
                    registry.update_entity_metadata(
                        entity_id=matched_id,
                        new_aliases=aliases,
                        new_video_ids=new_entity.get('source_video_ids', []),
                        experience_count=len(merged_entity.get('experiences', []))
                    )

                    logger.debug(f"   Merged: {name} -> {matched_id}")
                else:
                    # Register as new entity with stable ID
                    new_entity_id = registry.register_new_entity(new_entity)
                    new_entity['entity_id'] = new_entity_id
                    final_canonical_entities.append(new_entity)
                    new_count += 1
                    processed_entity_ids.add(new_entity_id)

                    logger.debug(f"   New: {name} -> {new_entity_id}")

            # Add unchanged existing entities (entities that existed but weren't touched in this run)
            for entity_id, existing_entity in existing_type_entities.items():
                if entity_id not in processed_entity_ids:
                    final_canonical_entities.append(existing_entity)
                    unchanged_count += 1
                    logger.debug(f"   Unchanged: {existing_entity.get('canonical_name')} ({entity_id})")

            canonical_entities = final_canonical_entities

            merge_duration = time.time() - merge_start
            logger.info(f"✅ Merge complete in {merge_duration:.2f}s:")
            logger.info(f"   Merged with existing: {merged_count}")
            logger.info(f"   New entities: {new_count}")
            logger.info(f"   Unchanged entities: {unchanged_count}")
            logger.info(f"   Total entities: {len(canonical_entities)}")

            incremental_stats['entities_merged'] += merged_count
            incremental_stats['entities_created'] += new_count
        else:
            # Full mode: Register all entities in registry
            for entity in canonical_entities:
                entity_id = registry.register_new_entity(entity)
                entity['entity_id'] = entity_id

        # Calculate consensus with parallel processing and error handling
        logger.info(f"\n🎯 Step 5: Calculating consensus for {entity_type}s...")
        consensus_start = time.time()

        try:
            # Use parallel processing for consensus building
            entities_with_consensus = process_consensus_parallel(
                canonical_entities,
                max_workers=CONSENSUS_PARALLEL_WORKERS
            )

            # Count entities with consensus
            consensus_count = sum(
                1 for entity in entities_with_consensus
                if 'consensus' in entity
            )

            # Get theme extraction stats
            from src.processors.consensus import get_theme_extraction_stats
            theme_stats = get_theme_extraction_stats()

            consensus_duration = time.time() - consensus_start

            logger.info(f"✅ Consensus calculation complete in {consensus_duration:.2f}s:")
            logger.info(f"   Total entities: {len(entities_with_consensus)}")
            logger.info(f"   Entities with consensus: {consensus_count}")
            if theme_stats['total_tokens_used'] > 0:
                logger.info("   LLM theme extraction:")
                logger.info(f"     - Tokens used: {theme_stats['total_tokens_used']:,}")
                logger.info(f"     - Cost: ${theme_stats['total_cost_usd']:.6f}")

        except Exception as e:
            logger.error(f"❌ Consensus calculation failed for {entity_type}: {e}", exc_info=True)
            # Fallback: use entities without consensus
            entities_with_consensus = canonical_entities
            consensus_count = 0
            theme_stats = {'total_tokens_used': 0, 'total_cost_usd': 0.0}

        # Enrich entities with temporal/logistics/computed fields
        # Uses hybrid approach: transcript aggregation + LLM knowledge fallback
        logger.info(f"\n✨ Step 5.5: Enriching {entity_type}s with temporal & logistics data...")
        logger.info("   Using hybrid enrichment: transcript data + LLM knowledge fallback")
        enrich_start = time.time()

        try:
            from src.processors.stage3_enrichment import batch_enrich_entities, get_enrichment_statistics

            # batch_enrich_entities now returns (entities, stats) tuple
            entities_enriched, batch_stats = batch_enrich_entities(
                entities_with_consensus,
                use_llm_fallback=True,  # Enable LLM fallback for well-known entities
                min_fame_score=0.5,     # Only enrich entities with fame >= 0.5
                max_llm_enrichments=100,  # Cost control: max 100 LLM calls per batch
                use_cache=use_cache  # Pass cache control flag
            )

            # Get detailed enrichment stats
            enrichment_stats = get_enrichment_statistics(entities_enriched)

            enrich_duration = time.time() - enrich_start

            logger.info(f"✅ Enrichment complete in {enrich_duration:.2f}s:")
            logger.info(f"   Total entities: {enrichment_stats['total_entities']}")

            # Temporal info breakdown by source
            temporal_coverage = enrichment_stats['enrichment_coverage']['temporal_info']
            temporal_sources = temporal_coverage.get('sources', {})
            logger.info(f"   Temporal info: {temporal_coverage['count']} ({temporal_coverage['percentage']:.1f}%)")
            if temporal_sources:
                logger.info(f"     - Transcript: {temporal_sources.get('transcript_extracted', 0)}")
                logger.info(f"     - LLM: {temporal_sources.get('llm_inferred', 0)}")
                logger.info(f"     - Hybrid: {temporal_sources.get('hybrid', 0)}")
                logger.info(f"     - Avg confidence: {temporal_coverage.get('avg_confidence', 0):.2f}")

            # Logistics info breakdown by source
            logistics_coverage = enrichment_stats['enrichment_coverage']['logistics_info']
            logistics_sources = logistics_coverage.get('sources', {})
            logger.info(f"   Logistics info: {logistics_coverage['count']} ({logistics_coverage['percentage']:.1f}%)")
            if logistics_sources:
                logger.info(f"     - Transcript: {logistics_sources.get('transcript_extracted', 0)}")
                logger.info(f"     - LLM: {logistics_sources.get('llm_inferred', 0)}")
                logger.info(f"     - Hybrid: {logistics_sources.get('hybrid', 0)}")
                logger.info(f"     - Avg confidence: {logistics_coverage.get('avg_confidence', 0):.2f}")

            # Practical tips (LLM only)
            practical_tips_coverage = enrichment_stats['enrichment_coverage'].get('practical_tips', {})
            if practical_tips_coverage.get('count', 0) > 0:
                logger.info(f"   Practical tips (LLM): {practical_tips_coverage['count']} ({practical_tips_coverage['percentage']:.1f}%)")

            logger.info(f"   Avg popularity score: {enrichment_stats['average_scores']['popularity']:.3f}")
            logger.info(f"   Avg freshness score: {enrichment_stats['average_scores']['freshness']:.3f}")

            # LLM cost tracking
            if batch_stats.get('llm_cost_usd', 0) > 0:
                logger.info(f"   💰 LLM enrichment cost: ${batch_stats['llm_cost_usd']:.4f}")

        except Exception as e:
            logger.error(f"❌ Enrichment failed for {entity_type}: {e}", exc_info=True)
            # Fallback: use entities without enrichment
            entities_enriched = entities_with_consensus
            enrichment_stats = {
                'total_entities': len(entities_enriched),
                'enrichment_coverage': {
                    'temporal_info': {'count': 0, 'percentage': 0.0, 'sources': {}},
                    'logistics_info': {'count': 0, 'percentage': 0.0, 'sources': {}},
                    'practical_tips': {'count': 0, 'percentage': 0.0}
                },
                'average_scores': {'popularity': 0.0, 'freshness': 0.0}
            }

        # Geocode entities with error handling and coordinate validation
        # Using Google Maps ONLY (no Nominatim) for accuracy and global scalability
        logger.info(f"\n🌍 Step 6: Geocoding {entity_type}s (Google Maps)...")
        geocode_start = time.time()

        try:
            from src.processors.geolocation import batch_geocode_google_only

            # Prepare entities for geocoding (need canonical_name, location, entity_id)
            cache_file = f'data/geocode_cache_{entity_type}.json' if use_cache else None
            geocode_results = batch_geocode_google_only(
                entities=entities_enriched,
                cache_file=cache_file,
                fill_missing_locations=True  # Also reverse geocode to fill city/country
            )

            geocode_stats = geocode_results['statistics']
            geocoded_coords = geocode_results['results']

            # Add coordinates to entities with validation
            entities_with_coords = []
            invalid_coords_count = 0

            for entity in entities_enriched:
                entity_id = entity.get('entity_id')
                if entity_id in geocoded_coords:
                    coords = geocoded_coords[entity_id]
                    # VALIDATE coordinates before adding
                    if validate_coordinates(coords):
                        entity['coordinates'] = coords
                    else:
                        logger.warning(f"Invalid coordinates for {entity_id}: {coords}")
                        invalid_coords_count += 1
                entities_with_coords.append(entity)

            geocode_duration = time.time() - geocode_start

            logger.info(f"✅ Geocoding complete in {geocode_duration:.2f}s:")
            logger.info(f"   Total entities: {geocode_stats['total_entities']}")
            logger.info(f"   From cache: {geocode_stats['cached']}")
            logger.info(f"   Google Maps (new): {geocode_stats['geocoded']}")
            logger.info(f"   Skipped (generic): {geocode_stats['skipped_generic']}")
            logger.info(f"   Failed: {geocode_stats['failed']}")
            logger.info(f"   Success rate: {geocode_stats['success_rate']:.1f}%")
            if invalid_coords_count > 0:
                logger.warning(f"   ⚠️  Invalid coordinates filtered: {invalid_coords_count}")
            if geocode_stats.get('reverse_geocoded', 0) > 0:
                logger.info(f"   Reverse geocoded (city/country filled): {geocode_stats['reverse_geocoded']}")
            logger.info(f"   💰 Google Maps cost: ${geocode_stats['google_cost_usd']:.4f}")

        except Exception as e:
            logger.error(f"❌ Geocoding failed for {entity_type}: {e}", exc_info=True)
            # Fallback: continue without coordinates
            entities_with_coords = entities_enriched
            geocode_stats = {
                'total_entities': len(entities_enriched),
                'cached': 0,
                'geocoded': 0,
                'skipped_generic': 0,
                'failed': len(entities_enriched),
                'success_rate': 0.0,
                'google_cost_usd': 0.0
            }

        # Save to PostgreSQL
        if save_to_s3:  # Keep parameter name for compatibility
            logger.info(f"\n💾 Step 7: Saving canonical {entity_type}s to PostgreSQL...")

            # Get video IDs from this batch
            video_ids_for_type = set()
            for entity in entities_with_coords:
                for exp in entity.get('experiences', []):
                    video_ids_for_type.add(exp.get('video_id'))

            try:
                save_result = save_canonical_entities_to_postgres(
                    db=db,
                    canonical_entities=entities_with_coords,
                    video_ids=list(video_ids_for_type)
                )

                logger.info(f"✅ Saved {save_result['total']} canonical entities to PostgreSQL "
                          f"({save_result['saved']} new, {save_result['updated']} updated, "
                          f"{save_result['experiences']} experiences)")

            except Exception as e:
                logger.error(f"❌ Failed to save {entity_type} entities to PostgreSQL: {e}")

        # Store results
        all_results[entity_type] = {
            'dedup_result': dedup_result,
            'canon_result': canon_result,
            'entities_final': entities_with_coords,
            'consensus_count': consensus_count,
            'geocode_stats': geocode_stats,
            'enrichment_stats': enrichment_stats
        }

        total_canonical_entities += len(entities_with_coords)
        total_consensus_calculated += consensus_count

    # Calculate total geocoding stats
    total_geocoded = 0
    total_cached = 0
    total_newly_geocoded = 0
    total_geocode_failed = 0
    total_google_cost = 0.0
    overall_enrichment_stats = None

    for entity_type, results in all_results.items():
        geocode_stats = results.get('geocode_stats', {})
        # batch_geocode_google_only returns: 'cached', 'geocoded', 'failed', 'google_cost_usd'
        total_cached += geocode_stats.get('cached', 0)
        total_newly_geocoded += geocode_stats.get('geocoded', 0)
        total_geocoded += geocode_stats.get('cached', 0) + geocode_stats.get('geocoded', 0)
        total_geocode_failed += geocode_stats.get('failed', 0)
        total_google_cost += geocode_stats.get('google_cost_usd', 0.0)

    # Get overall enrichment stats (use last entity type as representative)
    if all_results:
        last_result = list(all_results.values())[-1]
        overall_enrichment_stats = last_result.get('enrichment_stats', {})

    # QUALITY GATES: Validate processing quality
    logger.info("\n🔍 Running quality gate checks...")
    quality_warnings = validate_quality_gates(
        total_canonical_entities=total_canonical_entities,
        total_input_entities=total_entities,
        geocode_stats={
            'success_rate': (total_geocoded / total_canonical_entities * 100) if total_canonical_entities > 0 else 0
        },
        enrichment_stats=overall_enrichment_stats or {}
    )

    if quality_warnings:
        logger.warning(f"\n⚠️  Quality Gate Warnings ({len(quality_warnings)} issues found):")
        for warning in quality_warnings:
            logger.warning(f"   • {warning}")
    else:
        logger.info("✅ All quality gates passed")

    # Get theme extraction costs
    from src.processors.consensus import get_theme_extraction_stats
    theme_stats = get_theme_extraction_stats()

    # Consolidate costs into cost tracker
    logger.info("\n💰 Consolidating cost tracking...")

    # Add LLM costs from theme extraction
    if theme_stats['total_tokens_used'] > 0:
        # Approximate input/output split (theme extraction is mostly output)
        estimated_input = int(theme_stats['total_tokens_used'] * 0.3)
        estimated_output = int(theme_stats['total_tokens_used'] * 0.7)
        # Get model from config or default to gemini-2.5-flash-lite
        model = theme_stats.get('model', 'gemini-2.5-flash-lite')
        cost_tracker.track_llm_call(estimated_input, estimated_output, model)

    # Add geocoding costs (only Google Maps is used now)
    if total_newly_geocoded > 0:
        cost_tracker.track_geocoding('google', total_newly_geocoded)

    # Save cost report to file
    cost_report_path = f'data/cost_reports/stage3_cost_report_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.json'
    cost_tracker.save_cost_report(cost_report_path)

    # Mark processed videos and save registry
    logger.info("\n📋 Saving entity registry...")
    try:
        # Collect all canonical entities to track video-entity mappings
        all_canonical_entities = []
        for entity_type, results in all_results.items():
            all_canonical_entities.extend(results.get('entities_final', []))

        # Mark videos as processed
        for entity in all_canonical_entities:
            entity_id = entity.get('entity_id')
            for video_id in entity.get('source_video_ids', []):
                if not registry.is_video_processed(video_id):
                    registry.mark_video_processed(
                        video_id=video_id,
                        run_id=run_id,
                        entity_ids=[entity_id]
                    )

        # Save registry to S3 and local cache
        registry.save()
        reg_stats = registry.get_stats()
        logger.info(f"✅ Registry saved: {reg_stats['total_entities']} entities, "
                   f"{reg_stats['total_processed_videos']} processed videos")
    except Exception as e:
        logger.warning(f"⚠️  Failed to save registry: {e}")

    # Record score history for trend tracking (Phase 5)
    logger.info("\n📊 Recording score history...")
    try:
        score_history = ScoreHistory(s3_storage=s3)
        history_stats = score_history.batch_record_scores(
            entities=all_canonical_entities,
            run_id=run_id
        )
        logger.info(f"✅ Score history recorded: {history_stats['recorded']}/{history_stats['total']} entities")
    except Exception as e:
        logger.warning(f"⚠️  Failed to record score history: {e}")

    # Calculate total pipeline duration
    pipeline_duration = time.time() - pipeline_start

    # Get final cost report
    cost_report = cost_tracker.get_cost_report()

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3 PIPELINE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"⏱️  TOTAL TIME: {pipeline_duration:.2f}s ({pipeline_duration/60:.1f} minutes)")
    logger.info(f"🔄 MODE: {mode.upper()}")
    logger.info("\n📥 INPUT:")
    logger.info(f"   Loaded {incremental_stats['total_videos_loaded']} videos total")
    if mode == 'incremental':
        logger.info(f"   Already processed: {incremental_stats['videos_already_processed']} videos")
        logger.info(f"   New to process: {incremental_stats['videos_to_process']} videos")
    logger.info(f"   Entities processed: {total_entities}")
    logger.info("\n📊 PROCESSING:")
    logger.info(f"   Processed {len(types_to_process)} entity types: {types_to_process}")
    if mode == 'incremental':
        logger.info(f"   Merged with existing: {incremental_stats['entities_merged']} entities")
        logger.info(f"   Created new: {incremental_stats['entities_created']} entities")
    logger.info("\n📤 OUTPUT:")
    logger.info(f"   Total canonical entities: {total_canonical_entities}")
    logger.info(f"   Calculated consensus for {total_consensus_calculated} entities")
    logger.info("\n🌍 GEOLOCATION:")
    logger.info(f"   Successfully geocoded: {total_geocoded}/{total_canonical_entities} ({total_geocoded/total_canonical_entities*100 if total_canonical_entities > 0 else 0:.1f}%)")
    logger.info(f"   Cached (from previous runs): {total_cached}")
    logger.info(f"   Newly geocoded (Google Maps): {total_newly_geocoded}")
    logger.info(f"   Failed: {total_geocode_failed}")
    if save_to_s3:
        logger.info("\n💾 STORAGE:")
        logger.info(f"   Saved all canonical entities to S3")
        logger.info(f"   Cost report saved to: {cost_report_path}")
    logger.info("=" * 80)

    # Structured logging for monitoring dashboards
    logger.info(
        "stage3_pipeline_complete",
        extra={
            'duration_seconds': pipeline_duration,
            'total_input_entities': total_entities,
            'total_canonical_entities': total_canonical_entities,
            'geocoding_success_rate': (total_geocoded / total_canonical_entities * 100) if total_canonical_entities > 0 else 0,
            'consensus_count': total_consensus_calculated,
            'entity_types_processed': len(types_to_process),
            'total_cost_usd': cost_report.get('grand_total', 0.0)
        }
    )

    # Print detailed cost report
    cost_tracker.print_cost_report()

    # Check budget warning
    cost_tracker.check_budget_warning(budget_usd=5.0)  # Warn if over $5

    # Update metadata tracker with Stage 3 completion (BATCH OPTIMIZED)
    logger.info("\n📊 Updating metadata tracker...")
    metadata_update_start = time.time()

    try:
        tracker = MetadataTracker(s3)

        # Build mappings from canonical entities back to source videos
        # Structure: video_id -> {canonical_entity_ids: [...], stage2_to_canonical: {...}}
        video_mappings = {}

        # Collect all canonical entities across all types
        all_canonical_entities = []
        for entity_type, results in all_results.items():
            all_canonical_entities.extend(results.get('entities_final', []))

        # For each canonical entity, trace back to source videos
        for canonical_entity in all_canonical_entities:
            entity_id = canonical_entity.get('entity_id')
            experiences = canonical_entity.get('experiences', [])

            # Group experiences by video_id
            for exp in experiences:
                # Get video_id from experience metadata
                video_id = exp.get('video_id') or exp.get('source_video_id')
                stage2_entity_id = exp.get('entity_id')  # Original Stage 2 entity ID

                if video_id:
                    # Initialize video mapping if not exists
                    if video_id not in video_mappings:
                        video_mappings[video_id] = {
                            'canonical_entity_ids': set(),
                            'stage2_to_canonical': {}
                        }

                    # Add canonical entity ID
                    video_mappings[video_id]['canonical_entity_ids'].add(entity_id)

                    # Add Stage 2 -> canonical mapping
                    if stage2_entity_id:
                        video_mappings[video_id]['stage2_to_canonical'][stage2_entity_id] = entity_id

        # Calculate overall deduplication rate
        total_stage2_entities = sum(len(mapping['stage2_to_canonical']) for mapping in video_mappings.values())
        dedup_rate = (1 - (total_canonical_entities / total_stage2_entities)) if total_stage2_entities > 0 else 0.0

        # BATCH UPDATE: Process all videos in memory, save once
        videos_updated = 0
        videos_skipped = 0

        for video_id, mapping in video_mappings.items():
            if not tracker.content_exists(video_id):
                logger.warning(f"Video {video_id} not found in tracker, skipping")
                videos_skipped += 1
                continue

            # Start Stage 3 tracking
            tracker.start_stage(
                content_id=video_id,
                stage='stage_3_deduplicate'
            )

            # Convert sets to lists for JSON serialization
            canonical_ids_list = sorted(list(mapping['canonical_entity_ids']))

            # Prepare Stage 3 metadata
            stage3_metadata = {
                'canonical_entity_ids': canonical_ids_list,
                'total_entities_contributed': len(mapping['stage2_to_canonical']),
                'deduplication_rate': dedup_rate,
                'stage3_to_canonical_mapping': mapping['stage2_to_canonical']
            }

            # Mark Stage 3 as complete
            tracker.complete_stage(
                content_id=video_id,
                stage='stage_3_deduplicate',
                s3_paths=[
                    f"s3://{s3.bucket_name}/stage3-canonical/entities_all_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
                ],
                metadata=stage3_metadata
            )
            videos_updated += 1

        # BATCH SAVE: Single S3 write for all updates
        tracker.save_to_s3()

        metadata_update_duration = time.time() - metadata_update_start

        logger.info(f"✅ Updated metadata tracker for {videos_updated} videos in {metadata_update_duration:.2f}s")
        if videos_skipped > 0:
            logger.warning(f"   ⚠️  Skipped {videos_skipped} videos not found in tracker")

    except Exception as e:
        logger.error(f"❌ Failed to update metadata tracker: {e}", exc_info=True)
        # Don't fail entire pipeline for metadata update failure
        logger.warning("Continuing despite metadata update failure...")

    # Move processed Stage 2 files to stage3_extracted folder with transaction safety
    # IMPORTANT: Only move files if ALL processing succeeded
    logger.info("\n📦 Moving processed Stage 2 files to stage3_extracted folder...")

    # Check if we should move files (only if entities were successfully processed)
    should_move_files = (
        total_canonical_entities > 0 and
        save_to_s3 and
        all_results  # At least one entity type processed successfully
    )

    if not should_move_files:
        logger.warning("⚠️  Skipping file moves - processing incomplete or failed")
    else:
        file_move_start = time.time()

        try:
            processed_files = []
            failed_moves = []
            files_to_move = []

            # Get all source file paths from by_video
            by_video = load_result.get('by_video', {})

            # STEP 1: Build list of files to move (validation phase)
            for video_id, video_data in by_video.items():
                source_file_path = video_data.get('source_file_path')
                if source_file_path and '/stage2-extracted/new/' in source_file_path:
                    filename = source_file_path.split('/stage2-extracted/new/')[-1]
                    dest_file_path = source_file_path.replace(
                        '/stage2-extracted/new/',
                        '/stage2-extracted/stage3_extracted/'
                    )
                    files_to_move.append({
                        'video_id': video_id,
                        'source': source_file_path,
                        'dest': dest_file_path,
                        'filename': filename
                    })

            logger.info(f"   Planning to move {len(files_to_move)} files...")

            # STEP 2: Move files one by one with error tracking
            for file_info in files_to_move:
                try:
                    success = s3.move_file(
                        file_info['source'],
                        file_info['dest'],
                        delete_source=True
                    )

                    if success:
                        processed_files.append(file_info['filename'])
                    else:
                        failed_moves.append(file_info['filename'])
                        logger.error(f"Failed to move {file_info['filename']}")

                except Exception as move_error:
                    logger.error(f"Error moving {file_info['filename']}: {move_error}")
                    failed_moves.append(file_info['filename'])

            file_move_duration = time.time() - file_move_start

            logger.info(f"✅ Successfully moved {len(processed_files)}/{len(files_to_move)} files in {file_move_duration:.2f}s")

            if failed_moves:
                logger.warning(f"⚠️  Failed to move {len(failed_moves)} files:")
                for failed_file in failed_moves[:10]:  # Show first 10
                    logger.warning(f"   • {failed_file}")
                if len(failed_moves) > 10:
                    logger.warning(f"   ... and {len(failed_moves) - 10} more")

                # Log files that need manual intervention
                logger.warning("\n⚠️  MANUAL INTERVENTION REQUIRED:")
                logger.warning("   The following files were processed but not moved.")
                logger.warning("   They will be reprocessed on next run if not moved manually.")

        except Exception as e:
            logger.error(f"❌ Failed to move Stage 2 files: {e}", exc_info=True)
            logger.warning("   Files remain in stage2-extracted/new/ and may be reprocessed")
            # Don't fail entire pipeline for file move failure

    # Close database session
    db.close()

    return {
        'load_result': load_result,
        'results_by_type': all_results,
        'total_canonical_entities': total_canonical_entities,
        'total_consensus_calculated': total_consensus_calculated,
        'total_geocoded': total_geocoded,
        'geocoding_success_rate': total_geocoded/total_canonical_entities*100 if total_canonical_entities > 0 else 0,
        'total_cost_usd': cost_report['grand_total'],
        'cost_report': cost_report,
        'cost_report_path': cost_report_path
    }


# =============================================================================
# CLI Interface
# =============================================================================

@click.command()
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Limit number of videos to load (for testing). Default: process all videos'
)
@click.option(
    '--entity-types',
    type=str,
    default=None,
    help='Comma-separated list of entity types to process (e.g., attraction,destination). Default: all types'
)
@click.option(
    '--mode',
    type=click.Choice(['full', 'incremental'], case_sensitive=False),
    default='incremental',
    help='Processing mode: "full" reprocesses all entities, "incremental" (default) merges new data with existing'
)
@click.option(
    '--no-save',
    is_flag=True,
    default=False,
    help='Do not save canonical entities to S3 (for testing)'
)
@click.option(
    '--no-cache',
    is_flag=True,
    default=False,
    help='Bypass all caches (LLM enrichment, geocoding) for fresh processing'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Logging level. Default: INFO'
)
def main(limit, entity_types, mode, no_save, no_cache, log_level):
    """
    Process Stage 3: Entity Deduplication, Canonicalization & Consensus.

    This command processes Stage 2 entities through the complete Stage 3 pipeline:
    1. Load Stage 2 entities from S3
    2. Deduplicate entities (4-tier matching)
    3. Canonicalize entity groups
    4. Calculate consensus data
    5. Save canonical entities to S3

    Processing Modes:
    - incremental (default): Only process new videos, merge with existing entities
    - full: Reprocess all entities from scratch (ignores existing canonical entities)

    Examples:

        # Process first 10 videos (testing)
        python cli/process_stage3.py --limit 10

        # Incremental processing (default - merge new with existing)
        python cli/process_stage3.py

        # Full reprocessing (recreate all entities)
        python cli/process_stage3.py --mode full

        # Process only attractions
        python cli/process_stage3.py --entity-types attraction
    """
    # Setup logging
    setup_logging(log_level=log_level)

    # Parse entity types
    entity_types_list = None
    if entity_types:
        entity_types_list = [t.strip() for t in entity_types.split(',')]

    try:
        # Log mode and cache status
        logger.info(f"🔄 Processing mode: {mode.upper()}")
        if no_cache:
            logger.info("🔄 Cache disabled - all entities will be processed fresh")

        # Run Stage 3 pipeline
        result = process_stage3(
            limit=limit,
            entity_types=entity_types_list,
            mode=mode,
            save_to_s3=not no_save,
            use_cache=not no_cache
        )

        if 'error' in result:
            logger.error(f"❌ Stage 3 processing failed: {result['error']}")
            sys.exit(1)

        logger.info("\n✅ Stage 3 processing complete!")
        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Processing interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
