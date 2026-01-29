#!/usr/bin/env python3
"""
Insight Registry - Persistent storage for canonical insight tracking.

Maintains stable insight IDs across Insights Pipeline runs and enables
deduplication by tracking which insights exist and their metadata.

Features:
    - Stable insight ID generation (format: INS_CAT_###)
    - Content-based index for fast insight matching
    - Alias tracking for similar phrasings
    - Processed video tracking to avoid reprocessing
    - S3 + local cache for performance

Usage:
    from src.storage.insight_registry import InsightRegistry

    registry = InsightRegistry(s3_storage)

    # Find existing insight
    insight_id = registry.find_matching_insight(
        content="Use 12goasia for buses",
        category="services",
        scope={"destination_type": "country", "country": "Thailand"}
    )

    # Register new insight
    insight_id = registry.register_new_insight(insight_dict)

    # Check if video already processed
    if registry.is_video_processed("youtube_abc123"):
        skip...
"""

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict

from src.storage.s3 import S3Storage
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

REGISTRY_VERSION = "1.0"
REGISTRY_S3_KEY = "insights-pipeline/registry/insight_registry.json"
PROCESSED_VIDEOS_S3_KEY = "insights-pipeline/registry/video_processing_log.json"
LOCAL_CACHE_DIR = Path("cache/insights_registry")

# Category abbreviations for insight IDs
CATEGORY_ABBREV = {
    "services": "SVC",
    "logistics": "LOG",
    "tips": "TIP",
    "regional": "REG",
    "cultural": "CUL",
    "safety": "SAF",
    "cost_info": "CST",
    "seasonal": "SZN"
}


# =============================================================================
# Content Normalization
# =============================================================================

def normalize_content(content: str) -> str:
    """
    Normalize insight content for matching.

    - Lowercase
    - Remove special characters
    - Collapse whitespace
    """
    if not content:
        return ""

    # Lowercase
    normalized = content.lower().strip()

    # Remove special characters except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip()


def content_hash(content: str, category: str, scope: Dict[str, Any]) -> str:
    """
    Create a unique hash for insight matching.

    Based on normalized content + category + destination scope.
    """
    norm_content = normalize_content(content)
    scope_key = create_scope_key(scope)

    signature = f"{category}||{scope_key}||{norm_content}"
    return hashlib.md5(signature.encode()).hexdigest()


def create_scope_key(scope: Dict[str, Any]) -> str:
    """
    Create a string key from scope dict.

    Examples:
        - {"destination_type": "global"} -> "global"
        - {"destination_type": "country", "country": "Thailand"} -> "country:thailand"
        - {"destination_type": "city", "country": "Thailand", "city": "Bangkok"} -> "city:thailand:bangkok"
    """
    dest_type = scope.get("destination_type", "unknown")

    if dest_type == "global":
        return "global"
    elif dest_type == "region":
        region = (scope.get("region") or "unknown").lower().replace(" ", "_")
        return f"region:{region}"
    elif dest_type == "country":
        country = (scope.get("country") or "unknown").lower().replace(" ", "_")
        return f"country:{country}"
    elif dest_type == "city":
        country = (scope.get("country") or "unknown").lower().replace(" ", "_")
        city = (scope.get("city") or "unknown").lower().replace(" ", "_")
        return f"city:{country}:{city}"
    elif dest_type == "area":
        country = (scope.get("country") or "unknown").lower().replace(" ", "_")
        city = (scope.get("city") or "unknown").lower().replace(" ", "_")
        area = (scope.get("area") or "unknown").lower().replace(" ", "_")
        return f"area:{country}:{city}:{area}"
    else:
        return "unknown"


# =============================================================================
# Insight Registry Class
# =============================================================================

