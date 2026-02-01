# Current Pipeline Flow: Transcript → Stage 2 → Stage 3 → Insights

Complete explanation of how data flows through the TravelAI processing pipeline.

---

## 📊 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            STAGE 1: CRAWLING                            │
│                         (src/crawlers/youtube.py)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   YouTube Video Download       │
                    │   - Audio extraction (.mp3)    │
                    │   - Metadata (title, duration) │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Whisper Transcription        │
                    │   - Segment-by-segment         │
                    │   - Timestamps                 │
                    │   - Language detection         │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Thai Place Name Correction   │
                    │   - Dictionary matching        │
                    │   - Pattern correction         │
                    │   - Fuzzy matching             │
                    └────────────────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────┐
                          │  TRANSCRIPT     │
                          │  (with segments)│
                          └─────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        STAGE 2: ENTITY EXTRACTION                       │
│                    (src/processors/stage2_extractor.py)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
         ┌──────────────────┐           ┌──────────────────────┐
         │  SHORT VIDEO     │           │   LONG VIDEO         │
         │  (< 20 minutes)  │           │   (>= 20 minutes)    │
         └──────────────────┘           └──────────────────────┘
                    │                                 │
                    ▼                                 ▼
         ┌──────────────────┐           ┌──────────────────────┐
         │  Single LLM Call │           │  Chunked Processing  │
         │  - Full transcript│           │  - 5-min chunks      │
         │  - Extract all    │           │  - 1-min overlap     │
         │    entities       │           │  - Per-chunk extract │
         │  - Traveler profile│          │  - Merge & dedupe    │
         └──────────────────┘           └──────────────────────┘
                    │                                 │
                    └────────────────┬────────────────┘
                                     ▼
                    ┌────────────────────────────────┐
                    │   EXTRACTED ENTITIES           │
                    │   (EntityExperience objects)   │
                    │                                │
                    │   For each entity:             │
                    │   - entity_name                │
                    │   - entity_type                │
                    │   - location                   │
                    │   - experience (description)   │
                    │   - sentiment                  │
                    │   - cost_mentioned             │
                    │   - rating                     │
                    │   - timestamp_start/end        │
                    │   - confidence_score           │
                    │                                │
                    │   Plus:                        │
                    │   - traveler_profile           │
                    │   - llm_model, tokens, cost    │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   SAVE TO S3                   │
                    │   stage2-extracted/new/        │
                    │   youtube_video_{id}.jsonl     │
                    └────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              STAGE 3: DEDUPLICATION & CANONICALIZATION                  │
