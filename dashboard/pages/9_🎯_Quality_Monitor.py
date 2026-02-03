"""
Quality Monitor Page

Monitor data quality, processing issues, and improvement opportunities.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import pandas as pd

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    load_stage3_canonical_entities,
    load_canonical_insights,
    get_processing_errors,
    get_quality_issues,
    get_videos_summary
)

st.set_page_config(page_title="Quality Monitor", page_icon="🎯", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("🎯 Data Quality Monitor")
st.markdown("Monitor data quality, identify issues, and find improvement opportunities")

# Load data
with st.spinner("Loading quality data..."):
    entities_df = load_stage3_canonical_entities()
    insights_df = load_canonical_insights()
    quality_issues = get_quality_issues()
    processing_errors = get_processing_errors()
    videos_df = get_videos_summary()

# Quality Overview Metrics
st.subheader("📊 Quality Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
    # Calculate data quality score
    if not entities_df.empty:
        geocoded_pct = (entities_df['lat'].notna().sum() / len(entities_df)) if len(entities_df) > 0 else 0

        enrichment_count = 0
        if 'temporal_confidence' in entities_df.columns:
            enrichment_count = entities_df['temporal_confidence'].notna().sum()
        if 'logistics_confidence' in entities_df.columns:
            enrichment_count = max(enrichment_count, entities_df['logistics_confidence'].notna().sum())

        enriched_pct = (enrichment_count / len(entities_df)) if len(entities_df) > 0 else 0

        # Avg confidence (use enhanced_rating_confidence if available)
        if 'enhanced_rating_confidence' in entities_df.columns:
            avg_conf = entities_df['enhanced_rating_confidence'].mean()
        else:
            avg_conf = 0

        # Composite quality score (0-1)
        data_quality_score = (geocoded_pct + enriched_pct + avg_conf) / 3
        st.metric("Data Quality Score", f"{data_quality_score:.2f}", help="Composite: geocoding + enrichment + confidence")
    else:
        st.metric("Data Quality Score", "N/A")

with col2:
    # Total issues detected
    total_issues = (
        len(quality_issues.get('low_confidence_entities', [])) +
        len(quality_issues.get('missing_geocoding', [])) +
        len(quality_issues.get('missing_enrichment', [])) +
        len(quality_issues.get('low_confidence_insights', [])) +
        len(quality_issues.get('single_source_insights', [])) +
        len(quality_issues.get('stale_entities', []))
    )
    st.metric("Issues Detected", total_issues, delta=f"-{total_issues}" if total_issues > 0 else None, help="Total quality warnings")

with col3:
    # Entities needing review
    entities_needing_review = (
        len(quality_issues.get('low_confidence_entities', [])) +
        len(quality_issues.get('missing_geocoding', [])) +
        len(quality_issues.get('missing_enrichment', []))
    )
    st.metric("Entities Needing Review", entities_needing_review, help="Low confidence, missing data")

with col4:
    # Insights needing review
    insights_needing_review = (
        len(quality_issues.get('low_confidence_insights', [])) +
        len(quality_issues.get('single_source_insights', []))
    )
    st.metric("Insights Needing Review", insights_needing_review, help="Low confidence, single source")

st.markdown("---")

# Entity Quality Issues
st.subheader("📍 Entity Quality Issues")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("##### Low Confidence Entities (<0.6)")
    low_conf_entities = quality_issues.get('low_confidence_entities', [])
    if low_conf_entities:
        st.warning(f"Found {len(low_conf_entities)} low confidence entities")

        # Show table
        if len(low_conf_entities) > 0:
            df = pd.DataFrame(low_conf_entities)
            display_cols = ['canonical_name', 'entity_type', 'enhanced_rating_confidence', 'total_mentions']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(low_conf_entities)}")
    else:
        st.success("No low confidence entities")

with col2:
    st.markdown("##### Missing Geocoding")
    missing_geo = quality_issues.get('missing_geocoding', [])
    if missing_geo:
        st.warning(f"Found {len(missing_geo)} entities without coordinates")

        # Show table
        if len(missing_geo) > 0:
            df = pd.DataFrame(missing_geo)
            display_cols = ['canonical_name', 'entity_type', 'city', 'country']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(missing_geo)}")
    else:
        st.success("All entities geocoded")

with col3:
    st.markdown("##### Missing Enrichment")
    missing_enrich = quality_issues.get('missing_enrichment', [])
    if missing_enrich:
        st.warning(f"Found {len(missing_enrich)} entities without temporal/logistics data")

        # Show table
        if len(missing_enrich) > 0:
            df = pd.DataFrame(missing_enrich)
            display_cols = ['canonical_name', 'entity_type', 'city']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(missing_enrich)}")
    else:
        st.success("All entities enriched")

# Quality score distribution
if not entities_df.empty and 'enhanced_rating' in entities_df.columns:
    st.markdown("##### Entity Rating Distribution")
    ratings = entities_df['enhanced_rating'].dropna()

    if not ratings.empty:
        fig = px.histogram(
            ratings,
            nbins=20,
            title="Entity Rating Distribution",
            labels={'value': 'Rating', 'count': 'Count'},
            color_discrete_sequence=['#3498db']
        )
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# Insight Quality Issues
st.subheader("💡 Insight Quality Issues")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("##### Low Confidence Insights (<0.6)")
    low_conf_insights = quality_issues.get('low_confidence_insights', [])
    if low_conf_insights:
        st.warning(f"Found {len(low_conf_insights)} low confidence insights")

        # Show table
        if len(low_conf_insights) > 0:
            df = pd.DataFrame(low_conf_insights)
            display_cols = ['category', 'content', 'confidence_score', 'mention_count']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                # Truncate content
                if 'content' in df.columns:
                    df['content'] = df['content'].apply(lambda x: x[:50] + '...' if len(x) > 50 else x)

                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(low_conf_insights)}")
    else:
        st.success("No low confidence insights")

with col2:
    st.markdown("##### Single-Source Insights")
    single_source = quality_issues.get('single_source_insights', [])
    if single_source:
        st.info(f"Found {len(single_source)} insights from only 1 video")

        # Show table
        if len(single_source) > 0:
            df = pd.DataFrame(single_source)
            display_cols = ['category', 'content', 'confidence_score']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                # Truncate content
                if 'content' in df.columns:
                    df['content'] = df['content'].apply(lambda x: x[:50] + '...' if len(x) > 50 else x)

                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(single_source)}")
    else:
        st.success("All insights have multiple sources")

with col3:
    st.markdown("##### Stale Insights")
    # Note: Stale insights check is based on freshness_score if available
    if 'freshness_score' in insights_df.columns:
        stale_insights = insights_df[insights_df['freshness_score'] < 0.5]
        if not stale_insights.empty:
            st.warning(f"Found {len(stale_insights)} stale insights")

            display_cols = ['category', 'content', 'freshness_score']
            display_cols = [col for col in display_cols if col in stale_insights.columns]

            if display_cols:
                # Truncate content
                stale_display = stale_insights.copy()
                if 'content' in stale_display.columns:
                    stale_display['content'] = stale_display['content'].apply(lambda x: x[:50] + '...' if len(x) > 50 else x)

                st.dataframe(
                    stale_display[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(stale_insights)}")
        else:
            st.success("No stale insights")
    else:
        st.info("Freshness data not available")

st.markdown("---")

# Processing Issues
st.subheader("⚠️ Processing Issues")

if not processing_errors.empty:
    st.warning(f"Found {len(processing_errors)} failed processing stages")

    col1, col2 = st.columns(2)

    with col1:
        # Failed videos table
        st.markdown("##### Failed Videos")
        display_cols = ['video_id', 'title', 'stage', 'error', 'retry_count']
        display_cols = [col for col in display_cols if col in processing_errors.columns]

        if display_cols:
            # Truncate error messages
            error_display = processing_errors.copy()
            if 'error' in error_display.columns:
                error_display['error'] = error_display['error'].apply(lambda x: x[:50] + '...' if len(str(x)) > 50 else str(x))

            st.dataframe(
                error_display[display_cols],
                hide_index=True,
                width="stretch"
            )

    with col2:
        # Failure rate by stage
        st.markdown("##### Failures by Stage")
        if 'stage' in processing_errors.columns:
            stage_failures = processing_errors['stage'].value_counts()

            fig = px.pie(
                values=stage_failures.values,
                names=stage_failures.index,
                title='Failure Distribution by Stage',
                color_discrete_sequence=px.colors.sequential.Reds,
                hole=0.3
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, width="stretch")

else:
    st.success("✅ No processing failures detected")

st.markdown("---")

# Improvement Opportunities
st.subheader("🔧 Improvement Opportunities")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("##### Videos with Low Entity Count")
    if not videos_df.empty:
        # Count entities per video
        from utils.data_loader import load_video_stage2

        low_entity_videos = []
        for _, video in videos_df.iterrows():
            if video['stage_2'] == 'completed':
                stage2_data = load_video_stage2(video['video_id'])
                if stage2_data:
                    entity_count = len(stage2_data.get('entities', []))
                    if entity_count < 10:
                        low_entity_videos.append({
                            'video_id': video['video_id'],
                            'title': video['title'],
                            'entity_count': entity_count
                        })

        if low_entity_videos:
            st.warning(f"Found {len(low_entity_videos)} videos with <10 entities")
            df = pd.DataFrame(low_entity_videos)
            st.dataframe(df.head(10), hide_index=True, width="stretch")
            st.caption(f"Showing 10 of {len(low_entity_videos)}")
        else:
            st.success("All videos have good entity counts")
    else:
        st.info("No video data available")

with col2:
    st.markdown("##### Entities Mentioned Only Once")
    if not entities_df.empty and 'total_mentions' in entities_df.columns:
        single_mention = entities_df[entities_df['total_mentions'] == 1]

        if not single_mention.empty:
            st.info(f"Found {len(single_mention)} entities with 1 mention")
            st.caption("These may be duplicates or errors")

            display_cols = ['canonical_name', 'entity_type', 'city']
            display_cols = [col for col in display_cols if col in single_mention.columns]

            if display_cols:
                st.dataframe(
                    single_mention[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(single_mention)}")
        else:
            st.success("No single-mention entities")
    else:
        st.info("Mention data not available")

with col3:
    st.markdown("##### Missing Temporal/Logistics Data")
    missing_data_count = len(quality_issues.get('missing_enrichment', []))

    if missing_data_count > 0:
        st.warning(f"{missing_data_count} entities need enrichment")
        st.caption("Candidates for LLM enrichment")
    else:
        st.success("All entities have enrichment data")

st.markdown("---")

# Data Freshness Tracking
st.subheader("📅 Data Freshness")

if not entities_df.empty and 'days_since_last_mention' in entities_df.columns:
    col1, col2 = st.columns(2)

    with col1:
        # Days since last update distribution
        st.markdown("##### Days Since Last Mention Distribution")
        days_data = entities_df['days_since_last_mention'].dropna()

        if not days_data.empty:
            fig = px.histogram(
                days_data,
                nbins=30,
                title="Entity Age Distribution",
                labels={'value': 'Days Since Last Mention', 'count': 'Count'},
                color_discrete_sequence=['#e74c3c']
            )
            fig.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch")

    with col2:
        # Stale entities (freshness_score < 0.5)
        st.markdown("##### Stale Entities (Freshness < 0.5)")
        stale_entities = quality_issues.get('stale_entities', [])

        if stale_entities:
            st.warning(f"Found {len(stale_entities)} stale entities")

            df = pd.DataFrame(stale_entities)
            display_cols = ['canonical_name', 'entity_type', 'freshness_score', 'days_since_last_mention']
            display_cols = [col for col in display_cols if col in df.columns]

            if display_cols:
                st.dataframe(
                    df[display_cols].head(10),
                    hide_index=True,
                    width="stretch"
                )
                st.caption(f"Showing 10 of {len(stale_entities)}")
        else:
            st.success("No stale entities")

else:
    st.info("Freshness data not available")

# Navigation
st.markdown("---")
if st.button("← Back to Home", width="stretch"):
    st.switch_page("🏠_Home.py")
