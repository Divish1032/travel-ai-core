# Pipeline Overview

TravelAI consists of two pipelines: a **Main Pipeline** (5 stages) that processes videos into itineraries, and an **Insights Pipeline** that generates entity insights in parallel.

---

## Main Pipeline (5 Stages)

```
YouTube Videos
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Crawling                                            │
│ • Download video metadata (YouTube Data API)                │
│ • Download audio (yt-dlp)                                   │
│ • Transcribe speech-to-text (Whisper)                       │
│ • Output: Transcript + metadata                             │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Entity Extraction                                   │
│ • Semantic chunking (not fixed-time)                        │
│ • LLM entity extraction per chunk                           │
│ • Fuzzy deduplication within video                          │
│ • Traveler profile inference (VIBE)                         │
│ • Output: Raw entities per video                            │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Canonicalization + Enrichment                      │
│ • 4-tier deduplication across all videos:                   │
│   - Tier 1: Exact name matching                             │
│   - Tier 2: Fuzzy name matching (85%)                       │
│   - Tier 3: Geohash matching                                │
│   - Tier 4: LLM consensus                                   │
│ • Enrichment:                                               │
│   - temporal_info (best time to visit)                      │
│   - logistics_info (hours, booking)                         │
│   - popularity_score (0-100)                                │
│   - data_freshness (recency)                                │
│ • Output: Canonical entities                                │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: Vectorization                                       │
│ • Generate gte-large embeddings (FREE, local)               │
│ • 3 embedding types:                                        │
│   - full_context (complete description)                     │
│   - experience (subjective only)                            │
│   - logistics (practical only)                              │
│ • Enhanced metadata:                                        │
│   - Geohash (geospatial search)                             │
│   - Temporal filters (best months)                          │
│   - Logistics filters (booking, hours)                      │
│ • Index in ChromaDB (Chroma Cloud)                          │
│ • Output: Vector embeddings + metadata                      │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: RAG Itinerary Generation                           │
│ • 7-phase RAG pipeline:                                     │
│   1. Intent parsing (destination, duration, vibe)           │
│   2. Retrieval (ChromaDB with geohash + filters)            │
│   3. Re-ranking (VIBE match scoring)                        │
│   4. Context building (assemble entities)                   │
│   5. Generation (day-by-day itinerary)                      │
│   6. Validation (feasibility check)                         │
│   7. Narrative (tips and explanations)                      │
│ • Output: Personalized itinerary                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Crawling

**Purpose:** Collect travel video content and transcribe to text

### Inputs
- YouTube video URLs or channel IDs
- Video metadata filters (language, duration)

### Processing
1. Fetch video metadata via YouTube Data API v3
2. Download audio using `yt-dlp`
3. Transcribe audio with OpenAI Whisper (small model by default)
4. Extract video metadata (title, channel, views, etc.)

### Outputs
- `stage1_transcripts/{video_id}.json`:
  ```json
  {
    "video_id": "youtube_UEDeptPVNQA",
    "title": "Bangkok Travel Guide 2024",
    "channel": "Travel Vlogger",
    "duration_seconds": 895,
    "transcript": "Today we're exploring Bangkok...",
    "language": "en",
    "quality_score": 0.87
  }
  ```

### Key Features
- Supports multiple languages (Whisper auto-detects)
- Browser cookie support for age-restricted videos
- Quality scoring based on transcript confidence
- Automatic retry for failed downloads

**See:** [stage1-crawling.md](../03-pipeline-stages/stage1-crawling.md)

---

## Stage 2: Entity Extraction

**Purpose:** Extract structured travel entities from transcripts

### Inputs
- Stage 1 transcripts

### Processing
1. **Semantic Chunking:** Split transcript into coherent segments (not fixed-time)
2. **Entity Extraction:** LLM extracts entities per chunk:
   - Places (attractions, neighborhoods)
   - Restaurants (name, cuisine, price range)
   - Hotels (name, area, price range)
   - Activities (tours, experiences)
   - General Tips
3. **Fuzzy Deduplication:** Deduplicate entities within video (85% similarity threshold)
4. **Traveler Profile:** Infer VIBE dimensions from content

### Outputs
- `stage2_entities/{video_id}.json`:
  ```json
  {
    "video_id": "youtube_UEDeptPVNQA",
    "traveler_profile": {
      "touristiness": 6,
      "adventure_level": 4,
      "budget_level": 5,
      "pace": "moderate",
      "food_focus": 8
    },
    "entities": [
      {
        "name": "Chatuchak Weekend Market",
        "type": "place",
        "sentiment": "positive",
        "context": "Amazing market with endless stalls...",
        "mentions": 3,
        "confidence": 0.92
      }
    ]
  }
  ```

### Key Features
- Semantic chunking (not fixed-time windows)
- Fuzzy deduplication within video
- Sentiment analysis per entity
- Quality confidence scoring
- Focus on subjective experience data

**See:** [stage2-extraction.md](../03-pipeline-stages/stage2-extraction.md)

---

## Stage 3: Canonicalization + Enrichment

**Purpose:** Deduplicate entities across all videos and enrich with metadata

### Inputs
- All Stage 2 entity files

### Processing

#### 4-Tier Deduplication
1. **Tier 1 - Exact Matching:** Identical names → merge
2. **Tier 2 - Fuzzy Matching:** 85%+ similarity → merge
3. **Tier 3 - Geohash Matching:** Geocode entities, match by geohash proximity
4. **Tier 4 - LLM Consensus:** Resolve ambiguous cases with LLM

#### Enrichment
For each canonical entity:
- **temporal_info:** Best time to visit, seasonal notes
- **logistics_info:** Opening hours, booking requirements, practical tips
- **popularity_score:** Relative popularity (0-100) based on mentions
- **data_freshness:** Recency score based on video upload dates

### Outputs
- `metadata/canonical_entities.json`:
  ```json
  {
    "canonical_place_001": {
      "name": "Chatuchak Weekend Market",
      "type": "place",
      "location": {
        "city": "Bangkok",
        "country": "Thailand",
        "lat": 13.7998,
        "lon": 100.5498,
        "geohash": "w4rqqq"
      },
      "merged_from": ["youtube_UEDeptPVNQA", "youtube_8m8ReerO060"],
      "mention_count": 8,
      "popularity_score": 87,
      "data_freshness": 95,
      "temporal_info": {
        "best_months": [11, 12, 1, 2],
        "avoid_months": [4, 5],
        "seasonal_notes": "Best in cool season (Nov-Feb)"
      },
      "logistics_info": {
        "opening_hours": "Saturday-Sunday 9:00-18:00",
        "booking_required": false,
        "advance_booking_days": 0,
        "practical_tips": "Arrive early to avoid crowds"
      }
    }
  }
  ```

### Key Features
- 4-tier deduplication strategy
- LLM-based consensus for ambiguous cases
- Geocoding with 90% free Nominatim + 10% Google Maps fallback
- Geohash for geospatial search
- Comprehensive enrichment metadata
- Tracks source videos for provenance

**See:** [stage3-enrichment.md](../03-pipeline-stages/stage3-enrichment.md)

---

## Stage 4: Vectorization

**Purpose:** Create searchable vector embeddings

### Inputs
- Stage 3 canonical entities

### Processing
1. **Embedding Generation:** Use `gte-large` model (FREE, local)
2. **3 Embedding Types:**
   - `full_context`: Complete entity description
   - `experience`: Subjective experiences only
   - `logistics`: Practical information only
3. **Enhanced Metadata:**
   - Geohash (for geospatial filtering)
   - Temporal filters (best months, seasonal)
   - Logistics filters (booking required, hours)
4. **ChromaDB Indexing:** Upload to Chroma Cloud with metadata

### Outputs
- ChromaDB `travel_entities` collection:
  ```python
  {
    "id": "canonical_place_001_full_context",
    "embedding": [0.123, -0.456, ...],  # 768 dims
    "metadata": {
      "canonical_id": "canonical_place_001",
      "entity_name": "Chatuchak Weekend Market",
      "entity_type": "place",
      "embedding_type": "full_context",
      "city": "Bangkok",
      "country": "Thailand",
      "geohash": "w4rqqq",
      "best_months": [11, 12, 1, 2],
      "booking_required": false,
      "popularity_score": 87,
      "data_freshness": 95
    }
  }
  ```

### Key Features
- FREE local embeddings (no API cost)
- 3 embedding types for different query types
- Geohash geospatial search
- Rich metadata for filtering
- ChromaDB cloud hosting (scalable)

**See:** [stage4-vectorization.md](../03-pipeline-stages/stage4-vectorization.md)

---

## Stage 5: RAG Itinerary Generation

**Purpose:** Generate personalized itineraries from natural language queries

### Inputs
- User query: `"5 days Bangkok solo budget street food"`
- ChromaDB vector embeddings

### 7-Phase RAG Pipeline

#### Phase 1: Intent Parsing
Extract structured intent from query:
```json
{
  "destination": "Bangkok, Thailand",
  "duration_days": 5,
  "vibe": {
    "touristiness": 4,
    "adventure_level": 5,
    "budget_level": 3,
    "pace": "moderate",
    "food_focus": 9
  },
  "constraints": ["solo", "budget", "street food"]
}
```

#### Phase 2: Retrieval
Query ChromaDB with:
- Geohash filter (Bangkok area)
- Temporal filter (best months)
- Embedding similarity search
- Return top 50 entities

#### Phase 3: Re-ranking
Score entities by VIBE match:
- Compare entity characteristics to user vibe
- Penalize mismatches (e.g., luxury hotels for budget travelers)
- Boost entities matching constraints (street food)
- Return top 20 entities

#### Phase 4: Context Building
Assemble retrieved entities into LLM context:
- Group by type (places, restaurants, hotels)
- Include metadata (temporal, logistics, popularity)
- Add source provenance

#### Phase 5: Generation
LLM generates day-by-day itinerary:
- Considers travel time between locations
- Balances activity types per day
- Respects budget constraints
- Includes timing recommendations

#### Phase 6: Validation
Check feasibility:
- Distances between locations reasonable?
- Activities open on suggested days?
- Budget estimate realistic?
- Required bookings flagged?

#### Phase 7: Narrative
Add helpful narrative:
- Travel tips specific to destination
- Cultural notes
- Budget breakdown
- Alternative suggestions

### Outputs
- `stage5_itineraries/itinerary_{timestamp}.json`:
  ```json
  {
    "destination": "Bangkok, Thailand",
    "duration_days": 5,
    "vibe_match_score": 8.7,
    "days": [
      {
        "day": 1,
        "theme": "Old Bangkok Street Food Tour",
        "activities": [...]
      }
    ],
    "budget_estimate": {
      "total": "$250",
      "breakdown": {...}
    },
    "travel_tips": [...]
  }
  ```

### Key Features
- 7-phase pipeline with validation
- VIBE-based re-ranking
- Geospatial and temporal filtering
- Cost tracking per phase
- Error handling and retries
- Explainable recommendations

**See:** [stage5-rag.md](../03-pipeline-stages/stage5-rag.md)

---

## Insights Pipeline (Parallel)

**Purpose:** Generate entity-specific insights from raw video content

### Overview
The Insights Pipeline runs **parallel to the main pipeline**, starting from Stage 1 data. It generates curated insights about specific entities mentioned in videos.

### Processing Flow
```
Stage 1 Transcripts
    ↓
