# Data Flow

This document illustrates how data transforms through the TravelAI pipeline, from raw YouTube videos to personalized itineraries.

---

## High-Level Data Flow

```
YouTube Video URL
    ↓
[Stage 1] Video + Audio + Metadata
    ↓
[Stage 1] Transcript (12,500 tokens)
    ↓
[Stage 2] Raw Entities (87 entities)
    ↓
[Stage 2] Deduplicated Entities (64 entities per video)
    ↓
[Stage 3] Canonical Entities (128 raw → 62 canonical across videos)
    ↓
[Stage 3] Enriched Canonical Entities (temporal + logistics metadata)
    ↓
[Stage 4] Vector Embeddings (175 vectors: 62 × 3 types - some entities lack logistics/experience)
    ↓
[Stage 5] User Query ("5 days Bangkok solo budget")
    ↓
[Stage 5] Retrieved Entities (50 → re-ranked to 20)
    ↓
[Stage 5] Personalized Itinerary (day-by-day plan)
```

---

## Stage 1: Video → Transcript

### Input
```
YouTube URL: https://www.youtube.com/watch?v=UEDeptPVNQA
```

### Processing
1. **YouTube Data API:** Fetch metadata
2. **yt-dlp:** Download audio (MP3)
3. **Whisper:** Transcribe audio to text

### Output
**File:** `s3://your-bucket/stage1_transcripts/youtube_UEDeptPVNQA.json`

```json
{
  "video_id": "youtube_UEDeptPVNQA",
  "url": "https://www.youtube.com/watch?v=UEDeptPVNQA",
  "title": "BANGKOK Travel Guide 2024 | Best Places to Visit",
  "channel": "Travel with Dave",
  "duration_seconds": 895,
  "view_count": 125000,
  "upload_date": "2024-08-15",
  "language": "en",
  "transcript": "Hey everyone, today we're exploring Bangkok, one of the most vibrant cities in Southeast Asia. We'll start our day at the Grand Palace, an absolute must-see. The intricate details of the temples here are just breathtaking...",
  "transcript_tokens": 12543,
  "quality_score": 0.87,
  "processing_timestamp": "2026-01-29T10:15:23Z"
}
```

**Data Size:** ~15 KB per video

---

## Stage 2: Transcript → Entities

### Input
Stage 1 transcript (12,543 tokens)

### Processing
1. **Semantic Chunking:** Split into 8 coherent chunks (~1,500 tokens each)
2. **LLM Extraction:** Extract entities per chunk
3. **Fuzzy Deduplication:** Merge similar entities (85% threshold)
4. **Traveler Profile:** Infer VIBE dimensions

### Output
**File:** `s3://your-bucket/stage2_entities/youtube_UEDeptPVNQA.json`

```json
{
  "video_id": "youtube_UEDeptPVNQA",
  "processing_timestamp": "2026-01-29T10:18:45Z",
  "traveler_profile": {
    "touristiness": 7,
    "adventure_level": 4,
    "budget_level": 5,
    "pace": "moderate",
    "food_focus": 6,
    "confidence": 0.82
  },
  "entities": [
    {
      "entity_id": "youtube_UEDeptPVNQA_place_001",
      "name": "Grand Palace",
      "type": "place",
      "subtype": "historical_site",
      "sentiment": "positive",
      "context": "An absolute must-see with intricate temple details that are breathtaking",
      "vibe": {
        "touristiness": 9,
        "adventure_level": 2,
        "budget_level": 6,
        "pace": "slow"
      },
      "location": {
        "city": "Bangkok",
        "country": "Thailand"
      },
      "mentions": 3,
      "timestamps": ["00:02:15", "00:05:30", "00:12:45"],
      "confidence": 0.94
    },
    {
      "entity_id": "youtube_UEDeptPVNQA_restaurant_001",
      "name": "Jay Fai",
      "type": "restaurant",
      "subtype": "street_food",
      "cuisine": ["Thai"],
      "price_range": "$$",
      "sentiment": "positive",
      "context": "Michelin-starred street food, crab omelette is legendary but expect long queues",
      "vibe": {
        "touristiness": 8,
        "budget_level": 6,
        "food_focus": 10
      },
      "location": {
        "city": "Bangkok",
        "neighborhood": "Phra Nakhon"
      },
      "mentions": 2,
      "timestamps": ["00:08:20", "00:09:15"],
      "confidence": 0.91
    }
  ],
  "entity_count": {
    "place": 28,
    "restaurant": 18,
    "hotel": 6,
    "activity": 8,
    "general_tip": 4,
    "total": 64
  },
  "cost": {
    "extraction_cost": 0.0023,
    "total_tokens": 14200
  }
}
```

**Data Size:** ~45 KB per video
**Entities:** 87 raw → 64 after deduplication

---

