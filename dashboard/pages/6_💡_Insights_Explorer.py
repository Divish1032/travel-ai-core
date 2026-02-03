"""
Insights Explorer Page

Browse and search canonical travel insights across categories and destinations.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_canonical_insights

st.set_page_config(page_title="Insights Explorer", page_icon="💡", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("💡 Travel Insights Explorer")
st.markdown(
    "**Insights Pipeline**: Browse canonical travel insights (services, tips, logistics, cultural info)"
)

# Load insights data
with st.spinner("Loading insights..."):
    insights_df = load_canonical_insights()

if insights_df.empty:
    st.warning("No insights data available yet")
    st.info(
        "💡 Run the insights pipeline to extract travel tips, services, and practical information from videos!"
    )
    st.stop()

# Summary Metrics
st.subheader("📊 Summary")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    total_insights = len(insights_df)
    st.metric("Total Insights", total_insights, help="Total canonical insights")

with col2:
    # Unique destinations (count unique combinations of country/city)
    destinations = insights_df.copy()
    destinations = destinations[destinations["country"].notna()]
    unique_destinations = (
        destinations.groupby(["country", "city"]).size().reset_index().shape[0]
    )
    st.metric(
        "Unique Destinations", unique_destinations, help="Unique destination coverage"
    )

with col3:
    # Average confidence
    if "confidence_score" in insights_df.columns:
        avg_confidence = insights_df["confidence_score"].mean()
        st.metric(
            "Avg Confidence",
            f"{avg_confidence:.2f}",
            help="Average confidence score (0-1)",
        )
    else:
        st.metric("Avg Confidence", "N/A")

with col4:
    # Total source videos
    if "source_video_ids" in insights_df.columns:
        all_video_ids = set()
        for ids in insights_df["source_video_ids"]:
            if isinstance(ids, list):
                all_video_ids.update(ids)
        st.metric(
            "Source Videos", len(all_video_ids), help="Videos contributing insights"
        )
    else:
        st.metric("Source Videos", "N/A")

with col5:
    # Categories covered
    if "category" in insights_df.columns:
        categories_covered = insights_df["category"].nunique()
        st.metric("Categories", categories_covered, help="Insight categories covered")
    else:
        st.metric("Categories", "N/A")

st.markdown("---")

# Filters
st.subheader("🔍 Filters")

col1, col2, col3 = st.columns(3)

with col1:
    # Category filter
    if "category" in insights_df.columns:
        categories = ["All"] + sorted(
            insights_df["category"].dropna().unique().tolist()
        )
        selected_category = st.selectbox("Category", categories)
    else:
        selected_category = "All"

    # Destination type filter
    if "destination_type" in insights_df.columns:
        dest_types = ["All"] + sorted(
            insights_df["destination_type"].dropna().unique().tolist()
        )
        selected_dest_type = st.selectbox("Destination Type", dest_types)
    else:
        selected_dest_type = "All"

with col2:
    # Country filter - COMMENTED OUT (focusing on Thailand only)
    # if 'country' in insights_df.columns:
    #     countries = ['All'] + sorted(insights_df['country'].dropna().unique().tolist())
    #     selected_country = st.selectbox("Country", countries)
    # else:
    #     selected_country = 'All'
    selected_country = "All"  # Default since we're focusing on Thailand cities

    # City filter (Thailand cities)
    if "city" in insights_df.columns:
        cities = ["All"] + sorted(insights_df["city"].dropna().unique().tolist())
        selected_city = st.selectbox("City", cities)
    else:
        selected_city = "All"

with col3:
    # Confidence slider
    if "confidence_score" in insights_df.columns:
        min_confidence = st.slider(
            "Min Confidence Score",
            min_value=0.0,
            max_value=1.0,
            value=0.0,
            step=0.1,
            help="Filter by minimum confidence score",
        )
    else:
        min_confidence = 0.0

    # Mention count slider
    if "mention_count" in insights_df.columns:
        max_mentions = (
            int(insights_df["mention_count"].max())
            if insights_df["mention_count"].max() > 0
            else 10
        )
        min_mentions = st.slider(
            "Min Mention Count",
            min_value=0,
            max_value=max_mentions,
            value=0,
            help="Filter by minimum mentions",
        )
    else:
        min_mentions = 0

# Search box
search_query = st.text_input(
    "🔎 Search by content", placeholder="Type to search in insight content..."
)

# Apply filters
filtered_df = insights_df.copy()

if selected_category != "All":
    filtered_df = filtered_df[filtered_df["category"] == selected_category]

if selected_dest_type != "All":
    filtered_df = filtered_df[filtered_df["destination_type"] == selected_dest_type]

if selected_country != "All":
    filtered_df = filtered_df[filtered_df["country"] == selected_country]

if selected_city != "All":
    filtered_df = filtered_df[filtered_df["city"] == selected_city]

if "confidence_score" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["confidence_score"] >= min_confidence]

if "mention_count" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["mention_count"] >= min_mentions]

# Search filter
if search_query:
    if "content" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["content"].str.contains(search_query, case=False, na=False)
            | filtered_df.get("title", pd.Series()).str.contains(
                search_query, case=False, na=False
            )
        ]

st.caption(f"Showing {len(filtered_df)} of {len(insights_df)} insights")

if filtered_df.empty:
    st.warning("No insights match the selected filters")
    st.stop()

st.markdown("---")

# Visualizations
st.subheader("📊 Visualizations")

col1, col2 = st.columns(2)

with col1:
    # Treemap: Insights by category > destination
    st.markdown("##### Insights by Category & Destination")

    if "category" in filtered_df.columns and "country" in filtered_df.columns:
        # Prepare treemap data
        treemap_data = filtered_df.copy()
        treemap_data["destination"] = treemap_data.apply(
            lambda x: f"{x['city']}, {x['country']}"
            if pd.notna(x["city"])
            else (x["country"] if pd.notna(x["country"]) else "Global"),
            axis=1,
        )

        # Group by category and destination
        treemap_grouped = (
            treemap_data.groupby(["category", "destination"])
            .agg({"mention_count": "sum", "confidence_score": "mean"})
            .reset_index()
        )

        if not treemap_grouped.empty:
            fig = px.treemap(
                treemap_grouped,
                path=["category", "destination"],
                values="mention_count",
                color="confidence_score",
                color_continuous_scale="RdYlGn",
                title="Insights Hierarchy (size=mentions, color=confidence)",
                range_color=[0, 1],
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Not enough data for treemap")
    else:
        st.info("Treemap data not available")

with col2:
    # Sunburst: Category > Destination Type > Country
    st.markdown("##### Category Hierarchy")

    if "category" in filtered_df.columns and "destination_type" in filtered_df.columns:
        sunburst_data = filtered_df.copy()

        # Create hierarchy: category > destination_type > country
        sunburst_grouped = (
            sunburst_data.groupby(["category", "destination_type", "country"])
            .size()
            .reset_index(name="count")
        )

        if not sunburst_grouped.empty:
            fig = px.sunburst(
                sunburst_grouped,
                path=["category", "destination_type", "country"],
                values="count",
                title="Insight Categories & Scope",
                color_discrete_sequence=px.colors.sequential.Oranges,
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Not enough data for sunburst chart")
    else:
        st.info("Sunburst data not available")

# Top insights charts
col1, col2 = st.columns(2)

with col1:
    st.markdown("##### Top 15 Most Mentioned Insights")
    if "mention_count" in filtered_df.columns and "content" in filtered_df.columns:
        top_mentioned = filtered_df.nlargest(15, "mention_count")

        # Truncate content for display
        top_mentioned["display"] = top_mentioned.apply(
            lambda x: x["title"]
            if x.get("title")
            else (
                x["content"][:50] + "..." if len(x["content"]) > 50 else x["content"]
            ),
            axis=1,
        )

        fig = px.bar(
            top_mentioned,
            x="mention_count",
            y="display",
            orientation="h",
            title="Top Mentioned Insights",
            labels={"mention_count": "Mentions", "display": ""},
            color="mention_count",
            color_continuous_scale="Blues",
        )
        fig.update_layout(
            height=400, showlegend=False, yaxis={"categoryorder": "total ascending"}
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Mention data not available")

with col2:
    st.markdown("##### Top 15 Highest Confidence Insights")
    if "confidence_score" in filtered_df.columns and "content" in filtered_df.columns:
        top_confidence = filtered_df.nlargest(15, "confidence_score")

        # Truncate content for display
        top_confidence["display"] = top_confidence.apply(
            lambda x: x["title"]
            if x.get("title")
            else (
                x["content"][:50] + "..." if len(x["content"]) > 50 else x["content"]
            ),
            axis=1,
        )

        fig = go.Figure(
            data=[
                go.Bar(
                    x=top_confidence["confidence_score"],
                    y=top_confidence["display"],
                    orientation="h",
                    marker=dict(
                        color=top_confidence["confidence_score"],
                        colorscale="RdYlGn",
                        cmin=0,
                        cmax=1,
                    ),
                    text=top_confidence["confidence_score"].round(2),
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(
            title="Highest Confidence Insights",
            xaxis_title="Confidence",
            yaxis_title="",
            xaxis=dict(range=[0, 1.1]),
            height=400,
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Confidence data not available")

st.markdown("---")

# Insights Table
st.subheader("📋 Insights Details")

# Export options
col1, col2 = st.columns([1, 3])
with col1:
    # Download as CSV
    csv_data = filtered_df[
        [
            "insight_id",
            "category",
            "content",
            "title",
            "confidence_score",
            "mention_count",
            "video_count",
            "country",
            "city",
        ]
    ].copy()
    csv = csv_data.to_csv(index=False)
    st.download_button(
        "📥 Download as CSV",
        data=csv,
        file_name="insights_export.csv",
        mime="text/csv",
        width="stretch",
    )

with col2:
    st.write("")  # Spacer

# Display insights as expandable cards
for idx, insight in filtered_df.iterrows():
    category = insight.get("category", "unknown")
    title = insight.get("title", "")
    content = insight.get("content", "")
    confidence = insight.get("confidence_score", 0)

    # Create header
    display_title = (
        title if title else (content[:80] + "..." if len(content) > 80 else content)
    )

    with st.expander(f"**{category.upper()}** | {display_title}", expanded=False):
        col1, col2 = st.columns([2, 1])

        with col1:
            # Content
            st.markdown(f"**Content:** {content}")
            if title:
                st.markdown(f"**Title:** {title}")

            # Details
            details = insight.get("details")
            if details:
                st.markdown(f"**Details:** _{details}_")

            # Scope
            st.markdown("**Scope:**")
            scope_items = []
            if insight.get("destination_type"):
                scope_items.append(f"Type: {insight['destination_type']}")
            if insight.get("country"):
                scope_items.append(f"Country: {insight['country']}")
            if insight.get("city"):
                scope_items.append(f"City: {insight['city']}")
            if insight.get("region"):
                scope_items.append(f"Region: {insight['region']}")
            if insight.get("area"):
                scope_items.append(f"Area: {insight['area']}")

            if scope_items:
                st.write(" | ".join(scope_items))
            else:
                st.write("Global")

        with col2:
            # Metrics
            st.metric("Confidence", f"{confidence:.2f}")
            st.metric("Mentions", insight.get("mention_count", 0))
            st.metric("Videos", insight.get("video_count", 0))

            # Quality scores if available
            if insight.get("quality_score"):
                st.metric("Quality", f"{insight['quality_score']:.2f}")
            if insight.get("freshness_score"):
                st.metric("Freshness", f"{insight['freshness_score']:.2f}")

        # Tags
        tags = insight.get("tags", [])
        if tags:
            tag_str = " ".join([f"`{tag}`" for tag in tags[:10]])
            st.markdown(f"**Tags:** {tag_str}")

        # Source videos
        source_videos = insight.get("source_video_ids", [])
        if source_videos:
            st.caption(
                f"Source Videos ({len(source_videos)}): {', '.join(source_videos[:5])}{'...' if len(source_videos) > 5 else ''}"
            )

        # Extraction method
        extraction_method = insight.get("extraction_method")
        if extraction_method:
            st.caption(f"Extraction Method: {extraction_method}")

# Navigation
st.markdown("---")
if st.button("← Back to Home", width="stretch"):
    st.switch_page("🏠_Home.py")
