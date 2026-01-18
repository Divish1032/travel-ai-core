# Entity Extraction Pipeline Debugger

A comprehensive debugging tool for testing and analyzing the 3-stage entity extraction pipeline.

## Overview

This tool allows you to test the entire entity extraction pipeline with a single YouTube video and generates detailed HTML reports showing:

- **Stage 1 (YouTube Crawling)**: Video metadata, transcript quality, duration
- **Stage 2 (Entity Extraction)**: Extracted entities, quality scores, LLM costs
- **Stage 3 (Deduplication)**: Duplicate detection, deduplication statistics

## Usage
<!-- https://www.youtube.com/watch?v=5PtysfqW1GM -->
### Basic Command

```bash
./crawl.sh debug-extraction --url "https://youtube.com/watch?v=VIDEO_ID"
```

### With Custom Output Directory

```bash
./crawl.sh debug-extraction --url "https://youtube.com/watch?v=VIDEO_ID" --output-dir my_debug_reports/
```

### Direct Python Execution

```bash
python scripts/debug_entity_extraction.py --url "https://youtube.com/watch?v=VIDEO_ID"
```

## Output

The tool generates two report files:

1. **JSON Report**: Raw data for programmatic analysis
   - Location: `debug_reports/debug_{VIDEO_ID}_{TIMESTAMP}.json`
   - Contains all stage metrics, timings, and results

2. **HTML Report**: Visual interactive report
   - Location: `debug_reports/debug_{VIDEO_ID}_{TIMESTAMP}.html`
   - Open in browser for beautiful, interactive analysis

## What It Tests

### Stage 1: YouTube Crawling
- ✅ Video metadata fetching (title, channel, views, duration)
- ✅ Transcript extraction (segments, word count)
- ✅ Transcript quality assessment (words/minute, length)
- ✅ Language detection

### Stage 2: Entity Extraction
- ✅ LLM-based entity extraction
- ✅ Entity type distribution (attractions, restaurants, etc.)
- ✅ Quality score calculation
- ✅ Location and price coverage metrics
- ✅ Traveler profile extraction
- ✅ Token usage and cost tracking

### Stage 3: Deduplication
- ✅ Exact match detection (Tier 1)
- ✅ Fuzzy match detection (Tier 2)
- ✅ Deduplication statistics
- ✅ Unique entity count

## Example Use Cases

### 1. Test New Video Before Processing

```bash
# Before adding video to production pipeline, test it first
./crawl.sh debug-extraction --url "https://youtube.com/watch?v=NEW_VIDEO"
```

**What to check:**
- Is transcript quality "Good" or "Excellent"?
- Are entities being extracted correctly?
- What's the LLM cost per video?

### 2. Debug Extraction Quality Issues

```bash
# If you notice poor extraction quality, debug a sample video
./crawl.sh debug-extraction --url "https://youtube.com/watch?v=PROBLEM_VIDEO"
```

**What to look for:**
- Low word count → Bad transcript
- Low quality scores → Improve LLM prompts
- Missing locations → Enhance extraction prompts

### 3. Measure Pipeline Performance

```bash
# Test multiple videos to measure average performance
for video in video1 video2 video3; do
    ./crawl.sh debug-extraction --url "https://youtube.com/watch?v=$video"
done
```

**Metrics to track:**
- Average execution time per stage
- Average LLM cost per video
- Average entity count
- Deduplication rate

### 4. Validate LLM Prompt Changes

```bash
# After modifying extraction prompts, test with known video
./crawl.sh debug-extraction --url "https://youtube.com/watch?v=BASELINE_VIDEO"
```

**Compare:**
- Entity count before/after
- Quality scores before/after
- Cost impact

## Report Metrics Explained

### Transcript Quality Assessment

| Assessment | Criteria |
|-----------|----------|
| **Excellent** | 100-180 words/min, 50+ segments |
| **Good** | 80-200 words/min, reasonable length |
| **Fair** | Outside optimal range but usable |
| **Poor** | <50 or >200 words/min, or <10 segments |

### Entity Quality Score

- **5.0**: Verified with GPS, price, rating
- **4.0**: High confidence with most details
- **3.0**: Moderate confidence, some details
- **2.0**: Low confidence, minimal details
- **1.0**: Very uncertain mention

### Coverage Metrics

- **Location Coverage**: % of entities with location data
- **Price Coverage**: % of entities with price information

### Deduplication Rate

```
Deduplication Rate = (Duplicates Found / Total Entities) × 100
```

- **0-10%**: Low redundancy (good)
- **10-30%**: Moderate redundancy (normal)
- **30%+**: High redundancy (investigate why)

## Troubleshooting

### "Failed to crawl video"
- Check internet connection
- Verify YouTube API key is set in `.env`
- Ensure video is public and has captions

### "Entity extraction failed"
- Check LLM API key (Gemini/DeepSeek)
- Verify API quota isn't exceeded
- Check transcript quality in Stage 1

### "No entities extracted"
- Video might not be travel-related
- Transcript quality might be too poor
- LLM prompt might need adjustment

## Cost Estimation

Typical costs per video (as of 2026):

| Stage | Service | Typical Cost |
|-------|---------|--------------|
| Stage 1 | YouTube API | $0.0000 (quota-based) |
| Stage 2 | DeepSeek/Gemini | $0.0001 - $0.0005 |
| Stage 3 | Computation | $0.0000 (local) |
| **Total** | | **~$0.0005/video** |

## Next Steps

After debugging:

1. **If quality is good** → Add video to production pipeline
2. **If quality is poor** → Investigate specific issues using report
3. **If consistent issues** → File bug report with JSON report attached
4. **If prompt changes needed** → Update prompts in `src/processors/extraction_prompts.py`

## Files Generated

```
debug_reports/
├── debug_VIDEO_ID_20260113_123456.json  # Raw data
└── debug_VIDEO_ID_20260113_123456.html  # Visual report
```

**Keep these reports** when filing bug reports or discussing improvements!

## Advanced Usage

### Batch Testing

```bash
# Test multiple videos and collect all reports
cat video_urls.txt | while read url; do
    ./crawl.sh debug-extraction --url "$url"
    sleep 5  # Rate limiting
done
```

### Programmatic Analysis

```python
import json

# Load JSON report
with open('debug_reports/debug_VIDEO_ID_TIMESTAMP.json') as f:
    report = json.load(f)

# Analyze metrics
entity_count = report['stages']['stage2']['entity_statistics']['total_entities']
avg_quality = report['stages']['stage2']['entity_statistics']['average_quality_score']
llm_cost = report['stages']['stage2']['llm_metrics']['cost_usd']

print(f"Extracted {entity_count} entities with quality {avg_quality} for ${llm_cost}")
```

## Contributing

Found bugs or have suggestions? Update:
- Script: `scripts/debug_entity_extraction.py`
- This README: `scripts/README_DEBUG.md`
