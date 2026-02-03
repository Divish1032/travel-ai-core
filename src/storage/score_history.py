#!/usr/bin/env python3
"""
Score History - Track entity score evolution over time.

Provides historical tracking of entity scores to:
- Detect trending entities (rapid score increase)
- Identify declining entities (score drop)
- Monitor data quality (score stability)
- Support analytics and reporting

Storage Structure:
    - S3: stage3-canonical/score_history/{entity_id}.json
    - Local cache: cache/score_history/{entity_id}.json

Usage:
    from src.storage.score_history import ScoreHistory

    history = ScoreHistory(s3_storage)

    # Record current scores for an entity
    history.record_scores(entity, run_id="run_20260126_120000")

    # Get score history for an entity
    history_data = history.get_entity_history(entity_id)

    # Detect trending entities
    trending = history.detect_trending_entities(min_increase=0.2)

    # Batch record for all entities
    history.batch_record_scores(all_entities, run_id)
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

SCORE_HISTORY_PREFIX = "stage3-canonical/score_history"
LOCAL_CACHE_DIR = Path("cache/score_history")
MAX_HISTORY_ENTRIES = 100  # Keep last N entries per entity
TRENDING_LOOKBACK_DAYS = 7  # Days to look back for trend detection


# =============================================================================
# Score Fields to Track
# =============================================================================

TRACKED_SCORES = [
    'popularity_score',
    'total_mentions',
    'experience_count',
]

TRACKED_NESTED_SCORES = {
    'data_freshness': ['freshness_score', 'days_since_last_mention'],
    'enhanced_rating': ['rating', 'confidence', 'signal_count'],
    'enrichment_provenance': ['fame_score', 'llm_confidence', 'transcript_mentions'],
}


# =============================================================================
# Score History Class
# =============================================================================

class ScoreHistory:
    """
    Tracks entity score evolution over time.

    Provides methods to:
    - Record scores after each Stage 3 run
    - Query historical scores
    - Detect trending/declining entities
    - Generate analytics reports
    """

    def __init__(self, s3_storage=None, local_only: bool = False):
        """
        Initialize score history tracker.

        Args:
            s3_storage: S3Storage instance for persistence
            local_only: If True, only use local cache
        """
        self.s3 = s3_storage
        self.local_only = local_only

        # In-memory cache for current session
        self._cache: Dict[str, Dict[str, Any]] = {}

        # Ensure local cache directory exists
        LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Recording Scores
    # -------------------------------------------------------------------------

    def record_scores(
        self,
        entity: Dict[str, Any],
        run_id: str,
        timestamp: Optional[str] = None
    ) -> bool:
        """
        Record current scores for an entity.

        Args:
            entity: Canonical entity dict
            run_id: Stage 3 run identifier
            timestamp: Optional timestamp (defaults to now)

        Returns:
            True if recorded successfully
        """
        entity_id = entity.get('entity_id')
        if not entity_id:
            logger.warning("Cannot record scores - entity has no entity_id")
            return False

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Extract scores from entity
        scores = self._extract_scores(entity)

        # Create history entry
        entry = {
            'timestamp': timestamp,
            'run_id': run_id,
            'scores': scores
        }

        # Load existing history
        history = self._load_entity_history(entity_id)

        # Add new entry
        if 'history' not in history:
            history['history'] = []

        history['history'].append(entry)

        # Trim to max entries
        if len(history['history']) > MAX_HISTORY_ENTRIES:
            history['history'] = history['history'][-MAX_HISTORY_ENTRIES:]

        # Update metadata
        history['entity_id'] = entity_id
        history['canonical_name'] = entity.get('canonical_name')
        history['entity_type'] = entity.get('entity_type')
        history['last_updated'] = timestamp
        history['entry_count'] = len(history['history'])

        # Save
        self._save_entity_history(entity_id, history)

        return True

    def batch_record_scores(
        self,
        entities: List[Dict[str, Any]],
        run_id: str,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Record scores for multiple entities.

        Args:
            entities: List of canonical entities
            run_id: Stage 3 run identifier
            timestamp: Optional timestamp (same for all)

        Returns:
            Stats dict with success/failure counts
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        stats = {
            'total': len(entities),
            'recorded': 0,
            'failed': 0
        }

        for entity in entities:
            try:
                if self.record_scores(entity, run_id, timestamp):
                    stats['recorded'] += 1
                else:
                    stats['failed'] += 1
            except Exception as e:
                logger.warning(f"Failed to record scores for {entity.get('entity_id')}: {e}")
                stats['failed'] += 1

        logger.info(f"📊 Recorded score history: {stats['recorded']}/{stats['total']} entities")

        return stats

    def _extract_scores(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tracked scores from entity."""
        scores = {}

        # Top-level scores
        for field in TRACKED_SCORES:
            if field in entity:
                scores[field] = entity[field]

        # Nested scores
        for parent_field, nested_fields in TRACKED_NESTED_SCORES.items():
            if parent_field in entity and entity[parent_field]:
                scores[parent_field] = {}
                for nested in nested_fields:
                    if nested in entity[parent_field]:
                        scores[parent_field][nested] = entity[parent_field][nested]

        # Experience count (derived)
        experiences = entity.get('experiences', [])
        scores['experience_count'] = len(experiences)

        # Video count (derived)
        video_ids = entity.get('source_video_ids', [])
        scores['video_count'] = len(video_ids)

        return scores

    # -------------------------------------------------------------------------
    # Querying History
    # -------------------------------------------------------------------------

    def get_entity_history(
        self,
        entity_id: str,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get score history for an entity.

        Args:
            entity_id: Entity ID to query
            limit: Optional limit on number of entries

        Returns:
            History dict or None if not found
        """
        history = self._load_entity_history(entity_id)

        if not history or 'history' not in history:
            return None

        if limit and len(history['history']) > limit:
            history['history'] = history['history'][-limit:]

        return history

    def get_latest_scores(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent scores for an entity."""
        history = self.get_entity_history(entity_id, limit=1)

        if history and history.get('history'):
            return history['history'][-1].get('scores')

        return None

    def get_score_trend(
        self,
        entity_id: str,
        score_field: str,
        lookback_days: int = TRENDING_LOOKBACK_DAYS
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate trend for a specific score field.

        Args:
            entity_id: Entity ID
            score_field: Field to analyze (e.g., 'popularity_score')
            lookback_days: Days to look back

        Returns:
            Trend analysis dict or None
        """
        history = self._load_entity_history(entity_id)

        if not history or 'history' not in history or len(history['history']) < 2:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_str = cutoff.isoformat()

        # Filter to recent entries
        recent = [
            entry for entry in history['history']
            if entry.get('timestamp', '') >= cutoff_str
        ]

        if len(recent) < 2:
            return None

        # Extract score values
        values = []
        for entry in recent:
            scores = entry.get('scores', {})
            # Handle nested fields
            if '.' in score_field:
                parts = score_field.split('.')
                value = scores.get(parts[0], {}).get(parts[1]) if len(parts) == 2 else None
            else:
                value = scores.get(score_field)

            if value is not None:
                values.append({
                    'timestamp': entry['timestamp'],
                    'value': value
                })

        if len(values) < 2:
            return None

        # Calculate trend
        first_value = values[0]['value']
        last_value = values[-1]['value']
        change = last_value - first_value
        percent_change = (change / first_value * 100) if first_value != 0 else 0

        return {
            'entity_id': entity_id,
            'score_field': score_field,
            'first_value': first_value,
            'last_value': last_value,
            'change': change,
            'percent_change': round(percent_change, 2),
            'data_points': len(values),
            'period_days': lookback_days,
            'trend': 'increasing' if change > 0 else 'decreasing' if change < 0 else 'stable'
        }

    # -------------------------------------------------------------------------
    # Trend Detection
    # -------------------------------------------------------------------------

    def detect_trending_entities(
        self,
        entity_ids: List[str],
        score_field: str = 'popularity_score',
        min_increase: float = 0.1,
        lookback_days: int = TRENDING_LOOKBACK_DAYS
    ) -> List[Dict[str, Any]]:
        """
        Detect entities with significant score increases.

        Args:
            entity_ids: List of entity IDs to check
            score_field: Score field to analyze
            min_increase: Minimum absolute increase to consider trending
            lookback_days: Days to look back

        Returns:
            List of trending entities with trend data
        """
        trending = []

        for entity_id in entity_ids:
            try:
                trend = self.get_score_trend(entity_id, score_field, lookback_days)

                if trend and trend['change'] >= min_increase:
                    trending.append(trend)

            except Exception as e:
                logger.debug(f"Error checking trend for {entity_id}: {e}")

        # Sort by change (descending)
        trending.sort(key=lambda x: x['change'], reverse=True)

        logger.info(f"📈 Found {len(trending)} trending entities "
                   f"(min increase: {min_increase}, field: {score_field})")

        return trending

    def detect_declining_entities(
        self,
        entity_ids: List[str],
        score_field: str = 'data_freshness.freshness_score',
        max_decrease: float = -0.2,
        lookback_days: int = TRENDING_LOOKBACK_DAYS
    ) -> List[Dict[str, Any]]:
        """
        Detect entities with significant score decreases.

        Args:
            entity_ids: List of entity IDs to check
            score_field: Score field to analyze
            max_decrease: Maximum (negative) decrease to consider declining
            lookback_days: Days to look back

        Returns:
            List of declining entities with trend data
        """
        declining = []

        for entity_id in entity_ids:
            try:
                trend = self.get_score_trend(entity_id, score_field, lookback_days)

                if trend and trend['change'] <= max_decrease:
                    declining.append(trend)

            except Exception as e:
                logger.debug(f"Error checking trend for {entity_id}: {e}")

        # Sort by change (ascending - most declined first)
        declining.sort(key=lambda x: x['change'])

        logger.info(f"📉 Found {len(declining)} declining entities "
                   f"(max decrease: {max_decrease}, field: {score_field})")

        return declining

    # -------------------------------------------------------------------------
    # Analytics
    # -------------------------------------------------------------------------

    def generate_score_report(
        self,
        entities: List[Dict[str, Any]],
        lookback_days: int = TRENDING_LOOKBACK_DAYS
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive score analytics report.

        Args:
            entities: List of canonical entities
            lookback_days: Days to look back for trends

        Returns:
            Report dict with trends, stats, and highlights
        """
        entity_ids = [e.get('entity_id') for e in entities if e.get('entity_id')]

        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_entities': len(entity_ids),
            'lookback_days': lookback_days,
            'trending': {},
            'declining': {},
            'summary': {}
        }

        # Analyze key score fields
        score_fields = [
            'popularity_score',
            'enhanced_rating.rating',
            'data_freshness.freshness_score',
            'total_mentions'
        ]

        for field in score_fields:
            try:
                trending = self.detect_trending_entities(
                    entity_ids, field, min_increase=0.1, lookback_days=lookback_days
                )
                declining = self.detect_declining_entities(
                    entity_ids, field, max_decrease=-0.1, lookback_days=lookback_days
                )

                report['trending'][field] = trending[:10]  # Top 10
                report['declining'][field] = declining[:10]  # Top 10

            except Exception as e:
                logger.warning(f"Error analyzing {field}: {e}")

        # Summary stats
        report['summary'] = {
            'total_trending': sum(len(v) for v in report['trending'].values()),
            'total_declining': sum(len(v) for v in report['declining'].values())
        }

        return report

    # -------------------------------------------------------------------------
    # Storage Operations
    # -------------------------------------------------------------------------

    def _load_entity_history(self, entity_id: str) -> Dict[str, Any]:
        """Load history for an entity from cache/storage."""
        # Check in-memory cache first
        if entity_id in self._cache:
            return self._cache[entity_id]

        # Try local cache
        local_path = LOCAL_CACHE_DIR / f"{entity_id}.json"
        if local_path.exists():
            try:
                with open(local_path, 'r') as f:
                    history = json.load(f)
                    self._cache[entity_id] = history
                    return history
            except Exception as e:
                logger.debug(f"Failed to load local history for {entity_id}: {e}")

        # Try S3
        if self.s3 and not self.local_only:
            try:
                s3_key = f"{SCORE_HISTORY_PREFIX}/{entity_id}.json"
                response = self.s3.s3_client.get_object(
                    Bucket=self.s3.bucket_name,
                    Key=s3_key
                )
                content = response['Body'].read().decode('utf-8')
                history = json.loads(content)
                self._cache[entity_id] = history

                # Save to local cache
                self._save_local_cache(entity_id, history)

                return history
            except Exception as e:
                logger.debug(f"Failed to load S3 history for {entity_id}: {e}")

        # Return empty history
        return {'entity_id': entity_id, 'history': []}

    def _save_entity_history(self, entity_id: str, history: Dict[str, Any]) -> bool:
        """Save history for an entity."""
        # Update in-memory cache
        self._cache[entity_id] = history

        # Save to local cache
        self._save_local_cache(entity_id, history)

        # Save to S3 (async would be better for performance)
        if self.s3 and not self.local_only:
            try:
                s3_key = f"{SCORE_HISTORY_PREFIX}/{entity_id}.json"
                self.s3.s3_client.put_object(
                    Bucket=self.s3.bucket_name,
                    Key=s3_key,
                    Body=json.dumps(history, indent=2, default=str),
                    ContentType='application/json'
                )
            except Exception as e:
                logger.warning(f"Failed to save S3 history for {entity_id}: {e}")
                return False

        return True

    def _save_local_cache(self, entity_id: str, history: Dict[str, Any]) -> None:
        """Save to local cache file."""
        try:
            local_path = LOCAL_CACHE_DIR / f"{entity_id}.json"
            with open(local_path, 'w') as f:
                json.dump(history, f, indent=2, default=str)
        except Exception as e:
            logger.debug(f"Failed to save local cache for {entity_id}: {e}")

    def flush_cache(self) -> None:
        """Flush in-memory cache to storage."""
        for entity_id, history in self._cache.items():
            self._save_entity_history(entity_id, history)

        logger.info(f"Flushed {len(self._cache)} entity histories to storage")

    # -------------------------------------------------------------------------
    # Cleanup & Maintenance
    # -------------------------------------------------------------------------

    def cleanup_old_entries(
        self,
        entity_id: str,
        days_to_keep: int = 90
    ) -> int:
        """
        Remove history entries older than specified days.

        Args:
            entity_id: Entity ID to clean up
            days_to_keep: Keep entries from last N days (default: 90)

        Returns:
            Number of entries removed
        """
        history = self._load_entity_history(entity_id)

        if not history or 'history' not in history:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        cutoff_str = cutoff.isoformat()

        original_count = len(history['history'])

        # Keep only recent entries
        history['history'] = [
            entry for entry in history['history']
            if entry.get('timestamp', '') >= cutoff_str
        ]

        removed = original_count - len(history['history'])

        if removed > 0:
            history['last_updated'] = datetime.now(timezone.utc).isoformat()
            history['entry_count'] = len(history['history'])
            self._save_entity_history(entity_id, history)
            logger.info(f"Cleaned {removed} old entries from {entity_id}")

        return removed

    def batch_cleanup_old_entries(
        self,
        entity_ids: List[str],
        days_to_keep: int = 90
    ) -> Dict[str, int]:
        """
        Cleanup old entries for multiple entities.

        Args:
            entity_ids: List of entity IDs to clean up
            days_to_keep: Keep entries from last N days

        Returns:
            Stats dict with cleanup results
        """
        stats = {
            'total': len(entity_ids),
            'cleaned': 0,
            'total_entries_removed': 0
        }

        for entity_id in entity_ids:
            try:
                removed = self.cleanup_old_entries(entity_id, days_to_keep)
                if removed > 0:
                    stats['cleaned'] += 1
                    stats['total_entries_removed'] += removed
            except Exception as e:
                logger.warning(f"Failed to cleanup {entity_id}: {e}")

        logger.info(
            f"Cleanup complete: {stats['cleaned']}/{stats['total']} entities, "
            f"{stats['total_entries_removed']} entries removed"
        )

        return stats

    def trim_history_to_limit(
        self,
        entity_id: str,
        max_entries: int = MAX_HISTORY_ENTRIES
    ) -> int:
        """
        Trim history to maximum number of entries (keeps most recent).

        Args:
            entity_id: Entity ID to trim
            max_entries: Maximum entries to keep

        Returns:
            Number of entries removed
        """
        history = self._load_entity_history(entity_id)

        if not history or 'history' not in history:
            return 0

        original_count = len(history['history'])

        if original_count <= max_entries:
            return 0

        # Keep most recent entries
        history['history'] = history['history'][-max_entries:]

        removed = original_count - len(history['history'])

        history['last_updated'] = datetime.now(timezone.utc).isoformat()
        history['entry_count'] = len(history['history'])
        self._save_entity_history(entity_id, history)

        logger.debug(f"Trimmed {removed} entries from {entity_id} (limit: {max_entries})")

        return removed

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about score history storage."""
        if not self.s3 or self.local_only:
            # Count local files
            local_files = list(LOCAL_CACHE_DIR.glob("*.json"))
            total_size = sum(f.stat().st_size for f in local_files)

            return {
                'total_entities': len(local_files),
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'storage': 'local_only'
            }

        # Count S3 objects
        try:
            response = self.s3.s3_client.list_objects_v2(
                Bucket=self.s3.bucket_name,
                Prefix=f"{SCORE_HISTORY_PREFIX}/"
            )

            if 'Contents' not in response:
                return {'total_entities': 0, 'total_size_bytes': 0}

            total_size = sum(obj['Size'] for obj in response['Contents'])
            total_objects = len([obj for obj in response['Contents'] if obj['Key'].endswith('.json')])

            return {
                'total_entities': total_objects,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'storage': 's3'
            }

        except Exception as e:
            logger.warning(f"Failed to get S3 storage stats: {e}")
            return {'error': str(e)}


# =============================================================================
# Testing
# =============================================================================

def test_score_history():
    """Test score history functionality."""
    logger.info("=" * 80)
    logger.info("SCORE HISTORY TEST")
    logger.info("=" * 80)

    # Create history tracker (local only for testing)
    history = ScoreHistory(local_only=True)

    # Create test entity
    entity = {
        'entity_id': 'test_attraction_001',
        'canonical_name': 'Test Temple',
        'entity_type': 'attraction',
        'popularity_score': 0.5,
        'total_mentions': 3,
        'experiences': [{'exp': 1}, {'exp': 2}, {'exp': 3}],
        'source_video_ids': ['v1', 'v2'],
        'data_freshness': {
            'freshness_score': 1.0,
            'days_since_last_mention': 2
        },
        'enhanced_rating': {
            'rating': 4.2,
            'confidence': 0.8,
            'signal_count': 3
        }
    }

    # Record initial scores
    history.record_scores(entity, 'run_001', '2026-01-20T10:00:00Z')
    logger.info("✅ Recorded initial scores")

    # Simulate score increase
    entity['popularity_score'] = 0.7
    entity['total_mentions'] = 5
    history.record_scores(entity, 'run_002', '2026-01-22T10:00:00Z')
    logger.info("✅ Recorded updated scores")

    # Another update
    entity['popularity_score'] = 0.85
    entity['total_mentions'] = 8
    history.record_scores(entity, 'run_003', '2026-01-25T10:00:00Z')
    logger.info("✅ Recorded final scores")

    # Get history
    entity_history = history.get_entity_history('test_attraction_001')
    assert entity_history is not None
    assert len(entity_history['history']) == 3
    logger.info(f"✅ Retrieved history: {len(entity_history['history'])} entries")

    # Check trend
    trend = history.get_score_trend('test_attraction_001', 'popularity_score', lookback_days=30)
    assert trend is not None
    assert trend['change'] > 0
    assert trend['trend'] == 'increasing'
    logger.info(f"✅ Trend detected: {trend['trend']} ({trend['change']:.2f})")

    # Detect trending
    trending = history.detect_trending_entities(
        ['test_attraction_001'],
        'popularity_score',
        min_increase=0.1
    )
    assert len(trending) == 1
    logger.info(f"✅ Trending detection: {len(trending)} entity")

    # Cleanup test file
    test_file = LOCAL_CACHE_DIR / "test_attraction_001.json"
    if test_file.exists():
        test_file.unlink()

    logger.info("=" * 80)
    logger.info("ALL TESTS PASSED")
    logger.info("=" * 80)


if __name__ == '__main__':
    test_score_history()
