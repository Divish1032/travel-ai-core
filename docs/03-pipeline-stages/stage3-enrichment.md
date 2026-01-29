# Stage 3: Canonicalization & Enrichment

Stage 3 deduplicates entities across all videos using a 4-tier strategy and enriches canonical entities with temporal, logistics, and computed metadata.

**Implementation:** [`src/processors/stage3_enrichment.py`](../../src/processors/stage3_enrichment.py), [`src/processors/deduplication.py`](../../src/processors/deduplication.py), [`src/processors/llm_enrichment.py`](../../src/processors/llm_enrichment.py)

---

## Overview

### Purpose
Transform per-video entities into canonical, enriched entities across all videos with comprehensive metadata.

### Inputs
- All Stage 2 entity files from S3
- Video upload dates for freshness calculation

### Outputs
- Canonical entities (deduplicated across videos)
- Enriched metadata (temporal, logistics, popularity, freshness)
- Provenance tracking (source videos)

### Storage
- **S3 Path:** `s3://{bucket}/metadata/canonical_entities.json`
- **File Size:** ~120 KB for 62 canonical entities

---

## Processing Pipeline

### 1. Load Stage 2 Entities

**Function:** `load_all_stage2_entities()`

Loads all Stage 2 entity files from S3:
```python
{
  "all_entities": [...],      # All entities from all videos
  "video_metadata": {...},    # Video metadata for freshness
  "entity_count": 128,        # Total raw entities
  "video_count": 2            # Total videos
}
```

**Normalization:**
- Normalize entity names (lowercase, strip whitespace)
- Normalize locations (city names)
- Add video_id and source_id for provenance

---

## 4-Tier Deduplication Strategy

### Tier 1: Exact Matching

**Function:** `exact_match()`, `group_exact_matches()`

**Criteria:**
- Same normalized name (case-insensitive)
- Same normalized location (city)
- Same entity_type

**Example:**
```
Video 1: "Wat Pho" (bangkok, attraction)
Video 2: "Wat Pho" (bangkok, attraction)
→ EXACT MATCH → Merge into canonical_attraction_001
```

**Algorithm:**
1. Create signature: `{name}||{location}||{type}`
2. Group entities with same signature
3. Auto-merge without verification

**Typical Results:** 30-40% of entities match exactly

---

### Tier 2: Fuzzy Matching

**Function:** `fuzzy_match()`, `find_fuzzy_candidates()`

Uses **rapidfuzz** for fuzzy string matching.

**Thresholds:**
- **≥0.90 similarity:** Auto-match (no LLM verification needed)
- **0.80-0.89 similarity:** LLM verification required
- **<0.80 similarity:** Not considered a match

**Similarity Calculation:**
```python
name_similarity = fuzz.ratio(name1, name2) / 100
location_similarity = fuzz.ratio(location1, location2) / 100
weighted_similarity = (name_similarity * 0.7) + (location_similarity * 0.3)
```

**Examples:**

| Entity 1 | Entity 2 | Similarity | Action |
|----------|----------|------------|--------|
| "Grand Palace" | "The Grand Palace" | 0.92 | ✅ Auto-match |
| "Wat Chalong" | "Wat Chalong Temple" | 0.88 | 🔍 LLM verify |
| "Big Buddha" | "The Big Buddha Temple" | 0.85 | 🔍 LLM verify |
| "Chatuchak Market" | "JJ Market" | 0.45 | ❌ No match |

**Algorithm:**
1. Compare all entity pairs (O(n²), acceptable for <500 entities per type)
2. Calculate fuzzy similarity
3. If ≥0.90: Auto-merge
4. If 0.80-0.89: Add to LLM verification queue

**Typical Results:** 15-25% of entities match fuzzily

---

### Tier 3: Semantic Matching

**Function:** `find_semantic_candidates()`

Uses **gte-large embeddings** for semantic similarity.

**Threshold:**
- **≥0.85 similarity:** LLM verification required

**Process:**
1. Generate embeddings for entity names + contexts
2. Calculate cosine similarity between embeddings
3. Find candidates above threshold
4. Send to LLM for verification

**Examples:**

| Entity 1 | Entity 2 | Semantic Sim | LLM Decision |
|----------|----------|--------------|--------------|
| "Chatuchak Market" | "Weekend Market" | 0.91 | ✅ Same place |
| "Sukhumvit Area" | "Sukhumvit Road" | 0.89 | ✅ Same area |
| "Patong Beach" | "Kata Beach" | 0.85 | ❌ Different beaches |

**Typical Results:** 5-10% of entities match semantically

---

### Tier 4: LLM Consensus

