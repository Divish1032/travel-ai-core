#!/usr/bin/env python3
"""
Stage 3 Batch Processor - Complete Pipeline

Processes entities from Stage 2 (extracted) through Stage 3 (canonical entities with consensus + geocoding).

Pipeline Steps:
    1. Load Stage 2 entities from S3
    2. Deduplicate using 4-tier matching (exact, fuzzy, semantic, LLM verification)
    3. Canonicalize entity groups into single entities
    4. Calculate consensus data (ratings, profiles, themes with LLM)
    5. Geocode entities (Nominatim FREE + Google Maps fallback)
    6. Save canonical entities to S3
    7. Track costs and generate comprehensive summary

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
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.processors.stage3_loader import load_all_stage2_entities
from src.processors.deduplication import deduplicate_entities
from src.processors.canonicalization import canonicalize_all_groups
from src.processors.consensus import build_entity_consensus
from src.utils.logging import get_logger, setup_logging
from src.utils.metadata_tracker import MetadataTracker
from src.utils.cost_tracker import CostTracker

logger = get_logger(__name__)


# =============================================================================
# S3 Save Function
# =============================================================================

def save_canonical_entities_to_s3(
    s3_storage: S3Storage,
    canonical_entities: List[Dict[str, Any]],
    processing_date: str,
    dedup_stats: Optional[Dict[str, Any]] = None,
    geocode_stats: Optional[Dict[str, Any]] = None,
    theme_stats: Optional[Dict[str, Any]] = None,
    enrichment_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Save canonical entities to S3 in multiple formats using Stage3Storage.

    Creates:
    - entities_all.jsonl (all entities)
    - by_city/{city}.jsonl (grouped by city)
    - by_type/{type}.jsonl (grouped by entity type)
    - metadata/processing_stats.json (processing statistics)

    Args:
        s3_storage: S3Storage instance
        canonical_entities: List of canonical entities with consensus
        processing_date: Processing date (YYYY-MM-DD)
        dedup_stats: Deduplication statistics
        geocode_stats: Geocoding statistics
        theme_stats: Theme extraction statistics
        enrichment_stats: Enrichment statistics (temporal, logistics, computed fields)

    Returns:
        Dict with save results
    """
    # Initialize Stage3Storage
    storage = Stage3Storage(s3_storage)

    # Build cost stats
    cost_stats = {}
    if theme_stats:
        cost_stats['llm_theme_extraction'] = {
            'tokens': theme_stats.get('total_tokens_used', 0),
            'cost_usd': theme_stats.get('total_cost_usd', 0.0)
        }
    if geocode_stats:
        cost_stats['google_maps_geocoding'] = {
            'requests': geocode_stats.get('google', 0),
            'cost_usd': geocode_stats.get('google_cost_usd', 0.0)
        }

    # Calculate total cost
    total_cost = sum(
        stat.get('cost_usd', 0.0)
        for stat in cost_stats.values()
    )
    cost_stats['total_cost_usd'] = total_cost

    # Save in all formats
    result = storage.save_canonical_entities(
        entities=canonical_entities,
        processing_date=processing_date,
        dedup_stats=dedup_stats,
        geocode_stats=geocode_stats,
        cost_stats=cost_stats
    )

    return result


# =============================================================================
# Main Processing Function
# =============================================================================

