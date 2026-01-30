# TravelAI Dashboard

Interactive analytics platform to monitor video processing pipelines, explore entities and insights, and analyze geographic coverage across the TravelAI data ecosystem.

## Quick Start

```bash
# Launch from project root
./crawl.sh dashboard

# Or run from dashboard folder
cd dashboard && ./run_dashboard.sh

# Or manual launch
cd dashboard && streamlit run app.py
```

**Opens at**: http://localhost:8501

## Features

### 🏠 Home Page (Overview)
- **Metrics**: Total videos, canonical entities, travel insights, avg rating, pipeline success
- **Insights Overview**: Insights by category chart, recent insights cards
- **Charts**: Stage completion funnel, entity type distribution, top destinations, top rated entities
- **Pipeline Progress**: Stage 1/2/3 completion + Insights pipeline status
- **Recent Activity**: Last 10 processed videos

### 🎬 Videos Page
- Searchable/filterable table of all videos
- Filter by status, language, duration
- Stage 1/2/3 status indicators (✅/⏳/❌)
- Click video → Deep dive into details
- Export to CSV/JSON

### 📋 Video Detail Page
- **Video Info**: Title, channel, duration, language, status
- **5 Tabs**:
  - **Stage 1**: Transcript quality metrics, full transcript preview
  - **Stage 2**: Traveler profile + all extracted entities in table
  - **Stage 3**: Deduplication stats, canonical entity IDs, enrichment data
  - **Insights**: Travel insights extracted from this video, grouped by category
  - **Raw Data**: Download Stage 1/2/3 JSON files

### 📍 Entities Explorer
- All entities across all videos aggregated
- Filter by type, location, sentiment, search by name
- **Related Insights**: Insights for the filtered destination
- **Enrichment Insights**: Temporal/logistics info, source tracking, popularity/freshness scores
- **Charts**: Top entities, entity types, locations map, enrichment coverage
- **Copy Entity Names**: One-click copy to clipboard
- Export to CSV/JSON

### 📈 Analytics Page
- Processing statistics and success rates
- Videos processed over time
- Entity quality analysis
- **Insights Pipeline Analytics**: Insights by category, destination type, confidence scores, timeline
- **Cross-Pipeline Correlation**: Entities vs insights by destination, scatter plots
- Duration and language analysis

### 💡 Insights Explorer (NEW)
- Browse and search canonical travel insights
- **Summary Metrics**: Total insights, destinations, avg confidence, source videos, categories
- **Filters**: Category, destination type, country, city, min confidence, min mentions, search
- **Visualizations**: Treemap (category/destination), sunburst (hierarchy), top mentioned, top confidence
- **Insights Table**: Expandable rows with full details, tags, source videos
- Export to CSV/JSON

### 🕸️ Knowledge Graph (NEW)
- Interactive network visualization of relationships
- **Graph Types**: Full graph, entity-insight, video-entity, entity-entity
- **Controls**: Country/city filters, entity type, insight category, max nodes
- **Visualizations**: Interactive network graph with nodes (entities/insights/videos) and edges (relationships)
- **Statistics**: Total nodes/edges, most connected nodes, network density, clustering
- **Top Lists**: Most connected entities, insights, and videos

### 📊 Cross-Pipeline Analytics (NEW)
- Compare entity pipeline vs insights pipeline
- **Pipeline Comparison**: Side-by-side metrics, costs, coverage
- **Sankey Diagram**: Video processing flow through both pipelines
- **Quality Correlation**: Entity rating vs insight confidence scatter plots, heatmaps
- **Temporal Analysis**: Entities vs insights over time (dual-axis chart)
- **Content Richness**: Distribution and top content-rich videos
- **Geographic Coverage**: Entities vs insights by country, coverage gap analysis

### 🎯 Quality Monitor (NEW)
- Monitor data quality and identify issues
- **Quality Overview**: Data quality score, issues detected, entities/insights needing review
- **Entity Quality Issues**: Low confidence, missing geocoding, missing enrichment
- **Insight Quality Issues**: Low confidence, single-source, stale insights
- **Processing Issues**: Failed videos table, failure rate by stage
- **Improvement Opportunities**: Low entity count videos, single mentions, missing data
- **Data Freshness**: Age distribution, stale entities tracking

### 🗺️ Geographic Coverage (NEW)
- Geographic analysis across destinations
- **Global Coverage Map**: Bubble map (size=content, color=quality)
- **Coverage Heatmap**: Country × content type matrix (entity types + insight categories)
- **Top Destinations**: Top 20 countries and cities by content
- **Coverage Gap Analysis**: Imbalance detection (high entities/low insights, etc.)
- **Destination Deep Dive**: 4 tabs per destination (Entities, Insights, Videos, Quality)

### 📋 Metadata Viewer
- View and manage metadata tracker JSONL
- Search and filter by content ID, status
- Individual items and full JSON views
- Export raw data

## Requirements

- Python 3.12+
- Streamlit 1.30+
- Valid AWS credentials in `.env` (project root)
- S3 bucket with processed data

## Data Sources

The dashboard loads directly from S3:
- **Metadata**: `metadata/processing_status.jsonl` (video processing status)
- **Stage 1**: `raw/` - Raw video + transcript files
- **Stage 2**: `stage2-extracted/` - Extracted entities files (per video)
- **Stage 3**: `stage3-canonical/entities/` - Canonical entities (deduplicated, geocoded, enriched)
- **Insights Pipeline**: `insights-pipeline/canonical/` - Canonical travel insights
  - `insights_all_*.jsonl` - All insights
  - `by_category/*.jsonl` - Insights by category
  - `by_destination/*.jsonl` - Insights by destination