**Function:** `batch_verify_matches()`

Uses **LLM (Gemini/OpenAI/DeepSeek)** to verify ambiguous cases from Tiers 2 and 3.

**LLM Prompt:**
```
Are these two entities referring to the same place?

Entity 1:
Name: "Wat Chalong"
Type: attraction
Location: Phuket
Context: "Beautiful temple with intricate details"

Entity 2:
Name: "Wat Chalong Temple"
Type: attraction
Location: Phuket
Context: "Must-visit temple in southern Phuket"

Answer: YES or NO
Confidence: 0.0-1.0
Reasoning: [Brief explanation]
```

**LLM Response:**
```json
{
  "match": true,
  "confidence": 0.95,
  "reasoning": "Same temple, 'Wat Chalong' is commonly called 'Wat Chalong Temple'"
}
```

**Confidence Threshold:** 0.70 minimum to accept match

**Batch Processing:**
- Groups candidates into batches of 10
- Processes in parallel for efficiency
- Caches results to avoid repeated LLM calls

**Typical Results:** 3-8% of entities verified by LLM

---

## Deduplication Statistics

**Example Results (128 raw entities → 62 canonical):**

| Tier | Method | Matches | Entities Merged | Cost |
|------|--------|---------|-----------------|------|
| Tier 1 | Exact | 45 duplicates | 45 entities | FREE |
| Tier 2 | Fuzzy (≥0.90) | 12 auto-matches | 12 entities | FREE |
| Tier 2 | Fuzzy (0.80-0.89) | 8 LLM-verified | 6 entities | $0.002 |
| Tier 3 | Semantic | 5 LLM-verified | 3 entities | $0.001 |
| **Total** | | **70 duplicates** | **66 merged** | **$0.003** |

**Deduplication Rate:** 51.6% reduction (128 → 62)

---

## Enrichment Process

After deduplication, each canonical entity is enriched with:

### 1. Temporal Information

**Function:** `aggregate_temporal_info()`

**Fields Added:**
```json
{
  "temporal_info": {
    "best_months": [11, 12, 1, 2],        // November-February
    "avoid_months": [4, 5],                // April-May (hot season)
    "seasonal_notes": "Best in cool season, avoid hot season",
    "time_of_day": "morning",              // Best time to visit
    "recommended_duration_hours": 2.5
  }
}
```

**Data Sources:**
1. **Transcript Data:** Extracted from traveler mentions
2. **LLM Knowledge:** For famous entities (e.g., Grand Palace, Wat Pho)
3. **Consensus:** Aggregate across all source videos

**Example:**
```
Video 1: "Visit Grand Palace in the morning to avoid crowds"
Video 2: "Best time is November to February"
Video 3: "Avoid visiting in April - too hot"

→ Aggregated:
  best_months: [11, 12, 1, 2]
  time_of_day: "morning"
  seasonal_notes: "Cool season recommended, very hot in April"
```

---

### 2. Logistics Information

**Function:** `aggregate_logistics_info()`

**Fields Added:**
```json
{
  "logistics_info": {
    "opening_hours": "Daily 8:30-15:30",
    "closed_on": [],
    "booking_required": false,
    "advance_booking_days": 0,
    "entry_fee": "500 THB (~$15)",
    "practical_tips": [
      "Dress modestly (cover shoulders and knees)",
      "Arrive early to avoid crowds",
      "Audio guide available for 200 THB"
    ]
  }
}
```

**Data Sources:**
1. **Transcript Data:** Extracted from traveler experiences
2. **LLM Knowledge:** For well-known places
3. **Geocoding:** Location verification

---

### 3. Computed Metrics

**Popularity Score:**
```python
popularity_score = min(100, (mention_count / max_mentions) * 100)
```
- Range: 0-100
- Based on total mentions across all videos
- Higher = more popular/talked about

**Data Freshness Score:**
```python
recency_score = weighted_average_of_video_upload_dates
```
- Range: 0-100
- Based on how recent the source videos are
- Higher = more recent information

**Examples:**
```
Entity: "Grand Palace"
- Mentions: 8 (across 5 videos)
- Max mentions: 10
- Popularity: 80/100

- Latest video: 2024-11-15 (3 months ago)
- Oldest video: 2024-06-20 (8 months ago)
- Freshness: 92/100
```

---

### 4. Provenance Tracking

**Fields Added:**
```json
{
  "merged_from": [
    "youtube_UEDeptPVNQA_place_001",
    "youtube_8m8ReerO060_place_003"
  ],
  "source_videos": [
    "youtube_UEDeptPVNQA",
    "youtube_8m8ReerO060"
  ],
  "mention_count": 8,
  "first_seen": "2024-06-20",
  "last_seen": "2024-11-15"
}
```

