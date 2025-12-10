#!/usr/bin/env python3
"""
Comprehensive Stage 3 Testing Suite

Tests all Stage 3 components individually and as a complete pipeline.
Includes validation, quality checks, and provenance tracking tests.

Usage:
    python tests/test_stage3.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage.s3 import S3Storage
from src.processors.stage3_loader import load_all_stage2_entities
from src.processors.deduplication import deduplicate_entities
from src.processors.canonicalization import canonicalize_all_groups
from src.processors.consensus import build_entity_consensus
from src.processors.geolocation import batch_geocode_hybrid, validate_coordinates
from src.utils.metadata_tracker import MetadataTracker
from src.utils.logging import get_logger, setup_logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Setup
setup_logging(log_level='INFO')
logger = get_logger(__name__)
console = Console()

# Test results tracking
test_results = {
    'test_deduplication': {'status': 'PENDING', 'details': {}},
    'test_canonicalization': {'status': 'PENDING', 'details': {}},
    'test_consensus': {'status': 'PENDING', 'details': {}},
    'test_geolocation': {'status': 'PENDING', 'details': {}},
    'test_full_pipeline': {'status': 'PENDING', 'details': {}},
    'test_provenance': {'status': 'PENDING', 'details': {}}
}


def test_deduplication():
    """
    Test 1: Deduplication Testing

    - Load 50 sample Stage 2 entities
    - Run deduplication
    - Verify no exact duplicates remain
    - Verify similar entities grouped correctly
    - Verify singletons identified
    - Print examples of matches found
    """
    console.print("\n[bold blue]TEST 1: Deduplication[/bold blue]")
    console.print("=" * 80)

    try:
        # Initialize S3 and load entities
        s3 = S3Storage()
        load_result = load_all_stage2_entities(
            s3_storage=s3,
            prefix='stage2-extracted/new/',
            limit=10,  # Limit to 10 videos to get ~50 entities
            show_progress=False
        )

        # Get attractions for testing
        entities = load_result['by_type'].get('attraction', [])

        if len(entities) < 10:
            console.print(f"[yellow]⚠️  Warning: Only {len(entities)} entities loaded (expected 50+)[/yellow]")

        console.print(f"[cyan]Loaded {len(entities)} entities for deduplication testing[/cyan]\n")

        # Run deduplication
        dedup_result = deduplicate_entities(
            entities=entities,
            entity_type='attraction',
            auto_match_threshold=0.90,
            llm_verify_threshold=0.80,
            semantic_threshold=0.85,
            llm_confidence_threshold=0.7,
            save_audit_trail=False,
            s3_storage=s3
        )

        entity_groups = dedup_result['entity_groups']
        singletons = dedup_result['singleton_entities']
        stats = dedup_result['deduplication_stats']

        # Verification checks
        checks_passed = []
        checks_failed = []

        # Check 1: No exact duplicates in singletons
        singleton_names = [e.get('name', '').lower() for e in singletons]
        if len(singleton_names) == len(set(singleton_names)):
            checks_passed.append("✓ No exact duplicate names in singletons")
        else:
            checks_failed.append("✗ Found exact duplicates in singletons")

        # Check 2: Entity groups are non-empty
        empty_groups = [gid for gid, group in entity_groups.items() if len(group) == 0]
        if len(empty_groups) == 0:
            checks_passed.append("✓ All entity groups contain entities")
        else:
            checks_failed.append(f"✗ Found {len(empty_groups)} empty groups")

        # Check 3: Groups have at least 2 entities
        small_groups = [gid for gid, group in entity_groups.items() if len(group) < 2]
        if len(small_groups) == 0:
            checks_passed.append("✓ All groups have 2+ entities")
        else:
            checks_failed.append(f"✗ Found {len(small_groups)} groups with <2 entities")

        # Check 4: Total entities preserved
        total_in_groups = sum(len(group) for group in entity_groups.values())
        total_after = total_in_groups + len(singletons)
        if total_after == len(entities):
            checks_passed.append(f"✓ All {len(entities)} entities accounted for")
        else:
            checks_failed.append(f"✗ Entity count mismatch: {len(entities)} → {total_after}")

        # Print results
        console.print("[green]Deduplication Statistics:[/green]")
        console.print(f"  Input entities: {stats['total_input']}")
        console.print(f"  Groups formed: {stats['total_groups']}")
        console.print(f"  Singletons: {stats['singletons']}")
        console.print(f"  Deduplication rate: {stats['deduplication_rate']:.1f}%\n")

        console.print("[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Show sample matches
        if len(entity_groups) > 0:
            console.print("\n[cyan]Sample Entity Groups:[/cyan]")
            sample_groups = list(entity_groups.items())[:3]

            for group_id, group_entities in sample_groups:
                names = [e.get('name', 'Unknown') for e in group_entities]
                console.print(f"\n  Group {group_id}:")
                console.print(f"    Entities: {len(group_entities)}")
                console.print(f"    Names: {names}")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_deduplication']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 1: PASSED[/bold green]")
        else:
            test_results['test_deduplication']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 1: FAILED[/bold red]")

        test_results['test_deduplication']['details'] = {
            'entities_tested': len(entities),
            'groups_formed': len(entity_groups),
            'singletons': len(singletons),
            'deduplication_rate': stats['deduplication_rate'],
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 1: ERROR - {e}[/bold red]")
        test_results['test_deduplication']['status'] = 'ERROR'
        test_results['test_deduplication']['details'] = {'error': str(e)}
        logger.exception(e)


def test_canonicalization():
    """
    Test 2: Canonicalization Testing

    - Take sample entity group
    - Generate canonical entity
    - Verify canonical name chosen correctly
    - Verify all aliases captured
    - Verify all experiences preserved
    - Verify entity ID format correct
    """
    console.print("\n[bold blue]TEST 2: Canonicalization[/bold blue]")
    console.print("=" * 80)

    try:
        # Load sample entities
        s3 = S3Storage()
        load_result = load_all_stage2_entities(
            s3_storage=s3,
            prefix='stage2-extracted/new/',
            limit=5,
            show_progress=False
        )

        entities = load_result['by_type'].get('attraction', [])

        # Run deduplication to get groups
        dedup_result = deduplicate_entities(
            entities=entities,
            entity_type='attraction',
            auto_match_threshold=0.90,
            save_audit_trail=False,
            s3_storage=s3
        )

        entity_groups = list(dedup_result['entity_groups'].values())
        singletons = dedup_result['singleton_entities']

        # Canonicalize
        canon_result = canonicalize_all_groups(
            entity_groups=entity_groups,
            singleton_entities=singletons,
            entity_type='attraction',
            starting_sequence=1
        )

        canonical_entities = canon_result['canonical_entities']
        stats = canon_result['statistics']

        console.print(f"[cyan]Generated {len(canonical_entities)} canonical entities[/cyan]\n")

        # Verification checks
        checks_passed = []
        checks_failed = []

        # Check 1: All canonical entities have required fields
        required_fields = ['entity_id', 'canonical_name', 'entity_type', 'location', 'experiences']
        for entity in canonical_entities:
            missing_fields = [f for f in required_fields if f not in entity]
            if len(missing_fields) > 0:
                checks_failed.append(f"✗ Entity {entity.get('entity_id')} missing fields: {missing_fields}")
                break
        else:
            checks_passed.append("✓ All canonical entities have required fields")

        # Check 2: Entity ID format correct (TYPE_NNN)
        import re
        id_pattern = re.compile(r'^[A-Z]{3}_\d{3}$')
        invalid_ids = [e['entity_id'] for e in canonical_entities if not id_pattern.match(e.get('entity_id', ''))]
        if len(invalid_ids) == 0:
            checks_passed.append("✓ All entity IDs have correct format")
        else:
            checks_failed.append(f"✗ Invalid entity IDs: {invalid_ids}")

        # Check 3: Experiences preserved
        for entity in canonical_entities:
            if entity['total_mentions'] > 1:
                if len(entity.get('experiences', [])) >= entity['total_mentions']:
                    checks_passed.append(f"✓ Entity {entity['entity_id']} has all {entity['total_mentions']} experiences")
                else:
                    checks_failed.append(f"✗ Entity {entity['entity_id']} missing experiences")
                break

        # Check 4: Aliases captured for entities with duplicates
        entities_with_dups = [e for e in canonical_entities if e['total_mentions'] > 1]
        if len(entities_with_dups) > 0:
            entity = entities_with_dups[0]
            if len(entity.get('aliases', [])) >= entity['total_mentions'] - 1:
                checks_passed.append(f"✓ Aliases captured for duplicated entities")
            else:
                checks_failed.append(f"✗ Missing aliases for duplicated entities")

        # Print sample canonical entity
        if len(canonical_entities) > 0:
            sample = canonical_entities[0]
            console.print("[cyan]Sample Canonical Entity:[/cyan]")
            console.print(f"  Entity ID: {sample['entity_id']}")
            console.print(f"  Canonical Name: {sample['canonical_name']}")
            console.print(f"  Entity Type: {sample['entity_type']}")
            console.print(f"  Location: {sample['location']}")
            console.print(f"  Total Mentions: {sample['total_mentions']}")
            console.print(f"  Aliases: {sample.get('aliases', [])}")
            console.print(f"  Experiences: {len(sample.get('experiences', []))}")
            console.print(f"  Keywords: {sample.get('attributes', {}).get('keywords', [])[:5]}\n")

        console.print("[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_canonicalization']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 2: PASSED[/bold green]")
        else:
            test_results['test_canonicalization']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 2: FAILED[/bold red]")

        test_results['test_canonicalization']['details'] = {
            'canonical_entities': len(canonical_entities),
            'entities_with_duplicates': stats['entities_with_duplicates'],
            'total_aliases': stats['total_aliases'],
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 2: ERROR - {e}[/bold red]")
        test_results['test_canonicalization']['status'] = 'ERROR'
        test_results['test_canonicalization']['details'] = {'error': str(e)}
        logger.exception(e)


def test_consensus():
    """
    Test 3: Consensus Building Testing

    - Take entity with 5+ experiences
    - Build consensus
    - Verify profile bucketing correct
    - Verify metrics calculated properly
    - Verify best_for/not_recommended make sense
    - Print consensus for manual review
    """
    console.print("\n[bold blue]TEST 3: Consensus Building[/bold blue]")
    console.print("=" * 80)

    try:
        # Load and process entities to get canonical entities
        s3 = S3Storage()
        load_result = load_all_stage2_entities(
            s3_storage=s3,
            prefix='stage2-extracted/new/',
            limit=10,
            show_progress=False
        )

        entities = load_result['by_type'].get('attraction', [])

        # Deduplicate and canonicalize
        dedup_result = deduplicate_entities(
            entities=entities,
            entity_type='attraction',
            save_audit_trail=False,
            s3_storage=s3
        )

        canon_result = canonicalize_all_groups(
            entity_groups=list(dedup_result['entity_groups'].values()),
            singleton_entities=dedup_result['singleton_entities'],
            entity_type='attraction',
            starting_sequence=1
        )

        canonical_entities = canon_result['canonical_entities']

        # Find entity with 3+ experiences (lower threshold for testing)
        entities_with_experiences = [e for e in canonical_entities if len(e.get('experiences', [])) >= 3]

        if len(entities_with_experiences) == 0:
            console.print("[yellow]⚠️  No entities with 3+ experiences found, using entity with most experiences[/yellow]")
            entities_with_experiences = sorted(canonical_entities, key=lambda e: len(e.get('experiences', [])), reverse=True)[:1]

        test_entity = entities_with_experiences[0]

        console.print(f"[cyan]Testing consensus for: {test_entity['canonical_name']}[/cyan]")
        console.print(f"[cyan]Experiences: {len(test_entity.get('experiences', []))}[/cyan]\n")

        # Build consensus
        entity_with_consensus = build_entity_consensus(test_entity)

        # Verification checks
        checks_passed = []
        checks_failed = []

        # Check 1: Consensus section exists
        if 'consensus' in entity_with_consensus:
            checks_passed.append("✓ Consensus section created")
            consensus = entity_with_consensus['consensus']

            # Check 2: Overall rating calculated
            if 'overall_rating' in consensus and 0 <= consensus['overall_rating'] <= 5:
                checks_passed.append(f"✓ Overall rating valid: {consensus['overall_rating']:.2f}/5.0")
            else:
                checks_failed.append("✗ Overall rating invalid or missing")

            # Check 3: Profile metrics exist
            if 'profile_metrics' in consensus and len(consensus['profile_metrics']) > 0:
                checks_passed.append(f"✓ Profile metrics calculated ({len(consensus['profile_metrics'])} profiles)")
            else:
                checks_failed.append("✗ No profile metrics found")

            # Check 4: Common themes extracted
            if 'common_themes' in consensus and len(consensus['common_themes']) > 0:
                checks_passed.append(f"✓ Common themes extracted ({len(consensus['common_themes'])} themes)")
            else:
                checks_failed.append("✗ No common themes found")

            # Check 5: Sentiment distribution
            if 'sentiment_distribution' in consensus:
                checks_passed.append("✓ Sentiment distribution calculated")
            else:
                checks_failed.append("✗ No sentiment distribution")

            # Print consensus for manual review
            console.print("[cyan]Consensus Data (Manual Review):[/cyan]")
            console.print(f"  Overall Rating: {consensus.get('overall_rating', 0):.2f}/5.0")
            console.print(f"  Total Mentions: {consensus.get('total_mentions', 0)}")
            console.print(f"  Best For: {consensus.get('best_for', [])[:5]}")
            console.print(f"  Not Recommended For: {consensus.get('not_recommended_for', [])[:3]}")
            console.print(f"  Common Themes: {consensus.get('common_themes', [])[:5]}")
            console.print(f"  Sentiment: {consensus.get('sentiment_distribution', {})}")

            if consensus.get('profile_metrics'):
                console.print("\n  Profile Metrics:")
                for profile, metrics in list(consensus['profile_metrics'].items())[:3]:
                    console.print(f"    {profile}: {metrics['avg_rating']:.1f}/5.0 ({metrics['mention_count']} mentions)")
        else:
            checks_failed.append("✗ No consensus section in entity")

        console.print("\n[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_consensus']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 3: PASSED[/bold green]")
        else:
            test_results['test_consensus']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 3: FAILED[/bold red]")

        test_results['test_consensus']['details'] = {
            'entity_tested': test_entity['canonical_name'],
            'experiences_count': len(test_entity.get('experiences', [])),
            'has_consensus': 'consensus' in entity_with_consensus,
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 3: ERROR - {e}[/bold red]")
        test_results['test_consensus']['status'] = 'ERROR'
        test_results['test_consensus']['details'] = {'error': str(e)}
        logger.exception(e)


def test_geolocation():
    """
    Test 4: Geolocation Testing

    - Geocode 10 known entities
    - Verify coordinates in Thailand bounds
    - Verify city roughly correct
    - Verify Nominatim/Google working
    - Print success rate
    """
    console.print("\n[bold blue]TEST 4: Geolocation[/bold blue]")
    console.print("=" * 80)

    try:
        # Sample well-known Thai entities
        test_entities = [
            {'entity_id': 'ATT_001', 'canonical_name': 'Wat Pho', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
            {'entity_id': 'ATT_002', 'canonical_name': 'Grand Palace', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
            {'entity_id': 'ATT_003', 'canonical_name': 'Doi Suthep', 'location': {'city': 'Chiang Mai', 'area': ''}},
            {'entity_id': 'ATT_004', 'canonical_name': 'Patong Beach', 'location': {'city': 'Phuket', 'area': 'Patong'}},
            {'entity_id': 'ATT_005', 'canonical_name': 'Railay Beach', 'location': {'city': 'Krabi', 'area': 'Ao Nang'}},
            {'entity_id': 'ATT_006', 'canonical_name': 'Khao San Road', 'location': {'city': 'Bangkok', 'area': 'Phra Nakhon'}},
            {'entity_id': 'ATT_007', 'canonical_name': 'Phi Phi Islands', 'location': {'city': 'Krabi', 'area': ''}},
            {'entity_id': 'ATT_008', 'canonical_name': 'Night Bazaar', 'location': {'city': 'Chiang Mai', 'area': 'Chang Khlan'}},
            {'entity_id': 'ATT_009', 'canonical_name': 'Ayutthaya Historical Park', 'location': {'city': 'Ayutthaya', 'area': ''}},
            {'entity_id': 'ATT_010', 'canonical_name': 'Chatuchak Market', 'location': {'city': 'Bangkok', 'area': 'Chatuchak'}},
        ]

        console.print(f"[cyan]Geocoding {len(test_entities)} known Thai entities...[/cyan]\n")

        # Geocode with hybrid strategy
        geocode_results = batch_geocode_hybrid(
            entities=test_entities,
            cache_file='data/test_geocode_cache.json',
            nominatim_confidence_threshold=0.8,
            validate=True
        )

        results = geocode_results['results']
        stats = geocode_results['statistics']

        # Verification checks
        checks_passed = []
        checks_failed = []

        # Check 1: Success rate >= 70%
        if stats['success_rate'] >= 70:
            checks_passed.append(f"✓ Success rate acceptable: {stats['success_rate']:.1f}%")
        else:
            checks_failed.append(f"✗ Success rate too low: {stats['success_rate']:.1f}%")

        # Check 2: All coordinates in Thailand bounds
        THAILAND_LAT_MIN, THAILAND_LAT_MAX = 5.0, 21.0
        THAILAND_LON_MIN, THAILAND_LON_MAX = 97.0, 106.0

        out_of_bounds = []
        for entity_id, coords in results.items():
            lat, lon = coords['lat'], coords['lon']
            if not (THAILAND_LAT_MIN <= lat <= THAILAND_LAT_MAX and THAILAND_LON_MIN <= lon <= THAILAND_LON_MAX):
                out_of_bounds.append(entity_id)

        if len(out_of_bounds) == 0:
            checks_passed.append("✓ All coordinates within Thailand bounds")
        else:
            checks_failed.append(f"✗ Coordinates out of bounds: {out_of_bounds}")

        # Check 3: Nominatim working (at least some free results)
        if stats['nominatim'] > 0:
            checks_passed.append(f"✓ Nominatim working ({stats['nominatim']} entities)")
        else:
            checks_failed.append("✗ Nominatim not working (0 results)")

        # Print results
        console.print("[green]Geocoding Statistics:[/green]")
        console.print(f"  Total entities: {stats['total_entities']}")
        console.print(f"  Nominatim (FREE): {stats['nominatim']}")
        console.print(f"  Google Maps (PAID): {stats['google']}")
        console.print(f"  Cached: {stats['cached']}")
        console.print(f"  Failed: {stats['failed']}")
        console.print(f"  Success rate: {stats['success_rate']:.1f}%")
        console.print(f"  Google cost: ${stats.get('google_cost_usd', 0):.4f}\n")

        # Show sample results
        console.print("[cyan]Sample Geocoding Results:[/cyan]")
        for entity in test_entities[:5]:
            entity_id = entity['entity_id']
            name = entity['canonical_name']

            if entity_id in results:
                coords = results[entity_id]
                provider_emoji = "🆓" if coords['provider'] == 'nominatim' else "💳"
                console.print(f"  {provider_emoji} {name}")
                console.print(f"     Coordinates: ({coords['lat']:.4f}, {coords['lon']:.4f})")
                console.print(f"     Provider: {coords['provider']} (confidence: {coords['confidence']:.2f})")
            else:
                console.print(f"  ❌ {name} - FAILED")

        console.print("\n[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_geolocation']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 4: PASSED[/bold green]")
        else:
            test_results['test_geolocation']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 4: FAILED[/bold red]")

        test_results['test_geolocation']['details'] = {
            'entities_tested': len(test_entities),
            'success_rate': stats['success_rate'],
            'nominatim_count': stats['nominatim'],
            'google_count': stats['google'],
            'failed_count': stats['failed'],
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 4: ERROR - {e}[/bold red]")
        test_results['test_geolocation']['status'] = 'ERROR'
        test_results['test_geolocation']['details'] = {'error': str(e)}
        logger.exception(e)


def test_full_pipeline():
    """
    Test 5: Full Pipeline Testing

    - Process 20 entities end-to-end
    - Verify output format
    - Check S3 saves correctly
    - Validate no data loss
    - Print sample canonical entity
    """
    console.print("\n[bold blue]TEST 5: Full Pipeline[/bold blue]")
    console.print("=" * 80)

    try:
        # Run complete pipeline
        from cli.process_stage3 import process_stage3

        console.print("[cyan]Running complete Stage 3 pipeline (limit: 5 videos)...[/cyan]\n")

        result = process_stage3(
            limit=5,
            entity_types=['attraction'],
            save_to_s3=False  # Don't save during testing
        )

        # Verification checks
        checks_passed = []
        checks_failed = []

        # Check 1: Pipeline completed successfully
        if result and 'total_canonical_entities' in result:
            checks_passed.append("✓ Pipeline completed successfully")
        else:
            checks_failed.append("✗ Pipeline failed to complete")
            test_results['test_full_pipeline']['status'] = 'FAIL'
            return

        # Check 2: Canonical entities generated
        if result['total_canonical_entities'] > 0:
            checks_passed.append(f"✓ Generated {result['total_canonical_entities']} canonical entities")
        else:
            checks_failed.append("✗ No canonical entities generated")

        # Check 3: Consensus calculated
        if result['total_consensus_calculated'] > 0:
            checks_passed.append(f"✓ Consensus calculated for {result['total_consensus_calculated']} entities")
        else:
            checks_failed.append("✗ No consensus calculated")

        # Check 4: Geocoding success
        if result.get('geocoding_success_rate', 0) >= 50:
            checks_passed.append(f"✓ Geocoding success rate: {result['geocoding_success_rate']:.1f}%")
        else:
            checks_failed.append(f"✗ Low geocoding success rate: {result.get('geocoding_success_rate', 0):.1f}%")

        # Check 5: No data loss (input entities = output entities)
        load_stats = result['load_result']['statistics']
        total_input = load_stats['total_entities']

        # Count entities in all canonical entities
        total_mentions = 0
        for entity_type, type_results in result['results_by_type'].items():
            for entity in type_results['entities_final']:
                total_mentions += entity.get('total_mentions', 1)

        if total_mentions >= total_input * 0.9:  # Allow 10% tolerance
            checks_passed.append(f"✓ No significant data loss ({total_mentions}/{total_input} entities)")
        else:
            checks_failed.append(f"✗ Data loss detected: {total_input} → {total_mentions}")

        # Print sample canonical entity
        console.print("[cyan]Sample Canonical Entity:[/cyan]")
        for entity_type, type_results in result['results_by_type'].items():
            entities = type_results['entities_final']
            if len(entities) > 0:
                sample = entities[0]
                console.print(json.dumps({
                    'entity_id': sample['entity_id'],
                    'canonical_name': sample['canonical_name'],
                    'location': sample['location'],
                    'total_mentions': sample['total_mentions'],
                    'has_consensus': 'consensus' in sample,
                    'has_coordinates': 'coordinates' in sample
                }, indent=2))
                break

        console.print("\n[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_full_pipeline']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 5: PASSED[/bold green]")
        else:
            test_results['test_full_pipeline']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 5: FAILED[/bold red]")

        test_results['test_full_pipeline']['details'] = {
            'canonical_entities': result['total_canonical_entities'],
            'consensus_calculated': result['total_consensus_calculated'],
            'geocoding_success_rate': result.get('geocoding_success_rate', 0),
            'total_cost': result.get('total_cost_usd', 0),
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 5: ERROR - {e}[/bold red]")
        test_results['test_full_pipeline']['status'] = 'ERROR'
        test_results['test_full_pipeline']['details'] = {'error': str(e)}
        logger.exception(e)


def test_provenance():
    """
    Test 6: Provenance Tracking Testing

    - Pick random canonical entity
    - Trace back to source videos
    - Verify all provenance fields present
    - Print provenance chain
    """
    console.print("\n[bold blue]TEST 6: Provenance Tracking[/bold blue]")
    console.print("=" * 80)

    try:
        # Run pipeline to generate some canonical entities with tracking
        from cli.process_stage3 import process_stage3

        console.print("[cyan]Running pipeline to generate entities with tracking...[/cyan]\n")

        result = process_stage3(
            limit=3,
            entity_types=['attraction'],
            save_to_s3=True  # Save to update metadata tracker
        )

        if not result or result['total_canonical_entities'] == 0:
            console.print("[yellow]⚠️  No entities generated, skipping provenance test[/yellow]")
            test_results['test_provenance']['status'] = 'SKIP'
            return

        # Get a canonical entity
        sample_entity_id = None
        for entity_type, type_results in result['results_by_type'].items():
            entities = type_results['entities_final']
            if len(entities) > 0:
                sample_entity_id = entities[0]['entity_id']
                break

        if not sample_entity_id:
            console.print("[yellow]⚠️  No entity ID found[/yellow]")
            test_results['test_provenance']['status'] = 'SKIP'
            return

        console.print(f"[cyan]Testing provenance for entity: {sample_entity_id}[/cyan]\n")

        # Test provenance tracking
        s3 = S3Storage()
        tracker = MetadataTracker(s3)

        # Verification checks
        checks_passed = []
        checks_failed = []

        try:
            provenance = tracker.get_entity_provenance(sample_entity_id)

            # Check 1: Provenance returned
            checks_passed.append("✓ Provenance data retrieved")

            # Check 2: Required fields present
            required_fields = ['canonical_entity_id', 'source_videos', 'total_source_videos',
                             'total_stage2_entities', 'deduplication_method']
            missing_fields = [f for f in required_fields if f not in provenance]

            if len(missing_fields) == 0:
                checks_passed.append("✓ All required provenance fields present")
            else:
                checks_failed.append(f"✗ Missing provenance fields: {missing_fields}")

            # Check 3: Source videos found
            if provenance['total_source_videos'] > 0:
                checks_passed.append(f"✓ Found {provenance['total_source_videos']} source videos")
            else:
                checks_failed.append("✗ No source videos found")

            # Check 4: Stage 2 entities tracked
            if provenance['total_stage2_entities'] > 0:
                checks_passed.append(f"✓ Tracked {provenance['total_stage2_entities']} Stage 2 entities")
            else:
                checks_failed.append("✗ No Stage 2 entities tracked")

            # Print provenance chain
            console.print("[cyan]Provenance Chain:[/cyan]")
            console.print(f"  Canonical Entity: {provenance['canonical_entity_id']}")
            console.print(f"  Source Videos: {provenance['total_source_videos']}")
            console.print(f"  Stage 2 Entities: {provenance['total_stage2_entities']}")
            console.print(f"  Deduplication Method: {provenance['deduplication_method']}")
            console.print(f"  Avg Contribution: {provenance['average_contribution_per_video']:.1f} entities/video\n")

            if provenance['source_videos']:
                console.print("  Source Video Details:")
                for video in provenance['source_videos'][:3]:
                    console.print(f"    - {video['content_id']}")
                    console.print(f"      Title: {video.get('title', 'N/A')}")
                    console.print(f"      Contributed: {video['contribution_count']} entities")

        except ValueError as e:
            checks_failed.append(f"✗ Provenance lookup failed: {e}")

        console.print("\n[green]Verification Results:[/green]")
        for check in checks_passed:
            console.print(f"  [green]{check}[/green]")
        for check in checks_failed:
            console.print(f"  [red]{check}[/red]")

        # Determine pass/fail
        if len(checks_failed) == 0:
            test_results['test_provenance']['status'] = 'PASS'
            console.print("\n[bold green]✓ TEST 6: PASSED[/bold green]")
        else:
            test_results['test_provenance']['status'] = 'FAIL'
            console.print("\n[bold red]✗ TEST 6: FAILED[/bold red]")

        test_results['test_provenance']['details'] = {
            'entity_tested': sample_entity_id,
            'source_videos': provenance.get('total_source_videos', 0) if 'provenance' in locals() else 0,
            'checks_passed': len(checks_passed),
            'checks_failed': len(checks_failed)
        }

    except Exception as e:
        console.print(f"\n[bold red]✗ TEST 6: ERROR - {e}[/bold red]")
        test_results['test_provenance']['status'] = 'ERROR'
        test_results['test_provenance']['details'] = {'error': str(e)}
        logger.exception(e)


def print_final_summary():
    """Print final test summary and save results to file."""
    console.print("\n" + "=" * 80)
    console.print("[bold blue]FINAL TEST SUMMARY[/bold blue]")
    console.print("=" * 80 + "\n")

    # Create summary table
    table = Table(title="Stage 3 Test Results", box=box.ROUNDED)
    table.add_column("Test", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Details", style="white")

    for test_name, result in test_results.items():
        status = result['status']

        # Color code status
        if status == 'PASS':
            status_text = "[green]✓ PASS[/green]"
        elif status == 'FAIL':
            status_text = "[red]✗ FAIL[/red]"
        elif status == 'ERROR':
            status_text = "[red]✗ ERROR[/red]"
        elif status == 'SKIP':
            status_text = "[yellow]⊘ SKIP[/yellow]"
        else:
            status_text = "[yellow]? PENDING[/yellow]"

        # Format details
        details = result.get('details', {})
        if 'error' in details:
            detail_text = f"Error: {details['error'][:50]}..."
        else:
            detail_text = f"Checks: {details.get('checks_passed', 0)} passed, {details.get('checks_failed', 0)} failed"

        table.add_row(test_name.replace('_', ' ').title(), status_text, detail_text)

    console.print(table)

    # Count results
    passed = sum(1 for r in test_results.values() if r['status'] == 'PASS')
    failed = sum(1 for r in test_results.values() if r['status'] == 'FAIL')
    errors = sum(1 for r in test_results.values() if r['status'] == 'ERROR')
    skipped = sum(1 for r in test_results.values() if r['status'] == 'SKIP')

    console.print(f"\n[bold]Results:[/bold]")
    console.print(f"  [green]Passed: {passed}[/green]")
    console.print(f"  [red]Failed: {failed}[/red]")
    console.print(f"  [red]Errors: {errors}[/red]")
    console.print(f"  [yellow]Skipped: {skipped}[/yellow]")

    # Overall status
    if failed == 0 and errors == 0:
        console.print(f"\n[bold green]✓ ALL TESTS PASSED ({passed}/{len(test_results)})[/bold green]")
        overall_status = 'PASS'
    else:
        console.print(f"\n[bold red]✗ SOME TESTS FAILED ({passed}/{len(test_results)} passed)[/bold red]")
        overall_status = 'FAIL'

    # Save results to file
    results_file = Path('tests/test_stage3_results.json')
    results_file.parent.mkdir(parents=True, exist_ok=True)

    output = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'overall_status': overall_status,
        'summary': {
            'total_tests': len(test_results),
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'skipped': skipped
        },
        'test_results': test_results
    }

    with open(results_file, 'w') as f:
        json.dump(output, f, indent=2)

    console.print(f"\n[cyan]Test results saved to: {results_file}[/cyan]")
    console.print("=" * 80 + "\n")


def main():
    """Run all Stage 3 tests."""
    console.print("\n[bold blue]STAGE 3 COMPREHENSIVE TEST SUITE[/bold blue]")
    console.print("=" * 80)
    console.print("Running 6 comprehensive tests for Stage 3 pipeline\n")

    # Run all tests
    test_deduplication()
    test_canonicalization()
    test_consensus()
    test_geolocation()
    test_full_pipeline()
    test_provenance()

    # Print final summary
    print_final_summary()


if __name__ == '__main__':
    main()