│                    (cli/process_stage3.py)                              │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
         ┌──────────────────┐           ┌──────────────────────┐
         │  STEP 1: LOAD    │           │  STEP 2: GROUP BY    │
         │  - Read S3 files │           │  ENTITY TYPE         │
         │  - Parse entities│───────────▶│  - attractions       │
         │  - Normalize     │           │  - restaurants       │
         │    names/locations│          │  - hotels, etc.      │
         └──────────────────┘           └──────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 3: DEDUPLICATION           │
                              │  (4-tier matching)               │
                              └──────────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
         │  TIER 1: EXACT   │         │  TIER 2: FUZZY   │         │  TIER 3: SEMANTIC│
         │  - Same name     │─────────▶│  - Similar names │─────────▶│  - Embedding     │
         │  - Same city     │         │  - >90% similar  │         │    similarity    │
         │  - Same type     │         │  (rapidfuzz)     │         │  - >85% match    │
         └──────────────────┘         └──────────────────┘         └──────────────────┘
                    │                              │                              │
                    └──────────────────────────────┼──────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  TIER 4: LLM VERIFICATION        │
                              │  - For uncertain pairs (80-90%)  │
                              │  - LLM judges if same entity     │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  DEDUPLICATION RESULT            │
                              │                                  │
                              │  - entity_groups: {              │
                              │      'group_abc': [e1, e2, e3],  │
                              │      'group_def': [e4, e5]       │
                              │    }                             │
                              │  - singleton_entities: [e6, e7]  │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 4: CANONICALIZATION        │
                              │  (merge entity groups)           │
                              └──────────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
         │  SELECT CANONICAL│         │  EXTRACT ALIASES │         │  MERGE EXPERIENCES│
         │  NAME            │         │  - All name      │         │  - Combine all   │
         │  - Most common   │─────────▶│    variations    │─────────▶│    mentions      │
         │  - Or first      │         │  - Original names│         │  - Preserve all  │
         │    mention       │         │                  │         │    contexts      │
         └──────────────────┘         └──────────────────┘         └──────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  CANONICAL ENTITY (Basic)        │
                              │                                  │
                              │  - entity_id (generated)         │
                              │  - canonical_name                │
                              │  - aliases []                    │
                              │  - entity_type                   │
                              │  - city, country                 │
                              │  - experiences [] (all mentions) │
                              │  - source_video_ids []           │
                              │  - confidence_score              │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 4a: FILTER NON-PLACES      │
                              │  - Remove apps (Grab, Agoda)     │
                              │  - Remove websites               │
                              │  - Remove generic categories     │
                              │  → Send to INSIGHT PIPELINE      │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 4b: MERGE WITH EXISTING    │
                              │  (Incremental Mode)              │
                              │  - Load existing canonical       │
                              │  - Match by name+city+type       │
                              │  - Merge experiences if match    │
                              │  - Create new if no match        │
                              │  - Keep unchanged entities       │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 5: CONSENSUS BUILDING      │
                              │  (Parallel LLM calls)            │
                              └──────────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
         │  AGGREGATE RATINGS│         │  EXTRACT THEMES  │         │  BUILD PROFILES  │
         │  - Avg rating    │         │  (LLM)           │         │  - Traveler types│
         │  - Avg cost      │─────────▶│  - Best for     │─────────▶│  - Budget tiers  │
         │  - Total mentions│         │  - Vibes/moods   │         │  - By experience │
         │                  │         │  - Top exp.      │         │                  │
         └──────────────────┘         └──────────────────┘         └──────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  CONSENSUS DATA (added to entity)│
                              │                                  │
                              │  consensus: {                    │
                              │    avg_rating: 4.5,              │
                              │    avg_cost: "$$",               │
                              │    themes: ["romantic", "food"], │
                              │    best_for: ["couples"],        │
                              │    top_experiences: [...],       │
                              │    traveler_profiles: [...]      │
                              │  }                               │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 5.5: ENRICHMENT            │
                              │  (Hybrid: Transcript + LLM)      │
                              └──────────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
         │  TEMPORAL INFO   │         │  LOGISTICS INFO  │         │  PRACTICAL TIPS  │
         │  - Opening hours │         │  - Duration      │         │  (LLM only)      │
         │  - Best time     │─────────▶│  - Costs         │─────────▶│  - Tips          │
         │  - Seasonal info │         │  - Booking req.  │         │  - Warnings      │
         │  Source: Hybrid  │         │  Source: Hybrid  │         │                  │
         └──────────────────┘         └──────────────────┘         └──────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  ENRICHMENT DATA (added)         │
                              │                                  │
                              │  temporal_info: {                │
                              │    opening_hours: "10:00-22:00", │
                              │    best_time: "sunset",          │
                              │    source: "transcript_extracted"│
                              │  }                               │
                              │  logistics_info: {               │
                              │    duration: "2-3 hours",        │
                              │    cost_range: "500-1000 THB"    │
                              │  }                               │
                              │  practical_tips: ["tip1", ...]   │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  STEP 6: GEOCODING               │
                              │  (Google Maps only)              │
                              └──────────────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
         ┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
         │  GEOCODE REQUEST │         │  CACHE LOOKUP    │         │  REVERSE GEOCODE │
         │  - canonical_name│         │  - Check cache   │         │  - Fill missing  │
         │  - city, country │─────────▶│  - Reuse coords  │─────────▶│    city/country  │
         │  - entity_type   │         │                  │         │                  │
         └──────────────────┘         └──────────────────┘         └──────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  COORDINATES (added)             │
                              │                                  │
                              │  coordinates: {                  │
                              │    lat: 13.7563,                 │
                              │    lon: 100.5018,                │
                              │    source: "google_maps"         │
                              │  }                               │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                              ┌──────────────────────────────────┐
                              │  FINAL CANONICAL ENTITY          │
                              │  (Complete with all data)        │
                              └──────────────────────────────────┘
                                                   │
                                                   ▼
                    ┌────────────────────────────────────────┐
                    │   SAVE TO S3                           │
                    │   stage3-canonical/                    │
                    │   - entities_all.jsonl                 │
                    │   - by_city/{city}.jsonl               │
                    │   - by_type/{type}.jsonl               │
                    └────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         INSIGHT PIPELINE                                │
