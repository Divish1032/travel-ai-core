# S3-Only Pipeline Test Plan

## Pre-Test Cleanup

### 1. Clean S3 Bucket (Manual Step)

```bash
# List what's currently in S3
aws s3 ls s3://YOUR_BUCKET_NAME/raw/youtube/videos/ --recursive
aws s3 ls s3://YOUR_BUCKET_NAME/metadata/ --recursive

# Delete all test data (BE CAREFUL!)
aws s3 rm s3://YOUR_BUCKET_NAME/raw/youtube/videos/ --recursive
aws s3 rm s3://YOUR_BUCKET_NAME/metadata/ --recursive

# Verify it's empty
aws s3 ls s3://YOUR_BUCKET_NAME/raw/youtube/videos/
aws s3 ls s3://YOUR_BUCKET_NAME/metadata/
```

### 2. Clean Local State

```bash
# Remove any local data (if exists)
rm -rf data/
rm -f failed_urls_*.txt

# Keep only code and config
ls -la
```

## Test Scenario

### Phase 1: Initial Crawl (3 Videos)

**Create test_urls.txt:**
```bash
cat > test_urls.txt << EOF
https://www.youtube.com/watch?v=jNQXAC9IVRw
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.youtube.com/watch?v=9bZkp7q19f0
EOF
```

**Run crawl:**
```bash
./crawl.sh youtube --input test_urls.txt
```

**Expected Results:**
- ✅ Shows "Checking S3 for already processed videos..."
- ✅ Shows "No previously processed videos found in S3"
- ✅ 3 videos crawled successfully
- ✅ Data uploaded to S3: `s3://bucket/raw/youtube/videos/YYYY-MM/batch_TIMESTAMP.jsonl`
- ✅ MetadataTracker created: `s3://bucket/metadata/processing_status.jsonl`
- ✅ All videos marked as `stage_1_crawl: complete`

**Verification:**
```bash
# Check S3 contents
aws s3 ls s3://YOUR_BUCKET_NAME/raw/youtube/videos/ --recursive
aws s3 ls s3://YOUR_BUCKET_NAME/metadata/

# Check tracking status
./crawl.sh status

# Check stage 1 details
./crawl.sh stage stage_1_crawl

# Expected output:
# Total: 3
# Complete: 3
# Failed: 0
```

---

### Phase 2: Automatic Deduplication Test (Add 2 New Videos)

**Add 2 new URLs to test_urls.txt:**
```bash
cat >> test_urls.txt << EOF
https://www.youtube.com/watch?v=kJQP7kiw5Fk
https://www.youtube.com/watch?v=fJ9rUzIMcZQ
EOF
```

Now test_urls.txt has 5 URLs total (3 old + 2 new)

**Run crawl (no flags needed):**
```bash
./crawl.sh youtube --input test_urls.txt
```

**Expected Results:**
- ✅ Shows "Checking S3 for already processed videos..."
- ✅ Shows "Found 3 already processed videos in S3 (will skip)"
- ✅ Shows "Skipping 3 already processed videos"
- ✅ Shows "Remaining to crawl: 2 videos"
- ✅ Crawls only 2 new videos
- ✅ Total time: ~6-8 minutes (not 15 minutes)
- ✅ New batch created in S3

**Verification:**
```bash
# Should show 5 total videos now
./crawl.sh status

# Check stage 1
./crawl.sh stage stage_1_crawl
# Expected: Total: 5, Complete: 5

# List all S3 batches
aws s3 ls s3://YOUR_BUCKET_NAME/raw/youtube/videos/2025-01/ --recursive

# Should see 2 JSONL files:
# - First batch with 3 videos
# - Second batch with 2 videos
```

---

### Phase 3: Duplicate Test (No New Videos)

**Run same command again (automatic deduplication):**
```bash
./crawl.sh youtube --input test_urls.txt
```

