"""
Entities Explorer Page

Explore canonical entities from Stage 3 with deduplication, consensus, and enrichment.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.express as px
import pandas as pd
import json

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_stage3_canonical_entities

st.set_page_config(page_title="Entities", page_icon="📍", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("📍 Canonical Entities Explorer")
st.markdown(
    "**Stage 3**: Deduplicated entities with consensus, geolocation, and enrichment"
)

# Load Stage 3 canonical entities
with st.spinner("Loading canonical entities from Stage 3..."):
    entities_df = load_stage3_canonical_entities()

if entities_df.empty:
    st.warning(
        "No canonical entities found. Process videos through Stage 3 to see entities here!"
    )
    st.info(
        "💡 Stage 3 deduplicates entities from Stage 2, adds consensus data, geocoding, temporal & logistics info."
    )
    st.stop()

# Summary metrics
st.subheader("📊 Summary")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Entities", len(entities_df))
with col2:
    st.metric(
        "Unique Cities", entities_df["city"].nunique() if "city" in entities_df else 0
    )
with col3:
    total_mentions = (
        entities_df["total_mentions"].sum() if "total_mentions" in entities_df else 0
    )
    st.metric("Total Mentions", int(total_mentions))
with col4:
    geocoded = entities_df["lat"].notna().sum() if "lat" in entities_df else 0
    st.metric("Geocoded", f"{geocoded} ({geocoded / len(entities_df) * 100:.0f}%)")
with col5:
    avg_rating = entities_df["avg_rating"].mean() if "avg_rating" in entities_df else 0
    st.metric("Avg Rating", f"{avg_rating:.1f}/5" if avg_rating > 0 else "N/A")

st.markdown("---")

# Filters
st.subheader("🔍 Filters")
col1, col2, col3, col4 = st.columns(4)

with col1:
    entity_types = ["All"] + sorted(
        [x for x in entities_df["entity_type"].unique() if x is not None]
    )
    type_filter = st.selectbox("Entity Type", entity_types)

with col2:
    cities = ["All"] + sorted(
        [x for x in entities_df["city"].unique() if x is not None and x != "unknown"]
    )
    city_filter = st.selectbox("City", cities)

with col3:
    max_mentions_value = (
        int(entities_df["total_mentions"].max())
        if len(entities_df) > 0 and entities_df["total_mentions"].max() > 0
        else 10
    )
    max_mentions = max(max_mentions_value, 2)  # Ensure max is at least 2
    min_mentions = st.slider("Min Mentions", 1, max_mentions, 1)

with col4:
    search_query = st.text_input("🔍 Search entity name", "")

# Apply filters
filtered_df = entities_df.copy()

if type_filter != "All":
    filtered_df = filtered_df[filtered_df["entity_type"] == type_filter]

if city_filter != "All":
    filtered_df = filtered_df[filtered_df["city"] == city_filter]

if min_mentions > 1:
    # Handle None and NaN values - treat them as 0
    filtered_df = filtered_df[filtered_df["total_mentions"].fillna(0) >= min_mentions]

if search_query:
    filtered_df = filtered_df[
        filtered_df["canonical_name"].str.contains(search_query, case=False, na=False)
        | filtered_df["aliases"].str.contains(search_query, case=False, na=False)
    ]

st.markdown(f"**Showing {len(filtered_df)} of {len(entities_df)} entities**")

st.markdown("---")

# Top entities and visualizations
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Top 15 Most Mentioned")
    if not filtered_df.empty and "total_mentions" in filtered_df:
        top_entities = filtered_df.nlargest(15, "total_mentions")[
            ["canonical_name", "total_mentions", "avg_rating"]
        ]
        fig = px.bar(
            top_entities,
            x="total_mentions",
            y="canonical_name",
            orientation="h",
            color="avg_rating",
            color_continuous_scale="RdYlGn",
            range_color=[1, 5],
            labels={
                "total_mentions": "Mentions",
                "canonical_name": "Entity",
                "avg_rating": "Rating",
            },
            title="Most Popular Entities (by mentions)",
        )
        fig.update_layout(
            height=500, showlegend=False, yaxis={"categoryorder": "total ascending"}
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No data")

with col2:
    st.subheader("⭐ Top 15 Highest Rated")
    if not filtered_df.empty and "avg_rating" in filtered_df:
        # Filter entities with at least 2 mentions for reliable ratings
        rated = filtered_df[filtered_df["total_mentions"] >= 2].copy()
        if not rated.empty:
            top_rated = rated.nlargest(15, "avg_rating")[
                ["canonical_name", "avg_rating", "total_mentions"]
            ]
            fig = px.bar(
                top_rated,
                x="avg_rating",
                y="canonical_name",
                orientation="h",
                color="total_mentions",
                color_continuous_scale="Blues",
                labels={
                    "avg_rating": "Avg Rating",
                    "canonical_name": "Entity",
                    "total_mentions": "Mentions",
                },
                title="Top Rated Entities (min 2 mentions)",
            )
            fig.update_layout(
                height=500, showlegend=False, yaxis={"categoryorder": "total ascending"}
            )
            fig.update_xaxes(range=[0, 5])
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No entities with 2+ mentions")
    else:
        st.info("No data")

st.markdown("---")

# Map visualization (if geocoded)
if not filtered_df.empty and "lat" in filtered_df and "lon" in filtered_df:
    geocoded_df = filtered_df.dropna(subset=["lat", "lon"])

    if not geocoded_df.empty:
        st.subheader("🗺️ Entity Map")

        # Prepare map data
        map_data = geocoded_df.copy()
        map_data["size"] = map_data["total_mentions"] * 5  # Scale for visibility
        map_data["color_value"] = map_data["avg_rating"].fillna(
            3
        )  # Default to 3 if no rating

        # Create hover text with rich info
        map_data["hover_text"] = map_data.apply(
            lambda row: f"<b>{row['canonical_name']}</b><br>"
            + f"Type: {row['entity_type']}<br>"
            + f"Location: {row['city']}<br>"
            + f"Mentions: {row['total_mentions']}<br>"
            + f"Rating: {row['avg_rating']:.1f}/5"
            if row["avg_rating"]
            else "No rating",
            axis=1,
        )

        fig = px.scatter_map(
            map_data,
            lat="lat",
            lon="lon",
            size="size",
            color="color_value",
            color_continuous_scale="RdYlGn",
            range_color=[1, 5],
            hover_name="canonical_name",
            hover_data={
                "lat": False,
                "lon": False,
                "size": False,
                "color_value": False,
            },
            zoom=5,
            height=500,
        )
        fig.update_layout(
            mapbox_style="open-street-map", margin={"r": 0, "t": 0, "l": 0, "b": 0}
        )
        st.plotly_chart(fig, width="stretch")

st.markdown("---")

# Entity type distribution
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Entity Type Distribution")
    if not filtered_df.empty:
        type_counts = filtered_df["entity_type"].value_counts()
        fig = px.pie(
            values=type_counts.values, names=type_counts.index, title="Entities by Type"
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No data")

with col2:
    st.subheader("🌍 Top Cities")
    if not filtered_df.empty and "city" in filtered_df:
        city_counts = filtered_df["city"].value_counts().head(10)
        # Create DataFrame for plotly
        city_df = pd.DataFrame(
            {"City": city_counts.index, "Entity Count": city_counts.values}
        )
        fig = px.bar(
            city_df,
            x="Entity Count",
            y="City",
            orientation="h",
            labels={"Entity Count": "Entity Count", "City": "City"},
            title="Top 10 Cities by Entity Count",
            color="Entity Count",
            color_continuous_scale="Teal",
        )
        fig.update_layout(
            height=400, showlegend=False, yaxis={"categoryorder": "total ascending"}
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No data")

st.markdown("---")

# NEW v2.0 Enrichment Metrics
st.subheader("✨ Stage 3 Enrichment Insights (NEW v2.0)")

col1, col2, col3 = st.columns(3)

with col1:
    if "temporal_confidence" in filtered_df:
        temporal_count = filtered_df["temporal_confidence"].notna().sum()
        st.metric(
            "With Temporal Info",
            f"{temporal_count} ({temporal_count / len(filtered_df) * 100:.0f}%)",
        )
    else:
        st.metric("With Temporal Info", "0")

with col2:
    if "logistics_confidence" in filtered_df:
        logistics_count = filtered_df["logistics_confidence"].notna().sum()
        st.metric(
            "With Logistics Info",
            f"{logistics_count} ({logistics_count / len(filtered_df) * 100:.0f}%)",
        )
    else:
        st.metric("With Logistics Info", "0")

with col3:
    if "popularity_score" in filtered_df:
        avg_popularity = filtered_df["popularity_score"].mean()
        st.metric(
            "Avg Popularity", f"{avg_popularity:.2f}" if avg_popularity > 0 else "N/A"
        )
    else:
        st.metric("Avg Popularity", "N/A")

st.markdown("---")

# Detailed entities table
st.subheader("📋 Entity Details")

if not filtered_df.empty:
    # Select columns to display
    display_cols = [
        "canonical_name",
        "entity_type",
        "city",
        "total_mentions",
        "avg_rating",
        "popularity_score",
        "freshness_score",
        "best_seasons",
        "typical_duration",
        "transport_options",
    ]

    # Filter to only existing columns
    display_cols = [col for col in display_cols if col in filtered_df.columns]

    display_df = filtered_df[display_cols].copy()

    # Create Google Maps link for Entity Name when coordinates are available
    if 'lat' in filtered_df.columns and 'lon' in filtered_df.columns:
        def create_maps_link(idx):
            name = display_df.at[idx, 'canonical_name']
            lat = filtered_df.at[idx, 'lat'] if idx in filtered_df.index else None
            lon = filtered_df.at[idx, 'lon'] if idx in filtered_df.index else None
            if pd.notna(lat) and pd.notna(lon):
                return f"https://www.google.com/maps?q={lat},{lon}#{name}"
            return name

        display_df['canonical_name'] = [create_maps_link(idx) for idx in display_df.index]

    # Sort by total mentions descending
    display_df = display_df.sort_values("total_mentions", ascending=False)

    # Round numerical columns
    if "avg_rating" in display_df:
        display_df["avg_rating"] = display_df["avg_rating"].round(2)
    if "popularity_score" in display_df:
        display_df["popularity_score"] = display_df["popularity_score"].round(3)
    if "freshness_score" in display_df:
        display_df["freshness_score"] = display_df["freshness_score"].round(2)

    # Display dataframe
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "canonical_name": st.column_config.LinkColumn(
                "Entity Name",
                display_text=r"#(.*)$",
                width="large",
            ),
            "entity_type": st.column_config.TextColumn("Type", width="small"),
            "city": st.column_config.TextColumn("City", width="medium"),
            "total_mentions": st.column_config.NumberColumn("Mentions", width="small"),
            "avg_rating": st.column_config.NumberColumn(
                "Rating", width="small", format="%.2f"
            ),
            "popularity_score": st.column_config.NumberColumn(
                "Popularity", width="small", format="%.3f"
            ),
            "freshness_score": st.column_config.NumberColumn(
                "Freshness", width="small", format="%.2f"
            ),
            "best_seasons": st.column_config.TextColumn("Best Seasons", width="medium"),
            "typical_duration": st.column_config.TextColumn("Duration", width="small"),
            "transport_options": st.column_config.TextColumn(
                "Transport", width="medium"
            ),
        },
    )

    # Entity detail expander
    st.markdown("---")
    st.subheader("🔍 Entity Details (Click to Expand)")

    # Show detailed view for all filtered entities (sorted by mentions)
    sorted_entities = filtered_df.sort_values("total_mentions", ascending=False)

    for idx, row in sorted_entities.iterrows():
        entity_name = row["canonical_name"]
        entity_type = row["entity_type"]
        mentions = row["total_mentions"]
        rating = row.get("avg_rating", "N/A")
        rating_str = f"{rating:.1f}/5" if isinstance(rating, (int, float)) else rating

        expander_label = (
            f"📍 {entity_name} ({entity_type}) - {mentions} mentions - ⭐ {rating_str}"
        )

        with st.expander(expander_label, expanded=False):
            detail_col1, detail_col2, detail_col3 = st.columns(3)

            with detail_col1:
                st.markdown("**Core Info**")
                st.caption(f"**Entity ID:** {row.get('entity_id', 'N/A')}")
                st.caption(f"**Type:** {row.get('entity_type', 'N/A')}")
                st.caption(
                    f"**Location:** {row.get('city', 'N/A')}, {row.get('country', 'N/A')}"
                )
                st.caption(f"**Aliases:** {row.get('aliases', 'None')}")

            with detail_col2:
                st.markdown("**Consensus**")
                st.caption(f"**Mentions:** {row.get('total_mentions', 0)}")
                st.caption(f"**Avg Rating:** {rating_str}")
                st.caption(f"**Source Videos:** {row.get('source_video_count', 0)}")
                st.caption(f"**Themes:** {row.get('themes', 'None')}")
                st.caption(f"**Best For:** {row.get('best_for', 'None')}")

            with detail_col3:
                st.markdown("**Metrics**")
                st.caption(f"**Popularity:** {row.get('popularity_score', 'N/A')}")
                st.caption(f"**Freshness:** {row.get('freshness_score', 'N/A')}")
                st.caption(
                    f"**Days Since Last:** {row.get('days_since_last_mention', 'N/A')}"
                )

            # Sentiment distribution
            if all(
                col in row
                for col in [
                    "sentiment_positive",
                    "sentiment_neutral",
                    "sentiment_negative",
                ]
            ):
                st.markdown("**Sentiment Distribution**")
                sent_col1, sent_col2, sent_col3, sent_col4 = st.columns(4)
                with sent_col1:
                    st.metric("Positive", int(row.get("sentiment_positive", 0)))
                with sent_col2:
                    st.metric("Neutral", int(row.get("sentiment_neutral", 0)))
                with sent_col3:
                    st.metric("Negative", int(row.get("sentiment_negative", 0)))
                with sent_col4:
                    st.metric("Mixed", int(row.get("sentiment_mixed", 0)))

            # Temporal info (NEW v2.0)
            if (
                row.get("best_seasons")
                or row.get("best_times_of_day")
                or row.get("typical_duration")
            ):
                st.markdown("**⏰ Temporal Info (NEW v2.0)**")
                temp_col1, temp_col2, temp_col3 = st.columns(3)
                with temp_col1:
                    st.caption(f"**Best Seasons:** {row.get('best_seasons', 'N/A')}")
                with temp_col2:
                    st.caption(f"**Best Times:** {row.get('best_times_of_day', 'N/A')}")
                with temp_col3:
                    st.caption(f"**Duration:** {row.get('typical_duration', 'N/A')}")

            # Logistics info (NEW v2.0)
            if row.get("transport_options") or row.get("accessibility"):
                st.markdown("**🚗 Logistics Info (NEW v2.0)**")
                log_col1, log_col2 = st.columns(2)
                with log_col1:
                    st.caption(f"**Transport:** {row.get('transport_options', 'N/A')}")
                    st.caption(
                        f"**Booking Required:** {row.get('booking_required', 'N/A')}"
                    )
                with log_col2:
                    st.caption(f"**Accessibility:** {row.get('accessibility', 'N/A')}")

            # Coordinates
            if row.get("lat") and row.get("lon"):
                st.markdown("**📍 Geolocation**")
                geo_col1, geo_col2, geo_col3 = st.columns(3)
                with geo_col1:
                    st.caption(f"**Coordinates:** ({row['lat']:.4f}, {row['lon']:.4f})")
                with geo_col2:
                    st.caption(f"**Provider:** {row.get('coord_provider', 'N/A')}")
                with geo_col3:
                    st.caption(f"**Confidence:** {row.get('coord_confidence', 'N/A')}")

            # Raw JSON viewer
            st.markdown("---")
            with st.expander("📄 View Raw JSON from S3", expanded=False):
                if "raw_json" in row and row["raw_json"] is not None:
                    # Pretty print the JSON
                    json_str = json.dumps(row["raw_json"], indent=2, ensure_ascii=False)
                    st.code(json_str, language="json", line_numbers=True)

                    # Download button for this specific entity's JSON
                    st.download_button(
                        label="💾 Download JSON",
                        data=json_str,
                        file_name=f"{row.get('entity_id', 'entity')}.json",
                        mime="application/json",
                        width="stretch",
                    )
                else:
                    st.info("Raw JSON data not available")

    # Export options
    st.markdown("---")
    st.subheader("📥 Export")

    col1, col2 = st.columns(2)
    with col1:
        csv_data = display_df.to_csv(index=False)
        st.download_button(
            "Download as CSV",
            data=csv_data,
            file_name="stage3_canonical_entities.csv",
            mime="text/csv",
            width="stretch",
        )

    with col2:
        json_data = display_df.to_json(orient="records", indent=2)
        st.download_button(
            "Download as JSON",
            data=json_data,
            file_name="stage3_canonical_entities.json",
            mime="application/json",
            width="stretch",
        )
else:
    st.warning("No entities match your filters")

# Navigation
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    if st.button("← Back to Videos", width="stretch"):
        st.switch_page("pages/1_🎬_Videos.py")
with col2:
    if st.button("View Analytics →", width="stretch"):
        st.switch_page("pages/4_📈_Analytics.py")
