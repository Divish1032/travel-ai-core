"""
Stage 3 Storage Manager

Handles saving canonical entities with consensus to S3 in multiple formats:
- Single JSONL file with all entities
- Grouped by city
- Grouped by entity type
- Processing metadata and stats
- Audit trails for quality review

Usage:
    from src.storage.stage3_storage import Stage3Storage

    storage = Stage3Storage(s3_storage)

    # Save canonical entities in all formats
    result = storage.save_canonical_entities(
        entities=canonical_entities,
        processing_date='2025-12-08',
        stats={...}
    )

    # Validate output
    validation = storage.validate_stage3_output(canonical_entities)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from loguru import logger
from src.storage.s3 import S3Storage


class Stage3Storage:
    """
    Manages Stage 3 canonical entity storage in S3.

    Provides multiple output formats and comprehensive validation.
    """

    def __init__(self, s3_storage: S3Storage):
        """
        Initialize Stage 3 storage manager.

        Args:
            s3_storage: S3Storage instance for uploading files
        """
        self.s3 = s3_storage
        self.base_prefix = 'stage3-canonical/new'

    def save_canonical_entities(
        self,
        entities: List[Dict[str, Any]],
        processing_date: str,
        dedup_stats: Optional[Dict[str, Any]] = None,
        geocode_stats: Optional[Dict[str, Any]] = None,
        consensus_stats: Optional[Dict[str, Any]] = None,
        cost_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save canonical entities in multiple formats.

        Creates 4 types of files:
        1. entities_all.jsonl - All entities in one file
        2. by_city/{city}.jsonl - Grouped by city
        3. by_type/{type}.jsonl - Grouped by entity type
        4. metadata/processing_stats.json - Processing statistics

        Args:
            entities: List of canonical entities with consensus
            processing_date: Date string (YYYY-MM-DD) for versioning
            dedup_stats: Deduplication statistics
            geocode_stats: Geocoding statistics
            consensus_stats: Consensus calculation statistics
            cost_stats: Cost breakdown (LLM + geocoding)

        Returns:
            Dict with save results and S3 paths

        Example:
            >>> storage = Stage3Storage(s3)
            >>> result = storage.save_canonical_entities(
            ...     entities=canonical_entities,
            ...     processing_date='2025-12-08',
            ...     dedup_stats={...},
            ...     geocode_stats={...}
            ... )
            >>> print(result['entities_all_path'])
            s3://bucket/stage3-canonical/entities_all_20251208.jsonl
        """
        logger.info(f"💾 Saving {len(entities)} canonical entities in multiple formats...")

        results = {
            'success': True,
            'files_saved': [],
            'errors': [],
            'entity_count': len(entities)
        }

        # Generate timestamp for file versioning
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        date_str = processing_date.replace('-', '')

        # 1. Save all entities in one JSONL file
        try:
            all_path = self._save_entities_all(entities, date_str, timestamp)
            results['entities_all_path'] = all_path
            results['files_saved'].append(all_path)
            logger.info(f"✅ Saved all entities: {all_path}")
        except Exception as e:
            error_msg = f"Failed to save entities_all.jsonl: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            results['success'] = False

        # 2. Save entities grouped by city
        try:
            city_paths = self._save_entities_by_city(entities, date_str, timestamp)
            results['by_city_paths'] = city_paths
            results['files_saved'].extend(city_paths.values())
            logger.info(f"✅ Saved {len(city_paths)} city files")
        except Exception as e:
            error_msg = f"Failed to save by_city files: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)

        # 3. Save entities grouped by type
        try:
            type_paths = self._save_entities_by_type(entities, date_str, timestamp)
            results['by_type_paths'] = type_paths
            results['files_saved'].extend(type_paths.values())
            logger.info(f"✅ Saved {len(type_paths)} entity type files")
        except Exception as e:
            error_msg = f"Failed to save by_type files: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)

        # 4. Save processing metadata
        try:
            stats_path = self._save_processing_stats(
                entities=entities,
                processing_date=processing_date,
                timestamp=timestamp,
                dedup_stats=dedup_stats,
                geocode_stats=geocode_stats,
                consensus_stats=consensus_stats,
                cost_stats=cost_stats
            )
            results['stats_path'] = stats_path
            results['files_saved'].append(stats_path)
            logger.info(f"✅ Saved processing stats: {stats_path}")
        except Exception as e:
            error_msg = f"Failed to save processing_stats.json: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)

        if results['success']:
            logger.info(f"✅ Successfully saved {len(results['files_saved'])} files to S3")
        else:
            logger.warning(f"⚠️  Saved with {len(results['errors'])} errors")

        return results

    def _save_entities_all(
        self,
        entities: List[Dict[str, Any]],
        date_str: str,
        timestamp: str
    ) -> str:
        """
        Save all entities in one JSONL file.

        Format: One JSON object per line
        Path: stage3-canonical/entities_all_YYYYMMDD_HHMMSS.jsonl

        Args:
            entities: List of canonical entities
            date_str: Date string (YYYYMMDD)
            timestamp: Timestamp string (YYYYMMDD_HHMMSS)

        Returns:
            S3 path of saved file
        """
        # Convert to JSONL
        jsonl_lines = []
        for entity in entities:
            jsonl_lines.append(json.dumps(entity, ensure_ascii=False))

        jsonl_content = '\n'.join(jsonl_lines)

        # Upload to S3
        s3_key = f'{self.base_prefix}/entities_all_{timestamp}.jsonl'

        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=s3_key,
            Body=jsonl_content.encode('utf-8'),
            ContentType='application/x-ndjson',
            Metadata={
                'entity_count': str(len(entities)),
                'processing_date': date_str,
                'uploaded_at': datetime.now(timezone.utc).isoformat()
            }
        )

        return f's3://{self.s3.bucket_name}/{s3_key}'

    def _save_entities_by_city(
        self,
        entities: List[Dict[str, Any]],
        date_str: str,
        timestamp: str
    ) -> Dict[str, str]:
        """
        Save entities grouped by city.

        Creates one JSONL file per city.
        Path: stage3-canonical/by_city/{city}_{timestamp}.jsonl

        Args:
            entities: List of canonical entities
            date_str: Date string (YYYYMMDD)
            timestamp: Timestamp string (YYYYMMDD_HHMMSS)

        Returns:
            Dict mapping city name to S3 path
        """
        # Group entities by city
        by_city = defaultdict(list)

        for entity in entities:
            location = entity.get('location', 'unknown')

            # Handle location being string or dict
            if isinstance(location, dict):
                city = location.get('city', 'unknown')
            elif isinstance(location, str):
                city = location
            else:
                city = 'unknown'

            # Normalize city name for file path
            city_normalized = city.lower().replace(' ', '_').replace('/', '_')
            by_city[city_normalized].append(entity)

        # Save each city's entities
        city_paths = {}

        for city, city_entities in by_city.items():
            # Convert to JSONL
            jsonl_lines = []
            for entity in city_entities:
                jsonl_lines.append(json.dumps(entity, ensure_ascii=False))

            jsonl_content = '\n'.join(jsonl_lines)

            # Upload to S3
            s3_key = f'{self.base_prefix}/by_city/{city}_{timestamp}.jsonl'

            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=s3_key,
                Body=jsonl_content.encode('utf-8'),
                ContentType='application/x-ndjson',
                Metadata={
                    'city': city,
                    'entity_count': str(len(city_entities)),
                    'processing_date': date_str,
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            )

            city_paths[city] = f's3://{self.s3.bucket_name}/{s3_key}'

        return city_paths

    def _save_entities_by_type(
        self,
        entities: List[Dict[str, Any]],
        date_str: str,
        timestamp: str
    ) -> Dict[str, str]:
        """
        Save entities grouped by entity type.

        Creates one JSONL file per entity type.
        Path: stage3-canonical/by_type/{type}_{timestamp}.jsonl

        Args:
            entities: List of canonical entities
            date_str: Date string (YYYYMMDD)
            timestamp: Timestamp string (YYYYMMDD_HHMMSS)

        Returns:
            Dict mapping entity type to S3 path
        """
        # Group entities by type
        by_type = defaultdict(list)

        for entity in entities:
            entity_type = entity.get('entity_type', 'unknown')
            by_type[entity_type].append(entity)

        # Save each type's entities
        type_paths = {}

        for entity_type, type_entities in by_type.items():
            # Convert to JSONL
            jsonl_lines = []
            for entity in type_entities:
                jsonl_lines.append(json.dumps(entity, ensure_ascii=False))

            jsonl_content = '\n'.join(jsonl_lines)

            # Upload to S3
            s3_key = f'{self.base_prefix}/by_type/{entity_type}_{timestamp}.jsonl'

            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=s3_key,
                Body=jsonl_content.encode('utf-8'),
                ContentType='application/x-ndjson',
                Metadata={
                    'entity_type': entity_type,
                    'entity_count': str(len(type_entities)),
                    'processing_date': date_str,
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            )

            type_paths[entity_type] = f's3://{self.s3.bucket_name}/{s3_key}'

        return type_paths

    def _save_processing_stats(
        self,
        entities: List[Dict[str, Any]],
        processing_date: str,
        timestamp: str,
        dedup_stats: Optional[Dict[str, Any]] = None,
        geocode_stats: Optional[Dict[str, Any]] = None,
        consensus_stats: Optional[Dict[str, Any]] = None,
        cost_stats: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save processing statistics and metadata.

        Path: stage3-canonical/metadata/processing_stats_{timestamp}.json

        Args:
            entities: List of canonical entities
            processing_date: Processing date string
            timestamp: Timestamp string
            dedup_stats: Deduplication statistics
            geocode_stats: Geocoding statistics
            consensus_stats: Consensus statistics
            cost_stats: Cost breakdown

        Returns:
            S3 path of saved file
        """
        # Calculate entity counts by city and type
        by_city_counts = defaultdict(int)
        by_type_counts = defaultdict(int)
        geocoded_count = 0
        with_consensus_count = 0

        for entity in entities:
            # Count by city
            location = entity.get('location', 'unknown')
            if isinstance(location, dict):
                city = location.get('city', 'unknown')
            elif isinstance(location, str):
                city = location
            else:
                city = 'unknown'
            by_city_counts[city] += 1

            # Count by type
            entity_type = entity.get('entity_type', 'unknown')
            by_type_counts[entity_type] += 1

            # Count geocoded
            if 'coordinates' in entity:
                geocoded_count += 1

            # Count with consensus
            if 'consensus' in entity:
                with_consensus_count += 1

        # Build stats document
        stats = {
            'metadata': {
                'processing_date': processing_date,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'stage': 'stage3_canonical',
                'version': '1.0'
            },
            'entity_counts': {
                'total': len(entities),
                'geocoded': geocoded_count,
                'with_consensus': with_consensus_count,
                'by_city': dict(by_city_counts),
                'by_type': dict(by_type_counts)
            },
            'deduplication': dedup_stats or {},
            'geocoding': geocode_stats or {},
            'consensus': consensus_stats or {},
            'costs': cost_stats or {}
        }

        # Convert to JSON
        json_content = json.dumps(stats, indent=2, ensure_ascii=False)

        # Upload to S3
        s3_key = f'{self.base_prefix}/metadata/processing_stats_{timestamp}.json'

        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=s3_key,
            Body=json_content.encode('utf-8'),
            ContentType='application/json',
            Metadata={
                'processing_date': processing_date,
                'entity_count': str(len(entities)),
                'uploaded_at': datetime.now(timezone.utc).isoformat()
            }
        )

        return f's3://{self.s3.bucket_name}/{s3_key}'

    def save_audit_trail(
        self,
        dedup_log: Dict[str, Any],
        processing_date: str
    ) -> str:
        """
        Save deduplication audit trail for quality review.

        Records all deduplication decisions including:
        - Match candidates considered
        - Similarity scores
        - LLM verification results
        - Final grouping decisions

        Path: stage3-canonical/metadata/deduplication_audit_{date}.json

        Args:
            dedup_log: Deduplication decisions and match details
            processing_date: Processing date string (YYYY-MM-DD)

        Returns:
            S3 path of saved file

        Example:
            >>> audit_trail = {
            ...     'total_entities': 100,
            ...     'total_groups': 85,
            ...     'matches': [
            ...         {
            ...             'entity1': 'ATT_001',
            ...             'entity2': 'ATT_002',
            ...             'similarity': 0.92,
            ...             'llm_verified': True,
            ...             'grouped': True
            ...         }
            ...     ]
            ... }
            >>> path = storage.save_audit_trail(audit_trail, '2025-12-08')
        """
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        date_str = processing_date.replace('-', '')

        # Add metadata
        audit_data = {
            'metadata': {
                'processing_date': processing_date,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'purpose': 'deduplication_quality_review'
            },
            'audit_trail': dedup_log
        }

        # Convert to JSON
        json_content = json.dumps(audit_data, indent=2, ensure_ascii=False)

        # Upload to S3
        s3_key = f'{self.base_prefix}/metadata/deduplication_audit_{date_str}_{timestamp}.json'

        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=s3_key,
            Body=json_content.encode('utf-8'),
            ContentType='application/json',
            Metadata={
                'processing_date': date_str,
                'uploaded_at': datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(f"✅ Saved deduplication audit trail: s3://{self.s3.bucket_name}/{s3_key}")
        return f's3://{self.s3.bucket_name}/{s3_key}'

    def save_geocoding_cache(
        self,
        cache: Dict[str, Any],
        cache_name: str = 'geocoding_cache'
    ) -> str:
        """
        Save geocoding cache for reuse in future processing.

        Geocoding is expensive (rate limited or paid), so caching results
        allows us to skip re-geocoding entities that haven't changed.

        Path: stage3-canonical/metadata/{cache_name}.json

        Args:
            cache: Dict mapping entity_id to geocoding results
            cache_name: Name for the cache file (default: 'geocoding_cache')

        Returns:
            S3 path of saved file

        Example:
            >>> cache = {
            ...     'ATT_001': {
            ...         'lat': 13.7463456,
            ...         'lon': 100.4927381,
            ...         'provider': 'nominatim',
            ...         'confidence': 0.9
            ...     }
            ... }
            >>> path = storage.save_geocoding_cache(cache)
        """
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        # Add metadata
        cache_data = {
            'metadata': {
                'cache_version': '1.0',
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'total_entries': len(cache)
            },
            'cache': cache
        }

        # Convert to JSON
        json_content = json.dumps(cache_data, indent=2, ensure_ascii=False)

        # Upload to S3
        s3_key = f'{self.base_prefix}/metadata/{cache_name}_{timestamp}.json'

        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=s3_key,
            Body=json_content.encode('utf-8'),
            ContentType='application/json',
            Metadata={
                'cache_entries': str(len(cache)),
                'uploaded_at': datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(f"✅ Saved geocoding cache ({len(cache)} entries): s3://{self.s3.bucket_name}/{s3_key}")
        return f's3://{self.s3.bucket_name}/{s3_key}'

    def validate_stage3_output(
        self,
        entities: List[Dict[str, Any]],
        stage2_entity_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Validate Stage 3 output for quality and completeness.

        Checks:
        1. All required fields present
        2. No data loss from Stage 2 (entity count comparison)
        3. Coordinate validity (within Thailand bounds)
        4. Consensus calculations look reasonable
        5. Data types are correct

        Args:
            entities: List of canonical entities to validate
            stage2_entity_count: Original entity count from Stage 2 (optional)

        Returns:
            Validation report with:
            - is_valid: Overall validation status
            - errors: List of validation errors
            - warnings: List of validation warnings
            - stats: Validation statistics

        Example:
            >>> validation = storage.validate_stage3_output(canonical_entities)
            >>> if not validation['is_valid']:
            ...     print(f"Validation failed: {validation['errors']}")
        """
        logger.info(f"🔍 Validating {len(entities)} canonical entities...")

        errors = []
        warnings = []
        stats = {
            'total_entities': len(entities),
            'entities_with_coordinates': 0,
            'entities_with_consensus': 0,
            'entities_with_experiences': 0,
            'invalid_coordinates': 0,
            'missing_required_fields': 0
        }

        # Required fields for canonical entities
        required_fields = [
            'entity_id',
            'canonical_name',
            'entity_type',
            'location',
            'total_mentions',
            'source_video_ids'
        ]

        # Thailand bounding box
        THAILAND_LAT_MIN, THAILAND_LAT_MAX = 5.0, 21.0
        THAILAND_LON_MIN, THAILAND_LON_MAX = 97.0, 106.0

        for i, entity in enumerate(entities):
            entity_id = entity.get('entity_id', f'unknown_{i}')

            # Check required fields
            missing_fields = [field for field in required_fields if field not in entity]
            if missing_fields:
                errors.append(f"Entity {entity_id} missing required fields: {missing_fields}")
                stats['missing_required_fields'] += 1

            # Validate coordinates if present
            if 'coordinates' in entity:
                stats['entities_with_coordinates'] += 1
                coords = entity['coordinates']

                # Check coordinate structure
                if not isinstance(coords, dict):
                    errors.append(f"Entity {entity_id} has invalid coordinates structure")
                elif 'lat' not in coords or 'lon' not in coords:
                    errors.append(f"Entity {entity_id} coordinates missing lat/lon")
                else:
                    lat = coords['lat']
                    lon = coords['lon']

                    # Validate Thailand bounds
                    if not (THAILAND_LAT_MIN <= lat <= THAILAND_LAT_MAX and
                            THAILAND_LON_MIN <= lon <= THAILAND_LON_MAX):
                        errors.append(
                            f"Entity {entity_id} coordinates out of Thailand bounds: "
                            f"({lat:.4f}, {lon:.4f})"
                        )
                        stats['invalid_coordinates'] += 1

                    # Check confidence score
                    confidence = coords.get('confidence')
                    if confidence is not None and (confidence < 0 or confidence > 1):
                        warnings.append(f"Entity {entity_id} has invalid confidence: {confidence}")

            # Validate consensus if present
            if 'consensus' in entity:
                stats['entities_with_consensus'] += 1
                consensus = entity['consensus']

                # Check consensus structure
                if not isinstance(consensus, dict):
                    errors.append(f"Entity {entity_id} has invalid consensus structure")
                else:
                    # Check overall rating
                    rating = consensus.get('overall_rating')
                    if rating is not None and (rating < 0 or rating > 5):
                        errors.append(f"Entity {entity_id} has invalid rating: {rating}")

                    # Check total mentions
                    mentions = consensus.get('total_mentions', 0)
                    entity_mentions = entity.get('total_mentions', 0)
                    if mentions != entity_mentions:
                        warnings.append(
                            f"Entity {entity_id} consensus mentions ({mentions}) "
                            f"doesn't match entity mentions ({entity_mentions})"
                        )

            # Check experiences
            if 'experiences' in entity:
                experiences = entity['experiences']
                if isinstance(experiences, list):
                    stats['entities_with_experiences'] += 1

                    # Verify experience count matches total_mentions
                    if len(experiences) != entity.get('total_mentions', 0):
                        warnings.append(
                            f"Entity {entity_id} experience count ({len(experiences)}) "
                            f"doesn't match total_mentions ({entity.get('total_mentions')})"
                        )

        # Check for data loss from Stage 2
        if stage2_entity_count is not None:
            if len(entities) > stage2_entity_count:
                warnings.append(
                    f"Entity count increased from Stage 2 ({stage2_entity_count}) "
                    f"to Stage 3 ({len(entities)}). This should not happen."
                )
            elif len(entities) < stage2_entity_count * 0.5:
                warnings.append(
                    f"Significant entity reduction from Stage 2 ({stage2_entity_count}) "
                    f"to Stage 3 ({len(entities)}). Verify deduplication is correct."
                )

        # Calculate validation status
        is_valid = len(errors) == 0

        validation_report = {
            'is_valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'stats': stats,
            'summary': {
                'total_errors': len(errors),
                'total_warnings': len(warnings),
                'validation_passed': is_valid
            }
        }

        # Log results
        if is_valid:
            logger.info(f"✅ Validation passed ({len(warnings)} warnings)")
        else:
            logger.error(f"❌ Validation failed with {len(errors)} errors")

        if warnings:
            logger.warning(f"⚠️  {len(warnings)} validation warnings")

        return validation_report

    def load_all_canonical_entities(self) -> List[Dict[str, Any]]:
        """
        Load all canonical entities from S3.

        Loads ONLY the most recent entities_all_*.jsonl file to avoid duplicates
        from multiple runs. Older files are kept for versioning/backup.

        Returns:
            List of all canonical entities

        Example:
            >>> storage = Stage3Storage(s3)
            >>> entities = storage.load_all_canonical_entities()
            >>> print(f"Loaded {len(entities)} entities")
        """
        try:
            # List all files in stage3-canonical/new/
            logger.info(f"Loading canonical entities from s3://{self.s3.bucket_name}/{self.base_prefix}/")

            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=self.base_prefix + '/'
            )

            if 'Contents' not in response:
                logger.warning(f"No canonical entities found in s3://{self.s3.bucket_name}/{self.base_prefix}/")
                return []

            # Find the most recent entities_all_*.jsonl file
            entity_files = []
            for obj in response['Contents']:
                s3_key = obj['Key']

                # Skip directory markers
                if s3_key.endswith('/'):
                    continue

                # Only consider entities_all_*.jsonl files
                if 'entities_all_' in s3_key and s3_key.endswith('.jsonl'):
                    entity_files.append({
                        'key': s3_key,
                        'last_modified': obj['LastModified']
                    })

            if not entity_files:
                logger.warning(f"No entities_all_*.jsonl files found in {self.base_prefix}/")
                return []

            # Sort by last modified time and get the most recent
            entity_files.sort(key=lambda x: x['last_modified'], reverse=True)
            latest_file = entity_files[0]['key']

            logger.info(f"Loading latest entity file: {latest_file}")
            if len(entity_files) > 1:
                logger.debug(f"Found {len(entity_files)} entity files, using most recent")

            # Load the latest file
            all_entities = []
            try:
                # Download file
                file_response = self.s3.s3_client.get_object(
                    Bucket=self.s3.bucket_name,
                    Key=latest_file
                )
                content = file_response['Body'].read().decode('utf-8')

                # Parse JSONL
                for line in content.strip().split('\n'):
                    if line.strip():
                        entity = json.loads(line)
                        all_entities.append(entity)

            except Exception as e:
                logger.error(f"Failed to load {latest_file}: {e}")
                return []

            logger.info(f"✅ Loaded {len(all_entities)} canonical entities from {latest_file}")
            return all_entities

        except Exception as e:
            logger.error(f"Failed to load canonical entities: {e}")
            return []