Insight Extraction (LLM)
    ↓
Insight Deduplication
    ↓
Insight Canonicalization
    ↓
Curated Entity Insights
```

### Key Differences from Main Pipeline
- **Source:** Stage 1 transcripts (raw content)
- **Focus:** Entity-specific insights and tips
- **Independence:** Can run without waiting for Stages 2-5
- **Output:** Insight collections per entity

### Use Cases
- Enrich entity profiles with traveler tips
- Surface non-obvious insights
- Provide context beyond basic facts

**See:** [insights-pipeline.md](../03-pipeline-stages/insights-pipeline.md)

---

## Pipeline Characteristics

### Data Flow
- **Linear Stages:** Each stage depends on previous stage output
- **S3-Based:** All stage outputs stored in S3 data lake
- **Metadata Tracking:** Pipeline state tracked in `metadata/processing_status.jsonl`
- **Idempotent:** Stages can be re-run safely (reset commands available)

### Scalability
- **Stage 1:** Limited by YouTube API quota (10,000 units/day)
- **Stage 2-3:** Limited by LLM API rate limits
- **Stage 4:** No rate limits (local embeddings)
- **Stage 5:** Fast (< 60 seconds per itinerary)

### Cost Efficiency
- **Stage 1:** FREE (Whisper local)
- **Stage 2:** ~$0.002-0.005 per video
- **Stage 3:** ~$0.001-0.003 per video
- **Stage 4:** FREE (local embeddings)
- **Stage 5:** ~$0.01-0.02 per itinerary

**Total:** ~$0.03-0.05 for end-to-end pipeline per video

### Monitoring
- Pipeline status: `./crawl.sh status`
- Stage-specific stats: `./crawl.sh stage3-stats`, `./crawl.sh stage4-stats`
- Cost tracking: Automatic per-phase tracking in Stage 5

**See:** [monitoring.md](../05-infrastructure/monitoring.md)

---

## References

- **System Architecture:** [system-architecture.md](system-architecture.md)
- **Data Flow:** [data-flow.md](data-flow.md)
- **Stage Details:**
  - [Stage 1: Crawling](../03-pipeline-stages/stage1-crawling.md)
  - [Stage 2: Extraction](../03-pipeline-stages/stage2-extraction.md)
  - [Stage 3: Enrichment](../03-pipeline-stages/stage3-enrichment.md)
  - [Stage 4: Vectorization](../03-pipeline-stages/stage4-vectorization.md)
  - [Stage 5: RAG](../03-pipeline-stages/stage5-rag.md)
  - [Insights Pipeline](../03-pipeline-stages/insights-pipeline.md)
- **CLI Commands:** [cli-commands.md](../04-reference/cli-commands.md)

---

**Pipeline overview complete!** Next: [Data Flow](data-flow.md)
