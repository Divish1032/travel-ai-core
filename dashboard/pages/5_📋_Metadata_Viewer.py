"""
Metadata Tracker Viewer Page

View and explore the metadata tracker JSONL file with a proper JSON viewer.
"""

import streamlit as st
import sys
from pathlib import Path
import json

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    load_metadata_tracker_jsonl,
    download_metadata_tracker_file,
)

st.set_page_config(page_title="Metadata Viewer", page_icon="📋", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    # st.divider()
    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("📋 Metadata Tracker Viewer")

# Auto-load metadata on page open
with st.spinner("Loading metadata tracker from S3..."):
    try:
        metadata_list = load_metadata_tracker_jsonl()
        metadata_loading_error = None
    except Exception as e:
        metadata_list = None
        metadata_loading_error = str(e)

# Action buttons section
st.markdown("---")
btn_col2, btn_col1 = st.columns(2, width=340)

with btn_col1:
    # Download button
    try:
        file_content = download_metadata_tracker_file()
        st.download_button(
            label="💾 Download JSONL",
            data=file_content,
            file_name="processing_status.jsonl",
            mime="application/x-ndjson",
            help="Download the metadata tracker file from S3",
            key="download_metadata_tracker",
            width="content",
        )
    except Exception:
        st.download_button(
            label="💾 Download JSONL",
            data=b"",
            file_name="processing_status.jsonl",
            mime="application/x-ndjson",
            disabled=True,
            help="File not available",
            width="content",
        )

with btn_col2:
    # Reload button
    if st.button("🔄 Reload from S3", width="content", help="Reload data from S3"):
        st.cache_data.clear()
        st.rerun()

# st.markdown("---")

# Display metadata if loaded
if metadata_list:

    # Summary stats
    st.subheader("📊 Summary Statistics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Items", len(metadata_list))

    with col2:
        completed = sum(
            1
            for item in metadata_list
            if item.get("pipeline_status", "").endswith("complete")
            or item.get("pipeline_status", "") == "complete"
        )
        st.metric("Completed", completed)

    with col3:
        failed = sum(
            1 for item in metadata_list if item.get("total_error_count", 0) > 0
        )
        st.metric("With Errors", failed)

    with col4:
        pending = sum(
            1
            for item in metadata_list
            if "pending" in item.get("pipeline_status", "").lower()
        )
        st.metric("Pending", pending)

    st.markdown("---")

    # Search and filter
    st.subheader("🔍 Search & Filter")
    search_col1, search_col2, search_col3 = st.columns([2, 1, 1])

    with search_col1:
        search_query = st.text_input(
            "Search by content_id, title, or source",
            key="metadata_search",
            placeholder="Enter search term...",
            label_visibility="collapsed",
        )

    with search_col2:
        view_mode = st.selectbox(
            "View Mode",
            ["Individual Items", "Full JSON"],
            key="metadata_view_mode",
            label_visibility="collapsed",
        )

    with search_col3:
        # Status filter
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "Completed", "Pending", "Failed"],
            key="status_filter",
            label_visibility="collapsed",
        )

    # Filter data based on search and status
    filtered_metadata = metadata_list

    # Apply search filter
    if search_query:
        search_lower = search_query.lower()
        filtered_metadata = [
            item
            for item in filtered_metadata
            if (
                search_lower in item.get("content_id", "").lower()
                or search_lower in item.get("title", "").lower()
                or search_lower in item.get("source", "").lower()
            )
        ]

    # Apply status filter
    if status_filter != "All":
        if status_filter == "Completed":
            filtered_metadata = [
                item
                for item in filtered_metadata
                if item.get("pipeline_status", "").endswith("complete")
                or item.get("pipeline_status", "") == "complete"
            ]
        elif status_filter == "Pending":
            filtered_metadata = [
                item
                for item in filtered_metadata
                if "pending" in item.get("pipeline_status", "").lower()
            ]
        elif status_filter == "Failed":
            filtered_metadata = [
                item
                for item in filtered_metadata
                if item.get("total_error_count", 0) > 0
            ]

    if search_query or status_filter != "All":
        st.info(f"Showing {len(filtered_metadata)} of {len(metadata_list)} items")

    st.markdown("---")

    # Display based on view mode
    if view_mode == "Individual Items":
        st.subheader("📄 Individual Items")

        if not filtered_metadata:
            st.warning("No items match your filters.")
        else:
            # Display items with expanders
            for idx, item in enumerate(filtered_metadata):
                content_id = item.get("content_id", f"Item {idx + 1}")
                title = item.get("title", "No title")
                pipeline_status = item.get("pipeline_status", "unknown")
                source = item.get("source", "unknown")

                # Create expander with more info
                expander_label = f"📄 {content_id} | {title[:40]}... | Status: {pipeline_status} | Source: {source}"

                with st.expander(expander_label, expanded=False):
                    # Quick info columns
                    info_col1, info_col2, info_col3 = st.columns(3)

                    with info_col1:
                        st.caption(f"**Content ID:** {content_id}")
                        st.caption(f"**Source:** {source}")
                        st.caption(f"**Pipeline Status:** {pipeline_status}")

                    with info_col2:
                        stages = item.get("stages", {})
                        st.caption(
                            f"**Stage 1:** {stages.get('stage_1_crawl', {}).get('status', 'N/A')}"
                        )
                        st.caption(
                            f"**Stage 2:** {stages.get('stage_2_extract', {}).get('status', 'N/A')}"
                        )
                        st.caption(
                            f"**Stage 3:** {stages.get('stage_3_deduplicate', {}).get('status', 'N/A')}"
                        )

                    with info_col3:
                        added_at = item.get("added_at", "N/A")
                        last_updated = item.get("last_updated", "N/A")
                        error_count = item.get("total_error_count", 0)
                        st.caption(
                            f"**Added:** {added_at[:10] if len(added_at) > 10 else added_at}"
                        )
                        st.caption(
                            f"**Updated:** {last_updated[:10] if len(last_updated) > 10 else last_updated}"
                        )
                        st.caption(f"**Errors:** {error_count}")

                    st.markdown("---")

                    # Full JSON viewer
                    st.markdown("**Full JSON:**")
                    st.json(item, expanded=1)
    else:
        # Full JSON view
        st.subheader("📄 Full Metadata JSON")

        if not filtered_metadata:
            st.warning("No items match your filters.")
        else:
            # Display full JSON with expandable tree
            st.json(filtered_metadata, expanded=1)

            st.markdown("---")

            # Download filtered JSON
            json_str = json.dumps(filtered_metadata, indent=2, ensure_ascii=False)
            st.download_button(
                label="⬇️ Download Filtered JSON",
                data=json_str,
                file_name="metadata_tracker_filtered.json",
                mime="application/json",
                key="download_filtered_json",
                width="stretch",
            )

elif metadata_loading_error:
    st.error(f"Error loading metadata: {metadata_loading_error}")
    st.info(
        "Please check your S3 connection and ensure the metadata tracker file exists."
    )

# Navigation
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    if st.button("← Back to Home", width="stretch"):
        st.switch_page("🏠_Home.py")
with col2:
    if st.button("View Videos →", width="stretch"):
        st.switch_page("pages/1_🎬_Videos.py")
