# Quickstart Guide

This guide walks you through the complete TravelAI pipeline from crawling YouTube videos to generating a personalized itinerary.

**Time:** ~30 minutes
**Prerequisites:** Complete [installation](installation.md) first

---

## Overview

This quickstart demonstrates:
1. Crawling 2 YouTube travel videos
2. Extracting travel entities (places, restaurants, activities)
3. Deduplicating and enriching entities
4. Generating vector embeddings
5. Creating a personalized itinerary

---

## Step 1: Prepare Test URLs

Create a file with YouTube video URLs:

```bash
cat > test_urls.txt << EOF
https://www.youtube.com/watch?v=UEDeptPVNQA
https://www.youtube.com/watch?v=8m8ReerO060
EOF
```

**These videos** are Bangkok travel vlogs (~10-15 minutes each).

---

## Step 2: Activate Environment

```bash
cd TravelAI
source venv/bin/activate
```

**Verify setup:**
```bash
./crawl.sh status
```

**Expected output:**
```
Pipeline Status:
✅ Configuration loaded successfully
✅ AWS credentials valid
✅ S3 bucket accessible: your-travel-ai-data
📊 Total videos: 0
```

---

## Step 3: Stage 1 - Crawl Videos

Download videos and transcribe with Whisper:

```bash
./crawl.sh youtube --input test_urls.txt --limit 2
```

**What happens:**
1. Downloads video metadata from YouTube API
2. Downloads audio using `yt-dlp`
3. Transcribes audio with Whisper (small model)
4. Uploads transcript and metadata to S3

**Duration:** ~5-10 minutes (depends on video length)

**Output:**
```
🎬 Processing: Bangkok Travel Guide
✅ Downloaded audio (15.2 MB)
🎤 Transcribing with Whisper...
✅ Transcription complete (12,500 tokens)
📤 Uploaded to S3: stage1_transcripts/youtube_UEDeptPVNQA.json
```

**Verify:**
```bash
./crawl.sh status
```

Should show: `📋 Stage 1 complete: 2`

---

## Step 4: Stage 2 - Extract Entities

Extract travel entities using LLM:

```bash
./crawl.sh process-stage2 --limit 2
```

**What happens:**
1. Loads transcript from Stage 1
2. Chunks transcript semantically (not fixed-time)
3. Extracts entities per chunk using LLM
4. Deduplicates entities within video (fuzzy matching)
5. Builds traveler profile (VIBE framework)
6. Uploads entities to S3

**Duration:** ~2-5 minutes (LLM API calls)

**Output:**
```
🔍 Extracting entities: youtube_UEDeptPVNQA
  Chunk 1/8: Extracted 12 entities
  Chunk 2/8: Extracted 8 entities
  ...
✅ Total entities: 87 raw → 64 deduplicated
💰 Cost: $0.0023
📤 Uploaded to S3: stage2_entities/youtube_UEDeptPVNQA.json
```

**View extracted entities:**
```bash
./crawl.sh view-stage2 youtube_UEDeptPVNQA
```

**Expected output:**
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
      ...
    }
  ]
}
```

---

## Step 5: Stage 3 - Deduplicate & Enrich

Canonicalize entities across all videos:

```bash
./crawl.sh process-stage3
```

**What happens:**
1. Loads entities from all Stage 2 videos
2. Applies 4-tier deduplication:
   - Tier 1: Exact name matching
   - Tier 2: Fuzzy name matching (85% threshold)
   - Tier 3: Geocoding + geohash matching
   - Tier 4: LLM consensus resolution
3. Enriches canonical entities:
   - `temporal_info`: Best time to visit, seasonal notes
   - `logistics_info`: Opening hours, booking requirements
   - `popularity_score`: Relative popularity (0-100)
   - `data_freshness`: Recency score
4. Saves canonical entities to S3

**Duration:** ~3-8 minutes (geocoding + LLM enrichment)

**Output:**
```
🔄 Stage 3: Deduplication & Enrichment
📥 Loaded 128 raw entities from 2 videos

