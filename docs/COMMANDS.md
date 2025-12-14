# TravelAI Command Reference

Complete reference for all commands available in the TravelAI YouTube crawler pipeline.

---

## Table of Contents

1. [Stage 1: YouTube Crawling & Transcription](#stage-1-youtube-crawling--transcription)
2. [Stage 2: LLM Entity Extraction](#stage-2-llm-entity-extraction)
3. [Stage 3: Deduplication, Canonicalization & Consensus](#stage-3-deduplication-canonicalization--consensus)
   - [process-stage3](#crawlsh-process-stage3)
   - [validate-stage3](#crawlsh-validate-stage3)
   - [stage3-stats](#crawlsh-stage3-stats)
   - [show-entity](#crawlsh-show-entity)
   - [search-entities](#crawlsh-search-entities)
   - [reset-stage3](#crawlsh-reset-stage3)
4. [Stage 4: Vector Embeddings & Semantic Search](#stage-4-vector-embeddings--semantic-search)
   - [process-stage4](#crawlsh-process-stage4)
   - [stage4-stats](#crawlsh-stage4-stats)
   - [search](#crawlsh-search)
   - [backup-vectors](#crawlsh-backup-vectors)
   - [sync-to-cloud](#crawlsh-sync-to-cloud)
   - [monitor-stage4](#crawlsh-monitor-stage4)
5. [Pipeline Monitoring](#pipeline-monitoring)
6. [S3 Audit & Data Management](#s3-audit--data-management)
   - [Audit](#crawlsh-audit)
   - [Reset](#crawlsh-reset)
   - [Sync](#crawlsh-sync)
7. [Stage 2 Data Viewing](#stage-2-data-viewing)

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

## Stage 3: Deduplication, Canonicalization & Consensus

### `./crawl.sh process-stage3`

Deduplicates entities across all videos, creates canonical entities with consensus data, and geocodes them.

**Usage:**
```bash
./crawl.sh process-stage3 [OPTIONS]
```

**Optional Flags:**
- `--limit N` - Limit to first N videos (useful for testing)
- `--entity-types TYPES` - Comma-separated entity types to process (e.g., `attraction,destination`)
- `--log-level LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)

**Examples:**
```bash
# Process all videos, all entity types
./crawl.sh process-stage3

# Test with 10 videos first
./crawl.sh process-stage3 --limit 10

# Process only attractions
./crawl.sh process-stage3 --entity-types attraction

# Process attractions and destinations with debug logging
./crawl.sh process-stage3 --entity-types attraction,destination --log-level DEBUG
```

**What it does:**
1. Loads all Stage 2 entities from S3
2. Groups entities by type (attraction, destination, etc.)
3. **Deduplicates** using 4-tier matching:
   - Exact name matching (case-insensitive)
   - Fuzzy matching (handles typos: "Wat Po" = "Wat Pho")
   - Semantic matching (understands "Grand Palace" = "Phra Borom Maha Ratcha Wang")
   - Location proximity (identifies same place with different names)
4. **Canonicalizes** entity groups:
   - Selects best canonical name
   - Merges all aliases
   - Preserves all experiences from source entities
5. **Calculates consensus**:
   - Average ratings across all mentions
   - Traveler profile aggregation (solo, couple, family, etc.)
   - Best-for categories (budget, luxury, families, etc.)
   - **LLM theme extraction** (identifies key themes/tags)
6. **Geocodes** entities:
   - Primary: Nominatim (OpenStreetMap) - FREE
   - Fallback: Google Maps Geocoding API - Paid ($5/1000 requests)
   - Returns lat/lon coordinates
   - Validates coordinates are in Thailand bounds
7. Saves canonical entities to S3 in multiple formats
8. Tracks costs (LLM + geocoding)
9. Updates metadata tracker with provenance

**Deduplication Algorithm:**
- **Tier 1 - Exact**: Exact name match (case-insensitive)
- **Tier 2 - Fuzzy**: Levenshtein distance + fuzzy ratio (handles typos)
- **Tier 3 - Semantic**: Sentence-BERT embeddings (understands meaning)
- **Tier 4 - Location**: Geographic proximity for same-city entities

**Geocoding Strategy:**
- Tries Nominatim first (FREE, 1 req/sec)
- Falls back to Google Maps if:
  - Nominatim fails
  - Confidence < 0.8
- 90%+ entities use FREE Nominatim
- Only ~10% need Google Maps fallback

**Output Location:**
- S3: `s3://bucket/stage3-canonical/`
  - `entities_all_YYYYMMDD.jsonl` (all entities)
  - `by_city/bangkok.jsonl` (grouped by city)
  - `by_type/attraction.jsonl` (grouped by type)
  - `metadata/processing_stats_YYYYMMDD.json`
- Local: `data/cost_reports/stage3_cost_report_YYYYMMDD_HHMMSS.json`

**Cost Tracking:**
- LLM theme extraction: ~$0.000026 per entity (Gemini Flash)
- Geocoding: $0.005 per entity (only if Google needed)
- Typical 1000 entities: ~$0.03 (mostly FREE)

**Performance:**
- 50 entities: ~30 seconds
- 1000 entities: ~10 minutes
- Deduplication rate: typically 30-40% (reduces entities)

---

### `./crawl.sh validate-stage3`

Validates Stage 3 canonical entities for quality assurance.

**Usage:**
```bash
./crawl.sh validate-stage3 [OPTIONS]
```

**Optional Flags:**
- `--sample N` - Number of entities to sample for review (default: 20)
- `--log-level LEVEL` - Set logging level

**Examples:**
```bash
# Validate with default settings
./crawl.sh validate-stage3

# Validate with larger sample
./crawl.sh validate-stage3 --sample 50
```

**What it validates:**
1. **Completeness**: All required fields present
2. **Deduplication Quality**: No over-deduplication
3. **Geolocation Accuracy**: Coordinates valid and in Thailand
4. **Consensus Logic**: Calculations correct
5. **Provenance**: Entities traceable to source videos

**Output:**
- Console report with validation results
- QA report saved to: `stage3-canonical/metadata/qa_report_YYYYMMDD_HHMMSS.json`
- Actionable recommendations for improvements

---

### `./crawl.sh stage3-stats`

Displays comprehensive statistics about Stage 3 canonical entities.

**Usage:**
```bash
./crawl.sh stage3-stats
```

**No flags required.**

**Output:**
- Entity counts by type and city
- Deduplication rate
- Geocoding success rate (Nominatim vs Google)
- Rating distribution
- Top 10 cities by entity count

**Example:**
```bash
./crawl.sh stage3-stats
```

---

### `./crawl.sh show-entity`

Displays complete details about a canonical entity including provenance.

**Usage:**
```bash
./crawl.sh show-entity <ENTITY_ID> [OPTIONS]
```

**Required:**
- `ENTITY_ID` - The canonical entity ID (e.g., ATT_001)

**Optional Flags:**
- `--json-output` - Output as JSON instead of formatted text

**Examples:**
```bash
# Show entity details
./crawl.sh show-entity ATT_001

# Output as JSON
./crawl.sh show-entity ATT_001 --json-output
```

**Output:**
- Entity details (name, type, location, coordinates)
- Consensus data (ratings, themes, best_for)
- All experiences from source videos
- Provenance (source videos, Stage 2 entities)
- Google Maps link

---

### `./crawl.sh search-entities`

Search canonical entities by name with fuzzy matching.

**Usage:**
```bash
./crawl.sh search-entities --query QUERY [OPTIONS]
```

**Required:**
- `--query`, `-q` - Search query

**Optional Flags:**
- `--city`, `-c` - Filter by city (e.g., Bangkok)
- `--type`, `-t` - Filter by entity type (e.g., attraction)
- `--limit`, `-l` - Max results to display (default: 20)
- `--threshold` - Fuzzy match threshold 0-100 (default: 60)

**Examples:**
```bash
# Search for "Khao San"
./crawl.sh search-entities --query "Khao San"

# Search for temples in Bangkok
./crawl.sh search-entities --query "temple" --city "Bangkok"

# Search for beaches (show all results)
./crawl.sh search-entities --query "beach" --type attraction --limit 100

# More permissive matching
./crawl.sh search-entities --query "wat" --threshold 40
```

**Output:**
- Scored search results (100 = perfect match)
- Entity ID, name, type, location
- Can pipe to `show-entity` for details

---

### `./crawl.sh reset-stage3`

Resets Stage 3 processing completely, allowing you to reprocess with different configuration or fix errors.

**Usage:**
```bash
./crawl.sh reset-stage3 [OPTIONS]
```

**Action Flags (choose one):**
- `--all` - Reset all Stage 3 data (required if not using --video-ids)
- `--video-ids VIDEO_IDS` - Comma-separated list of video IDs to reset (e.g., abc123,xyz789)

**Optional Flags:**
- `--dry-run` - Preview what would be reset without actually resetting
- `--log-level LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)

**Examples:**
```bash
# Preview what will be reset
./crawl.sh reset-stage3 --all --dry-run

# Reset all Stage 3 data
./crawl.sh reset-stage3 --all

# Reset specific videos
./crawl.sh reset-stage3 --video-ids abc123,xyz789

# Dry run for specific videos
./crawl.sh reset-stage3 --video-ids abc123,xyz789 --dry-run
```

**What it does:**
1. **Deletes Stage 3 canonical entities** from `stage3-canonical/new/` in S3
2. **Moves Stage 2 files back** from `stage2-extracted/stage3_extracted/` to `stage2-extracted/new/`
3. **Resets Stage 3 metadata** in the tracker (status, timestamps, S3 paths)

**When to use:**
- You forgot to configure Google Maps API key and entities failed geocoding
- You want to change deduplication parameters and reprocess
- You want to add more entity types to process
- Stage 3 processing failed and you need to start over
- You want to test Stage 3 with different configuration

**Important Notes:**
- When resetting `--all`, deletes ALL Stage 3 canonical entities (not selective)
- When resetting specific `--video-ids`, Stage 3 files are NOT deleted (they contain data from multiple videos)
- Always use `--dry-run` first to preview changes
- After reset, run `./crawl.sh process-stage3` to reprocess

**Complete Workflow Example:**
```bash
# 1. Something went wrong, check what would be reset
./crawl.sh reset-stage3 --all --dry-run

# 2. Reset Stage 3
./crawl.sh reset-stage3 --all

# 3. Update configuration (e.g., add Google Maps API key)
# Edit .env file: GOOGLE_MAPS_API_KEY=your_key_here

# 4. Reprocess Stage 3 with new configuration
./crawl.sh process-stage3

# 5. Validate results
./crawl.sh validate-stage3
./crawl.sh stage3-stats
```

**Safety Features:**
- Dry-run mode to preview all changes
- Clear summary of what will be deleted/moved/reset
- Separate handling for full reset vs. specific videos
- Detailed logging of all operations

---

## Stage 4: Vector Embeddings & Semantic Search

Stage 4 generates embeddings for canonical entities and indexes them into ChromaDB for semantic search. Supports three embedding strategies and includes production-ready monitoring, backup, and cloud sync capabilities.

### `./crawl.sh process-stage4`

Generate and index embeddings for canonical entities into ChromaDB vector database.

**Usage:**
```bash
./crawl.sh process-stage4 [OPTIONS]
```

**Optional Flags:**
- `--embedding-types TYPE` - Embedding types to process: `entity`, `profile`, `experience`, `all`, or comma-separated list (default: `all`)
- `--limit N` - Limit processing to first N entities (for testing)
- `--batch-size N` - Batch size for embedding generation (default: 100)

**Examples:**
```bash
# Process all embedding types (entity, profile, experience)
./crawl.sh process-stage4 --embedding-types all

# Process only entity-level embeddings
./crawl.sh process-stage4 --embedding-types entity

# Process profiles and experiences only
./crawl.sh process-stage4 --embedding-types profile,experience

# Test with limited entities
./crawl.sh process-stage4 --embedding-types all --limit 10
```

**What It Does:**
1. Loads canonical entities from Stage 3 (`stage3-canonical/`)
2. Generates embeddings using configured model (default: gte-large)
3. Indexes embeddings into ChromaDB collections:
   - `entities` - Entity-level embeddings (one per entity)
   - `profile_consensus` - Profile-specific embeddings
   - `experiences` - Experience-level embeddings
4. Updates metadata tracker to mark source videos as Stage 4 complete
5. Saves indexing statistics and provenance

**Outputs:**
- ChromaDB vector database (local: `./chroma_data` or cloud)
- Indexing statistics: `stage4-vectors/metadata/`
- Stage 4 tracking report: `stage4-vectors/reports/`
- Provenance mapping: `metadata/embedding_provenance.jsonl` (S3)

**Environment Variables:**
- `CHROMADB_MODE` - `local` or `cloud` (default: local)
- `CHROMADB_PERSIST_DIR` - Local ChromaDB directory (default: ./chroma_data)
- `CHROMADB_HOST` - Cloud ChromaDB host (for cloud mode)
- `CHROMADB_API_KEY` - Cloud ChromaDB API key (for cloud mode)
- `EMBEDDING_MODEL` - Embedding model to use (default: gte-large)

---

### `./crawl.sh stage4-stats`

Display comprehensive statistics for Stage 4 vector database including collection sizes, embedding counts, cost metrics, and performance data.

**Usage:**
```bash
./crawl.sh stage4-stats [OPTIONS]
```

**Optional Flags:**
- `--detailed`, `-d` - Show detailed per-collection statistics
- `--json`, `-j` - Export statistics as JSON

**Examples:**
```bash
# Basic statistics
./crawl.sh stage4-stats

# Detailed statistics with breakdown
./crawl.sh stage4-stats --detailed

# Export as JSON for reporting
./crawl.sh stage4-stats --json > weekly_report.json
```

**What It Shows:**
- Collection sizes (entities, profile_consensus, experiences)
- Total embeddings and storage utilization
- Embedding generation costs and token usage
- Indexing performance metrics
- Search performance (if available)
- Latest session information

---

### `./crawl.sh search`

Interactive semantic search interface for querying the vector database.

**Usage:**
```bash
./crawl.sh search [OPTIONS]
```

**Optional Flags:**
- `--query TEXT` - Search query text
- `--city CITY` - Filter by city
- `--profile PROFILE` - Use traveler profile for personalization
- `--top-k N` - Number of results to return (default: 10)
- `--interactive` - Launch interactive search mode

**Examples:**
```bash
# Simple search
./crawl.sh search --query "beach parties"

# City-specific search
./crawl.sh search --query "romantic dinner" --city Bangkok

# Personalized search with traveler profile
./crawl.sh search --query "places to stay" --profile solo_budget_party

# Interactive mode
./crawl.sh search --interactive

# Top 3 results
./crawl.sh search --query "nightlife" --top-k 3
```

**Available Profiles:**
- `solo_budget_party` - Solo budget party traveler
- `couple_luxury` - Luxury couple traveler
- `family_budget` - Budget family traveler
- `solo_luxury` - Luxury solo traveler

**What It Does:**
- Generates embedding for search query
- Searches ChromaDB collections
- Applies city/profile filters if specified
- Ranks results by semantic similarity
- Returns top-k most relevant entities

---

### `./crawl.sh backup-vectors`

Backup ChromaDB vector database to S3 for disaster recovery.

**Usage:**
```bash
./crawl.sh backup-vectors [OPTIONS]
```

**Optional Flags:**
- `--collections LIST` - Comma-separated list of collections to backup (default: all)
- `--compress` - Compress backup files with gzip
- `--incremental` - Perform incremental backup (only changes since last backup)

**Examples:**
```bash
# Backup all collections (recommended weekly)
./crawl.sh backup-vectors --compress

# Backup specific collections
./crawl.sh backup-vectors --collections entities,profile_consensus

# Compressed full backup
./crawl.sh backup-vectors --compress

# Incremental backup
./crawl.sh backup-vectors --incremental --compress
```

**What It Does:**
1. Exports embeddings from ChromaDB collections
2. Serializes to JSON with metadata
3. Optionally compresses with gzip
4. Uploads to S3: `stage4-vectors/backups/`
5. Includes full provenance and metadata

**S3 Backup Structure:**
```
stage4-vectors/backups/
  entities_backup_YYYYMMDD_HHMMSS.json.gz
  profile_consensus_backup_YYYYMMDD_HHMMSS.json.gz
  experiences_backup_YYYYMMDD_HHMMSS.json.gz
```

---

### `./crawl.sh sync-to-cloud`

Sync local ChromaDB database to cloud-hosted ChromaDB instance.

**Usage:**
```bash
./crawl.sh sync-to-cloud [OPTIONS]
```

**Optional Flags:**
- `--collections LIST` - Comma-separated list of collections (default: all)
- `--dry-run` - Show what would be synced without making changes
- `--force` - Force full resync (overwrite cloud data)

**Examples:**
```bash
# Dry run first (recommended)
./crawl.sh sync-to-cloud --dry-run

# Sync all collections
./crawl.sh sync-to-cloud

# Sync specific collections
./crawl.sh sync-to-cloud --collections entities

# Force resync (overwrites cloud data)
./crawl.sh sync-to-cloud --force
```

**Prerequisites:**
- Cloud ChromaDB credentials in `.env`:
  ```
  CHROMA_CLOUD_HOST=https://your-chroma-host.com
  CHROMA_CLOUD_API_KEY=your_api_key
  ```

**What It Does:**
1. Connects to local and cloud ChromaDB
2. Exports data from local collections
3. Creates/updates cloud collections
4. Uploads embeddings in batches
5. Verifies sync completion

**Use Cases:**
- Deploy to production (cloud hosting)
- Backup to managed ChromaDB
- Scale beyond local capacity
- Enable team collaboration

---

### `./crawl.sh monitor-stage4`

Monitor Stage 4 health, performance, and system status with automatic alerting.

**Usage:**
```bash
./crawl.sh monitor-stage4 [OPTIONS]
```

**Optional Flags:**
- `--check-all` - Run comprehensive health checks (including performance tests)
- `--generate-report` - Generate and save monitoring report
- `--alert-email EMAIL` - Email address for alerts (requires email integration)

**Examples:**
```bash
# Basic health check (recommended daily)
./crawl.sh monitor-stage4

# Comprehensive check (recommended weekly)
./crawl.sh monitor-stage4 --check-all

# Generate report
./crawl.sh monitor-stage4 --generate-report

# With email alerts
./crawl.sh monitor-stage4 --check-all --alert-email admin@example.com
```

**What It Checks:**
1. **Collection Health**
   - All collections exist and are accessible
   - Collection counts are non-zero
   - ChromaDB connection status

2. **Search Performance** (with `--check-all`)
   - Test queries with latency measurement
   - Average/max query times
   - Search success rate

3. **Storage Utilization**
   - Total embeddings across collections
   - Estimated storage size
   - Growth rate monitoring

**Exit Codes:**
- `0` - System healthy
- `1` - System has warnings
- `2` - System has critical issues
- `3` - Monitoring failed

**Alert Thresholds:**
- **Critical:** ChromaDB connection lost, all searches failing
- **Warning:** Query latency > 1000ms, error rate > 1%

**Monitoring Reports:**
Saved to: `stage4-vectors/monitoring/reports/monitor_report_YYYYMMDD_HHMMSS.json`

**Cron Integration:**
```bash
# Add to crontab for every 6 hours
0 */6 * * * /path/to/TravelAI/crawl.sh monitor-stage4 --alert-email admin@example.com
```

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
- `--stage STAGE_NAME` - Stage to sync (supported: `stage_1_crawl`, `stage_2_extract`, `stage_3_deduplicate`, `stage_4_vectorize`)

**Examples:**
```bash
# Sync Stage 1 metadata
./crawl.sh sync --stage stage_1_crawl

# Sync Stage 2 metadata
./crawl.sh sync --stage stage_2_extract

# Sync Stage 3 metadata
./crawl.sh sync --stage stage_3_deduplicate

# Sync Stage 4 metadata (ChromaDB)
./crawl.sh sync --stage stage_4_vectorize
```

**What it does:**
- Scans actual data sources (S3 or ChromaDB) for existing data
- Updates metadata for videos/entities with data but marked as 'not_started'
- Marks videos as 'complete' if they have been processed

**Use Cases:**
- Fix metadata after manual S3 uploads
- Recover from metadata corruption
- Update tracking after external processing
- Reconcile ChromaDB vector database with metadata

**Data Locations Checked:**
- **Stage 1**: `raw/new/` and `raw/stage2_processed/`
- **Stage 2**: `stage2-extracted/new/` and `stage2-extracted/stage3_processed/`
- **Stage 3**: `stage2-extracted/new/` and `stage2-extracted/stage3_extracted/`
- **Stage 4**: ChromaDB collections (`entities`, `profile_consensus`, `experiences`)

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
