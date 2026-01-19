"""
Video Detail Page

Deep dive into a specific video showing all extracted data.
"""

import streamlit as st
import sys
from pathlib import Path
import json
import pandas as pd

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    get_videos_summary,
    load_video_stage1,
    load_video_stage2,
    load_video_stage3,
    format_status
)

st.set_page_config(page_title="Video Detail", page_icon="📋", layout="wide")

st.title("📋 Video Detail")

# Get videos list
videos_df = get_videos_summary()

if videos_df.empty:
    st.error("No videos available")
    st.stop()

# Always show the dropdown for video selection
video_ids = videos_df['video_id'].tolist()

# Determine default index
default_index = 0
if 'selected_video_id' in st.session_state and st.session_state['selected_video_id'] in video_ids:
    default_index = video_ids.index(st.session_state['selected_video_id'])

# Show dropdown - use key to let Streamlit manage state
video_id = st.selectbox(
    "Select a video:",
    video_ids,
    index=default_index,
    format_func=lambda x: f"{x} - {videos_df[videos_df['video_id']==x]['title'].iloc[0][:60]}",
    key='video_selector'
)

# Store selection in session state
st.session_state['selected_video_id'] = video_id

if not video_id:
    st.info("Please select a video to view details")
    st.stop()

# Load video metadata
videos_df = get_videos_summary()
video_meta = videos_df[videos_df['video_id'] == video_id].iloc[0] if not videos_df.empty and video_id in videos_df['video_id'].values else None

if video_meta is None:
    st.error("Video not found")
    st.stop()

# Header
st.markdown(f"### {video_meta['title']}")
st.caption(f"Video ID: `{video_id}` | Author: {video_meta['author']}")

# Info cards
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Duration", video_meta['duration_formatted'])
with col2:
    st.metric("Language", video_meta['language'].upper())
with col3:
    st.metric("Upload Date", video_meta['upload_date'][:10] if len(video_meta['upload_date']) > 10 else video_meta['upload_date'])
with col4:
    all_complete = video_meta['all_stages_complete']
    st.metric("Status", "✅ Complete" if all_complete else "⏳ In Progress")

st.markdown("---")

# Stage progress
st.subheader("🎯 Stage Progress")
col1, col2, col3 = st.columns(3)

with col1:
    status = video_meta['stage_1']
    if status == 'completed':
        st.success(f"**Stage 1**: {format_status(status)}")
    else:
        st.warning(f"**Stage 1**: {format_status(status)}")

with col2:
    status = video_meta['stage_2']
    if status == 'completed':
        st.success(f"**Stage 2**: {format_status(status)}")
    elif status == 'pending':
        st.info(f"**Stage 2**: {format_status(status)}")
    else:
        st.warning(f"**Stage 2**: {format_status(status)}")

with col3:
    status = video_meta['stage_3']
    if status == 'completed':
        st.success(f"**Stage 3**: {format_status(status)}")
    elif status == 'pending':
        st.info(f"**Stage 3**: {format_status(status)}")
    else:
        st.warning(f"**Stage 3**: {format_status(status)}")

st.markdown("---")

# Tabs for different stages
tab1, tab2, tab3, tab4 = st.tabs(["📹 Stage 1: Transcript", "🎯 Stage 2: Entities", "🔄 Stage 3: Deduplication", "💾 Raw Data"])

