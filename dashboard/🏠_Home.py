"""
TravelAI Data Dashboard

Interactive dashboard to monitor video processing pipeline and explore extracted entities.
"""

import streamlit as st
import plotly.express as px
from utils.data_loader import get_videos_summary, get_dashboard_stats

# Page config
st.set_page_config(
    page_title="Pipeline Monitor",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 10rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://em-content.zobj.net/source/apple/391/globe-showing-asia-australia_1f30f.png", width=100)
    st.title("TravelAI")

    # Refresh button
    if st.button("🔄 Refresh Data", width='stretch'):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("v1.0.0 | © 2026 TravelAI")

# Main content
st.markdown('<h2 class="main-header">🌍 TravelAI Dashboard</h2>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Monitor your video processing pipeline and explore extracted entities</p>', unsafe_allow_html=True)

# Load data (only what's needed for homepage)
with st.spinner("Loading dashboard data..."):
    stats = get_dashboard_stats()
    videos_df = get_videos_summary()

# Metrics row
st.subheader("📈 Overview Metrics")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Videos",
        stats['total_videos'],
        delta=None,
        help="Total number of videos in the system"
    )

with col2:
    st.metric(
        "Total Entities",
        stats['total_entities'],
        delta=None,
        help="Total entities extracted across all videos"
    )

with col3:
    st.metric(
        "Unique Entities",
        stats['unique_entities'],
        delta=None,
        help="Unique entities after deduplication"
    )

with col4:
    st.metric(
        "Success Rate",
        f"{stats['success_rate']:.1f}%",
        delta=None,
        help="Percentage of videos that completed all stages"
    )

st.markdown("---")

# Stage completion metrics
st.subheader("🎯 Stage Completion")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Stage 1 Complete", stats['stage1_complete'])
with col2:
    st.metric("Stage 2 Complete", stats['stage2_complete'])
with col3:
    st.metric("Stage 3 Complete", stats['stage3_complete'])
with col4:
    st.metric("All Stages Complete", stats['all_stages_complete'])

st.markdown("---")

# Charts row
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Stage Completion Funnel")
    if stats['total_videos'] > 0:
        funnel_data = {
            'Stage': ['Stage 1', 'Stage 2', 'Stage 3', 'Complete'],
            'Count': [
                stats['stage1_complete'],
                stats['stage2_complete'],
                stats['stage3_complete'],
                stats['all_stages_complete']
            ]
        }
        fig = px.funnel(
            funnel_data,
            x='Count',
            y='Stage',
            title='Video Processing Funnel',
            color='Stage',
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No data available")

with col2:
    st.subheader("🎨 Stage Status Distribution")
    if not videos_df.empty:
        # Create stage status summary
        stage_status = {
            'Stage 1': stats['stage1_complete'],
            'Stage 2': stats['stage2_complete'],
            'Stage 3': stats['stage3_complete']
        }
        fig = px.pie(
            values=list(stage_status.values()),
            names=list(stage_status.keys()),
            title='Videos Completed by Stage',
            color_discrete_sequence=px.colors.sequential.RdBu
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No data available")

st.markdown("---")

# Recent activity
st.subheader("🕒 Recent Videos")
if not videos_df.empty:
    recent_videos = videos_df.sort_values('last_modified', ascending=False).head(10)

    # Format for display
    display_df = recent_videos[['video_id', 'title', 'duration_formatted', 'stage_1', 'stage_2', 'stage_3', 'upload_date']].copy()
    display_df.columns = ['Video ID', 'Title', 'Duration', 'Stage 1', 'Stage 2', 'Stage 3', 'Upload Date']

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Video ID": st.column_config.TextColumn("Video ID", width="medium"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Duration": st.column_config.TextColumn("Duration", width="small"),
            "Stage 1": st.column_config.TextColumn("Stage 1", width="small"),
            "Stage 2": st.column_config.TextColumn("Stage 2", width="small"),
            "Stage 3": st.column_config.TextColumn("Stage 3", width="small"),
        }
    )
else:
    st.info("No videos found. Process some videos to see them here!")

st.markdown("---")

# Language distribution
st.subheader("🌐 Language Distribution")
if not videos_df.empty:
    lang_counts = videos_df['language'].value_counts().head(10)
    fig = px.bar(
        x=lang_counts.index,
        y=lang_counts.values,
        labels={'x': 'Language', 'y': 'Count'},
        title='Top 10 Languages',
        color=lang_counts.values,
        color_continuous_scale='Viridis'
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, width='stretch')
else:
    st.info("No language data available")
