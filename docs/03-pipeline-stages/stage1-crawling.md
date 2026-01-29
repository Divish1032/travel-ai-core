# Stage 1: YouTube Crawling

Stage 1 collects travel video content from YouTube and transcribes it into structured text for downstream processing.

**Implementation:** [`src/crawlers/youtube.py`](../../src/crawlers/youtube.py)

---

## Overview

### Purpose
Download YouTube travel videos, extract metadata, and transcribe audio to text using OpenAI Whisper.

### Inputs
- YouTube video URLs or channel IDs
- Optional filters (language, duration, limit)

### Outputs
- Video metadata (title, channel, views, duration, etc.)
- Full transcript with timestamps
- Detected language
- Quality scores

### Storage
- **S3 Path:** `s3://{bucket}/stage1_transcripts/{video_id}.json`
- **File Size:** ~15 KB per video

---

## Processing Pipeline

### 1. Video ID Extraction

**Function:** `extract_video_id(url)`

Supports multiple YouTube URL formats:
- `https://youtube.com/watch?v=VIDEO_ID`
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://youtube.com/embed/VIDEO_ID`
- `https://m.youtube.com/watch?v=VIDEO_ID`
- `https://youtube.com/shorts/VIDEO_ID` (YouTube Shorts)

**Example:**
```python
video_id = extract_video_id("https://youtube.com/watch?v=UEDeptPVNQA")
# Returns: "UEDeptPVNQA"
```

---

### 2. Metadata Fetching

**Function:** `fetch_video_metadata(video_id)`

Uses **YouTube Data API v3** to fetch comprehensive video metadata.

**Metadata Fields:**
- `video_id` - YouTube video ID
- `url` - Full YouTube URL
- `title` - Video title
- `author` - Channel name
- `channel_url` - Channel URL
- `duration_seconds` - Video duration in seconds
- `published_date` - Upload date (YYYY-MM-DD)
- `view_count` - Total views
- `like_count` - Total likes (NEW with official API!)
- `comment_count` - Total comments (NEW with official API!)
- `description` - Video description
- `keywords` - Tags/keywords

**API Key Required:**
- Set `YOUTUBE_API_KEY` in `.env`
- Get free API key from: https://console.cloud.google.com/apis/credentials
- Free tier: 10,000 units/day ≈ 3,000 videos/day

**Duration Parsing:**
YouTube returns duration in ISO 8601 format (e.g., `PT15M33S`), which is parsed to seconds:
- `PT15M33S` → 933 seconds
- `PT1H2M10S` → 3,730 seconds

**Error Handling:**
- **403 Forbidden:** API quota exceeded or invalid key
- **404 Not Found:** Video does not exist or is private
- **Other errors:** Network issues, API downtime

**Example Output:**
```json
{
  "video_id": "UEDeptPVNQA",
  "url": "https://youtube.com/watch?v=UEDeptPVNQA",
  "title": "BANGKOK Travel Guide 2024 | Best Places to Visit",
  "author": "Travel with Dave",
  "channel_url": "https://youtube.com/channel/UCJc4VuL2ynZhS1tn7ZqbLEg",
  "duration_seconds": 895,
  "published_date": "2024-08-15",
  "view_count": 125000,
  "like_count": 3200,
  "comment_count": 145,
  "description": "Exploring the best places to visit in Bangkok...",
  "keywords": ["Bangkok", "Thailand", "Travel Guide"]
}
```

---

### 3. Audio Download

**Function:** `download_audio(video_id, video_url)`

Uses **yt-dlp** (youtube-dl fork) to download audio.

**Key Features:**
- **Browser Cookie Support:** Handles age-restricted videos using Chrome cookies
- **Audio Format:** Downloads as MP3
- **User Agent:** Uses realistic browser user agent
- **No Playlists:** Downloads single video only
- **Timeout:** 5 minute timeout per download

