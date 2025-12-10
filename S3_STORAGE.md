# S3 Storage Structure Documentation

This document describes the complete S3 bucket structure for the TravelAI project, including directory organization, file formats, and data schemas for all pipeline stages.

## Table of Contents
1. [Bucket Overview](#bucket-overview)
2. [Directory Tree Structure](#directory-tree-structure)
3. [Stage 1: Raw YouTube Data](#stage-1-raw-youtube-data)
4. [Stage 2: Entity Extraction](#stage-2-entity-extraction)
5. [Stage 3: Canonical Entities](#stage-3-canonical-entities)
6. [Metadata Tracking](#metadata-tracking)
7. [File Format Examples](#file-format-examples)

---

## Bucket Overview

**Bucket Name**: `travel-ai-data-divyansh-2025` (configured in `.env`)
**Region**: `us-east-1`
**Purpose**: Store all YouTube travel content and processed entity data across pipeline stages

---

## Directory Tree Structure

```
s3://travel-ai-data-divyansh-2025/
│
├── raw/                                    # Stage 1: Raw YouTube data
│   └── youtube/
│       ├── videos/                         # Video metadata batches
│       │   └── YYYY-MM/
│       │       └── batch_YYYYMMDD_HHMMSS.jsonl
│       ├── transcripts/                    # Whisper transcriptions
│       │   └── youtube_video_{VIDEO_ID}_transcript.json
│       └── audio/                          # Downloaded audio files (optional)
│           └── youtube_video_{VIDEO_ID}.mp3
│
├── stage2-extracted/                       # Stage 2: LLM entity extraction
│   ├── new/                                # Newly extracted entities (ready for Stage 3)
│   │   └── youtube_video_{VIDEO_ID}_extracted.jsonl
│   └── stage3_extracted/                   # Processed by Stage 3 (archived)
│       └── youtube_video_{VIDEO_ID}_extracted.jsonl
│
├── stage3-canonical/                       # Stage 3: Deduplicated canonical entities
│   ├── new/                                # Current canonical entities
│   │   ├── entities_all_{YYYYMMDD}.jsonl  # All entity types combined
│   │   ├── entities_by_type_{TYPE}_{YYYYMMDD}.jsonl  # Entities grouped by type
│   │   └── metadata/
│   │       ├── deduplication_stats_{YYYYMMDD}.json
│   │       ├── geocoding_stats_{YYYYMMDD}.json
│   │       ├── consensus_stats_{YYYYMMDD}.json
│   │       └── qa_report_{YYYYMMDD_HHMMSS}.json
│   └── archive/                            # Historical snapshots (optional)
│       └── YYYY-MM-DD/
│
└── metadata/                               # Pipeline metadata & tracking
    └── processing_status.jsonl             # Content processing tracker
```

---

## Stage 1: Raw YouTube Data

### Purpose
Store raw YouTube video metadata, transcripts, and audio files from the YouTube Data API and Whisper transcription.

### Directory: `raw/youtube/`

#### 1.1 Video Metadata Batches
**Path**: `raw/youtube/videos/YYYY-MM/batch_YYYYMMDD_HHMMSS.jsonl`

**Format**: JSONL (one JSON object per line)

**Content**: Batch of YouTube videos discovered via API search

**Schema**:
```json
{
  "source_id": "dQw4w9WgXcQ",           // YouTube video ID
  "source_type": "youtube",             // Always "youtube"
  "title": "Amazing Thailand Travel Guide",
  "channel_id": "UCxxxxxxxxxxxxx",
  "channel_title": "Travel Vlogger",
  "published_at": "2024-11-15T10:30:00Z",
  "duration": "PT15M30S",               // ISO 8601 duration format
  "view_count": 125000,
  "like_count": 5200,
  "comment_count": 340,
  "description": "Full video description...",
  "tags": ["thailand", "travel", "bangkok"],
  "default_language": "en",
  "crawled_at": "2024-12-09T12:00:00Z"  // When we discovered it
}
```

**Key Fields**:
- `source_id`: Unique YouTube video ID (11 characters)
- `duration`: ISO 8601 format (PT15M30S = 15 minutes 30 seconds)
- `crawled_at`: Timestamp when video was added to our database

#### 1.2 Transcripts
**Path**: `raw/youtube/transcripts/youtube_video_{VIDEO_ID}_transcript.json`

**Format**: JSON

**Content**: Whisper-generated transcript with timestamps

**Schema**:
```json
{
  "video_id": "dQw4w9WgXcQ",
  "language": "en",
  "transcript": "Full transcript text...",
  "segments": [
    {
      "id": 0,
      "start": 0.0,              // Start time in seconds
      "end": 5.24,               // End time in seconds
      "text": "Welcome to Thailand!"
    }
  ],
  "whisper_model": "base",       // Whisper model used
  "transcribed_at": "2024-12-09T12:05:00Z"
}
```

**Key Fields**:
- `segments`: Array of timestamped transcript segments
- `start/end`: Time in seconds (float)
- `whisper_model`: Whisper model version (tiny/base/small/medium/large)

#### 1.3 Audio Files (Optional)
**Path**: `raw/youtube/audio/youtube_video_{VIDEO_ID}.mp3`

**Format**: MP3 audio file

**Content**: Downloaded audio extracted from YouTube video (used for Whisper transcription, can be deleted after processing)

---

## Stage 2: Entity Extraction

### Purpose
Store entities extracted from transcripts using LLM (OpenAI/DeepSeek/Gemini).

### Directory: `stage2-extracted/`

#### 2.1 Newly Extracted Files
**Path**: `stage2-extracted/new/youtube_video_{VIDEO_ID}_extracted.jsonl`

**Format**: JSON (single object, not JSONL)

**Content**: Extracted travel entities from one video

**Schema**:
```json
{
  "content_id": "youtube_dQw4w9WgXcQ",    // Prefixed with "youtube_"
  "source_id": "dQw4w9WgXcQ",             // Raw video ID
  "source_type": "youtube",
  "language": "en",
  "traveler_profile": {
    "traveler_type": "solo",              // solo, couple, family, group
    "budget_tier": "budget",              // budget, mid-range, luxury
    "travel_style": ["adventure", "cultural", "backpacker"]
  },
  "entities": [
    {
      "entity_name": "Wat Pho",
      "entity_type": "attraction",        // attraction, destination, hotel, activity, restaurant, shopping, transportation
      "location": "Bangkok, Thailand",
      "experience": "Amazing temple with reclining Buddha...",
      "keywords": ["temple", "cultural", "historic"],
      "travel_style": ["cultural", "sightseeing"],
      "cost_mentioned": "200 baht entrance fee",
      "season_mentioned": "dry_season"
    }
  ],
  "model_used": "deepseek-chat",          // LLM model name
  "cost_usd": 0.0012,                     // Extraction cost
  "tokens_used": {
    "input": 850,
    "output": 420,
    "total": 1270
  },
  "processed_at": "2024-12-09T12:10:00Z"
}
```

**Key Fields**:
- `content_id`: Standardized ID with "youtube_" prefix (used for metadata tracking)
- `source_id`: Raw YouTube video ID without prefix
- `traveler_profile`: Overall profile classification for the video creator
- `entities`: Array of extracted travel entities
- `entity_type`: One of 7 types (attraction, destination, hotel, activity, restaurant, shopping, transportation)
- `travel_style`: Can be multiple styles per entity
- `cost_mentioned`: Free-form text mentioning costs
- `season_mentioned`: When to visit (dry_season, rainy_season, peak_season, off_season)

#### 2.2 Processed Files
**Path**: `stage2-extracted/stage3_extracted/youtube_video_{VIDEO_ID}_extracted.jsonl`

**Format**: Same as above

**Content**: Files that have been processed by Stage 3 (moved from `new/` folder)

**Note**: These files are archived after Stage 3 processing completes. Can be moved back to `new/` using `reset-stage3` command.

---

## Stage 3: Canonical Entities

### Purpose
Store deduplicated, geocoded, and normalized canonical entities with consensus data.

### Directory: `stage3-canonical/new/`

#### 3.1 All Entities File
**Path**: `stage3-canonical/new/entities_all_{YYYYMMDD}.jsonl`

**Format**: JSONL (one canonical entity per line)

**Content**: All deduplicated entities across all types

**Schema**:
```json
{
  "entity_id": "attraction_bangkok_001",   // Unique ID: {type}_{city}_{sequence}
  "canonical_name": "Wat Pho",             // Chosen canonical name
  "aliases": ["Wat Pho Temple", "Temple of Reclining Buddha"],
  "entity_type": "attraction",
  "location": "Bangkok, Thailand",         // Original location string
  "normalized_location": "bangkok thailand", // Normalized for matching
  "city": "Bangkok",                       // Extracted city
  "country": "Thailand",                   // Extracted country
  "coordinates": {
    "lat": 13.7465,
    "lon": 100.4925,
    "provider": "google",                  // "nominatim" or "google"
    "confidence": "high"                   // high, medium, low
  },
  "attributes": {
    "keywords": ["temple", "cultural", "historic", "buddha"],
    "travel_style": ["cultural", "sightseeing", "religious"],
    "cost_mentioned": "budget-friendly",
    "season_mentioned": ["dry_season"]
  },
  "experiences": [
    {
      "experience": "Amazing temple with huge reclining Buddha...",
      "video_id": "youtube_dQw4w9WgXcQ",  // Source video
      "source_video_id": "dQw4w9WgXcQ",  // Raw ID for reference
      "traveler_profile": {
        "traveler_type": "solo",
        "budget_tier": "budget",
        "travel_style": ["cultural", "backpacker"]
      },
      "language": "en",
      "processed_at": "2024-12-09T12:10:00Z"
    }
  ],
  "consensus": {
    "avg_rating": 4.5,                     // Inferred from sentiment (1-5 scale)
    "mention_count": 3,                    // Number of unique videos mentioning this
    "themes": ["cultural", "historic", "buddhist", "architecture"],
    "profile_metrics": {
      "solo_budget_cultural": {
        "mention_count": 2,
        "avg_rating": 4.5,
        "sentiment_dist": {"positive": 2, "neutral": 0, "negative": 0},
        "common_themes": ["temple", "reclining buddha"],
        "avg_cost": 200.0,                 // Average cost in THB
        "confidence_score": 0.2            // 0-1, based on mention count
      }
    },
    "best_for": ["solo_budget_cultural", "couple_midrange_cultural"],
    "not_recommended_for": [],
    "cost_info": {
      "overall": {
        "min": 200.0,
        "max": 200.0,
        "avg": 200.0,
        "currency": "THB",
        "count": 3
      },
      "mentions": ["200 baht", "200 THB"]
    },
    "sentiment_distribution": {
      "positive": 15,
      "neutral": 3,
      "negative": 0,
      "mixed": 1
    }
  },
  "source_video_ids": ["dQw4w9WgXcQ", "abc123xyz", "def456ghi"],
  "total_mentions": 3,                     // Total entities merged (duplicates)
  "provenance": {
    "canonical_name_selection": {
      "canonical_name": "Wat Pho",
      "reasoning": "Most frequent (3 occurrences)",
      "frequency": 3,
      "alternatives": ["Wat Pho Temple"]
    },
    "entities_merged": 3,
    "merge_method": "stage3_deduplication",
    "original_entity_ids": ["dQw4w9WgXcQ", "abc123xyz", "def456ghi"]
  }
}
```

**Key Fields**:
- `entity_id`: Unique identifier format: `{entity_type}_{normalized_city}_{sequence:03d}`
- `canonical_name`: The "winning" name chosen from all variants (most frequent)
- `aliases`: All other name variants found for this entity
- `normalized_location`: Lowercase, no punctuation (used for deduplication matching)
- `coordinates.provider`:
  - `"nominatim"`: Free OpenStreetMap geocoding (50% of results)
  - `"google"`: Google Maps API geocoding (50% of results, more accurate)
- `consensus.avg_rating`: Calculated from sentiment analysis (1-5 scale)
- `consensus.mention_count`: Count of unique videos (experiences count)
- `consensus.profile_metrics`: Breakdown by traveler profile buckets
- `consensus.best_for`: Profiles with avg_rating >= 4.0 and >= 2 mentions
- `consensus.themes`: Common keywords extracted from experiences (LLM or keyword-based)
- `total_mentions`: Number of duplicate entities merged (indicates popularity)
- `provenance`: Audit trail showing how canonical entity was created

#### 3.2 Entities by Type
**Path**: `stage3-canonical/new/entities_by_type_{TYPE}_{YYYYMMDD}.jsonl`

**Format**: JSONL

**Content**: Canonical entities filtered by entity type

**Types**: attraction, destination, hotel, activity, restaurant, shopping, transportation

**Schema**: Same as `entities_all` but filtered

**Example**: `entities_by_type_attraction_20241209.jsonl` contains only attractions

#### 3.3 Statistics Files
**Path**: `stage3-canonical/new/metadata/`

##### Deduplication Stats
**File**: `deduplication_stats_{YYYYMMDD}.json`

**Content**: Statistics about deduplication process

```json
{
  "total_stage2_entities": 1250,
  "total_canonical_entities": 450,
  "deduplication_rate": 0.64,          // 64% reduction
  "by_type": {
    "attraction": {
      "stage2_count": 400,
      "canonical_count": 120,
      "dedup_rate": 0.70
    }
  },
  "avg_entities_per_canonical": 2.78,
  "singletons": 280,                   // Entities with no duplicates
  "duplicates": 170,                   // Entities with 2+ mentions
  "max_duplicates": 15                 // Most popular entity mention count
}
```

##### Geocoding Stats
**File**: `geocoding_stats_{YYYYMMDD}.json`

**Content**: Geocoding success rates and provider usage

```json
{
  "total_entities": 450,
  "geocoded": 445,
  "not_geocoded": 5,
  "success_rate": 0.989,
  "by_provider": {
    "nominatim": {
      "attempted": 450,
      "successful": 220,
      "failed": 230,
      "success_rate": 0.489
    },
    "google": {
      "attempted": 230,
      "successful": 225,
      "failed": 5,
      "success_rate": 0.978
    }
  },
  "cost_usd": 0.115,                  // Google Maps API cost
  "fallback_rate": 0.511              // % that required Google fallback
}
```

##### Consensus Stats
**File**: `consensus_stats_{YYYYMMDD}.json`

**Content**: Consensus calculation statistics

```json
{
  "total_entities": 450,
  "with_consensus": 450,
  "avg_mention_count": 2.78,
  "avg_rating": 4.2,
  "entities_by_rating": {
    "5": 120,
    "4": 200,
    "3": 100,
    "2": 25,
    "1": 5
  },
  "profile_distribution": {
    "solo_budget_cultural": 85,
    "couple_midrange_romantic": 62
  },
  "themes_extracted": 2500,
  "llm_theme_extraction_cost": 0.025
}
```

##### QA Validation Report
**File**: `qa_report_{YYYYMMDD_HHMMSS}.json`

**Content**: Validation results from `validate-stage3` command

```json
{
  "generated_at": "2024-12-09T17:11:33Z",
  "total_entities": 450,
  "validation_results": {
    "completeness": {
      "passed": true,
      "stats": {
        "completion_rate": 100.0,
        "missing_entity_id": 0,
        "missing_canonical_name": 0
      },
      "issues": []
    },
    "deduplication": {
      "passed": true,
      "stats": {
        "suspicious_deduplication_count": 2
      },
      "suspicious": [
        {
          "entity_id": "attraction_bangkok_042",
          "issue": "Too many duplicates (25 merged)",
          "details": "May indicate overly aggressive matching"
        }
      ]
    },
    "geolocation": {
      "passed": true,
      "stats": {
        "geocoding_success_rate": 98.9,
        "out_of_bounds": 2
      },
      "out_of_bounds": [
        {
          "entity_id": "attraction_unknown_015",
          "coordinates": {"lat": 91.5, "lon": 200.0},
          "issue": "Invalid coordinates"
        }
      ]
    },
    "consensus": {
      "passed": false,
      "issues": [
        {
          "entity_id": "destination_bangkok_005",
          "issue": "mention_count mismatch",
          "expected": 3,
          "actual": null
        }
      ]
    },
    "provenance": {
      "passed": true,
      "stats": {
        "orphaned_entities": 0,
        "provenance_verified": 450
      }
    }
  },
  "summary": {
    "all_validations_passed": false,
    "validations_run": 5,
    "validations_passed": 4,
    "validations_failed": 1
  },
  "recommendations": [
    {
      "category": "consensus",
      "priority": "high",
      "message": "Fix consensus calculation logic",
      "action": "Ensure mention_count is properly calculated"
    }
  ]
}
```

---

## Metadata Tracking

### Purpose
Track processing status of all content across pipeline stages.

### File: `metadata/processing_status.jsonl`

**Format**: JSONL (one content item per line)

**Content**: Processing state for each YouTube video

**Schema**:
```json
{
  "content_id": "youtube_dQw4w9WgXcQ",
  "source_type": "youtube",
  "source_id": "dQw4w9WgXcQ",
  "stages": {
    "stage_1_crawl": {
      "status": "completed",
      "started_at": "2024-12-09T12:00:00Z",
      "completed_at": "2024-12-09T12:01:30Z",
      "duration_seconds": 90.0,
      "s3_paths": [
        "s3://.../raw/youtube/transcripts/youtube_video_dQw4w9WgXcQ_transcript.json"
      ],
      "retry_count": 0,
      "error": null
    },
    "stage_2_extract": {
      "status": "completed",
      "started_at": "2024-12-09T12:05:00Z",
      "completed_at": "2024-12-09T12:10:00Z",
      "duration_seconds": 300.0,
      "s3_paths": [
        "s3://.../stage2-extracted/new/youtube_video_dQw4w9WgXcQ_extracted.jsonl"
      ],
      "metadata": {
        "entities_extracted": 15,
        "model_used": "deepseek-chat",
        "cost_usd": 0.0012
      },
      "retry_count": 0,
      "error": null
    },
    "stage_3_deduplicate": {
      "status": "completed",
      "started_at": "2024-12-09T13:00:00Z",
      "completed_at": "2024-12-09T13:02:00Z",
      "duration_seconds": 120.0,
      "s3_paths": [
        "s3://.../stage3-canonical/entities_all_20241209.jsonl"
      ],
      "metadata": {
        "canonical_entity_ids": [
          "attraction_bangkok_001",
          "destination_bangkok_005"
        ],
        "total_entities_contributed": 15,
        "deduplication_rate": 0.65
      },
      "retry_count": 0,
      "error": null
    }
  },
  "created_at": "2024-12-09T12:00:00Z",
  "updated_at": "2024-12-09T13:02:00Z"
}
```

**Key Fields**:
- `content_id`: Standardized ID with "youtube_" prefix
- `stages`: Dict of all pipeline stages
- `status`: "pending", "in_progress", "completed", "failed"
- `duration_seconds`: Time taken to process (null if no start time)
- `s3_paths`: Output files created by this stage
- `metadata`: Stage-specific information (varies by stage)
- `retry_count`: Number of retry attempts (incremented on failure)

**Stage Names**:
- `stage_1_crawl`: YouTube data collection + transcription
- `stage_2_extract`: LLM entity extraction
- `stage_3_deduplicate`: Deduplication, canonicalization, geocoding, consensus

---

## File Format Examples

### Example 1: Stage 2 Extracted File
**File**: `stage2-extracted/new/youtube_video_abc123_extracted.jsonl`

```json
{
  "content_id": "youtube_abc123",
  "source_id": "abc123",
  "source_type": "youtube",
  "language": "en",
  "traveler_profile": {
    "traveler_type": "solo",
    "budget_tier": "budget",
    "travel_style": ["adventure", "backpacker"]
  },
  "entities": [
    {
      "entity_name": "Khao San Road",
      "entity_type": "destination",
      "location": "Bangkok, Thailand",
      "experience": "Famous backpacker street with cheap hostels, street food, and nightlife",
      "keywords": ["backpacker", "nightlife", "street food", "hostels"],
      "travel_style": ["party", "social", "backpacker"],
      "cost_mentioned": "Very cheap accommodation from 200-500 baht per night",
      "season_mentioned": null
    }
  ],
  "model_used": "deepseek-chat",
  "cost_usd": 0.0008,
  "tokens_used": {"input": 650, "output": 280, "total": 930},
  "processed_at": "2024-12-09T12:15:00Z"
}
```

### Example 2: Stage 3 Canonical Entity
**File**: `stage3-canonical/new/entities_all_20241209.jsonl` (one line)

```json
{"entity_id":"destination_bangkok_001","canonical_name":"Khao San Road","aliases":["Khaosan Road","Khao San","Backpacker Street"],"entity_type":"destination","location":"Bangkok, Thailand","normalized_location":"bangkok thailand","city":"Bangkok","country":"Thailand","coordinates":{"lat":13.7589,"lon":100.4978,"provider":"google","confidence":"high"},"attributes":{"keywords":["backpacker","nightlife","street food","party","hostels"],"travel_style":["party","social","backpacker"],"cost_mentioned":"budget-friendly","season_mentioned":[]},"experiences":[{"experience":"Famous backpacker street with cheap hostels...","video_id":"youtube_abc123","source_video_id":"abc123","traveler_profile":{"traveler_type":"solo","budget_tier":"budget","travel_style":["adventure","backpacker"]},"language":"en","processed_at":"2024-12-09T12:15:00Z"}],"consensus":{"avg_rating":4.8,"mention_count":5,"themes":["backpacker","nightlife","party","social","budget"],"profile_metrics":{"solo_budget_party":{"mention_count":3,"avg_rating":5.0,"sentiment_dist":{"positive":3,"neutral":0},"common_themes":["party","nightlife"],"avg_cost":350.0,"confidence_score":0.3}},"best_for":["solo_budget_party","backpacker_social"],"not_recommended_for":[],"cost_info":{"overall":{"min":200.0,"max":500.0,"avg":350.0,"currency":"THB","count":5}},"sentiment_distribution":{"positive":5,"neutral":0,"negative":0,"mixed":0}},"source_video_ids":["abc123","def456","ghi789","jkl012","mno345"],"total_mentions":5,"provenance":{"canonical_name_selection":{"canonical_name":"Khao San Road","reasoning":"Most frequent (5 occurrences)","frequency":5,"alternatives":["Khaosan Road","Khao San"]},"entities_merged":5,"merge_method":"stage3_deduplication"}}
```

---

## Notes for Developers

### File Naming Conventions
- **Video IDs**: Always use format `youtube_video_{VIDEO_ID}` for file names
- **Content IDs**: Use `youtube_{VIDEO_ID}` for metadata tracking
- **Dates**: Use `YYYYMMDD` for dates, `YYYYMMDD_HHMMSS` for timestamps
- **Entity IDs**: Format `{type}_{city}_{sequence:03d}` (e.g., `attraction_bangkok_001`)

### JSONL vs JSON
- **JSONL**: Used for files with multiple records (one JSON per line)
  - Example: Video batches, canonical entities
  - Allows streaming processing without loading entire file
- **JSON**: Used for single-record files
  - Example: Transcripts, Stage 2 extracts, statistics
  - Easier to read and validate

### S3 Operations
- **Read**: Use `S3Storage.download_file()` or `s3_client.get_object()`
- **Write**: Use `S3Storage.upload_file()` or `s3_client.put_object()`
- **Move**: Copy to new location, then delete source
- **List**: Use `s3_client.list_objects_v2()` with prefix

### Cost Tracking
- Stage 2 LLM costs are tracked per video in `cost_usd` field
- Stage 3 geocoding costs are in `geocoding_stats` metadata
- Total pipeline cost = Sum of all stage costs

### Data Retention
- Raw data (Stage 1): Keep indefinitely for reprocessing
- Extracted data (Stage 2): Archive after Stage 3 processing
- Canonical data (Stage 3): Keep latest, optionally snapshot to `archive/`
- Metadata: Keep latest processing status only

---

## Command Reference

### View S3 Data
```bash
# Audit S3 bucket
./crawl.sh audit

# Show specific entity
./crawl.sh show-entity attraction_bangkok_001

# Search entities
./crawl.sh search-entities "temple"
```

### Reset Stages
```bash
# Reset Stage 3 (moves files back to stage2-extracted/new/)
./crawl.sh reset-stage3 --all

# Reset Stage 2
./crawl.sh reset --content-id youtube_abc123 --stage stage_2_extract
```

### Export Data
```bash
# Use AWS CLI to download
aws s3 cp s3://travel-ai-data-divyansh-2025/stage3-canonical/new/entities_all_20241209.jsonl .

# Or use boto3 in Python
from src.storage.s3 import S3Storage
s3 = S3Storage()
content = s3.download_file('stage3-canonical/new/entities_all_20241209.jsonl')
```

---

**Last Updated**: December 9, 2024
**Version**: 1.0
**Maintainer**: TravelAI Team