**Expected Results:**
- ✅ Shows "Checking S3 for already processed videos..."
- ✅ Shows "Found 5 already processed videos in S3 (will skip)"
- ✅ Shows "Skipping 5 already processed videos"
- ✅ "No videos to crawl (all already processed)"
- ✅ No new S3 uploads
- ✅ Completes in <5 seconds

---

### Phase 4: Tracking Details Test

**View individual video details:**
```bash
# Get content_id from status
./crawl.sh status

# View specific video info
./crawl.sh info youtube_jNQXAC9IVRw
./crawl.sh info youtube_dQw4w9WgXcQ
```

**Expected Output for each:**
```
Content Details: youtube_abc123

┌─────────── Basic Information ───────────┐
│ Content ID     │ youtube_abc123          │
│ Source         │ youtube                 │
│ Title          │ Video Title             │
│ Source URL     │ https://youtube.com/... │
│ Added At       │ 2025-01-03T14:30:22Z    │
│ Last Updated   │ 2025-01-03T14:35:15Z    │
│ Pipeline Status│ stage_2_pending         │
│ Total Errors   │ 0                       │
└──────────────────────────────────────────┘

┌──────────── Stage Status ────────────────┐
│ Stage          │ Status   │ Duration     │
│ stage_1_crawl  │ complete │ 3m 45s       │
│ stage_2_chunk  │ not_started │ N/A      │
│ stage_3_extract│ not_started │ N/A      │
│ stage_4_normalize│ not_started │ N/A    │
│ stage_5_embed  │ not_started │ N/A      │
└──────────────────────────────────────────┘

S3 Output Paths:
  stage_1_crawl:
    - s3://bucket/raw/youtube/videos/2025-01/batch_...jsonl
```

---

### Phase 5: Export Test

**Export pipeline status to CSV:**
```bash
./crawl.sh export test_pipeline_status.csv

# View in Excel or:
head -20 test_pipeline_status.csv
```

**Expected CSV Columns:**
```
content_id,source,title,source_url,stage,status,started_at,completed_at,duration_seconds,retry_count,error,added_at,pipeline_status
youtube_jNQXAC9IVRw,youtube,Video Title,https://...,stage_1_crawl,complete,2025-01-03T14:30:22Z,2025-01-03T14:34:07Z,225.5,0,,2025-01-03T14:30:22Z,stage_2_pending
...
```

---

### Phase 6: Force Re-processing Test

**Test --force flag:**
```bash
./crawl.sh youtube --input test_urls.txt --force
```

**Expected Results:**
- ✅ Shows "⚠️  --force flag detected"
- ✅ Shows "⚠️  Skipping deduplication check - will re-process all videos"
- ✅ Does NOT check S3 for duplicates
- ✅ Attempts to crawl all 5 videos again
- ✅ Uploads new batch to S3
- ✅ MetadataTracker updated with new processing times

---

### Phase 7: Failed URL Test

**Add an invalid URL:**
```bash
cat >> test_urls.txt << EOF
https://www.youtube.com/watch?v=INVALID_VIDEO_ID
EOF
```

**Run crawl:**
```bash
./crawl.sh youtube --input test_urls.txt
```

**Expected Results:**
- ✅ Skips 5 already processed videos automatically
- ✅ Attempts to crawl invalid video
- ✅ Marks it as failed
- ✅ Creates `failed_urls_TIMESTAMP.txt` with failed URL
- ✅ Continues without crashing

**Verification:**
```bash
# Check for failed URLs file
ls -la data/raw/failed_urls_*.txt

# View failed items
./crawl.sh failed

# Check tracking
./crawl.sh status
# Should show: Complete: 5, Failed: 0 (or 1 if registered)
```

---

## Verification Checklist

