"""
Data loader utilities for TravelAI Dashboard

Handles loading data from S3 with caching and processing.
"""

import sys
from pathlib import Path
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.utils.config import config


@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_metadata_tracker() -> Dict[str, Any]:
    """Load metadata tracker data from S3"""
    try:
        storage = S3Storage()
        tracker = MetadataTracker(storage)

        # Load data from S3
        tracker.load_from_s3()

        # Get all content items
        all_content = tracker.get_all_items()

        return all_content
    except Exception as e:
        st.error(f"Failed to load metadata: {e}")
        return {}


@st.cache_data(ttl=600)
def get_videos_summary() -> pd.DataFrame:
    """Get summary of all videos with their stage status"""
    metadata = load_metadata_tracker()

    if not metadata:
        return pd.DataFrame()

    videos = []
    for content_id, data in metadata.items():
        # Get stages info
        stages = data.get('stages', {})

        # Check stage status
        stage_1 = stages.get('stage_1_crawl', {})
        stage_2 = stages.get('stage_2_extract', {})
        stage_3 = stages.get('stage_3_deduplicate', {})

        # Map 'complete' to 'completed' for consistency
        def normalize_status(status):
            if status == 'complete':
                return 'completed'
            return status

        stage_1_status = normalize_status(stage_1.get('status', 'pending')) if stage_1 else 'pending'
        stage_2_status = normalize_status(stage_2.get('status', 'pending')) if stage_2 else 'not_started'
        stage_3_status = normalize_status(stage_3.get('status', 'pending')) if stage_3 else 'not_started'

        # Get S3 paths from stages (with safety checks for empty arrays)
        s3_paths = {}
        if stage_1:
            stage1_paths = stage_1.get('s3_paths', [])
            s3_paths['stage_1_raw'] = stage1_paths[0] if stage1_paths else None
        if stage_2:
            stage2_paths = stage_2.get('s3_paths', [])
            s3_paths['stage_2_extracted'] = stage2_paths[0] if stage2_paths else None
        if stage_3:
            stage3_paths = stage_3.get('s3_paths', [])
            s3_paths['stage_3_processed'] = stage3_paths[0] if stage3_paths else None

        # Get metadata
        title = data.get('title', 'Unknown')

        # Get duration from stage 1 metadata if available
        duration_seconds = 0
        if stage_1 and 'metadata' in stage_1:
            duration_seconds = stage_1['metadata'].get('duration_seconds', 0)
            
        # Get language from stage 1 metadata if available
        language = 'unknown'
        if stage_1 and 'metadata' in stage_1:
            language = stage_1['metadata'].get('language', 'unknown')
            
        # Get author from stage 1 metadata if available
        author = 'unknown'
        if stage_1 and 'metadata' in stage_1:
            author = stage_1['metadata'].get('author', 'unknown')

        videos.append({
            'video_id': content_id,
            'title': title,
            'author': author,
            'duration_seconds': duration_seconds,
            'language': language,
            'stage_1': stage_1_status,
            'stage_2': stage_2_status,
            'stage_3': stage_3_status,
            'upload_date': data.get('added_at', 'Unknown'),
            'last_modified': data.get('last_updated', 'Unknown'),
            's3_paths': s3_paths
        })

    df = pd.DataFrame(videos)

    # Add derived columns
    if not df.empty:
        df['duration_formatted'] = df['duration_seconds'].apply(lambda x: f"{x//60}m {x%60}s" if x > 0 else 'Unknown')
        df['all_stages_complete'] = (df['stage_1'] == 'completed') & (df['stage_2'] == 'completed') & (df['stage_3'] == 'completed')

    return df


@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_video_stage1(video_id: str) -> Optional[Dict[str, Any]]:
    """Load Stage 1 data for a specific video"""
    try:
        metadata = load_metadata_tracker()
        video_meta = metadata.get(video_id, {})

        # Extract S3 path from stages structure
        stages = video_meta.get('stages', {})
        stage_1 = stages.get('stage_1_crawl', {})
        stage1_paths = stage_1.get('s3_paths', [])
        stage1_path = stage1_paths[0] if stage1_paths else None

        if not stage1_path:
            return None

        storage = S3Storage()

        # Parse S3 path
        path_parts = stage1_path.replace('s3://', '').split('/', 1)
        if len(path_parts) != 2:
            return None

        bucket, key = path_parts

        # Download from S3
        response = storage.s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')

        return json.loads(content)
    except Exception as e:
        st.error(f"Failed to load Stage 1 data: {e}")
        return None