Tier 1 (Exact): 45 duplicates found
Tier 2 (Fuzzy): 12 duplicates found
Tier 3 (Geohash): 8 duplicates found
Tier 4 (LLM): 3 groups resolved

📊 Results:
  Raw entities: 128
  Canonical entities: 62
  Reduction: 51.6%

🌟 Enriching 62 canonical entities...
  ✅ temporal_info: 58/62 enriched
  ✅ logistics_info: 55/62 enriched
  ✅ popularity_score: 62/62 calculated
  ✅ data_freshness: 62/62 calculated

💰 Total cost: $0.0089
📤 Uploaded to S3: metadata/canonical_entities.json
```

**View canonical entities:**
```bash
./crawl.sh stage3-stats
```

---

## Step 6: Stage 4 - Generate Embeddings

Create vector embeddings for semantic search:

```bash
./crawl.sh process-stage4 --embedding-types all
```

**What happens:**
1. Loads canonical entities from Stage 3
2. Generates embeddings using `gte-large` (local, free)
3. Creates 3 embedding types:
   - `full_context`: Complete entity description
   - `experience`: Subjective experiences only
   - `logistics`: Practical information only
4. Adds enhanced metadata:
   - Geohash for geospatial search
   - Temporal filters (best months)
   - Logistics filters (booking required, etc.)
5. Indexes in ChromaDB (Chroma Cloud)

**Duration:** ~2-5 minutes

**Output:**
```
🔢 Stage 4: Vectorization
📥 Loaded 62 canonical entities

Generating embeddings:
  ✅ full_context: 62 embeddings (768 dims)
  ✅ experience: 58 embeddings (768 dims)
  ✅ logistics: 55 embeddings (768 dims)

📤 Uploading to ChromaDB (Chroma Cloud)...
  ✅ travel_entities collection: 175 vectors indexed

📊 Geohash distribution:
  w4r (Bangkok): 48 entities
  w4q (Pattaya): 8 entities
  ...

✅ Stage 4 complete!
```

**Verify:**
```bash
./crawl.sh stage4-stats
```

---

## Step 7: Stage 5 - Generate Itinerary

Create a personalized itinerary from natural language query:

```bash
./crawl.sh generate-itinerary -q "3 days Bangkok solo budget street food"
```

**What happens (7-phase RAG pipeline):**
1. **Intent Parsing**: Extract destination, duration, vibe, constraints
2. **Retrieval**: Search ChromaDB with geohash + filters
3. **Re-ranking**: Score entities by relevance to vibe
4. **Context Building**: Assemble retrieved entities into context
5. **Generation**: LLM creates day-by-day itinerary
6. **Validation**: Check feasibility (distances, timing, logistics)
7. **Narrative**: Add helpful tips and explanations

**Duration:** ~30-60 seconds

**Output:**
```
🗺️ Generating itinerary...

✅ Intent parsed:
  Destination: Bangkok, Thailand
  Duration: 3 days
  VIBE: touristiness=4, budget=3, food_focus=9
  Constraints: solo, street food focus

🔍 Retrieval: 45 entities found
📊 Re-ranked: Top 20 entities selected
📝 Generating itinerary...

💰 Cost breakdown:
  Intent parsing: $0.0001
  Retrieval: $0.0000 (ChromaDB)
  Re-ranking: $0.0003
  Generation: $0.0087
  Validation: $0.0012
  Total: $0.0103