**Benefits:**
- Full traceability to source videos
- Can verify information by watching original videos
- Understand entity popularity over time

---

## LLM-Based Enrichment

**Function:** `enrich_entity_with_llm()`

For **well-known entities** (e.g., Grand Palace, Wat Pho), TravelAI uses LLM knowledge to fill gaps in transcript data.

**Famous Entity Detection:**
```python
FAMOUS_ENTITIES = {
    'grand palace': 0.95,
    'wat pho': 0.95,
    'wat arun': 0.95,
    'chatuchak market': 0.90,
    'khao san road': 0.90,
    ...
}
```

**Fame Score:** 0.0-1.0 confidence that LLM has accurate knowledge

**LLM Enrichment Prompt:**
```
Entity: Grand Palace
Location: Bangkok, Thailand
Type: attraction

Provide:
1. Best time to visit (months, time of day)
2. Opening hours and entry fees
3. Booking requirements
4. Practical tips for visitors
5. Typical duration

Format: JSON
```

**LLM Response:**
```json
{
  "best_months": [11, 12, 1, 2],
  "opening_hours": "Daily 8:30-15:30",
  "entry_fee": "500 THB",
  "booking_required": false,
  "practical_tips": ["Dress modestly", "Arrive early"],
  "recommended_duration": "2-3 hours",
  "provenance": "llm_inferred"
}
```

**Hybrid Data Merging:**
- **Transcript data:** Prioritized (real experiences)
- **LLM data:** Fills gaps where transcript lacks info
- **Provenance:** Tracked as `transcript_extracted`, `llm_inferred`, or `hybrid`

**Cost:** ~$0.001-0.002 per entity (only for famous entities, ~20% of total)

---

## Geocoding & Geohash

**Function:** `geocode_entity()` from [`src/processors/geolocation.py`](../../src/processors/geolocation.py)

**Purpose:** Add precise coordinates and geohash for geospatial search

**Geocoding Strategy:**
- **90% free:** Nominatim (OpenStreetMap)
- **10% fallback:** Google Maps Geocoding API (for Nominatim failures)

**Process:**
1. Construct query: `{entity_name}, {city}, {country}`
2. Call Nominatim API
3. If fails, fallback to Google Maps API
4. Extract lat/lon coordinates
5. Generate geohash (precision 7)

**Output:**
```json
{
  "location": {
    "city": "Bangkok",
    "country": "Thailand",
    "lat": 13.7498,
    "lon": 100.4914,
    "geohash": "w4rqjgb"
  }
}
```

**Geohash:**
- **Precision 7:** ~150m × 150m area (street-level)
- Used for geospatial filtering in Stage 4
- Example: All Bangkok entities start with `w4r`

---

## CLI Usage

### Run Stage 3

```bash
# Process all Stage 2 entities
./crawl.sh process-stage3

# Process with specific LLM provider
./crawl.sh process-stage3 --provider gemini
```

### View Canonical Entities

```bash
# Show statistics
./crawl.sh stage3-stats

# View specific entity
./crawl.sh show-entity canonical_place_001

# Validate Stage 3 output
./crawl.sh validate-stage3
```

---

## Performance & Costs

### Processing Time
- **Deduplication:** ~3-5 minutes for 130 entities
- **Enrichment:** ~3-5 minutes for 60 canonical entities
- **Geocoding:** ~2-3 minutes (mostly free Nominatim)
- **Total:** ~8-13 minutes for 2 videos (130 → 62 entities)

### Cost Breakdown

**Per 100 Videos (~300 canonical entities):**
- Tier 2 LLM verification: ~$0.10
- Tier 3 Semantic matching: ~$0.05
- LLM enrichment: ~$0.30 (only for famous entities)
- Geocoding: ~$0.02 (10% Google Maps fallback)
- **Total:** ~$0.47

**Cost per Video:** ~$0.005

---

## Error Handling

### Common Errors

**1. Geocoding Failed**
```
GeocodingError: Could not geocode "Unknown Restaurant"
```
**Solution:**
- Uses entity without coordinates
- Stage 4 will skip geospatial metadata
- Entity still usable via text search

**2. LLM Verification Timeout**
```
TimeoutError: LLM verification exceeded 30 seconds
```
**Solution:**
- Automatic retry with exponential backoff
- Falls back to not merging if LLM unavailable
- Prefers false negatives over false positives

**3. Insufficient Data for Enrichment**
```
Warning: Not enough transcript data for temporal_info
```
**Solution:**
- Falls back to LLM enrichment for famous entities
- Leaves fields empty for unknown entities
- Stage 5 will use available data only

