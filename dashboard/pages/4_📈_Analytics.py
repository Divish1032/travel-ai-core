"""
Analytics Page

View analytics, trends, and performance metrics.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    get_videos_summary,
    load_all_entities,
    load_canonical_insights,
    get_geographic_coverage_stats
)

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    # st.divider()
    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("📈 Analytics")
st.markdown("Performance metrics and quality analysis")

# Load data
with st.spinner("Loading analytics data..."):
    videos_df = get_videos_summary()
    entities_df = load_all_entities()
    insights_df = load_canonical_insights()  # Load insights for analytics

if videos_df.empty:
    st.warning("No data available for analytics")
    st.stop()

# Processing Stats
st.subheader("⚙️ Processing Statistics")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_videos = len(videos_df)
    st.metric("Total Videos", total_videos)

with col2:
    completed = len(videos_df[videos_df["all_stages_complete"]])
    st.metric("Fully Processed", completed)

with col3:
    in_progress = len(videos_df[~videos_df["all_stages_complete"]])
    st.metric("In Progress", in_progress)

with col4:
    success_rate = (completed / total_videos * 100) if total_videos > 0 else 0
    st.metric("Success Rate", f"{success_rate:.1f}%")

st.markdown("---")

# Processing timeline
st.subheader("📅 Processing Over Time")

if "upload_date" in videos_df.columns:
    # Parse dates
    videos_df["date"] = pd.to_datetime(videos_df["upload_date"], errors="coerce")
    videos_df["date"] = videos_df["date"].dt.date

    # Group by date
    daily_counts = videos_df.groupby("date").size().reset_index(name="count")

    fig = px.line(
        daily_counts,
        x="date",
        y="count",
        title="Videos Processed Over Time",
        labels={"date": "Date", "count": "Videos Processed"},
        markers=True,
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, width="stretch")
else:
    st.info("Timeline data not available")

st.markdown("---")

# Entity Quality Analysis
st.subheader("🎯 Entity Quality Analysis")

if (
    not entities_df.empty
    and "quality_score" in entities_df.columns
    and "confidence_score" in entities_df.columns
):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Quality Score Distribution")
        fig = px.histogram(
            entities_df,
            x="quality_score",
            nbins=20,
            title="Entity Quality Scores",
            labels={"quality_score": "Quality Score", "count": "Count"},
            color_discrete_sequence=["#3498db"],
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.markdown("#### Confidence Score Distribution")
        fig = px.histogram(
            entities_df,
            x="confidence_score",
            nbins=20,
            title="Entity Confidence Scores",
            labels={"confidence_score": "Confidence Score", "count": "Count"},
            color_discrete_sequence=["#2ecc71"],
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")

    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Avg Quality", f"{entities_df['quality_score'].mean():.2f}")
    with col2:
        st.metric("Avg Confidence", f"{entities_df['confidence_score'].mean():.2f}")
    with col3:
        high_quality = len(entities_df[entities_df["quality_score"] >= 4.0])
        st.metric("High Quality (>4.0)", high_quality)
    with col4:
        low_quality = len(entities_df[entities_df["quality_score"] < 3.0])
        st.metric("Low Quality (<3.0)", low_quality)
else:
    st.info("Entity quality data not available")

st.markdown("---")

# Duration Analysis
st.subheader("⏱️ Video Duration Analysis")

if "duration_seconds" in videos_df.columns:
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Duration Distribution")
        # Convert to minutes
        videos_df["duration_minutes"] = videos_df["duration_seconds"] / 60

        fig = px.histogram(
            videos_df,
            x="duration_minutes",
            nbins=30,
            title="Video Duration Distribution",
            labels={"duration_minutes": "Duration (minutes)", "count": "Count"},
            color_discrete_sequence=["#e74c3c"],
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.markdown("#### Duration Categories")

        # Categorize
        def categorize_duration(seconds):
            if seconds < 300:
                return "Short (<5 min)"
            elif seconds < 1200:
                return "Medium (5-20 min)"
            else:
                return "Long (>20 min)"

        videos_df["duration_category"] = videos_df["duration_seconds"].apply(
            categorize_duration
        )
        category_counts = videos_df["duration_category"].value_counts()

        fig = px.pie(
            values=category_counts.values,
            names=category_counts.index,
            title="Video Duration Categories",
            color_discrete_sequence=px.colors.sequential.RdBu,
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
else:
    st.info("Duration data not available")

st.markdown("---")

# Language Distribution
st.subheader("🌐 Language Distribution")

if "language" in videos_df.columns:
    lang_counts = videos_df["language"].value_counts().head(10)

    fig = px.bar(
        x=lang_counts.index,
        y=lang_counts.values,
        title="Top 10 Languages",
        labels={"x": "Language", "y": "Count"},
        color=lang_counts.values,
        color_continuous_scale="Viridis",
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, width="stretch")
else:
    st.info("Language data not available")

st.markdown("---")

# Data Quality Insights
st.subheader("🔍 Data Quality Insights")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Videos Needing Attention")

    # Low entity count videos
    if not entities_df.empty:
        entity_counts_per_video = entities_df.groupby("video_id").size()
        low_entity_videos = entity_counts_per_video[entity_counts_per_video < 10]

        st.metric("Videos with <10 entities", len(low_entity_videos))

        if len(low_entity_videos) > 0:
            st.caption("These videos may have poor extraction quality")
    else:
        st.info("No entity data available")

with col2:
    st.markdown("#### Stage Completion Issues")

    # Failed or pending stages
    stage_issues = {
        "Stage 1 Pending": len(videos_df[videos_df["stage_1"] == "pending"]),
        "Stage 2 Pending": len(videos_df[videos_df["stage_2"] == "pending"]),
        "Stage 3 Pending": len(videos_df[videos_df["stage_3"] == "pending"]),
    }

    for stage, count in stage_issues.items():
        if count > 0:
            st.warning(f"{stage}: {count} videos")

st.markdown("---")

# Entity Coverage
if not entities_df.empty:
    st.subheader("📊 Entity Coverage Analysis")

    col1, col2 = st.columns(2)

    with col1:
        # Entities per video
        entities_per_video = entities_df.groupby("video_id").size()

        st.metric("Avg Entities per Video", f"{entities_per_video.mean():.1f}")
        st.metric("Max Entities in a Video", entities_per_video.max())
        st.metric("Min Entities in a Video", entities_per_video.min())

    with col2:
        # Entity type breakdown
        if "entity_type" in entities_df.columns:
            type_counts = entities_df["entity_type"].value_counts()

            fig = px.bar(
                x=type_counts.index,
                y=type_counts.values,
                title="Entity Types Distribution",
                labels={"x": "Type", "y": "Count"},
                color=type_counts.values,
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch")

st.markdown("---")

# Insights Pipeline Analytics (NEW)
st.subheader("💡 Insights Pipeline Analytics")

if not insights_df.empty:
    col1, col2 = st.columns(2)

    with col1:
        # Total insights by category
        st.markdown("##### Insights by Category")
        if 'category' in insights_df.columns:
            category_counts = insights_df['category'].value_counts()

            fig = px.bar(
                x=category_counts.index,
                y=category_counts.values,
                title="Total Insights by Category",
                labels={'x': 'Category', 'y': 'Count'},
                color=category_counts.values,
                color_continuous_scale='Oranges'
            )
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Insights by destination type
        st.markdown("##### Insights by Destination Type")
        if 'destination_type' in insights_df.columns:
            dest_type_counts = insights_df['destination_type'].value_counts()

            fig = px.pie(
                values=dest_type_counts.values,
                names=dest_type_counts.index,
                title="Insights by Destination Scope",
                color_discrete_sequence=px.colors.sequential.Oranges,
                hole=0.3
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

    # Average confidence by category
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### Average Confidence by Category")
        if 'category' in insights_df.columns and 'confidence_score' in insights_df.columns:
            avg_confidence = insights_df.groupby('category')['confidence_score'].mean().sort_values(ascending=False)

            fig = go.Figure(data=[
                go.Bar(
                    x=avg_confidence.values,
                    y=avg_confidence.index,
                    orientation='h',
                    marker=dict(
                        color=avg_confidence.values,
                        colorscale='RdYlGn',
                        cmin=0,
                        cmax=1
                    ),
                    text=avg_confidence.round(2),
                    textposition='outside'
                )
            ])
            fig.update_layout(
                title='Average Confidence Score by Category',
                xaxis_title='Confidence',
                yaxis_title='',
                xaxis=dict(range=[0, 1.1]),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Insights timeline (if timestamps available)
        st.markdown("##### Insights Timeline")
        if 'created_at' in insights_df.columns:
            insights_df['date'] = pd.to_datetime(insights_df['created_at'], errors='coerce')
            insights_df['date'] = insights_df['date'].dt.date

            if insights_df['date'].notna().any():
                daily_insights = insights_df.groupby('date').size().reset_index(name='count')

                fig = px.line(
                    daily_insights,
                    x='date',
                    y='count',
                    title='Insights Extracted Over Time',
                    labels={'date': 'Date', 'count': 'Insights'},
                    markers=True
                )
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Timeline data not available for insights")
        else:
            st.info("Timeline data not available")

else:
    st.info("No insights data available yet. Run the insights pipeline to see analytics.")

st.markdown("---")

# Cross-Pipeline Correlation (NEW)
st.subheader("🔀 Cross-Pipeline Analytics")
st.markdown("Compare entities and insights across destinations")

if not insights_df.empty:
    # Get geographic coverage stats
    coverage_df = get_geographic_coverage_stats()

    if not coverage_df.empty:
        col1, col2 = st.columns(2)

        with col1:
            # Entities vs Insights by Destination (scatter plot)
            st.markdown("##### Entities vs Insights by Destination")

            # Filter to show only destinations with data
            plot_df = coverage_df[
                (coverage_df['entity_count'] > 0) | (coverage_df['insight_count'] > 0)
            ].copy()

            if not plot_df.empty:
                # Combine country and city for label
                plot_df['destination'] = plot_df.apply(
                    lambda x: f"{x['city']}, {x['country']}" if pd.notna(x['city']) else str(x['country']),
                    axis=1
                )

                fig = px.scatter(
                    plot_df,
                    x='entity_count',
                    y='insight_count',
                    size='video_count',
                    hover_data=['destination', 'coverage_score'],
                    title='Entity Count vs Insight Count per Destination',
                    labels={'entity_count': 'Entities', 'insight_count': 'Insights'},
                    color='coverage_score',
                    color_continuous_scale='Viridis'
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No destination data available")

        with col2:
            # Top destinations by coverage score
            st.markdown("##### Top Destinations by Coverage")

            if not coverage_df.empty:
                top_destinations = coverage_df.nlargest(10, 'coverage_score')

                # Create destination label
                top_destinations['destination'] = top_destinations.apply(
                    lambda x: f"{x['city']}, {x['country']}" if pd.notna(x['city']) else str(x['country']),
                    axis=1
                )

                fig = px.bar(
                    top_destinations,
                    x='coverage_score',
                    y='destination',
                    orientation='h',
                    title='Top 10 Destinations by Coverage Score',
                    labels={'coverage_score': 'Coverage Score', 'destination': ''},
                    color='coverage_score',
                    color_continuous_scale='Blues'
                )
                fig.update_layout(height=400, showlegend=False, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No coverage data available")

else:
    st.info("Cross-pipeline analytics require insights data. Run the insights pipeline to see correlations.")

# Navigation
st.markdown("---")
if st.button("← Back to Home", width="stretch"):
    st.switch_page("🏠_Home.py")