│                 (Parallel to Stage 3, Phase 2C)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
         ┌──────────────────┐           ┌──────────────────────┐
         │  PASS 1:         │           │  PASS 2:             │
         │  Filtered        │           │  Info-only Videos    │
         │  Entities        │           │  (<5 entities)       │
         │                  │           │                      │
         │  Input:          │           │  Input:              │
         │  - Apps (Grab)   │           │  - Full transcript   │
         │  - Websites      │           │                      │
         │  - Services      │           │  Extract:            │
         │                  │           │  - Travel tips       │
         │  Extract:        │           │  - Logistics advice  │
         │  - Usage tips    │           │  - Packing lists     │
         │  - Pricing       │           │  - Service recs      │
         │  - Booking info  │           │                      │
         └──────────────────┘           └──────────────────────┘
                    │                                 │
                    └────────────────┬────────────────┘
                                     ▼
                    ┌────────────────────────────────┐
                    │   TRAVEL INSIGHTS              │
                    │                                │
                    │   For each insight:            │
                    │   - insight_id                 │
                    │   - category (tips, services,  │
                    │     logistics, packing)        │
                    │   - scope (city, country, etc.)│
                    │   - content (the actual tip)   │
                    │   - context (from experiences) │
                    │   - source_videos []           │
                    │   - mentioned_entities []      │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   INSIGHT DEDUPLICATION        │
                    │   (3-tier)                     │
                    │   - Exact content match        │
                    │   - Fuzzy content match        │
                    │   - Semantic similarity        │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   CANONICAL INSIGHTS           │
                    │   (Merged from multiple videos)│
                    └────────────────────────────────┘
```

---

## 🔍 Detailed Step-by-Step Breakdown

### STAGE 1: CRAWLING (YouTube Video → Transcript)

**Input:** YouTube video URL
**Output:** Transcript with segments + metadata
**File:** `src/crawlers/youtube.py`

**Steps:**

1. **Download Audio** (yt-dlp)
   - Extract audio as .mp3
   - Store temporarily

2. **Transcribe** (OpenAI Whisper)
   - Segment-by-segment transcription
   - Timestamps for each segment
   - Language detection

3. **Correct Thai Place Names**
   - Dictionary matching (common tourist spots)
   - Pattern correction (tone marks, spellings)
   - Fuzzy matching for variants

4. **Save to S3**
   - `raw/new/youtube_video_{id}.jsonl`
   - Update MetadataTracker (stage_1_crawl: complete)

**Output Structure:**
```json
{
  "source_id": "abc123",
  "title": "Bangkok Travel Guide 2024",
  "duration_seconds": 1250,
  "language": "en",
  "transcript": [
    {
      "index": 0,
      "start": 0.0,
      "end": 5.2,
      "text": "Welcome to Bangkok! Today we're visiting Wat Pho."
    },
    ...
  ]
}
```

---

### STAGE 2: ENTITY EXTRACTION (Transcript → Entities)

**Input:** Transcript from Stage 1
**Output:** List of EntityExperience objects
**File:** `src/processors/stage2_extractor.py`

#### Classification Step

**Function:** `classify_video_length(duration_seconds)`

- **Short video** (< 20 min = 1200 seconds): Single-pass extraction
- **Long video** (>= 20 min): Chunked extraction

---

#### Path A: Short Video Processing

**Function:** `process_short_video()`

**Steps:**

1. **Prepare Transcript**
   - Join all segments into full text
   - Translate to English if needed (for non-English videos)

2. **Single LLM Call** (Gemini 2.5 Flash)
   - **Prompt:** `HIERARCHICAL_SINGLE_PASS_PROMPT`
   - **Extract:**
     - All entities (attractions, restaurants, hotels, etc.)
     - Traveler profile (solo/couple/family, budget, style)
   - **Structured Output:** Pydantic schema validation

3. **Parse & Validate**
   - Parse JSON response
   - Validate against `Stage2Output` schema
   - Handle malformed LLM outputs (retry up to 3 times)

4. **Enrich Entities**
   - Add timestamps from transcript matching
   - Add provenance (source_video_id, source_file_path)
   - Add extraction metadata (llm_model, tokens, cost)

---

#### Path B: Long Video Processing

**Function:** `process_long_video()`

**Steps:**

1. **Semantic Chunking** (optional, default: ON)
   - Split transcript into topic-based chunks
   - OR use fixed 5-min chunks with 1-min overlap

2. **Per-Chunk Extraction** (parallel LLM calls)
   - **For each chunk:**
     - Extract entities in that timeframe
     - Use `HIERARCHICAL_CHUNK_PROMPT`
     - Structured output validation

3. **Extract Traveler Profile** (first chunk only)
   - Single LLM call on first chunk
   - Get demographic + preferences

4. **Merge Chunk Results**
   - Combine entities from all chunks
   - Preserve all mentions

5. **Fuzzy Deduplication** (within video)
   - Find entities mentioned multiple times
   - Use rapidfuzz (90% similarity threshold)
   - Merge duplicate mentions
   - Keep all experiences

---

#### Stage 2 Output Structure

**Schema:** `Stage2Output` (Pydantic)

```python
{
  # Metadata
  "content_id": "youtube_abc123",
  "source_id": "abc123",
  "language": "en",
  "processed_at": "2024-01-15T10:30:00Z",
  "llm_model": "gemini-2.0-flash-exp",
  "tokens_used": 15000,
  "cost_usd": 0.0045,

  # Traveler Profile
  "traveler_profile": {
    "traveler_type": "couple",
    "age_range": "26-35",
    "budget_tier": "mid-range",
    "travel_style": ["foodie", "cultural", "romantic"],
    "confidence_score": 0.85
  },

  # Entities (list of EntityExperience)
  "entities": [
    {
      "entity_name": "Wat Pho",
      "entity_type": "attraction",
      "location": "Bangkok, Thailand",
      "experience": "Visited the famous reclining Buddha. Very peaceful and beautiful temple. Spent about 2 hours exploring.",
      "sentiment": "positive",
      "cost_mentioned": "200 THB",
      "rating": 5.0,
      "timestamp_start": 120.5,
      "timestamp_end": 450.2,
      "confidence_score": 0.95,
      "tags": ["temple", "buddha", "cultural"]
    },
    {
      "entity_name": "Thip Samai Pad Thai",
      "entity_type": "restaurant",
      "location": "Old Town, Bangkok",
      "experience": "Best pad thai in Bangkok! The crab pad thai is amazing. Long queue but worth the wait.",
      "sentiment": "positive",
      "cost_mentioned": "150 THB",
      "rating": 4.5,
      "timestamp_start": 680.0,
      "timestamp_end": 750.0,
      "confidence_score": 0.90,
      "tags": ["street food", "pad thai", "local"]
    }
  ],

  # Quality metrics
  "extraction_quality": "high",  # Based on confidence scores
  "total_entities": 24
}
```

**Save to S3:**
- Path: `stage2-extracted/new/youtube_video_{id}.jsonl`
- Format: Single-line JSON per file (one video per file)

---

### STAGE 3: DEDUPLICATION & CANONICALIZATION

**Input:** Stage 2 entities from multiple videos
**Output:** Canonical entities with consensus
**File:** `cli/process_stage3.py`

---

#### STEP 1: Load Stage 2 Entities

**Function:** `load_all_stage2_entities()`

**Actions:**
1. List all files in S3 `stage2-extracted/new/`
2. Download and parse each JSONL file
3. Normalize entity names and locations
4. Group by entity_type

**Normalization:**
- Lowercase names
- Remove special characters
- Normalize city names (e.g., "Bangkok, Thailand" → "bangkok")

---

#### STEP 2: Incremental Filtering (if mode=incremental)

**Function:** Filter to only NEW videos

**Actions:**
1. Load EntityRegistry from S3
2. Check which videos already processed
3. Filter out entities from processed videos
4. Only process new entities

---

#### STEP 3: Deduplication (4-Tier Matching)

**File:** `src/processors/deduplication.py`

**For each entity type separately (attractions, restaurants, etc.):**

##### Tier 1: Exact Matching

**Function:** `exact_match(entity1, entity2)`

**Criteria:** ALL must match:
- `normalized_name` (exact string match)
- `normalized_location` (city)
- `entity_type`

**Example:**
```python
# MATCH
entity1 = {"normalized_name": "wat pho", "normalized_location": "bangkok", "entity_type": "attraction"}
entity2 = {"normalized_name": "wat pho", "normalized_location": "bangkok", "entity_type": "attraction"}