---

## Configuration

### Environment Variables

```bash
# LLM Provider
LLM_PROVIDER=gemini

# Geocoding
GOOGLE_MAPS_API_KEY=your_key_here  # Optional fallback

# Deduplication Thresholds
FUZZY_AUTO_THRESHOLD=0.90          # Auto-match threshold
FUZZY_LLM_THRESHOLD=0.80           # LLM verification threshold
SEMANTIC_THRESHOLD=0.85            # Semantic matching threshold
LLM_CONFIDENCE_MIN=0.70            # Minimum LLM confidence
```

### Advanced Parameters

Edit `src/processors/deduplication.py`:
```python
deduplicate_entities(
    entities,
    auto_match_threshold=0.90,      # Fuzzy auto-match
    llm_verify_threshold=0.80,      # Fuzzy LLM verify
    semantic_threshold=0.85,        # Semantic LLM verify
    llm_confidence_threshold=0.70   # Min LLM confidence
)
```

---

## Quality Assurance

### Deduplication Accuracy

**Metrics to Monitor:**
1. **Deduplication Rate:** 40-60% is typical
2. **False Positives:** Check merged entities manually
3. **False Negatives:** Check singletons for obvious duplicates

**Validation:**
```bash
./crawl.sh validate-stage3
```

### Enrichment Completeness

**Target Completeness:**
- temporal_info: 80%+ of entities
- logistics_info: 70%+ of entities
- popularity_score: 100% of entities
- data_freshness: 100% of entities
- geohash: 85%+ of entities

---

## Best Practices

### 1. Use All 4 Tiers
- **Don't skip tiers** - each catches different duplicate patterns
- Tier 1-2: Fast, catches most duplicates
- Tier 3-4: Slower but catches edge cases

### 2. Monitor LLM Costs
- LLM verification: ~20% of entities
- LLM enrichment: ~20% of entities (famous only)
- Total LLM cost: ~$0.003-0.005 per video

### 3. Validate Geocoding
- Check entities have lat/lon coordinates
- Verify geohashes make sense (e.g., all Bangkok = w4r*)
- Use Google Maps fallback for important entities

### 4. Review Canonical Entities
```bash
./crawl.sh stage3-stats
./crawl.sh show-entity canonical_place_001
```

---

## Output Schema

**File:** `metadata/canonical_entities.json`

```typescript
{
  [canonical_id]: {
    canonical_id: string
    name: string
    type: string
    subtype?: string
    location: {
      city: string
      country: string
      neighborhood?: string
      lat?: number
      lon?: number
      geohash?: string
    }
    merged_from: string[]           // Original entity IDs
    source_videos: string[]         // Video IDs
    mention_count: number
    popularity_score: number        // 0-100
    data_freshness: number          // 0-100
    average_sentiment: number       // -1.0 to 1.0
    average_vibe: {
      touristiness?: number
      adventure_level?: number
      budget_level?: number
      pace?: string
      food_focus?: number
    }
    contexts: string[]              // All contexts merged
    temporal_info?: {
      best_months: number[]         // 1-12
      avoid_months: number[]
      seasonal_notes: string
      time_of_day?: string
      recommended_duration_hours?: number
    }
    logistics_info?: {
      opening_hours?: string
      closed_on?: string[]
      booking_required: boolean
      advance_booking_days: number
      entry_fee?: string
      practical_tips: string[]
    }
    provenance: {
      enrichment_method: "transcript_only" | "llm_inferred" | "hybrid"
      geocoding_source: "nominatim" | "google_maps"
      llm_fame_score?: number
    }
  }
}
```

---

## Next Stage

Once Stage 3 completes:
- ✅ Canonical entities created
- ✅ Temporal + logistics enrichment
- ✅ Geohash for geospatial search
- ➡️ **Ready for Stage 4:** [Vectorization](stage4-vectorization.md)

---

## References

- **Implementation:** [`src/processors/stage3_enrichment.py`](../../src/processors/stage3_enrichment.py)
- **Deduplication:** [`src/processors/deduplication.py`](../../src/processors/deduplication.py)
- **LLM Enrichment:** [`src/processors/llm_enrichment.py`](../../src/processors/llm_enrichment.py)
- **Geocoding:** [`src/processors/geolocation.py`](../../src/processors/geolocation.py)
- **CLI Command:** [`cli/process_stage3.py`](../../cli/process_stage3.py)
- **Pipeline Overview:** [pipeline-overview.md](../02-architecture/pipeline-overview.md)

---

**Stage 3 complete!** Next: [Stage 4: Vectorization](stage4-vectorization.md)