## Performance & Caching

Data is cached for fast loading:
- Metadata tracker: 10 minutes
- Video details (Stage 1/2/3): 10 minutes
- Canonical entities: 20 minutes
- Canonical insights: 20 minutes
- Geographic coverage: 20 minutes
- Entity aggregations: 20 minutes

Click **"🔄 Refresh Data"** in sidebar to clear cache and reload from S3.

**Performance Tips:**
- First load may take 10-30 seconds (caching data from S3)
- Subsequent page loads are instant (served from cache)
- Large datasets (>1000 entities) may take longer to visualize
- Knowledge graph limited to max 200 nodes for performance

## Troubleshooting

**No data showing?**
- Ensure pipeline (Stages 1-3) has processed videos
- Check S3 bucket has data
- Verify AWS credentials in `.env`

**Slow loading?**
- First load caches data (10-30 seconds)
- Subsequent loads are instant
- Check S3 region latency

**Failed to load data?**
- Check internet connection
- Verify S3 bucket name in config
- Ensure AWS credentials are valid

## Architecture

```
dashboard/
├── 🏠_Home.py                           # Home page (overview + insights)
├── pages/
│   ├── 1_🎬_Videos.py                 # Videos list
│   ├── 2_📋_Video_Detail.py           # Video deep dive (5 tabs)
│   ├── 3_📍_Entities.py               # Entity explorer + related insights
│   ├── 4_📈_Analytics.py              # Analytics + insights analytics
│   ├── 5_📋_Metadata_Viewer.py        # Metadata JSONL viewer
│   ├── 6_💡_Insights_Explorer.py     # Insights browsing (NEW)
│   ├── 7_🕸️_Knowledge_Graph.py       # Network graph visualization (NEW)
│   ├── 8_📊_Cross-Pipeline_Analytics.py # Entity/insights correlation (NEW)
│   ├── 9_🎯_Quality_Monitor.py        # Data quality monitoring (NEW)
│   └── 10_🗺️_Geographic_Coverage.py  # Geographic analysis (NEW)
├── utils/
│   ├── __init__.py
│   └── data_loader.py                 # S3 data loading + caching
│       ├── load_canonical_insights()         # Insights data
│       ├── get_entity_insight_relationships() # Relationship mapping
│       ├── get_geographic_coverage_stats()   # Coverage aggregation
│       ├── get_quality_issues()              # Quality issue detection
│       ├── get_processing_errors()           # Failed videos
│       ├── build_knowledge_graph_data()      # Network graph data
│       └── get_video_content_summary()       # Per-video aggregation
├── requirements.txt
└── README.md
```

## New Visualizations

The redesigned dashboard includes advanced visualizations:
- **Treemaps**: Hierarchical insights by category/destination
- **Sunburst Charts**: Category hierarchy visualization
- **Network Graphs**: Entity-insight-video relationships (using NetworkX + Plotly)
- **Sankey Diagrams**: Pipeline flow visualization
- **Heatmaps**: Correlation matrices, coverage analysis
- **Dual-Axis Charts**: Temporal comparison (entities vs insights over time)
- **Bubble Maps**: Global geographic coverage (using Plotly Geo)
- **Scatter Geo**: World map with country-level content coverage

## Export & Download

All pages support data export:
- **Videos**: Export as CSV or JSON
- **Entities**: Export filtered entities as CSV/JSON, copy entity names to clipboard
- **Insights**: Export filtered insights as CSV
- **Raw Data**: Download Stage 1/2/3 JSON files for any video
- **Metadata**: Download raw JSONL file

## Key Features (v2.0)

### Insights Pipeline Integration
- Browse 1000+ canonical travel insights (services, tips, logistics, cultural info)
- Search and filter by category, destination, confidence
- Visualize insights hierarchy with treemaps and sunburst charts
- Track insights sources and quality scores

### Cross-Pipeline Analytics
- Compare entity pipeline vs insights pipeline performance
- Analyze entity-insight correlations by destination
- Identify coverage gaps and imbalances
- Track content richness (entities + insights per video)

### Knowledge Graph
- Interactive network visualization of relationships
- Multiple graph types (full, entity-insight, video-entity, entity-entity)
- Network metrics (degree, density, clustering, connected components)
- Most connected nodes analysis

### Quality Monitoring
- Comprehensive quality score (geocoding + enrichment + confidence)
- Automated issue detection (low confidence, missing data, processing failures)
- Improvement opportunities identification
- Data freshness tracking

### Geographic Coverage
- Global coverage visualization with bubble maps
- Country × content type heatmaps
- Coverage gap analysis (high entities/low insights, etc.)
- Destination deep dive with 4-tab analysis

### Enhanced Entity Explorer
- Multi-signal entity ratings (transcript + sentiment + LLM knowledge)
- Temporal information (best seasons, times, duration)
- Logistics information (transport, booking, accessibility)
- Related insights for each destination
- Popularity and freshness scores

---

**Built with**: Streamlit + Plotly + Pandas + NetworkX
**Data**: Direct S3 integration via `S3Storage` and `MetadataTracker`
**Version**: v2.0 - Comprehensive analytics platform with insights pipeline integration
