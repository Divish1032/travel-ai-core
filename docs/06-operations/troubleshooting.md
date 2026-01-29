# Troubleshooting Guide

Common issues and solutions for TravelAI pipeline.

---

## Stage 1: Crawling Issues

### YouTube API Quota Exceeded

**Error:**
```
FetchError: YouTube API quota exceeded
```

**Solution:**
1. Wait 24 hours for quota reset (10,000 units/day)
2. Use different API key
3. Request quota increase from Google Cloud Console

---

### Video Download Failed

**Error:**
```
yt-dlp error: Video unavailable
```

**Causes & Solutions:**
- **Age-restricted:** Use `--cookies-from-browser chrome`
- **Region-locked:** Use VPN or skip video
- **Private/deleted:** Skip video
- **Network timeout:** Check internet connection, retry

---

### Whisper Transcription Failed

**Error:**
```
Error: ffmpeg not found
```

**Solution:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Verify
ffmpeg -version
```

---

## Stage 2: Extraction Issues

### LLM API Rate Limit

**Error:**
```
RateLimitError: Exceeded requests per minute
```

**Solution:**
- Automatic retry with exponential backoff
- Reduce concurrent requests
- Upgrade to paid tier for higher limits

---

### Empty Entities Extracted

**Issue:** Video processed but 0 entities extracted

**Causes:**
1. **Non-travel content:** Video not about travel
2. **Poor transcript:** Whisper quality too low
3. **Language mismatch:** Non-English without translation
4. **LLM hallucination:** Retry with different provider

**Solution:**
```bash
# Check transcript quality
./crawl.sh view-stage1 youtube_abc123

# Re-process with different LLM
LLM_PROVIDER=openai ./crawl.sh process-stage2 --video-id youtube_abc123
```

---

### High Stage 2 Costs

**Issue:** $0.05+ per video (expected: $0.002-0.005)

**Causes:**
- Using OpenAI instead of Gemini
- Very long videos (>60 minutes)
- Re-processing already-completed videos

**Solution:**
```bash
# Switch to Gemini
LLM_PROVIDER=gemini

# Limit video duration
./crawl.sh youtube --max-duration 1800  # 30 minutes

# Check status before re-running
./crawl.sh status
```

---

## Stage 3: Canonicalization Issues

### Geocoding Failed

**Error:**
```
GeocodingError: Could not geocode "Unknown Restaurant"
```

**Impact:** Entity won't have lat/lon/geohash

**Solution:**
- Entity still usable via text search
- Add Google Maps API key for better geocoding success rate
- Manually verify entity names for ambiguous cases

---

### Over-merging Entities

**Issue:** Different entities incorrectly merged

**Example:**
```
"Patong Beach" + "Kata Beach" → Incorrectly merged
```

**Causes:**
- Fuzzy threshold too low
- LLM verification incorrect

**Solution:**
```bash
# Increase thresholds
FUZZY_AUTO_THRESHOLD=0.95  # Increase from 0.90
FUZZY_LLM_THRESHOLD=0.85   # Increase from 0.80

# Re-run Stage 3
./crawl.sh reset-stage3
./crawl.sh process-stage3
```

---

### Under-merging Entities

**Issue:** Same entity appears multiple times

**Example:**
```
"Grand Palace" and "The Grand Palace" → Not merged
```

**Causes:**
- Fuzzy threshold too high
- Missing LLM verification

**Solution:**
```bash
# Decrease thresholds
FUZZY_AUTO_THRESHOLD=0.85  # Decrease from 0.90

# Re-run Stage 3
./crawl.sh reset-stage3
./crawl.sh process-stage3
```

---

## Stage 4: Vectorization Issues

### ChromaDB Connection Failed

**Error:**
```
ConnectionError: Could not connect to ChromaDB
```

**Solution:**
```bash
# Verify credentials
echo $CHROMA_API_KEY
echo $CHROMA_SERVER_URL

# Test connection
./crawl.sh check-stage5-ready

# Check Chroma Cloud dashboard
open https://app.trychroma.com/
```

---

### Embedding Generation Slow

**Issue:** >5 seconds per entity

**Causes:**
- CPU-only (no GPU)
- Large batch size
- Network latency

**Solution:**
```bash
# Reduce batch size
EMBEDDING_BATCH_SIZE=16  # Default: 32

