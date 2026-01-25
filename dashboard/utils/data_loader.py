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

        # Try to fetch the object; if missing, surface a friendly message instead of an error
        try:
            response = storage.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except storage.s3_client.exceptions.NoSuchKey:
            st.info("Stage 1 data file not found in S3 for this video.")
            return None
        except Exception as e:
            st.info(f"Stage 1 data unavailable: {e}")
            return None
    except Exception:
        # Silent failure to avoid noisy UI; caller handles None
        st.info("Stage 1 data could not be loaded.")
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
    """Calculate dashboard statistics using Stage 3 canonical entities"""
    videos_df = get_videos_summary()

    # Default stats if no data
    default_stats = {
        'total_videos': 0,
        'stage1_complete': 0,
        'stage2_complete': 0,
        'stage3_complete': 0,
        'all_stages_complete': 0,
        'canonical_entities': 0,
        'avg_entity_rating': 0,
        'geocoded_pct': 0,
        'with_enrichment_pct': 0,
        'success_rate': 0
    }

    if videos_df.empty:
        return default_stats

    # Start with default stats to ensure all keys exist
    stats = default_stats.copy()
    stats.update({
        'total_videos': len(videos_df),
        'stage1_complete': len(videos_df[videos_df['stage_1'].isin(['completed', 'complete'])]),
        'stage2_complete': len(videos_df[videos_df['stage_2'].isin(['completed', 'complete'])]),
        'stage3_complete': len(videos_df[videos_df['stage_3'].isin(['completed', 'complete'])]),
        'all_stages_complete': len(videos_df[videos_df['all_stages_complete']]),
        'success_rate': (len(videos_df[videos_df['all_stages_complete']]) / len(videos_df) * 100) if len(videos_df) > 0 else 0
    })

    # Load Stage 3 canonical entities (deduplicated, enriched)
    try:
        canonical_df = load_stage3_canonical_entities()
    except Exception:
        canonical_df = pd.DataFrame()

    if not canonical_df.empty:
        stats['canonical_entities'] = len(canonical_df)

        # Average entity rating (quality metric)
        if 'avg_rating' in canonical_df.columns:
            ratings = canonical_df['avg_rating'].dropna()
            stats['avg_entity_rating'] = ratings.mean() if len(ratings) > 0 else 0
        else:
            stats['avg_entity_rating'] = 0

        # Geocoding coverage
        if 'lat' in canonical_df.columns and 'lon' in canonical_df.columns:
            geocoded = canonical_df['lat'].notna().sum()
            stats['geocoded_pct'] = (geocoded / len(canonical_df) * 100) if len(canonical_df) > 0 else 0
        else:
            stats['geocoded_pct'] = 0

        # Enrichment coverage (NEW v2.0 - entities with temporal or logistics info)
        if 'temporal_confidence' in canonical_df.columns or 'logistics_confidence' in canonical_df.columns:
            temporal_count = canonical_df.get('temporal_confidence', pd.Series()).notna().sum()
            logistics_count = canonical_df.get('logistics_confidence', pd.Series()).notna().sum()
            enriched = max(temporal_count, logistics_count)  # At least one type of enrichment
            stats['with_enrichment_pct'] = (enriched / len(canonical_df) * 100) if len(canonical_df) > 0 else 0
        else:
            stats['with_enrichment_pct'] = 0

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


@st.cache_data(ttl=300)  # Cache for 5 minutes to avoid repeated S3 calls
def download_metadata_tracker_file() -> bytes:
    """
    Download the raw metadata tracker file from S3.
    Cached for 5 minutes to avoid repeated S3 calls.
    
    Returns:
        Raw file content as bytes (JSONL format)
        
    Raises:
        Exception: If download fails
    """
    try:
        storage = S3Storage()
        tracker = MetadataTracker(storage)
        
        # Build S3 URI for metadata tracker file
        s3_uri = f"s3://{storage.bucket_name}/{tracker.METADATA_PATH}"
        
        # Download raw file content
        bucket, key = storage._parse_s3_uri(s3_uri)
        response = storage.s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read()
        
        return content
    except Exception as e:
        raise Exception(f"Failed to download metadata tracker file: {e}")


