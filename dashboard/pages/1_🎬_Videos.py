"""
Videos Page

Browse and search all videos with their processing status.
"""

import streamlit as st
import sys
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import get_videos_summary, format_status

st.set_page_config(page_title="Videos", page_icon="🎬", layout="wide")

st.title("🎬 Videos")
st.markdown("Browse all videos and their processing status")

# Load data
with st.spinner("Loading videos..."):
    videos_df = get_videos_summary()

if videos_df.empty:
    st.warning("No videos found. Process some videos first!")
    st.stop()

# Filters
st.subheader("🔍 Filters")
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Stage filter
    stage_options = ['All', 'All Stages Complete', 'Stage 1 Only', 'Stage 2 Only', 'Incomplete']
    stage_filter = st.selectbox("Status", stage_options)

with col2:
    # Language filter
    languages = ['All'] + sorted(videos_df['language'].unique().tolist())
    language_filter = st.selectbox("Language", languages)

with col3:
    # Duration filter
    duration_options = ['All', 'Short (<5 min)', 'Medium (5-20 min)', 'Long (>20 min)']
    duration_filter = st.selectbox("Duration", duration_options)

with col4:
    # Search
    search_query = st.text_input("🔍 Search title/author/channel", "")

# Apply filters
filtered_df = videos_df.copy()

# Stage filter
if stage_filter == 'All Stages Complete':
    filtered_df = filtered_df[filtered_df['all_stages_complete']]
elif stage_filter == 'Stage 1 Only':
    filtered_df = filtered_df[(filtered_df['stage_1'] == 'completed') & (filtered_df['stage_2'] != 'completed')]
elif stage_filter == 'Stage 2 Only':
    filtered_df = filtered_df[(filtered_df['stage_2'] == 'completed') & (filtered_df['stage_3'] != 'completed')]
elif stage_filter == 'Incomplete':
    filtered_df = filtered_df[~filtered_df['all_stages_complete']]

# Language filter
if language_filter != 'All':
    filtered_df = filtered_df[filtered_df['language'] == language_filter]

# Duration filter
if duration_filter == 'Short (<5 min)':
    filtered_df = filtered_df[filtered_df['duration_seconds'] < 300]
elif duration_filter == 'Medium (5-20 min)':
    filtered_df = filtered_df[(filtered_df['duration_seconds'] >= 300) & (filtered_df['duration_seconds'] < 1200)]
elif duration_filter == 'Long (>20 min)':
    filtered_df = filtered_df[filtered_df['duration_seconds'] >= 1200]

# Search filter
if search_query:
    filtered_df = filtered_df[
        filtered_df['title'].str.contains(search_query, case=False, na=False) |
        filtered_df['author'].str.contains(search_query, case=False, na=False)
    ]

# Show count
st.markdown(f"**Showing {len(filtered_df)} of {len(videos_df)} videos**")

st.markdown("---")

# Display table
if not filtered_df.empty:
    # Prepare display dataframe
    display_df = filtered_df[[
        'video_id', 'title', 'author', 'duration_formatted',
        'language', 'stage_1', 'stage_2', 'stage_3', 'upload_date'
    ]].copy()

    # Format status columns
    display_df['stage_1'] = display_df['stage_1'].apply(format_status)
    display_df['stage_2'] = display_df['stage_2'].apply(format_status)
    display_df['stage_3'] = display_df['stage_3'].apply(format_status)

    display_df.columns = ['Video ID', 'Title', 'Author', 'Duration', 'Language', 'Stage 1', 'Stage 2', 'Stage 3', 'Upload Date']

    # Interactive table
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Video ID": st.column_config.TextColumn("Video ID", width="medium", help="Click to copy"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Author": st.column_config.TextColumn("Author", width="medium"),
            "Duration": st.column_config.TextColumn("Duration", width="small"),
            "Language": st.column_config.TextColumn("Lang", width="small"),
            "Stage 1": st.column_config.TextColumn("S1", width="small"),
            "Stage 2": st.column_config.TextColumn("S2", width="small"),
            "Stage 3": st.column_config.TextColumn("S3", width="small"),
            "Upload Date": st.column_config.TextColumn("Uploaded", width="medium"),
        }
    )

    st.markdown("---")

    # Video detail viewer
    st.subheader("📋 View Video Details")
    col1, col2 = st.columns([3, 1])

    with col1:
        selected_video = st.selectbox(
            "Select a video to view details:",
            filtered_df['video_id'].tolist(),
            format_func=lambda x: f"{x} - {filtered_df[filtered_df['video_id']==x]['title'].iloc[0][:50]}"
        )

    with col2:
        if st.button("View Details →", width='stretch', type="primary"):
            # Store selected video in session state and navigate
            st.session_state['selected_video_id'] = selected_video
            st.switch_page("pages/2_📋_Video_Detail.py")

else:
    st.warning("No videos match your filters. Try adjusting the filters.")

# Export option
st.markdown("---")
st.subheader("📥 Export")
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    # Export filtered data as CSV
    csv_data = filtered_df.to_csv(index=False)
    st.download_button(
        label="Download as CSV",
        data=csv_data,
        file_name="travelai_videos.csv",
        mime="text/csv",
        width='stretch'
    )

with col2:
    # Export as JSON
    json_data = filtered_df.to_json(orient='records', indent=2)
    st.download_button(
        label="Download as JSON",
        data=json_data,
        file_name="travelai_videos.json",
        mime="application/json",
        width='stretch'
    )
