"""
Insights Pipeline Storage Manager

Handles saving travel insights to S3 in multiple formats:
- Single JSONL file with all insights
- Grouped by category (services, tips, logistics, etc.)
- Grouped by destination (country, city, region)
- Processing metadata and stats
- Audit trails for quality review

Usage:
    from src.storage.insights_storage import InsightsStorage

    storage = InsightsStorage(s3_storage)

    # Save extracted insights (Pass 1 or Pass 2)
    result = storage.save_extracted_insights(
        insights=extracted_insights,
        extraction_pass="pass1",
        processing_date='2026-01-27'
    )

    # Save canonical insights after deduplication
    result = storage.save_canonical_insights(
        insights=canonical_insights,
        processing_date='2026-01-27',
        stats={...}
    )
"""

import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from collections import defaultdict

from src.storage.s3 import S3Storage
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InsightsStorage:
    """
    Manages Insights Pipeline storage in S3.

    Provides multiple output formats for extracted and canonical insights.
    """

    def __init__(self, s3_storage: S3Storage):
        """
        Initialize Insights storage manager.

        Args:
            s3_storage: S3Storage instance for uploading files
        """
        self.s3 = s3_storage
        self.extracted_prefix = 'insights-pipeline/extracted'
        self.canonical_prefix = 'insights-pipeline/canonical'
        self.registry_prefix = 'insights-pipeline/registry'
        self.filtered_prefix = 'insights-pipeline/filtered'

    def save_extracted_insights(
        self,
        insights: List[Dict[str, Any]],
        extraction_pass: str,
        processing_date: str
    ) -> Dict[str, Any]:
        """
        Save extracted insights to S3 (raw, before deduplication).

        Args:
            insights: List of extracted TravelInsight dicts
            extraction_pass: "pass1" (entities) or "pass2" (transcripts)
            processing_date: Date string (YYYYMMDD) for versioning

        Returns:
            Dict with save results and S3 paths

        Example:
            >>> storage = InsightsStorage(s3)
            >>> result = storage.save_extracted_insights(
            ...     insights=extracted_insights,
            ...     extraction_pass="pass1",
            ...     processing_date='20260127'
            ... )
            >>> print(result['s3_path'])
            s3://bucket/insights-pipeline/extracted/new/pass1_entities_20260127.jsonl
        """
        logger.info(f"💾 Saving {len(insights)} extracted insights ({extraction_pass})...")

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"{extraction_pass}_{processing_date}_{timestamp}.jsonl"
        s3_key = f"{self.extracted_prefix}/new/{filename}"

        try:
            # Convert to JSONL format (handle datetime objects)
            def json_serializer(obj):
                """JSON serializer for objects not serializable by default json code"""
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")

            jsonl_content = '\n'.join([json.dumps(insight, default=json_serializer) for insight in insights])

            # Upload to S3
            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=s3_key,
                Body=jsonl_content.encode('utf-8'),
                ContentType='application/x-ndjson',
                Metadata={
                    'insight_count': str(len(insights)),
                    'extraction_pass': extraction_pass,
                    'processing_date': processing_date,
                    'uploaded_at': datetime.now(timezone.utc).isoformat()
                }
            )

            s3_path = f"s3://{self.s3.bucket_name}/{s3_key}"
            logger.info(f"   ✅ Saved to: {s3_path}")

            return {
                'success': True,
                'file_saved': filename,
                's3_key': s3_key,
                's3_path': s3_path,
                'insight_count': len(insights),
                'extraction_pass': extraction_pass
            }

        except Exception as e:
            logger.error(f"   ❌ Failed to save extracted insights: {e}")
            return {
                'success': False,
                'error': str(e),
                'insight_count': len(insights),
                'extraction_pass': extraction_pass
            }

    def save_canonical_insights(
        self,
        insights: List[Dict[str, Any]],
        processing_date: str,
        dedup_stats: Optional[Dict[str, Any]] = None,
        quality_stats: Optional[Dict[str, Any]] = None,
        cost_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save canonical insights in multiple formats after deduplication.

        Creates 4 types of files:
        1. insights_all.jsonl - All insights in one file
        2. by_category/{category}.jsonl - Grouped by category
        3. by_destination/{destination}.jsonl - Grouped by destination
        4. metadata/processing_stats.json - Processing statistics

        Args:
            insights: List of canonical CanonicalInsight dicts
            processing_date: Date string (YYYYMMDD) for versioning
            dedup_stats: Deduplication statistics
            quality_stats: Quality filtering statistics
            cost_stats: Cost breakdown

        Returns:
            Dict with save results and S3 paths
        """
        logger.info(f"💾 Saving {len(insights)} canonical insights in multiple formats...")

        results = {
            'success': True,
            'files_saved': [],
            'errors': [],
            'insight_count': len(insights)
        }

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

        try:
            # 1. Save all insights in one file
            all_insights_key = f"{self.canonical_prefix}/insights_all_{timestamp}.jsonl"
            all_path = self._save_jsonl(
                insights=insights,
                s3_key=all_insights_key,
                metadata={'insight_count': str(len(insights))}
            )
            results['files_saved'].append(all_path)
            results['insights_all_path'] = all_path
            logger.info(f"   ✅ Saved all insights: {all_path}")

            # 2. Save grouped by category
            by_category = self._group_by_category(insights)
            for category, category_insights in by_category.items():
                category_key = f"{self.canonical_prefix}/by_category/{category}_{timestamp}.jsonl"
                category_path = self._save_jsonl(
                    insights=category_insights,
                    s3_key=category_key,
                    metadata={
                        'category': category,
                        'insight_count': str(len(category_insights))
                    }
                )
                results['files_saved'].append(category_path)
            logger.info(f"   ✅ Saved {len(by_category)} category files")

            # 3. Save grouped by destination
            by_destination = self._group_by_destination(insights)
            for dest_key, dest_insights in by_destination.items():
                dest_s3_key = f"{self.canonical_prefix}/by_destination/{dest_key}_{timestamp}.jsonl"
                dest_path = self._save_jsonl(
                    insights=dest_insights,
                    s3_key=dest_s3_key,
                    metadata={
                        'destination': dest_key,
                        'insight_count': str(len(dest_insights))
                    }
                )
                results['files_saved'].append(dest_path)
            logger.info(f"   ✅ Saved {len(by_destination)} destination files")

            # 4. Save processing statistics
            if dedup_stats or quality_stats or cost_stats:
                stats_key = f"{self.canonical_prefix}/metadata/processing_stats_{timestamp}.json"
                stats_content = {
                    'metadata': {
                        'processing_date': processing_date,
                        'generated_at': datetime.now(timezone.utc).isoformat(),
                        'pipeline': 'insights',
                        'version': '1.0'
                    },
                    'insight_counts': {
                        'total': len(insights),
                        'by_category': {cat: len(ins) for cat, ins in by_category.items()},
                        'by_destination': {dest: len(ins) for dest, ins in by_destination.items()}
                    },
                    'deduplication': dedup_stats or {},
                    'quality': quality_stats or {},
                    'costs': cost_stats or {}
                }

                self.s3.s3_client.put_object(
                    Bucket=self.s3.bucket_name,
                    Key=stats_key,
                    Body=json.dumps(stats_content, indent=2).encode('utf-8'),
                    ContentType='application/json'
                )

                stats_path = f"s3://{self.s3.bucket_name}/{stats_key}"
                results['files_saved'].append(stats_path)
                results['stats_path'] = stats_path
                logger.info(f"   ✅ Saved processing stats: {stats_path}")

            logger.info(f"✅ Saved {len(results['files_saved'])} files successfully")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to save canonical insights: {e}")
            results['success'] = False
            results['errors'].append(str(e))
            return results

    def save_filtered_insights(
        self,
        filtered_insights: List[Dict[str, Any]],
        processing_date: str
    ) -> Dict[str, Any]:
        """
        Save low-quality filtered insights.

        Args:
            filtered_insights: List of filtered out insights
            processing_date: Date string (YYYYMMDD)

        Returns:
            Dict with save results
        """
        if not filtered_insights:
            logger.info("   No filtered insights to save")
            return {'success': True, 'insight_count': 0}

        logger.info(f"💾 Saving {len(filtered_insights)} filtered insights...")

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filtered_key = f"{self.filtered_prefix}/filtered_{processing_date}_{timestamp}.jsonl"

        try:
            filtered_path = self._save_jsonl(
                insights=filtered_insights,
                s3_key=filtered_key,
                metadata={'insight_count': str(len(filtered_insights))}
            )

            logger.info(f"   ✅ Saved filtered insights: {filtered_path}")

            return {
                'success': True,
                'file_saved': filtered_path,
                'insight_count': len(filtered_insights)
            }

        except Exception as e:
            logger.error(f"   ❌ Failed to save filtered insights: {e}")
            return {
                'success': False,
                'error': str(e),
                'insight_count': len(filtered_insights)
            }

    def load_extracted_insights(
        self,
        extraction_pass: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Load all extracted insights from S3 (before deduplication).

        Args:
            extraction_pass: Filter by "pass1" or "pass2", or None for all

        Returns:
            List of extracted insight dicts
        """
        logger.info(f"📥 Loading extracted insights (pass={extraction_pass or 'all'})...")

        prefix = f"{self.extracted_prefix}/new/"
        all_insights = []

        try:
            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                logger.warning("   No extracted insights found in S3")
                return []

            files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.jsonl')]

            # Filter by extraction pass if specified
            if extraction_pass:
                files = [f for f in files if extraction_pass in f]

            logger.info(f"   Found {len(files)} insight files to load")

            for s3_key in files:
                content = self.s3.s3_client.get_object(
                    Bucket=self.s3.bucket_name,
                    Key=s3_key
                )['Body'].read().decode('utf-8')

                # Parse JSONL
                for line in content.strip().split('\n'):
                    if line.strip():
                        all_insights.append(json.loads(line))

            logger.info(f"   ✅ Loaded {len(all_insights)} insights from {len(files)} files")
            return all_insights

        except Exception as e:
            logger.error(f"   ❌ Failed to load extracted insights: {e}")
            return []

    def load_all_canonical_insights(self) -> List[Dict[str, Any]]:
        """
        Load the most recent canonical insights file.

        Returns:
            List of canonical insight dicts
        """
        logger.info("📥 Loading canonical insights from S3...")

        prefix = f"{self.canonical_prefix}/"

        try:
            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                logger.warning("   No canonical insights found in S3")
                return []

            # Find the most recent insights_all_*.jsonl file
            insight_files = []
            for obj in response['Contents']:
                s3_key = obj['Key']
                if 'insights_all_' in s3_key and s3_key.endswith('.jsonl'):
                    insight_files.append({
                        'key': s3_key,
                        'last_modified': obj['LastModified']
                    })

            if not insight_files:
                logger.warning("   No insights_all_*.jsonl files found")
                return []

            # Sort by last modified time and get the most recent
            insight_files.sort(key=lambda x: x['last_modified'], reverse=True)
            latest_file = insight_files[0]['key']

            logger.info(f"   Loading most recent file: {latest_file}")

            # Load the file
            content = self.s3.s3_client.get_object(
                Bucket=self.s3.bucket_name,
                Key=latest_file
            )['Body'].read().decode('utf-8')

            # Parse JSONL
            insights = []
            for line in content.strip().split('\n'):
                if line.strip():
                    insights.append(json.loads(line))

            logger.info(f"   ✅ Loaded {len(insights)} canonical insights")
            return insights

        except Exception as e:
            logger.error(f"   ❌ Failed to load canonical insights: {e}")
            return []

    def move_processed_files(self) -> Dict[str, Any]:
        """
        Move extracted insights from new/ to processed/ after deduplication.

        Returns:
            Dict with move results
        """
        logger.info("📦 Moving processed insight files from new/ to processed/...")

        source_prefix = f"{self.extracted_prefix}/new/"
        dest_prefix = f"{self.extracted_prefix}/processed/"

        try:
            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=source_prefix
            )

            if 'Contents' not in response:
                logger.info("   No files to move")
                return {'success': True, 'files_moved': 0}

            files_to_move = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.jsonl')]
            moved_count = 0

            for source_key in files_to_move:
                filename = source_key.split('/')[-1]
                dest_key = f"{dest_prefix}{filename}"

                # Copy to new location
                self.s3.s3_client.copy_object(
                    Bucket=self.s3.bucket_name,
                    CopySource={'Bucket': self.s3.bucket_name, 'Key': source_key},
                    Key=dest_key
                )

                # Delete from old location
                self.s3.s3_client.delete_object(
                    Bucket=self.s3.bucket_name,
                    Key=source_key
                )

                moved_count += 1
                logger.debug(f"   Moved: {filename}")

            logger.info(f"   ✅ Moved {moved_count} files to processed/")

            return {
                'success': True,
                'files_moved': moved_count
            }

        except Exception as e:
            logger.error(f"   ❌ Failed to move processed files: {e}")
            return {
                'success': False,
                'error': str(e),
                'files_moved': 0
            }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _save_jsonl(
        self,
        insights: List[Dict[str, Any]],
        s3_key: str,
        metadata: Dict[str, str]
    ) -> str:
        """
        Save insights as JSONL to S3.

        Args:
            insights: List of insight dicts
            s3_key: S3 key path
            metadata: S3 object metadata

        Returns:
            Full S3 path (s3://bucket/key)
        """
        # JSON serializer for datetime objects
        def json_serializer(obj):
            """JSON serializer for objects not serializable by default json code"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        jsonl_content = '\n'.join([json.dumps(insight, default=json_serializer) for insight in insights])

        self.s3.s3_client.put_object(
            Bucket=self.s3.bucket_name,
            Key=s3_key,
            Body=jsonl_content.encode('utf-8'),
            ContentType='application/x-ndjson',
            Metadata=metadata
        )

        return f"s3://{self.s3.bucket_name}/{s3_key}"

    def _group_by_category(
        self,
        insights: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group insights by category.

        Returns:
            Dict mapping category -> list of insights
        """
        by_category = defaultdict(list)
        for insight in insights:
            category = insight.get('category', 'unknown')
            by_category[category].append(insight)
        return dict(by_category)

    def _group_by_destination(
        self,
        insights: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group insights by destination.

        Creates destination keys based on scope:
        - global: "global"
        - region: "region_{region_name}"
        - country: "{country_name}"
        - city: "{country_name}_{city_name}"
        - area: "{country_name}_{city_name}_{area_name}"

        Returns:
            Dict mapping destination key -> list of insights
        """
        by_destination = defaultdict(list)

        for insight in insights:
            scope = insight.get('scope', {})
            dest_type = scope.get('destination_type', 'unknown')

            if dest_type == 'global':
                dest_key = 'global'
            elif dest_type == 'region':
                region = scope.get('region', 'unknown_region').lower().replace(' ', '_')
                dest_key = f"region_{region}"
            elif dest_type == 'country':
                country = scope.get('country', 'unknown').lower().replace(' ', '_')
                dest_key = country
            elif dest_type == 'city':
                country = scope.get('country', 'unknown').lower().replace(' ', '_')
                city = scope.get('city', 'unknown').lower().replace(' ', '_')
                dest_key = f"{country}_{city}"
            elif dest_type == 'area':
                country = scope.get('country', 'unknown').lower().replace(' ', '_')
                city = scope.get('city', 'unknown').lower().replace(' ', '_')
                area = scope.get('area', 'unknown').lower().replace(' ', '_')
                dest_key = f"{country}_{city}_{area}"
            else:
                dest_key = 'unknown'

            by_destination[dest_key].append(insight)

        return dict(by_destination)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_insights_output(
    insights: List[Dict[str, Any]],
    min_confidence: float = 0.60
) -> Dict[str, Any]:
    """
    Validate insights output quality.

    Args:
        insights: List of insight dicts to validate
        min_confidence: Minimum confidence score threshold

    Returns:
        Dict with validation results
    """
    issues = []
    warnings = []

    for idx, insight in enumerate(insights):
        # Check required fields
        required_fields = ['insight_id', 'category', 'content', 'scope', 'confidence_score']
        missing_fields = [f for f in required_fields if f not in insight]

        if missing_fields:
            issues.append(f"Insight {idx}: Missing required fields: {missing_fields}")

        # Check confidence score
        if 'confidence_score' in insight:
            confidence = insight['confidence_score']
            if confidence < min_confidence:
                warnings.append(f"Insight {idx}: Low confidence score: {confidence:.2f}")

        # Check content length
        if 'content' in insight:
            content_len = len(insight['content'])
            if content_len < 10:
                issues.append(f"Insight {idx}: Content too short ({content_len} chars)")
            elif content_len > 1000:
                warnings.append(f"Insight {idx}: Content very long ({content_len} chars)")

        # Check mention count
        if 'mention_count' in insight:
            mentions = insight['mention_count']
            if mentions < 1:
                issues.append(f"Insight {idx}: Invalid mention_count: {mentions}")

    is_valid = len(issues) == 0

    return {
        'is_valid': is_valid,
        'total_insights': len(insights),
        'issues': issues,
        'warnings': warnings,
        'validation_summary': f"{'✅ Valid' if is_valid else '❌ Invalid'} - {len(issues)} issues, {len(warnings)} warnings"
    }