**yt-dlp Command:**
```bash
yt-dlp \
  --cookies-from-browser chrome \
  --user-agent "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  -x --audio-format mp3 \
  -o /tmp/yt_audio_{video_id}.mp3 \
  --no-playlist \
  --quiet --progress \
  {video_url}
```

**Output:**
- Temporary MP3 file in `/tmp/yt_audio_{video_id}.mp3`
- File size: typically 5-20 MB for 10-minute video

**Error Handling:**
- Timeout after 5 minutes
- Logs download errors
- Returns `None` on failure (allows graceful skipping)

---

### 4. Transcription with Whisper

**Function:** `transcribe_audio(audio_file, video_id, model, use_thai_prompt, apply_corrections)`

Uses **OpenAI Whisper** for speech-to-text transcription.

**Whisper Model:**
- **Default:** `small` model (244M parameters)
- **Other options:** `tiny`, `base`, `medium`, `large`
- **Trade-off:** Speed vs. accuracy
- **Language Detection:** Automatic (supports 90+ languages)

**Model Sizes:**
| Model | Parameters | Speed | Quality | Use Case |
|-------|-----------|-------|---------|----------|
| tiny | 39M | Fastest | Lowest | Quick tests |
| base | 74M | Fast | Decent | Draft transcripts |
| **small** | 244M | Balanced | Good | **Default (recommended)** |
| medium | 769M | Slow | Better | High-quality needed |
| large | 1.5B | Slowest | Best | Professional use |

**Thai Place Name Optimization:**

TravelAI includes special handling for Thai place names, which Whisper often mis-transcribes:

1. **Whisper Priming:** Uses `initial_prompt` with common Thai place names
   - Example prompt includes: "Bangkok, Phuket, Chiang Mai, Pattaya, Krabi..."
   - Helps Whisper recognize these names correctly

2. **Post-Transcription Correction:** Applies dictionary-based corrections
   - **Dictionary Corrections:** Exact matches (e.g., "Pataya" → "Pattaya")
   - **Pattern Corrections:** Common patterns (e.g., "Bangkok Suvarnabhumi" spacing)
   - **Fuzzy Corrections:** Similarity matching (85% threshold)
   - **LLM Proofreading:** Disabled at Stage 1 (done in Stage 2 if needed)

**Transcription Options:**
```python
transcribe_options = {
    "verbose": False,
    "initial_prompt": get_whisper_thailand_prompt()  # Thai place names
}
result = model.transcribe(audio_file, **transcribe_options)
```

**Output Format:**
```python
[
  {
    "text": "Hey everyone, today we're exploring Bangkok...",
    "start": 0.0,      # seconds (float)
    "duration": 5.2    # seconds (float)
  },
  {
    "text": "We'll start at the Grand Palace, an absolute must-see.",
    "start": 5.2,
    "duration": 4.8
  }
]
```

**Detected Language:**
- Whisper auto-detects language
- Returns ISO 639-1 code (e.g., `en`, `hi`, `th`, `es`)

**Duration:**
- Typically 1-2 minutes for 10-minute video on CPU
- Faster with GPU (if available)

---

### 5. Data Assembly & Upload

**Function:** `YouTubeCrawler.crawl(video_url)`

Assembles final Stage 1 output and uploads to S3.

**Output Schema:**
```json
{
  "video_id": "youtube_UEDeptPVNQA",
  "url": "https://youtube.com/watch?v=UEDeptPVNQA",
  "title": "BANGKOK Travel Guide 2024",
  "channel": "Travel with Dave",
  "duration_seconds": 895,
  "view_count": 125000,
  "like_count": 3200,
  "comment_count": 145,
  "upload_date": "2024-08-15",
  "language": "en",
  "transcript": "Hey everyone, today we're exploring Bangkok...",
  "transcript_segments": [
    {
      "text": "Hey everyone, today we're exploring Bangkok...",
      "start": 0.0,
      "duration": 5.2
    }
  ],
  "quality_score": 0.87,
  "processing_timestamp": "2026-01-29T10:15:23Z",
  "provenance": {
    "source": "youtube",
    "crawl_date": "2026-01-29",
    "whisper_model": "small"
  }
}
```

