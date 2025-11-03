# Travel AI

YouTube travel vlog crawler with S3 storage and automatic deduplication.

## What This Does

**Stage 1 (Current)**: Crawls YouTube videos, extracts metadata + transcripts, stores in S3.

- S3-only storage (single source of truth for teams)
- Automatic deduplication (skips already processed videos)
- MetadataTracker for pipeline stage tracking
- Whisper-based transcription fallback

## Prerequisites

- Python 3.11+
- AWS Account with S3 access

## Setup

```bash
# Clone repo
git clone <your-repo-url>
cd TravelAI

# Run automated setup (recommended)
./setup.sh

# The setup script will:
# - Check Python 3.11+ is installed
# - Create virtual environment
# - Install all dependencies
# - Create necessary directories
# - Set up .env file
# - Verify AWS credentials
# - Run basic tests
```

After setup, activate the virtual environment:
```bash
source venv/bin/activate  # Windows: venv\Scripts\activate
```

## Usage

### Stage 1: Crawl YouTube Videos

```bash
# Create URLs file
cat > urls.txt << EOF
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2
EOF

# Crawl videos (automatically skips duplicates)
./crawl.sh youtube --input urls.txt

# Test with limited videos
./crawl.sh youtube --input urls.txt --limit 5

# Force re-processing (overwrites existing data)
./crawl.sh youtube --input urls.txt --force

# Dry run (preview without crawling)
./crawl.sh youtube --input urls.txt --dry-run
```

**Note**: `crawl.sh` is a helper script that automatically sets `PYTHONPATH`. You can also run directly:
```bash
PYTHONPATH=. python cli/crawl.py youtube --input urls.txt
```

### Tracking Commands

```bash
# View pipeline status
./crawl.sh status

# View specific stage details
./crawl.sh stage stage_1_crawl

# List failed items
./crawl.sh failed

# View specific video info
./crawl.sh info youtube_VIDEO_ID

# Export to CSV
./crawl.sh export pipeline_status.csv
```

### Validate Pipeline

```bash
# Check S3 connectivity, MetadataTracker, and data consistency
python validate_pipeline.py
```

## How It Works

1. **Deduplication**: Always checks S3 for already processed videos (unless `--force` is used)
2. **Crawling**: Fetches metadata + transcripts using yt-dlp + Whisper
3. **S3 Upload**: Stores data in `s3://bucket/raw/youtube/videos/YYYY-MM/batch_TIMESTAMP.jsonl`
4. **Tracking**: Updates MetadataTracker in `s3://bucket/metadata/processing_status.jsonl`

## S3 Structure

```
s3://your-bucket/
├── raw/youtube/videos/YYYY-MM/
│   └── batch_TIMESTAMP.jsonl        # Raw video data
└── metadata/
    ├── processing_status.jsonl      # Pipeline tracking
    └── backups/
        └── processing_status_*.jsonl
```

## Testing

```bash
# Run tests
pytest tests/

# Validate pipeline
python validate_pipeline.py

# Test with sample URLs
./crawl.sh youtube --input test_urls.txt --limit 3
```

## Project Structure

```
TravelAI/
├── cli/
│   ├── crawl.py           # Main crawler CLI
│   └── tracking.py        # Tracking CLI
├── src/
│   ├── crawlers/
│   │   └── youtube.py     # YouTube crawler
│   ├── storage/
│   │   └── s3.py          # S3 storage
│   └── utils/
│       ├── metadata_tracker.py  # Pipeline tracking
│       ├── content_id.py        # Content ID generation
│       └── schemas.py           # Data models
├── tests/                 # Tests
├── crawl.sh              # Helper script (sets PYTHONPATH)
└── validate_pipeline.py  # Pipeline validation
```

## Troubleshooting

**S3 upload failed**:
```bash
# Check AWS credentials
cat .env | grep AWS

# Test S3 access
aws s3 ls s3://your-bucket/
```

**Module not found**:
```bash
# Use helper script (sets PYTHONPATH automatically)
./crawl.sh youtube --input urls.txt

# Or set PYTHONPATH manually
export PYTHONPATH=/path/to/TravelAI
python cli/crawl.py youtube --input urls.txt
```

**Already processed videos not being skipped**:
- Deduplication is automatic, check S3 connection
- Use `./crawl.sh status` to verify tracking data

## Team Workflow

All data is stored in S3 only (no local data files). This ensures:
- Single source of truth across team members
- Automatic deduplication
- No git conflicts from data files

```bash
# Developer A
./crawl.sh youtube --input urls.txt

# Developer B (same day, different machine)
git pull
./crawl.sh youtube --input urls.txt
# ✅ Automatically skips videos A already crawled
```

## License

MIT License