### S3 Structure
```bash
# Should look like this:
aws s3 ls s3://YOUR_BUCKET_NAME/ --recursive

# Expected structure:
# raw/youtube/videos/2025-01/batch_TIMESTAMP1.jsonl  (3 videos)
# raw/youtube/videos/2025-01/batch_TIMESTAMP2.jsonl  (2 videos)
# metadata/processing_status.jsonl                    (5 videos tracked)
# metadata/backups/processing_status_TIMESTAMP1.jsonl
# metadata/backups/processing_status_TIMESTAMP2.jsonl
```

### Tracking Data
```bash
# Download and inspect metadata
aws s3 cp s3://YOUR_BUCKET_NAME/metadata/processing_status.jsonl ./

# Check contents
cat processing_status.jsonl | jq .

# Should have 5 entries, each with:
# - content_id: youtube_VIDEO_ID
# - source: youtube
# - source_url: https://youtube.com/watch?v=...
# - stages.stage_1_crawl.status: complete
# - pipeline_status: stage_2_pending
```

### No Local Data
```bash
# Verify no local data was created
ls -la data/  # Should NOT exist or be empty

# Only these should exist locally:
ls -la
# - test_urls.txt (input)
# - logs/ (temporary logs)
# - .env (config)
# - failed_urls_*.txt (if any failures)
```

---

## Success Criteria

All of these must be TRUE:

- [x] ✅ Videos crawled successfully to S3
- [x] ✅ MetadataTracker created and updated in S3
- [x] ✅ Resume flag skips already crawled videos
- [x] ✅ No duplicate processing
- [x] ✅ Tracking CLI shows correct status
- [x] ✅ No local data directory created
- [x] ✅ Failed URLs handled gracefully
- [x] ✅ S3 is single source of truth
- [x] ✅ Export to CSV works
- [x] ✅ Individual video info accessible

---

## Troubleshooting

### Issue: "S3 upload failed"
```bash
# Check AWS credentials
cat .env | grep AWS

# Test S3 access
aws s3 ls s3://YOUR_BUCKET_NAME/

# Check bucket name in .env
cat .env | grep S3_BUCKET_NAME
```

### Issue: "Already crawled videos not being skipped"
```bash
# Check MetadataTracker
aws s3 cp s3://YOUR_BUCKET_NAME/metadata/processing_status.jsonl ./
cat processing_status.jsonl | jq '.stages.stage_1_crawl.status'

# Deduplication is automatic - check the output for S3 check messages
./crawl.sh youtube --input test_urls.txt
```

### Issue: "No videos in tracking CLI"
```bash
# Check if metadata file exists
aws s3 ls s3://YOUR_BUCKET_NAME/metadata/

# Check file contents
aws s3 cp s3://YOUR_BUCKET_NAME/metadata/processing_status.jsonl ./
cat processing_status.jsonl

# Verify S3_BUCKET_NAME in .env matches
cat .env | grep S3_BUCKET_NAME
```

---

## Clean Up After Test

```bash
# Optional: Remove test files
rm test_urls.txt
rm test_pipeline_status.csv
rm processing_status.jsonl
rm -f data/raw/failed_urls_*.txt

# Keep S3 data for future stages
# OR delete if starting fresh:
# aws s3 rm s3://YOUR_BUCKET_NAME/raw/youtube/videos/ --recursive
# aws s3 rm s3://YOUR_BUCKET_NAME/metadata/ --recursive
```

---

## Next Steps

Once all tests pass:

1. ✅ Pipeline is ready for production use
2. ✅ Team members can collaborate using same S3 bucket
3. ✅ Start crawling actual video lists
4. ✅ Move to Stage 2 (Chunking) when ready

---

## Quick Test Commands

```bash
# Full test sequence
./crawl.sh youtube --input test_urls.txt              # Initial crawl
./crawl.sh status                                     # Check status
./crawl.sh youtube --input test_urls.txt              # Should skip all
./crawl.sh youtube --input test_urls.txt --force      # Force re-process
./crawl.sh stage stage_1_crawl                        # Stage details
./crawl.sh export test_status.csv                     # Export to CSV
```