# =============================================================================
# Testing
# =============================================================================

def test_stage3_storage():
    """
    Test Stage 3 storage with sample entities.

    Creates sample canonical entities and saves them in all formats.
    """
    from src.storage.s3 import S3Storage

    logger.info("=" * 80)
    logger.info("STAGE 3 STORAGE TEST")
    logger.info("=" * 80)

    # Initialize storage
    s3 = S3Storage()
    storage = Stage3Storage(s3)

    # Create sample entities
    sample_entities = [
        {
            'entity_id': 'attraction_bangkok_001',
            'canonical_name': 'Wat Pho',
            'aliases': ['Wat Phra Chetuphon'],
            'entity_type': 'attraction',
            'location': 'Bangkok',
            'total_mentions': 2,
            'source_video_ids': ['video_1', 'video_2'],
            'coordinates': {
                'lat': 13.7463456,
                'lon': 100.4927381,
                'confidence': 0.9,
                'provider': 'nominatim'
            },
            'consensus': {
                'overall_rating': 4.5,
                'total_mentions': 2,
                'best_for': ['culture_enthusiast'],
                'common_themes': ['temple', 'architecture', 'buddha']
            },
            'experiences': [
                {'experience': 'Amazing temple with huge reclining Buddha'},
                {'experience': 'Beautiful architecture and peaceful atmosphere'}
            ]
        },
        {
            'entity_id': 'attraction_chiangmai_002',
            'canonical_name': 'Doi Suthep',
            'aliases': ['Wat Phra That Doi Suthep'],
            'entity_type': 'attraction',
            'location': 'Chiang Mai',
            'total_mentions': 1,
            'source_video_ids': ['video_3'],
            'coordinates': {
                'lat': 18.8166077,
                'lon': 98.89236,
                'confidence': 0.85,
                'provider': 'nominatim'
            },
            'consensus': {
                'overall_rating': 4.8,
                'total_mentions': 1,
                'best_for': ['nature_lover'],
                'common_themes': ['mountain', 'temple', 'view']
            },
            'experiences': [
                {'experience': 'Stunning mountain temple with amazing views'}
            ]
        }
    ]

    # Test validation
    logger.info("\n🔍 Testing validation...")
    validation = storage.validate_stage3_output(sample_entities, stage2_entity_count=2)
    logger.info(f"Validation result: {validation['is_valid']}")
    logger.info(f"Errors: {len(validation['errors'])}")
    logger.info(f"Warnings: {len(validation['warnings'])}")

    # Test saving (commented out to avoid actual S3 upload during test)
    # logger.info("\n💾 Testing save...")
    # result = storage.save_canonical_entities(
    #     entities=sample_entities,
    #     processing_date='2025-12-08',
    #     geocode_stats={'total': 2, 'success': 2}
    # )
    # logger.info(f"Save result: {result['success']}")
    # logger.info(f"Files saved: {len(result['files_saved'])}")

    logger.info("\n✅ Stage 3 storage test complete!")
    return validation


if __name__ == '__main__':
    test_stage3_storage()