✅ Itinerary saved: stage5_itineraries/itinerary_2026-01-29_14-23-45.json
```

**View itinerary:**
```bash
cat stage5_itineraries/itinerary_2026-01-29_14-23-45.json
```

**Example itinerary structure:**
```json
{
  "destination": "Bangkok, Thailand",
  "duration_days": 3,
  "vibe_match_score": 8.5,
  "days": [
    {
      "day": 1,
      "theme": "Old Bangkok Street Food Tour",
      "activities": [
        {
          "time": "09:00 - 12:00",
          "entity_id": "canonical_place_001",
          "name": "Chatuchak Weekend Market",
          "description": "Explore Bangkok's largest market...",
          "why_recommended": "Perfect for budget travelers, massive variety of street food..."
        }
      ]
    }
  ],
  "budget_estimate": {
    "accommodation": "$60 (3 nights)",
    "food": "$45",
    "transport": "$15",
    "activities": "$30",
    "total": "$150"
  },
  "travel_tips": [
    "Download Grab app for easy transport",
    "Carry cash - many street vendors don't accept cards"
  ]
}
```

---

## Step 8: Explore with Dashboard

Launch the interactive dashboard:

```bash
./crawl.sh dashboard
```

**Open:** http://localhost:8501

**Features:**
- 🎬 **Videos**: Browse all crawled videos
- 📋 **Video Detail**: Deep dive into transcripts and entities
- 📍 **Entities**: Explore all canonical entities
- 📈 **Analytics**: Pipeline statistics and quality metrics

---

## Common Commands Reference

### Status and Monitoring
```bash
./crawl.sh status                    # Pipeline status
./crawl.sh stage3-stats              # Stage 3 canonical entities
./crawl.sh stage4-stats              # Stage 4 vector stats
```

### Search and Explore
```bash
./crawl.sh search --query "street food" --city Bangkok
./crawl.sh show-entity canonical_place_001
```

### Reset Commands (Careful!)
```bash
./crawl.sh reset-stage2              # Delete Stage 2 only
./crawl.sh reset-stage3              # Delete Stage 3 only
./crawl.sh reset-stage4              # Delete Stage 4 only
./crawl.sh reset-all-stages          # ⚠️ Delete all stages (keeps Stage 1)
```

---

## What You've Accomplished

✅ Crawled 2 YouTube travel videos
✅ Extracted 128 raw entities
✅ Deduplicated to 62 canonical entities
✅ Generated 175 vector embeddings
✅ Created a personalized 3-day itinerary

**Total cost:** ~$0.03-0.05 for entire pipeline

---

## Next Steps

### Scale Up Your Data
```bash
# Crawl from channels
./crawl.sh youtube --channel UCJc4VuL2ynZhS1tn7ZqbLEg --limit 50

# Process in bulk
./crawl.sh process-stage2 --limit 50
./crawl.sh process-stage3
./crawl.sh process-stage4 --embedding-types all
```

### Advanced Queries
```bash
# Family travel
./crawl.sh generate-itinerary -q "5 days Tokyo family mid-range culture"

# Adventure focus
./crawl.sh generate-itinerary -q "7 days Phuket couple adventure diving"
```

### Explore the Codebase
- **Architecture**: [system-architecture.md](../02-architecture/system-architecture.md)
- **Pipeline Details**: [pipeline-overview.md](../02-architecture/pipeline-overview.md)
- **Stage Deep Dives**: [stage1-crawling.md](../03-pipeline-stages/stage1-crawling.md), [stage2-extraction.md](../03-pipeline-stages/stage2-extraction.md), etc.

---

## Troubleshooting

**Issue:** Stage 1 fails with "YouTube API quota exceeded"
- **Solution:** Wait 24 hours for quota reset or use different API key

**Issue:** Stage 2 extraction is slow
- **Solution:** Switch to faster LLM provider (Gemini → DeepSeek → OpenAI)

**Issue:** No itinerary generated (Stage 5)
- **Solution:** Ensure Stage 4 has indexed entities: `./crawl.sh stage4-stats`

**More help:** [troubleshooting.md](../06-operations/troubleshooting.md)

---

**Quickstart complete!** You've successfully run the entire TravelAI pipeline. Next: [Project Structure](project-structure.md)
