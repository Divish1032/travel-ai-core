# TravelAI - Project Status & Architecture

**Last Updated:** 2025-11-04
**Current Stage:** Stage 1 (YouTube Video Crawling) - ✅ **COMPLETE**
**Total Videos Processed:** 117+ videos
**S3 Storage:** travel-ai-data-divyansh-2025

---

## 🎯 Current Capabilities

### ✅ What Works Now (Stage 1 Complete)

1. **YouTube Video Crawling**
   - Crawls YouTube videos (regular videos + Shorts)
   - Extracts metadata (title, author, duration, views, likes, etc.)
   - Downloads audio and transcribes using Whisper AI
   - **Auto-detects language** (supports 99+ languages)
   - Stores everything in S3

2. **Automatic Deduplication**
   - Checks S3 before processing to avoid re-processing
   - Safe by default (no `--resume` flag needed)
   - `--force` flag available for intentional re-processing

3. **S3-Only Storage Architecture**
   - Single source of truth for team collaboration
   - No local data files (git-friendly)
   - Automatic metadata tracking

4. **Pipeline Tracking**
   - View processing status (`./crawl.sh status`)
   - Check stage details (`./crawl.sh stage stage_1_crawl`)
   - List failed videos (`./crawl.sh failed`)
   - Language distribution analysis (`./crawl.sh languages`)
   - Export to CSV (`./crawl.sh export data.csv`)

5. **Browser Cookie Support**
   - Bypasses YouTube bot detection
   - Uses Chrome/Firefox/Safari cookies for authentication

---

## 📊 S3 Data Architecture

### S3 Bucket Structure

```
s3://travel-ai-data-divyansh-2025/
│
├── raw/youtube/videos/YYYY-MM/
│   ├── batch_20251103_182033.jsonl    (115 videos)
│   ├── batch_20251103_203521.jsonl    (1 video)
│   └── batch_20251103_205016.jsonl    (6 videos)
│
└── metadata/
    ├── processing_status.jsonl         (Pipeline tracking)
    └── backups/
        └── processing_status_*.jsonl   (Auto backups)
```

### Path Logic

#### 1. Raw Video Data Path
**Format:** `raw/youtube/videos/YYYY-MM/batch_TIMESTAMP.jsonl`

**Example:** `raw/youtube/videos/2025-11/batch_20251103_182033.jsonl`

**Logic:**
- `raw/youtube/videos/` - Base path for YouTube video data
- `YYYY-MM/` - Year-Month partition (e.g., `2025-11/`)
- `batch_TIMESTAMP.jsonl` - Batch file with UTC timestamp

**Why this structure?**
- ✅ Time-based partitioning for easy data management
- ✅ One batch file per crawl session
- ✅ JSONL format (one JSON object per line) for streaming
- ✅ Scalable - won't have too many files in one folder

**Code Location:** `src/storage/s3.py:upload_jsonl()`

#### 2. Metadata Tracking Path
**Format:** `metadata/processing_status.jsonl`

**Single file** that tracks all content items across all pipeline stages.

**Why single file?**
- ✅ Centralized state management
- ✅ Fast loading (entire state in memory)
- ✅ Atomic updates (no partial state)
- ✅ Auto-backups before each update

**Code Location:** `src/utils/metadata_tracker.py`

---

## 📁 Raw Video Data Schema

### JSONL File Structure

Each line in `batch_*.jsonl` is a JSON object with this schema:

```json
{
  "source": "youtube",
  "source_id": "DR5GVH-rmdQ",
  "source_url": "https://youtube.com/watch?v=DR5GVH-rmdQ",
  "content_type": "vlog",
  "title": "The Perfect 7 Days Thailand Itinerary",
  "author": "Tripoto",
  "author_url": "https://youtube.com/channel/UCjOXlKzzxdZG6BhKCQtWKWQ",
  "published_date": "2024-01-21",
  "duration_seconds": 331,
  "language": "hi",
  "transcript": [
    {
      "text": "उन्भ ही लएकियोव exploding eating",
      "start": 0.0,
      "duration": 19.72
    },
    {
      "text": "अगे की जगा जाने वासे है...",
      "start": 19.72,
      "duration": 5.26
    }
  ],
  "metadata": {
    "view_count": 72247,
    "like_count": 823,
    "comment_count": 21,
    "tags": ["Thailand Travel", "Phuket", "Krabi"],
    "transcript_type": "whisper"
  },
  "provenance": {
    "can_redistribute": false,
    "attribution_required": true,
    "tos_version": "youtube_tos_2024"
  },
  "fetched_at": "2025-11-03T14:18:27.633472+00:00Z",
  "fetched_by": "crawler_v1_whisper"
}
```