**Quality Score Calculation:**
- Based on transcript confidence from Whisper
- Range: 0.0 - 1.0
- Typical values: 0.8 - 0.95 for clear audio
- Lower scores indicate poor audio quality or background noise

**S3 Upload:**
- Path: `stage1_transcripts/youtube_{video_id}.json`
- Format: JSON
- Size: ~15 KB per video

**Metadata Tracking:**
- Updates `metadata/processing_status.jsonl` with:
  - `video_id`
  - `stage1_status: "completed"`
  - `stage1_timestamp`

---

## CLI Usage

### Crawl from URLs

```bash
# Crawl single video
./crawl.sh youtube --input single_url.txt

# Crawl multiple videos
./crawl.sh youtube --input urls.txt --limit 10

# Crawl with language filter
./crawl.sh youtube --input urls.txt --language en --limit 20
```

### Crawl from Channel

```bash
# Crawl latest 50 videos from channel
./crawl.sh youtube --channel UCJc4VuL2ynZhS1tn7ZqbLEg --limit 50
```

### Check Status

```bash
./crawl.sh status
```

**Expected Output:**
```
Pipeline Status:
✅ Configuration loaded successfully
✅ AWS credentials valid
✅ S3 bucket accessible: your-travel-ai-data
📊 Total videos: 117
📋 Stage 1 complete: 117
📋 Stage 2 complete: 117
📋 Stage 3 complete: 117
📋 Stage 4 complete: 117
```

---

## Performance & Costs

### Processing Time
- **Metadata fetch:** ~1 second per video (YouTube API)
- **Audio download:** ~30 seconds for 10-minute video (depends on network)
- **Transcription:** ~1-2 minutes for 10-minute video (CPU)
- **Total:** ~3-5 minutes per video

### Costs
- **YouTube Data API:** FREE (10,000 units/day quota)
- **yt-dlp:** FREE (open source)
- **Whisper:** FREE (runs locally)
- **S3 Storage:** ~$0.023 per GB/month (~$0.001 per 100 videos)

**Total Stage 1 Cost:** **FREE** (excluding S3 storage)

### YouTube API Quota
- **Free Tier:** 10,000 units/day
- **Cost per Video:**
  - Video metadata: ~3 units
  - ~3,000 videos/day within free tier
- **Quota Exceeded:** Wait 24 hours or upgrade to paid quota

---

## Error Handling

### Common Errors

**1. YouTube API Quota Exceeded**
```
FetchError: YouTube API quota exceeded or invalid API key
```
**Solution:**
- Wait 24 hours for quota reset
- Use different API key
- Request quota increase from Google Cloud Console

**2. Video Not Found / Private**
```
FetchError: Video not found: youtube_abc123
```
**Solution:**
- Verify URL is correct
- Check if video is private, deleted, or region-restricted
- Skip and continue with next video

**3. Audio Download Failed**
```
yt-dlp error: Video unavailable
```
**Solution:**
- Video may be age-restricted (requires cookies)
- Video may be region-locked
- Try different browser for cookie extraction
- Skip and continue with next video

**4. Transcription Failed**
```
Error transcribing audio: Whisper model not loaded
```
**Solution:**
- Ensure Whisper is installed: `pip install openai-whisper`
- Ensure ffmpeg is installed: `brew install ffmpeg` (macOS)
- Check audio file exists and is valid

### Retry Logic
- **YouTube API:** No automatic retry (quota-sensitive)
- **Audio Download:** No automatic retry (timeout after 5 minutes)
- **Transcription:** No automatic retry (fails gracefully)

All errors are logged but do not stop the batch crawl.

---

## Configuration

### Environment Variables

