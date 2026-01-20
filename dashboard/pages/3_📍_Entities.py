"""
Entities Explorer Page

Explore all entities extracted across all videos.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_all_entities

st.set_page_config(page_title="Entities", page_icon="📍", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # st.divider()
    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("📍 Entities Explorer")
st.markdown("Explore all entities extracted across all videos")

# Load data
with st.spinner("Loading entities..."):
    entities_df = load_all_entities()

if entities_df.empty:
    st.warning("No entities found. Process videos through Stage 2 to see entities here!")
    st.stop()

# Summary metrics
st.subheader("📊 Summary")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Entities", len(entities_df))
with col2:
    st.metric("Unique Entity Names", entities_df['entity_name'].nunique())
with col3:
    st.metric("Locations", entities_df['location'].nunique())
with col4:
    st.metric("Videos", entities_df['video_id'].nunique())

st.markdown("---")

# Filters
st.subheader("🔍 Filters")
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Entity type filter
    entity_types = ['All'] + sorted([x for x in entities_df['entity_type'].unique() if x is not None])
    type_filter = st.selectbox("Entity Type", entity_types)

with col2:
    # Location filter
    locations = ['All'] + sorted([x for x in entities_df['location'].unique() if x is not None])
    location_filter = st.selectbox("Location", locations)

with col3:
    # Sentiment filter
    sentiments = ['All', 'positive', 'negative', 'neutral']
    sentiment_filter = st.selectbox("Sentiment", sentiments)

with col4:
    # Search
    search_query = st.text_input("🔍 Search entity name", "")

# Apply filters
filtered_df = entities_df.copy()

if type_filter != 'All':
    filtered_df = filtered_df[filtered_df['entity_type'] == type_filter]

if location_filter != 'All':
    filtered_df = filtered_df[filtered_df['location'] == location_filter]

if sentiment_filter != 'All':
    filtered_df = filtered_df[filtered_df['sentiment'] == sentiment_filter]

if search_query:
    filtered_df = filtered_df[filtered_df['entity_name'].str.contains(search_query, case=False, na=False)]

st.markdown(f"**Showing {len(filtered_df)} of {len(entities_df)} entities**")

st.markdown("---")

# Top entities
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Top 20 Most Mentioned")
    if not filtered_df.empty:
        top_entities = filtered_df['entity_name'].value_counts().head(20)
        fig = px.bar(
            x=top_entities.values,
            y=top_entities.index,
            orientation='h',
            labels={'x': 'Mentions', 'y': 'Entity'},
            title='Most Frequently Mentioned Entities',
            color=top_entities.values,
            color_continuous_scale='Viridis'
        )
        fig.update_layout(height=500, showlegend=False, yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No data")

with col2:
    st.subheader("📊 Sentiment Distribution")
    if not filtered_df.empty:
        sentiment_counts = filtered_df['sentiment'].value_counts()
        colors = {'positive': '#2ecc71', 'neutral': '#95a5a6', 'negative': '#e74c3c'}
        fig = px.pie(
            values=sentiment_counts.values,
            names=sentiment_counts.index,
            title='Entity Sentiment Breakdown',
            color=sentiment_counts.index,
            color_discrete_map=colors
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No data")

st.markdown("---")

# Entities by location
st.subheader("🗺️ Entities by Location")
if not filtered_df.empty:
    location_counts = filtered_df['location'].value_counts().head(15)
    fig = px.bar(
        x=location_counts.index,
        y=location_counts.values,
        labels={'x': 'Location', 'y': 'Count'},
        title='Top 15 Locations by Entity Count',
        color=location_counts.values,
        color_continuous_scale='Blues'
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, width='stretch')
else:
    st.info("No data")

st.markdown("---")

# Detailed entities table
st.subheader("📋 All Entities")

if not filtered_df.empty:
    # Aggregate by entity name
    entity_agg = filtered_df.groupby('entity_name').agg({
        'entity_type': 'first',
        'location': 'first',
        'video_id': 'count',
        'sentiment': lambda x: x.mode()[0] if len(x.mode()) > 0 else 'neutral',
        'quality_score': 'mean',
        'confidence_score': 'mean'
    }).reset_index()

    entity_agg.columns = ['Entity Name', 'Type', 'Location', 'Mentions', 'Sentiment', 'Avg Quality', 'Avg Confidence']

    # Round numerical columns
    entity_agg['Avg Quality'] = entity_agg['Avg Quality'].round(2)
    entity_agg['Avg Confidence'] = entity_agg['Avg Confidence'].round(2)

    # Sort by mentions
    entity_agg = entity_agg.sort_values('Mentions', ascending=False)

    # Display
    st.dataframe(
        entity_agg,
        width="stretch",
        hide_index=True,
        column_config={
            "Entity Name": st.column_config.TextColumn("Entity Name", width="large"),
            "Type": st.column_config.TextColumn("Type", width="medium"),
            "Location": st.column_config.TextColumn("Location", width="medium"),
            "Mentions": st.column_config.NumberColumn("Mentions", width="small"),
            "Sentiment": st.column_config.TextColumn("Sentiment", width="small"),
            "Avg Quality": st.column_config.NumberColumn("Avg Quality", width="small", format="%.2f"),
            "Avg Confidence": st.column_config.NumberColumn("Avg Conf", width="small", format="%.2f"),
        }
    )

    # Export
    st.markdown("---")
    st.subheader("📥 Export")

    col1, col2 = st.columns(2)
    with col1:
        csv_data = entity_agg.to_csv(index=False)
        st.download_button(
            "Download as CSV",
            data=csv_data,
            file_name="travelai_entities.csv",
            mime="text/csv",
            width='stretch'
        )

    with col2:
        json_data = entity_agg.to_json(orient='records', indent=2)
        st.download_button(
            "Download as JSON",
            data=json_data,
            file_name="travelai_entities.json",
            mime="application/json",
            width='stretch'
        )
else:
    st.warning("No entities match your filters")

# Navigation
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    if st.button("← Back to Videos", width='stretch'):
        st.switch_page("pages/1_🎬_Videos.py")
with col2:
    if st.button("View Analytics →", width='stretch'):
        st.switch_page("pages/4_📈_Analytics.py")