@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_video_stage2(video_id: str) -> Optional[Dict[str, Any]]:
    """Load Stage 2 data for a specific video"""
    try:
        metadata = load_metadata_tracker()
        video_meta = metadata.get(video_id, {})

        # Extract S3 path from stages structure
        stages = video_meta.get('stages', {})
        stage_2 = stages.get('stage_2_extract', {})
        stage2_paths = stage_2.get('s3_paths', [])
        stage2_path = stage2_paths[0] if stage2_paths else None

        storage = S3Storage()

        # If path from metadata doesn't work, try the actual location
        paths_to_try = []
        if stage2_path:
            path_parts = stage2_path.replace('s3://', '').split('/', 1)
            if len(path_parts) == 2:
                paths_to_try.append(path_parts[1])

        # Add fallback path (actual location in S3)
        source_id = video_meta.get('source_id', video_id.replace('youtube_', ''))
        fallback_key = f"stage2-extracted/stage3_extracted/youtube_video_{source_id}_extracted.jsonl"
        paths_to_try.append(fallback_key)

        # Try each path
        for key in paths_to_try:
            try:
                response = storage.s3_client.get_object(Bucket=storage.bucket_name, Key=key)
                content = response['Body'].read().decode('utf-8')
                return json.loads(content)
            except storage.s3_client.exceptions.NoSuchKey:
                continue
            except Exception:
                continue

        return None
    except Exception as e:
        st.error(f"Failed to load Stage 2 data: {e}")
        return None


@st.cache_data(ttl=600)  # Cache for 10 minutes
def load_video_stage3(video_id: str) -> Optional[Dict[str, Any]]:
    """Load Stage 3 data for a specific video

    Note: Stage 3 data may be embedded in metadata rather than separate files.
    Returns None if no separate S3 file exists.
    """
    try:
        metadata = load_metadata_tracker()
        video_meta = metadata.get(video_id, {})

        # Extract S3 path from stages structure
        stages = video_meta.get('stages', {})
        stage_3 = stages.get('stage_3_deduplicate', {})

        # Stage 3 data might be in metadata itself
        stage3_metadata = stage_3.get('metadata', {})
        if stage3_metadata and 'canonical_entity_ids' in stage3_metadata:
            # Return metadata as stage 3 data
            return {
                'canonical_entities': [],  # Empty list, IDs are in metadata
                'canonical_entity_ids': stage3_metadata.get('canonical_entity_ids', []),
                'total_entities_contributed': stage3_metadata.get('total_entities_contributed', 0),
                'deduplication_rate': stage3_metadata.get('deduplication_rate', 0.0),
                'stage3_to_canonical_mapping': stage3_metadata.get('stage3_to_canonical_mapping', {})
            }

        # Try loading from S3 if path exists
        stage3_paths = stage_3.get('s3_paths', [])
        stage3_path = stage3_paths[0] if stage3_paths else None

        if not stage3_path:
            return None

        storage = S3Storage()

        # Parse S3 path
        path_parts = stage3_path.replace('s3://', '').split('/', 1)
        if len(path_parts) != 2:
            return None

        bucket, key = path_parts

        try:
            # Download from S3
            response = storage.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except storage.s3_client.exceptions.NoSuchKey:
            # File doesn't exist, return None (not an error)
            return None

    except Exception as e:
        # Only show error for unexpected exceptions
        return None