### Key Fields Explained

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Always "youtube" for Stage 1 |
| `source_id` | string | YouTube video ID (e.g., "DR5GVH-rmdQ") |
| `source_url` | string | Full YouTube URL |
| `content_type` | string | "vlog" (default for travel videos) |
| `title` | string | Video title from YouTube |
| `author` | string | Channel name |
| `published_date` | string | ISO date (YYYY-MM-DD) |
| `duration_seconds` | int | Video length in seconds |
| **`language`** | **string** | **ISO 639-1 code (en, hi, es, etc.)** - Detected by Whisper |
| `transcript` | array | Transcript segments with timestamps |
| `metadata.transcript_type` | string | "whisper" (transcribed using Whisper AI) |
| `fetched_at` | string | ISO 8601 timestamp (UTC) |

---

## 📋 Metadata Tracking Schema

### Processing Status Structure

**File:** `metadata/processing_status.jsonl`

Each line tracks one video's processing status across all stages:

```json
{
  "content_id": "youtube_DR5GVH-rmdQ",
  "source": "youtube",
  "source_url": "https://youtube.com/watch?v=DR5GVH-rmdQ",
  "title": "The Perfect 7 Days Thailand Itinerary",
  "added_at": "2025-11-03T14:18:30.123456Z",
  "stages": {
    "stage_1_crawl": {
      "status": "complete",
      "started_at": "2025-11-03T14:18:30.123456Z",
      "completed_at": "2025-11-03T14:21:45.789012Z",
      "duration_seconds": 195.66,
      "s3_paths": [
        "s3://travel-ai-data-divyansh-2025/raw/youtube/videos/2025-11/batch_20251103_182033.jsonl"
      ],
      "metadata": {
        "video_id": "DR5GVH-rmdQ",
        "duration_seconds": 331,
        "transcript_segments": 25,
        "view_count": 72247,
        "language": "hi"
      },
      "error": null,
      "retry_count": 0
    },
    "stage_2_chunk": {
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "duration_seconds": null,
      "s3_paths": [],
      "metadata": {},
      "error": null,
      "retry_count": 0
    },
    "stage_3_extract": { "status": "pending", ... },
    "stage_4_normalize": { "status": "pending", ... },
    "stage_5_embed": { "status": "pending", ... }
  },
  "pipeline_status": "stage_2_pending",
  "last_updated": "2025-11-03T14:21:45.789012Z",
  "total_error_count": 0,
  "tags": []
}
```

### Pipeline Stages

| Stage | Status | Description |
|-------|--------|-------------|
| **stage_1_crawl** | ✅ **complete** | YouTube crawling (implemented) |
| **stage_2_chunk** | 🔜 pending | Transcript chunking (not implemented) |
| **stage_3_extract** | 🔜 pending | LLM information extraction (not implemented) |
| **stage_4_normalize** | 🔜 pending | Data normalization (not implemented) |
| **stage_5_embed** | 🔜 pending | Vector embeddings (not implemented) |

### Content ID Format

**Pattern:** `youtube_{VIDEO_ID}`

**Examples:**
- `youtube_DR5GVH-rmdQ`
- `youtube_dQw4w9WgXcQ`

**Logic:**
- Unique identifier across entire pipeline
- Easy to extract video ID: `content_id.replace('youtube_', '')`
- Consistent naming for deduplication

**Code Location:** `src/utils/content_id.py:generate_content_id()`

---

## 🔄 Data Flow & Processing Logic

### 1. Crawling Flow

```
URLs (urls.txt)
    ↓
Extract Video IDs
    ↓
Check S3 Metadata (deduplication)
    ↓
Skip if already processed
    ↓
For new videos:
    ↓
Fetch Metadata (YouTube Data API)
    ↓
Download Audio (yt-dlp + browser cookies)
    ↓
Transcribe Audio (Whisper AI)
    ↓
Detect Language (Whisper auto-detect)
    ↓
Build YouTubeVideo object
    ↓
Upload to S3 (batch_*.jsonl)
    ↓
Update MetadataTracker
    ↓
Save tracking to S3
```

**Code Locations:**
- Main flow: `cli/crawl.py:youtube()`
- Video processing: `src/crawlers/youtube.py:crawl_video()`
- Deduplication: `cli/crawl.py:load_crawled_video_ids_from_s3()`

### 2. Deduplication Logic

**How it works:**

1. **Load MetadataTracker** from S3
2. **Find all `stage_1_crawl: complete`** entries
3. **Extract video IDs** from content_ids
4. **Filter input URLs** - skip if video_id in already-crawled set
5. **Process only new videos**

