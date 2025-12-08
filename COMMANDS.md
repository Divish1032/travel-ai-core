# TravelAI Command Reference

Complete reference for all commands available in the TravelAI YouTube crawler pipeline.

---

## Table of Contents

1. [Stage 1: YouTube Crawling & Transcription](#stage-1-youtube-crawling--transcription)
2. [Stage 2: LLM Entity Extraction](#stage-2-llm-entity-extraction)
3. [Pipeline Monitoring](#pipeline-monitoring)
4. [S3 Audit & Data Management](#s3-audit--data-management)
   - [Audit](#crawlsh-audit)
   - [Reset](#crawlsh-reset)
   - [Sync](#crawlsh-sync)
5. [Stage 2 Data Viewing](#stage-2-data-viewing)

---

## Stage 1: YouTube Crawling & Transcription

### `./crawl.sh youtube`

Crawls YouTube videos, downloads metadata, extracts audio, transcribes to text, and uploads to S3.

**Usage:**
```bash
./crawl.sh youtube --input FILE [OPTIONS]
```

**Required Flags:**
- `--input FILE`, `-i FILE` - Path to text file containing YouTube URLs (one per line)

**Optional Flags:**
- `--limit N`, `-l N` - Limit processing to first N videos from the input file
- `--force` - Force re-processing of videos (skip deduplication check, reprocess even if already in S3)
- `--dry-run` - Preview what would be crawled without actually crawling

**Examples:**
```bash
# Crawl all videos from urls.txt (skips already processed)
./crawl.sh youtube --input urls.txt

# Force re-process all videos (ignore deduplication)
./crawl.sh youtube --input urls.txt --force

# Test with first 5 videos
./crawl.sh youtube --input urls.txt --limit 5

# Preview what would be crawled
./crawl.sh youtube --input urls.txt --dry-run --limit 10
```

**What it does:**
1. Reads YouTube URLs from input file
2. Checks for duplicates in S3 (unless `--force`)
3. Downloads video metadata using YouTube API
4. Extracts audio using yt-dlp
5. Transcribes audio using OpenAI Whisper
6. Uploads all data to S3 with structured paths
7. Updates metadata tracker

**Output Location:**
- S3: `s3://bucket/raw/new/youtube_video_VIDEOID.jsonl`
- Metadata: `s3://bucket/metadata/processing_status.jsonl`

**Note:** After Stage 2 processing completes, files are moved from `raw/new/` to `raw/stage2_processed/`

---

## Stage 2: LLM Entity Extraction

### `./crawl.sh process-stage2`

Extracts structured travel information (places, restaurants, activities, traveler profile) from video transcripts using LLM.

**Processing Strategies:**
- **Short Videos (<35 min)**: Single-pass extraction using full transcript
- **Long Videos (>=35 min)**: Hierarchical chunked extraction (5-min chunks with 1-min overlap)

**Usage:**
```bash
./crawl.sh process-stage2 [OPTIONS]
```

**Optional Flags:**
- `--limit N` - Limit to first N videos (useful for testing)
- `--force` - Reprocess videos that already have Stage 2 data
- `--log-level LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
- `--provider PROVIDER` - LLM provider to use (gemini, openai, deepseek)

**Examples:**
```bash
# Process all pending videos (recommended)
./crawl.sh process-stage2

# Test with 5 videos first
./crawl.sh process-stage2 --limit 5

# Reprocess all videos (including already processed)
./crawl.sh process-stage2 --force

# Reprocess 10 videos with debug logging
./crawl.sh process-stage2 --force --limit 10 --log-level DEBUG
```

**What it does:**
1. Finds all videos ready for Stage 2 (completed Stage 1)
2. Downloads transcripts from S3
3. Classifies video length:
   - **Short (<35 min)**: Single-pass extraction
   - **Long (>=35 min)**: Hierarchical chunked extraction
4. For short videos:
   - Sends full transcript to LLM in one call
   - Extracts traveler profile + entities
5. For long videos:
   - Splits transcript into 5-minute chunks with 1-minute overlap
   - Extracts entities from each chunk separately
   - Merges and deduplicates entities by (name, location)
   - Combines traveler profile signals from all chunks
6. Parses and validates JSON response
7. Uploads extracted data to S3
8. Moves raw file from `raw/new/` to `raw/stage2_processed/`
9. Updates metadata tracker

**LLM Provider Configuration:**
Set in `.env` file:
```bash
LLM_PROVIDER=gemini  # Options: openai, deepseek, gemini
OPENAI_API_KEY=your_key
DEEPSEEK_API_KEY=your_key
GEMINI_API_KEY=your_key
```

**Output Location:**
- S3: `s3://bucket/stage2-extracted/new/youtube_video_VIDEOID_extracted.jsonl`

**File Movement:**
- Raw input file moved from `raw/new/` to `raw/stage2_processed/` after successful extraction
- Extracted data stored in `stage2-extracted/new/` awaiting Stage 3 processing

**Extracted Data Structure:**
- Traveler profile (type, age, budget, style)
- Entities: restaurants, hotels, activities, attractions, destinations
- Each entity includes: name, type, location, experience, sentiment, cost, timestamp

**Processing Performance:**
- **Short videos**: ~15-20 seconds, ~$0.0023 per video
- **Long videos**: ~2-4 minutes, ~$0.02-0.03 per video
- **Token usage**: Tracked per video, displayed in summary
- **Quality scoring**: Automatic assessment (high, medium, low)

**Deduplication (Long Videos):**
- Groups entities by (name, location) - case insensitive
- Combines experiences: "Experience 1. Experience 2."
- Keeps highest confidence score
- Keeps earliest timestamp
- Merges sentiments (uses "mixed" if conflicting)

---

## Pipeline Monitoring

### `./crawl.sh status`

Shows overall pipeline status with statistics for all stages.

**Usage:**
```bash
./crawl.sh status
```

**No flags required.**

**Output:**
- Total videos in pipeline
- Stage 1 statistics (complete, pending, failed, running)
- Stage 2 statistics (complete, pending, failed, running)
- Overall pipeline status distribution

**Example:**
```bash
./crawl.sh status
```

---

### `./crawl.sh stage`

Shows detailed statistics for a specific pipeline stage.

**Usage:**
```bash
./crawl.sh stage STAGE_NAME
```

**Arguments:**
- `STAGE_NAME` - Name of the stage (e.g., `stage_1_crawl`, `stage_2_extract`)

**Examples:**
```bash
# View Stage 1 details
./crawl.sh stage stage_1_crawl

# View Stage 2 details
./crawl.sh stage stage_2_extract
```

**Output:**
- Stage-specific statistics
- Status breakdown (complete, pending, failed, running)
- Average processing time
- Success rate

---

### `./crawl.sh failed`

Lists all failed items across all pipeline stages.

**Usage:**
```bash
./crawl.sh failed
```

**No flags required.**

**Output:**
- List of videos that failed processing
- Stage where failure occurred
- Error messages
- Retry counts

**Example:**
```bash
./crawl.sh failed
```

---

### `./crawl.sh languages`

Shows language distribution of processed videos.

**Usage:**
```bash
./crawl.sh languages
```

**No flags required.**

**Output:**
- Count of videos per language
- Percentage distribution
- Language codes (en, hi, es, etc.)

**Example:**
```bash
./crawl.sh languages
```

---

## S3 Audit & Data Management

### `./crawl.sh audit`

Compares actual S3 bucket contents with metadata tracker to find discrepancies.

**Usage:**
```bash
./crawl.sh audit --stage STAGE_NAME [OPTIONS]
```

**Required Flags:**
- `--stage STAGE_NAME` - Stage to audit (e.g., `stage_2_extract`, `stage_1_crawl`)

**Optional Flags:**
- `--show-missing` - Show videos marked complete in metadata but missing in S3
- `--show-extra` - Show videos in S3 but not tracked in metadata

**Examples:**
```bash
# Basic audit for Stage 2
./crawl.sh audit --stage stage_2_extract

# Show all missing videos
./crawl.sh audit --stage stage_2_extract --show-missing

# Show extra files in S3
./crawl.sh audit --stage stage_2_extract --show-extra

# Audit Stage 1
./crawl.sh audit --stage stage_1_crawl
```

**Output:**
- Videos in S3 (actual file count)
- Videos in metadata (marked as complete)
- Missing in S3 (metadata says complete but no file)
- Extra in S3 (file exists but not in metadata)
- Detailed list of discrepancies

**Use Cases:**
- Diagnose data consistency issues
- Find videos that need reprocessing
- Verify successful uploads

---

### `./crawl.sh reset`

Resets stage status for videos back to 'not_started', allowing reprocessing.

**Usage:**
```bash
./crawl.sh reset --stage STAGE_NAME [OPTIONS]
```

**Required Flags:**
- `--stage STAGE_NAME` - Stage to reset (e.g., `stage_2_extract`, `stage_1_crawl`)

**Action Flags (choose one):**
- `--all` - Reset all videos for this stage
- `--video-id VIDEO_ID` - Reset specific video (can specify multiple times)

**Optional Flags:**
- `--status STATUS` - Only reset videos with this status (choices: complete, failed, pending, running)
- `--dry-run` - Preview what would be reset without actually resetting
- `--yes`, `-y` - Skip confirmation prompt

**Examples:**
```bash
# Preview resetting all Stage 2 videos
./crawl.sh reset --stage stage_2_extract --all --dry-run

# Reset all Stage 2 videos (with confirmation)
./crawl.sh reset --stage stage_2_extract --all

# Reset all Stage 2 videos (skip confirmation)
./crawl.sh reset --stage stage_2_extract --all -y

# Reset specific video
./crawl.sh reset --stage stage_2_extract --video-id youtube_abc123

# Reset multiple specific videos
./crawl.sh reset --stage stage_2_extract --video-id youtube_abc123 --video-id youtube_xyz789

# Reset only failed videos
./crawl.sh reset --stage stage_2_extract --status failed

# Reset only completed videos (for reprocessing)
./crawl.sh reset --stage stage_2_extract --status complete --dry-run
```

**What it resets:**
- Stage status → `not_started`
- Started/completed timestamps → `null`
- Duration → `null`
- S3 paths → `[]`
- Metadata → `{}`
- Error messages → `null`
- Retry count → `0`
- Pipeline status updated accordingly

**Safety Features:**
- Dry-run mode to preview changes
- Confirmation prompts (unless `-y` flag)
- Detailed output of what will be reset

---

### `./crawl.sh sync`

Syncs metadata tracker with actual S3 bucket contents.

**Usage:**
```bash
./crawl.sh sync --stage STAGE_NAME
```

**Required Flags:**
- `--stage STAGE_NAME` - Stage to sync (e.g., `stage_2_extract`, `stage_1_crawl`)

**Examples:**
```bash
# Sync Stage 2 metadata
./crawl.sh sync --stage stage_2_extract

# Sync Stage 1 metadata
./crawl.sh sync --stage stage_1_crawl
```

**What it does:**
- Scans actual S3 bucket for files
- Updates metadata for videos with files but marked as 'not_started'
- Marks videos as 'complete' if they have data in S3

**Use Cases:**
- Fix metadata after manual S3 uploads
- Recover from metadata corruption
- Update tracking after external processing

**S3 Locations Checked:**
- Stage 1: `raw/new/` and `raw/stage2_processed/`
- Stage 2: `stage2-extracted/new/` and `stage2-extracted/stage3_processed/`

---

## Stage 2 Data Viewing

### `./crawl.sh view-stage2`

View extracted entities for a specific video.

**Usage:**
```bash
./crawl.sh view-stage2 VIDEO_ID [OPTIONS]
```

**Required Arguments:**
- `VIDEO_ID` - YouTube video ID (e.g., `youtube_abc123`)

**Optional Flags:**
- `--type TYPE`, `-t TYPE` - Filter by entity type (restaurant, hotel, activity, attraction, destination, transport, other)
- `--sentiment SENTIMENT`, `-s SENTIMENT` - Filter by sentiment (positive, negative, neutral, mixed)
- `--min-confidence SCORE` - Filter entities with confidence >= SCORE (0.0-1.0)
- `--json` - Output raw JSON instead of formatted table

**Examples:**
```bash
# View all entities for a video
./crawl.sh view-stage2 youtube_abc123

# View only restaurants
./crawl.sh view-stage2 youtube_abc123 --type restaurant

# View only activities
./crawl.sh view-stage2 youtube_abc123 -t activity

# View only positive experiences
./crawl.sh view-stage2 youtube_abc123 --sentiment positive

# View high-confidence entities (>= 0.8)
./crawl.sh view-stage2 youtube_abc123 --min-confidence 0.8

# Combine filters: high-confidence restaurants
./crawl.sh view-stage2 youtube_abc123 -t restaurant --min-confidence 0.8

# Get raw JSON output
./crawl.sh view-stage2 youtube_abc123 --json
```

**Output:**
- Video metadata (title, duration, language)
- Traveler profile
- Extracted entities in formatted table:
  - Entity name
  - Type
  - Location
  - Experience description
  - Sentiment
  - Cost mentioned
  - Confidence score

---

### `./crawl.sh list-stage2`

List all videos that have been processed through Stage 2.

**Usage:**
```bash
./crawl.sh list-stage2 [OPTIONS]
```

**Optional Flags:**
- `--limit N` - Limit to top N videos
- `--sort-by FIELD` - Sort by field (choices: entities, title, date, duration)
- `--type TYPE` - Filter videos containing specific entity type
- `--min-entities N` - Only show videos with at least N entities

**Examples:**
```bash
# List all Stage 2 processed videos
./crawl.sh list-stage2

# List top 20 videos (sorted by entity count)
./crawl.sh list-stage2 --limit 20

# Sort by video title
./crawl.sh list-stage2 --sort-by title

# Sort by processing date
./crawl.sh list-stage2 --sort-by date

# Show videos with at least 30 entities
./crawl.sh list-stage2 --min-entities 30

# Show videos containing restaurants
./crawl.sh list-stage2 --type restaurant
```

**Output:**
- Video ID
- Video title
- Number of entities extracted
- Entity type breakdown
- Processing date
- Video duration

---

## Validation Commands

### `./crawl.sh validate`

Validates input URLs file format before crawling.

**Usage:**
```bash
./crawl.sh validate --input FILE
```

**Required Flags:**
- `--input FILE`, `-i FILE` - Path to URLs file to validate

**Examples:**
```bash
# Validate urls.txt
./crawl.sh validate --input urls.txt
```

**What it checks:**
- File exists and is readable
- URLs are valid YouTube format
- No duplicate URLs
- File format is correct (one URL per line)

**Output:**
- Validation status
- Number of valid URLs
- Number of invalid URLs
- List of invalid URLs (if any)

---

## Help Command

### `./crawl.sh help`

Shows help information with all available commands.

**Usage:**
```bash
./crawl.sh help
# or
./crawl.sh --help
# or
./crawl.sh -h
# or
./crawl.sh  # (no arguments)
```

**Output:**
- Complete list of commands
- Usage examples
- Flag descriptions
- Common workflows

---

## Common Workflows

### Full Pipeline: Stage 1 → Stage 2

```bash
# 1. Crawl videos from URLs file
./crawl.sh youtube --input urls.txt

# 2. Check status
./crawl.sh status

# 3. Process through Stage 2
./crawl.sh process-stage2

# 4. View results
./crawl.sh list-stage2 --limit 10
./crawl.sh view-stage2 youtube_abc123
```

### Testing Workflow

```bash
# 1. Test crawl with 5 videos
./crawl.sh youtube --input urls.txt --limit 5

# 2. Test Stage 2 with 3 videos
./crawl.sh process-stage2 --limit 3

# 3. Check results
./crawl.sh status
./crawl.sh list-stage2
```

### Recovery Workflow

```bash
# 1. Audit for discrepancies
./crawl.sh audit --stage stage_2_extract --show-missing

# 2. Reset failed videos
./crawl.sh reset --stage stage_2_extract --status failed

# 3. Reprocess
./crawl.sh process-stage2
```

### Data Quality Workflow

```bash
# 1. Check for failed items
./crawl.sh failed

# 2. Audit S3 consistency
./crawl.sh audit --stage stage_2_extract

# 3. Reset and reprocess if needed
./crawl.sh reset --stage stage_2_extract --status failed -y
./crawl.sh process-stage2
```

---

## Environment Variables

Commands use configuration from `.env` file:

**Required:**
- `AWS_ACCESS_KEY_ID` - AWS credentials
- `AWS_SECRET_ACCESS_KEY` - AWS credentials
- `AWS_REGION` - AWS region (e.g., us-east-1)
- `S3_BUCKET_NAME` - S3 bucket name

**Optional:**
- `YOUTUBE_API_KEY` - For video metadata (recommended)
- `LLM_PROVIDER` - LLM provider choice (openai/deepseek/gemini)
- `OPENAI_API_KEY` - For OpenAI API
- `DEEPSEEK_API_KEY` - For DeepSeek API
- `GEMINI_API_KEY` - For Google Gemini API
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)

---

## Exit Codes

All commands return standard exit codes:
- `0` - Success
- `1` - Error (invalid arguments, API failure, etc.)

---

## Notes

- All commands use the helper script `./crawl.sh` which handles PYTHONPATH and virtual environment
- Commands automatically create `.env` validation before running
- Most commands support rich console output with colors and tables
- Progress bars shown for long-running operations
- All data is uploaded to S3 with structured paths
- Metadata tracker maintains state for deduplication and pipeline tracking