## Stage 3: Entities → Canonical Entities

### Input
Multiple Stage 2 entity files (e.g., 2 videos with 128 total raw entities)

### Processing

#### 4-Tier Deduplication
```
Video 1: "Grand Palace"
Video 2: "The Grand Palace"
    ↓ Tier 1 (Exact) → No match
    ↓ Tier 2 (Fuzzy 85%) → Match! (92% similarity)
    ↓ Merge into canonical entity

Video 1: "Jay Fai"
Video 2: "Jay Fai Restaurant"
    ↓ Tier 1 (Exact) → No match
    ↓ Tier 2 (Fuzzy 85%) → Match! (88% similarity)
    ↓ Merge into canonical entity

Video 1: "Chatuchak Market"
Video 2: "Weekend Market Bangkok"
    ↓ Tier 1 (Exact) → No match
    ↓ Tier 2 (Fuzzy 85%) → No match (65% similarity)
    ↓ Tier 3 (Geohash) → Geocode both
        • Chatuchak Market: lat=13.7998, lon=100.5498, geohash=w4rqqq
        • Weekend Market: lat=13.7999, lon=100.5497, geohash=w4rqqq
    ↓ Same geohash → Match!
    ↓ Merge into canonical entity

Video 1: "Sukhumvit Area"
Video 2: "Sukhumvit Road"
    ↓ Tier 1-3 → No definitive match
    ↓ Tier 4 (LLM Consensus)
        • LLM: "These refer to the same general area in Bangkok"
    ↓ Merge into canonical entity
```

#### Enrichment
For each canonical entity, add:
- `temporal_info`: Best time to visit
- `logistics_info`: Opening hours, booking
- `popularity_score`: Based on mentions
- `data_freshness`: Based on video upload dates

### Output
**File:** `s3://your-bucket/metadata/canonical_entities.json`

```json
{
  "canonical_place_001": {
    "canonical_id": "canonical_place_001",
    "name": "Grand Palace",
    "type": "place",
    "subtype": "historical_site",
    "location": {
      "city": "Bangkok",
      "country": "Thailand",
      "lat": 13.7498,
      "lon": 100.4914,
      "geohash": "w4rqjg"
    },
    "merged_from": [
      "youtube_UEDeptPVNQA_place_001",
      "youtube_8m8ReerO060_place_003"
    ],
    "source_videos": ["youtube_UEDeptPVNQA", "youtube_8m8ReerO060"],
    "mention_count": 5,
    "popularity_score": 89,
    "data_freshness": 92,
    "average_sentiment": 0.91,
    "average_vibe": {
      "touristiness": 9,
      "adventure_level": 2,
      "budget_level": 6
    },
    "contexts": [
      "An absolute must-see with intricate temple details",
      "The Grand Palace is the most iconic landmark in Bangkok"
    ],
    "temporal_info": {
      "best_months": [11, 12, 1, 2],
      "avoid_months": [4, 5],
      "seasonal_notes": "Best visited in cool season (November-February). Avoid hot season (April-May).",
      "time_of_day": "Morning (8am-10am) to avoid crowds",
      "recommended_duration_hours": 2.5
    },
    "logistics_info": {
      "opening_hours": "Daily 8:30-15:30 (last entry 15:00)",
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
}
```

**Data Size:** ~120 KB for 62 canonical entities
**Reduction:** 128 raw entities → 62 canonical (51.6% reduction)

---

## Stage 4: Canonical Entities → Vector Embeddings

### Input
62 canonical entities from Stage 3

### Processing
1. Generate text representations for each embedding type:
   - **full_context:** Complete description
   - **experience:** Subjective experiences only
   - **logistics:** Practical information only
2. Generate embeddings using `gte-large` (768 dimensions)
3. Add enhanced metadata for filtering

### Example Entity Text Representations

**Full Context:**
```
Grand Palace, Bangkok, Thailand
Type: historical_site
Description: An absolute must-see with intricate temple details. The Grand Palace is the most iconic landmark in Bangkok.
Best Time: November-February (cool season)
Hours: Daily 8:30-15:30
Booking: Not required
Entry: 500 THB
Tips: Dress modestly, arrive early to avoid crowds
Popularity: 89/100
Mentions: 5 videos
```

**Experience Only:**
```
Grand Palace, Bangkok, Thailand
An absolute must-see with intricate temple details. The most iconic landmark in Bangkok. Breathtaking architecture. Best visited in the morning to avoid crowds. Can get very busy during peak season.
```

**Logistics Only:**
```
Grand Palace, Bangkok, Thailand
Opening hours: Daily 8:30-15:30 (last entry 15:00)
Entry fee: 500 THB (~$15)
Dress code: Cover shoulders and knees
Booking: Not required
Duration: 2.5 hours recommended
Audio guide available: 200 THB
```

