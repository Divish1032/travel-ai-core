"""
Test complete Stage 3 pipeline: Load → Deduplicate → Canonicalize → Consensus

Tests the full Stage 3 workflow from Stage 2 entities to canonical entities with consensus.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.s3 import S3Storage
from src.processors.stage3_loader import load_all_stage2_entities
from src.processors.deduplication import deduplicate_entities
from src.processors.canonicalization import canonicalize_all_groups
from src.processors.consensus import build_entity_consensus
from src.utils.logging import get_logger

logger = get_logger(__name__)


def test_stage3_pipeline():
    """
    Test complete Stage 3 pipeline with real data.

    Steps:
    1. Load Stage 2 entities from S3 (limit to 10 videos for testing)
    2. Deduplicate entities (4-tier matching)
    3. Canonicalize entity groups
    4. Calculate consensus for each canonical entity
    5. Verify results
    """
    logger.info("=" * 80)
    logger.info("STAGE 3 PIPELINE TEST")
    logger.info("=" * 80)

    # Initialize S3
    logger.info("\n📦 Step 1: Initializing S3...")
    s3 = S3Storage()

    # Load Stage 2 entities (limit to 10 videos for quick test)
    logger.info("\n📥 Step 2: Loading Stage 2 entities (10 videos)...")
    load_result = load_all_stage2_entities(
        s3_storage=s3,
        prefix='stage2-extracted/new/',
        limit=10,
        show_progress=False
    )

    total_entities = load_result['statistics']['total_entities']
    logger.info(f"Loaded {total_entities} entities from {load_result['statistics']['total_videos']} videos")

    # Test with attractions only
    logger.info("\n🔍 Step 3: Filtering attractions only...")
    attractions = load_result['by_type'].get('attraction', [])
    logger.info(f"Found {len(attractions)} attractions")

    if len(attractions) < 2:
        logger.warning("Not enough attractions to test deduplication. Exiting.")
        return

    # Deduplicate
    logger.info("\n🔗 Step 4: Deduplicating attractions...")
    dedup_result = deduplicate_entities(
        entities=attractions,
        entity_type='attraction',
        auto_match_threshold=0.90,
        llm_verify_threshold=0.80,
        semantic_threshold=0.85,
        llm_confidence_threshold=0.7,
        save_audit_trail=False,  # Don't save to S3 for testing
        s3_storage=None
    )

    entity_groups = dedup_result['entity_groups']
    singleton_entities = dedup_result['singleton_entities']
    stats = dedup_result['deduplication_stats']

    logger.info(f"✅ Deduplication complete:")
    logger.info(f"   Input entities: {stats['total_input']}")
    logger.info(f"   Entity groups: {stats['total_groups']}")
    logger.info(f"   Singleton entities: {stats['singletons']}")
    logger.info(f"   Deduplication rate: {stats['deduplication_rate']:.1f}%")

    # Canonicalize
    logger.info("\n✨ Step 5: Canonicalizing entities...")
    # Convert entity_groups dict to list of lists
    entity_groups_list = list(entity_groups.values())

    canon_result = canonicalize_all_groups(
        entity_groups=entity_groups_list,
        singleton_entities=singleton_entities,
        entity_type='attraction',
        starting_sequence=1
    )

    canonical_entities = canon_result['canonical_entities']
    canon_stats = canon_result['statistics']

    logger.info(f"✅ Canonicalization complete:")
    logger.info(f"   Total canonical entities: {canon_stats['total_canonical_entities']}")
    logger.info(f"   From groups: {canon_stats['entities_from_groups']}")
    logger.info(f"   From singletons: {canon_stats['entities_from_singletons']}")
    logger.info(f"   Total mentions: {canon_stats['total_mentions']}")
    logger.info(f"   Entities with duplicates: {canon_stats['entities_with_duplicates']}")
    logger.info(f"   Total aliases: {canon_stats['total_aliases']}")

    # Calculate consensus
    logger.info("\n🎯 Step 6: Calculating consensus for canonical entities...")
    entities_with_consensus = []
    consensus_stats = {
        'total_processed': 0,
        'entities_with_consensus': 0,
        'total_profiles_found': 0,
        'entities_with_best_for': 0,
        'entities_with_not_recommended': 0
    }

    for entity in canonical_entities:
        # Only calculate consensus if entity has experiences
        if entity.get('experiences') and len(entity['experiences']) > 0:
            entity_with_consensus = build_entity_consensus(entity)
            entities_with_consensus.append(entity_with_consensus)
            consensus_stats['total_processed'] += 1

            if 'consensus' in entity_with_consensus:
                consensus = entity_with_consensus['consensus']
                consensus_stats['entities_with_consensus'] += 1
                consensus_stats['total_profiles_found'] += len(consensus.get('profile_metrics', {}))

                if consensus.get('best_for'):
                    consensus_stats['entities_with_best_for'] += 1
                if consensus.get('not_recommended_for'):
                    consensus_stats['entities_with_not_recommended'] += 1
        else:
            entities_with_consensus.append(entity)

    logger.info(f"✅ Consensus calculation complete:")
    logger.info(f"   Total entities processed: {consensus_stats['total_processed']}")
    logger.info(f"   Entities with consensus: {consensus_stats['entities_with_consensus']}")
    logger.info(f"   Total profiles found: {consensus_stats['total_profiles_found']}")
    logger.info(f"   Entities with 'best_for' recommendations: {consensus_stats['entities_with_best_for']}")
    logger.info(f"   Entities with 'not_recommended' warnings: {consensus_stats['entities_with_not_recommended']}")

    # Display sample canonical entities
    logger.info("\n📊 Step 7: Sample Canonical Entities with Consensus")
    logger.info("=" * 80)

    # Show entities with duplicates first
    entities_with_dups = [e for e in entities_with_consensus if e['total_mentions'] > 1]
    if entities_with_dups:
        logger.info("\nEntities with duplicates detected:")
        for entity in entities_with_dups[:3]:
            logger.info(f"\n  🎯 {entity['canonical_name']} (ID: {entity['entity_id']})")
            logger.info(f"     Type: {entity['entity_type']}")
            logger.info(f"     Location: {entity['location']}")
            logger.info(f"     Mentions: {entity['total_mentions']}")
            logger.info(f"     Aliases: {entity['aliases']}")
            logger.info(f"     Keywords: {entity['attributes']['keywords'][:5]}")
            logger.info(f"     Source videos: {entity['source_video_ids']}")
            logger.info(f"     Canonical name selection: {entity['provenance']['canonical_name_selection']['reasoning']}")

            # Display consensus data if available
            if 'consensus' in entity:
                consensus = entity['consensus']
                logger.info(f"\n     📊 Consensus Data:")
                logger.info(f"        Overall rating: {consensus['overall_rating']:.2f}/5.0")
                logger.info(f"        Total mentions: {consensus['total_mentions']}")
                logger.info(f"        Best for: {consensus['best_for'][:3] if consensus['best_for'] else 'None'}")
                logger.info(f"        Not recommended for: {consensus['not_recommended_for'][:3] if consensus['not_recommended_for'] else 'None'}")
                logger.info(f"        Common themes: {consensus['common_themes'][:5]}")
                logger.info(f"        Sentiment: {consensus['sentiment_distribution']}")

                # Show top 2 profile metrics
                if consensus.get('profile_metrics'):
                    logger.info(f"        Top profiles:")
                    sorted_profiles = sorted(
                        consensus['profile_metrics'].items(),
                        key=lambda x: x[1]['avg_rating'],
                        reverse=True
                    )
                    for profile_key, metrics in sorted_profiles[:2]:
                        logger.info(f"          - {profile_key}: {metrics['avg_rating']:.1f}/5.0 ({metrics['mention_count']} mentions)")

    # Show sample singletons
    singletons = [e for e in entities_with_consensus if e['total_mentions'] == 1]
    if singletons:
        logger.info(f"\n\nSample singleton entities (showing 3 of {len(singletons)}):")
        for entity in singletons[:3]:
            logger.info(f"\n  📍 {entity['canonical_name']} (ID: {entity['entity_id']})")
            logger.info(f"     Location: {entity['location']}")
            logger.info(f"     Keywords: {entity['attributes']['keywords'][:5]}")

            # Display consensus if available
            if 'consensus' in entity and entity.get('experiences'):
                consensus = entity['consensus']
                logger.info(f"     Overall rating: {consensus['overall_rating']:.2f}/5.0")
                logger.info(f"     Best for: {consensus['best_for'][:2] if consensus['best_for'] else 'N/A'}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("PIPELINE TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"✅ Loaded {total_entities} entities from {load_result['statistics']['total_videos']} videos")
    logger.info(f"✅ Deduplicated {len(attractions)} attractions → {stats['total_groups']} groups, {stats['singletons']} singletons")
    logger.info(f"✅ Generated {canon_stats['total_canonical_entities']} canonical entities")
    logger.info(f"✅ Found {canon_stats['entities_with_duplicates']} entities with duplicates ({canon_stats['deduplication_rate']:.1f}% deduplication rate)")
    logger.info(f"✅ Extracted {canon_stats['total_aliases']} total aliases")
    logger.info(f"✅ Calculated consensus for {consensus_stats['entities_with_consensus']} entities")
    logger.info(f"✅ Found {consensus_stats['entities_with_best_for']} entities with 'best_for' recommendations")
    logger.info(f"✅ Identified {consensus_stats['entities_with_not_recommended']} entities with warnings")
    logger.info("=" * 80)

    return {
        'load_result': load_result,
        'dedup_result': dedup_result,
        'canon_result': canon_result,
        'consensus_result': {
            'entities_with_consensus': entities_with_consensus,
            'consensus_stats': consensus_stats
        }
    }


if __name__ == '__main__':
    test_stage3_pipeline()
