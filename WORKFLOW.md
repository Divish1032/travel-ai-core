# Travel AI - Production Workflow (S3-Only)

## Architecture: Single Source of Truth

All data is stored in **S3 only** (no local data directories). This ensures:
- ✅ Team members always see the same data
- ✅ No git conflicts from data files
- ✅ No sync issues between team members
- ✅ Single source of truth for pipeline status
- ✅ Automatic deduplication via MetadataTracker

## Quick Start

### 1. Setup (One-Time)

```bash
# Clone repo
git clone <repo-url>
cd TravelAI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials
cp .env.example .env
# Edit .env with your AWS credentials
```

### 2. Crawl YouTube Videos

```bash
# Create urls.txt with your YouTube URLs
cat > urls.txt << EOF
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2
https://www.youtube.com/watch?v=VIDEO_ID_3
EOF

# Crawl and upload to S3 (automatically skips already processed videos)
./crawl.sh youtube --input urls.txt

# Force re-processing of all videos (ignores deduplication)
./crawl.sh youtube --input urls.txt --force

# Test with limited videos
./crawl.sh youtube --input urls.txt --limit 5
```

### 3. Check Status

```bash
# View overall pipeline status
./crawl.sh status

# View specific stage details
./crawl.sh stage stage_1_crawl

# List failed items
./crawl.sh failed

# View specific content details
./crawl.sh info youtube_abc123
```

## S3 Data Structure

```
s3://your-bucket/
├── raw/youtube/videos/              # Raw crawled videos
│   └── 2025-01/
│       ├── batch_20250103_143022.jsonl
│       └── batch_20250104_091530.jsonl
├── metadata/
│   ├── processing_status.jsonl      # 👈 SINGLE SOURCE OF TRUTH
│   └── backups/
│       └── processing_status_*.jsonl
└── (future: chunked/, extracted/, etc.)
```

## Team Workflow

### Developer A (First Run)
```bash
# Add URLs
echo "https://youtube.com/watch?v=abc123" >> urls.txt

# Crawl
./crawl.sh youtube --input urls.txt

# ✅ Data goes to S3
# ✅ MetadataTracker updated in S3
```

### Developer B (Same Day, Different Machine)
```bash
# Pull latest code
git pull

# Run crawler (automatically checks S3)
./crawl.sh youtube --input urls.txt

# ✅ Automatically checks S3 MetadataTracker
# ✅ Skips videos A already crawled
# ✅ No duplicates!
# ✅ No flags needed - safe by default!
```

### Anyone (Check Status)
```bash
./crawl.sh status
# ✅ Shows complete picture from S3
```

## URL Management

### Option 1: Single urls.txt (Recommended for MVP)
```bash
# Keep adding to same file
echo "https://youtube.com/watch?v=NEW_VIDEO" >> urls.txt

# Run crawler (automatically skips duplicates)
./crawl.sh youtube --input urls.txt
```

### Option 2: Dated Batches (For Organization)
```
urls/
├── 2025-01-batch1.txt
├── 2025-01-batch2.txt
└── 2025-02-batch1.txt

# Process each batch
./crawl.sh youtube --input urls/2025-01-batch1.txt
```

## Deduplication

The system **automatically** prevents duplicate processing:

1. **MetadataTracker** (S3-based) tracks all processed videos
2. **Always checks S3** before crawling (no flag needed!)
3. **content_id** uniquely identifies each video
4. **`--force` flag** available for intentional re-processing

```bash
# Safe to run multiple times - automatically skips duplicates
./crawl.sh youtube --input urls.txt
./crawl.sh youtube --input urls.txt  # Skips all (safe by default!)

# Force re-processing when needed
./crawl.sh youtube --input urls.txt --force
```

## What's in Git vs S3

### Git (Code Only)
- ✅ Source code (src/, cli/, tests/)
- ✅ Configuration templates (.env.example)
- ✅ URL lists (urls.txt) - optional
- ✅ Documentation (README.md, WORKFLOW.md)
- ❌ NO data files
- ❌ NO logs
- ❌ NO .env (secrets)

### S3 (Data Only)
- ✅ Raw crawled data (raw/youtube/videos/)
- ✅ Metadata/tracking (metadata/processing_status.jsonl)
- ✅ Processed data (future stages)
- ✅ Backups (metadata/backups/)

### Local (Ephemeral Only)
- Logs (logs/) - gitignored
- Temp files during processing - auto-cleaned
- NO persistent data

## Troubleshooting

### "S3 upload failed"
```bash
# Check AWS credentials
cat .env  # Verify AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# Test S3 access
aws s3 ls s3://your-bucket/

# Check logs
tail -f logs/errors_*.log
```

### "Already crawled videos not being skipped"
```bash
# Deduplication is automatic - check what's in S3
./crawl.sh status
./crawl.sh stage stage_1_crawl

# If you need to force re-processing
./crawl.sh youtube --input urls.txt --force
```

### "Module not found" errors
```bash
# Make sure PYTHONPATH is set
export PYTHONPATH=/path/to/TravelAI

# Or use the helper script (sets PYTHONPATH automatically)
./crawl.sh youtube --input urls.txt
```

## Best Practices

1. **Deduplication is automatic** - just run the crawler, it checks S3 automatically
2. **Test with `--limit`** before full crawl
3. **Check status regularly**: `./crawl.sh status`
4. **Keep urls.txt in git** (it's just URLs, not data)
5. **Never commit data/** directory (already .gitignored)
6. **Use helper script** (`./crawl.sh`) for convenience
7. **Use `--force` only when needed** for intentional re-processing

## Next Steps (Future Stages)

1. **Stage 1** (Complete): Crawl YouTube videos → S3
2. **Stage 2** (TODO): Chunk transcripts → S3
3. **Stage 3** (TODO): Extract entities → S3
4. **Stage 4** (TODO): Normalize data → S3
5. **Stage 5** (TODO): Generate embeddings → S3

Each stage uses MetadataTracker for deduplication and progress tracking.