# NO MATCH (different city)
entity3 = {"normalized_name": "wat pho", "normalized_location": "chiang mai", "entity_type": "attraction"}
```

**Output:**
- Groups: `{'group_abc': [e1, e2, e3], ...}`
- Singletons: `[e4, e5, ...]` (no exact matches)

---

##### Tier 2: Fuzzy Matching

**Function:** `fuzzy_match()` using `rapidfuzz`

**Criteria:**
- Name similarity > 90% (configurable threshold)
- Same city
- Same entity_type

**Algorithm:** Token Sort Ratio (handles word order variations)

**Example:**
```python
# MATCH (95% similar)
e1 = "Thip Samai Pad Thai Restaurant"
e2 = "Thip Samai Pad Thai"

# MATCH (92% similar)
e3 = "Jim Thompson House Museum"
e4 = "Jim Thompson House"

# NO MATCH (78% similar, below threshold)
e5 = "Central World Mall"
e6 = "Central Plaza"
```

---

##### Tier 3: Semantic Matching

**Function:** Embedding similarity

**Criteria:**
- Embedding cosine similarity > 85%
- Same city
- Same entity_type

**How it works:**
1. Generate embeddings for entity names (OpenAI text-embedding-3-small)
2. Calculate cosine similarity
3. If above threshold, consider as potential match

**Example:**
```python
# MATCH (semantic similarity)
e1 = "Grand Palace"
e2 = "The Grand Palace of Bangkok"

# MATCH
e3 = "Floating Market"
e4 = "Damnoen Saduak Floating Market"
```

---

##### Tier 4: LLM Verification

**Function:** `verify_match_with_llm()`

**When:** Fuzzy or semantic score between 80-90% (uncertain)

**Prompt:**
```
Are these two entities the same place?