def _fetch_video_entities_parallel(video_id: str, metadata: Dict[str, Any], storage: S3Storage) -> List[Dict[str, Any]]:
    """
    Helper function to fetch entities for a single video (for parallel execution).
    Does NOT use Streamlit caching to avoid ScriptRunContext warnings in threads.
    """
    try:
        video_meta = metadata.get(video_id, {})
        if not video_meta:
            return []

        # Extract S3 path from stages structure
        stages = video_meta.get('stages', {})
        stage_2 = stages.get('stage_2_extract', {})
        stage2_paths = stage_2.get('s3_paths', [])
        stage2_path = stage2_paths[0] if stage2_paths else None

        # Try paths
        paths_to_try = []
        if stage2_path:
            path_parts = stage2_path.replace('s3://', '').split('/', 1)
            if len(path_parts) == 2:
                paths_to_try.append(path_parts[1])

        # Add fallback path
        source_id = video_meta.get('source_id', video_id.replace('youtube_', ''))
        fallback_key = f"stage2-extracted/stage3_extracted/youtube_video_{source_id}_extracted.jsonl"
        paths_to_try.append(fallback_key)

        # Try each path
        stage2_data = None
        for key in paths_to_try:
            try:
                response = storage.s3_client.get_object(Bucket=storage.bucket_name, Key=key)
                content = response['Body'].read().decode('utf-8')
                stage2_data = json.loads(content)
                break
            except storage.s3_client.exceptions.NoSuchKey:
                continue
            except Exception:
                continue

        if not stage2_data:
            return []

        # Extract entities
        entities = stage2_data.get('entities', [])
        result = []
        for entity in entities:
            result.append({
                'video_id': video_id,
                'entity_name': entity.get('entity_name', 'Unknown'),
                'entity_type': entity.get('entity_type', 'unknown'),
                'location': entity.get('location', 'Unknown'),
                'sentiment': entity.get('sentiment', 'neutral'),
                'quality_score': entity.get('quality_score', 0),
                'confidence_score': entity.get('confidence_score', 0)
            })
        return result
    except Exception:
        # Silently skip failed videos (no st.error in thread)
        return []


@st.cache_data(ttl=1200)
def load_all_entities() -> pd.DataFrame:
    """Load and aggregate all entities from Stage 2 across all videos using parallel S3 fetching"""
    try:
        videos_df = get_videos_summary()
        # Filter for stage 2 completed (handles both 'complete' and 'completed')
        stage2_complete = videos_df[videos_df['stage_2'].isin(['completed', 'complete'])]

        if stage2_complete.empty:
            return pd.DataFrame()

        # Load metadata and create storage object once (shared across threads)
        metadata = load_metadata_tracker()
        storage = S3Storage()

        all_entities = []
        video_ids = stage2_complete['video_id'].tolist()

        # Use ThreadPoolExecutor for parallel S3 fetching
        # Limit to 20 workers to avoid overwhelming S3 API
        max_workers = min(20, len(video_ids))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all fetch tasks with shared metadata and storage
            future_to_video = {
                executor.submit(_fetch_video_entities_parallel, video_id, metadata, storage): video_id
                for video_id in video_ids
            }

            # Collect results as they complete
            for future in as_completed(future_to_video):
                try:
                    entities = future.result()
                    all_entities.extend(entities)
                except Exception:
                    # Skip failed videos
                    continue

        return pd.DataFrame(all_entities)
    except Exception as e:
        st.error(f"Failed to load entities: {e}")
        return pd.DataFrame()


def get_dashboard_stats() -> Dict[str, Any]:
    """Calculate dashboard statistics"""
    videos_df = get_videos_summary()

    # Default stats if no data
    default_stats = {
        'total_videos': 0,
        'stage1_complete': 0,
        'stage2_complete': 0,
        'stage3_complete': 0,
        'all_stages_complete': 0,
        'total_entities': 0,
        'unique_entities': 0,
        'success_rate': 0
    }

    if videos_df.empty:
        return default_stats

    stats = {
        'total_videos': len(videos_df),
        'stage1_complete': len(videos_df[videos_df['stage_1'].isin(['completed', 'complete'])]),
        'stage2_complete': len(videos_df[videos_df['stage_2'].isin(['completed', 'complete'])]),
        'stage3_complete': len(videos_df[videos_df['stage_3'].isin(['completed', 'complete'])]),
        'all_stages_complete': len(videos_df[videos_df['all_stages_complete']]),
        'success_rate': (len(videos_df[videos_df['all_stages_complete']]) / len(videos_df) * 100) if len(videos_df) > 0 else 0
    }

    # Count entities
    entities_df = load_all_entities()
    stats['total_entities'] = len(entities_df) if not entities_df.empty else 0

    # Unique entities
    if not entities_df.empty:
        stats['unique_entities'] = entities_df['entity_name'].nunique()
    else:
        stats['unique_entities'] = 0

    return stats


def format_status(status: str) -> str:
    """Format status with emoji"""
    status_map = {
        'completed': '✅ Completed',
        'pending': '⏳ Pending',
        'failed': '❌ Failed',
        'not_started': '⚪ Not Started',
        'unknown': '❓ Unknown'
    }
    return status_map.get(status, status)