def load_metadata_tracker_jsonl() -> List[Dict[str, Any]]:
    """
    Load and parse the metadata tracker JSONL file from S3.

    Returns:
        List of dictionaries, one per line in the JSONL file

    Raises:
        Exception: If download or parsing fails
    """
    try:
        storage = S3Storage()
        tracker = MetadataTracker(storage)

        # Build S3 URI for metadata tracker file
        s3_uri = f"s3://{storage.bucket_name}/{tracker.METADATA_PATH}"

        # Download and parse JSONL
        data = storage.download_jsonl(s3_uri)

        return data
    except Exception as e:
        raise Exception(f"Failed to load metadata tracker JSONL: {e}")


@st.cache_data(ttl=1200)  # Cache for 20 minutes
def load_stage3_canonical_entities() -> pd.DataFrame:
    """
    Load Stage 3 canonical entities from S3.

    Stage 3 entities are deduplicated, enriched, and include:
    - Consensus data (avg_rating, mention_count, themes, profile_metrics)
    - Geolocation (coordinates with lat/lon)
    - Temporal info (best_seasons, best_times_of_day, typical_duration)
    - Logistics info (transport_options, booking_required, accessibility)
    - Popularity and freshness scores
    - All experiences from multiple videos aggregated

    Returns:
        DataFrame with canonical entities

    Example columns:
        entity_id, canonical_name, aliases, entity_type, location, city, country,
        lat, lon, total_mentions, avg_rating, popularity_score, freshness_score,
        best_seasons, transport_options, etc.
    """
    try:
        storage = S3Storage()

        # List all files in stage3-canonical/new/ directory
        prefix = 'stage3-canonical/new/'

        try:
            response = storage.s3_client.list_objects_v2(
                Bucket=storage.bucket_name,
                Prefix=prefix
            )
        except Exception:
            return pd.DataFrame()

        if 'Contents' not in response:
            return pd.DataFrame()

        # Find ALL entities_all_*.jsonl files (there may be multiple per entity type)
        entity_files = []
        for obj in response['Contents']:
            s3_key = obj['Key']
            if 'entities_all_' in s3_key and s3_key.endswith('.jsonl'):
                entity_files.append(s3_key)

        if not entity_files:
            return pd.DataFrame()

        # Load and combine ALL entity files
        all_entities = []
        for s3_key in entity_files:
            try:
                file_response = storage.s3_client.get_object(
                    Bucket=storage.bucket_name,
                    Key=s3_key
                )
                content = file_response['Body'].read().decode('utf-8')

                # Parse JSONL (one JSON object per line)
                for line in content.strip().split('\n'):
                    if line.strip():
                        entity = json.loads(line)
                        all_entities.append(entity)
            except Exception as e:
                st.warning(f"Failed to load {s3_key}: {e}")
                continue

        if not all_entities:
            return pd.DataFrame()

        # Flatten entities into DataFrame rows
        rows = []
        for entity in all_entities:
            # Extract coordinates
            coords = entity.get('coordinates', {})
            lat = coords.get('lat') if coords else None
            lon = coords.get('lon') if coords else None
            coord_provider = coords.get('provider') if coords else None
            coord_confidence = coords.get('confidence') if coords else None

            # Extract consensus
            consensus = entity.get('consensus', {})
            avg_rating = consensus.get('avg_rating')
            mention_count = consensus.get('mention_count', 0)
            themes = consensus.get('themes', [])
            best_for = consensus.get('best_for', [])
            sentiment_dist = consensus.get('sentiment_distribution', {})
            cost_info = consensus.get('cost_info', {})

            # Extract temporal info (NEW v2.0)
            temporal = entity.get('temporal_info', {})
            best_seasons = temporal.get('best_seasons', [])
            best_times_of_day = temporal.get('best_times_of_day', [])
            typical_duration = temporal.get('typical_duration')
            temporal_confidence = temporal.get('confidence')

            # Extract logistics info (NEW v2.0)
            logistics = entity.get('logistics_info', {})
            transport_options = logistics.get('transport_options', [])
            booking_required = logistics.get('booking_required')
            accessibility = logistics.get('accessibility_features', [])
            logistics_confidence = logistics.get('confidence')

            # Extract computed metrics (NEW v2.0)
            popularity_score = entity.get('popularity_score')
            freshness = entity.get('data_freshness', {})
            freshness_score = freshness.get('freshness_score')
            days_since_last = freshness.get('days_since_last_mention')
            most_recent = freshness.get('most_recent_mention')

            # Extract provenance
            provenance = entity.get('provenance', {})
            canonical_selection = provenance.get('canonical_name_selection', {})
            canonical_reasoning = canonical_selection.get('reasoning')

            row = {
                # Core fields
                'entity_id': entity.get('entity_id'),
                'canonical_name': entity.get('canonical_name'),
                'aliases': ', '.join(entity.get('aliases', [])),
                'entity_type': entity.get('entity_type'),
                'location': entity.get('location'),
                'city': entity.get('city'),
                'country': entity.get('country'),

                # Coordinates
                'lat': lat,
                'lon': lon,
                'coord_provider': coord_provider,
                'coord_confidence': coord_confidence,

                # Consensus
                'total_mentions': entity.get('total_mentions', 0),
                'avg_rating': avg_rating,
                'mention_count': mention_count,
                'themes': ', '.join(themes[:5]) if themes else None,  # Top 5 themes
                'best_for': ', '.join(best_for) if best_for else None,

                # Sentiment distribution
                'sentiment_positive': sentiment_dist.get('positive', 0),
                'sentiment_neutral': sentiment_dist.get('neutral', 0),
                'sentiment_negative': sentiment_dist.get('negative', 0),
                'sentiment_mixed': sentiment_dist.get('mixed', 0),

                # Cost info
                'cost_avg': cost_info.get('overall', {}).get('avg') if cost_info.get('overall') else None,
                'cost_currency': cost_info.get('overall', {}).get('currency') if cost_info.get('overall') else None,

                # Temporal info (NEW v2.0)
                'best_seasons': ', '.join(best_seasons) if best_seasons else None,
                'best_times_of_day': ', '.join(best_times_of_day) if best_times_of_day else None,
                'typical_duration': typical_duration,
                'temporal_confidence': temporal_confidence,

                # Logistics info (NEW v2.0)
                'transport_options': ', '.join(transport_options[:3]) if transport_options else None,  # Top 3
                'booking_required': booking_required,
                'accessibility': ', '.join(accessibility) if accessibility else None,
                'logistics_confidence': logistics_confidence,

                # Computed metrics (NEW v2.0)
                'popularity_score': popularity_score,
                'freshness_score': freshness_score,
                'days_since_last_mention': days_since_last,
                'most_recent_mention': most_recent,

                # Provenance
                'source_video_count': len(entity.get('source_video_ids', [])),
                'canonical_reasoning': canonical_reasoning,

                # Raw JSON (for viewing full data)
                'raw_json': entity,
            }

            rows.append(row)

        df = pd.DataFrame(rows)

        # Convert numeric columns to proper types
        numeric_columns = [
            'total_mentions', 'avg_rating', 'mention_count',
            'sentiment_positive', 'sentiment_neutral', 'sentiment_negative', 'sentiment_mixed',
            'cost_avg', 'temporal_confidence', 'logistics_confidence',
            'popularity_score', 'freshness_score', 'days_since_last_mention',
            'source_video_count', 'lat', 'lon', 'coord_confidence'
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    except Exception as e:
        st.error(f"Failed to load Stage 3 canonical entities: {e}")
        return pd.DataFrame()