Entity 1:
Name: "Chatuchak Weekend Market"
Location: Bangkok
Type: shopping

Entity 2:
Name: "JJ Market"
Location: Bangkok
Type: shopping

Context 1: "Visited the huge weekend market in Chatuchak. Got lost in the maze of stalls!"
Context 2: "Went to JJ Market on Saturday morning. So many things to buy!"

Answer with JSON:
{
  "is_match": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "..."
}
```

**LLM Response:**
```json
{
  "is_match": true,
  "confidence": 0.95,
  "reasoning": "JJ Market is a common nickname for Chatuchak Weekend Market. Both are in Bangkok and described as large weekend markets."
}
```

---

#### Deduplication Output

**Structure:**
```python
{
  "entity_groups": {
    "group_001": [
      # 5 mentions of "Wat Pho" from different videos
      entity1, entity2, entity3, entity4, entity5
    ],
    "group_002": [
      # 3 mentions of "Thip Samai Pad Thai"
      entity6, entity7, entity8
    ]
  },
  "singleton_entities": [
    # Entities mentioned only once
    entity9, entity10, ...
  ],
  "statistics": {
    "total_input": 245,
    "total_groups": 78,
    "singletons": 89,
    "deduplication_rate": 67.8  # % reduced
  }
}
```

---

#### STEP 4: Canonicalization (Merge Groups into Single Entities)

**File:** `src/processors/canonicalization.py`

**For each entity group:**

##### 4.1 Select Canonical Name

**Function:** `select_canonical_name(group)`

**Logic:**
1. Count frequency of each name variant
2. Choose most common name
3. Tie-breaker: first alphabetically

**Example:**
```python
group = [
  {"entity_name": "Wat Pho"},
  {"entity_name": "Wat Pho Temple"},
  {"entity_name": "Wat Pho"},
  {"entity_name": "Temple of the Reclining Buddha"},
  {"entity_name": "Wat Pho"}
]

# Result: "Wat Pho" (appears 3 times)
canonical_name = "Wat Pho"
```

---

##### 4.2 Extract Aliases

**Function:** `extract_aliases(group, canonical_name)`

**Actions:**
- Collect all unique name variants
- Exclude canonical name
- Sort alphabetically

**Example:**
```python
aliases = [
  "Wat Pho Temple",
  "Temple of the Reclining Buddha"
]
```

---

##### 4.3 Merge Experiences

**Function:** `merge_experiences(group)`

**Actions:**
- Combine all experiences from all mentions
- Preserve all contexts
- Track source_video_id for each experience

**Example:**
```python
experiences = [
  {
    "experience": "Visited the famous reclining Buddha...",
    "sentiment": "positive",
    "rating": 5.0,
    "video_id": "youtube_abc123",
    "timestamp_start": 120.5
  },
  {
    "experience": "Beautiful temple with stunning architecture...",
    "sentiment": "positive",
    "rating": 4.5,
    "video_id": "youtube_def456",
    "timestamp_start": 340.0
  },
  ...
]
```

---

##### 4.4 Generate Entity ID

**Function:** `generate_entity_id(entity_type, city, sequence)`

**Format:** `{type}_{city}_{sequence:03d}`

**Example:**
```python
entity_id = "attraction_bangkok_001"
entity_id = "restaurant_bangkok_042"
entity_id = "hotel_phuket_015"
```

**Note:** Sequence numbers are STABLE across runs via EntityRegistry

---

##### 4.5 Calculate Confidence Score

**Function:** Aggregate from mention confidence scores

**Formula:**
```python
# Weighted average based on number of mentions
confidence = sum(e.confidence * e.mentions for e in group) / total_mentions
```

---

#### Canonicalization Output

**One canonical entity per group:**

```python
{
  "entity_id": "attraction_bangkok_001",
  "canonical_name": "Wat Pho",
  "aliases": ["Wat Pho Temple", "Temple of the Reclining Buddha"],
  "entity_type": "attraction",
  "city": "Bangkok",
  "country": "Thailand",
  "experiences": [...],  # All merged experiences
  "source_video_ids": ["youtube_abc123", "youtube_def456", "youtube_ghi789"],
  "total_mentions": 5,
  "confidence_score": 0.92
}
```

---

#### STEP 4a: Filter Non-Place Entities

**File:** `src/processors/entity_filter.py`

**Purpose:** Remove entities that aren't physical places

**Filter Patterns:**
- Apps: Grab, Agoda, Booking.com, Google Maps
- Websites: Skyscanner, TripAdvisor
- Services: Visa services, SIM cards
- Generic categories: "mall", "beach", "temple" (too vague)

**These are sent to INSIGHT PIPELINE instead**

---

#### STEP 4b: Merge with Existing Entities (Incremental Mode)

**File:** `src/processors/entity_merger.py`

**Function:** `merge_entity_complete(existing, new_experiences)`

**Steps:**

1. **Find Matching Existing Entity**
   - Query EntityRegistry by name + city + type
   - Get stable entity_id

2. **Merge New Experiences**
   - Append new experiences to existing
   - Deduplicate experiences (same video_id + similar text)
   - Recalculate aggregate scores

3. **Update Metadata**
   - Add new video_ids to source_video_ids
   - Update total_mentions
   - Recalculate confidence_score
   - Update aliases (add new name variants)

4. **Or Create New Entity**
   - If no match found, register as new
   - Get new stable entity_id from registry

**Example:**
```python
# Existing entity in DB
existing = {
  "entity_id": "attraction_bangkok_001",
  "canonical_name": "Wat Pho",
  "experiences": [exp1, exp2, exp3],  # From 3 videos
  "source_video_ids": ["vid1", "vid2", "vid3"],
  "total_mentions": 3
}