# Stage 1 Tab
with tab1:
    st.subheader("Stage 1: Video Crawling & Transcription")

    if video_meta['stage_1'] != 'completed':
        st.warning("Stage 1 not completed yet")
    else:
        with st.spinner("Loading Stage 1 data..."):
            stage1_data = load_video_stage1(video_id)

        if stage1_data:
            # Video Metadata Section
            st.markdown("#### 📹 Video Metadata")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Basic Information**")
                st.write(f"**Title:** {stage1_data.get('title', 'N/A')}")
                st.write(f"**Author:** {stage1_data.get('author', 'N/A')}")
                st.write(f"**Channel:** [{stage1_data.get('author', 'N/A')}]({stage1_data.get('author_url', '#')})")
                st.write(f"**Published:** {stage1_data.get('published_date', 'N/A')}")
                st.write(f"**Duration:** {stage1_data.get('duration_seconds', 0)} seconds")
                st.write(f"**Language:** {stage1_data.get('language', 'N/A').upper()}")

            with col2:
                st.markdown("**Engagement Metrics**")
                metadata = stage1_data.get('metadata', {})
                st.metric("👁️ Views", f"{metadata.get('view_count', 0):,}")
                st.metric("👍 Likes", f"{metadata.get('like_count', 0):,}")
                st.metric("💬 Comments", f"{metadata.get('comment_count', 0):,}")
                st.metric("⭐ Favorites", f"{metadata.get('favorite_count', 0):,}")

            # Description
            description = stage1_data.get('description', '')
            if description:
                with st.expander("📝 Video Description"):
                    st.text(description)

            # Tags
            tags = stage1_data.get('metadata', {}).get('tags', [])
            if tags:
                with st.expander(f"🏷️ Tags ({len(tags)})"):
                    st.write(", ".join(tags))

            st.markdown("---")

            # Transcript quality
            st.markdown("#### 📊 Transcript Quality")
            transcript = stage1_data.get('transcript', [])
            transcript_text = " ".join([seg.get('text', '') for seg in transcript])
            word_count = len(transcript_text.split())
            words_per_minute = (word_count / video_meta['duration_seconds']) * 60 if video_meta['duration_seconds'] > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Segments", len(transcript))
            with col2:
                st.metric("Word Count", word_count)
            with col3:
                st.metric("Words/Min", f"{words_per_minute:.1f}")
            with col4:
                transcript_type = stage1_data.get('metadata', {}).get('transcript_type', 'unknown')
                st.metric("Type", transcript_type.title())

            # Quality assessment
            if 100 <= words_per_minute <= 180:
                st.success("✅ Excellent transcript quality")
            elif 80 <= words_per_minute <= 200:
                st.info("✓ Good transcript quality")
            else:
                st.warning("⚠ Fair transcript quality")

            # Transcript preview
            st.markdown("#### 📄 Transcript Preview")
            with st.expander("Click to view full transcript"):
                st.text_area("Transcript", transcript_text, height=400)

            st.markdown("---")

            # Provenance and Fetching Info
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 🔒 Provenance")
                provenance = stage1_data.get('provenance', {})
                st.write(f"**Can Redistribute:** {'✅' if provenance.get('can_redistribute') else '❌'}")
                st.write(f"**Attribution Required:** {'✅' if provenance.get('attribution_required') else '❌'}")
                st.write(f"**TOS Version:** {provenance.get('tos_version', 'N/A')}")

            with col2:
                st.markdown("#### 🕐 Fetching Info")
                st.write(f"**Fetched At:** {stage1_data.get('fetched_at', 'N/A')[:19]}")
                st.write(f"**Fetched By:** {stage1_data.get('fetched_by', 'N/A')}")
                st.write(f"**Source:** {stage1_data.get('source', 'N/A')}")
                source_url = stage1_data.get('source_url', '#')
                st.write(f"**Watch Video:** [🔗 YouTube]({source_url})")
        else:
            st.error("Failed to load Stage 1 data")

# Stage 2 Tab
with tab2:
    st.subheader("Stage 2: Entity Extraction")

    if video_meta['stage_2'] != 'completed':
        st.warning("Stage 2 not completed yet")
    else:
        with st.spinner("Loading Stage 2 data..."):
            stage2_data = load_video_stage2(video_id)

        if stage2_data:
            # Traveler Profile
            st.markdown("#### 👤 Traveler Profile")
            traveler_profile = stage2_data.get('traveler_profile', {})

            if traveler_profile:
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown("**Budget Tier**")
                    st.info(traveler_profile.get('budget_tier', 'Unknown'))

                with col2:
                    st.markdown("**Trip Duration**")
                    duration = traveler_profile.get('trip_duration_days')
                    st.info(f"{duration} days" if duration else "Unknown")

                with col3:
                    st.markdown("**Confidence**")
                    confidence = traveler_profile.get('confidence_score', 0)
                    st.info(f"{confidence:.2f}")

                # Travel style
                travel_style = traveler_profile.get('travel_style', [])
                if travel_style:
                    st.markdown("**Travel Style**")
                    st.write(", ".join(travel_style))

            st.markdown("---")

            # Entities
            st.markdown("#### 📍 Extracted Entities")
            entities = stage2_data.get('entities', [])

            if entities:
                st.markdown(f"**Total Entities: {len(entities)}**")

                # Convert to dataframe
                entities_df = pd.DataFrame(entities)

                # Entity type distribution
                if 'entity_type' in entities_df.columns:
                    entity_counts = entities_df['entity_type'].value_counts()
                    st.markdown("**Entity Types:**")
                    for etype, count in entity_counts.items():
                        st.write(f"- {etype}: {count}")

                st.markdown("---")

                # Entities table
                st.markdown("**All Entities:**")

                # Prepare display
                display_cols = ['entity_name', 'entity_type', 'location', 'sentiment', 'confidence_score']
                available_cols = [col for col in display_cols if col in entities_df.columns]

                if available_cols:
                    display_df = entities_df[available_cols].copy()

                    # Format columns
                    if 'confidence_score' in display_df.columns:
                        display_df['confidence_score'] = display_df['confidence_score'].round(2)

                    # Rename for display
                    display_df.columns = [col.replace('_', ' ').title() for col in display_df.columns]

                    st.dataframe(
                        display_df,
                        width="stretch",
                        hide_index=True
                    )

                    # Download entities as CSV
                    csv_data = display_df.to_csv(index=False)
                    st.download_button(
                        "Download Entities as CSV",
                        data=csv_data,
                        file_name=f"{video_id}_entities.csv",
                        mime="text/csv"
                    )
            else:
                st.info("No entities extracted")
        else:
            st.error("Failed to load Stage 2 data")