### Output
**ChromaDB Collection:** `travel_entities`

```python
# Vector 1: Full Context
{
  "id": "canonical_place_001_full_context",
  "embedding": [0.123, -0.456, 0.789, ...],  # 768 dimensions
  "metadata": {
    "canonical_id": "canonical_place_001",
    "entity_name": "Grand Palace",
    "entity_type": "place",
    "entity_subtype": "historical_site",
    "embedding_type": "full_context",
    "city": "Bangkok",
    "country": "Thailand",
    "geohash": "w4rqjg",
    "geohash_precision": 6,
    "lat": 13.7498,
    "lon": 100.4914,
    "mention_count": 5,
    "popularity_score": 89,
    "data_freshness": 92,
    "best_months": [11, 12, 1, 2],
    "avoid_months": [4, 5],
    "booking_required": false,
    "has_entry_fee": true,
    "vibe_touristiness": 9,
    "vibe_adventure": 2,
    "vibe_budget": 6
  }
}

# Vector 2: Experience Only
{
  "id": "canonical_place_001_experience",
  "embedding": [0.234, -0.567, 0.890, ...],  # 768 dimensions
  "metadata": {...}  # Same metadata as above
}

# Vector 3: Logistics Only
{
  "id": "canonical_place_001_logistics",
  "embedding": [0.345, -0.678, 0.901, ...],  # 768 dimensions
  "metadata": {...}  # Same metadata as above
}
```

**Total Vectors:** 175 (62 entities × ~2.8 avg, some entities lack logistics/experience)
**Vector Dimension:** 768 (gte-large)
**Storage:** ChromaDB Chroma Cloud

---

## Stage 5: Query → Itinerary

### Input
User query: `"5 days Bangkok solo budget street food"`

### Phase 1: Intent Parsing

**LLM extracts structured intent:**
```json
{
  "destination": "Bangkok, Thailand",
  "duration_days": 5,
  "travel_style": "solo",
  "vibe": {
    "touristiness": 5,
    "adventure_level": 6,
    "budget_level": 3,
    "pace": "moderate",
    "food_focus": 9
  },
  "constraints": ["budget", "street food focus"],
  "preferences": ["authentic local experiences", "food-centric"]
}
```

### Phase 2: Retrieval

**Query ChromaDB with filters:**
```python
results = chromadb.query(
    query_embeddings=embed_query("Bangkok budget street food experiences"),
    n_results=50,
    where={
        "city": "Bangkok",
        "country": "Thailand",
        "vibe_budget": {"$lte": 5},  # Budget-friendly only
        "booking_required": False     # No advance booking needed
    }
)
```

**Retrieved:** 50 entities (places, restaurants, activities)

### Phase 3: Re-ranking

**Score each entity by VIBE match:**
```python
Grand Palace:
  - touristiness: 9 (user wants 5) → penalty
  - budget: 6 (user wants 3) → penalty
  - food_focus: 2 (user wants 9) → major penalty
  → Score: 4.2/10

Jay Fai (street food):
  - touristiness: 8 (user wants 5) → slight penalty
  - budget: 6 (user wants 3) → penalty
  - food_focus: 10 (user wants 9) → perfect match!
  → Score: 8.5/10

Chatuchak Weekend Market:
  - touristiness: 7 (user wants 5) → slight penalty
  - budget: 3 (user wants 3) → perfect match!
  - food_focus: 8 (user wants 9) → great match!
  → Score: 9.2/10
```

**Re-ranked:** Top 20 entities selected

### Phase 4: Context Building

**Assemble context for LLM:**
```
User Intent:
- Destination: Bangkok, Thailand
- Duration: 5 days
- Style: Solo budget traveler
- Focus: Street food experiences
- VIBE: Low touristiness, high food focus

Retrieved Entities:
[Top 20 entities with full details...]

Task: Generate a day-by-day itinerary optimized for this traveler's vibe and constraints.
```

### Phase 5: Generation

**LLM generates itinerary:**
```json
{
  "destination": "Bangkok, Thailand",
  "duration_days": 5,
  "vibe_match_score": 8.9,
  "days": [
    {
      "day": 1,
      "theme": "Old Bangkok Street Food Discovery",
      "activities": [
        {
          "time": "09:00 - 12:00",
          "entity_id": "canonical_place_012",
          "name": "Chatuchak Weekend Market",
          "type": "place",
          "description": "Explore Bangkok's largest market with endless street food stalls. Perfect for budget travelers.",
          "why_recommended": "Matches your budget focus and offers incredible street food variety. Low touristiness compared to main attractions.",
          "estimated_cost": "$10-15",
          "duration_hours": 3
        },
        {
          "time": "13:00 - 14:30",
          "entity_id": "canonical_restaurant_005",
          "name": "Jay Fai",
          "type": "restaurant",
          "description": "Michelin-starred street food, famous for crab omelette.",
          "why_recommended": "Legendary street food experience, though slightly pricey for budget travel. Worth it for the experience.",
          "estimated_cost": "$20-25",
          "duration_hours": 1.5
        }
      ],
      "daily_budget": "$45",
      "travel_between_locations": [
        {
          "from": "Chatuchak Market",
          "to": "Jay Fai",
          "mode": "BTS + walk",
          "duration_minutes": 35,
          "cost": "$1.50"
        }
      ]
    }
  ]
}
```