# New extraction
new_entity = {
  "canonical_name": "Wat Pho Temple",  # Variant name
  "experiences": [exp4, exp5],  # From 2 new videos
}

# Merged result
merged = {
  "entity_id": "attraction_bangkok_001",  # SAME ID (stable)
  "canonical_name": "Wat Pho",
  "aliases": ["Wat Pho Temple"],  # Added variant
  "experiences": [exp1, exp2, exp3, exp4, exp5],  # Combined
  "source_video_ids": ["vid1", "vid2", "vid3", "vid4", "vid5"],
  "total_mentions": 5,
  "confidence_score": 0.94  # Recalculated
}
```

---

#### STEP 5: Consensus Building (LLM Theme Extraction)

**File:** `src/processors/consensus.py`

**Function:** `build_entity_consensus(entity)`

**Purpose:** Extract high-level themes and profiles from experiences

**LLM Prompt:**
```
You are analyzing experiences from multiple travelers about: Wat Pho

Experiences:
1. "Visited the famous reclining Buddha. Very peaceful..."
2. "Beautiful temple with stunning architecture..."
3. "Great for photos. Bring sunscreen, it's hot!"
...

Extract:
1. Best for (traveler types): solo, couple, family, group
2. Vibes/moods: peaceful, romantic, adventurous, cultural, etc.
3. Top experiences (3-5 highlights)
4. Average rating (1-5)
5. Average cost tier: budget ($), mid-range ($$), luxury ($$$)
```

**Output:**
```json
{
  "avg_rating": 4.5,
  "avg_cost": "$",
  "themes": ["cultural", "peaceful", "photography"],
  "best_for": ["couples", "solo", "cultural enthusiasts"],
  "top_experiences": [
    "Seeing the giant reclining Buddha",
    "Traditional Thai massage",
    "Exploring temple architecture"
  ],
  "traveler_profiles": [
    {
      "profile_key": "couple_mid-range",
      "count": 3,
      "avg_rating": 4.7
    },
    {
      "profile_key": "solo_budget",
      "count": 2,
      "avg_rating": 4.3
    }
  ]
}
```

**Added to canonical entity:**
```python
entity["consensus"] = consensus_data
```

**Parallel Processing:**
- Use ThreadPoolExecutor for 4 concurrent LLM calls
- Process high-confidence entities only (>= 0.7)
- Skip entities with < 3 experiences

---

#### STEP 5.5: Enrichment (Temporal + Logistics)

**File:** `src/processors/stage3_enrichment.py`

**Function:** `batch_enrich_entities(entities)`

**Purpose:** Extract operational details from transcripts + LLM knowledge

**Two-Phase Approach:**

##### Phase 1: Transcript Extraction (Cheap, High Precision)

**Extract from experience texts:**
- Opening hours: "open 8am-6pm"
- Duration: "spent 2 hours there"
- Costs: "entrance fee 200 baht"
- Booking: "need to book in advance"
- Best time: "go at sunset"

**Algorithm:**
- Regex pattern matching
- NLP entity recognition
- Aggregate across mentions

---

##### Phase 2: LLM Fallback (For Famous Entities)

**When:** Transcript extraction failed BUT entity is well-known

**Criteria:**
- `fame_score >= 0.5` (popularity + confidence)
- Max 100 LLM calls per batch (cost control)

**LLM Prompt:**
```
Entity: Wat Pho, Bangkok

Provide factual information:
1. Opening hours (if applicable)
2. Typical visit duration
3. Cost range
4. Best time to visit
5. Booking requirements
6. Seasonal information