**Code Location:** `cli/crawl.py:load_crawled_video_ids_from_s3()`

**Benefits:**
- ✅ Prevents duplicate processing
- ✅ Saves time and money (no re-transcription)
- ✅ Team-safe (S3 is single source of truth)

### 3. Metadata Update Flow

```
Video successfully crawled
    ↓
Generate content_id (youtube_VIDEO_ID)
    ↓
Check if content_id exists in tracker
    ↓
If new: Register content
    ↓
Mark stage_1_crawl as "started"
    ↓
Mark stage_1_crawl as "complete"
    ↓
Store metadata:
    - video_id
    - duration_seconds
    - transcript_segments count
    - view_count
    - language (NEW!)
    ↓
Store S3 path to raw JSONL
    ↓
Update pipeline_status to "stage_2_pending"
    ↓
Save to S3 (with auto-backup)
```

**Code Location:** `cli/crawl.py` lines 370-395

---

## 🛠️ Key Components

### 1. Storage Layer

**File:** `src/storage/s3.py`

**Key Functions:**
- `upload_jsonl()` - Upload video data batches
- `download_jsonl()` - Download JSONL files
- Auto-generates timestamped paths
- Handles AWS credentials from .env

### 2. Metadata Tracker

**File:** `src/utils/metadata_tracker.py`

**Key Functions:**
- `register_content()` - Add new video to tracking
- `start_stage()` - Mark stage as started
- `complete_stage()` - Mark stage as complete with metadata
- `save_to_s3()` - Persist tracking data (with auto-backup)
- `content_exists()` - Check if video already tracked

**In-Memory Cache:**
- Loads entire `processing_status.jsonl` into memory
- Fast lookups and updates
- Saves to S3 on modification

### 3. YouTube Crawler

**File:** `src/crawlers/youtube.py`

**Key Functions:**
- `extract_video_id()` - Parse video ID from URL (supports Shorts!)
- `fetch_video_metadata()` - Get metadata from YouTube Data API
- `download_audio()` - Download audio using yt-dlp + browser cookies
- `transcribe_audio()` - Transcribe using Whisper + detect language
- `fetch_transcript()` - Complete flow (download + transcribe)
- `crawl_video()` - Crawl single video (full pipeline)
- `crawl_videos()` - Crawl multiple videos with progress tracking

**Whisper Models:**
- Currently using: **"small"** model (244M params)
- Other options: tiny, base, medium, large
- Device: CPU (Mac) - can be GPU on Colab

### 4. CLI Tools

**File:** `cli/crawl.py`

**Commands:**
- `./crawl.sh youtube --input urls.txt` - Crawl videos
- `./crawl.sh youtube --input urls.txt --force` - Force re-process
- `./crawl.sh youtube --input urls.txt --limit 5` - Test mode

**File:** `cli/tracking.py`

**Commands:**
- `./crawl.sh status` - Pipeline overview
- `./crawl.sh stage stage_1_crawl` - Stage details
- `./crawl.sh failed` - List failed videos
- `./crawl.sh languages` - Language distribution
- `./crawl.sh export data.csv` - Export to CSV

---

## 📈 Current Statistics

**As of 2025-11-04:**

- **Total Videos Crawled:** 117
- **S3 Batches:** 3 batches
  - batch_20251103_182033.jsonl: 115 videos
  - batch_20251103_203521.jsonl: 1 video
  - batch_20251103_205016.jsonl: 6 videos
- **Languages Detected:** Multiple (check with `./crawl.sh languages`)
- **Storage Used:** ~XX MB (raw JSONL + metadata)

---

## 🚀 Next Steps (Future Stages)

### Stage 2: Transcript Chunking (Not Implemented)

**Goal:** Split long transcripts into semantic chunks for LLM processing

**Planned Data Path:** `processed/youtube/chunks/YYYY-MM/chunks_*.jsonl`

**Tasks:**
- Implement chunking strategy (token-based, semantic, sliding window)
- Maintain context across chunks
- Store chunk metadata (parent video, chunk index, etc.)

### Stage 3: Information Extraction (Not Implemented)

**Goal:** Extract travel information using LLMs (locations, activities, costs, tips)

**Planned Data Path:** `processed/youtube/extracted/YYYY-MM/extracted_*.jsonl`

**Tasks:**
- LLM integration (OpenAI/Anthropic)
- Prompt engineering for travel data
- Structured output (Pydantic schemas)
- Cost tracking for LLM API calls

### Stage 4: Data Normalization (Not Implemented)

**Goal:** Normalize extracted data into structured format

**Planned Data Path:** `processed/youtube/normalized/YYYY-MM/normalized_*.jsonl`