class InsightRegistry:
    """
    Persistent registry for tracking canonical insights across pipeline runs.

    Provides:
    - Stable insight ID generation (format: INS_CAT_###)
    - Fast insight lookup by content hash
    - Alias-based matching
    - Processed video tracking
    """

    def __init__(self, s3_storage: Optional[S3Storage] = None, local_only: bool = False):
        """
        Initialize the insight registry.

        Args:
            s3_storage: S3Storage instance for persistence
            local_only: If True, only use local cache (for testing)
        """
        self.s3 = s3_storage
        self.local_only = local_only

        # Registry data structures
        self.insights: Dict[str, Dict[str, Any]] = {}  # insight_id -> metadata
        self.content_index: Dict[str, str] = {}  # content_hash -> insight_id
        self.alias_index: Dict[str, str] = {}  # alias_hash -> insight_id
        self.next_sequence: Dict[str, int] = defaultdict(int)  # category -> next_seq

        # Processed videos tracking
        self.processed_videos: Dict[str, Dict[str, Any]] = {}  # video_id -> processing info

        # Load existing registry
        self.load()

    # =========================================================================
    # ID Generation
    # =========================================================================

    def generate_insight_id(self, category: str) -> str:
        """
        Generate a new stable insight ID.

        Format: INS_{CAT_ABBREV}_{SEQUENCE:03d}
        Examples:
            - services: INS_SVC_001
            - logistics: INS_LOG_042
            - tips: INS_TIP_123

        Args:
            category: Insight category (services, tips, etc.)

        Returns:
            New insight ID
        """
        # Get category abbreviation
        cat_abbrev = CATEGORY_ABBREV.get(category, "UNK")

        # Get next sequence number for this category
        seq = self.next_sequence[category]
        self.next_sequence[category] += 1

        # Format: INS_CAT_###
        insight_id = f"INS_{cat_abbrev}_{seq:03d}"

        logger.debug(f"Generated insight ID: {insight_id} (category={category}, seq={seq})")
        return insight_id

    # =========================================================================
    # Insight Registration
    # =========================================================================

    def find_matching_insight(
        self,
        content: str,
        category: str,
        scope: Dict[str, Any]
    ) -> Optional[str]:
        """
        Find existing insight that matches the given content.

        Args:
            content: Insight content text
            category: Insight category
            scope: Destination scope dict

        Returns:
            insight_id if match found, None otherwise
        """
        # Create content hash
        hash_key = content_hash(content, category, scope)

        # Check content index
        if hash_key in self.content_index:
            insight_id = self.content_index[hash_key]
            logger.debug(f"Found matching insight: {insight_id} (content hash match)")
            return insight_id

        # Check alias index
        if hash_key in self.alias_index:
            insight_id = self.alias_index[hash_key]
            logger.debug(f"Found matching insight: {insight_id} (alias match)")
            return insight_id

        return None

    def register_new_insight(
        self,
        insight: Dict[str, Any],
        generate_id: bool = True
    ) -> str:
        """
        Register a new insight in the registry.

        Args:
            insight: Insight dict with content, category, scope
            generate_id: If True, generate new ID; if False, use existing insight_id

        Returns:
            insight_id
        """
        # Generate or use existing ID
        if generate_id:
            category = insight.get('category', 'unknown')
            insight_id = self.generate_insight_id(category)
            insight['insight_id'] = insight_id
        else:
            insight_id = insight.get('insight_id')
            if not insight_id:
                raise ValueError("insight_id required when generate_id=False")

        # Create content hash
        hash_key = content_hash(
            content=insight.get('content', ''),
            category=insight.get('category', ''),
            scope=insight.get('scope', {})
        )

        # Register in content index
        self.content_index[hash_key] = insight_id

        # Register aliases if present
        for alias in insight.get('aliases', []):
            alias_hash = content_hash(
                content=alias,
                category=insight.get('category', ''),
                scope=insight.get('scope', {})
            )
            self.alias_index[alias_hash] = insight_id

        # Store metadata
        self.insights[insight_id] = {
            'insight_id': insight_id,
            'category': insight.get('category'),
            'canonical_content': insight.get('content'),
            'scope': insight.get('scope'),
            'mention_count': insight.get('mention_count', 1),
            'video_count': insight.get('video_count', 1),
            'source_video_ids': insight.get('provenance', {}).get('source_video_ids', []),
            'last_seen': datetime.now(timezone.utc).isoformat(),
            'created_at': insight.get('created_at', datetime.now(timezone.utc).isoformat())
        }

        logger.debug(f"Registered new insight: {insight_id}")
        return insight_id

    def update_insight(
        self,
        insight_id: str,
        insight: Dict[str, Any]
    ) -> None:
        """
        Update existing insight metadata.

        Args:
            insight_id: Existing insight ID
            insight: Updated insight dict
        """
        if insight_id not in self.insights:
            logger.warning(f"Insight {insight_id} not found in registry for update")
            return

        # Update metadata
        self.insights[insight_id].update({
            'mention_count': insight.get('mention_count', 1),
            'video_count': insight.get('video_count', 1),
            'source_video_ids': insight.get('provenance', {}).get('source_video_ids', []),
            'last_seen': datetime.now(timezone.utc).isoformat()
        })

        logger.debug(f"Updated insight: {insight_id}")

    # =========================================================================
    # Video Processing Tracking
    # =========================================================================

    def is_video_processed(
        self,
        video_id: str,
        extraction_pass: Optional[str] = None
    ) -> bool:
        """
        Check if a video has already been processed.

        Args:
            video_id: Video ID to check
            extraction_pass: Optional pass filter ("pass1" or "pass2")

        Returns:
            True if video was processed, False otherwise
        """
        if video_id not in self.processed_videos:
            return False

        if extraction_pass:
            # Check if specific pass was processed
            return self.processed_videos[video_id].get(f'{extraction_pass}_processed', False)

        # Check if any pass was processed
        return True

    def mark_video_processed(
        self,
        video_id: str,
        extraction_pass: str,
        insights_contributed: List[str],
        insight_count: int,
        processing_date: str
    ) -> None:
        """
        Mark a video as processed and record contributed insights.

        Args:
            video_id: Video ID
            extraction_pass: "pass1" or "pass2"
            insights_contributed: List of insight IDs extracted from this video
            insight_count: Number of insights extracted
            processing_date: Date string (YYYYMMDD)
        """
        if video_id not in self.processed_videos:
            self.processed_videos[video_id] = {
                'video_id': video_id,
                'first_processed': datetime.now(timezone.utc).isoformat(),
                'pass1_processed': False,
                'pass2_processed': False,
                'insights_contributed': [],
                'total_insight_count': 0
            }

        # Update processing info
        self.processed_videos[video_id].update({
            f'{extraction_pass}_processed': True,
            f'{extraction_pass}_date': processing_date,
            'last_processed': datetime.now(timezone.utc).isoformat()
        })

        # Add contributed insights (avoid duplicates)
        existing_insights = set(self.processed_videos[video_id]['insights_contributed'])
        self.processed_videos[video_id]['insights_contributed'] = list(
            existing_insights | set(insights_contributed)
        )
        self.processed_videos[video_id]['total_insight_count'] += insight_count

        logger.debug(f"Marked video {video_id} as processed ({extraction_pass}, {insight_count} insights)")

    def get_processed_videos(self, extraction_pass: Optional[str] = None) -> List[str]:
        """
        Get list of processed video IDs.

        Args:
            extraction_pass: Optional filter by "pass1" or "pass2"

        Returns:
            List of video IDs
        """
        if not extraction_pass:
            return list(self.processed_videos.keys())

        # Filter by specific pass
        return [
            video_id for video_id, info in self.processed_videos.items()
            if info.get(f'{extraction_pass}_processed', False)
        ]

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dict with statistics
        """
        total_insights = len(self.insights)
        by_category = defaultdict(int)

        for insight_id, metadata in self.insights.items():
            category = metadata.get('category', 'unknown')
            by_category[category] += 1

        return {
            'total_insights': total_insights,
            'insights_by_category': dict(by_category),
            'total_processed_videos': len(self.processed_videos),
            'pass1_videos': len(self.get_processed_videos('pass1')),
            'pass2_videos': len(self.get_processed_videos('pass2')),
            'registry_version': REGISTRY_VERSION,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # Persistence (S3 + Local Cache)
    # =========================================================================

    def load(self) -> None:
        """
        Load registry from S3 or local cache.

        Priority:
        1. Try S3 (if s3_storage provided)
        2. Fall back to local cache
        3. Create new empty registry
        """
        logger.info("📥 Loading insight registry...")

        # Try S3 first
        if self.s3 and not self.local_only:
            if self._load_from_s3():
                logger.info("   ✅ Loaded from S3")
                self._save_to_local_cache()  # Update local cache
                return

        # Fall back to local cache
        if self._load_from_local_cache():
            logger.info("   ✅ Loaded from local cache")
            return

        # Create new empty registry
        logger.info("   ℹ️  No existing registry found - creating new")
        self._initialize_empty_registry()

    def save(self, save_to_s3: bool = True) -> None:
        """
        Save registry to S3 and local cache.

        Args:
            save_to_s3: If True, save to S3 (default: True)
        """
        logger.info("💾 Saving insight registry...")

        # Always save to local cache
        self._save_to_local_cache()
        logger.debug("   ✅ Saved to local cache")

        # Save to S3 if requested
        if save_to_s3 and self.s3 and not self.local_only:
            self._save_to_s3()
            logger.info("   ✅ Saved to S3")

    def _load_from_s3(self) -> bool:
        """Load registry from S3. Returns True if successful."""
        try:
            # Load insight registry
            registry_content = self.s3.s3_client.get_object(
                Bucket=self.s3.bucket_name,
                Key=REGISTRY_S3_KEY
            )['Body'].read().decode('utf-8')

            registry_data = json.loads(registry_content)

            self.insights = registry_data.get('insights', {})
            self.content_index = registry_data.get('content_index', {})
            self.alias_index = registry_data.get('alias_index', {})
            self.next_sequence = defaultdict(int, registry_data.get('next_sequence', {}))

            # Load processed videos
            try:
                videos_content = self.s3.s3_client.get_object(
                    Bucket=self.s3.bucket_name,
                    Key=PROCESSED_VIDEOS_S3_KEY
                )['Body'].read().decode('utf-8')

                self.processed_videos = json.loads(videos_content).get('processed_videos', {})
            except:
                logger.warning("   ⚠️  Processed videos log not found in S3")
                self.processed_videos = {}

            return True

        except Exception as e:
            logger.debug(f"   Could not load from S3: {e}")
            return False

    def _save_to_s3(self) -> None:
        """Save registry to S3."""
        try:
            # Save insight registry
            registry_data = {
                'version': REGISTRY_VERSION,
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'insights': self.insights,
                'content_index': self.content_index,
                'alias_index': self.alias_index,
                'next_sequence': dict(self.next_sequence)
            }

            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=REGISTRY_S3_KEY,
                Body=json.dumps(registry_data, indent=2).encode('utf-8'),
                ContentType='application/json'
            )

            # Save processed videos
            videos_data = {
                'version': REGISTRY_VERSION,
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'processed_videos': self.processed_videos
            }

            self.s3.s3_client.put_object(
                Bucket=self.s3.bucket_name,
                Key=PROCESSED_VIDEOS_S3_KEY,
                Body=json.dumps(videos_data, indent=2).encode('utf-8'),
                ContentType='application/json'
            )

        except Exception as e:
            logger.error(f"   ❌ Failed to save to S3: {e}")
            raise

    def _load_from_local_cache(self) -> bool:
        """Load registry from local cache. Returns True if successful."""
        cache_file = LOCAL_CACHE_DIR / "insight_registry.json"
        videos_file = LOCAL_CACHE_DIR / "video_processing_log.json"

        try:
            # Load insight registry
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    registry_data = json.load(f)

                self.insights = registry_data.get('insights', {})
                self.content_index = registry_data.get('content_index', {})
                self.alias_index = registry_data.get('alias_index', {})
                self.next_sequence = defaultdict(int, registry_data.get('next_sequence', {}))

                # Load processed videos
                if videos_file.exists():
                    with open(videos_file, 'r') as f:
                        self.processed_videos = json.load(f).get('processed_videos', {})
                else:
                    self.processed_videos = {}

                return True

        except Exception as e:
            logger.debug(f"   Could not load from local cache: {e}")
            return False

        return False

    def _save_to_local_cache(self) -> None:
        """Save registry to local cache."""
        try:
            LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # Save insight registry
            cache_file = LOCAL_CACHE_DIR / "insight_registry.json"
            registry_data = {
                'version': REGISTRY_VERSION,
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'insights': self.insights,
                'content_index': self.content_index,
                'alias_index': self.alias_index,
                'next_sequence': dict(self.next_sequence)
            }

            with open(cache_file, 'w') as f:
                json.dump(registry_data, f, indent=2)

            # Save processed videos
            videos_file = LOCAL_CACHE_DIR / "video_processing_log.json"
            videos_data = {
                'version': REGISTRY_VERSION,
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'processed_videos': self.processed_videos
            }

            with open(videos_file, 'w') as f:
                json.dump(videos_data, f, indent=2)

        except Exception as e:
            logger.warning(f"   ⚠️  Could not save to local cache: {e}")

    def _initialize_empty_registry(self) -> None:
        """Initialize empty registry structures."""
        self.insights = {}
        self.content_index = {}
        self.alias_index = {}
        self.next_sequence = defaultdict(int)
        self.processed_videos = {}


# =============================================================================
# Testing
# =============================================================================

if __name__ == '__main__':
    # Test registry functionality
    from src.utils.logging import setup_logging
    setup_logging(log_level='DEBUG')

    registry = InsightRegistry(local_only=True)

    # Test ID generation
    insight_id = registry.generate_insight_id("services")
    print(f"Generated ID: {insight_id}")

    # Test insight registration
    test_insight = {
        'content': "Use 12goasia for booking buses in Thailand",
        'category': "services",
        'scope': {"destination_type": "country", "country": "Thailand"},
        'mention_count': 1,
        'video_count': 1,
        'provenance': {'source_video_ids': ['youtube_test123']}
    }

    insight_id = registry.register_new_insight(test_insight)
    print(f"Registered insight: {insight_id}")

    # Test matching
    match_id = registry.find_matching_insight(
        content="Use 12goasia for booking buses in Thailand",
        category="services",
        scope={"destination_type": "country", "country": "Thailand"}
    )
    print(f"Found match: {match_id}")

    # Test statistics
    stats = registry.get_statistics()
    print(f"Registry stats: {json.dumps(stats, indent=2)}")

    print("✅ Registry tests passed!")
