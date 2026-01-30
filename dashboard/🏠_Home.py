"""
TravelAI Data Dashboard

Interactive dashboard to monitor video processing pipeline and explore extracted entities.
"""

import streamlit as st
import plotly.express as px
from utils.data_loader import (
    get_videos_summary,
    get_dashboard_stats,
    load_canonical_insights
)

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

    # st.divider()
    st.caption("v1.0.0 | © 2026 TravelAI")

# Main content
st.markdown('<h2 class="main-header">🌍 TravelAI Dashboard</h2>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Monitor your video processing pipeline and explore extracted entities</p>', unsafe_allow_html=True)

# Load data (only what's needed for homepage)
with st.spinner("Loading dashboard data..."):
    stats = get_dashboard_stats()
    videos_df = get_videos_summary()
    insights_df = load_canonical_insights()  # Load insights data

# Metrics row
st.subheader("📈 Overview Metrics")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        "Total Videos",
        stats['total_videos'],
        delta=None,
        help="Total number of videos in the system"
    )

with col2:
    st.metric(
        "Canonical Entities",
        stats['canonical_entities'],
        delta=None,
        help="Stage 3 deduplicated entities with enrichment (v2.0)"
    )

with col3:
    # Insights count (NEW)
    total_insights = len(insights_df) if not insights_df.empty else 0
    st.metric(
        "Travel Insights",
        total_insights,
        delta=None,
        help="Canonical travel insights (tips, services, logistics, cultural info)"
    )

with col4:
    rating = stats['avg_entity_rating']
    st.metric(
        "Avg Entity Rating",
        f"{rating:.1f}/5" if rating > 0 else "N/A",
        delta=None,
        help="Multi-signal rating combining: explicit transcript ratings, sentiment analysis, and LLM knowledge (Google Maps ratings for famous places)"
    )

with col5:
    st.metric(
        "Pipeline Success",
        f"{stats['success_rate']:.0f}%",
        delta=None,
        help="Videos that completed all 3 stages"
    )

st.markdown("---")

# Pipeline and Data Quality metrics
col1, col2 = st.columns(2)

with col1:
    st.subheader("🎯 Pipeline Progress")
    subcol1, subcol2, subcol3, subcol4, subcol5 = st.columns(5)
    with subcol1:
        st.metric("Stage 1", stats['stage1_complete'])
    with subcol2:
        st.metric("Stage 2", stats['stage2_complete'])
    with subcol3:
        st.metric("Stage 3", stats['stage3_complete'])
    with subcol4:
        # Insights pipeline count (NEW)
        insights_complete = total_insights if total_insights > 0 else 0
        st.metric("Insights", insights_complete, help="Insights pipeline processed")
    with subcol5:
        st.metric("Complete", stats['all_stages_complete'])

with col2:
    st.subheader("✨ Data Quality (v2.0)")
    subcol1, subcol2, subcol3 = st.columns(3)
    with subcol1:
        geocoded = stats['geocoded_pct']
        st.metric(
            "Geocoded",
            f"{geocoded:.0f}%",
            delta=None,
            help="Entities with coordinates (lat/lon)"
        )
    with subcol2:
        enriched = stats['with_enrichment_pct']
        st.metric(
            "Enriched",
            f"{enriched:.0f}%",
            delta=None,
            help="Entities with temporal/logistics data (NEW v2.0)"
        )
    with subcol3:
        # Calculate data freshness if we have entities
        st.metric(
            "Avg Rating",
            f"{stats['avg_entity_rating']:.1f}",
            delta=None,
            help="Average entity consensus rating"
        )

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
    st.subheader("📍 Entity Type Distribution (Stage 3)")
    # Load Stage 3 canonical entities for visualization
    try:
        from utils.data_loader import load_stage3_canonical_entities
        canonical_df = load_stage3_canonical_entities()

        if not canonical_df.empty and 'entity_type' in canonical_df:
            type_counts = canonical_df['entity_type'].value_counts()
            fig = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                title='Canonical Entities by Type',
                color_discrete_sequence=px.colors.sequential.Teal,
                hole=0.3  # Donut chart
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No Stage 3 entities available yet. Process videos through Stage 3 to see entity types.")
    except Exception as e:
        st.info("No Stage 3 entities available yet")

st.markdown("---")

# Insights Section (NEW)
st.subheader("💡 Insights Overview")
col1, col2 = st.columns(2)

