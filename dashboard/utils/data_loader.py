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
        # Prefer enhanced_rating (multi-signal) over avg_rating (sentiment-only)
        if 'enhanced_rating' in canonical_df.columns:
            ratings = canonical_df['enhanced_rating'].dropna()
            stats['avg_entity_rating'] = ratings.mean() if len(ratings) > 0 else 0
        elif 'avg_rating' in canonical_df.columns:
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

            # Extract temporal info (NEW v2.0 - with hybrid source tracking)
            temporal = entity.get('temporal_info', {})
            best_seasons = temporal.get('best_seasons', [])
            best_times_of_day = temporal.get('best_times_of_day', [])
            typical_duration = temporal.get('typical_duration')
            temporal_confidence = temporal.get('confidence')
            temporal_source = temporal.get('source', 'none')  # transcript_extracted, llm_inferred, hybrid, none

            # Extract logistics info (NEW v2.0 - with hybrid source tracking)
            logistics = entity.get('logistics_info', {})
            transport_options = logistics.get('transport_options', [])
            booking_required = logistics.get('booking_required')
            accessibility = logistics.get('accessibility_features', [])
            logistics_confidence = logistics.get('confidence')
            logistics_source = logistics.get('source', 'none')  # transcript_extracted, llm_inferred, hybrid, none

            # Extract practical tips (LLM enrichment only)
            practical_tips = entity.get('practical_tips', {})
            has_practical_tips = bool(practical_tips)
            dress_code = practical_tips.get('dress_code')
            entrance_fee = practical_tips.get('entrance_fee')
            opening_hours = practical_tips.get('opening_hours')

            # Extract enrichment provenance
            enrichment_provenance = entity.get('enrichment_provenance', {})
            enrichment_source = enrichment_provenance.get('source', 'none')
            llm_fame_score = enrichment_provenance.get('fame_score')

            # Extract computed metrics (NEW v2.0)
            popularity_score = entity.get('popularity_score')
            freshness = entity.get('data_freshness', {})
            freshness_score = freshness.get('freshness_score')
            days_since_last = freshness.get('days_since_last_mention')
            most_recent = freshness.get('most_recent_mention')

            # Extract enhanced rating (NEW - multi-signal rating)
            enhanced_rating = entity.get('enhanced_rating', {})
            enhanced_rating_value = enhanced_rating.get('rating')
            enhanced_rating_confidence = enhanced_rating.get('confidence')
            enhanced_rating_signals = enhanced_rating.get('signal_count', 0)
            rating_source_breakdown = enhanced_rating.get('source_breakdown', {})

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

                # Temporal info (NEW v2.0 - with hybrid source tracking)
                'best_seasons': ', '.join(best_seasons) if best_seasons else None,
                'best_times_of_day': ', '.join(best_times_of_day) if best_times_of_day else None,
                'typical_duration': typical_duration,
                'temporal_confidence': temporal_confidence,
                'temporal_source': temporal_source,  # transcript_extracted, llm_inferred, hybrid, none

                # Logistics info (NEW v2.0 - with hybrid source tracking)
                'transport_options': ', '.join(transport_options[:3]) if transport_options else None,  # Top 3
                'booking_required': booking_required,
                'accessibility': ', '.join(accessibility) if accessibility else None,
                'logistics_confidence': logistics_confidence,
                'logistics_source': logistics_source,  # transcript_extracted, llm_inferred, hybrid, none

                # Practical tips (LLM enrichment only)
                'has_practical_tips': has_practical_tips,
                'dress_code': dress_code,
                'entrance_fee': entrance_fee,
                'opening_hours': opening_hours,

                # Enrichment provenance
                'enrichment_source': enrichment_source,
                'llm_fame_score': llm_fame_score,

                # Computed metrics (NEW v2.0)
                'popularity_score': popularity_score,
                'freshness_score': freshness_score,
                'days_since_last_mention': days_since_last,
                'most_recent_mention': most_recent,

                # Enhanced rating (NEW - multi-signal rating)
                'enhanced_rating': enhanced_rating_value,
                'enhanced_rating_confidence': enhanced_rating_confidence,
                'enhanced_rating_signals': enhanced_rating_signals,
                'has_explicit_ratings': 'explicit_transcript' in rating_source_breakdown,
                'has_llm_rating': 'llm_known' in rating_source_breakdown,

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
            'source_video_count', 'lat', 'lon', 'coord_confidence',
            'enhanced_rating', 'enhanced_rating_confidence', 'enhanced_rating_signals'
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    except Exception as e:
        st.error(f"Failed to load Stage 3 canonical entities: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=1200)  # Cache for 20 minutes
def load_canonical_insights() -> pd.DataFrame:
    """
    Load canonical insights from insights pipeline.

    Returns DataFrame with columns:
        insight_id, category, content, title, details, scope (dict),
        confidence_score, mention_count, video_count, source_video_ids (list),
        tags (list), quality_score, freshness_score, applicability_score,
        created_at, updated_at

    Returns empty DataFrame if no insights data exists yet.
    """
    try:
        storage = S3Storage()

        # List all files in insights-pipeline/canonical/ directory
        prefix = 'insights-pipeline/canonical/'

        try:
            response = storage.s3_client.list_objects_v2(
                Bucket=storage.bucket_name,
                Prefix=prefix
            )
        except Exception:
            # Insights pipeline may not exist yet
            return pd.DataFrame()

        if 'Contents' not in response:
            return pd.DataFrame()

        # Find insights_all_*.jsonl files
        insight_files = []
        for obj in response['Contents']:
            s3_key = obj['Key']
            if 'insights_all_' in s3_key and s3_key.endswith('.jsonl'):
                insight_files.append(s3_key)

        if not insight_files:
            return pd.DataFrame()

        # Load and combine all insight files
        all_insights = []
        for s3_key in insight_files:
            try:
                file_response = storage.s3_client.get_object(
                    Bucket=storage.bucket_name,
                    Key=s3_key
                )
                content = file_response['Body'].read().decode('utf-8')

                # Parse JSONL (one JSON object per line)
                for line in content.strip().split('\n'):
                    if line.strip():
                        insight = json.loads(line)
                        all_insights.append(insight)
            except Exception as e:
                st.warning(f"Failed to load {s3_key}: {e}")
                continue

        if not all_insights:
            return pd.DataFrame()

        # Flatten insights into DataFrame rows
        rows = []
        for insight in all_insights:
            # Extract scope
            scope = insight.get('scope', {})
            destination_type = scope.get('destination_type', 'unknown')
            country = scope.get('country')
            city = scope.get('city')
            region = scope.get('region')
            area = scope.get('area')

            # Extract provenance
            provenance = insight.get('provenance', {})
            source_video_ids = provenance.get('source_video_ids', [])
            extraction_method = provenance.get('extraction_method', 'unknown')

            row = {
                # Core fields
                'insight_id': insight.get('insight_id'),
                'category': insight.get('category'),
                'content': insight.get('content'),
                'title': insight.get('title'),
                'details': insight.get('details'),

                # Scope
                'destination_type': destination_type,
                'country': country,
                'city': city,
                'region': region,
                'area': area,

                # Quality metrics
                'confidence_score': insight.get('confidence_score'),
                'mention_count': insight.get('mention_count', 0),
                'video_count': insight.get('video_count', 0),

                # Canonical insight fields (if present)
                'quality_score': insight.get('quality_score'),
                'freshness_score': insight.get('freshness_score'),
                'applicability_score': insight.get('applicability_score'),

                # Provenance
                'source_video_ids': source_video_ids,
                'extraction_method': extraction_method,
                'tags': insight.get('tags', []),

                # Timestamps
                'created_at': insight.get('created_at'),
                'updated_at': insight.get('updated_at'),

                # Raw JSON for full details
                'raw_json': insight,
            }

            rows.append(row)

        df = pd.DataFrame(rows)

        # Convert numeric columns to proper types
        numeric_columns = [
            'confidence_score', 'mention_count', 'video_count',
            'quality_score', 'freshness_score', 'applicability_score'
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    except Exception as e:
        # Silently return empty DataFrame if insights pipeline not implemented yet
        return pd.DataFrame()


@st.cache_data(ttl=1200)  # Cache for 20 minutes
def load_insights_by_category(category: str) -> pd.DataFrame:
    """
    Load insights for a specific category from insights pipeline.

    Args:
        category: One of 'services', 'tips', 'logistics', 'cultural',
                  'safety', 'cost_info', 'seasonal', 'regional'

    Returns:
        DataFrame of insights for the specified category
    """
    try:
        storage = S3Storage()
        prefix = f'insights-pipeline/canonical/by_category/{category}_'

        try:
            response = storage.s3_client.list_objects_v2(
                Bucket=storage.bucket_name,
                Prefix=prefix
            )
        except Exception:
            return pd.DataFrame()

        if 'Contents' not in response:
            return pd.DataFrame()

        # Find latest file for this category
        category_files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.jsonl')]
        if not category_files:
            return pd.DataFrame()

        # Load the most recent file
        latest_file = sorted(category_files, reverse=True)[0]

        file_response = storage.s3_client.get_object(
            Bucket=storage.bucket_name,
            Key=latest_file
        )
        content = file_response['Body'].read().decode('utf-8')

        # Parse JSONL
        insights = []
        for line in content.strip().split('\n'):
            if line.strip():
                insights.append(json.loads(line))

        # Convert to DataFrame (use same structure as load_canonical_insights)
        # Simplified version - just return raw data
        return pd.DataFrame(insights)

    except Exception:
        return pd.DataFrame()


def get_entity_insight_relationships() -> List[tuple]:
    """
    Build relationship mapping between entities and insights.

    Returns:
        List of (entity_id, insight_id, relationship_type, strength) tuples
        relationship_type: 'same_city', 'same_country', 'same_area', 'same_region'
        strength: 0.0-1.0 based on location specificity
    """
    try:
        entities_df = load_stage3_canonical_entities()
        insights_df = load_canonical_insights()

        if entities_df.empty or insights_df.empty:
            return []

        relationships = []

        # For each entity, find insights in the same location
        for _, entity in entities_df.iterrows():
            entity_id = entity['entity_id']
            entity_city = entity['city']
            entity_country = entity['country']

            for _, insight in insights_df.iterrows():
                insight_id = insight['insight_id']
                insight_city = insight.get('city')
                insight_country = insight.get('country')
                insight_area = insight.get('area')

                # Match by area (highest specificity)
                if insight_area and entity.get('location') and insight_area.lower() in str(entity['location']).lower():
                    relationships.append((entity_id, insight_id, 'same_area', 1.0))
                # Match by city
                elif insight_city and entity_city and insight_city.lower() == entity_city.lower():
                    relationships.append((entity_id, insight_id, 'same_city', 0.8))
                # Match by country
                elif insight_country and entity_country and insight_country.lower() == entity_country.lower():
                    relationships.append((entity_id, insight_id, 'same_country', 0.5))

        return relationships

    except Exception as e:
        st.error(f"Failed to build entity-insight relationships: {e}")
        return []


def get_video_content_summary(video_id: str) -> Dict[str, Any]:
    """
    Aggregate entities and insights for a specific video.

    Args:
        video_id: The video content ID

    Returns:
        {
            'entities': List of entity dicts,
            'insights': List of insight dicts,
            'content_richness': float (entities + insights) / duration_minutes
        }
    """
    try:
        # Load video Stage 2 data (entities)
        stage2_data = load_video_stage2(video_id)
        entities = stage2_data.get('entities', []) if stage2_data else []

        # Load insights that mention this video
        insights_df = load_canonical_insights()
        if not insights_df.empty:
            # Filter insights that have this video in source_video_ids
            video_insights = []
            for _, insight in insights_df.iterrows():
                source_ids = insight.get('source_video_ids', [])
                if video_id in source_ids or video_id.replace('youtube_', '') in [sid.replace('youtube_', '') for sid in source_ids]:
                    video_insights.append(insight.to_dict())
        else:
            video_insights = []

        # Calculate content richness
        videos_df = get_videos_summary()
        video_row = videos_df[videos_df['video_id'] == video_id]

        content_richness = 0
        if not video_row.empty:
            duration_minutes = video_row.iloc[0]['duration_seconds'] / 60
            if duration_minutes > 0:
                content_richness = (len(entities) + len(video_insights)) / duration_minutes

        return {
            'entities': entities,
            'insights': video_insights,
            'content_richness': content_richness
        }

    except Exception as e:
        st.error(f"Failed to get video content summary: {e}")
        return {'entities': [], 'insights': [], 'content_richness': 0}


def get_processing_errors() -> pd.DataFrame:
    """
    Query metadata tracker for failed stages.

    Returns:
        DataFrame with columns: video_id, title, stage, status, error, retry_count
    """
    try:
        metadata = load_metadata_tracker()

        if not metadata:
            return pd.DataFrame()

        errors = []
        for video_id, data in metadata.items():
            stages = data.get('stages', {})
            title = data.get('title', 'Unknown')

            for stage_name, stage_data in stages.items():
                if not stage_data:
                    continue

                status = stage_data.get('status')
                if status == 'failed':
                    error_msg = stage_data.get('error', 'Unknown error')
                    retry_count = stage_data.get('retry_count', 0)

                    errors.append({
                        'video_id': video_id,
                        'title': title,
                        'stage': stage_name,
                        'status': status,
                        'error': error_msg,
                        'retry_count': retry_count,
                        'failed_at': stage_data.get('completed_at', 'Unknown')
                    })

        return pd.DataFrame(errors)

    except Exception as e:
        st.error(f"Failed to get processing errors: {e}")
        return pd.DataFrame()


def get_quality_issues() -> Dict[str, List[Dict[str, Any]]]:
    """
    Identify entities and insights with quality issues.

    Returns:
        {
            'low_confidence_entities': List of entity dicts with confidence < 0.6,
            'missing_geocoding': List of entity dicts without coordinates,
            'missing_enrichment': List of entity dicts without temporal or logistics info,
            'low_confidence_insights': List of insight dicts with confidence < 0.6,
            'single_source_insights': List of insight dicts with video_count = 1,
            'stale_entities': List of entity dicts with freshness_score < 0.5
        }
    """
    try:
        entities_df = load_stage3_canonical_entities()
        insights_df = load_canonical_insights()

        issues = {
            'low_confidence_entities': [],
            'missing_geocoding': [],
            'missing_enrichment': [],
            'low_confidence_insights': [],
            'single_source_insights': [],
            'stale_entities': []
        }

        # Entity quality issues
        if not entities_df.empty:
            # Low confidence entities (no direct confidence field, use rating confidence)
            if 'enhanced_rating_confidence' in entities_df.columns:
                low_conf = entities_df[entities_df['enhanced_rating_confidence'] < 0.6]
                issues['low_confidence_entities'] = low_conf.to_dict('records')

            # Missing geocoding
            missing_geo = entities_df[entities_df['lat'].isna() | entities_df['lon'].isna()]
            issues['missing_geocoding'] = missing_geo.to_dict('records')

            # Missing enrichment (no temporal AND no logistics info)
            if 'temporal_confidence' in entities_df.columns and 'logistics_confidence' in entities_df.columns:
                missing_enrich = entities_df[
                    entities_df['temporal_confidence'].isna() & entities_df['logistics_confidence'].isna()
                ]
                issues['missing_enrichment'] = missing_enrich.to_dict('records')

            # Stale entities
            if 'freshness_score' in entities_df.columns:
                stale = entities_df[entities_df['freshness_score'] < 0.5]
                issues['stale_entities'] = stale.to_dict('records')

        # Insight quality issues
        if not insights_df.empty:
            # Low confidence insights
            if 'confidence_score' in insights_df.columns:
                low_conf_insights = insights_df[insights_df['confidence_score'] < 0.6]
                issues['low_confidence_insights'] = low_conf_insights.to_dict('records')

            # Single-source insights
            if 'video_count' in insights_df.columns:
                single_source = insights_df[insights_df['video_count'] == 1]
                issues['single_source_insights'] = single_source.to_dict('records')

        return issues

    except Exception as e:
        st.error(f"Failed to get quality issues: {e}")
        return {
            'low_confidence_entities': [],
            'missing_geocoding': [],
            'missing_enrichment': [],
            'low_confidence_insights': [],
            'single_source_insights': [],
            'stale_entities': []
        }


@st.cache_data(ttl=1200)  # Cache for 20 minutes
def get_geographic_coverage_stats() -> pd.DataFrame:
    """
    Aggregate entities and insights by country/city.

    Returns:
        DataFrame with columns: country, city, entity_count, insight_count,
                               video_count, coverage_score
    """
    try:
        entities_df = load_stage3_canonical_entities()
        insights_df = load_canonical_insights()
        videos_df = get_videos_summary()

        if entities_df.empty:
            return pd.DataFrame()

        # Group entities by country/city
        entity_groups = entities_df.groupby(['country', 'city'], dropna=False).agg({
            'entity_id': 'count',
            'source_video_count': 'sum'
        }).reset_index()

        entity_groups.columns = ['country', 'city', 'entity_count', 'entity_video_count']

        # Convert city to string to avoid dtype mismatch during merge
        entity_groups['city'] = entity_groups['city'].astype(str)
        entity_groups['country'] = entity_groups['country'].astype(str)

        # Group insights by country/city (if insights exist)
        if not insights_df.empty:
            insight_groups = insights_df.groupby(['country', 'city'], dropna=False).agg({
                'insight_id': 'count',
                'video_count': 'sum'
            }).reset_index()

            insight_groups.columns = ['country', 'city', 'insight_count', 'insight_video_count']

            # Convert city to string to avoid dtype mismatch during merge
            insight_groups['city'] = insight_groups['city'].astype(str)
            insight_groups['country'] = insight_groups['country'].astype(str)

            # Merge
            coverage = pd.merge(
                entity_groups,
                insight_groups,
                on=['country', 'city'],
                how='outer'
            )
        else:
            coverage = entity_groups.copy()
            coverage['insight_count'] = 0
            coverage['insight_video_count'] = 0

        # Fill NaN with 0 (for numeric columns)
        coverage = coverage.fillna(0)

        # Replace 'nan' strings in country/city columns with None
        coverage['city'] = coverage['city'].replace('nan', None)
        coverage['country'] = coverage['country'].replace('nan', None)

        # Calculate coverage score (0-1): weighted by content volume and diversity
        # Score = (entities + insights) / max(entities + insights) * diversity_factor
        total_content = coverage['entity_count'] + coverage['insight_count']
        max_content = total_content.max() if not total_content.empty else 1

        # Diversity factor: higher if both entities AND insights exist
        diversity_factor = 1.0
        if not insights_df.empty:
            has_both = (coverage['entity_count'] > 0) & (coverage['insight_count'] > 0)
            diversity_factor = 1.2 * has_both + 1.0 * ~has_both

        coverage['coverage_score'] = (total_content / max_content) * diversity_factor

        # Video count (unique videos contributing to this destination)
        coverage['video_count'] = coverage['entity_video_count'] + coverage['insight_video_count']

        # Drop intermediate columns
        coverage = coverage.drop(columns=['entity_video_count', 'insight_video_count'], errors='ignore')

        return coverage

    except Exception as e:
        st.error(f"Failed to get geographic coverage stats: {e}")
        return pd.DataFrame()


def build_knowledge_graph_data(filters: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build nodes and edges for knowledge graph visualization.

    Args:
        filters: Optional dict with keys:
            - 'graph_type': 'entity-entity', 'entity-insight', 'video-entity', 'full'
            - 'country': Country filter
            - 'city': City filter
            - 'entity_type': Entity type filter
            - 'insight_category': Insight category filter
            - 'max_nodes': Maximum number of nodes to include

    Returns:
        {
            'nodes': [
                {
                    'id': 'unique_id',
                    'type': 'entity|insight|video',
                    'label': 'display_name',
                    'size': float (mentions/confidence),
                    'color': 'hex_color',
                    'metadata': {additional info}
                },
                ...
            ],
            'edges': [
                {
                    'source': 'node_id',
                    'target': 'node_id',
                    'type': 'mentions|extracts|relates',
                    'weight': float (0-1)
                },
                ...
            ]
        }
    """
    try:
        filters = filters or {}
        graph_type = filters.get('graph_type', 'full')
        max_nodes = filters.get('max_nodes', 100)

        nodes = []
        edges = []

        entities_df = load_stage3_canonical_entities()
        insights_df = load_canonical_insights()
        videos_df = get_videos_summary()

        # Apply filters
        if not entities_df.empty:
            if filters.get('country'):
                entities_df = entities_df[entities_df['country'] == filters['country']]
            if filters.get('city'):
                entities_df = entities_df[entities_df['city'] == filters['city']]
            if filters.get('entity_type'):
                entities_df = entities_df[entities_df['entity_type'] == filters['entity_type']]

        if not insights_df.empty:
            if filters.get('country'):
                insights_df = insights_df[insights_df['country'] == filters['country']]
            if filters.get('city'):
                insights_df = insights_df[insights_df['city'] == filters['city']]
            if filters.get('insight_category'):
                insights_df = insights_df[insights_df['category'] == filters['insight_category']]

        # Limit nodes
        if not entities_df.empty:
            entities_df = entities_df.nlargest(max_nodes // 2, 'total_mentions')
        if not insights_df.empty:
            insights_df = insights_df.nlargest(max_nodes // 2, 'mention_count')

        # Build entity nodes
        if graph_type in ['entity-entity', 'entity-insight', 'video-entity', 'full']:
            for _, entity in entities_df.iterrows():
                nodes.append({
                    'id': entity['entity_id'],
                    'type': 'entity',
                    'label': entity['canonical_name'],
                    'size': entity.get('total_mentions', 1),
                    'color': '#3498db',  # Blue for entities
                    'metadata': {
                        'entity_type': entity['entity_type'],
                        'city': entity['city'],
                        'country': entity['country'],
                        'rating': entity.get('enhanced_rating', entity.get('avg_rating'))
                    }
                })

        # Build insight nodes
        if graph_type in ['entity-insight', 'full'] and not insights_df.empty:
            for _, insight in insights_df.iterrows():
                nodes.append({
                    'id': insight['insight_id'],
                    'type': 'insight',
                    'label': insight['title'] or insight['content'][:50],
                    'size': insight.get('mention_count', 1),
                    'color': '#e74c3c',  # Red for insights
                    'metadata': {
                        'category': insight['category'],
                        'confidence': insight.get('confidence_score')
                    }
                })

        # Build video nodes (limited)
        if graph_type in ['video-entity', 'full']:
            video_ids = set()

            # Collect video IDs from entities
            for _, entity in entities_df.iterrows():
                raw = entity.get('raw_json', {})
                source_ids = raw.get('source_video_ids', [])
                video_ids.update(source_ids[:3])  # Limit to 3 videos per entity

            # Limit total video nodes
            video_ids = list(video_ids)[:max_nodes // 4]

            for video_id in video_ids:
                video_row = videos_df[videos_df['video_id'] == video_id]
                if not video_row.empty:
                    video = video_row.iloc[0]
                    nodes.append({
                        'id': video_id,
                        'type': 'video',
                        'label': video['title'][:30],
                        'size': 5,
                        'color': '#2ecc71',  # Green for videos
                        'metadata': {
                            'duration': video['duration_formatted'],
                            'author': video['author']
                        }
                    })

        # Build edges: entity-insight relationships
        if graph_type in ['entity-insight', 'full'] and not insights_df.empty:
            relationships = get_entity_insight_relationships()
            for entity_id, insight_id, rel_type, strength in relationships:
                # Check if both nodes exist
                entity_exists = any(n['id'] == entity_id for n in nodes)
                insight_exists = any(n['id'] == insight_id for n in nodes)

                if entity_exists and insight_exists:
                    edges.append({
                        'source': entity_id,
                        'target': insight_id,
                        'type': rel_type,
                        'weight': strength
                    })

        # Build edges: video-entity relationships
        if graph_type in ['video-entity', 'full']:
            for _, entity in entities_df.iterrows():
                entity_id = entity['entity_id']
                raw = entity.get('raw_json', {})
                source_ids = raw.get('source_video_ids', [])

                for video_id in source_ids[:3]:  # Limit edges
                    video_exists = any(n['id'] == video_id for n in nodes)
                    if video_exists:
                        edges.append({
                            'source': video_id,
                            'target': entity_id,
                            'type': 'mentions',
                            'weight': 1.0
                        })

        return {
            'nodes': nodes,
            'edges': edges
        }

    except Exception as e:
        st.error(f"Failed to build knowledge graph data: {e}")
        return {'nodes': [], 'edges': []}