Return JSON with confidence scores.
```

**Output:**
```json
{
  "temporal_info": {
    "opening_hours": "08:00-18:30",
    "best_time_to_visit": "early morning (8-10am) to avoid crowds",
    "seasonal_info": "Best in Nov-Feb (cool season)",
    "source": "llm_inferred",
    "confidence": 0.85
  },
  "logistics_info": {
    "typical_duration": "1.5-2 hours",
    "cost_range": "200-300 THB (entrance + massage)",
    "booking_required": false,
    "source": "llm_inferred",
    "confidence": 0.90
  },
  "practical_tips": [
    "Dress modestly (cover shoulders and knees)",
    "Arrive early to avoid tour groups",
    "Try traditional Thai massage on-site"
  ]
}
```

**Hybrid Source Tracking:**
```python
if temporal_info_from_transcript and temporal_info_from_llm:
    source = "hybrid"  # Both sources agree
elif temporal_info_from_transcript:
    source = "transcript_extracted"  # High confidence
else:
    source = "llm_inferred"  # Lower confidence
```

---

#### STEP 6: Geocoding (Google Maps)

**File:** `src/processors/geolocation.py`

**Function:** `batch_geocode_google_only(entities)`

**Steps:**

1. **Cache Lookup**
   - Check local cache file: `data/geocode_cache_{entity_type}.json`
   - Reuse coordinates if already geocoded

2. **Google Maps Geocoding API**
   - Query: `"{canonical_name}, {city}, {country}"`
   - Get latitude, longitude
   - Cost: $0.005 per request

3. **Reverse Geocoding** (fill missing city/country)
   - If entity has coords but missing city/country
   - Reverse geocode to get location details

4. **Validation**
   - Validate lat/lon ranges (-90 to 90, -180 to 180)
   - Filter invalid coordinates

**Output:**
```python
entity["coordinates"] = {
  "lat": 13.7466,
  "lon": 100.4927,
  "source": "google_maps",
  "geocoded_at": "2024-01-15T12:00:00Z"
}
```

---

### Final Canonical Entity Structure (Current)

```python
{
  # ===== IDENTITY =====
  "entity_id": "attraction_bangkok_001",
  "canonical_name": "Wat Pho",
  "aliases": [
    "Wat Pho Temple",
    "Temple of the Reclining Buddha",
    "Wat Phra Chetuphon"
  ],
  "entity_type": "attraction",

  # ===== LOCATION =====
  "city": "Bangkok",
  "country": "Thailand",
  "location": "Phra Nakhon District, Bangkok",
  "coordinates": {
    "lat": 13.7466,
    "lon": 100.4927,
    "source": "google_maps",
    "geocoded_at": "2024-01-15T12:00:00Z"
  },

  # ===== EXPERIENCES (All Mentions) =====
  "experiences": [
    {
      "entity_id": "youtube_abc123_entity_005",  # Original Stage 2 entity ID
      "video_id": "youtube_abc123",
      "experience": "Visited the famous reclining Buddha. Very peaceful and beautiful temple. Spent about 2 hours exploring the grounds.",
      "sentiment": "positive",
      "rating": 5.0,
      "cost_mentioned": "200 THB",
      "timestamp_start": 120.5,
      "timestamp_end": 450.2,
      "confidence_score": 0.95,
      "tags": ["temple", "buddha", "cultural"],
      "traveler_profile": {
        "traveler_type": "couple",
        "budget_tier": "mid-range",
        "travel_style": ["cultural", "photography"]
      }
    },
    # ... more experiences from other videos
  ],
  "source_video_ids": [
    "youtube_abc123",
    "youtube_def456",
    "youtube_ghi789"
  ],

  # ===== AGGREGATED STATS =====
  "total_mentions": 5,
  "confidence_score": 0.92,
  "source_video_count": 3,

  # ===== CONSENSUS (LLM-Generated) =====
  "consensus": {
    "avg_rating": 4.5,
    "avg_cost": "$",  # budget-friendly
    "themes": ["cultural", "peaceful", "photography", "architecture"],
    "best_for": ["couples", "solo", "cultural enthusiasts", "photographers"],
    "top_experiences": [
      "Seeing the 46-meter reclining Buddha",
      "Traditional Thai massage at the temple",
      "Exploring intricate temple architecture and murals"
    ],
    "traveler_profiles": [
      {
        "profile_key": "couple_mid-range",
        "count": 3,
        "avg_rating": 4.7,
        "sentiment_distribution": {"positive": 3, "neutral": 0, "negative": 0}
      },
      {
        "profile_key": "solo_budget",
        "count": 2,
        "avg_rating": 4.3,
        "sentiment_distribution": {"positive": 2, "neutral": 0, "negative": 0}
      }
    ]
  },

  # ===== ENRICHMENT DATA =====
  "temporal_info": {
    "opening_hours": "08:00-18:30 daily",
    "best_time_to_visit": "early morning (8-10am) to avoid crowds",
    "seasonal_info": "Best during cool season (Nov-Feb)",
    "source": "hybrid",  # transcript + LLM
    "confidence": 0.90
  },

  "logistics_info": {
    "typical_duration": "1.5-2 hours",
    "cost_range": "200-300 THB (entrance + optional massage)",
    "booking_required": false,
    "accessibility": "wheelchair accessible in main areas",
    "source": "transcript_extracted",
    "confidence": 0.95
  },

  "practical_tips": [
    "Dress modestly (cover shoulders and knees)",
    "Arrive early to avoid large tour groups",
    "Try the traditional Thai massage on-site",
    "Bring water and sunscreen"
  ],

  # ===== COMPUTED SCORES =====
  "popularity_score": 0.85,  # Based on mentions + recency
  "freshness_score": 0.72,   # How recent the mentions are
  "fame_score": 0.79,        # Combination of popularity + confidence

  # ===== REGISTRY TRACKING =====
  "first_seen_video_id": "youtube_abc123",
  "last_seen_video_id": "youtube_ghi789",

  # ===== TIMESTAMPS =====
  "created_at": "2024-01-10T08:00:00Z",
  "updated_at": "2024-01-15T12:00:00Z"
}
```

---

## 💡 INSIGHT PIPELINE (Parallel Process)

**Purpose:** Extract reusable travel tips from filtered entities

### Pass 1: Filtered Entity Enrichment

**Input:** Entities filtered out from main pipeline (apps, websites, services)

**Function:** `extract_insights_from_entity(entity)`

**Example Input:**
```python
filtered_entity = {
  "canonical_name": "Grab",
  "entity_type": "service",
  "filter_reason": "apps_websites",
  "city": "Bangkok",
  "experiences": [
    "Used Grab for all rides. Much cheaper than taxis and very reliable.",
    "Grab was essential for getting around. Download it before you arrive."
  ]
}
```

**LLM Extraction:**
```json
{
  "insights": [
    {
      "category": "services",
      "scope": "thailand",
      "title": "Use Grab for Transportation",
      "content": "Grab is the most reliable and affordable ride-hailing service in Thailand. Download the app before arrival and link a payment method. Generally 30-50% cheaper than taxis.",
      "tags": ["transportation", "app", "cost-saving"],
      "mentioned_entities": ["Bangkok", "Chiang Mai"],
      "confidence": 0.90
    }
  ]
}
```

---

### Pass 2: Info-Only Video Processing

**Input:** Videos with < 5 place entities (mostly tips/advice)

**Function:** `extract_insights_from_transcript(transcript)`

**Example:** "10 Things to Pack for Thailand" video

**LLM Extraction:**
```json
{
  "insights": [
    {
      "category": "packing",
      "scope": "thailand",
      "title": "Power Adapter",
      "content": "Thailand uses Type A, B, C outlets (220V). Bring a universal adapter.",
      "tags": ["packing", "electronics"],
      "confidence": 0.95
    },
    {
      "category": "tips",
      "scope": "thailand",
      "title": "Cash for Markets",
      "content": "Bring small bills (20-100 THB) for street markets and food stalls. Many don't accept cards.",
      "tags": ["money", "markets"],
      "confidence": 0.88
    }
  ]
}
```

---

### Insight Deduplication (3-Tier)

**Similar to entity deduplication:**

1. **Exact Match:** Same content + category + scope
2. **Fuzzy Match:** 90% similar content
3. **Semantic Match:** Embedding similarity

**Canonical Insights:**
```python
{
  "insight_id": "thailand_services_001",
  "category": "services",
  "scope": "thailand",
  "title": "Use Grab for Transportation",
  "content": "...",
  "source_videos": ["vid1", "vid2", "vid3"],
  "total_mentions": 3,
  "confidence": 0.92
}
```

---

## 📈 Summary

### Data Flow

```
YouTube URL
    → Stage 1: Transcript (1 video → 1 transcript)
    → Stage 2: Entities (1 transcript → 10-50 entities)
    → Stage 3: Canonical (100 entities → 30 canonical after dedup)
    → Insights: Tips (filtered entities → insights)
```

### Processing Time (Estimates)

- Stage 1: 5-10 min per video (download + transcribe)
- Stage 2: 30-60 sec per video (LLM extraction)
- Stage 3: 5-10 min per 1000 entities (dedup + canonicalize + geocode)
- Insights: 10-20 sec per filtered entity

### Current Storage

- **Stage 1:** S3 raw JSONL
- **Stage 2:** S3 individual JSONL files
- **Stage 3:** S3 canonical JSONL (multiple formats)
- **Metadata:** S3 JSON tracker file

---

## 🎯 Questions for Refinement

Now that you understand the full pipeline, what would you like to refine about the canonical entity structure?

1. **Which fields to keep/remove?**
2. **New fields to add?**
3. **How to structure nested data (consensus, temporal_info, etc.)?**
4. **What PostgreSQL tables make sense for your use case?**

Let me know what you want to change, and I'll design the PostgreSQL schema accordingly!
