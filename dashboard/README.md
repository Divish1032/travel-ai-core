# TravelAI Dashboard

Interactive dashboard to monitor video processing pipeline and explore extracted entities from S3 data.

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

### Home Page (Overview)
- **Metrics**: Total videos, entities, unique entities, success rate
- **Charts**: Stage completion funnel, entity type distribution, language breakdown
- **Recent Activity**: Last 10 processed videos

### Videos Page (🎬)
- Searchable/filterable table of all videos
- Filter by status, language, duration
- Stage 1/2/3 status indicators (✅/⏳/❌)
- Click video → Deep dive into details
- Export to CSV/JSON

### Video Detail Page (📋)
- **Video Info**: Title, channel, duration, language, status
- **Stage 1**: Transcript quality metrics, full transcript preview
- **Stage 2**: Traveler profile + **all extracted entities in table**
- **Stage 3**: Deduplication stats, canonical entity IDs
- **Raw Data**: Download Stage 1/2/3 JSON files

### Entities Explorer (📍)
- All entities across all videos aggregated
- Filter by type, location, sentiment
- Search by entity name
- **Charts**: Top 20 entities, sentiment distribution, locations
- **Table**: Entity aggregations with mention counts, quality scores
- Export to CSV/JSON

### Analytics Page (📈)
- Processing statistics and success rates
- Videos processed over time
- Quality score distributions
- Duration analysis
- Data quality insights

## Requirements

- Python 3.12+
- Streamlit 1.30+
- Valid AWS credentials in `.env` (project root)
- S3 bucket with processed data

## Data Sources

The dashboard loads directly from S3:
- **Metadata**: `metadata/processing_status.jsonl`
- **Stage 1**: Raw video + transcript files
- **Stage 2**: Extracted entities files (per video)
- **Stage 3**: Canonical entity data (in metadata)

## Performance & Caching

Data is cached for fast loading:
- Metadata tracker: 5 minutes
- Video details: 1 minute
- Entity aggregations: 10 minutes

Click **"Refresh Data"** in sidebar to reload from S3.

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
├── 🏠_Home.py                 # Home page (overview)
├── pages/
│   ├── 1_🎬_Videos.py       # Videos list
│   ├── 2_📋_Video_Detail.py # Video deep dive
│   ├── 3_📍_Entities.py     # Entity explorer
│   └── 4_📈_Analytics.py    # Analytics
├── utils/
│   └── data_loader.py       # S3 data loading + caching
├── requirements.txt
└── README.md
```

## Export & Download

- Export videos/entities as CSV or JSON
- Download raw JSON for any video (Stages 1/2/3)
- Entity aggregations for external analysis

---

**Built with**: Streamlit + Plotly + Pandas
**Data**: Direct S3 integration via existing `S3Storage` and `MetadataTracker`