# Stage 3 Tab
with tab3:
    st.subheader("Stage 3: Deduplication")

    if video_meta['stage_3'] != 'completed':
        st.warning("Stage 3 not completed yet")
    else:
        with st.spinner("Loading Stage 3 data..."):
            stage3_data = load_video_stage3(video_id)

        if stage3_data:
            # Deduplication stats
            st.markdown("#### 📊 Deduplication Statistics")

            # Get entities before and after
            stage2_data = load_video_stage2(video_id)
            entities_before = len(stage2_data.get('entities', [])) if stage2_data else 0

            canonical_entities = stage3_data.get('canonical_entities', [])
            entities_after = len(canonical_entities)

            duplicates = entities_before - entities_after
            dedup_rate = (duplicates / entities_before * 100) if entities_before > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Before Dedup", entities_before)
            with col2:
                st.metric("After Dedup", entities_after)
            with col3:
                st.metric("Duplicates Removed", duplicates)
            with col4:
                st.metric("Dedup Rate", f"{dedup_rate:.1f}%")

            # Quality assessment
            if dedup_rate < 10:
                st.success("✅ Low redundancy - good quality extraction")
            elif dedup_rate < 30:
                st.info("✓ Moderate redundancy - acceptable")
            else:
                st.warning("⚠ High redundancy - may indicate extraction issues")

            # Canonical entities
            canonical_entity_ids = stage3_data.get('canonical_entity_ids', [])
            if canonical_entities:
                st.markdown("---")
                st.markdown("#### 📋 Final Canonical Entities")

                canonical_df = pd.DataFrame(canonical_entities)

                # Show sample
                display_cols = ['canonical_name', 'entity_type', 'canonical_location', 'mention_count', 'avg_quality_score']
                available_cols = [col for col in display_cols if col in canonical_df.columns]

                if available_cols:
                    st.dataframe(
                        canonical_df[available_cols],
                        width="stretch",
                        hide_index=True
                    )
            elif canonical_entity_ids:
                st.markdown("---")
                st.markdown("#### 📋 Canonical Entity IDs")
                st.info(f"This video contributed {len(canonical_entity_ids)} entities to the canonical entity database.")

                # Show entity IDs in an expandable section
                with st.expander(f"View {len(canonical_entity_ids)} Entity IDs"):
                    # Group by entity type (prefix before underscore)
                    entity_groups = {}
                    for entity_id in canonical_entity_ids:
                        entity_type = entity_id.split('_')[0] if '_' in entity_id else 'other'
                        if entity_type not in entity_groups:
                            entity_groups[entity_type] = []
                        entity_groups[entity_type].append(entity_id)

                    # Display by type
                    for entity_type, ids in sorted(entity_groups.items()):
                        st.markdown(f"**{entity_type.title()}** ({len(ids)})")
                        st.write(", ".join(sorted(ids)))
        else:
            st.info("Stage 3 data not available yet")

# Raw Data Tab
with tab4:
    st.subheader("💾 Raw Data")
    st.markdown("Download raw JSON data for each stage")

    col1, col2, col3 = st.columns(3)

    with col1:
        if video_meta['stage_1'] == 'completed':
            stage1_data = load_video_stage1(video_id)
            if stage1_data:
                json_data = json.dumps(stage1_data, indent=2)
                st.download_button(
                    "📥 Download Stage 1 JSON",
                    data=json_data,
                    file_name=f"{video_id}_stage1.json",
                    mime="application/json",
                    width='stretch'
                )
        else:
            st.info("Stage 1 not complete")

    with col2:
        if video_meta['stage_2'] == 'completed':
            stage2_data = load_video_stage2(video_id)
            if stage2_data:
                json_data = json.dumps(stage2_data, indent=2)
                st.download_button(
                    "📥 Download Stage 2 JSON",
                    data=json_data,
                    file_name=f"{video_id}_stage2.json",
                    mime="application/json",
                    width='stretch'
                )
        else:
            st.info("Stage 2 not complete")

    with col3:
        if video_meta['stage_3'] == 'completed':
            stage3_data = load_video_stage3(video_id)
            if stage3_data:
                json_data = json.dumps(stage3_data, indent=2)
                st.download_button(
                    "📥 Download Stage 3 JSON",
                    data=json_data,
                    file_name=f"{video_id}_stage3.json",
                    mime="application/json",
                    width='stretch'
                )
        else:
            st.info("Stage 3 not complete")

# Navigation
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    if st.button("← Back to Videos", width='stretch'):
        st.switch_page("pages/1_🎬_Videos.py")
with col2:
    if st.button("View All Entities →", width='stretch'):
        st.switch_page("pages/3_📍_Entities.py")
