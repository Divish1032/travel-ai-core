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
   - [reset-stage4](#crawlsh-reset-stage4)
5. [Stage 5: RAG Itinerary Generation](#stage-5-rag-itinerary-generation)
   - [generate-itinerary](#crawlsh-generate-itinerary)
   - [parse-query](#crawlsh-parse-query)
   - [validate-itinerary](#crawlsh-validate-itinerary)
   - [itinerary-examples](#crawlsh-itinerary-examples)
   - [check-stage5](#crawlsh-check-stage5)
   - [test-stage5](#crawlsh-test-stage5)
   - [quick-test](#crawlsh-quick-test)
6. [Pipeline Monitoring](#pipeline-monitoring)
7. [S3 Audit & Data Management](#s3-audit--data-management)
   - [Audit](#crawlsh-audit)
   - [Reset](#crawlsh-reset)
   - [Sync](#crawlsh-sync)
8. [Stage 2 Data Viewing](#stage-2-data-viewing)

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
- ChromaDB vector database (Chroma Cloud)
- Indexing statistics: `stage4-vectors/metadata/`
- Stage 4 tracking report: `stage4-vectors/reports/`
- Provenance mapping: `metadata/embedding_provenance.jsonl` (S3)

**Environment Variables:**
- `CHROMADB_TENANT` - Chroma Cloud tenant ID (required)
- `CHROMADB_DATABASE` - Chroma Cloud database name (default: default_database)
- `CHROMADB_API_KEY` - Chroma Cloud API key (required)
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

### `./crawl.sh reset-stage4`

Reset Stage 4 vector database (ChromaDB collections) and metadata tracker. Useful for rebuilding the vector index or switching between local/cloud deployments.

**Usage:**
```bash
./crawl.sh reset-stage4 [OPTIONS]
```

**Options:**
- `--all` - Reset all collections and metadata (required if not using other options)
- `--collections NAMES` - Reset specific collections (comma-separated: entities, profile_consensus, experiences)
- `--metadata` - Reset metadata files only
- `--dry-run` - Preview what would be reset without making changes
- `--force` - Skip confirmation prompt
- `--update-tracker` - Update metadata tracker to mark videos as pending (default: True)
- `--no-update-tracker` - Skip updating metadata tracker
- `--log-level LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)

**What Gets Reset:**
1. **ChromaDB Collections**: Deletes and recreates empty collections
2. **Metadata Files**: Deletes Stage 4 metadata files in `stage4-vectors/metadata/`
3. **Metadata Tracker**: Marks videos as "pending" for Stage 4 (unless `--no-update-tracker`)

**Collections:**
- `entities` - Entity-level embeddings (attractions, hotels, restaurants)
- `profile_consensus` - Profile consensus embeddings (aggregated perspectives)
- `experiences` - Experience-level embeddings (individual video mentions)

**Examples:**

```bash
# Preview reset (dry-run, no changes)
./crawl.sh reset-stage4 --all --dry-run

# Reset all collections and metadata (requires confirmation)
./crawl.sh reset-stage4 --all

# Reset specific collection only
./crawl.sh reset-stage4 --collections entities

# Reset multiple collections
./crawl.sh reset-stage4 --collections entities,profile_consensus

# Reset only metadata files (keep vector database)
./crawl.sh reset-stage4 --metadata

# Reset without updating metadata tracker
./crawl.sh reset-stage4 --all --no-update-tracker

# Force reset without confirmation
./crawl.sh reset-stage4 --all --force
```

**Common Workflows:**

**Rebuild Vector Index:**
```bash
# 1. Preview reset
./crawl.sh reset-stage4 --all --dry-run

# 2. Reset everything
./crawl.sh reset-stage4 --all

# 3. Rebuild vector index
./crawl.sh process-stage4 --embedding-types all
```

**Switch from Local to Cloud:**
```bash
# 1. Backup local vectors
./crawl.sh backup-vectors

# 2. Reset local database
./crawl.sh reset-stage4 --all

# 3. Update .env: CHROMADB_MODE=cloud

# 4. Rebuild in cloud
./crawl.sh process-stage4 --embedding-types all
```

**Reset Single Collection:**
```bash
# Reset only entity embeddings
./crawl.sh reset-stage4 --collections entities

# Regenerate entity embeddings only
./crawl.sh process-stage4 --embedding-types entity
```

**Output:**
- Shows current collection statistics before reset
- Lists what will be reset
- Requires confirmation (unless `--force`)
- Extracts video IDs from collections before deletion
- Updates metadata tracker to mark videos as pending
- Displays reset summary

**Notes:**
- If ChromaDB extraction fails (collections already empty), automatically falls back to reading from metadata tracker to find completed Stage 4 videos
- Metadata tracker is always updated unless `--no-update-tracker` is specified
- Works with both local and cloud ChromaDB deployments
- ChromaDB collections are recreated as empty after deletion

---

## Stage 5: RAG Itinerary Generation

Stage 5 uses RAG (Retrieval-Augmented Generation) to generate personalized travel itineraries from natural language queries. Takes a query like *"5 days Bangkok solo budget party"* and produces a detailed day-by-day itinerary with activities, costs, and travel tips.

### `./crawl.sh generate-itinerary`

Generate a personalized travel itinerary from a natural language query using the full 7-phase RAG pipeline.

**Usage:**
```bash
./crawl.sh generate-itinerary -q QUERY [OPTIONS]
```

**Required Flags:**
- `--query QUERY`, `-q QUERY` - Natural language query (e.g., "5 days Bangkok solo budget party")

**Optional Flags:**
- `--output-format FORMAT` - Output format: `markdown` (default), `text`, `json`, `html`
- `--save FILE` - Save output to file
- `--skip-narrative` - Skip narrative generation phase (faster, cheaper)
- `--max-retries N` - Maximum validation retries (default: 2)
- `--budget-limit USD` - Set budget limit for cost tracking (raises error if exceeded)
- `--debug` - Enable debug logging with detailed phase breakdown

**Examples:**
```bash
# Basic itinerary generation
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget party"

# With specific output format
./crawl.sh generate-itinerary -q "3 days Phuket couple mid-range beach" \
    --output-format markdown

# Save to file
./crawl.sh generate-itinerary -q "7 days Thailand backpacking" \
    --save my_trip.md

# Skip narrative for faster/cheaper generation
./crawl.sh generate-itinerary -q "2 days Bangkok temples culture" \
    --skip-narrative

# With budget limit
./crawl.sh generate-itinerary -q "5 days luxury resort" \
    --budget-limit 0.02

# Debug mode with detailed logs
./crawl.sh generate-itinerary -q "4 days Chiang Mai family" \
    --debug
```

**What It Does:**

**Phase 1: Intent Parsing** (~2-3s, ~$0.0001)
- Extracts structured intent from natural language query
- Identifies: destination, duration, budget tier, traveler type, interests
- Uses DeepSeek API with JSON mode

**Phase 2: Retrieval** (~2-3s, FREE)
- Semantic search across ChromaDB collections (1,200+ entities)
- Retrieves 20-40 relevant entities
- Filters by destination, budget, and interests

**Phase 3: Re-ranking** (~2-3s, ~$0.0015)
- LLM-based personalization and ranking
- Scores entities by relevance to user profile
- Returns top 15-20 entities

**Phase 4: Context Building** (~1s, FREE)
- Groups entities by type and location
- Calculates daily budgets
- Builds structured context for generation

**Phase 5: Itinerary Generation** (~15-20s, ~$0.008)
- Generates day-by-day itinerary
- Includes activities, timings, costs, tips
- Uses Gemini API

**Phase 6: Validation** (~5-8s, ~$0.0005)
- Detects hallucinations (entities not in database)
- Validates budget constraints
- Checks logical consistency
- Auto-retries if issues found (up to 2x)

**Phase 7: Narrative** (~10-15s, ~$0.0025) - Optional
- Generates engaging travel narrative
- Adds title, introduction, day narratives, conclusion
- Provides insider tips and budget breakdown

**Total Time:** 30-60 seconds (35-50s without narrative)
**Total Cost:** $0.01-0.02 per itinerary (Gemini + DeepSeek)

**Output Example:**
```markdown
# 5-Day Bangkok Itinerary: Solo Budget Traveler's Party Adventure

## Day 1: Welcome to Bangkok - Old Town Exploration
- **Morning**: Grand Palace & Wat Phra Kaew (9:00 AM - 12:00 PM)
  - Entry: 500 THB (~$14)
  - Tips: Dress modestly, arrive early
- **Lunch**: Street Food at Khao San Road (12:30 PM - 1:30 PM)
  - Cost: ~150 THB (~$4)
- **Evening**: Khao San Road Nightlife (8:00 PM - Late)
  - Budget: 600-800 THB (~$17-23)

**Daily Budget**: ~$50 | **Total So Far**: $50

[... Days 2-5 ...]

## Trip Summary
- **Total Budget**: ~$250 for 5 days
- **Best Value Tips**: Book hostels near Khao San ($8-12/night), Use BTS/MRT...
```

**Error Handling:**
- **Insufficient data**: Suggests alternative destinations or shorter duration
- **Budget exceeded**: Recommends budget increase or cheaper destination
- **Validation failure**: Auto-retries with adjustments
- **LLM failure**: Retries with exponential backoff (3 attempts)

**Cost Tracking:**
- Displays phase-by-phase cost breakdown
- Tracks token usage across all LLM calls
- Warns at 80% of budget limit
- Raises error if budget exceeded

---

### `./crawl.sh parse-query`

Test intent parsing without generating a full itinerary. Useful for debugging query understanding.

**Usage:**
```bash
./crawl.sh parse-query QUERY
```

**Required Arguments:**
- `QUERY` - Natural language query to parse

**Examples:**
```bash
# Parse a simple query
./crawl.sh parse-query "5 days Bangkok solo budget party"

# Parse a complex query
./crawl.sh parse-query "week in Thailand with family, mid-range hotels, cultural sites"

# Test edge cases
./crawl.sh parse-query "cheap trip to Phuket"
```

**Output:**
- Extracted destination
- Duration (days)
- Traveler profile (type, budget tier)
- Interests/travel style
- Budget constraints
- Confidence scores

**Example Output:**
```json
{
  "destination": "Bangkok",
  "duration_days": 5,
  "traveler_profile": {
    "traveler_type": "solo",
    "budget_tier": "budget",
    "travel_style": ["nightlife", "cultural"]
  },
  "interests": ["party", "nightlife", "temples"],
  "budget_per_day": {"min": 30, "max": 60}
}
```

**Use Cases:**
- Test if your query is understood correctly
- Debug intent extraction issues
- Validate query format before generating expensive itinerary

---

### `./crawl.sh validate-itinerary`

Validate an existing itinerary JSON file for quality issues.

**Usage:**
```bash
./crawl.sh validate-itinerary FILE
```

**Required Arguments:**
- `FILE` - Path to itinerary JSON file

**Examples:**
```bash
# Validate itinerary file
./crawl.sh validate-itinerary my_trip.json

# Validate after manual edits
./crawl.sh validate-itinerary output/bangkok_5day.json
```

**What It Validates:**
1. **Hallucination Detection**: Checks if entities exist in database
2. **Budget Validation**: Verifies total cost within budget constraints
3. **Logical Consistency**: Checks duration, timing, day counts
4. **Completeness**: Ensures all required fields present
5. **Entity Accuracy**: Verifies entity types, locations match query

**Output:**
- Overall validation score (0-1.0)
- List of issues with severity (error, warning, info)
- Suggestions for fixes
- Pass/fail status

**Example Output:**
```
Validation Report
-----------------
Overall Score: 0.85 / 1.0
Status: PASSED WITH WARNINGS

Issues Found:
  [WARNING] Day 2: "Fake Beach Club" not found in database (possible hallucination)
  [INFO] Total budget ($245) slightly under user's $250 budget

Suggestions:
  - Replace "Fake Beach Club" with verified entity from database
  - Consider adding more activities to utilize full budget
```

---

### `./crawl.sh itinerary-examples`

Show example queries and their expected outputs to help users understand how to write effective queries.

**Usage:**
```bash
./crawl.sh itinerary-examples
```

**No flags required.**

**Output:**
- 10-15 example queries with explanations
- Tips for writing effective queries
- Common query patterns
- Budget tier examples

**Example Output:**
```
RAG Itinerary Generation - Example Queries

BASIC QUERIES:
  "5 days Bangkok solo budget party"
  → Generates budget party itinerary for solo traveler in Bangkok (5 days)

  "3 days Phuket couple mid-range beach"
  → Romantic beach getaway for couples, mid-range budget (3 days)

COMPLEX QUERIES:
  "week in Thailand backpacking, budget hostels, temples and hiking"
  → Multi-destination backpacking trip with cultural/adventure focus

TIPS:
  - Include: destination, duration, budget tier, traveler type, interests
  - Budget tiers: budget (<$50/day), mid-range ($50-150), luxury (>$150)
  - Traveler types: solo, couple, family, group
  - Be specific about interests for better personalization
```

---

### `./crawl.sh check-stage5`

Check if Stage 5 environment is ready (ChromaDB connection, API keys, RAG components).

**Usage:**
```bash
./crawl.sh check-stage5
```

**No flags required.**

**What It Checks:**
1. **ChromaDB Connection**: Verifies connection to vector database
2. **ChromaDB Collections**: Checks entities, profile_consensus, experiences exist
3. **LLM API Keys**: Validates DeepSeek, Gemini, OpenAI keys are set
4. **Embedding Model**: Checks embedding model is available
5. **RAG Components**: Verifies all 9 RAG modules importable
6. **Python Packages**: Validates required dependencies installed

**Output:**
- Green checkmarks for passing checks
- Red X for failures
- Yellow warnings for optional issues
- Overall readiness status

**Example Output:**
```
Stage 5 Readiness Check
=======================

✅ ChromaDB Connection: OK (connected to cloud)
✅ Collection 'entities': 2,254 vectors
✅ Collection 'profile_consensus': 145 vectors
✅ Collection 'experiences': 646 vectors
✅ DeepSeek API Key: Set
✅ Gemini API Key: Set
⚠️  OpenAI API Key: Not set (optional)
✅ Embedding Model: gte-large available
✅ RAG Components: All 9 modules loaded

Status: ✅ READY
```

**Exit Codes:**
- `0` - Ready (all critical checks passed)
- `1` - Not ready (critical errors found)
- `2` - Ready with warnings (optional components missing)

**When to Use:**
- Before running itinerary generation for first time
- After environment changes or updates
- When debugging setup issues
- As part of deployment verification

---

### `./crawl.sh test-stage5`

Run comprehensive integration tests for Stage 5 RAG pipeline.

**Usage:**
```bash
./crawl.sh test-stage5 [OPTIONS]
```

**Optional Flags:**
- `--verbose`, `-v` - Show detailed test output
- `--skip-slow` - Skip slow tests (narrative generation)
- `--test-case NAME` - Run specific test case

**Examples:**
```bash
# Run all tests
./crawl.sh test-stage5

# Verbose output
./crawl.sh test-stage5 --verbose

# Skip slow tests (narrative generation)
./crawl.sh test-stage5 --skip-slow

# Run specific test
./crawl.sh test-stage5 --test-case test_intent_parser
```

**Test Coverage:**
1. **Intent Parser**: Query parsing accuracy
2. **Retrieval**: Entity retrieval and ranking
3. **Re-ranker**: Personalization scoring
4. **Generator**: Itinerary generation quality
5. **Validator**: Hallucination detection
6. **Narrative**: Narrative generation
7. **Pipeline**: End-to-end integration
8. **Error Handling**: Edge cases and failures
9. **Cost Tracking**: Budget enforcement

**Output:**
- Test results with pass/fail status
- Execution time per test
- Coverage statistics
- Failed test details with error messages

**Example Output:**
```
Running Stage 5 Integration Tests
==================================

test_intent_parser ............................ PASSED (1.2s)
test_retrieval ................................ PASSED (2.5s)
test_reranker ................................. PASSED (3.1s)
test_generator ................................ PASSED (18.4s)
test_validator ................................ PASSED (6.2s)
test_narrative ................................ PASSED (12.8s)
test_pipeline_end_to_end ...................... PASSED (35.7s)
test_error_handling_insufficient_data ......... PASSED (0.8s)
test_cost_tracking ............................ PASSED (0.3s)

9 tests passed, 0 failed (80.0s total)
Coverage: 95%
```

---

### `./crawl.sh quick-test`

Quick sanity check for Stage 5 pipeline (generates one test itinerary).

**Usage:**
```bash
./crawl.sh quick-test
```

**No flags required.**

**What It Does:**
- Generates a simple test itinerary: "3 days Bangkok solo budget party"
- Skips narrative generation for speed
- Shows validation results
- Displays cost and time metrics
- Returns exit code 0 if successful, 1 if failed

**Processing Time:** ~35-50 seconds
**Cost:** ~$0.01

**Output:**
```
Quick Stage 5 Test
==================

Query: "3 days Bangkok solo budget party"

Phase 1/7: Parsing query... ✅ (2.3s)
Phase 2/7: Retrieving entities... ✅ (2.8s)
Phase 3/7: Re-ranking... ✅ (3.1s)
Phase 4/7: Building context... ✅ (0.5s)
Phase 5/7: Generating itinerary... ✅ (16.2s)
Phase 6/7: Validating... ✅ (5.7s)
Phase 7/7: Formatting... ✅ (0.3s)

Results:
--------
Validation: ✅ PASSED (score: 0.95)
Processing Time: 30.9s
Total Cost: $0.0098
Hallucinations: 0
Budget: $180 for 3 days

Test Status: ✅ SUCCESS
```

**When to Use:**
- After installation to verify setup
- After code changes to ensure nothing broke
- Before important deployments
- As a health check for production monitoring

**Exit Codes:**
- `0` - Test passed
- `1` - Test failed

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
