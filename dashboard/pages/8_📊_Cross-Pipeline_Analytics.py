"""
Cross-Pipeline Analytics Page

Compare and analyze data across entity pipeline and insights pipeline.
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
    load_stage3_canonical_entities,
    load_canonical_insights,
    get_videos_summary,
    get_geographic_coverage_stats
)

st.set_page_config(page_title="Cross-Pipeline Analytics", page_icon="📊", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("📊 Cross-Pipeline Analytics")
st.markdown("Compare and analyze entity pipeline vs insights pipeline")

# Load data
with st.spinner("Loading cross-pipeline data..."):
    entities_df = load_stage3_canonical_entities()
    insights_df = load_canonical_insights()
    videos_df = get_videos_summary()
    coverage_df = get_geographic_coverage_stats()

if entities_df.empty and insights_df.empty:
    st.warning("No pipeline data available for analysis")
    st.stop()

# Pipeline Comparison Metrics
st.subheader("📈 Pipeline Comparison")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### Entity Pipeline")
    subcol1, subcol2 = st.columns(2)

    with subcol1:
        total_entities = len(entities_df) if not entities_df.empty else 0
        st.metric("Total Entities", total_entities)

        if not entities_df.empty and 'enhanced_rating' in entities_df.columns:
            avg_rating = entities_df['enhanced_rating'].mean()
            st.metric("Avg Rating", f"{avg_rating:.2f}/5")
        else:
            st.metric("Avg Rating", "N/A")

    with subcol2:
        if not entities_df.empty and 'lat' in entities_df.columns:
            geocoded_count = entities_df['lat'].notna().sum()
            geocoded_pct = (geocoded_count / len(entities_df) * 100) if len(entities_df) > 0 else 0
            st.metric("Geocoded", f"{geocoded_pct:.0f}%")
        else:
            st.metric("Geocoded", "N/A")

        st.metric("Processing Cost", "~$0.10/video", help="Estimated entity extraction cost")

with col2:
    st.markdown("### Insights Pipeline")
    subcol1, subcol2 = st.columns(2)

    with subcol1:
        total_insights = len(insights_df) if not insights_df.empty else 0
        st.metric("Total Insights", total_insights)

        if not insights_df.empty and 'confidence_score' in insights_df.columns:
            avg_confidence = insights_df['confidence_score'].mean()
            st.metric("Avg Confidence", f"{avg_confidence:.2f}")
        else:
            st.metric("Avg Confidence", "N/A")

    with subcol2:
        if not insights_df.empty and 'category' in insights_df.columns:
            coverage_pct = (insights_df['category'].nunique() / 8 * 100)  # 8 categories total
            st.metric("Category Coverage", f"{coverage_pct:.0f}%")
        else:
            st.metric("Category Coverage", "N/A")

        st.metric("Processing Cost", "~$0.05/video", help="Estimated insight extraction cost")

st.markdown("---")

# Destination Coverage Comparison
st.subheader("🌍 Destination Coverage")

if not coverage_df.empty:
    col1, col2 = st.columns(2)

    with col1:
        # Sankey Diagram: Videos → Entities + Insights
        st.markdown("##### Pipeline Flow Distribution")

        # Calculate flow data
        total_videos = len(videos_df)
        videos_with_entities = 0
        videos_with_insights = 0
        videos_with_both = 0

        # This is simplified - in reality we'd track per-video
        if total_entities > 0:
            videos_with_entities = len(videos_df[videos_df['stage_3'] == 'completed'])

        if total_insights > 0 and not insights_df.empty:
            # Count unique source videos from insights
            all_video_ids = set()
            for ids in insights_df.get('source_video_ids', []):
                if isinstance(ids, list):
                    all_video_ids.update(ids)
            videos_with_insights = len(all_video_ids)

        # Estimate overlap (simplified)
        videos_with_both = min(videos_with_entities, videos_with_insights)

        # Create Sankey diagram
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=["Videos", "Entity Pipeline", "Insights Pipeline", "Entities", "Insights"],
                color=["lightblue", "lightgreen", "orange", "blue", "red"]
            ),
            link=dict(
                source=[0, 0, 1, 2],  # Videos → Entity Pipeline, Videos → Insights Pipeline, Pipelines → Outputs
                target=[1, 2, 3, 4],
                value=[videos_with_entities, videos_with_insights, total_entities, total_insights],
                color=["rgba(0,255,0,0.3)", "rgba(255,165,0,0.3)", "rgba(0,0,255,0.3)", "rgba(255,0,0,0.3)"]
            )
        )])

        fig.update_layout(
            title="Video Processing Flow",
            height=400,
            font_size=10
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        # Entity Types ↔ Insight Categories correlation
        st.markdown("##### Content Type Distribution")

        # Create a combined bar chart showing entity types and insight categories
        chart_data = []

        if not entities_df.empty and 'entity_type' in entities_df.columns:
            entity_counts = entities_df['entity_type'].value_counts().head(8)
            for etype, count in entity_counts.items():
                chart_data.append({'Type': etype, 'Count': count, 'Pipeline': 'Entity'})

        if not insights_df.empty and 'category' in insights_df.columns:
            category_counts = insights_df['category'].value_counts().head(8)
            for cat, count in category_counts.items():
                chart_data.append({'Type': cat, 'Count': count, 'Pipeline': 'Insight'})

        if chart_data:
            chart_df = pd.DataFrame(chart_data)

            fig = px.bar(
                chart_df,
                x='Type',
                y='Count',
                color='Pipeline',
                barmode='group',
                title='Entity Types vs Insight Categories',
                color_discrete_map={'Entity': '#3498db', 'Insight': '#e74c3c'}
            )
            fig.update_layout(height=400, xaxis_tickangle=-45)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No data available for comparison")

else:
    st.info("Coverage data not available")

st.markdown("---")

# Quality Correlation Analysis
st.subheader("🎯 Quality Correlation")

col1, col2 = st.columns(2)

with col1:
    # Entity Rating vs Insight Confidence (per video)
    st.markdown("##### Entity Rating vs Insight Confidence (per video)")

    # Build per-video aggregation
    video_quality = []

    for _, video in videos_df.iterrows():
        video_id = video['video_id']

        # Get entities for this video
        if not entities_df.empty:
            video_entities = entities_df[
                entities_df.get('raw_json', pd.Series()).apply(
                    lambda x: video_id in x.get('source_video_ids', []) if isinstance(x, dict) else False
                )
            ]

            avg_entity_rating = 0
            if not video_entities.empty and 'enhanced_rating' in video_entities.columns:
                avg_entity_rating = video_entities['enhanced_rating'].mean()

        else:
            avg_entity_rating = 0

        # Get insights for this video
        avg_insight_conf = 0
        if not insights_df.empty and 'source_video_ids' in insights_df.columns:
            video_insights = insights_df[
                insights_df['source_video_ids'].apply(
                    lambda x: video_id in x if isinstance(x, list) else False
                )
            ]

            if not video_insights.empty and 'confidence_score' in video_insights.columns:
                avg_insight_conf = video_insights['confidence_score'].mean()

        # Only include videos with both
        if avg_entity_rating > 0 and avg_insight_conf > 0:
            video_quality.append({
                'video_id': video_id,
                'avg_entity_rating': avg_entity_rating,
                'avg_insight_confidence': avg_insight_conf,
                'duration_category': video.get('duration_formatted', 'Unknown')
            })

    if video_quality:
        quality_df = pd.DataFrame(video_quality)

        fig = px.scatter(
            quality_df,
            x='avg_entity_rating',
            y='avg_insight_confidence',
            color='duration_category',
            title='Entity Rating vs Insight Confidence',
            labels={'avg_entity_rating': 'Avg Entity Rating (1-5)', 'avg_insight_confidence': 'Avg Insight Confidence (0-1)'},
            hover_data=['video_id']
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Not enough data for correlation analysis")

with col2:
    # Entity Type × Insight Category correlation heatmap
    st.markdown("##### Entity-Insight Co-occurrence Heatmap")

    # Build co-occurrence matrix
    correlation_matrix = []

    if not entities_df.empty and not insights_df.empty:
        # For each video, count entity types and insight categories
        entity_types = entities_df['entity_type'].unique() if 'entity_type' in entities_df.columns else []
        insight_categories = insights_df['category'].unique() if 'category' in insights_df.columns else []

        # Build matrix (simplified approach)
        matrix_data = {}

        for etype in entity_types[:8]:  # Limit to top 8
            matrix_data[etype] = {}
            for category in insight_categories[:8]:
                # Count videos that have both this entity type and this insight category
                count = 0
                # Simplified: just show if they exist in the same dataset
                entity_count = len(entities_df[entities_df['entity_type'] == etype])
                insight_count = len(insights_df[insights_df['category'] == category])
                # Normalize
                count = min(entity_count, insight_count) / max(entity_count, insight_count, 1)
                matrix_data[etype][category] = count

        if matrix_data:
            # Convert to DataFrame for heatmap
            heatmap_df = pd.DataFrame(matrix_data).T

            fig = px.imshow(
                heatmap_df,
                labels=dict(x="Insight Category", y="Entity Type", color="Correlation"),
                color_continuous_scale='Blues',
                title='Entity Type × Insight Category Correlation'
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Not enough data for correlation matrix")
    else:
        st.info("Both pipelines need data for correlation analysis")

st.markdown("---")

# Temporal Analysis
st.subheader("📅 Temporal Analysis")

col1, col2 = st.columns(2)

with col1:
    # Entities vs Insights over time
    st.markdown("##### Entities vs Insights Over Time")

    # Prepare timeline data
    timeline_data = []

    # Entities timeline (use entity creation dates if available)
    if not entities_df.empty and 'most_recent_mention' in entities_df.columns:
        entity_dates = pd.to_datetime(entities_df['most_recent_mention'], errors='coerce')
        entity_timeline = entity_dates.dt.date.value_counts().sort_index()

        for date, count in entity_timeline.items():
            timeline_data.append({'date': date, 'count': count, 'type': 'Entities'})

    # Insights timeline
    if not insights_df.empty and 'created_at' in insights_df.columns:
        insight_dates = pd.to_datetime(insights_df['created_at'], errors='coerce')
        insight_timeline = insight_dates.dt.date.value_counts().sort_index()

        for date, count in insight_timeline.items():
            timeline_data.append({'date': date, 'count': count, 'type': 'Insights'})

    if timeline_data:
        timeline_df = pd.DataFrame(timeline_data)

        # Create dual-axis chart
        fig = px.line(
            timeline_df,
            x='date',
            y='count',
            color='type',
            title='Extraction Timeline',
            labels={'date': 'Date', 'count': 'Count'},
            markers=True,
            color_discrete_map={'Entities': '#3498db', 'Insights': '#e74c3c'}
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Timeline data not available")

with col2:
    # Content Richness Score
    st.markdown("##### Content Richness Distribution")

    # Calculate content richness: (entities + insights) / duration
    richness_data = []

    for _, video in videos_df.iterrows():
        video_id = video['video_id']
        duration_minutes = video['duration_seconds'] / 60 if video['duration_seconds'] > 0 else 1

        # Count entities
        entity_count = 0
        if not entities_df.empty:
            video_entities = entities_df[
                entities_df.get('raw_json', pd.Series()).apply(
                    lambda x: video_id in x.get('source_video_ids', []) if isinstance(x, dict) else False
                )
            ]
            entity_count = len(video_entities)

        # Count insights
        insight_count = 0
        if not insights_df.empty and 'source_video_ids' in insights_df.columns:
            video_insights = insights_df[
                insights_df['source_video_ids'].apply(
                    lambda x: video_id in x if isinstance(x, list) else False
                )
            ]
            insight_count = len(video_insights)

        richness = (entity_count + insight_count) / duration_minutes

        if richness > 0:
            richness_data.append({
                'video_id': video_id[:20],
                'richness': richness,
                'entities': entity_count,
                'insights': insight_count
            })

    if richness_data:
        richness_df = pd.DataFrame(richness_data)

        fig = px.histogram(
            richness_df,
            x='richness',
            nbins=20,
            title='Content Richness Score Distribution',
            labels={'richness': 'Content Richness (items/minute)', 'count': 'Videos'},
            color_discrete_sequence=['#9b59b6']
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")

        # Top 10 most content-rich videos
        st.markdown("**Top 10 Content-Rich Videos:**")
        top_rich = richness_df.nlargest(10, 'richness')
        st.dataframe(
            top_rich[['video_id', 'richness', 'entities', 'insights']],
            hide_index=True,
            width="stretch"
        )
    else:
        st.info("Content richness data not available")

st.markdown("---")

# Geographic Coverage - COMMENTED OUT (focusing on Thailand cities only, not country-level comparisons)
# st.subheader("🗺️ Geographic Coverage")
#
# if not coverage_df.empty:
#     col1, col2 = st.columns(2)
#
#     with col1:
#         # Stacked bar: Entities vs Insights by Country
#         st.markdown("##### Entities vs Insights by Country")
#
#         # Get top 10 countries by total content
#         coverage_df['total_content'] = coverage_df['entity_count'] + coverage_df['insight_count']
#         top_countries = coverage_df.nlargest(10, 'total_content')
#
#         # Prepare data for stacked bar
#         stacked_data = []
#         for _, row in top_countries.iterrows():
#             country = row['country'] if pd.notna(row['country']) else 'Unknown'
#             stacked_data.append({'Country': country, 'Type': 'Entities', 'Count': row['entity_count']})
#             stacked_data.append({'Country': country, 'Type': 'Insights', 'Count': row['insight_count']})
#
#         if stacked_data:
#             stacked_df = pd.DataFrame(stacked_data)
#
#             fig = px.bar(
#                 stacked_df,
#                 x='Country',
#                 y='Count',
#                 color='Type',
#                 title='Top 10 Countries by Content',
#                 barmode='stack',
#                 color_discrete_map={'Entities': '#3498db', 'Insights': '#e74c3c'}
#             )
#             fig.update_layout(height=400, xaxis_tickangle=-45)
#             st.plotly_chart(fig, width="stretch")
#
#     with col2:
#         # Coverage gap analysis
#         st.markdown("##### Coverage Gap Analysis")
#
#         # Find countries with high entities but low insights
#         if not coverage_df.empty:
#             coverage_df['entity_insight_ratio'] = coverage_df['entity_count'] / (coverage_df['insight_count'] + 1)
#
#             high_entity_low_insight = coverage_df[
#                 (coverage_df['entity_count'] > 5) &
#                 (coverage_df['entity_insight_ratio'] > 3)
#             ].nlargest(10, 'entity_insight_ratio')
#
#             if not high_entity_low_insight.empty:
#                 st.warning(f"Countries with high entities but low insights:")
#
#                 gap_display = high_entity_low_insight[['country', 'entity_count', 'insight_count']].copy()
#                 gap_display['gap'] = gap_display['entity_count'] - gap_display['insight_count']
#
#                 st.dataframe(
#                     gap_display,
#                     hide_index=True,
#                     width="stretch"
#                 )
#             else:
#                 st.success("Good balance between entities and insights")
#
# else:
#     st.info("Geographic coverage data not available")

# Navigation
st.markdown("---")
if st.button("← Back to Home", width="stretch"):
    st.switch_page("🏠_Home.py")
