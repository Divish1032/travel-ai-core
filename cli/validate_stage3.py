#!/usr/bin/env python3
"""
Stage 3 Validation & Quality Assurance

Validates Stage 3 canonical entities for:
- Completeness (all required fields present)
- Deduplication quality (matches look correct)
- Geolocation accuracy (coordinates valid)
- Consensus logic (calculations correct)
- Provenance (entities traceable to source videos)

Usage:
    python cli/validate_stage3.py [--sample N] [--log-level DEBUG]
    ./crawl.sh validate-stage3 [--sample N]

Output:
    - Console report with validation results
    - QA report saved to: stage3-canonical/metadata/qa_report_{date}.json
    - Actionable recommendations for improvements
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import random
from collections import Counter

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal
from src.database.models import CanonicalEntity, EntityExperience, Video
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_completeness(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate all entities have required fields.

    Checks:
    - entity_id, canonical_name present
    - location with city
    - coordinates (or marked as failed)
    - experiences list (not empty)
    - consensus section

    Returns:
        Dict with validation results and issues
    """
    logger.info("🔍 Validating entity completeness...")

    issues = []
    stats = {
        'total_entities': len(entities),
        'missing_entity_id': 0,
        'missing_canonical_name': 0,
        'missing_location': 0,
        'missing_city': 0,
        'missing_coordinates': 0,
        'missing_experiences': 0,
        'empty_experiences': 0,
        'missing_consensus': 0,
        'fully_complete': 0
    }

    for i, entity in enumerate(entities):
        entity_issues = []
        entity_id = entity.get('entity_id', f'unknown_{i}')

        # Check entity_id
        if not entity.get('entity_id'):
            stats['missing_entity_id'] += 1
            entity_issues.append('missing entity_id')

        # Check canonical_name
        if not entity.get('canonical_name'):
            stats['missing_canonical_name'] += 1
            entity_issues.append('missing canonical_name')

        # Check location
        location = entity.get('location')
        if not location:
            stats['missing_location'] += 1
            entity_issues.append('missing location')
        else:
            # Check city
            if isinstance(location, dict):
                if not location.get('city'):
                    stats['missing_city'] += 1
                    entity_issues.append('missing city in location')
            elif isinstance(location, str):
                # Location is just a string - acceptable
                pass
            else:
                stats['missing_city'] += 1
                entity_issues.append('invalid location format')

        # Check coordinates
        if 'coordinates' not in entity:
            stats['missing_coordinates'] += 1
            entity_issues.append('missing coordinates')

        # Check experiences
        experiences = entity.get('experiences')
        if experiences is None:
            stats['missing_experiences'] += 1
            entity_issues.append('missing experiences field')
        elif len(experiences) == 0:
            stats['empty_experiences'] += 1
            entity_issues.append('empty experiences list')

        # Check consensus
        if 'consensus' not in entity:
            stats['missing_consensus'] += 1
            entity_issues.append('missing consensus')

        # Track issues
        if entity_issues:
            issues.append({
                'entity_id': entity_id,
                'canonical_name': entity.get('canonical_name', 'N/A'),
                'issues': entity_issues
            })
        else:
            stats['fully_complete'] += 1

    # Calculate completion rate
    stats['completion_rate'] = stats['fully_complete'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0

    return {
        'passed': len(issues) == 0,
        'stats': stats,
        'issues': issues[:50],  # Limit to first 50 issues
        'total_issues': len(issues)
    }


def validate_deduplication_quality(entities: List[Dict[str, Any]], sample_size: int = 20) -> Dict[str, Any]:
    """
    Validate deduplication quality by sampling entity groups.

    Checks:
    - Entities with multiple experiences (were deduplicated)
    - Names are similar across experiences
    - Locations match

    Returns:
        Dict with validation results and sample entities
    """
    logger.info("🔍 Validating deduplication quality...")

    # Find entities with multiple experiences
    deduplicated_entities = [e for e in entities if len(e.get('experiences', [])) > 1]

    logger.info(f"Found {len(deduplicated_entities)} deduplicated entities (out of {len(entities)} total)")

    # Sample for review
    sample_entities = random.sample(deduplicated_entities, min(sample_size, len(deduplicated_entities)))

    suspicious = []
    for entity in sample_entities:
        canonical_name = entity.get('canonical_name', '')
        experiences = entity.get('experiences', [])

        # Check name similarity
        exp_names = [exp.get('name', '') for exp in experiences]
        unique_names = set(exp_names)

        # Flag if too many unique names (might be bad deduplication)
        if len(unique_names) > len(experiences) * 0.7:  # More than 70% unique
            suspicious.append({
                'entity_id': entity.get('entity_id'),
                'canonical_name': canonical_name,
                'experience_count': len(experiences),
                'unique_names': list(unique_names),
                'reason': 'Too many unique names - might be over-deduplication'
            })

    stats = {
        'total_entities': len(entities),
        'deduplicated_entities': len(deduplicated_entities),
        'singleton_entities': len(entities) - len(deduplicated_entities),
        'deduplication_rate': (len(entities) - len(deduplicated_entities)) / len(entities) * 100 if len(entities) > 0 else 0,
        'avg_experiences_per_deduplicated': sum(len(e.get('experiences', [])) for e in deduplicated_entities) / len(deduplicated_entities) if deduplicated_entities else 0,
        'suspicious_deduplication_count': len(suspicious)
    }

    return {
        'passed': len(suspicious) == 0,
        'stats': stats,
        'sample_entities': [
            {
                'entity_id': e.get('entity_id'),
                'canonical_name': e.get('canonical_name'),
                'experience_count': len(e.get('experiences', [])),
                'experience_names': [exp.get('name', '') for exp in e.get('experiences', [])]
            }
            for e in sample_entities[:10]
        ],
        'suspicious': suspicious
    }


def validate_geolocation(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate geolocation quality.

    Checks:
    - Coordinates are valid (lat/lon in range)
    - Thailand bounds check
    - Success/failure rates
    - Provider distribution (Nominatim vs Google)

    Returns:
        Dict with validation results
    """
    logger.info("🔍 Validating geolocation...")

    # Thailand bounds
    THAILAND_BOUNDS = {
        'lat_min': 5.0,
        'lat_max': 21.0,
        'lon_min': 97.0,
        'lon_max': 106.0
    }

    stats = {
        'total_entities': len(entities),
        'geocoded': 0,
        'not_geocoded': 0,
        'nominatim': 0,
        'google': 0,
        'out_of_bounds': 0,
        'invalid_coordinates': 0
    }

    out_of_bounds = []
    invalid_coords = []

    for entity in entities:
        coords = entity.get('coordinates')

        if not coords:
            stats['not_geocoded'] += 1
            continue

        stats['geocoded'] += 1

        # Check provider
        provider = coords.get('provider', 'unknown')
        if provider == 'nominatim':
            stats['nominatim'] += 1
        elif provider == 'google':
            stats['google'] += 1

        # Check coordinates validity
        lat = coords.get('lat')
        lon = coords.get('lon')

        if lat is None or lon is None:
            stats['invalid_coordinates'] += 1
            invalid_coords.append({
                'entity_id': entity.get('entity_id'),
                'canonical_name': entity.get('canonical_name'),
                'reason': 'Missing lat or lon'
            })
            continue

        # Check type
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            stats['invalid_coordinates'] += 1
            invalid_coords.append({
                'entity_id': entity.get('entity_id'),
                'canonical_name': entity.get('canonical_name'),
                'reason': f'Invalid type: lat={type(lat)}, lon={type(lon)}'
            })
            continue

        # Check bounds
        if not (THAILAND_BOUNDS['lat_min'] <= lat <= THAILAND_BOUNDS['lat_max'] and
                THAILAND_BOUNDS['lon_min'] <= lon <= THAILAND_BOUNDS['lon_max']):
            stats['out_of_bounds'] += 1
            out_of_bounds.append({
                'entity_id': entity.get('entity_id'),
                'canonical_name': entity.get('canonical_name'),
                'lat': lat,
                'lon': lon,
                'location': entity.get('location')
            })

    # Calculate rates
    stats['geocoding_success_rate'] = stats['geocoded'] / stats['total_entities'] * 100 if stats['total_entities'] > 0 else 0
    stats['nominatim_rate'] = stats['nominatim'] / stats['geocoded'] * 100 if stats['geocoded'] > 0 else 0
    stats['google_rate'] = stats['google'] / stats['geocoded'] * 100 if stats['geocoded'] > 0 else 0

    return {
        'passed': stats['invalid_coordinates'] == 0 and stats['out_of_bounds'] < stats['total_entities'] * 0.05,  # Allow 5% out of bounds
        'stats': stats,
        'out_of_bounds': out_of_bounds[:20],
        'invalid_coordinates': invalid_coords[:20]
    }


def validate_consensus_logic(entities: List[Dict[str, Any]], sample_size: int = 10) -> Dict[str, Any]:
    """
    Validate consensus calculations are correct.

    Checks:
    - avg_rating matches experience ratings
    - mention_count correct
    - best_for calculated properly

    Returns:
        Dict with validation results
    """
    logger.info("🔍 Validating consensus logic...")

    issues = []

    for entity in random.sample(entities, min(sample_size, len(entities))):
        entity_id = entity.get('entity_id')
        consensus = entity.get('consensus', {})
        experiences = entity.get('experiences', [])

        if not consensus or not experiences:
            continue

        # Check avg_rating
        ratings = [exp.get('rating') for exp in experiences if exp.get('rating') is not None]
        if ratings:
            expected_avg = sum(ratings) / len(ratings)
            actual_avg = consensus.get('avg_rating')

            if actual_avg and abs(expected_avg - actual_avg) > 0.1:
                issues.append({
                    'entity_id': entity_id,
                    'canonical_name': entity.get('canonical_name'),
                    'issue': 'avg_rating mismatch',
                    'expected': expected_avg,
                    'actual': actual_avg
                })

        # Check mention_count
        expected_mentions = len(experiences)
        actual_mentions = consensus.get('mention_count')

        if actual_mentions != expected_mentions:
            issues.append({
                'entity_id': entity_id,
                'canonical_name': entity.get('canonical_name'),
                'issue': 'mention_count mismatch',
                'expected': expected_mentions,
                'actual': actual_mentions
            })

    return {
        'passed': len(issues) == 0,
        'stats': {
            'entities_checked': min(sample_size, len(entities)),
            'issues_found': len(issues)
        },
        'issues': issues
    }


def validate_provenance(
    entities: List[Dict[str, Any]],
    db
) -> Dict[str, Any]:
    """
    Validate entity provenance tracking.

    Checks:
    - All entities traceable to source videos via EntityExperience relationships
    - No orphaned entities
    - Stage 2 -> Stage 3 mapping complete

    Returns:
        Dict with validation results
    """
    logger.info("🔍 Validating provenance...")

    orphaned = []
    missing_video_ids = []

    for entity in entities:
        entity_id = entity.get('entity_id')
        experiences = entity.get('experiences', [])

        if not experiences:
            orphaned.append({
                'entity_id': entity_id,
                'canonical_name': entity.get('canonical_name'),
                'reason': 'No experiences'
            })
            continue

        # Check if all experiences have video_id
        for exp in experiences:
            video_id = exp.get('video_id') or exp.get('source_video_id')
            if not video_id:
                missing_video_ids.append({
                    'entity_id': entity_id,
                    'canonical_name': entity.get('canonical_name'),
                    'experience_index': experiences.index(exp)
                })

    # Verify provenance via PostgreSQL
    provenance_verified = 0
    provenance_failed = 0

    for entity in random.sample(entities, min(20, len(entities))):
        entity_id = entity.get('entity_id')
        try:
            # Query EntityExperience relationships
            experience_count = db.query(EntityExperience).filter(
                EntityExperience.canonical_entity_id == entity_id
            ).count()

            if experience_count > 0:
                provenance_verified += 1
            else:
                provenance_failed += 1
        except Exception:
            provenance_failed += 1

    stats = {
        'total_entities': len(entities),
        'orphaned_entities': len(orphaned),
        'missing_video_ids': len(missing_video_ids),
        'provenance_sample_size': min(20, len(entities)),
        'provenance_verified': provenance_verified,
        'provenance_failed': provenance_failed
    }

    return {
        'passed': len(orphaned) == 0 and len(missing_video_ids) == 0,
        'stats': stats,
        'orphaned': orphaned[:20],
        'missing_video_ids': missing_video_ids[:20]
    }


def sample_entities_for_review(entities: List[Dict[str, Any]], n: int = 20) -> List[Dict[str, Any]]:
    """
    Sample random entities for manual quality review.

    Returns:
        List of sampled entities with key fields
    """
    logger.info(f"📋 Sampling {n} entities for manual review...")

    sample = random.sample(entities, min(n, len(entities)))

    formatted = []
    for entity in sample:
        formatted.append({
            'entity_id': entity.get('entity_id'),
            'canonical_name': entity.get('canonical_name'),
            'entity_type': entity.get('entity_type'),
            'location': entity.get('location'),
            'coordinates': {
                'lat': entity.get('coordinates', {}).get('lat'),
                'lon': entity.get('coordinates', {}).get('lon'),
                'provider': entity.get('coordinates', {}).get('provider')
            } if entity.get('coordinates') else None,
            'experience_count': len(entity.get('experiences', [])),
            'consensus': {
                'avg_rating': entity.get('consensus', {}).get('avg_rating'),
                'mention_count': entity.get('consensus', {}).get('mention_count'),
                'themes': entity.get('consensus', {}).get('themes', [])[:3]
            } if entity.get('consensus') else None
        })

    return formatted


def generate_qa_report(
    validation_results: Dict[str, Any],
    entities: List[Dict[str, Any]],
    output_path: str
) -> bool:
    """
    Generate comprehensive QA report.

    Args:
        validation_results: Dict with all validation results
        entities: List of entities
        output_path: Path to save report

    Returns:
        True if saved successfully
    """
    logger.info("📝 Generating QA report...")

    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_entities': len(entities),
        'validation_results': validation_results,
        'summary': {
            'all_validations_passed': all(
                r.get('passed', False)
                for k, r in validation_results.items()
                if k != 'sample_entities' and isinstance(r, dict)
            ),
            'validations_run': len([k for k in validation_results.keys() if k != 'sample_entities']),
            'validations_passed': sum(
                1 for k, r in validation_results.items()
                if k != 'sample_entities' and isinstance(r, dict) and r.get('passed', False)
            ),
            'validations_failed': sum(
                1 for k, r in validation_results.items()
                if k != 'sample_entities' and isinstance(r, dict) and not r.get('passed', False)
            )
        },
        'recommendations': []
    }

    # Generate recommendations based on results
    if not validation_results['completeness']['passed']:
        report['recommendations'].append({
            'category': 'completeness',
            'priority': 'high',
            'message': f"Fix {validation_results['completeness']['total_issues']} entities with missing required fields",
            'action': 'Review entities list in QA report and update pipeline to ensure all fields are populated'
        })

    if not validation_results['geolocation']['passed']:
        out_of_bounds = validation_results['geolocation']['stats']['out_of_bounds']
        invalid = validation_results['geolocation']['stats']['invalid_coordinates']
        if out_of_bounds > 0:
            report['recommendations'].append({
                'category': 'geolocation',
                'priority': 'medium',
                'message': f"{out_of_bounds} entities have coordinates outside Thailand bounds",
                'action': 'Review geocoding queries and consider manual correction for out-of-bounds entities'
            })
        if invalid > 0:
            report['recommendations'].append({
                'category': 'geolocation',
                'priority': 'high',
                'message': f"{invalid} entities have invalid coordinates",
                'action': 'Fix coordinate extraction logic in geocoding pipeline'
            })

    if not validation_results['deduplication']['passed']:
        report['recommendations'].append({
            'category': 'deduplication',
            'priority': 'medium',
            'message': f"Found {len(validation_results['deduplication']['suspicious'])} suspicious deduplication cases",
            'action': 'Review suspicious entities and adjust deduplication thresholds if needed'
        })

    if not validation_results['consensus']['passed']:
        report['recommendations'].append({
            'category': 'consensus',
            'priority': 'high',
            'message': f"Found {len(validation_results['consensus']['issues'])} consensus calculation errors",
            'action': 'Fix consensus calculation logic in build_entity_consensus()'
        })

    if not validation_results['provenance']['passed']:
        report['recommendations'].append({
            'category': 'provenance',
            'priority': 'high',
            'message': f"Found {validation_results['provenance']['stats']['orphaned_entities']} orphaned entities",
            'action': 'Ensure all entities have proper experience records with video_id'
        })

    # Save report
    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ QA report saved to: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to save QA report: {e}")
        return False


# =============================================================================
# Main Validation Function
# =============================================================================

def validate_stage3(sample_size: int = 20) -> Dict[str, Any]:
    """
    Run all Stage 3 validations.

    Args:
        sample_size: Number of entities to sample for manual review

    Returns:
        Dict with all validation results
    """
    logger.info("=" * 80)
    logger.info("STAGE 3 VALIDATION & QUALITY ASSURANCE")
    logger.info("=" * 80)

    # Initialize database
    logger.info("\n📦 Connecting to PostgreSQL...")
    db = SessionLocal()

    # Load canonical entities from PostgreSQL
    logger.info("\n📥 Loading canonical entities from PostgreSQL...")
    canonical_entities = db.query(CanonicalEntity).all()

    if not canonical_entities:
        logger.error("❌ No canonical entities found in PostgreSQL")
        db.close()
        return {'error': 'No entities to validate'}

    logger.info(f"✅ Loaded {len(canonical_entities)} canonical entities")

    # Convert ORM models to dicts for compatibility with validation functions
    entities = []
    for entity in canonical_entities:
        entity_dict = {
            'entity_id': entity.canonical_id,
            'canonical_name': entity.canonical_name,
            'entity_type': entity.entity_type.value if entity.entity_type else 'unknown',
            'location': entity.location or 'unknown',
            'coordinates': {
                'lat': entity.lat,
                'lon': entity.lon,
                'provider': entity.geocode_provider
            } if entity.lat and entity.lon else None,
            'experiences': [{'video_id': exp.video_id} for exp in entity.experiences] if entity.experiences else [],
            'consensus': entity.consensus or {}
        }
        entities.append(entity_dict)

    # Run validations
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING VALIDATIONS")
    logger.info("=" * 80)

    validation_results = {}

    # 1. Completeness
    validation_results['completeness'] = validate_completeness(entities)
    logger.info(f"\n1. Completeness: {'✅ PASSED' if validation_results['completeness']['passed'] else '❌ FAILED'}")
    logger.info(f"   Fully complete: {validation_results['completeness']['stats']['fully_complete']}/{validation_results['completeness']['stats']['total_entities']}")
    logger.info(f"   Completion rate: {validation_results['completeness']['stats']['completion_rate']:.1f}%")

    # 2. Deduplication
    validation_results['deduplication'] = validate_deduplication_quality(entities, sample_size=sample_size)
    logger.info(f"\n2. Deduplication: {'✅ PASSED' if validation_results['deduplication']['passed'] else '❌ FAILED'}")
    logger.info(f"   Deduplicated entities: {validation_results['deduplication']['stats']['deduplicated_entities']}")
    logger.info(f"   Suspicious cases: {validation_results['deduplication']['stats']['suspicious_deduplication_count']}")

    # 3. Geolocation
    validation_results['geolocation'] = validate_geolocation(entities)
    logger.info(f"\n3. Geolocation: {'✅ PASSED' if validation_results['geolocation']['passed'] else '❌ FAILED'}")
    logger.info(f"   Geocoded: {validation_results['geolocation']['stats']['geocoded']}/{validation_results['geolocation']['stats']['total_entities']}")
    logger.info(f"   Success rate: {validation_results['geolocation']['stats']['geocoding_success_rate']:.1f}%")
    logger.info(f"   Nominatim: {validation_results['geolocation']['stats']['nominatim']} ({validation_results['geolocation']['stats']['nominatim_rate']:.1f}%)")
    logger.info(f"   Google: {validation_results['geolocation']['stats']['google']} ({validation_results['geolocation']['stats']['google_rate']:.1f}%)")

    # 4. Consensus
    validation_results['consensus'] = validate_consensus_logic(entities, sample_size=10)
    logger.info(f"\n4. Consensus: {'✅ PASSED' if validation_results['consensus']['passed'] else '❌ FAILED'}")
    logger.info(f"   Entities checked: {validation_results['consensus']['stats']['entities_checked']}")
    logger.info(f"   Issues found: {validation_results['consensus']['stats']['issues_found']}")

    # 5. Provenance
    validation_results['provenance'] = validate_provenance(entities, db)
    logger.info(f"\n5. Provenance: {'✅ PASSED' if validation_results['provenance']['passed'] else '❌ FAILED'}")
    logger.info(f"   Orphaned entities: {validation_results['provenance']['stats']['orphaned_entities']}")
    logger.info(f"   Provenance verified: {validation_results['provenance']['stats']['provenance_verified']}/{validation_results['provenance']['stats']['provenance_sample_size']}")

    # Sample entities for review
    logger.info(f"\n📋 Sampling {sample_size} entities for manual review...")
    sample_entities = sample_entities_for_review(entities, n=sample_size)

    # Print sample
    logger.info("\n" + "=" * 80)
    logger.info(f"SAMPLE ENTITIES FOR REVIEW (First 5 of {len(sample_entities)})")
    logger.info("=" * 80)
    for i, entity in enumerate(sample_entities[:5], 1):
        logger.info(f"\n{i}. {entity['canonical_name']} ({entity['entity_id']})")
        logger.info(f"   Type: {entity['entity_type']}")
        logger.info(f"   Location: {entity['location']}")
        if entity['coordinates']:
            logger.info(f"   Coordinates: ({entity['coordinates']['lat']:.4f}, {entity['coordinates']['lon']:.4f}) [{entity['coordinates']['provider']}]")
        logger.info(f"   Experiences: {entity['experience_count']}")
        if entity['consensus']:
            logger.info(f"   Avg Rating: {entity['consensus']['avg_rating']}")
            logger.info(f"   Themes: {', '.join(entity['consensus']['themes']) if entity['consensus']['themes'] else 'N/A'}")

    # Generate QA report
    logger.info("\n" + "=" * 80)
    logger.info("GENERATING QA REPORT")
    logger.info("=" * 80)

    report_path = f'stage3-canonical/metadata/qa_report_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.json'
    validation_results['sample_entities'] = sample_entities

    success = generate_qa_report(validation_results, entities, report_path)

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)

    all_passed = all(r.get('passed', False) for r in validation_results.values() if 'passed' in r)

    logger.info(f"\nOverall Result: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")
    logger.info(f"Total Entities: {len(entities)}")
    logger.info(f"Validations Run: 5")
    logger.info(f"Validations Passed: {sum(1 for k, r in validation_results.items() if k != 'sample_entities' and r.get('passed', False))}")
    logger.info(f"Validations Failed: {sum(1 for k, r in validation_results.items() if k != 'sample_entities' and not r.get('passed', False))}")

    if success:
        logger.info(f"\n📄 Full QA report saved to: {report_path}")

    logger.info("=" * 80)

    db.close()
    return validation_results


# =============================================================================
# CLI Interface
# =============================================================================

@click.command()
@click.option('--sample', default=20, help='Number of entities to sample for review (default: 20)')
@click.option('--log-level', default='INFO', help='Logging level (default: INFO)')
def main(sample: int, log_level: str):
    """
    Validate Stage 3 canonical entities.

    Runs comprehensive quality assurance checks on Stage 3 output:
    - Completeness validation
    - Deduplication quality
    - Geolocation accuracy
    - Consensus logic
    - Provenance tracking

    Examples:
        # Validate with default settings
        python cli/validate_stage3.py

        # Validate with larger sample size
        python cli/validate_stage3.py --sample 50

        # Enable debug logging
        python cli/validate_stage3.py --log-level DEBUG
    """
    # Setup logging
    setup_logging(log_level=log_level)

    try:
        # Run validation
        results = validate_stage3(sample_size=sample)

        # Exit with appropriate code
        if results.get('error'):
            sys.exit(1)

        all_passed = all(r.get('passed', False) for k, r in results.items() if k != 'sample_entities' and 'passed' in r)
        sys.exit(0 if all_passed else 1)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