### Phase 6: Validation

**Check feasibility:**
- ✅ Distances reasonable (all activities < 10km apart)
- ✅ Opening hours match (Chatuchak open on weekend)
- ✅ Budget realistic ($45/day for budget travel)
- ⚠️ Jay Fai may have 2-hour queue (add note)

### Phase 7: Narrative

**Add tips and explanations:**
```json
{
  "travel_tips": [
    "Download Grab app for easy transport (~$3-5 per ride)",
    "Carry cash - most street vendors don't accept cards",
    "Jay Fai has long queues (2-3 hours), arrive before 11am or after 2pm"
  ],
  "budget_breakdown": {
    "accommodation": "$75 (5 nights hostel in Sukhumvit)",
    "food": "$125 (focused on street food)",
    "transport": "$25 (BTS + occasional Grab)",
    "activities": "$50 (entry fees, tours)",
    "total": "$275 for 5 days"
  },
  "cultural_notes": [
    "Remove shoes before entering temples",
    "Dress modestly when visiting religious sites"
  ]
}
```

### Output
**File:** `s3://your-bucket/stage5_itineraries/itinerary_2026-01-29_14-23-45.json`

**Data Size:** ~25 KB
**Cost:** $0.0103 (total for all 7 phases)

---

## Data Transformation Summary

| Stage | Input | Output | Transformation |
|-------|-------|--------|----------------|
| **Stage 1** | YouTube URL | Transcript JSON | Video → Text (12,500 tokens) |
| **Stage 2** | Transcript (12.5k tokens) | Entity JSON | Text → 64 structured entities |
| **Stage 3** | 128 raw entities (2 videos) | 62 canonical entities | Deduplication (51% reduction) + Enrichment |
| **Stage 4** | 62 canonical entities | 175 vectors | Entities → Embeddings (768 dims × 3 types) |
| **Stage 5** | User query + vectors | Itinerary JSON | Query → 5-day plan (50 → 20 → 15 entities) |

---

## Data Growth Patterns

### Per Video
- **Stage 1:** 15 KB (transcript)
- **Stage 2:** 45 KB (entities)
- **Stage 3:** Contributes to shared canonical pool
- **Stage 4:** ~4 KB metadata (vectors stored in ChromaDB)

### Across 100 Videos
- **Stage 1:** 1.5 MB (transcripts)
- **Stage 2:** 4.5 MB (entities)
- **Stage 3:** ~500 KB (canonical entities, assuming 50% dedup rate)
- **Stage 4:** ~400 KB metadata + 40 MB vectors (in ChromaDB)
- **Total S3:** ~7 MB for 100 videos

### Cost Scaling
- **100 videos:** ~$0.25 (Stages 1-4)
- **1,000 videos:** ~$2.50 (Stages 1-4)
- **Per itinerary:** ~$0.01-0.02 (Stage 5)

---

## Key Data Characteristics

### Data Quality Improvements
1. **Stage 1 → 2:** Raw text → Structured entities
2. **Stage 2 → 3:** Per-video → Cross-video canonicalization
3. **Stage 3 → 4:** Entities → Searchable vectors with metadata
4. **Stage 4 → 5:** Vectors → Personalized recommendations

### Data Reduction
- **Stage 2:** 87 raw → 64 deduplicated (26% reduction per video)
- **Stage 3:** 128 raw → 62 canonical (51% reduction across videos)
- **Stage 5:** 50 retrieved → 20 re-ranked → 15 in itinerary (70% reduction)

### Data Enrichment
- **Stage 3:** Adds temporal_info, logistics_info, popularity_score, data_freshness
- **Stage 4:** Adds geohash, embedding_type, enhanced metadata
- **Stage 5:** Adds why_recommended, timing, travel_between_locations

---

## References

- **System Architecture:** [system-architecture.md](system-architecture.md)
- **Pipeline Overview:** [pipeline-overview.md](pipeline-overview.md)
- **Data Schemas:** [data-schemas.md](../04-reference/data-schemas.md)
- **S3 Storage:** [s3-storage.md](../05-infrastructure/s3-storage.md)

---

**Data flow documented!** Next: [Stage 1: Crawling](../03-pipeline-stages/stage1-crawling.md)