**Tasks:**
- Entity resolution (same location, different names)
- Currency normalization
- Date/time normalization
- Geocoding (location → coordinates)

### Stage 5: Vector Embeddings (Not Implemented)

**Goal:** Generate embeddings for semantic search

**Planned Data Path:** `processed/youtube/embeddings/YYYY-MM/embeddings_*.jsonl`

**Tasks:**
- Embedding model selection
- Generate embeddings for chunks/entities
- Vector database integration (Pinecone/Weaviate)
- Semantic search API

---

## 🐛 Known Issues & Limitations

### Current Issues

1. **YouTube Bot Detection**
   - ✅ **FIXED** - Now uses browser cookies (`--cookies-from-browser chrome`)
   - Some videos may still fail if YouTube is aggressive
   - Requires being logged into YouTube in browser

2. **Processing Time**
   - Average: 2-4 minutes per video (CPU-based Whisper)
   - Download: 30-60s
   - Transcription: 1-3 minutes
   - GPU would be 2-4x faster (not implemented)

3. **Language Detection**
   - Old videos (110+) had `language: "unknown"` bug
   - ✅ **FIXED** - New videos correctly detect language
   - ✅ Migration script available: `python migrate_languages.py`

### Limitations

- ✅ Stage 1 only (no LLM processing yet)
- ✅ CPU-based transcription (slower than GPU)
- ✅ No video content analysis (only audio/transcript)
- ✅ English-only metadata (YouTube API limitation)
- ✅ YouTube API quota limits (10,000 units/day)

---

## 📝 Important Files

### Configuration
- `.env` - AWS credentials, YouTube API key
- `.env.example` - Template for .env

### Main Code
- `cli/crawl.py` - Crawler CLI (370 lines)
- `cli/tracking.py` - Tracking CLI (707 lines)
- `src/crawlers/youtube.py` - YouTube crawler logic (650 lines)
- `src/storage/s3.py` - S3 storage layer (300 lines)
- `src/utils/metadata_tracker.py` - Pipeline tracking (400 lines)
- `src/utils/schemas.py` - Pydantic data models (200 lines)

### Utilities
- `crawl.sh` - Helper script (sets PYTHONPATH automatically)
- `migrate_languages.py` - One-time migration for old videos
- `validate_pipeline.py` - Pipeline health check

### Documentation
- `README.md` - Quick start guide
- `PROJECT_STATUS.md` - This file (current state & architecture)

---

## 🔧 Configuration

### Environment Variables (.env)

```bash
# AWS Configuration (Required)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=travel-ai-data-divyansh-2025

# YouTube API (Required)
YOUTUBE_API_KEY=your_youtube_api_key

# Optional
LOG_LEVEL=INFO
CRAWLER_RATE_LIMIT=2
MAX_RETRIES=3
```

### Browser Cookie Configuration

**File:** `src/crawlers/youtube.py:261`

```python
"--cookies-from-browser", "chrome",  # Change to: firefox, safari, edge
```

**Supported browsers:**
- Chrome (default)
- Firefox
- Safari (Mac only)
- Edge

---

## 📊 Monitoring & Debugging

### Check Pipeline Health

```bash
# Overall status
./crawl.sh status

# Language distribution
./crawl.sh languages

# Failed videos
./crawl.sh failed

# Stage 1 details
./crawl.sh stage stage_1_crawl

# Validate S3 consistency
python validate_pipeline.py
```

### View Logs

```bash
# Application logs
tail -f logs/app_*.log

# Error logs only
tail -f logs/errors_*.log

# Crawler logs
tail -f logs/crawler_*.log
```

### Direct S3 Access

```bash
# List batches
aws s3 ls s3://travel-ai-data-divyansh-2025/raw/youtube/videos/2025-11/

# Download metadata
aws s3 cp s3://travel-ai-data-divyansh-2025/metadata/processing_status.jsonl ./

# Download a batch
aws s3 cp s3://travel-ai-data-divyansh-2025/raw/youtube/videos/2025-11/batch_20251103_182033.jsonl ./

# View sample
head -n 1 batch_20251103_182033.jsonl | jq '.'
```

---

## 🎯 Summary

**TravelAI is currently at Stage 1** with a fully functional YouTube video crawler:

✅ **What's Working:**
- YouTube video + Shorts crawling
- Whisper-based transcription with auto language detection
- S3-only storage architecture
- Automatic deduplication
- Comprehensive tracking and monitoring
- Browser cookie support for bot detection bypass

📦 **Data Status:**
- 117+ videos successfully crawled and stored in S3
- All data validated and tracked
- Ready for Stage 2 processing

---

**For questions or issues, check README.md or contact the team.**
