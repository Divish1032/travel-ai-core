"""
Entities Explorer Page

Explore canonical entities from Stage 3 with deduplication, consensus, and enrichment.
"""

import streamlit as st
import streamlit.components.v1 as components
import sys
from pathlib import Path
import plotly.express as px
import pandas as pd
import json
import uuid

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_stage3_canonical_entities, load_canonical_insights

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
    if "total_mentions" in entities_df:
        total_mentions = pd.to_numeric(entities_df["total_mentions"], errors="coerce").sum()
    else:
        total_mentions = 0
    st.metric("Total Mentions", int(total_mentions))
with col4:
    geocoded = entities_df["lat"].notna().sum() if "lat" in entities_df else 0
    st.metric("Geocoded", f"{geocoded} ({geocoded / len(entities_df) * 100:.0f}%)")
with col5:
    # Prefer enhanced_rating (multi-signal) over avg_rating (sentiment-only)
    if "enhanced_rating" in entities_df.columns:
        avg_rating = pd.to_numeric(entities_df["enhanced_rating"], errors="coerce").mean()
        rating_label = "Rating ⭐"
    elif "avg_rating" in entities_df.columns:
        avg_rating = pd.to_numeric(entities_df["avg_rating"], errors="coerce").mean()
        rating_label = "Avg Rating"
    else:
        avg_rating = 0
        rating_label = "Avg Rating"
    st.metric(rating_label, f"{avg_rating:.1f}/5" if avg_rating > 0 else "N/A")

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
        # Convert total_mentions to numeric
        temp_df = filtered_df.copy()
        temp_df["total_mentions"] = pd.to_numeric(temp_df["total_mentions"], errors="coerce")
        temp_df = temp_df.dropna(subset=["total_mentions"])

        # Prefer enhanced_rating for coloring
        rating_col = 'enhanced_rating' if 'enhanced_rating' in temp_df.columns else 'avg_rating'

        if not temp_df.empty:
            cols_to_select = ["canonical_name", "total_mentions"]
            if rating_col in temp_df.columns:
                cols_to_select.append(rating_col)
            top_entities = temp_df.nlargest(15, "total_mentions")[cols_to_select]
        else:
            st.info("No valid mention data available")
            top_entities = None

        if top_entities is not None:
            fig = px.bar(
                top_entities,
                x="total_mentions",
                y="canonical_name",
                orientation="h",
                color=rating_col if rating_col in top_entities.columns else None,
                color_continuous_scale="RdYlGn",
                range_color=[1, 5],
                labels={
                    "total_mentions": "Mentions",
                    "canonical_name": "Entity",
                    rating_col: "Rating",
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
    # Prefer enhanced_rating (multi-signal) over avg_rating (sentiment-only)
    rating_col = 'enhanced_rating' if 'enhanced_rating' in filtered_df.columns else 'avg_rating'

    if not filtered_df.empty and rating_col in filtered_df.columns:
        # Filter entities with at least 2 mentions for reliable ratings
        rated = filtered_df[filtered_df["total_mentions"] >= 2].copy()
        if not rated.empty:
            # Convert rating to numeric (handle non-numeric values)
            rated[rating_col] = pd.to_numeric(rated[rating_col], errors="coerce")
            # Drop rows with NaN ratings
            rated = rated.dropna(subset=[rating_col])

            if not rated.empty:
                top_rated = rated.nlargest(15, rating_col)[
                    ["canonical_name", rating_col, "total_mentions"]
                ]
                rating_type = "Multi-Signal" if rating_col == 'enhanced_rating' else "Sentiment"
                fig = px.bar(
                    top_rated,
                    x=rating_col,
                    y="canonical_name",
                    orientation="h",
                    color="total_mentions",
                    color_continuous_scale="Blues",
                    labels={
                        rating_col: "Rating",
                        "canonical_name": "Entity",
                        "total_mentions": "Mentions",
                    },
                    title=f"Top Rated Entities ({rating_type} Rating, min 2 mentions)",
                )
                fig.update_layout(
                    height=500, showlegend=False, yaxis={"categoryorder": "total ascending"}
                )
                fig.update_xaxes(range=[0, 5])
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No valid ratings available")
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

        # Prefer enhanced_rating for map coloring
        map_rating_col = 'enhanced_rating' if 'enhanced_rating' in map_data.columns else 'avg_rating'
        map_data["color_value"] = map_data[map_rating_col].fillna(3) if map_rating_col in map_data.columns else 3

        # Create hover text with rich info
        map_data["hover_text"] = map_data.apply(
            lambda row: f"<b>{row['canonical_name']}</b><br>"
            + f"Type: {row['entity_type']}<br>"
            + f"Location: {row['city']}<br>"
            + f"Mentions: {row['total_mentions']}<br>"
            + f"Rating: {row.get(map_rating_col, 0):.1f}/5"
            if row.get(map_rating_col)
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

# NEW v2.0 Enrichment Metrics with Source Breakdown
st.subheader("✨ Stage 3 Enrichment Insights (Hybrid: Transcript + LLM)")

col1, col2, col3, col4 = st.columns(4)

with col1:
    # Count entities with temporal info (confidence > 0)
    if "temporal_confidence" in filtered_df:
        temporal_count = (filtered_df["temporal_confidence"] > 0).sum()
        pct = temporal_count / len(filtered_df) * 100 if len(filtered_df) > 0 else 0
        st.metric("With Temporal Info", f"{temporal_count} ({pct:.0f}%)")
    else:
        st.metric("With Temporal Info", "0")

with col2:
    # Count entities with logistics info (confidence > 0)
    if "logistics_confidence" in filtered_df:
        logistics_count = (filtered_df["logistics_confidence"] > 0).sum()
        pct = logistics_count / len(filtered_df) * 100 if len(filtered_df) > 0 else 0
        st.metric("With Logistics Info", f"{logistics_count} ({pct:.0f}%)")
    else:
        st.metric("With Logistics Info", "0")

with col3:
    # Count entities with practical tips (LLM enriched)
    if "has_practical_tips" in filtered_df:
        tips_count = filtered_df["has_practical_tips"].sum()
        pct = tips_count / len(filtered_df) * 100 if len(filtered_df) > 0 else 0
        st.metric("With Practical Tips", f"{tips_count} ({pct:.0f}%)")
    else:
        st.metric("With Practical Tips", "0")

with col4:
    if "popularity_score" in filtered_df:
        avg_popularity = pd.to_numeric(filtered_df["popularity_score"], errors="coerce").mean()
        st.metric("Avg Popularity", f"{avg_popularity:.2f}" if avg_popularity > 0 else "N/A")
    else:
        st.metric("Avg Popularity", "N/A")

# Source breakdown for enrichment
if "temporal_source" in filtered_df or "logistics_source" in filtered_df:
    st.markdown("##### 📊 Enrichment Source Breakdown")
    source_col1, source_col2 = st.columns(2)

    with source_col1:
        if "temporal_source" in filtered_df:
            st.markdown("**Temporal Info Sources:**")
            source_counts = filtered_df["temporal_source"].value_counts()
            for source, count in source_counts.items():
                icon = "📝" if source == "transcript_extracted" else "🧠" if source == "llm_inferred" else "🔀" if source == "hybrid" else "❌"
                st.caption(f"{icon} {source}: {count}")

    with source_col2:
        if "logistics_source" in filtered_df:
            st.markdown("**Logistics Info Sources:**")
            source_counts = filtered_df["logistics_source"].value_counts()
            for source, count in source_counts.items():
                icon = "📝" if source == "transcript_extracted" else "🧠" if source == "llm_inferred" else "🔀" if source == "hybrid" else "❌"
                st.caption(f"{icon} {source}: {count}")

st.markdown("---")

# Related Insights Section (NEW)
st.subheader("💡 Related Travel Insights")
st.markdown("Insights for the filtered destination (services, tips, logistics, cultural info)")

# Load insights data
insights_df = load_canonical_insights()

if not insights_df.empty and not filtered_df.empty:
    # Get unique locations from filtered entities
    filtered_countries = filtered_df['country'].dropna().unique()
    filtered_cities = filtered_df['city'].dropna().unique()

    # Filter insights by matching locations
    related_insights = insights_df[
        (insights_df['country'].isin(filtered_countries)) |
        (insights_df['city'].isin(filtered_cities))
    ]

    if not related_insights.empty:
        # Get top 5 insights by confidence
        top_insights = related_insights.nlargest(5, 'confidence_score')

        with st.expander(f"**🌍 Insights for this Destination** ({len(related_insights)} total, showing top 5)", expanded=False):
            for idx, insight in top_insights.iterrows():
                col1, col2 = st.columns([3, 1])

                with col1:
                    category = insight.get('category', 'unknown')
                    title = insight.get('title', '')
                    content = insight.get('content', '')

                    st.markdown(f"**{category.upper()}**: {title if title else content[:100]}")
                    if title and content:
                        st.write(content)

                    # Show scope
                    scope_items = []
                    if insight.get('country'):
                        scope_items.append(f"🌍 {insight['country']}")
                    if insight.get('city'):
                        scope_items.append(f"🏙️ {insight['city']}")

                    if scope_items:
                        st.caption(" | ".join(scope_items))

                with col2:
                    confidence = insight.get('confidence_score', 0)
                    mentions = insight.get('mention_count', 0)
                    st.metric("Confidence", f"{confidence:.2f}")
                    st.metric("Mentions", mentions)

                st.markdown("---")
    else:
        st.info("No insights found for the selected destination. The insights pipeline may need to be run for this region.")
elif insights_df.empty:
    st.info("No insights data available yet. Run the insights pipeline to see travel tips and information.")
else:
    st.info("Select entities above to see related insights")

st.markdown("---")

# Detailed entities table
st.subheader("📋 Entity Details")

if not filtered_df.empty:
    # Add button to copy all entity names as a list to clipboard
    col_copy, col_spacer = st.columns([1, 3])
    with col_copy:
        entity_names = filtered_df['canonical_name'].tolist()
        entity_names_str = json.dumps(entity_names, indent=2, ensure_ascii=False)

        # Create a unique ID for this button
        button_id = f"copy_btn_{uuid.uuid4().hex[:8]}"

        # JavaScript to copy to clipboard
        copy_script = f"""
            <script>
            function copyToClipboard_{button_id}() {{
                const text = {json.dumps(entity_names_str)};
                navigator.clipboard.writeText(text).then(function() {{
                    const btn = document.getElementById('{button_id}');
                    const originalText = btn.innerHTML;
                    btn.innerHTML = '✅ Copied!';
                    btn.style.backgroundColor = '#4CAF50';
                    setTimeout(function() {{
                        btn.innerHTML = originalText;
                        btn.style.backgroundColor = '#FF4B4B';
                    }}, 2000);
                }}, function(err) {{
                    alert('Failed to copy to clipboard');
                }});
            }}
            </script>
            <button id="{button_id}"
                    onclick="copyToClipboard_{button_id}()"
                    style="
                        background-color: #FF4B4B;
                        color: white;
                        padding: 0.4rem 0.2rem;
                        border: none;
                        border-radius: 0.5rem;
                        cursor: pointer;
                        font-size: 13px;
                        width: 60%;
                        font-family: 'Source Sans Pro', sans-serif;
                    ">
                📋 Copy Entity Names
            </button>
        """

        components.html(copy_script, height=60)

    # Determine which rating column to use (prefer enhanced_rating)
    table_rating_col = 'enhanced_rating' if 'enhanced_rating' in filtered_df.columns else 'avg_rating'

    # Select columns to display
    display_cols = [
        "canonical_name",
        "entity_type",
        "city",
        "total_mentions",
        table_rating_col,  # Use the preferred rating column
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
    if table_rating_col in display_df.columns:
        display_df[table_rating_col] = display_df[table_rating_col].round(2)
    if "popularity_score" in display_df:
        display_df["popularity_score"] = display_df["popularity_score"].round(3)
    if "freshness_score" in display_df:
        display_df["freshness_score"] = display_df["freshness_score"].round(2)

    # Build column config dynamically based on rating column
    column_config = {
        "canonical_name": st.column_config.LinkColumn(
            "Entity Name",
            display_text=r"#(.*)$",
            width="large",
        ),
        "entity_type": st.column_config.TextColumn("Type", width="small"),
        "city": st.column_config.TextColumn("City", width="medium"),
        "total_mentions": st.column_config.NumberColumn("Mentions", width="small"),
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
    }

    # Add rating column config (handles both enhanced_rating and avg_rating)
    rating_label = "Rating ⭐" if table_rating_col == 'enhanced_rating' else "Rating"
    column_config[table_rating_col] = st.column_config.NumberColumn(
        rating_label, width="small", format="%.2f"
    )

    # Display dataframe
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config=column_config,
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

        # Prefer enhanced_rating over avg_rating
        rating = row.get("enhanced_rating") if row.get("enhanced_rating") else row.get("avg_rating", "N/A")
        rating_str = f"{rating:.1f}/5" if isinstance(rating, (int, float)) else rating
        rating_icon = "⭐" if row.get("enhanced_rating") else "📊"  # Different icon for multi-signal vs sentiment-only

        expander_label = (
            f"📍 {entity_name} ({entity_type}) - {mentions} mentions - {rating_icon} {rating_str}"
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
                # Show rating with confidence if enhanced rating is available
                if row.get('enhanced_rating'):
                    confidence = row.get('enhanced_rating_confidence', 0)
                    signals = row.get('enhanced_rating_signals', 0)
                    st.caption(f"**Rating:** {rating_str} (confidence: {confidence:.0%}, {signals} signals)")
                else:
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

            # Temporal info (with source tracking)
            if (
                row.get("best_seasons")
                or row.get("best_times_of_day")
                or row.get("typical_duration")
            ):
                source_icon = "📝" if row.get('temporal_source') == 'transcript_extracted' else "🧠" if row.get('temporal_source') == 'llm_inferred' else "🔀" if row.get('temporal_source') == 'hybrid' else ""
                st.markdown(f"**⏰ Temporal Info** {source_icon}")
                temp_col1, temp_col2, temp_col3 = st.columns(3)
                with temp_col1:
                    st.caption(f"**Best Seasons:** {row.get('best_seasons', 'N/A')}")
                with temp_col2:
                    st.caption(f"**Best Times:** {row.get('best_times_of_day', 'N/A')}")
                with temp_col3:
                    st.caption(f"**Duration:** {row.get('typical_duration', 'N/A')}")
                if row.get('temporal_source'):
                    st.caption(f"_Source: {row.get('temporal_source')} | Confidence: {row.get('temporal_confidence', 0):.2f}_")

            # Logistics info (with source tracking)
            if row.get("transport_options") or row.get("accessibility"):
                source_icon = "📝" if row.get('logistics_source') == 'transcript_extracted' else "🧠" if row.get('logistics_source') == 'llm_inferred' else "🔀" if row.get('logistics_source') == 'hybrid' else ""
                st.markdown(f"**🚗 Logistics Info** {source_icon}")
                log_col1, log_col2 = st.columns(2)
                with log_col1:
                    st.caption(f"**Transport:** {row.get('transport_options', 'N/A')}")
                    st.caption(f"**Booking Required:** {row.get('booking_required', 'N/A')}")
                with log_col2:
                    st.caption(f"**Accessibility:** {row.get('accessibility', 'N/A')}")
                if row.get('logistics_source'):
                    st.caption(f"_Source: {row.get('logistics_source')} | Confidence: {row.get('logistics_confidence', 0):.2f}_")

            # Practical tips (LLM enrichment)
            if row.get("has_practical_tips"):
                st.markdown("**💡 Practical Tips** 🧠")
                tips_col1, tips_col2, tips_col3 = st.columns(3)
                with tips_col1:
                    if row.get('dress_code'):
                        st.caption(f"**Dress Code:** {row.get('dress_code')}")
                with tips_col2:
                    if row.get('entrance_fee'):
                        st.caption(f"**Entrance Fee:** {row.get('entrance_fee')}")
                with tips_col3:
                    if row.get('opening_hours'):
                        st.caption(f"**Hours:** {row.get('opening_hours')}")

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

                    random_id = uuid.uuid4().hex[:8]
                    
                    # Download button for this specific entity's JSON
                    st.download_button(
                        label="💾 Download JSON",
                        data=json_str,
                        file_name=f"{row.get('entity_id', 'entity')}.json",
                        mime="application/json",
                        width="stretch",
                        key=f"download_json_{row.get('entity_id', idx)}_{random_id}",
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