```bash
# Required
YOUTUBE_API_KEY=your_youtube_api_key_here

# Optional
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
WHISPER_MODEL=small      # tiny, base, small, medium, large
```

### Whisper Model Selection

Edit `src/crawlers/youtube.py`:
```python
model = whisper.load_model("small")  # Change to: tiny, base, medium, large
```

**Recommendation:** Use `small` for balance of speed and quality.

---

## Quality Assurance

### Transcript Quality Indicators
1. **Quality Score:** 0.8+ indicates good transcription
2. **Segment Count:** More segments = better granularity
3. **Language Detection:** Verify detected language matches expected

### Manual Verification
```bash
# View transcript for a specific video
./crawl.sh view-stage1 youtube_UEDeptPVNQA
```

---

## Best Practices

### 1. Batch Processing
Process videos in batches to reuse Whisper model in memory:
```python
model = whisper.load_model("small")  # Load once
for video_url in urls:
    transcribe_audio(audio_file, video_id, model=model)
```

### 2. API Quota Management
- Track daily API usage
- Implement rate limiting if needed
- Use multiple API keys for high-volume crawls

### 3. Audio Cleanup
Temporary audio files are automatically deleted after transcription to save disk space.

### 4. Error Monitoring
- Check logs for failed videos: `logs/crawler.log`
- Retry failed videos manually if needed

---

## Troubleshooting

### Whisper Installation Issues

**Install Whisper:**
```bash
pip install openai-whisper
```

**Install ffmpeg (required by Whisper):**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### yt-dlp Issues

**Update yt-dlp:**
```bash
pip install --upgrade yt-dlp
```

**Browser Cookie Issues:**
- Change browser: `--cookies-from-browser firefox` (instead of chrome)
- Or disable cookies: remove `--cookies-from-browser` flag

### YouTube API Issues

**Get API Key:**
1. Go to https://console.cloud.google.com/apis/credentials
2. Create new project
3. Enable YouTube Data API v3
4. Create API key
5. Copy to `.env` as `YOUTUBE_API_KEY`

---

## Output Schema

**File:** `stage1_transcripts/youtube_{video_id}.json`

```typescript
{
  video_id: string              // YouTube video ID
  url: string                   // Full YouTube URL
  title: string                 // Video title
  channel: string               // Channel name
  duration_seconds: number      // Video duration
  view_count: number            // Total views
  like_count: number            // Total likes
  comment_count: number         // Total comments
  upload_date: string           // YYYY-MM-DD
  language: string              // ISO 639-1 code (e.g., 'en')
  transcript: string            // Full transcript text
  transcript_segments: Array<{  // Timestamped segments
    text: string
    start: number               // Start time (seconds)
    duration: number            // Duration (seconds)
  }>
  quality_score: number         // 0.0-1.0
  processing_timestamp: string  // ISO 8601 timestamp
  provenance: {
    source: "youtube"
    crawl_date: string          // YYYY-MM-DD
    whisper_model: string       // e.g., "small"
  }
}
```

---

## Next Stage

Once Stage 1 completes:
- ✅ Transcripts stored in S3
- ✅ Metadata tracked
- ➡️ **Ready for Stage 2:** [Entity Extraction](stage2-extraction.md)

---

## References

- **Implementation:** [`src/crawlers/youtube.py`](../../src/crawlers/youtube.py)
- **CLI Command:** [`cli/crawl.py`](../../cli/crawl.py)
- **Schemas:** [`src/utils/schemas.py`](../../src/utils/schemas.py)
- **Pipeline Overview:** [pipeline-overview.md](../02-architecture/pipeline-overview.md)
- **YouTube Data API:** https://developers.google.com/youtube/v3
- **Whisper:** https://github.com/openai/whisper
- **yt-dlp:** https://github.com/yt-dlp/yt-dlp

---

**Stage 1 complete!** Next: [Stage 2: Entity Extraction](stage2-extraction.md)