# Use GPU if available (requires CUDA)
pip install sentence-transformers[gpu]
```

---

### Metadata Too Large

**Error:**
```
MetadataError: Metadata exceeds 4KB limit
```

**Solution:**
- Automatic truncation of long fields
- Check logs for truncated fields
- Review entity data for excessive text

---

## Stage 5: RAG Issues

### Insufficient Data for Destination

**Error:**
```
InsufficientDataError: Not enough entities for "Tokyo"
```

**Solution:**
1. Crawl more Tokyo videos (Stage 1)
2. Process through Stages 2-4
3. Query different destination with more data

---

### Low VIBE Match Score

**Issue:** Generated itinerary has vibe_match_score < 7.0

**Causes:**
- Query too vague
- Insufficient entities matching VIBE
- LLM hallucination

**Solution:**
```bash
# Be more specific in query
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget street food morning person"

# Check available entities
./crawl.sh search --query "Bangkok budget food" --limit 50

# Retry with different LLM
LLM_PROVIDER=openai ./crawl.sh generate-itinerary -q "..."
```

---

### Validation Failed

**Error:**
```
ValidationError: Itinerary score 6.2/10 (threshold: 7.0)
Issues: Entity "ABC" not found, Day 2 timing overlap
```

**Solution:**
- Automatic retry (max 2 times)
- Review logs for specific issues
- Lower validation threshold if needed: `RAG_VALIDATION_THRESHOLD=6.5`

---

## General Issues

### AWS Credentials Not Found

**Error:**
```
NoCredentialsError: Unable to locate credentials
```

**Solution:**
```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1

# Verify
aws s3 ls
```

---

### Module Not Found

**Error:**
```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
```bash
# Ensure virtual environment activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Use crawl.sh (sets PYTHONPATH automatically)
./crawl.sh status
```

---

### Out of Memory

**Error:**
```
MemoryError: Unable to allocate array
```

**Causes:**
- Whisper model too large
- Processing too many entities at once
- Insufficient RAM

**Solution:**
```bash
# Use smaller Whisper model
WHISPER_MODEL=small  # Or: tiny, base

# Reduce batch sizes
EMBEDDING_BATCH_SIZE=16
./crawl.sh process-stage2 --limit 10  # Process in smaller batches
```

---

## Performance Issues

### Slow Pipeline

**Symptoms:** Stages take 2-3x expected time

**Diagnosis:**
```bash
# Check logs
tail -f logs/travelai.log

# Monitor system resources
top  # or htop

# Check network
ping google.com
```

**Solutions:**
1. **LLM API latency:** Switch to faster provider (Gemini)
2. **Network issues:** Check internet connection
3. **CPU bottleneck:** Use smaller models, reduce batch sizes
4. **Disk I/O:** Use SSD for cache/logs

---

## Debugging Tips

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG ./crawl.sh process-stage2
```

### Check Logs

```bash
# View recent logs
tail -100 logs/travelai.log

# Search for errors
grep -i error logs/travelai.log

# View specific stage logs
grep "Stage 2" logs/travelai.log
```

### Validate Data

```bash
# Check Stage 1 output
./crawl.sh view-stage1 youtube_abc123

# Check Stage 2 output
./crawl.sh view-stage2 youtube_abc123

# Validate Stage 3
./crawl.sh validate-stage3

# Check Stage 4 stats
./crawl.sh stage4-stats
```

---

## Getting Help

### Check Documentation

1. [Installation Guide](../01-getting-started/installation.md)
2. [CLI Commands](../04-reference/cli-commands.md)
3. [Configuration](../04-reference/configuration.md)

### Report Issues

1. Check existing issues: [GitHub Issues](https://github.com/your-repo/issues)
2. Create new issue with:
   - Error message
   - Relevant logs
   - Steps to reproduce
   - Environment info (OS, Python version)

---

## Prevention Tips

### Regular Maintenance

```bash
# Check status regularly
./crawl.sh status

# Monitor costs
cat stage5-costs/*.json

# Backup data
./crawl.sh backup-vectors
```

### Best Practices

1. **Test with small batches first** (`--limit 10`)
2. **Use Gemini for cost efficiency**
3. **Enable debug logging when testing**
4. **Monitor API quotas and costs**
5. **Keep dependencies updated:** `pip install --upgrade -r requirements.txt`

---

## References

- **Error Handling:** [error-handling.md](error-handling.md)
- **Runbook:** [runbook.md](runbook.md)
- **Backup & Recovery:** [backup-recovery.md](backup-recovery.md)