def process_stage3(
    limit: Optional[int] = None,
    entity_types: Optional[List[str]] = None,
    save_to_s3: bool = True
) -> Dict[str, Any]:
    """
    Process Stage 3 pipeline: Load → Deduplicate → Canonicalize → Consensus.

    Args:
        limit: Limit number of videos to load (for testing)
        entity_types: List of entity types to process (default: all)
        save_to_s3: Save canonical entities to S3 (default: True)

    Returns:
        Dict with processing results
    """
    logger.info("=" * 80)
    logger.info("STAGE 3 PIPELINE: CANONICAL ENTITIES WITH CONSENSUS")
    logger.info("=" * 80)

    # Initialize cost tracker
    cost_tracker = CostTracker()
    logger.info("💰 Cost tracking initialized")

    # Initialize S3
    logger.info("\n📦 Step 1: Initializing S3...")
    s3 = S3Storage()

    # Load Stage 2 entities
    logger.info(f"\n📥 Step 2: Loading Stage 2 entities{f' (limit: {limit} videos)' if limit else ''}...")
    load_result = load_all_stage2_entities(
        s3_storage=s3,
        prefix='stage2-extracted/new/',
        limit=limit,
        show_progress=True
    )

    total_entities = load_result['statistics']['total_entities']
    total_videos = load_result['statistics']['total_videos']
    logger.info(f"✅ Loaded {total_entities} entities from {total_videos} videos")

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

        # Deduplicate
        logger.info(f"\n🔗 Step 3: Deduplicating {entity_type}s...")
        dedup_result = deduplicate_entities(
            entities=entities,
            entity_type=entity_type,
            auto_match_threshold=0.90,
            llm_verify_threshold=0.80,
            semantic_threshold=0.85,
            llm_confidence_threshold=0.7,
            save_audit_trail=True,
            s3_storage=s3
        )

        entity_groups = dedup_result['entity_groups']
        singleton_entities = dedup_result['singleton_entities']
        dedup_stats = dedup_result['deduplication_stats']

        logger.info(f"✅ Deduplication complete:")
        logger.info(f"   Input: {dedup_stats['total_input']} entities")
        logger.info(f"   Groups: {dedup_stats['total_groups']}")
        logger.info(f"   Singletons: {dedup_stats['singletons']}")
        logger.info(f"   Deduplication rate: {dedup_stats['deduplication_rate']:.1f}%")

        # Canonicalize
        logger.info(f"\n✨ Step 4: Canonicalizing {entity_type}s...")
        entity_groups_list = list(entity_groups.values())

        canon_result = canonicalize_all_groups(
            entity_groups=entity_groups_list,
            singleton_entities=singleton_entities,
            entity_type=entity_type,
            starting_sequence=1
        )

        canonical_entities = canon_result['canonical_entities']
        canon_stats = canon_result['statistics']

        logger.info(f"✅ Canonicalization complete:")
        logger.info(f"   Total canonical entities: {canon_stats['total_canonical_entities']}")
        logger.info(f"   From groups: {canon_stats['entities_from_groups']}")
        logger.info(f"   From singletons: {canon_stats['entities_from_singletons']}")
        logger.info(f"   Total mentions: {canon_stats['total_mentions']}")

        # Calculate consensus
        logger.info(f"\n🎯 Step 5: Calculating consensus for {entity_type}s...")
        entities_with_consensus = []
        consensus_count = 0

        for entity in canonical_entities:
            if entity.get('experiences') and len(entity['experiences']) > 0:
                entity_with_consensus = build_entity_consensus(entity)
                entities_with_consensus.append(entity_with_consensus)
                if 'consensus' in entity_with_consensus:
                    consensus_count += 1
            else:
                entities_with_consensus.append(entity)

        # Get theme extraction stats
        from src.processors.consensus import get_theme_extraction_stats
        theme_stats = get_theme_extraction_stats()

        logger.info(f"✅ Consensus calculation complete:")
        logger.info(f"   Total entities: {len(entities_with_consensus)}")
        logger.info(f"   Entities with consensus: {consensus_count}")
        if theme_stats['total_tokens_used'] > 0:
            logger.info(f"   LLM theme extraction:")
            logger.info(f"     - Tokens used: {theme_stats['total_tokens_used']:,}")
            logger.info(f"     - Cost: ${theme_stats['total_cost_usd']:.6f}")

        # Enrich entities with temporal/logistics/computed fields
        logger.info(f"\n✨ Step 5.5: Enriching {entity_type}s with temporal & logistics data...")
        from src.processors.stage3_enrichment import batch_enrich_entities, get_enrichment_statistics

        entities_enriched = batch_enrich_entities(entities_with_consensus)

        # Get enrichment stats
        enrichment_stats = get_enrichment_statistics(entities_enriched)
        logger.info(f"✅ Enrichment complete:")
        logger.info(f"   Total entities: {enrichment_stats['total_entities']}")
        logger.info(f"   With temporal info: {enrichment_stats['enrichment_coverage']['temporal_info']['count']} ({enrichment_stats['enrichment_coverage']['temporal_info']['percentage']:.1f}%)")
        logger.info(f"   With logistics info: {enrichment_stats['enrichment_coverage']['logistics_info']['count']} ({enrichment_stats['enrichment_coverage']['logistics_info']['percentage']:.1f}%)")
        logger.info(f"   Avg popularity score: {enrichment_stats['average_scores']['popularity']:.3f}")
        logger.info(f"   Avg freshness score: {enrichment_stats['average_scores']['freshness']:.3f}")

        # Geocode entities
        logger.info(f"\n🌍 Step 6: Geocoding {entity_type}s...")
        from src.processors.geolocation import batch_geocode_hybrid, get_google_maps_cost_stats

        # Prepare entities for geocoding (need canonical_name, location, entity_id)
        geocode_results = batch_geocode_hybrid(
            entities=entities_enriched,
            cache_file=f'data/geocode_cache_{entity_type}.json',
            nominatim_confidence_threshold=0.8,
            validate=True
        )

        geocode_stats = geocode_results['statistics']
        geocoded_coords = geocode_results['results']

        # Add coordinates to entities
        entities_with_coords = []
        for entity in entities_enriched:
            entity_id = entity.get('entity_id')
            if entity_id in geocoded_coords:
                entity['coordinates'] = geocoded_coords[entity_id]
            entities_with_coords.append(entity)

        logger.info(f"✅ Geocoding complete:")
        logger.info(f"   Total entities: {geocode_stats['total_entities']}")
        logger.info(f"   Nominatim (FREE): {geocode_stats['nominatim']}")
        logger.info(f"   Google Maps (PAID): {geocode_stats['google']}")
        logger.info(f"   Failed: {geocode_stats['failed']}")
        logger.info(f"   Success rate: {geocode_stats['success_rate']:.1f}%")
        if geocode_stats['google'] > 0:
            logger.info(f"   💰 Google Maps cost: ${geocode_stats['google_cost_usd']:.4f}")

        # Save to S3
        if save_to_s3:
            logger.info(f"\n💾 Step 7: Saving canonical {entity_type}s to S3...")

            # Collect stats for current entity type
            dedup_stats_type = {
                'entity_type': entity_type,
                'total_groups': dedup_result.get('statistics', {}).get('total_groups', 0),
                'singletons': dedup_result.get('statistics', {}).get('singletons', 0),
                'deduplication_rate': canon_result.get('statistics', {}).get('deduplication_rate', 0.0)
            }

            save_result = save_canonical_entities_to_s3(
                s3_storage=s3,
                canonical_entities=entities_with_coords,
                processing_date=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                dedup_stats=dedup_stats_type,
                geocode_stats=geocode_stats,
                theme_stats=theme_stats,
                enrichment_stats=enrichment_stats
            )

            if not save_result['success']:
                logger.error(f"❌ Failed to save {entity_type} entities to S3")
                for error in save_result.get('errors', []):
                    logger.error(f"   {error}")
            else:
                logger.info(f"✅ Saved {len(save_result['files_saved'])} files to S3")

        # Store results
        all_results[entity_type] = {
            'dedup_result': dedup_result,
            'canon_result': canon_result,
            'entities_final': entities_with_coords,
            'consensus_count': consensus_count,
            'geocode_stats': geocode_stats
        }

        total_canonical_entities += len(entities_with_coords)
        total_consensus_calculated += consensus_count

    # Calculate total geocoding stats
    total_geocoded = 0
    total_nominatim = 0
    total_google = 0
    total_geocode_failed = 0
    total_google_cost = 0.0

    for entity_type, results in all_results.items():
        geocode_stats = results.get('geocode_stats', {})
        total_geocoded += geocode_stats.get('nominatim', 0) + geocode_stats.get('google', 0)
        total_nominatim += geocode_stats.get('nominatim', 0)
        total_google += geocode_stats.get('google', 0)
        total_geocode_failed += geocode_stats.get('failed', 0)
        total_google_cost += geocode_stats.get('google_cost_usd', 0.0)

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

    # Add geocoding costs
    if total_nominatim > 0:
        cost_tracker.track_geocoding('nominatim', total_nominatim)
    if total_google > 0:
        cost_tracker.track_geocoding('google', total_google)

    # Save cost report to file
    cost_report_path = f'data/cost_reports/stage3_cost_report_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.json'
    cost_tracker.save_cost_report(cost_report_path)

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 3 PIPELINE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"📥 INPUT:")
    logger.info(f"   Loaded {total_entities} entities from {total_videos} videos")
    logger.info(f"\n📊 PROCESSING:")
    logger.info(f"   Processed {len(types_to_process)} entity types: {types_to_process}")
    logger.info(f"\n📤 OUTPUT:")
    logger.info(f"   Generated {total_canonical_entities} canonical entities")
    logger.info(f"   Calculated consensus for {total_consensus_calculated} entities")
    logger.info(f"\n🌍 GEOLOCATION:")
    logger.info(f"   Successfully geocoded: {total_geocoded}/{total_canonical_entities} ({total_geocoded/total_canonical_entities*100 if total_canonical_entities > 0 else 0:.1f}%)")
    logger.info(f"   Nominatim (FREE): {total_nominatim}")
    logger.info(f"   Google Maps (PAID): {total_google}")
    logger.info(f"   Failed: {total_geocode_failed}")
    if save_to_s3:
        logger.info(f"\n💾 STORAGE:")
        logger.info(f"   Saved all canonical entities to S3")
        logger.info(f"   Cost report saved to: {cost_report_path}")
    logger.info("=" * 80)

    # Print detailed cost report
    cost_tracker.print_cost_report()

    # Check budget warning
    cost_tracker.check_budget_warning(budget_usd=5.0)  # Warn if over $5

    # Update metadata tracker with Stage 3 completion
    logger.info("\n📊 Updating metadata tracker...")
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

        # Update tracking for each video
        videos_updated = 0
        for video_id, mapping in video_mappings.items():
            if not tracker.content_exists(video_id):
                logger.warning(f"Video {video_id} not found in tracker, skipping")
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

        # Save all updates at once (batch save at the end)
        tracker.save_to_s3()
        logger.info(f"✅ Updated metadata tracker for {videos_updated} videos")

    except Exception as e:
        logger.error(f"❌ Failed to update metadata tracker: {e}")
        logger.exception(e)

    # Move processed Stage 2 files to stage3_extracted folder
    logger.info("\n📦 Moving processed Stage 2 files to stage3_extracted folder...")
    try:
        processed_files = []
        failed_moves = []

        # Get all source file paths from by_video
        by_video = load_result.get('by_video', {})
        for video_id, video_data in by_video.items():
            source_file_path = video_data.get('source_file_path')
            if source_file_path:
                # Generate destination path: stage2-extracted/new/ -> stage2-extracted/stage3_extracted/
                # Extract the filename from the source path
                # Format: s3://bucket/stage2-extracted/new/youtube_video_{id}_extracted.jsonl
                if '/stage2-extracted/new/' in source_file_path:
                    filename = source_file_path.split('/stage2-extracted/new/')[-1]
                    dest_file_path = source_file_path.replace(
                        '/stage2-extracted/new/',
                        '/stage2-extracted/stage3_extracted/'
                    )

                    # Move file
                    success = s3.move_file(source_file_path, dest_file_path, delete_source=True)
                    if success:
                        processed_files.append(filename)
                    else:
                        failed_moves.append(filename)

        logger.info(f"✅ Successfully moved {len(processed_files)} Stage 2 files to stage3_extracted/")
        if failed_moves:
            logger.warning(f"⚠️  Failed to move {len(failed_moves)} files: {failed_moves[:5]}")

    except Exception as e:
        logger.error(f"❌ Failed to move Stage 2 files: {e}")
        logger.exception(e)

    # Get final cost report
    cost_report = cost_tracker.get_cost_report()

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
    '--no-save',
    is_flag=True,
    default=False,
    help='Do not save canonical entities to S3 (for testing)'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Logging level. Default: INFO'
)
def main(limit, entity_types, no_save, log_level):
    """
    Process Stage 3: Entity Deduplication, Canonicalization & Consensus.

    This command processes Stage 2 entities through the complete Stage 3 pipeline:
    1. Load Stage 2 entities from S3
    2. Deduplicate entities (4-tier matching)
    3. Canonicalize entity groups
    4. Calculate consensus data
    5. Save canonical entities to S3

    Examples:

        # Process first 10 videos (testing)
        python cli/process_stage3.py --limit 10

        # Process only attractions
        python cli/process_stage3.py --entity-types attraction

        # Process attractions and destinations
        python cli/process_stage3.py --entity-types attraction,destination

        # Process all videos
        python cli/process_stage3.py
    """
    # Setup logging
    setup_logging(log_level=log_level)

    # Parse entity types
    entity_types_list = None
    if entity_types:
        entity_types_list = [t.strip() for t in entity_types.split(',')]

    try:
        # Run Stage 3 pipeline
        result = process_stage3(
            limit=limit,
            entity_types=entity_types_list,
            save_to_s3=not no_save
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
