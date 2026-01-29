"""
Geographic Coverage Page

Geographic analysis of entities and insights across destinations.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    load_stage3_canonical_entities,
    load_canonical_insights,
    get_geographic_coverage_stats,
    get_videos_summary
)

st.set_page_config(page_title="Geographic Coverage", page_icon="🗺️", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("🗺️ Geographic Coverage")
st.markdown("Analyze entity and insight coverage across global destinations")

# Load data
with st.spinner("Loading geographic data..."):
    entities_df = load_stage3_canonical_entities()
    insights_df = load_canonical_insights()
    coverage_df = get_geographic_coverage_stats()
    videos_df = get_videos_summary()

if coverage_df.empty:
    st.warning("No geographic coverage data available")
    st.info("💡 Process videos with location data to see geographic coverage")
    st.stop()

# Global Coverage Map - COMMENTED OUT (focusing on Thailand cities only, not global country view)
# st.subheader("🌍 Global Coverage Map")

# Prepare map data (aggregate by country) - still needed for other sections
country_coverage = coverage_df.groupby('country').agg({
    'entity_count': 'sum',
    'insight_count': 'sum',
    'video_count': 'sum',
    'coverage_score': 'mean'
}).reset_index()

# Add total content column
country_coverage['total_content'] = country_coverage['entity_count'] + country_coverage['insight_count']

# Calculate avg quality (normalized)
country_coverage['avg_quality'] = country_coverage['coverage_score']

# Create bubble map - COMMENTED OUT
# fig = px.scatter_geo(
#     country_coverage,
#     locations='country',
#     locationmode='country names',
#     size='total_content',
#     color='avg_quality',
#     hover_name='country',
#     hover_data={
#         'entity_count': True,
#         'insight_count': True,
#         'video_count': True,
#         'coverage_score': ':.2f',
#         'avg_quality': False,
#         'total_content': False
#     },
#     color_continuous_scale='Viridis',
#     size_max=50,
#     title='Global Content Coverage (size=content volume, color=quality)',
#     projection='natural earth'
# )
#
# fig.update_layout(
#     height=500,
#     geo=dict(
#         showframe=False,
#         showcoastlines=True,
#         projection_type='natural earth'
#     )
# )
#
# st.plotly_chart(fig, use_container_width=True)
#
# st.markdown("---")

# Coverage Heatmap - COMMENTED OUT (country-level heatmap not needed for Thailand focus)
# st.subheader("🔥 Coverage Heatmap")
#
# col1, col2 = st.columns([2, 1])
#
# with col1:
#     st.markdown("##### Country × Content Type Coverage")
#
#     # Build heatmap data (Country × [Entity Types + Insight Categories])
#     heatmap_data = {}
#
#     # Get top 15 countries by coverage
#     top_countries = country_coverage.nlargest(15, 'total_content')['country'].tolist()
#
#     for country in top_countries:
#         heatmap_data[country] = {}
#
#         # Entity types for this country
#         if not entities_df.empty and 'entity_type' in entities_df.columns:
#             country_entities = entities_df[entities_df['country'] == country]
#             entity_types = country_entities['entity_type'].value_counts()
#
#             for etype, count in entity_types.items():
#                 heatmap_data[country][f"E: {etype}"] = count
#
#         # Insight categories for this country
#         if not insights_df.empty and 'category' in insights_df.columns:
#             country_insights = insights_df[insights_df['country'] == country]
#             insight_categories = country_insights['category'].value_counts()
#
#             for cat, count in insight_categories.items():
#                 heatmap_data[country][f"I: {cat}"] = count
#
#     if heatmap_data:
#         # Convert to DataFrame
#         heatmap_df = pd.DataFrame(heatmap_data).T.fillna(0)
#
#         if not heatmap_df.empty:
#             fig = px.imshow(
#                 heatmap_df,
#                 labels=dict(x="Content Type", y="Country", color="Count"),
#                 color_continuous_scale='Blues',
#                 aspect='auto',
#                 title='Content Type Distribution by Country (E=Entity, I=Insight)'
#             )
#             fig.update_layout(height=500)
#             st.plotly_chart(fig, use_container_width=True)
#         else:
#             st.info("Not enough data for heatmap")
#     else:
#         st.info("Not enough data for heatmap")
#
# with col2:
#     st.markdown("##### Coverage Gap Indicators")
#
#     # Identify gaps
#     gaps = []
#
#     for country in top_countries:
#         country_entities = len(entities_df[entities_df['country'] == country]) if not entities_df.empty else 0
#         country_insights = len(insights_df[insights_df['country'] == country]) if not insights_df.empty else 0
#
#         # Check for entity types
#         if not entities_df.empty and 'entity_type' in entities_df.columns:
#             country_entity_types = entities_df[entities_df['country'] == country]['entity_type'].nunique()
#         else:
#             country_entity_types = 0
#
#         # Check for insight categories
#         if not insights_df.empty and 'category' in insights_df.columns:
#             country_insight_cats = insights_df[insights_df['country'] == country]['category'].nunique()
#         else:
#             country_insight_cats = 0
#
#         # Identify specific gaps
#         if country_entity_types < 3:
#             gaps.append(f"❌ {country}: Limited entity types ({country_entity_types})")
#
#         if country_insight_cats < 3:
#             gaps.append(f"❌ {country}: Limited insight categories ({country_insight_cats})")
#
#         if country_entities > 10 and country_insights < 3:
#             gaps.append(f"⚠️ {country}: High entities, low insights")
#
#         if country_insights > 10 and country_entities < 3:
#             gaps.append(f"⚠️ {country}: High insights, low entities")
#
#     if gaps:
#         st.warning(f"Coverage Gaps Detected ({len(gaps)})")
#         for gap in gaps[:15]:
#             st.caption(gap)
#     else:
#         st.success("✅ Good coverage balance")
#
# st.markdown("---")

# Top Destinations
st.subheader("🏆 Top Destinations")

# with col1: - COMMENTED OUT Top Countries section (focusing on Thailand cities only)
# col1, col2 = st.columns(2)
#
# with col1:
#     st.markdown("##### Top 20 Countries by Content")
#
#     top_countries_display = country_coverage.nlargest(20, 'total_content')
#
#     # Format for display
#     display_df = top_countries_display[['country', 'entity_count', 'insight_count', 'video_count', 'coverage_score']].copy()
#     display_df.columns = ['Country', 'Entities', 'Insights', 'Videos', 'Coverage Score']
#
#     st.dataframe(
#         display_df,
#         hide_index=True,
#         use_container_width=True,
#         column_config={
#             'Coverage Score': st.column_config.ProgressColumn(
#                 'Coverage',
#                 min_value=0,
#                 max_value=display_df['Coverage Score'].max() if not display_df.empty else 1,
#                 format='%.2f'
#             )
#         }
#     )
#
# with col2:

# Keep city-level analysis (Thailand cities)
st.markdown("##### Top 20 Cities by Content (Thailand)")

# Aggregate by city (keep country for context)
if not coverage_df[coverage_df['city'].notna()].empty:
    city_coverage = coverage_df[coverage_df['city'].notna()].copy()

    # Create city display name
    city_coverage['city_display'] = city_coverage.apply(
        lambda x: f"{x['city']}, {x['country']}" if pd.notna(x['city']) and pd.notna(x['country']) else x['city'],
        axis=1
    )

    top_cities = city_coverage.nlargest(20, 'entity_count')

    display_df = top_cities[['city_display', 'entity_count', 'insight_count', 'video_count', 'coverage_score']].copy()
    display_df.columns = ['City', 'Entities', 'Insights', 'Videos', 'Coverage Score']

    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            'Coverage Score': st.column_config.ProgressColumn(
                'Coverage',
                min_value=0,
                max_value=display_df['Coverage Score'].max() if not display_df.empty else 1,
                format='%.2f'
            )
        }
    )
else:
    st.info("No city-level data available")

st.markdown("---")

# Coverage Gap Analysis - COMMENTED OUT (country-level balance analysis not needed for Thailand focus)
# st.subheader("⚖️ Coverage Balance Analysis")
#
# col1, col2 = st.columns(2)
#
# with col1:
#     # Countries with high entities, low insights
#     st.markdown("##### High Entities, Low Insights")
#
#     if not country_coverage.empty:
#         high_entity_low_insight = country_coverage[
#             (country_coverage['entity_count'] > 5) &
#             (country_coverage['insight_count'] < 3)
#         ].nlargest(10, 'entity_count')
#
#         if not high_entity_low_insight.empty:
#             st.warning(f"Found {len(high_entity_low_insight)} countries with imbalance")
#
#             display_df = high_entity_low_insight[['country', 'entity_count', 'insight_count']].copy()
#             display_df['gap'] = display_df['entity_count'] - display_df['insight_count']
#             display_df.columns = ['Country', 'Entities', 'Insights', 'Gap']
#
#             st.dataframe(display_df, hide_index=True, use_container_width=True)
#         else:
#             st.success("✅ Good balance")
#     else:
#         st.info("No data available")
#
# with col2:
#     # Coverage balance scatter
#     st.markdown("##### Entity-Insight Balance")
#
#     if not country_coverage.empty:
#         fig = px.scatter(
#             country_coverage,
#             x='entity_count',
#             y='insight_count',
#             size='video_count',
#             color='coverage_score',
#             hover_data=['country'],
#             title='Content Balance by Country',
#             labels={'entity_count': 'Entities', 'insight_count': 'Insights'},
#             color_continuous_scale='Viridis'
#         )
#
#         # Add diagonal line for perfect balance
#         max_val = max(country_coverage['entity_count'].max(), country_coverage['insight_count'].max())
#         fig.add_trace(go.Scatter(
#             x=[0, max_val],
#             y=[0, max_val],
#             mode='lines',
#             line=dict(dash='dash', color='gray'),
#             showlegend=False,
#             name='Perfect Balance'
#         ))
#
#         fig.update_layout(height=400)
#         st.plotly_chart(fig, use_container_width=True)
#     else:
#         st.info("No data available")
#
# st.markdown("---")

# Destination Deep Dive (Thailand Cities)
st.subheader("🔍 Destination Deep Dive (Thailand)")

# Country/City selector - MODIFIED to default to Thailand
col1, col2 = st.columns([1, 3])

with col1:
    # Select country - COMMENTED OUT, defaulting to Thailand
    # available_countries = sorted(country_coverage['country'].dropna().unique().tolist())
    # selected_country = st.selectbox("Select Country", available_countries)
    selected_country = 'Thailand'  # Default to Thailand
    st.info(f"📍 Showing: {selected_country}")

    # Select city (Thailand cities only)
    if selected_country:
        country_cities = ['All Cities']
        if not coverage_df.empty:
            city_list = coverage_df[
                (coverage_df['country'] == selected_country) &
                (coverage_df['city'].notna())
            ]['city'].unique().tolist()
            country_cities += sorted(city_list)

        selected_city = st.selectbox("Select City (optional)", country_cities)

if selected_country:
    # Filter data for selected destination
    dest_entities = entities_df[entities_df['country'] == selected_country] if not entities_df.empty else pd.DataFrame()
    dest_insights = insights_df[insights_df['country'] == selected_country] if not insights_df.empty else pd.DataFrame()

    if selected_city and selected_city != 'All Cities':
        dest_entities = dest_entities[dest_entities['city'] == selected_city] if not dest_entities.empty else pd.DataFrame()
        dest_insights = dest_insights[dest_insights['city'] == selected_city] if not dest_insights.empty else pd.DataFrame()

    # Tabs for deep dive
    tab1, tab2, tab3, tab4 = st.tabs(["📍 Entities", "💡 Insights", "🎬 Videos", "📊 Quality"])

    with tab1:
        st.markdown(f"### Entities in {selected_city if selected_city != 'All Cities' else selected_country}")

        if not dest_entities.empty:
            col1, col2 = st.columns(2)

            with col1:
                # Entity type breakdown
                st.markdown("##### Entity Types")
                if 'entity_type' in dest_entities.columns:
                    type_counts = dest_entities['entity_type'].value_counts()

                    fig = px.pie(
                        values=type_counts.values,
                        names=type_counts.index,
                        title=f'Entity Types ({len(dest_entities)} total)',
                        color_discrete_sequence=px.colors.sequential.Teal
                    )
                    fig.update_layout(height=300)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                # Map of entity locations (if coordinates available)
                st.markdown("##### Entity Locations")
                if 'lat' in dest_entities.columns and 'lon' in dest_entities.columns:
                    geo_entities = dest_entities[dest_entities['lat'].notna() & dest_entities['lon'].notna()]

                    if not geo_entities.empty:
                        fig = px.scatter_mapbox(
                            geo_entities,
                            lat='lat',
                            lon='lon',
                            hover_name='canonical_name',
                            hover_data=['entity_type', 'total_mentions'],
                            size='total_mentions',
                            color='entity_type',
                            zoom=6,
                            height=300
                        )
                        fig.update_layout(mapbox_style="open-street-map")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No geocoded entities")
                else:
                    st.info("Coordinates not available")

            # Top entities
            st.markdown("##### Top Entities")
            if 'total_mentions' in dest_entities.columns:
                top_entities = dest_entities.nlargest(10, 'total_mentions')
                display_cols = ['canonical_name', 'entity_type', 'total_mentions', 'enhanced_rating']
                display_cols = [col for col in display_cols if col in top_entities.columns]

                st.dataframe(
                    top_entities[display_cols],
                    hide_index=True,
                    use_container_width=True
                )
        else:
            st.info("No entities found for this destination")

    with tab2:
        st.markdown(f"### Insights for {selected_city if selected_city != 'All Cities' else selected_country}")

        if not dest_insights.empty:
            # Insights by category
            st.markdown("##### Insights by Category")
            if 'category' in dest_insights.columns:
                cat_counts = dest_insights['category'].value_counts()

                fig = px.bar(
                    x=cat_counts.index,
                    y=cat_counts.values,
                    title=f'Insight Categories ({len(dest_insights)} total)',
                    labels={'x': 'Category', 'y': 'Count'},
                    color=cat_counts.values,
                    color_continuous_scale='Oranges'
                )
                fig.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            # List of insights
            st.markdown("##### Insights List")
            for _, insight in dest_insights.head(10).iterrows():
                category = insight.get('category', 'unknown')
                content = insight.get('content', '')
                title = insight.get('title', '')
                confidence = insight.get('confidence_score', 0)

                with st.expander(f"**{category.upper()}** | {title if title else content[:60]}", expanded=False):
                    st.write(content)
                    st.caption(f"Confidence: {confidence:.2f} | Mentions: {insight.get('mention_count', 0)}")
        else:
            st.info("No insights found for this destination")

    with tab3:
        st.markdown(f"### Videos featuring {selected_city if selected_city != 'All Cities' else selected_country}")

        # Get videos for this destination
        dest_video_ids = set()

        if not dest_entities.empty:
            for _, entity in dest_entities.iterrows():
                raw = entity.get('raw_json', {})
                if isinstance(raw, dict):
                    source_ids = raw.get('source_video_ids', [])
                    dest_video_ids.update(source_ids)

        if dest_video_ids:
            dest_videos = videos_df[videos_df['video_id'].isin(dest_video_ids)]

            if not dest_videos.empty:
                st.metric("Total Videos", len(dest_videos))

                display_cols = ['video_id', 'title', 'duration_formatted', 'stage_1', 'stage_2', 'stage_3']
                display_cols = [col for col in display_cols if col in dest_videos.columns]

                st.dataframe(
                    dest_videos[display_cols],
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No video data available")
        else:
            st.info("No videos found for this destination")

    with tab4:
        st.markdown(f"### Quality Metrics for {selected_city if selected_city != 'All Cities' else selected_country}")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### Entity Quality")

            if not dest_entities.empty:
                # Geocoding rate
                if 'lat' in dest_entities.columns:
                    geocoded = dest_entities['lat'].notna().sum()
                    geocoded_pct = (geocoded / len(dest_entities) * 100) if len(dest_entities) > 0 else 0
                    st.metric("Geocoded", f"{geocoded_pct:.0f}%")

                # Avg rating
                if 'enhanced_rating' in dest_entities.columns:
                    avg_rating = dest_entities['enhanced_rating'].mean()
                    st.metric("Avg Rating", f"{avg_rating:.2f}/5")

                # Enrichment rate
                if 'temporal_confidence' in dest_entities.columns or 'logistics_confidence' in dest_entities.columns:
                    enriched = 0
                    if 'temporal_confidence' in dest_entities.columns:
                        enriched = max(enriched, dest_entities['temporal_confidence'].notna().sum())
                    if 'logistics_confidence' in dest_entities.columns:
                        enriched = max(enriched, dest_entities['logistics_confidence'].notna().sum())

                    enriched_pct = (enriched / len(dest_entities) * 100) if len(dest_entities) > 0 else 0
                    st.metric("Enriched", f"{enriched_pct:.0f}%")
            else:
                st.info("No entity data")

        with col2:
            st.markdown("##### Insight Quality")

            if not dest_insights.empty:
                # Avg confidence
                if 'confidence_score' in dest_insights.columns:
                    avg_conf = dest_insights['confidence_score'].mean()
                    st.metric("Avg Confidence", f"{avg_conf:.2f}")

                # Avg mentions
                if 'mention_count' in dest_insights.columns:
                    avg_mentions = dest_insights['mention_count'].mean()
                    st.metric("Avg Mentions", f"{avg_mentions:.1f}")

                # Category coverage
                if 'category' in dest_insights.columns:
                    cat_coverage = dest_insights['category'].nunique()
                    st.metric("Categories Covered", f"{cat_coverage}/8")
            else:
                st.info("No insight data")

# Navigation
st.markdown("---")
if st.button("← Back to Home", use_container_width=True):
    st.switch_page("🏠_Home.py")
