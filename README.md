# TravelAI - YouTube Travel Content Intelligence Pipeline

**A fully automated pipeline for extracting structured travel insights from YouTube videos**

Turn travel vlogs into searchable, structured data using AI-powered transcription and entity extraction.

---

## Table of Contents

1. [What is TravelAI?](#what-is-travelai)
2. [Current Capabilities](#current-capabilities)
3. [Quick Start](#quick-start)
4. [Usage Guide](#usage-guide)
5. [Architecture & Design](#architecture--design)
6. [Data Schemas](#data-schemas)
7. [Configuration](#configuration)
8. [Project Status & Statistics](#project-status--statistics)
9. [Cost Analysis](#cost-analysis)
10. [Troubleshooting & Advanced Topics](#troubleshooting--advanced-topics)
11. [Future Roadmap](#future-roadmap)
12. [Project Structure](#project-structure)

---

## What is TravelAI?

TravelAI is an **AI-powered data pipeline** that transforms unstructured YouTube travel content into structured, queryable travel intelligence.

### The Problem
Millions of hours of travel experiences are shared on YouTube, but this valuable information is locked in video format - unsearchable, unstructured, and hard to extract insights from.

### The Solution
TravelAI automatically:
1. **Crawls** YouTube travel videos and extracts transcripts using Whisper AI
2. **Extracts** structured travel entities (destinations, restaurants, hotels, activities) using LLMs
3. **Stores** everything in S3 with automatic deduplication and pipeline tracking
4. **Provides** search and filtering tools to explore extracted travel insights

### Real-World Use Cases
- **Travel recommendation engines**: "Find budget restaurants in Phuket mentioned by solo travelers"
- **Destination research**: Aggregate experiences across hundreds of videos about a location
- **Travel planning**: Discover hidden gems and authentic experiences from real travelers
- **Content analysis**: Understand travel trends, popular destinations, and traveler preferences

---

## Current Capabilities

### ✅ Stage 1: YouTube Video Crawling (Complete)

**What it does:**
- Crawls YouTube videos (regular videos + Shorts)
- Extracts metadata (title, author, duration, views, likes, tags, etc.)
- Downloads audio and transcribes using **Whisper AI**
- **Auto-detects language** (supports 99+ languages)
- Stores everything in **S3** with structured paths

**Key Features:**
- **Automatic Deduplication**: Checks S3 before processing to avoid re-processing
- **S3-Only Storage**: Single source of truth for team collaboration (no local data files)
- **Browser Cookie Support**: Bypasses YouTube bot detection using Chrome/Firefox/Safari cookies
- **Pipeline Tracking**: MetadataTracker maintains processing state for each video across all stages

**Processing Time:** 2-4 minutes per video (CPU-based Whisper)
**Cost:** FREE (except minimal S3 storage ~$0.01/month)

---

### ✅ Stage 2: LLM Entity Extraction (Complete)

**What it does:**
- Extracts structured travel information from video transcripts
- Identifies **traveler profile** (type, age, budget, travel style)
- Extracts **travel entities**: destinations, restaurants, hotels, activities, attractions
- Provides **rich details**: location, experience description, sentiment, costs, timestamps

**Key Features:**
- **Multi-LLM Support**: Gemini (default), OpenAI, DeepSeek
- **Automatic Fallback**: If primary LLM fails, automatically tries alternatives
- **Smart Video Classification**: Automatically detects short (<35 min) vs long (>=35 min) videos
- **Dual Processing Strategies**:
  - **Short videos**: Single-pass extraction (entire transcript at once)
  - **Long videos**: Hierarchical chunked extraction (5-min chunks with 1-min overlap)
- **Intelligent Deduplication**: Merges duplicate entities across chunks by name+location
- **Cost-Optimized**: Uses Gemini Flash ($0.075/$0.30 per 1M tokens) - 50% cheaper than OpenAI
- **Quality Scoring**: Automatic assessment (high, medium, low)
- **Data Viewing**: View and filter extracted entities with built-in CLI tools

**Processing Time:**
- Short videos: 15-20 seconds
- Long videos: 2-4 minutes (depends on video length and chunk count)

**Cost:**
- Short videos: ~$0.0023 per video
- Long videos: ~$0.02-0.03 per video (with Gemini)

---

### ✅ Stage 3: Deduplication, Canonicalization & Consensus (Complete)

**What it does:**
- **Deduplicates** entities across all videos using 4-tier matching
- **Canonicalizes** entity groups into single unified entities
- **Calculates consensus** data (ratings, traveler profiles, themes)
- **Geocodes** entities with coordinates (lat/lon)
- **Tracks provenance** (traces entities back to source videos)

**Key Features:**
- **4-Tier Deduplication**:
  - Exact name matching (case-insensitive)
  - Fuzzy matching (handles typos, variations)
  - Semantic matching (understands "Grand Palace" = "Phra Borom Maha Ratcha Wang")
  - Location proximity (same place with different names)
- **Hybrid Geocoding**:
  - Primary: Nominatim (OpenStreetMap) - **FREE**
  - Fallback: Google Maps Geocoding API - Paid ($5/1000 requests)
  - Smart strategy: 90%+ use free Nominatim, only 10% need Google
- **LLM Theme Extraction**: Automatically extracts themes/tags using Gemini
- **Comprehensive Cost Tracking**: Tracks both LLM and geocoding costs
- **Quality Validation**: Built-in QA tools to validate output quality
- **Entity Search & Exploration**: Search, filter, and view canonical entities

**Processing Time:**
- 50 entities: ~30 seconds (mostly FREE geocoding)
- 1000 entities: ~10 minutes

**Cost:**
- LLM theme extraction: ~$0.000026 per entity (Gemini Flash)
- Geocoding: ~$0.005 per entity if Google needed, otherwise FREE
- **Typical 1000 entities**: ~$0.03 (mostly FREE with Nominatim)

**Output:**
- Canonical entities saved to S3 in multiple formats:
  - `stage3-canonical/entities_all.jsonl` (all entities)
  - `stage3-canonical/by_city/{city}.jsonl` (grouped by city)
  - `stage3-canonical/by_type/{type}.jsonl` (grouped by type)
- Cost reports with detailed breakdown
- QA reports with validation results

---

### ✅ Stage 4: Vector Embeddings & Semantic Search (Complete)

**What it does:**
- **Generates embeddings** for canonical entities using local FREE model
- **Indexes vectors** in ChromaDB for fast semantic search
- **Supports 3 embedding strategies** (entity, profile-consensus, experience)
- **Enables semantic search** (find similar entities by meaning, not just keywords)
- **Full provenance tracking** (trace embeddings back to source videos)

**Key Features:**
- **FREE Embedding Model**: Alibaba-NLP/gte-large (1024 dimensions)
  - Better quality than OpenAI's text-embedding-3-small
  - Runs locally (no API costs)
  - Fast inference (~50ms per embedding on CPU)
- **3-Collection Architecture**:
  - **Entities**: General entity search (1 embedding per entity)
  - **Profile Consensus**: Personalized search (1 embedding per entity-profile combo)
  - **Experiences**: Detailed exploration (1 embedding per traveler experience)
- **Local or Cloud Deployment**:
  - Local mode: FREE persistent storage (disk)
  - Cloud mode: Docker container or Kubernetes cluster
- **Metadata Filtering**: Filter by city, type, cost tier, traveler profile, themes
- **Built-in Backup/Restore**: S3 integration for vector backups
- **Provenance Tracking**: Every embedding linked to source video(s)

**Processing Time:**
- Entity embeddings: ~20 entities/second (CPU)
- Profile embeddings: ~15 embeddings/second (CPU)
- Experience embeddings: ~10 experiences/second (CPU)
- **1,000 entities (all types): ~5 minutes**

**Cost:**
- **FREE** (local embedding model, no API costs)
- Storage: ~5KB per entity (including metadata)
- 1,000 entities ≈ 15MB total storage

**ChromaDB Storage:**
- **3 Collections**:
  - `entities`: Entity-level embeddings with consensus data
  - `profile_consensus`: Profile-specific embeddings for personalized search
  - `experiences`: Individual traveler experiences with full provenance
- **Metadata Schema**: Rich filtering (location, type, cost, sentiment, traveler profile)
- **Similarity Metric**: Cosine similarity
- **Query Performance**: <100ms for 10,000 vectors (local mode)

**Example Searches:**
```bash
# General entity search
./crawl.sh search --query "best street food" --city Bangkok --top-k 10

# Personalized search
./crawl.sh search --query "romantic restaurants" \
    --profile couple_mid-range --city Phuket --top-k 5

# Filter by cost tier
./crawl.sh search --query "luxury hotels with beach view" \
    --cost-tier luxury --top-k 10

# Explore individual experiences
./crawl.sh search --query "snorkeling adventures" \
    --collection experiences --city "Phi Phi Islands" --top-k 20
```

**Output:**
- Vectors indexed in ChromaDB (local: `./chroma_data/` or cloud server)
- Provenance mapping saved to S3: `metadata/embedding_provenance.jsonl`
- Backup available at: `stage4-vectors/backup_YYYYMMDD_HHMMSS/`

For detailed ChromaDB configuration and schema, see [CHROMADB.md](CHROMADB.md).

---

### ✅ Stage 5: RAG Itinerary Generation (Complete)

**What it does:**
- **Natural Language Queries** → Personalized travel itineraries in 30-60 seconds
- Converts queries like *"5 days Bangkok solo budget party"* into structured day-by-day itineraries
- Uses 7-phase RAG pipeline with automatic validation and retry
- Generates engaging narratives with travel tips and cost breakdowns

**Key Features:**
- **7-Phase RAG Pipeline**:
  1. Intent Parsing: Extract destination, duration, budget, traveler profile
  2. Retrieval: Semantic search across 1,200+ canonical entities
  3. Re-ranking: LLM-based personalization (budget, interests, profile)
  4. Context Building: Group entities by relevance, cost, and location
  5. Generation: Create day-by-day itinerary with activities
  6. Validation: Detect hallucinations, budget violations, logical errors
  7. Narrative: Generate engaging travel guide with tips
- **Automatic Validation**: Retries up to 2x if quality issues detected
- **Cost Tracking**: Phase-by-phase cost breakdown with budget limits
- **Error Handling**: Graceful degradation with user-friendly messages
- **Multi-Format Output**: Markdown, text, JSON, or HTML
- **Batch Processing**: Generate multiple itineraries in parallel
- **Caching**: Reuse results for duplicate queries

**Processing Time:**
- Query parsing: ~2-3 seconds
- Retrieval + re-ranking: ~3-5 seconds
- Itinerary generation: ~15-20 seconds
- Validation: ~5-8 seconds
- Narrative generation: ~10-15 seconds (can be skipped)
- **Total: 30-60 seconds per itinerary** (35-50s without narrative)

**Cost:**
- Intent parsing: ~$0.0001 (DeepSeek)
- Re-ranking: ~$0.0015 (DeepSeek/Gemini)
- Itinerary generation: ~$0.008 (Gemini)
- Narrative generation: ~$0.0025 (DeepSeek)
- **Total per itinerary: $0.01-0.02** (using Gemini + DeepSeek)
- Embedding retrieval: **FREE** (local ChromaDB)

**Example Usage:**
```bash
# Generate itinerary from natural language query
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget party"

# With options
./crawl.sh generate-itinerary \
    -q "3 days Phuket couple mid-range beach relaxation" \
    --output-format markdown \
    --save output.md \
    --skip-narrative

# Quick test (no narrative, faster)
./crawl.sh quick-test

# Check environment readiness
./crawl.sh check-stage5

# Run integration tests
./crawl.sh test-stage5
```

**Example Output:**
```markdown
# 5-Day Bangkok Itinerary: Solo Budget Traveler's Party Adventure

## Day 1: Welcome to Bangkok - Old Town Exploration
- **Morning**: Grand Palace & Wat Phra Kaew (9:00 AM - 12:00 PM)
  - Entry: 500 THB (~$14)
  - Tips: Dress modestly, arrive early to beat crowds
- **Lunch**: Street Food at Khao San Road (12:30 PM - 1:30 PM)
  - Cost: ~150 THB (~$4)
  - Try: Pad Thai, Mango Sticky Rice
- **Evening**: Khao San Road Nightlife (8:00 PM - Late)
  - Budget: 600-800 THB (~$17-23)
  - Tips: Pre-game at 7-Eleven to save money

**Daily Budget**: ~$50 | **Total So Far**: $50

[... Days 2-5 ...]

## Trip Summary
- **Total Budget**: ~$250 for 5 days
- **Budget Breakdown**: Accommodation (40%), Food (25%), Activities (20%), Transport (10%), Nightlife (5%)
- **Best Value Tips**:
  - Book hostels near Khao San Road ($8-12/night)
  - Use street food and local markets
  - Take BTS/MRT instead of taxis
```

**Advanced Features:**
- **Budget alerts**: Warns if itinerary exceeds user budget
- **Insufficient data handling**: Suggests alternative destinations if not enough data
- **Automatic retry**: Regenerates if validation fails
- **Graceful degradation**: Relaxes constraints if no perfect match
- **Cost reports**: Detailed breakdown of LLM API costs

**Files Created:**
- Pipeline orchestrator: [src/rag/pipeline.py](src/rag/pipeline.py)
- Cost tracking: [src/utils/rag_cost_tracker.py](src/utils/rag_cost_tracker.py)
- Error handling: [src/rag/error_handling.py](src/rag/error_handling.py)
- CLI interface: [cli/generate_itinerary.py](cli/generate_itinerary.py)
- Quick test: [cli/quick_test.py](cli/quick_test.py)
- Environment check: [cli/check_stage5_ready.py](cli/check_stage5_ready.py)

**Documentation:**
- Cost tracking guide: [docs/COST_TRACKING.md](docs/COST_TRACKING.md)
- Error handling guide: [docs/ERROR_HANDLING.md](docs/ERROR_HANDLING.md)
- Command reference: [docs/COMMANDS.md](docs/COMMANDS.md)

---

### ✅ Pipeline Monitoring & Management

**Available Commands:**
- View pipeline status and statistics (`./crawl.sh status`)
- Check stage-specific details (`./crawl.sh stage stage_2_extract`, `./crawl.sh stage stage_3_deduplicate`, `./crawl.sh stage stage_4_vectorize`)
- List failed videos (`./crawl.sh failed`)
- View language distribution (`./crawl.sh languages`)
- View extracted entities for any video (`./crawl.sh view-stage2 VIDEO_ID`)
- List all processed videos with filtering (`./crawl.sh list-stage2`)
- **Stage 3 Tools**:
  - View canonical entity statistics (`./crawl.sh stage3-stats`)
  - Search entities by name (`./crawl.sh search-entities --query "temple"`)
  - Show entity details with provenance (`./crawl.sh show-entity ATT_001`)
  - Validate Stage 3 quality (`./crawl.sh validate-stage3`)
- **Stage 4 Tools**:
  - View vector database statistics (`./crawl.sh stage4-stats`)
  - Semantic search across entities (`./crawl.sh search --query "best street food" --city Bangkok`)
  - Backup vectors to S3 (`./crawl.sh backup-vectors --destination s3`)
  - Sync to cloud ChromaDB (`./crawl.sh sync-to-cloud --source local --destination cloud`)
  - Monitor Stage 4 processing (`./crawl.sh monitor-stage4`)
- Audit S3 consistency (`./crawl.sh audit --stage stage_2_extract`)
- Export data to CSV (`./crawl.sh export data.csv`)

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **AWS Account** with S3 access
- **API Keys**:
  - YouTube Data API key (for metadata)
  - Gemini API key (recommended for Stage 2) OR OpenAI/DeepSeek

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd TravelAI

# Run automated setup
./setup.sh

# The setup script will:
# - Verify Python 3.11+ is installed
# - Create virtual environment
# - Install all dependencies
# - Create necessary directories
# - Set up .env file
# - Verify AWS credentials
```

### Configuration

1. **Copy environment template:**
```bash
cp .env.example .env
```

2. **Edit `.env` with your credentials:**
```bash
# AWS Configuration (Required)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# YouTube API (Required for Stage 1)
YOUTUBE_API_KEY=your_youtube_api_key

# LLM Provider (Required for Stage 2)
LLM_PROVIDER=gemini  # Options: gemini, openai, deepseek

# Gemini API (Recommended - cheapest option)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash-lite

# Optional: OpenAI or DeepSeek (for fallback)
OPENAI_API_KEY=your_openai_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

### First Run

```bash
# Activate virtual environment
source venv/bin/activate  # Windows: venv\Scripts\activate

# Create a test URLs file
cat > test_urls.txt << EOF
https://www.youtube.com/watch?v=UEDeptPVNQA
https://www.youtube.com/watch?v=8m8ReerO060
EOF

# Stage 1: Crawl videos (metadata + transcripts)
./crawl.sh youtube --input test_urls.txt --limit 2

# Check status
./crawl.sh status

# Stage 2: Extract travel entities
./crawl.sh process-stage2 --limit 2

# View extracted entities
./crawl.sh list-stage2
./crawl.sh view-stage2 youtube_UEDeptPVNQA

# Stage 3: Deduplicate and create canonical entities
./crawl.sh process-stage3 --limit 2

# View canonical entities
./crawl.sh stage3-stats
./crawl.sh search-entities --query "temple"
./crawl.sh validate-stage3

# Stage 4: Generate embeddings and index in ChromaDB
./crawl.sh process-stage4 --embedding-types all --limit 2

# View vector database and test semantic search
./crawl.sh stage4-stats
./crawl.sh search --query "best street food" --city Bangkok --top-k 5
```

**Note:** `crawl.sh` is a helper script that automatically sets `PYTHONPATH`. You can also run directly:
```bash
PYTHONPATH=. python cli/crawl.py youtube --input urls.txt
```

---

## Usage Guide

### Stage 1: Crawling YouTube Videos

#### Basic Crawling

```bash
# Create URLs file with YouTube video links
cat > urls.txt << EOF
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2
https://www.youtube.com/shorts/SHORT_ID
EOF

# Crawl videos (automatically skips already processed)
./crawl.sh youtube --input urls.txt

# Test with limited videos
./crawl.sh youtube --input urls.txt --limit 5

# Preview without actually crawling
./crawl.sh youtube --input urls.txt --dry-run
```

#### Advanced Options

```bash
# Force re-processing (overwrites existing data)
./crawl.sh youtube --input urls.txt --force

# Validate URLs file before crawling
./crawl.sh validate --input urls.txt
```

**How Deduplication Works:**
- TravelAI checks S3 metadata before processing each video
- If video already exists with `stage_1_crawl: complete`, it's skipped
- Use `--force` flag to intentionally reprocess videos
- Safe by default - no accidental re-processing

---

### Stage 2: Entity Extraction

#### Basic Extraction

```bash
# Process all pending videos (recommended)
./crawl.sh process-stage2

# Test with limited videos
./crawl.sh process-stage2 --limit 5

# Use specific LLM provider
./crawl.sh process-stage2 --provider gemini
./crawl.sh process-stage2 --provider openai
```

#### Advanced Options

```bash
# Reprocess videos that already have Stage 2 data
./crawl.sh process-stage2 --force

# Reprocess specific videos
./crawl.sh process-stage2 --force --limit 10

# Debug mode
./crawl.sh process-stage2 --limit 1 --log-level DEBUG
```

**What Gets Extracted:**

**Traveler Profile:**
- Type (solo, couple, family, group)
- Age range (18-25, 26-35, 36-50, 50+)
- Budget tier (budget, mid-range, luxury)
- Travel style (adventure, cultural, foodie, relaxation, nightlife)

**Travel Entities:**
- **Destinations**: Cities, beaches, regions
- **Restaurants**: Street food, cafes, fine dining
- **Hotels**: Hostels, resorts, Airbnbs
- **Activities**: Tours, experiences, adventures
- **Attractions**: Temples, museums, landmarks
- **Transportation**: Flights, taxis, boats
- **Shopping**: Markets, malls, stores

Each entity includes:
- Name and type
- Location (city/area)
- Experience description (what the traveler said)
- Sentiment (positive, negative, neutral, mixed)
- Cost mentioned (if any)
- Timestamp in video
- Confidence score

**Processing Strategies:**

**Short Videos (<35 minutes):**
- Single-pass extraction using full transcript
- Faster processing (~15-20 seconds)
- Lower cost (~$0.0023 per video)
- Best for: Most travel vlogs, quick guides, destination highlights

**Long Videos (>=35 minutes):**
- Hierarchical chunked extraction:
  - Splits transcript into 5-minute chunks with 1-minute overlap
  - Extracts entities from each chunk independently
  - Merges and deduplicates results by (name, location)
  - Combines traveler profile signals from all chunks
- Longer processing (~2-4 minutes depending on length)
- Slightly higher cost (~$0.02-0.03 per video)
- Best for: In-depth travel documentaries, multi-day itineraries, detailed guides

---

### Pipeline Monitoring

#### Check Status

```bash
# Overall pipeline status
./crawl.sh status

# Stage-specific details
./crawl.sh stage stage_1_crawl
./crawl.sh stage stage_2_extract

# List failed videos
./crawl.sh failed

# Language distribution
./crawl.sh languages

# Export to CSV
./crawl.sh export pipeline_status.csv
```

#### View Extracted Data

```bash
# View all entities for a video
./crawl.sh view-stage2 youtube_abc123

# Filter by entity type
./crawl.sh view-stage2 youtube_abc123 --type restaurant
./crawl.sh view-stage2 youtube_abc123 --type hotel
./crawl.sh view-stage2 youtube_abc123 --type activity

# Filter by sentiment
./crawl.sh view-stage2 youtube_abc123 --sentiment positive
./crawl.sh view-stage2 youtube_abc123 --sentiment negative

# Filter by confidence score
./crawl.sh view-stage2 youtube_abc123 --min-confidence 0.8

# Combine filters
./crawl.sh view-stage2 youtube_abc123 -t restaurant --min-confidence 0.8

# Export as JSON
./crawl.sh view-stage2 youtube_abc123 --json > output.json
```

#### List Processed Videos

```bash
# List all Stage 2 processed videos
./crawl.sh list-stage2

# List top 20 videos (sorted by entity count)
./crawl.sh list-stage2 --limit 20

# Sort by different fields
./crawl.sh list-stage2 --sort-by title
./crawl.sh list-stage2 --sort-by date
./crawl.sh list-stage2 --sort-by entities

# Filter videos
./crawl.sh list-stage2 --min-entities 30
./crawl.sh list-stage2 --type restaurant
```

---

### S3 Data Management

#### Audit S3 Consistency

```bash
# Check for discrepancies between S3 and metadata
./crawl.sh audit --stage stage_2_extract
./crawl.sh audit --stage stage_1_crawl

# Show missing videos
./crawl.sh audit --stage stage_2_extract --show-missing

# Show extra files
./crawl.sh audit --stage stage_2_extract --show-extra
```

#### Reset Stage Status

```bash
# Preview reset (dry-run)
./crawl.sh reset --stage stage_2_extract --all --dry-run

# Reset all videos for a stage
./crawl.sh reset --stage stage_2_extract --all

# Reset specific video
./crawl.sh reset --stage stage_2_extract --video-id youtube_abc123

# Reset only failed videos
./crawl.sh reset --stage stage_2_extract --status failed

# Skip confirmation prompt
./crawl.sh reset --stage stage_2_extract --all -y
```

#### Sync Metadata with S3

```bash
# Sync metadata tracker with actual S3 contents
./crawl.sh sync --stage stage_2_extract
./crawl.sh sync --stage stage_1_crawl
```

For complete command reference, see [COMMANDS.md](COMMANDS.md).

---

## Architecture & Design

### S3 Storage Structure

```
s3://your-bucket/
│
├── raw/
│   ├── new/                         # Videos pending Stage 2
│   │   └── youtube_video_VIDEO_ID.jsonl
│   └── stage2_processed/            # Videos completed Stage 2
│       └── youtube_video_VIDEO_ID.jsonl
│
├── stage2-extracted/
│   ├── new/                         # Extractions pending Stage 3
│   │   └── youtube_video_VIDEO_ID_extracted.jsonl
│   └── stage3_processed/            # Extractions completed Stage 3
│       └── youtube_video_VIDEO_ID_extracted.jsonl
│
├── stage3-canonical/                # Stage 3 output
│   ├── entities_all.jsonl           # All canonical entities
│   ├── by_city/                     # Grouped by city
│   │   └── Bangkok.jsonl
│   └── by_type/                     # Grouped by type
│       └── restaurant.jsonl
│
├── stage4-vectors/                  # Stage 4 vector backups
│   └── backup_YYYYMMDD_HHMMSS/
│       └── chroma_data.tar.gz
│
└── metadata/
    ├── processing_status.jsonl      # Pipeline tracking
    └── embedding_provenance.jsonl   # Embedding-to-video mapping
```

### Path Conventions

#### Stage 1: Raw Video Data
**Format:** `raw/new/youtube_video_{VIDEO_ID}.jsonl`
**Example:** `raw/new/youtube_video_UEDeptPVNQA.jsonl`

**After Stage 2 completion, moved to:** `raw/stage2_processed/youtube_video_{VIDEO_ID}.jsonl`

**Why this structure?**
- ✅ One file per video (independent processing)
- ✅ Self-documenting filename
- ✅ Easy to find specific video data
- ✅ File movement tracks processing state

#### Stage 2: Extracted Entities
**Format:** `stage2-extracted/new/youtube_video_{VIDEO_ID}_extracted.jsonl`
**Example:** `stage2-extracted/new/youtube_video_UEDeptPVNQA_extracted.jsonl`

**After Stage 3 completion, will move to:** `stage2-extracted/stage3_processed/`

**Why this structure?**
- ✅ Clear distinction between stages
- ✅ Easy to identify extraction output files
- ✅ File movement indicates progress through pipeline
- ✅ Ready for Stage 3 processing

#### Metadata Tracking
**Format:** `metadata/processing_status.jsonl`
**Single file** that tracks all content items across all pipeline stages.

**Why single file?**
- ✅ Centralized state management
- ✅ Fast loading (entire state in memory)
- ✅ Atomic updates (no partial state)
- ✅ Simple synchronization across team

### Processing Flow

#### Stage 1: Crawling Flow

```
Input: URLs (urls.txt)
    ↓
Extract Video IDs
    ↓
Check S3 Metadata (deduplication)
    ↓
Skip if already processed (unless --force)
    ↓
For new videos:
    ↓
Fetch Metadata → YouTube Data API
    ↓
Download Audio → yt-dlp + browser cookies
    ↓
Transcribe Audio → Whisper AI
    ↓
Detect Language → Whisper auto-detect
    ↓
Build YouTubeVideo object
    ↓
Upload to S3 → raw/new/youtube_video_*.jsonl
    ↓
Update MetadataTracker → stage_1_crawl: complete
    ↓
Save tracking to S3
```

**Code Location:** [cli/crawl.py](cli/crawl.py), [src/crawlers/youtube.py](src/crawlers/youtube.py)

#### Stage 2: Entity Extraction Flow

```
Input: Videos with stage_1_crawl: complete
    ↓
Filter: stage_2_extract: not_started | pending | failed
    ↓
For each video:
    ↓
Download transcript from S3
    ↓
Classify video length (< 35 min = short, >= 35 min = long)
    ↓
If short video (< 35 min):
    ↓
Build extraction prompt (full transcript)
    ↓
Call LLM API → Gemini/OpenAI/DeepSeek
    ↓
Parse JSON response → traveler_profile + entities
    ↓
Validate with Pydantic schemas
    ↓
Calculate quality score (high/medium/low)
    ↓
Upload to S3 → stage2-extracted/new/youtube_video_*_extracted.jsonl
    ↓
Move raw file → raw/new/ to raw/stage2_processed/
    ↓
Update MetadataTracker → stage_2_extract: complete
    ↓
Save tracking to S3
```

**Code Location:** [cli/process_stage2.py](cli/process_stage2.py), [src/processors/stage2_extractor.py](src/processors/stage2_extractor.py)

#### LLM Provider Fallback Logic

```
User specifies provider (--provider gemini)
    OR
Default from .env (LLM_PROVIDER=gemini)
    ↓
Try primary provider (e.g., Gemini)
    ↓
If API key missing or error occurs:
    ↓
Automatic fallback to alternatives:
    - Gemini → DeepSeek → OpenAI
    - DeepSeek → Gemini → OpenAI
    - OpenAI → Gemini → DeepSeek
    ↓
If all providers fail → return error
```

**Code Location:** [src/utils/llm_client.py](src/utils/llm_client.py)

### Key Components

#### 1. S3 Storage Layer
**File:** [src/storage/s3.py](src/storage/s3.py)

**Key Functions:**
- `upload_jsonl()` - Upload data to S3
- `download_jsonl()` - Download JSONL files
- `list_files()` - List files in S3 prefix
- `file_exists()` - Check if file exists
- `move_file()` - Move files between S3 paths

#### 2. Metadata Tracker
**File:** [src/utils/metadata_tracker.py](src/utils/metadata_tracker.py)

**Key Functions:**
- `register_content()` - Add new video to tracking
- `start_stage()` - Mark stage as started
- `complete_stage()` - Mark stage as complete with metadata
- `fail_stage()` - Mark stage as failed with error
- `save_to_s3()` - Persist tracking data to S3
- `content_exists()` - Check if video already tracked
- `get_stage_statistics()` - Get stats for a pipeline stage

**In-Memory Cache:**
- Loads entire `processing_status.jsonl` into memory on initialization
- Provides fast lookups and updates
- Automatically saves to S3 on modification

#### 3. YouTube Crawler
**File:** [src/crawlers/youtube.py](src/crawlers/youtube.py)

**Key Functions:**
- `extract_video_id()` - Parse video ID from URL (supports Shorts!)
- `fetch_video_metadata()` - Get metadata from YouTube Data API
- `download_audio()` - Download audio using yt-dlp + browser cookies
- `transcribe_audio()` - Transcribe using Whisper + auto-detect language
- `crawl_video()` - Full crawl pipeline for single video
- `crawl_videos()` - Batch crawl with progress tracking

**Whisper Configuration:**
- Current model: **"small"** (244M parameters)
- Available: tiny, base, small, medium, large
- Device: CPU (can use GPU on cloud)

#### 4. LLM Client
**File:** [src/utils/llm_client.py](src/utils/llm_client.py)

**Key Functions:**
- `extract_with_llm()` - Unified interface for all LLM providers
- `extract_with_gemini()` - Google Gemini integration
- `extract_with_openai()` - OpenAI GPT-4o-mini integration
- `extract_with_deepseek()` - DeepSeek API integration
- `get_extraction_cost()` - Calculate extraction costs

**Supported Models:**
- **Gemini**: gemini-2.5-flash-lite (default), gemini-1.5-pro
- **OpenAI**: gpt-4o-mini
- **DeepSeek**: deepseek-chat, deepseek-reasoner

**Features:**
- Automatic provider fallback
- Native JSON mode (structured output)
- Token usage tracking
- Cost calculation per extraction
- Retry logic with exponential backoff

#### 5. Stage 2 Processor
**File:** [src/processors/stage2_extractor.py](src/processors/stage2_extractor.py)

**Key Functions:**
- `process_short_video()` - Extract entities from videos < 35 min
- `classify_video_length()` - Determine extraction strategy
- `save_stage2_output()` - Save extracted data to S3
- `assess_extraction_quality()` - Calculate quality score

**Quality Assessment:**
- **High**: 40+ entities, high confidence scores
- **Medium**: 20-39 entities or medium confidence
- **Low**: < 20 entities or low confidence

---

## Data Schemas

### Stage 1: Raw Video Data Schema

**File Location:** `raw/new/youtube_video_{VIDEO_ID}.jsonl`

#### Video Metadata
```json
{
  "source": "youtube",
  "source_id": "UEDeptPVNQA",
  "source_url": "https://youtube.com/watch?v=UEDeptPVNQA",
  "content_type": "vlog",
  "title": "How to travel Thailand | The PERFECT 2 week Itinerary",
  "author": "Travel Vlogger",
  "author_url": "https://youtube.com/channel/UC...",
  "published_date": "2024-11-17",
  "duration_seconds": 1565,
  "language": "en"
}
```

#### Transcript Structure
```json
"transcript": [
  {
    "text": "Today we're exploring Phuket, starting with Patong Beach",
    "start": 45.0,
    "duration": 3.2
  },
  {
    "text": "The beach is beautiful but quite touristy",
    "start": 48.2,
    "duration": 2.8
  }
]
```

#### Additional Metadata
```json
"metadata": {
  "view_count": 156789,
  "like_count": 5432,
  "comment_count": 234,
  "tags": ["Thailand", "Phuket", "Travel Guide"],
  "transcript_type": "whisper"
},
"provenance": {
  "can_redistribute": false,
  "attribution_required": true,
  "tos_version": "youtube_tos_2024"
},
"fetched_at": "2025-12-03T14:18:27.633472Z",
"fetched_by": "crawler_v1_whisper"
```

**Key Fields:**
- `language`: ISO 639-1 code (en, hi, es, etc.) - auto-detected by Whisper
- `transcript`: Array of segments with text, start time, and duration
- `duration_seconds`: Total video length
- `source_id`: YouTube video ID

---

### Stage 2: Extracted Entities Schema

**File Location:** `stage2-extracted/new/youtube_video_{VIDEO_ID}_extracted.jsonl`

#### Complete Structure
```json
{
  "content_id": "youtube_UEDeptPVNQA",
  "source_id": "UEDeptPVNQA",
  "language": "en",
  "processed_at": "2025-12-03T07:26:27.916200Z",
  "llm_model": "gemini:gemini-2.5-flash-lite",
  "tokens_used": 13450,
  "cost_usd": 0.0022,
  "extraction_quality": "high",
  "traveler_profile": {
    "traveler_type": "solo",
    "age_range": "26-35",
    "budget_tier": "mid-range",
    "travel_style": ["adventure", "cultural", "foodie"],
    "confidence_score": 0.85
  },
  "entities": [
    {
      "entity_name": "Patong Beach",
      "entity_type": "destination",
      "location": "Phuket",
      "experience": "Beautiful beach but quite touristy. Best time to visit is early morning to avoid crowds.",
      "sentiment": "positive",
      "cost_mentioned": "free entry",
      "timestamp_start": 45.0,
      "confidence_score": 0.9
    },
    {
      "entity_name": "Street Food Near Big Buddha",
      "entity_type": "restaurant",
      "location": "Phuket",
      "experience": "Authentic Thai street food. Pad thai was delicious and mango sticky rice was amazing.",
      "sentiment": "positive",
      "cost_mentioned": "60 baht pad thai, 80 baht mango sticky rice",
      "timestamp_start": 120.5,
      "confidence_score": 0.85
    }
  ]
}
```

#### Traveler Profile Fields

| Field | Possible Values | Description |
|-------|----------------|-------------|
| `traveler_type` | solo, couple, family, group, unknown | Type of traveler |
| `age_range` | 18-25, 26-35, 36-50, 50+, unknown | Age demographic |
| `budget_tier` | budget, mid-range, luxury, unknown | Budget category |
| `travel_style` | array of tags | adventure, cultural, foodie, relaxation, nightlife |
| `confidence_score` | 0.0 - 1.0 | Confidence in profile inference |

#### Entity Fields

| Field | Type | Description |
|-------|------|-------------|
| `entity_name` | string | Name of place/activity |
| `entity_type` | string | destination, restaurant, hotel, activity, attraction, transportation, shopping, unknown |
| `location` | string | City or area (e.g., "Phuket", "Bangkok Old Town") |
| `experience` | string | Detailed description from traveler (10-300 chars) |
| `sentiment` | string | positive, negative, neutral, mixed |
| `cost_mentioned` | string | Cost info if mentioned (optional) |
| `timestamp_start` | float | Start time in video seconds (optional) |
| `confidence_score` | float | Confidence in extraction (0.0-1.0) |

---

### Metadata Tracking Schema

**File Location:** `metadata/processing_status.jsonl`

Each line represents one video's status across all pipeline stages:

```json
{
  "content_id": "youtube_UEDeptPVNQA",
  "source": "youtube",
  "source_url": "https://youtube.com/watch?v=UEDeptPVNQA",
  "title": "How to travel Thailand | The PERFECT 2 week Itinerary",
  "added_at": "2025-11-03T14:18:30.123456Z",
  "stages": {
    "stage_1_crawl": {
      "status": "complete",
      "started_at": "2025-11-03T14:18:30Z",
      "completed_at": "2025-11-03T14:21:45Z",
      "duration_seconds": 195.66,
      "s3_paths": [
        "s3://bucket/raw/new/youtube_video_UEDeptPVNQA.jsonl"
      ],
      "metadata": {
        "video_id": "UEDeptPVNQA",
        "duration_seconds": 1565,
        "transcript_segments": 168,
        "view_count": 156789,
        "language": "en"
      },
      "error": null,
      "retry_count": 0
    },
    "stage_2_extract": {
      "status": "complete",
      "started_at": "2025-12-03T07:26:08Z",
      "completed_at": "2025-12-03T07:26:27Z",
      "duration_seconds": 19.67,
      "s3_paths": [
        "s3://bucket/stage2-extracted/new/youtube_video_UEDeptPVNQA_extracted.jsonl"
      ],
      "metadata": {
        "entities_extracted": 42,
        "extraction_quality": "high",
        "tokens_used": 13450,
        "cost_usd": 0.0022,
        "llm_model": "gemini:gemini-2.5-flash-lite"
      },
      "error": null,
      "retry_count": 0
    },
    "stage_3_deduplicate": {
      "status": "complete",
      "started_at": "2025-12-14T10:15:00Z",
      "completed_at": "2025-12-14T10:15:45Z",
      "duration_seconds": 45.2,
      "s3_paths": [
        "s3://bucket/stage3-canonical/entities_all.jsonl"
      ],
      "metadata": {
        "canonical_entities_created": 42,
        "entity_groups_merged": 12,
        "geocoding_cost_usd": 0.015,
        "llm_cost_usd": 0.0012
      }
    },
    "stage_4_vectorize": {
      "status": "complete",
      "started_at": "2025-12-14T10:20:00Z",
      "completed_at": "2025-12-14T10:25:30Z",
      "duration_seconds": 330.5,
      "metadata": {
        "chromadb_mode": "local",
        "embedding_types_indexed": ["entity", "profile", "experience"],
        "canonical_entities_from_video": 42,
        "collections": {
          "entities": true,
          "profile_consensus": true,
          "experiences": true
        },
        "total_embeddings_in_db": 156
      }
    }
  },
  "pipeline_status": "stage_3_pending",
  "last_updated": "2025-12-03T07:26:27Z",
  "total_error_count": 0,
  "tags": []
}
```

**Pipeline Stages:**

| Stage | Status | Description |
|-------|--------|-------------|
| `stage_1_crawl` | ✅ complete | YouTube crawling & transcription |
| `stage_2_extract` | ✅ complete | LLM entity extraction |
| `stage_3_deduplicate` | ✅ complete | Deduplication & canonicalization |
| `stage_4_vectorize` | ✅ complete | Vector embeddings & ChromaDB indexing |

**Stage Status Values:**
- `not_started` - Stage hasn't begun
- `pending` - Stage queued but not running
- `running` - Currently processing
- `complete` - Successfully completed
- `failed` - Processing failed (with error details)

---

## Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# ============================================
# AWS Configuration (Required)
# ============================================
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# ============================================
# YouTube API (Required for Stage 1)
# ============================================
YOUTUBE_API_KEY=your_youtube_api_key

# ============================================
# LLM Provider (Required for Stage 2)
# ============================================
LLM_PROVIDER=gemini  # Options: gemini, openai, deepseek

# Gemini API (Recommended - cheapest option)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash-lite  # or gemini-1.5-pro

# OpenAI API (Optional - for fallback)
OPENAI_API_KEY=your_openai_api_key

# DeepSeek API (Optional - for fallback)
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat

# ============================================
# Optional Configuration
# ============================================
LOG_LEVEL=INFO
CRAWLER_RATE_LIMIT=2
MAX_RETRIES=3
```

### Getting API Keys

#### YouTube Data API
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "YouTube Data API v3"
4. Create credentials (API Key)
5. Copy the API key to `.env`

#### Gemini API (Recommended)
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy to `.env` as `GEMINI_API_KEY`

#### OpenAI API (Optional)
1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create a new API key
3. Copy to `.env` as `OPENAI_API_KEY`

#### DeepSeek API (Optional)
1. Go to [DeepSeek Platform](https://platform.deepseek.com/)
2. Create a new API key
3. Copy to `.env` as `DEEPSEEK_API_KEY`

---

## Project Status & Statistics

**Last Updated:** December 7, 2025
**Current Stage:** Stage 2 (Entity Extraction) - ✅ **COMPLETE**
**S3 Bucket:** travel-ai-data-divyansh-2025

### Current Statistics

#### Stage 1 (Crawling)
- **Total Videos Crawled:** 117
- **Languages Detected:** Multiple (English, Hindi, Spanish, Thai, etc.)
- **Success Rate:** 100%
- **Average Processing Time:** 2-4 minutes per video
- **Total Cost:** ~FREE (only S3 storage ~$0.01/month)

#### Stage 2 (Entity Extraction)
- **Total Videos Processed:** 117
- **Success Rate:** ~100%
- **Total Entities Extracted:** ~5,000+
- **Average Entities per Video:** 42-57
- **Average Cost per Video:** $0.0022-0.0030 (using Gemini)
- **Average Processing Time:** 16-20 seconds per video
- **Total Stage 2 Cost:** ~$0.26 for all 117 videos

#### Quality Distribution
- **High Quality:** ~95% of videos
- **Medium Quality:** ~5% of videos
- **Low Quality:** ~0% of videos

#### LLM Provider Usage
- **Primary:** Gemini 2.5 Flash Lite (99% of extractions)
- **Fallback Used:** < 1% (mostly for testing)

---

## Cost Analysis

### Detailed Cost Breakdown

#### Stage 1 Costs (Crawling)
- **YouTube Data API:** FREE (within 10,000 units/day quota)
- **Whisper Transcription:** FREE (local CPU processing)
- **S3 Storage:** ~$0.023 per GB/month
  - Current usage: ~500 MB
  - Monthly cost: **~$0.01**
- **Data Transfer:** Negligible (< $0.01)
- **Total Stage 1:** **~FREE** (excluding minimal S3)

#### Stage 2 Costs (Entity Extraction)

**Gemini API (Recommended):**
- Pricing: $0.075 per 1M input tokens, $0.30 per 1M output tokens
- Average per video: ~12K input tokens, ~3K output tokens
- Cost per video: **~$0.0022**
- Cost for 117 videos: **~$0.26**

**Cost Comparison (per 1M tokens):**
| Provider | Input | Output | Est. Cost/Video |
|----------|-------|--------|----------------|
| **Gemini** | $0.075 | $0.30 | **$0.0022** |
| DeepSeek | $0.14 | $0.28 | $0.0028 |
| OpenAI | $0.150 | $0.60 | $0.0045 |

**Savings:** Using Gemini saves ~50% vs OpenAI, ~25% vs DeepSeek

#### Total Project Cost
- **Development:** N/A (internal)
- **Infrastructure:** ~$0.27 total
- **Per Video (end-to-end):** ~$0.0023
- **Cost to Scale:**
  - 1,000 videos: ~$2.30
  - 10,000 videos: ~$23.00
  - 100,000 videos: ~$230.00

**Conclusion:** Extremely cost-effective pipeline! Cheaper than hiring humans to watch and annotate videos.

---

## Troubleshooting & Advanced Topics

### Common Issues

#### S3 Upload Failed
```bash
# Check AWS credentials
cat .env | grep AWS

# Test S3 access
aws s3 ls s3://your-bucket/

# Verify bucket exists
aws s3 mb s3://your-bucket/  # Create if needed
```

#### Module Not Found
```bash
# Use helper script (sets PYTHONPATH automatically)
./crawl.sh youtube --input urls.txt

# Or set PYTHONPATH manually
export PYTHONPATH=/path/to/TravelAI
python cli/crawl.py youtube --input urls.txt
```

#### YouTube Bot Detection (403 Error)
```bash
# Make sure you're logged into YouTube in Chrome
# Then run crawler (it uses browser cookies)
./crawl.sh youtube --input urls.txt

# If still failing, try different browser:
# Update yt-dlp to use Firefox cookies instead
# Edit src/crawlers/youtube.py: --cookies-from-browser firefox
```

#### Already Processed Videos Not Being Skipped
```bash
# Check S3 connection
aws s3 ls s3://your-bucket/metadata/

# Verify metadata tracker
./crawl.sh status

# If metadata is corrupted, sync with S3
./crawl.sh sync --stage stage_1_crawl
```

#### LLM API Errors
```bash
# Check API keys are set
cat .env | grep API_KEY

# Test with debug logging
./crawl.sh process-stage2 --limit 1 --log-level DEBUG

# Try different provider
./crawl.sh process-stage2 --provider openai
./crawl.sh process-stage2 --provider deepseek
```

### Advanced Features

#### Direct S3 Access

```bash
# List Stage 1 raw videos
aws s3 ls s3://your-bucket/raw/new/

# List Stage 2 extractions
aws s3 ls s3://your-bucket/stage2-extracted/new/

# Download specific video data
aws s3 cp s3://your-bucket/raw/new/youtube_video_abc123.jsonl ./

# Download extracted entities
aws s3 cp s3://your-bucket/stage2-extracted/new/youtube_video_abc123_extracted.jsonl ./

# View sample with jq
cat youtube_video_abc123_extracted.jsonl | jq '.entities[] | select(.entity_type == "restaurant")'
```

#### Team Workflow

All data is stored in S3 only (no local data files). This ensures:
- **Single source of truth** across team members
- **Automatic deduplication** prevents duplicate work
- **No git conflicts** from data files

**Example Team Workflow:**
```bash
# Developer A
./crawl.sh youtube --input urls.txt
# Crawls 100 videos, uploads to S3

# Developer B (same day, different machine)
git pull
./crawl.sh youtube --input urls.txt
# ✅ Automatically skips the 100 videos A already crawled
# Only processes new videos
```

#### Monitoring Logs

```bash
# Application logs
tail -f logs/app_*.log

# Error logs only
tail -f logs/errors_*.log

# Crawler logs
tail -f logs/crawler_*.log

# Stage 2 processing logs
tail -f logs/stage2_*.log
```

#### Performance Tuning

**Stage 1 (Crawling):**
- Bottleneck: Whisper transcription (CPU-bound)
- Solution: Use GPU-enabled machine or cloud (Google Colab)
- Alternative: Switch to smaller Whisper model ("tiny" or "base")

**Stage 2 (Extraction):**
- Bottleneck: LLM API latency
- Solution: Already optimized (parallel processing in batches)
- Alternative: Use faster model (trade-off: lower quality)

---

## Future Roadmap

### ✅ Stages 1-5: Complete

All core pipeline stages are now fully implemented and production-ready:
- ✅ Stage 1: YouTube video crawling & transcription
- ✅ Stage 2: LLM entity extraction (Gemini/OpenAI/DeepSeek)
- ✅ Stage 3: Deduplication, canonicalization & geocoding
- ✅ Stage 4: Vector embeddings & ChromaDB indexing
- ✅ Stage 5: RAG itinerary generation with natural language queries

### Stage 6: REST API & Web Interface (Planned)

**Goal:** Build production API and web UI for public access

**Planned Tasks:**
- REST API with FastAPI
- Public endpoints:
  - `/generate-itinerary` - Generate from natural language
  - `/search-entities` - Semantic entity search
  - `/destinations` - List available destinations
  - `/cost-estimate` - Estimate trip costs
- Authentication & rate limiting
- Web UI for itinerary generation
- User accounts & saved itineraries
- Share itinerary links

**Estimated Effort:** 3-4 weeks

---

## Known Issues & Limitations

### Current Issues

1. **YouTube Bot Detection**
   - ✅ **MOSTLY FIXED** - Uses browser cookies
   - Some videos may still fail if YouTube is aggressive
   - Requires being logged into YouTube in browser

2. **Processing Time**
   - Stage 1: 2-4 minutes per video (CPU-based Whisper)
   - Stage 2: 15-20 seconds per video (LLM API)
   - Total: 2-5 minutes per video end-to-end

3. **Entity Type Validation Warnings**
   - LLMs sometimes return non-standard entity types
   - Examples: "transport" instead of "transportation", "food" instead of "restaurant"
   - ~10-15 entities per video fail validation (minor issue)
   - Can be fixed with prompt refinement

### Limitations

- ✅ Stages 3-5 not implemented (normalization, embeddings, search)
- ✅ CPU-based transcription slower than GPU
- ✅ No video content analysis (only audio/transcript)
- ✅ YouTube API quota limits (10,000 units/day = ~3,000 videos/day)
- ✅ LLM API costs (though minimized with Gemini)

---

## Project Structure

```
TravelAI/
│
├── cli/                          # Command-line interfaces
│   ├── crawl.py                  # Stage 1: YouTube crawler CLI
│   ├── process_stage2.py         # Stage 2: Entity extraction CLI
│   ├── tracking.py               # Pipeline monitoring CLI
│   └── audit_s3.py               # S3 data audit CLI
│
├── src/                          # Core application code
│   ├── crawlers/
│   │   └── youtube.py            # YouTube crawling logic
│   ├── processors/
│   │   ├── stage2_extractor.py   # Entity extraction logic
│   │   └── extraction_prompts.py # LLM prompt templates
│   ├── storage/
│   │   └── s3.py                 # S3 storage interface
│   └── utils/
│       ├── metadata_tracker.py   # Pipeline state tracking
│       ├── llm_client.py         # Multi-LLM client
│       ├── schemas.py            # Pydantic data models
│       ├── config.py             # Configuration loader
│       ├── logging.py            # Logging setup
│       └── content_id.py         # Content ID utilities
│
├── tests/                        # Unit tests
│   ├── test_stage1.py
│   └── test_stage2.py
│
├── .env                          # Environment variables (not in git)
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── crawl.sh                      # Helper script (sets PYTHONPATH)
├── setup.sh                      # Automated setup script
├── README.md                     # This file
└── COMMANDS.md                   # Complete command reference
```

### Important Files

**Configuration:**
- `.env` - AWS credentials, API keys (keep private!)
- `.env.example` - Template for creating `.env`

**Main Entry Points:**
- `crawl.sh` - Helper script for all CLI commands
- `cli/crawl.py` - Stage 1 crawler
- `cli/process_stage2.py` - Stage 2 processor
- `cli/tracking.py` - Monitoring tools

**Core Logic:**
- `src/crawlers/youtube.py` - YouTube video crawling
- `src/processors/stage2_extractor.py` - Entity extraction
- `src/storage/s3.py` - S3 operations
- `src/utils/metadata_tracker.py` - Pipeline state management

**Documentation:**
- `README.md` - This comprehensive guide
- `COMMANDS.md` - Complete CLI command reference

---

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_stage2.py

# Run with coverage
pytest --cov=src tests/

# Test with sample URLs
cat > test_urls.txt << EOF
https://www.youtube.com/watch?v=UEDeptPVNQA
https://www.youtube.com/watch?v=8m8ReerO060
EOF

./crawl.sh youtube --input test_urls.txt --limit 2
./crawl.sh process-stage2 --limit 2
./crawl.sh status
```

---

## Contributing

This is a team project. When contributing:

1. **Pull latest changes** before starting work
```bash
git pull origin main
```

2. **Create feature branch**
```bash
git checkout -b feature/your-feature-name
```

3. **Make changes and test**
```bash
pytest tests/
./crawl.sh youtube --input test_urls.txt --limit 2
```

4. **Commit with clear messages**
```bash
git add .
git commit -m "Add: description of changes"
```

5. **Push and create PR**
```bash
git push origin feature/your-feature-name
```

---

## License

MIT License - See LICENSE file for details

---

## Summary

**TravelAI** is a production-ready pipeline for extracting structured travel intelligence from YouTube videos and generating personalized itineraries:

✅ **Stages 1-5 Complete:**
- YouTube video crawling with Whisper transcription
- LLM-powered entity extraction (Gemini/OpenAI/DeepSeek)
- Deduplication, canonicalization & geocoding (FREE Nominatim + Google Maps fallback)
- Vector embeddings & ChromaDB indexing (FREE local model)
- RAG itinerary generation from natural language queries
- S3-only storage architecture
- Full end-to-end metadata tracking
- Comprehensive CLI tools for monitoring, semantic search, and itinerary generation

📦 **Current Scale:**
- 117 videos processed through all 5 stages
- ~5,000+ raw entities extracted
- ~1,200+ canonical entities created (after deduplication)
- ~13,000+ vector embeddings indexed (entity + profile + experience levels)
- Total pipeline cost: ~$0.30 for all data processing (mostly FREE)
- Itinerary generation: ~$0.01-0.02 per query
- Ready to scale to 100,000+ entities and unlimited itineraries

🎯 **Next Steps:**
- Stage 6: REST API and web interface for public access

For detailed command reference, see [COMMANDS.md](COMMANDS.md).

For questions or issues, please open a GitHub issue or contact the team.
