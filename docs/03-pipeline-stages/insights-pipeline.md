# Insights Pipeline Documentation

## Overview

The **Insights Pipeline** is a parallel processing system that extracts reusable travel knowledge (services, tips, logistics) from video content. Unlike the main entity pipeline which focuses on **places** (restaurants, hotels, attractions), the insights pipeline captures **actionable travel advice** that isn't tied to specific locations.

**Key Features:**
- Destination-agnostic design (works globally, not Thailand-specific)
- Dual-pass extraction (filtered entities + info-only videos)
- 3-tier deduplication (exact, semantic, LLM verification)
- Quality scoring (quality, freshness, applicability)
- Cost-efficient (Gemini Flash 2.5 Lite - FREE tier)

---

## Table of Contents

1. [Architecture](#architecture)
2. [Data Flow](#data-flow)
3. [Insight Categories](#insight-categories)
4. [Extraction Passes](#extraction-passes)
5. [Deduplication](#deduplication)
6. [Quality Scoring](#quality-scoring)
7. [Storage Structure](#storage-structure)
8. [Usage](#usage)
9. [Schema Reference](#schema-reference)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      INSIGHTS PIPELINE                          │
│                  (Parallel to Entity Pipeline)                  │
└─────────────────────────────────────────────────────────────────┘

Input Sources:
┌──────────────────────┐    ┌──────────────────────┐
│  Filtered Entities   │    │  Info-Only Videos    │
│  (Stage 3 output)    │    │  (<5 place entities) │
│  • Apps & websites   │    │  • Tips & advice     │
│  • Packing items     │    │  • How-to guides     │
│  • Transport modes   │    │  • Service reviews   │
└──────────────────────┘    └──────────────────────┘
         │                            │
         │                            │
         ▼                            ▼
    ┌────────────────────────────────────┐
    │      PASS 1: Entity Enrichment     │
    │   Extract insights from filtered   │
    │   entities (1-3 insights/entity)   │
    └────────────────────────────────────┘
                    │
                    ▼
    ┌────────────────────────────────────┐
    │    PASS 2: Transcript Extraction   │
    │  Extract insights from transcripts │
    │   (5-15 insights/video, chunked)   │
    └────────────────────────────────────┘
                    │
                    ▼
    ┌────────────────────────────────────┐
    │         DEDUPLICATION              │
    │  Tier 1: Exact content match       │
    │  Tier 2: Semantic similarity       │
    │  Tier 3: LLM verification          │
    └────────────────────────────────────┘
                    │
                    ▼
    ┌────────────────────────────────────┐
    │      CANONICALIZATION              │
    │  • Choose consensus content        │
    │  • Merge mentions & videos         │
    │  • Calculate quality scores        │
    └────────────────────────────────────┘
                    │
                    ▼
    ┌────────────────────────────────────┐
    │      CANONICAL INSIGHTS            │
    │  • Stable IDs (INS_CAT_###)        │
    │  • Quality/freshness/applicability │
    │  • Ready for retrieval/indexing    │
    └────────────────────────────────────┘
```

---

## Data Flow

### Phase 1: Prerequisites (Completed)
- **Phase 1A**: Entity filtering (identifies non-place entities with `insights_candidate: true`)
- **Phase 1B**: Stage 2 guardrails (prevents non-places from entering entity pipeline)

### Phase 2: Insights Pipeline

#### Phase 2A: Foundation ✅
- [schemas.py](../src/utils/schemas.py) - Data models (TravelInsight, CanonicalInsight, InsightScope)
- [insights_storage.py](../src/storage/insights_storage.py) - S3 storage manager
- [insight_registry.py](../src/storage/insight_registry.py) - ID tracking and deduplication cache
- [metadata_tracker.py](../src/utils/metadata_tracker.py) - Added `insights_pipeline` stage

#### Phase 2B: Extraction ✅
- [insight_prompts.py](../src/processors/insight_prompts.py) - LLM prompts for Pass 1 & Pass 2
- [insights_extractor.py](../src/processors/insights_extractor.py) - Extraction engine
- [process_insights.py](../cli/process_insights.py) - CLI orchestrator

#### Phase 2C: Deduplication & Canonicalization ✅
- [insight_deduplication.py](../src/processors/insight_deduplication.py) - 3-tier deduplication
- [insight_canonicalization.py](../src/processors/insight_canonicalization.py) - Merging and scoring

#### Phase 2D: Tools & Documentation ✅
- [reset_insights.py](../cli/reset_insights.py) - Reset command
- [insights_stats.py](../cli/insights_stats.py) - Statistics display
- [crawl.sh](../crawl.sh) - Updated with insights commands
- **This document** - Comprehensive documentation

---

## Insight Categories

The pipeline extracts insights into **8 categories**:

| Category | Description | Examples |
|----------|-------------|----------|
| **services** | Apps, booking platforms, digital tools | "Use Grab app for ride-hailing", "12goasia for bus booking" |
| **logistics** | How-to guides, visa processes, getting around | "Visa on arrival process", "Airport to city by train" |
| **tips** | Practical travel advice, packing, money | "Pack Type C adapter", "Bring cash for markets" |
| **regional** | Area-specific knowledge (traffic, neighborhoods) | "Bangkok traffic worst 5-7pm", "Khao San Road nightlife" |
| **cultural** | Customs, etiquette, dos/don'ts | "Remove shoes at temples", "Dress modestly" |
| **safety** | Security, scams, health warnings | "Taxi meter scams at airport", "Get travel insurance" |
| **cost_info** | Price ranges, budget advice, value for money | "Street food $1-3", "Budget $40-60/day mid-range" |
| **seasonal** | Weather, best times to visit, timing | "Rainy season June-October", "Book 3 months ahead" |

---

## Extraction Passes

### Pass 1: Entity Enrichment

**Input**: Filtered non-place entities from Stage 3 (apps, websites, packing items, etc.)

**Process**:
1. Load filtered entities with `insights_candidate: true` flag
2. For each entity, extract 1-3 actionable insights
3. Use entity name + experience description + video context
4. Validate against TravelInsight schema

**Example**:
```
Entity: "Grab app"
Filter Reason: "apps_websites"
Experience: "Use Grab for ride-hailing. Cheaper than taxis."

Extracted Insights:
1. Category: services
   Content: "Use Grab app for ride-hailing in Southeast Asia. Much cheaper than taxis and very reliable."
   Scope: region (Southeast Asia)
   Confidence: 0.90
```

**Expected Output**: ~200 insights from ~200 filtered entities

### Pass 2: Transcript Extraction

**Input**: Info-only videos with <5 place entities (threshold configurable)

**Process**:
1. Identify videos with low place entity count
2. Split transcript into chunks (4000 words/chunk, 200 word overlap)
3. Extract 5-15 insights per video
4. Deduplicate within same video (exact content match)

**Example**:
```
Video: "Top 10 Thailand Travel Tips"
Place Entities: 3 (low count → info-only video)

Extracted Insights:
1. "Download offline maps before traveling"
2. "Pack Type C power adapter for Thailand"
3. "Use ride-hailing apps instead of street taxis"
... (10 total)
```

**Expected Output**: ~30 videos × 8 insights = ~240 insights

---

## Deduplication

### 3-Tier System

#### Tier 1: Exact Content Match (Hash-Based)
- **Method**: MD5 hash of normalized content + category + scope
- **Threshold**: 100% match
- **Cost**: FREE (instant)
- **Purpose**: Catch identical insights (copy-paste, repeated mentions)

**Example**:
```
Insight 1: "Use Grab app for ride-hailing"
Insight 2: "Use grab app for ride-hailing"  # Same (normalized)
→ Exact match (Tier 1)
```

#### Tier 2: Semantic Similarity (Embeddings)
- **Method**: Cosine similarity between embedding vectors
- **Threshold**: ≥0.90 auto-merge
- **Cost**: FREE (cached embeddings)
- **Purpose**: Catch paraphrased insights (same meaning, different words)

**Example**:
```
Insight 1: "Use Grab app for ride-hailing"
Insight 2: "Use Grab to get around the city"  # Similar meaning
→ Similarity: 0.93 → Auto-merge (Tier 2)
```

#### Tier 3: LLM Verification (Ambiguous Cases)
- **Method**: Gemini Flash 2.5 Lite LLM judgment
- **Threshold**: 0.80-0.90 similarity range
- **Min Confidence**: 0.7 to confirm match
- **Cost**: ~$0.00 (FREE tier, 1500 req/day)
- **Purpose**: Verify ambiguous semantic matches

**Example**:
```
Insight 1: "Pack Type C power adapter"
Insight 2: "Bring power adapter for Europe"  # Ambiguous
→ Similarity: 0.85 → LLM verification
→ LLM: "Match (confidence: 0.92)" → Merge (Tier 3)
```

### Deduplication Stats

Expected results:
- **Input**: ~440 raw insights (200 Pass 1 + 240 Pass 2)
- **Tier 1 duplicates**: ~50 insights (exact copies)
- **Tier 2 duplicates**: ~40 insights (high similarity)
- **Tier 3 duplicates**: ~20 insights (LLM verified)
- **Output**: ~330 unique canonical insights

---

## Quality Scoring

Each canonical insight gets **3 quality scores** (0.0-1.0):

### 1. Quality Score
**Measures**: Content completeness and reliability

**Factors** (weighted average):
- **Content length** (25%): Longer = more detail = higher quality
  - 50 chars = 0.0, 200+ chars = 1.0
- **Average confidence** (35%): From extraction confidence scores
- **Mention count** (25%): More mentions = higher quality
  - 1 mention = 0.5, 5+ mentions = 1.0
- **Completeness** (15%): Has title, has details

**Example**:
```
Insight: "Use Grab app for ride-hailing in Southeast Asia. Cheaper than taxis, reliable, accepts credit cards."
- Length: 110 chars → 0.60
- Confidence: 0.90
- Mentions: 3 → 0.75
- Complete: Has title + details → 1.0
Quality Score: 0.25(0.60) + 0.35(0.90) + 0.25(0.75) + 0.15(1.0) = 0.82
```

### 2. Freshness Score
**Measures**: How recent the insight is

**Formula**:
- 0-30 days old: 1.0 (very fresh)
- 30-180 days old: 1.0 → 0.5 (linear decay)
- 180+ days old: 0.5 (somewhat stale)

**Example**:
```
Extraction date: 2026-01-15
Current date: 2026-01-29
Age: 14 days → Freshness: 1.0
```

### 3. Applicability Score
**Measures**: How broadly applicable the insight is

**Factors** (weighted average):
- **Scope breadth** (60%): How wide the scope
  - Global: 1.0
  - Region: 0.8
  - Country: 0.6
  - City: 0.4
  - Area: 0.2
- **Video diversity** (40%): How many unique sources
  - 1 video = 0.5, 5+ videos = 1.0

**Example**:
```
Insight: "Get travel insurance before international trips"
- Scope: global → 1.0
- Videos: 8 unique sources → 1.0
Applicability Score: 0.6(1.0) + 0.4(1.0) = 1.0
```

---

## Storage Structure

### S3 Layout

```
insights-pipeline/
├── extracted/                     # Raw extracted insights
│   ├── new/
│   │   ├── pass1_20260127_143025.jsonl     # Pass 1 output
│   │   ├── pass2_20260127_143530.jsonl     # Pass 2 output
│   │   └── pass_all_20260127_144012.jsonl  # Combined
│   └── processed/                 # Moved after processing
│
├── canonical/                     # Deduplicated canonical insights
│   ├── new/
│   │   ├── insights_all_20260127_150015.jsonl
│   │   ├── by_category/
│   │   │   ├── services.jsonl
│   │   │   ├── logistics.jsonl
│   │   │   ├── tips.jsonl
│   │   │   └── ...
│   │   ├── by_destination/
│   │   │   ├── global.jsonl
│   │   │   ├── region_southeast_asia.jsonl
│   │   │   ├── thailand.jsonl
│   │   │   └── ...
│   │   └── metadata/
│   │       └── processing_stats.json
│   └── processed/
│
├── registry/                      # Insight registry cache
│   └── insight_registry.json
│
└── filtered/                      # Filtered entities (from Stage 3)
    └── (symlink to stage3-canonical/filtered/)
```

### File Formats

#### Extracted Insights (JSONL)
```json
{
  "content": "Use Grab app for ride-hailing in Southeast Asia",
  "title": "Grab for rides",
  "category": "services",
  "scope": {
    "destination_type": "region",
    "region": "Southeast Asia"
  },
  "confidence_score": 0.90,
  "mention_count": 1,
  "video_count": 1,
  "provenance": {
    "source_video_ids": ["youtube_abc123"],
    "extraction_method": "entity_enrichment",
    "extraction_date": "2026-01-27T14:30:25Z"
  },
  "tags": ["app", "transportation", "ride-hailing"]
}
```

#### Canonical Insights (JSONL)
```json
{
  "insight_id": "INS_SVC_001",
  "category": "services",
  "content": "Use Grab app for ride-hailing in Southeast Asia. Much cheaper than taxis and accepts credit cards.",
  "title": "Grab app for rides",
  "scope": {
    "destination_type": "region",
    "region": "Southeast Asia"
  },
  "confidence_score": 0.92,
  "mention_count": 3,
  "video_count": 3,
  "provenance": {
    "source_video_ids": ["youtube_abc123", "youtube_def456", "youtube_ghi789"],
    "extraction_method": "canonical",
    "extraction_date": "2026-01-27T15:00:15Z",
    "canonicalization_reasoning": "Most comprehensive (110 chars, conf: 0.95)"
  },
  "tags": ["app", "transportation", "ride-hailing", "payment"],
  "merged_from": ["hash1", "hash2", "hash3"],
  "consensus_content": "Use Grab app for ride-hailing in Southeast Asia. Much cheaper than taxis and accepts credit cards.",
  "aliases": [
    "Use Grab to get around",
    "Grab for ride-hailing"
  ],
  "quality_score": 0.87,
  "freshness_score": 1.0,
  "applicability_score": 0.92
}
```

---

## Usage

### Command Reference

#### 1. Extract Insights

```bash
# Test with 10 videos
./crawl.sh process-insights --limit 10

# Process all pending videos (both passes)
./crawl.sh process-insights

# Process only Pass 1 (filtered entities)
./crawl.sh process-insights --pass 1

# Process only Pass 2 (info-only videos)
./crawl.sh process-insights --pass 2

# Debug logging
./crawl.sh process-insights --limit 5 --log-level DEBUG
```

#### 2. View Statistics

```bash
# Show insights statistics
./crawl.sh insights-stats
```

Output includes:
- Total canonical insights
- Breakdown by category
- Breakdown by scope (global, region, country, etc.)
- Top destinations
- Deduplication rate
- Quality/freshness/applicability scores
- Top insights by mentions

#### 3. Reset Pipeline

```bash
# Preview what will be reset (dry run)
./crawl.sh reset-insights --dry-run --all

# Reset all insights data
./crawl.sh reset-insights --all

# Reset specific videos
./crawl.sh reset-insights --video-ids abc123,xyz789
```

---

## Schema Reference

### InsightCategory (Enum)
```python
class InsightCategory(str, Enum):
    SERVICES = "services"        # Apps, booking platforms
    LOGISTICS = "logistics"      # How-to guides, visa
    TIPS = "tips"                # Packing, money, advice
    REGIONAL = "regional"        # Area-specific info
    CULTURAL = "cultural"        # Customs, etiquette
    SAFETY = "safety"            # Security, scams, health
    COST_INFO = "cost_info"      # Prices, budget advice
    SEASONAL = "seasonal"        # Weather, timing
```

### InsightScope
```python
class InsightScope(BaseModel):
    destination_type: Literal["country", "region", "city", "area", "global"]
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    area: Optional[str] = None
```

### TravelInsight
```python
class TravelInsight(BaseModel):
    insight_id: str  # Format: INS_CAT_### (e.g., INS_SVC_001)
    category: InsightCategory
    content: str  # 10-1000 chars
    title: Optional[str] = None  # Max 150 chars
    scope: InsightScope
    confidence_score: float  # 0.0-1.0
    mention_count: int  # ≥1
    video_count: int  # ≥1
    provenance: InsightProvenance
    tags: List[str] = []
```

### CanonicalInsight (extends TravelInsight)
```python
class CanonicalInsight(TravelInsight):
    merged_from: List[str]  # Hash IDs of merged insights
    consensus_content: str  # Selected best content
    aliases: List[str]  # Alternative phrasings
    quality_score: float  # 0.0-1.0
    freshness_score: float  # 0.0-1.0
    applicability_score: float  # 0.0-1.0
```

---

## Cost Analysis

### Per-Run Cost Breakdown

| Component | Method | Unit Cost | Volume | Total Cost |
|-----------|--------|-----------|--------|------------|
| **Pass 1 Extraction** | Gemini Flash 2.5 Lite | FREE | ~200 entities | $0.00 |
| **Pass 2 Extraction** | Gemini Flash 2.5 Lite | FREE | ~30 videos | $0.00 |
| **Tier 1 Dedup** | Hash matching | FREE | ~440 insights | $0.00 |
| **Tier 2 Dedup** | Embeddings | FREE (cached) | ~150 pairs | $0.00 |
| **Tier 3 Dedup** | Gemini Flash LLM | FREE | ~20 pairs | $0.00 |
| **TOTAL** | | | | **$0.00** |

**Notes**:
- Gemini Flash 2.5 Lite: FREE tier (15 req/min, 1M tokens/min, 1500 req/day)
- Embedding cache reused across runs
- LLM verification uses minimal tokens (~200 tokens/pair)
- Full pipeline stays within free tier limits

### Scalability

At scale (10,000 videos):
- **Filtered entities**: ~2,000 entities → ~2,000 insights
- **Info-only videos**: ~300 videos → ~2,400 insights
- **Total raw insights**: ~4,400
- **Estimated unique**: ~3,300 canonical insights
- **Cost**: Still $0.00 (FREE tier)

---

## Best Practices

### 1. Incremental Processing
- Process new videos as they're crawled
- Metadata tracker ensures no reprocessing
- Registry tracks which videos already processed

### 2. Quality Control
- Review insights with low quality scores (<0.5)
- Check insights with single mentions (may be noise)
- Validate scope assignments (global vs region vs country)

### 3. Maintenance
- Run `reset-insights` if prompts or categories change
- Check `insights-stats` regularly for quality trends
- Monitor deduplication rate (should be >30%)

### 4. Integration
- Canonical insights ready for:
  - Vector indexing (Stage 4)
  - RAG retrieval (Stage 5)
  - User-facing insights API
  - Travel guide generation

---

## Troubleshooting

### No insights extracted
**Problem**: `process-insights` runs but extracts 0 insights

**Possible causes**:
1. No filtered entities in Stage 3 → Run entity filtering first
2. No info-only videos → Lower Pass 2 threshold (default: <5 entities)
3. LLM returns empty responses → Check API key, rate limits

**Solution**:
```bash
# Check filtered entities
aws s3 ls s3://your-bucket/stage3-canonical/filtered/

# Check metadata
./crawl.sh status | grep insights_pipeline

# Test with debug logging
./crawl.sh process-insights --limit 1 --log-level DEBUG
```

### Deduplication rate too low
**Problem**: Most insights are singletons, few duplicates found

**Possible causes**:
1. Semantic threshold too high (>0.90)
2. LLM confidence threshold too high (>0.7)
3. Content too diverse (not enough overlap)

**Solution**:
- Adjust thresholds in `deduplicate_insights()` function
- Review insight content for consistency
- Check if extraction prompts are too broad

### Quality scores all low
**Problem**: Most insights have quality score <0.5

**Possible causes**:
1. Content too short (< 50 chars)
2. Low confidence from extraction
3. Single mentions (no corroboration)

**Solution**:
- Improve extraction prompts for more detail
- Lower Pass 2 entity threshold to get more videos
- Run multiple extraction passes to accumulate mentions

---

## Related Documentation

- [Entity Filtering](./ENTITY_FILTERING.md) - Phase 1A (filtering non-places)
- [Stage 2 Guardrails](./STAGE2_GUARDRAILS.md) - Phase 1B (prevention)
- [Stage 3 Deduplication](./STAGE3_DEDUPLICATION.md) - Entity dedup patterns
- [Vector Indexing (Stage 4)](./STAGE4_VECTOR_INDEXING.md) - Indexing insights
- [RAG System (Stage 5)](./STAGE5_RAG.md) - Using insights in retrieval

---

## Future Enhancements

### Short-term
- [ ] CLI command for manual insight approval/rejection
- [ ] Insight tagging system (auto-tag with keywords)
- [ ] Confidence recalibration based on user feedback

### Medium-term
- [ ] Multi-language insights (translate to other languages)
- [ ] Insight versioning (track changes over time)
- [ ] Insight relationships (related insights, contradictions)

### Long-term
- [ ] Real-time insights extraction (as videos are crawled)
- [ ] Community curation (users vote on insight quality)
- [ ] Personalized insights (filter by traveler profile)

---

**Last Updated**: January 29, 2026
**Version**: 1.0.0
**Status**: Production Ready