with col1:
    st.markdown("##### Insights by Category")
    if not insights_df.empty and 'category' in insights_df.columns:
        category_counts = insights_df['category'].value_counts()
        fig = px.pie(
            values=category_counts.values,
            names=category_counts.index,
            title='Canonical Insights by Category',
            color_discrete_sequence=px.colors.sequential.Oranges,
            hole=0.3  # Donut chart
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No insights data available yet. Run the insights pipeline to see categories.")

with col2:
    st.markdown("##### Recent Insights")
    if not insights_df.empty:
        # Sort by updated_at or created_at (most recent first)
        if 'updated_at' in insights_df.columns:
            recent_insights = insights_df.sort_values('updated_at', ascending=False).head(5)
        elif 'created_at' in insights_df.columns:
            recent_insights = insights_df.sort_values('created_at', ascending=False).head(5)
        else:
            recent_insights = insights_df.head(5)

        # Display as cards
        for _, insight in recent_insights.iterrows():
            category = insight.get('category', 'unknown')
            content = insight.get('content', '')
            title = insight.get('title', '')
            confidence = insight.get('confidence_score', 0)

            # Truncate content for display
            display_text = title if title else (content[:80] + '...' if len(content) > 80 else content)

            with st.expander(f"**{category.upper()}** | {display_text}", expanded=False):
                st.write(f"**Content:** {content}")
                if title:
                    st.write(f"**Title:** {title}")
                st.write(f"**Confidence:** {confidence:.2f}")
                st.write(f"**Mentions:** {insight.get('mention_count', 0)}")
    else:
        st.info("No insights data available yet")

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

# Top destinations and entities
col1, col2 = st.columns(2)

with col1:
    st.subheader("🌍 Top Destinations")
    try:
        from utils.data_loader import load_stage3_canonical_entities
        canonical_df = load_stage3_canonical_entities()

        if not canonical_df.empty and 'city' in canonical_df:
            # Filter out unknown cities
            city_df = canonical_df[canonical_df['city'].notna() & (canonical_df['city'] != 'unknown')]
            if not city_df.empty:
                city_counts = city_df['city'].value_counts().head(10)
                fig = px.bar(
                    x=city_counts.values,
                    y=city_counts.index,
                    orientation='h',
                    labels={'x': 'Entity Count', 'y': 'City'},
                    title='Top 10 Cities by Entity Count',
                    color=city_counts.values,
                    color_continuous_scale='Blues'
                )
                fig.update_layout(height=400, showlegend=False, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("No city data available")
        else:
            st.info("No Stage 3 entities available")
    except Exception:
        st.info("No Stage 3 entities available")

with col2:
    st.subheader("⭐ Top Rated Entities")
    try:
        from utils.data_loader import load_stage3_canonical_entities
        canonical_df = load_stage3_canonical_entities()

        # Prefer enhanced_rating (multi-signal) over avg_rating (sentiment-only)
        rating_col = 'enhanced_rating' if 'enhanced_rating' in canonical_df.columns else 'avg_rating'

        if not canonical_df.empty and rating_col in canonical_df.columns:
            # Filter entities with at least 2 mentions for reliable ratings
            rated_df = canonical_df[
                (canonical_df['total_mentions'] >= 2) &
                (canonical_df[rating_col].notna())
            ].copy()

            if not rated_df.empty:
                top_rated = rated_df.nlargest(10, rating_col)[['canonical_name', rating_col, 'total_mentions']]

                import plotly.graph_objects as go
                fig = go.Figure(data=[
                    go.Bar(
                        y=top_rated['canonical_name'],
                        x=top_rated[rating_col],
                        orientation='h',
                        marker=dict(
                            color=top_rated[rating_col],
                            colorscale='RdYlGn',
                            cmin=1,
                            cmax=5
                        ),
                        text=top_rated[rating_col].round(1),
                        textposition='outside'
                    )
                ])
                rating_type = "Multi-Signal" if rating_col == 'enhanced_rating' else "Sentiment"
                fig.update_layout(
                    title=f'Top 10 Highest Rated Entities ({rating_type} Rating)',
                    xaxis_title='Rating',
                    yaxis_title='',
                    xaxis=dict(range=[0, 5.5]),
                    height=400,
                    yaxis={'categoryorder': 'total ascending'}
                )
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("No rated entities with 2+ mentions")
        else:
            st.info("No Stage 3 entities available")
    except Exception:
        st.info("No Stage 3 entities available")
