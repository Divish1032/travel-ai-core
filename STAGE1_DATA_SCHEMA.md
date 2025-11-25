# Stage 1 Data Schema - Verified Structure

**Date:** 2025-11-04
**Sample File:** `s3://travel-ai-data-divyansh-2025/raw/youtube/videos/2025-11/batch_20251103_203521.jsonl`

## ✅ Verified Fields

### Video Metadata
```json
{
  "source": "youtube",
  "source_id": "tq6cVSO1EO0",
  "source_url": "https://youtube.com/watch?v=tq6cVSO1EO0",
  "content_type": "vlog",
  "title": "THAILAND perfect 6-9 Days ITINERARY...",
  "author": "Being Roamers",
  "author_url": "https://youtube.com/channel/UC8c-N2BdQWm6cz5VV9e7cNw",
  "published_date": "2024-11-17",
  "duration_seconds": 1619,
  "language": "hi"
}
```

### Transcript Structure
```json
"transcript": [
  {
    "text": "थाईलिंग जनगा प्लान गर रहो और भहुत दूँँने के बाद भी आपको थाईलिंग की परफ्रेक थाईलितनरी नी मिली",
    "start": 0.0,
    "duration": 5.32
  },
  {
    "text": "तो ये विडियो आपके लिए है",
    "start": 5.32,
    "duration": 1.92
  }
]
```

### Additional Metadata
```json
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
```

## Key Observations for Stage 2

### 1. Language Detection
- ✅ **Field exists**: `language: "hi"` (Hindi)
- Whisper auto-detects language
- Supports 99+ languages (ISO 639-1 codes)

### 2. Transcript Quality
- Each segment has `text`, `start`, `duration`
- Timestamps in seconds (float)
- Hindi text in Devanagari script (Unicode)
- Some transcription errors (expected with Whisper)

### 3. Video Length
- Sample video: 1619 seconds (~27 minutes)
- Transcript: 465+ segments
- Average segment: ~3.5 seconds

### 4. Content Type
- Currently hardcoded as `"vlog"`
- Should be inferred in Stage 2 based on content

## Stage 2 Requirements

Based on verified schema, Stage 2 needs to:

1. **Read from**: `raw/youtube/videos/YYYY-MM/batch_*.jsonl`
2. **Access fields**:
   - `source_id` (video ID)
   - `language` (for language-specific prompts)
   - `transcript` (array of segments)
   - `duration_seconds` (for context)
   - `title`, `tags` (additional context)

3. **Process**:
   - Combine transcript segments into coherent chunks
   - Send to LLM for extraction
   - Extract traveler profile + entities

4. **Output to**: `processed/youtube/extracted/YYYY-MM/extracted_*.jsonl`

## Metadata Tracker Structure

From `src/utils/metadata_tracker.py`:

```python
{
  "content_id": "youtube_tq6cVSO1EO0",
  "source": "youtube",
  "source_url": "https://youtube.com/watch?v=tq6cVSO1EO0",
  "title": "THAILAND perfect 6-9 Days ITINERARY...",
  "added_at": "2025-11-03T20:35:22Z",
  "stages": {
    "stage_1_crawl": {
      "status": "complete",
      "started_at": "2025-11-03T20:35:22Z",
      "completed_at": "2025-11-03T20:38:45Z",
      "duration_seconds": 203.0,
      "s3_paths": [
        "s3://travel-ai-data-divyansh-2025/raw/youtube/videos/2025-11/batch_20251103_203521.jsonl"
      ],
      "metadata": {
        "video_id": "tq6cVSO1EO0",
        "duration_seconds": 1619,
        "transcript_segments": 465,
        "view_count": 0,
        "language": "hi"
      },
      "error": null,
      "retry_count": 0
    },
    "stage_2_chunk": {
      "status": "pending",
      ...
    }
  },
  "pipeline_status": "stage_2_pending",
  "last_updated": "2025-11-03T20:38:45Z"
}
```

## Data Flow for Stage 2

1. **Input**: Query MetadataTracker for `pipeline_status: "stage_2_pending"`
2. **Load**: Download JSONL from `s3_paths` in stage_1_crawl
3. **Extract**: Process transcript with LLM
4. **Save**: Upload to new S3 path
5. **Update**: Mark stage_2_extract as complete in MetadataTracker
