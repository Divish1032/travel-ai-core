"""
Knowledge Graph Page

Visualize relationships between entities, insights, and videos using network graphs.
"""

import streamlit as st
import sys
from pathlib import Path
import plotly.graph_objects as go
import pandas as pd
import networkx as nx

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import (
    build_knowledge_graph_data,
    load_stage3_canonical_entities,
    load_canonical_insights
)

st.set_page_config(page_title="Knowledge Graph", page_icon="🕸️", layout="wide")

# Sidebar
with st.sidebar:
    if st.button("🔄 Refresh Data", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.caption("v1.0.0 | © 2026 TravelAI")

st.title("🕸️ Knowledge Graph")
st.markdown("Visualize relationships between entities, insights, and videos")

# Load data for filters
entities_df = load_stage3_canonical_entities()
insights_df = load_canonical_insights()

if entities_df.empty and insights_df.empty:
    st.warning("No data available for knowledge graph")
    st.info("💡 Process videos through the entity and insights pipelines to build the knowledge graph")
    st.stop()

# Graph Controls
st.subheader("🎛️ Graph Controls")

col1, col2, col3 = st.columns(3)

with col1:
    # Graph type selector
    graph_type = st.selectbox(
        "Graph Type",
        ['full', 'entity-insight', 'video-entity', 'entity-entity'],
        format_func=lambda x: {
            'full': 'Full Graph (All Relationships)',
            'entity-insight': 'Entity-Insight Relationships',
            'video-entity': 'Video-Entity Relationships',
            'entity-entity': 'Entity-Entity Network'
        }[x],
        help="Select the type of relationships to visualize"
    )

    # Max nodes slider
    max_nodes = st.slider(
        "Max Nodes",
        min_value=10,
        max_value=200,
        value=50,
        step=10,
        help="Maximum number of nodes to display (for performance)"
    )

with col2:
    # Destination filters - Country filter COMMENTED OUT (focusing on Thailand cities only)
    # countries = ['All']
    # if not entities_df.empty and 'country' in entities_df.columns:
    #     countries += sorted(entities_df['country'].dropna().unique().tolist())
    # selected_country = st.selectbox("Country Filter", countries)
    selected_country = 'All'  # Default since focusing on Thailand

    # City filter (Thailand cities)
    cities = ['All']
    if not entities_df.empty and 'city' in entities_df.columns:
        city_list = entities_df['city'].dropna().unique().tolist()
        cities += sorted(city_list)

    selected_city = st.selectbox("City Filter", cities)

with col3:
    # Entity type filter
    entity_types = ['All']
    if not entities_df.empty and 'entity_type' in entities_df.columns:
        entity_types += sorted(entities_df['entity_type'].dropna().unique().tolist())

    selected_entity_type = st.selectbox("Entity Type", entity_types)

    # Insight category filter
    insight_categories = ['All']
    if not insights_df.empty and 'category' in insights_df.columns:
        insight_categories += sorted(insights_df['category'].dropna().unique().tolist())

    selected_insight_category = st.selectbox("Insight Category", insight_categories)

# Build filters dict
filters = {
    'graph_type': graph_type,
    'max_nodes': max_nodes
}

if selected_country != 'All':
    filters['country'] = selected_country

if selected_city != 'All':
    filters['city'] = selected_city

if selected_entity_type != 'All':
    filters['entity_type'] = selected_entity_type

if selected_insight_category != 'All':
    filters['insight_category'] = selected_insight_category

st.markdown("---")

# Build graph data
with st.spinner("Building knowledge graph..."):
    graph_data = build_knowledge_graph_data(filters)

nodes = graph_data.get('nodes', [])
edges = graph_data.get('edges', [])

if not nodes:
    st.warning("No nodes found with the selected filters")
    st.info("Try adjusting the filters or increasing the max nodes limit")
    st.stop()

# Graph Statistics
st.subheader("📊 Graph Statistics")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Nodes", len(nodes))

with col2:
    st.metric("Total Edges", len(edges))

with col3:
    # Node type breakdown
    node_types = {}
    for node in nodes:
        ntype = node.get('type', 'unknown')
        node_types[ntype] = node_types.get(ntype, 0) + 1

    type_str = " | ".join([f"{k}: {v}" for k, v in node_types.items()])
    st.metric("Node Types", len(node_types), help=type_str)

with col4:
    # Calculate average degree
    if nodes and edges:
        # Count connections per node
        node_connections = {node['id']: 0 for node in nodes}
        for edge in edges:
            node_connections[edge['source']] = node_connections.get(edge['source'], 0) + 1
            node_connections[edge['target']] = node_connections.get(edge['target'], 0) + 1

        avg_degree = sum(node_connections.values()) / len(node_connections)
        st.metric("Avg Degree", f"{avg_degree:.1f}", help="Average connections per node")

st.markdown("---")

# Network Visualization
st.subheader("🔷 Interactive Network Graph")

# Create NetworkX graph for layout
G = nx.Graph()

# Add nodes
for node in nodes:
    G.add_node(node['id'], **node['metadata'])

# Add edges
for edge in edges:
    G.add_edge(edge['source'], edge['target'], weight=edge.get('weight', 1))

# Calculate layout (use spring layout for good distribution)
try:
    # Use spring layout for better visualization
    pos = nx.spring_layout(G, k=0.5, iterations=50, seed=42)
except:
    # Fallback to random layout if spring fails
    pos = nx.random_layout(G, seed=42)

# Create Plotly figure
edge_trace_list = []

# Create edges
for edge in edges:
    x0, y0 = pos[edge['source']]
    x1, y1 = pos[edge['target']]

    edge_trace = go.Scatter(
        x=[x0, x1, None],
        y=[y0, y1, None],
        mode='lines',
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        showlegend=False
    )
    edge_trace_list.append(edge_trace)

# Create nodes by type
node_trace_by_type = {}

for node in nodes:
    ntype = node.get('type', 'unknown')
    x, y = pos[node['id']]

    if ntype not in node_trace_by_type:
        node_trace_by_type[ntype] = {
            'x': [],
            'y': [],
            'text': [],
            'size': [],
            'color': [],
            'ids': []
        }

    node_trace_by_type[ntype]['x'].append(x)
    node_trace_by_type[ntype]['y'].append(y)
    node_trace_by_type[ntype]['text'].append(node.get('label', node['id']))
    node_trace_by_type[ntype]['size'].append(min(node.get('size', 5) * 2, 30))  # Scale size
    node_trace_by_type[ntype]['color'].append(node.get('color', '#888'))
    node_trace_by_type[ntype]['ids'].append(node['id'])

# Create figure
fig = go.Figure()

# Add edges
for edge_trace in edge_trace_list[:500]:  # Limit edges for performance
    fig.add_trace(edge_trace)

# Add nodes by type
for ntype, trace_data in node_trace_by_type.items():
    node_trace = go.Scatter(
        x=trace_data['x'],
        y=trace_data['y'],
        mode='markers+text',
        text=trace_data['text'],
        textposition='top center',
        textfont=dict(size=8),
        marker=dict(
            size=trace_data['size'],
            color=trace_data['color'],
            line=dict(width=1, color='white')
        ),
        hovertext=[f"{ntype}: {text}" for text in trace_data['text']],
        hoverinfo='text',
        name=f"{ntype.title()}s",
        showlegend=True
    )
    fig.add_trace(node_trace)

# Update layout
fig.update_layout(
    title=f"Knowledge Graph ({graph_type})",
    title_font_size=16,
    showlegend=True,
    hovermode='closest',
    margin=dict(b=0, l=0, r=0, t=40),
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    height=600,
    plot_bgcolor='white'
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Most Connected Nodes
st.subheader("🔝 Most Connected Nodes")

# Calculate node degrees
node_degrees = {}
for node in nodes:
    node_id = node['id']
    degree = 0
    for edge in edges:
        if edge['source'] == node_id or edge['target'] == node_id:
            degree += 1
    node_degrees[node_id] = {
        'degree': degree,
        'label': node.get('label', node_id),
        'type': node.get('type', 'unknown')
    }

# Sort by degree
sorted_nodes = sorted(node_degrees.items(), key=lambda x: x[1]['degree'], reverse=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("##### Top Entities")
    entity_nodes = [(nid, data) for nid, data in sorted_nodes if data['type'] == 'entity'][:10]

    if entity_nodes:
        entity_df = pd.DataFrame([
            {'Name': data['label'], 'Connections': data['degree']}
            for nid, data in entity_nodes
        ])
        st.dataframe(entity_df, hide_index=True, use_container_width=True)
    else:
        st.info("No entity nodes in graph")

with col2:
    st.markdown("##### Top Insights")
    insight_nodes = [(nid, data) for nid, data in sorted_nodes if data['type'] == 'insight'][:10]

    if insight_nodes:
        insight_df = pd.DataFrame([
            {'Title': data['label'][:40], 'Connections': data['degree']}
            for nid, data in insight_nodes
        ])
        st.dataframe(insight_df, hide_index=True, use_container_width=True)
    else:
        st.info("No insight nodes in graph")

with col3:
    st.markdown("##### Top Videos")
    video_nodes = [(nid, data) for nid, data in sorted_nodes if data['type'] == 'video'][:10]

    if video_nodes:
        video_df = pd.DataFrame([
            {'Video': data['label'], 'Connections': data['degree']}
            for nid, data in video_nodes
        ])
        st.dataframe(video_df, hide_index=True, use_container_width=True)
    else:
        st.info("No video nodes in graph")

st.markdown("---")

# Graph Metrics
st.subheader("📐 Network Metrics")

col1, col2, col3 = st.columns(3)

with col1:
    # Network density
    if len(nodes) > 1:
        max_edges = len(nodes) * (len(nodes) - 1) / 2
        density = len(edges) / max_edges if max_edges > 0 else 0
        st.metric("Network Density", f"{density:.3f}", help="Ratio of actual edges to possible edges")
    else:
        st.metric("Network Density", "N/A")

with col2:
    # Average clustering coefficient (if graph is connected)
    try:
        if nx.is_connected(G):
            avg_clustering = nx.average_clustering(G)
            st.metric("Avg Clustering", f"{avg_clustering:.3f}", help="How tightly nodes cluster together")
        else:
            st.metric("Avg Clustering", "Disconnected")
    except:
        st.metric("Avg Clustering", "N/A")

with col3:
    # Number of connected components
    n_components = nx.number_connected_components(G)
    st.metric("Connected Components", n_components, help="Number of separate sub-graphs")

# Navigation
st.markdown("---")
if st.button("← Back to Home", use_container_width=True):
    st.switch_page("🏠_Home.py")
