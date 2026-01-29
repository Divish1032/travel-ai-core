# Stage 4: Vectorization

Stage 4 generates vector embeddings from canonical entities and indexes them in ChromaDB with enhanced metadata for semantic search.

**Implementation:** [`src/processors/embedding_generator.py`](../../src/processors/embedding_generator.py), [`src/processors/vector_indexer.py`](../../src/processors/vector_indexer.py)

---

## Overview

### Purpose
Transform canonical entities into searchable vector embeddings with rich metadata for semantic retrieval.

### Key Features
- **FREE local embeddings** using gte-large model
- **3 embedding types** for different query scenarios
- **Geohash geospatial search** for location filtering
- **Enhanced metadata** with temporal and logistics filters
- **ChromaDB Cloud hosting** for scalable vector storage

### Inputs
- Canonical entities from Stage 3
- Temporal and logistics metadata

### Outputs
- Vector embeddings (768 dimensions)
- Enhanced metadata per embedding
- ChromaDB `travel_entities` collection

---

## Embedding Model: gte-large

**Model:** `thenlper/gte-large` (General Text Embeddings)

**Specifications:**
- **Dimensions:** 768
- **Max tokens:** 512
- **Language:** Multilingual (optimized for English)
- **Cost:** **FREE** (runs locally)
- **Performance:** SOTA on MTEB benchmark

**Why gte-large?**
1. **No API costs** - Runs locally
2. **High quality** - Better than OpenAI ada-002 on many benchmarks
3. **Fast** - ~50ms per embedding on CPU
4. **Open source** - No vendor lock-in

**Installation:**
```bash
pip install sentence-transformers
```

**Usage:**
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('thenlper/gte-large')
embedding = model.encode("Bangkok is an amazing city")
# Returns: array of 768 floats
```

---

## 3 Embedding Types

TravelAI generates **3 embedding types** per entity for different query scenarios:

### Type 1: Full Context (Entity-Level)

**Purpose:** General entity search

**Text Content:**
- Entity name, type, location
- Overall description and characteristics
- Consensus ratings and mentions
- Temporal information (best months, time of day)
- Logistics information (hours, booking, fees)
- Practical tips
- Common experiences

**Example Text:**
```
Grand Palace is an attraction located in Bangkok, Thailand. This attraction has been mentioned 8 times across different travel videos with an average rating of 4.8/5.0. Travelers describe it as: breathtaking architecture, must-visit landmark, crowded but worth it.

WHEN TO VISIT: Best months are November to February (cool season). Best time is early morning (8:30-10:00am) to avoid crowds. Typical visit duration is 2-3 hours. Avoid visiting in April-May (hot season).

HOW TO GET THERE: Located in Phra Nakhon district. Accessible by BTS + walk or taxi. No advance booking required.

PRACTICAL TIPS: Entry fee 500 THB (~$15). Strict dress code - cover shoulders and knees. Audio guide available for 200 THB. Arrive early to avoid tour groups.
```

**Metadata:**
```json
{
  "entity_id": "canonical_place_001",
  "entity_name": "Grand Palace",
  "entity_type": "attraction",
  "embedding_type": "full_context",
  "city": "Bangkok",
  "country": "Thailand",
  "geohash": "w4rqjg",
  "lat": 13.7498,
  "lon": 100.4914,
  "popularity_score": 89,
  "data_freshness": 92,
  "best_months": [11, 12, 1, 2],
  "booking_required": false,
  "has_entry_fee": true
}
```

---

### Type 2: Experience Focus

**Purpose:** Query for subjective experiences and vibes

**Text Content:**
- **Only subjective experiences** (no facts)
- Traveler emotions and reactions
- Vibe indicators (touristiness, pace, food focus)
- Sentiment and atmosphere descriptions
- Personal recommendations

**Example Text:**
```
Grand Palace in Bangkok. Amazing experience, absolutely breathtaking. The intricate details are mind-blowing. Very crowded with tourists but definitely worth it. Can feel overwhelming due to the heat and crowds. Peaceful early in the morning. Stunning photo opportunities everywhere. Cultural experience like no other.

Vibe: High touristiness (9/10), slow pace, cultural immersion. Popular with couples and families. Best for those who appreciate history and architecture.
```

**Use Case:** "Find experiences that feel authentic and not too touristy"

---

### Type 3: Logistics Focus

**Purpose:** Query for practical information

**Text Content:**
- **Only logistics** (no experiences)
- Opening hours and closures
- Booking requirements
- Entry fees and costs
- Transportation and accessibility
- Practical tips and requirements

**Example Text:**
```
Grand Palace, Bangkok, Thailand

HOURS: Open daily 8:30am-3:30pm (last entry 3:00pm). No weekly closures.

BOOKING: No advance booking required. Buy tickets on-site.

COST: Entry fee 500 THB (~$15 USD). Audio guide 200 THB extra. Cash and cards accepted.

ACCESS: Located in Phra Nakhon district. Nearest BTS: Saphan Taksin (then taxi/boat). Taxi from city center ~100-150 THB.

REQUIREMENTS: Strict dress code - shoulders and knees must be covered. Free sarongs available if needed. Bags subject to security check.

TIPS: Arrive before 9am to avoid crowds. Bring water. Allow 2-3 hours minimum.
```

**Use Case:** "What are the opening hours and how do I get there?"

---

## Enhanced Metadata Schema

**ChromaDB Metadata (per embedding):**

```typescript
{
  // Identity
  entity_id: string
  entity_name: string
  entity_type: "destination" | "restaurant" | "hotel" | "activity" | "attraction"
  embedding_type: "full_context" | "experience" | "logistics"

  // Location
  city: string
  country: string
  geohash: string              // Precision 7 (~150m)
  geohash_region: string       // Precision 4 (~20km)
  lat: number
  lon: number

  // Temporal Filters
  best_months: number[]        // [11, 12, 1, 2] = Nov-Feb
  avoid_months: number[]       // [4, 5] = Apr-May
  best_time_of_day: string     // "morning" | "afternoon" | "evening"
  visit_duration_hours: number // 2.5

  // Logistics Filters
  booking_required: boolean
  advance_days_needed: number  // 0, 7, 14, 30
  has_entry_fee: boolean
  wheelchair_accessible: boolean
  transport_modes: string[]    // ["bts", "taxi", "walk"]

  // Quality Metrics
  popularity_score: number     // 0-100
  data_freshness: number       // 0-100
  mention_count: number
  avg_rating: number           // 1.0-5.0

  // VIBE Dimensions (for filtering)
  vibe_touristiness: number    // 0-10
  vibe_adventure: number       // 0-10
  vibe_budget: number          // 1-10
  vibe_pace: string            // "slow" | "moderate" | "fast"
  vibe_food_focus: number      // 0-10

  // Provenance
  source_videos: string        // JSON array as string
  s3_key: string               // Reference to Stage 3 data
}
```

**Metadata Size Limit:** 4KB per embedding (ChromaDB Cloud limit)

---

## Geohash Geospatial Search

### What is Geohash?

**Geohash** encodes lat/lon coordinates into a short string where similar locations share common prefixes.

**Example:**
```
Grand Palace:     lat=13.7498, lon=100.4914 → geohash="w4rqjg6"
Wat Pho (nearby): lat=13.7465, lon=100.4927 → geohash="w4rqjg5"
                                                        ^^^^^^ (same prefix = nearby!)

Phuket:           lat=7.8804, lon=98.3923  → geohash="w3qb2x4"
                                                        ^^ (different = far away)
```

### Geohash Precision Levels

| Precision | Area Size | Use Case |
|-----------|-----------|----------|
| 4 | ~20km × 20km | Regional search (all of Bangkok) |
| 5 | ~5km × 5km | District search (Sukhumvit area) |
| 6 | ~1.2km × 0.6km | Neighborhood search |
| **7** | ~150m × 150m | **Street-level search (default)** |

### Geospatial Filtering

**Query Examples:**

1. **Find nearby entities:**
```python
# Find all entities within ~150m of Grand Palace
results = chromadb.query(
    where={"geohash": {"$eq": "w4rqjg6"}}  # Exact geohash match
)
```

2. **Find in same district:**
```python
# Find all entities in same district as Grand Palace
results = chromadb.query(
    where={"geohash": {"$gte": "w4rqjg", "$lt": "w4rqjh"}}  # Prefix match
)
```

3. **Find in Bangkok region:**
```python
# Find all Bangkok entities
results = chromadb.query(
    where={"geohash_region": "w4r"}  # All Bangkok starts with w4r
)
```

**Benefits:**
- **Fast filtering** before vector search
- **Location-aware retrieval**
- **Nearby suggestions** without complex geo queries

---

## Processing Pipeline

### 1. Load Canonical Entities

Load enriched entities from Stage 3:
```python
from src.storage.stage3_storage import Stage3Storage

stage3 = Stage3Storage()
entities = stage3.load_all_canonical_entities()
# Returns: List of 62 canonical entities
```

---

### 2. Generate Embedding Text

**Function:** `generate_entity_embedding_text()`

Converts structured entity data into rich descriptive text:
- 400-600 words per entity (full_context)
- 200-300 words per entity (experience)
- 150-250 words per entity (logistics)

**Example:**
```python
from src.processors.embedding_generator import generate_entity_embedding_text

text = generate_entity_embedding_text(entity)
print(f"Generated {len(text.split())} words")
# Output: Generated 487 words
```

---

### 3. Generate Embeddings

**Function:** `EmbeddingClient.encode()`

Uses gte-large to generate 768-dimensional vectors:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('thenlper/gte-large')
embedding = model.encode(text)
# Returns: numpy array of shape (768,)
```

**Batch Processing:**
- Process 32 entities at once for efficiency
- ~1-2 seconds for 32 embeddings on CPU
- ~0.5 seconds on GPU (if available)

---

### 4. Prepare Metadata

**Function:** `prepare_entity_metadata()`

Extracts and flattens metadata for ChromaDB:
- Converts arrays to JSON strings (ChromaDB requirement)
- Extracts temporal/logistics fields
- Generates geohash from coordinates
- Validates metadata size (<4KB)

---

### 5. Index in ChromaDB

**Function:** `index_entity_embeddings()`

Uploads to ChromaDB Chroma Cloud:
```python
chromadb.add(
    collection_name="travel_entities",
    embeddings=[embedding1, embedding2, ...],
    metadatas=[metadata1, metadata2, ...],
    ids=["canonical_place_001_full", "canonical_place_001_exp", ...]
)
```

**Collection Name:** `travel_entities`
**Batch Size:** 100 embeddings per batch

---

## CLI Usage

### Process Stage 4

```bash
# Generate and index all embedding types
./crawl.sh process-stage4 --embedding-types all

# Generate specific embedding types
./crawl.sh process-stage4 --embedding-types full_context
./crawl.sh process-stage4 --embedding-types experience,logistics

# Limit entities (for testing)
./crawl.sh process-stage4 --limit 10
```

### View Stats

```bash
# Check Stage 4 statistics
./crawl.sh stage4-stats

# Monitor progress
./crawl.sh monitor-stage4
```

### Reset Stage 4

```bash
# Reset and reindex (careful!)
./crawl.sh reset-stage4
```

---

## Performance & Costs

### Processing Time

**Per Entity:**
- Text generation: ~50ms
- Embedding generation: ~150ms (3 types × 50ms)
- Metadata preparation: ~10ms
- ChromaDB upload: ~20ms
- **Total:** ~230ms per entity

**For 62 Entities:**
- Total time: ~15 seconds
- Batch processing optimized

**For 1,000 Entities:**
- Total time: ~4 minutes

### Costs

**Embedding Generation:** **FREE** (local gte-large)
**ChromaDB Storage:**
- Free tier: 1M vectors
- Paid: $0.0004 per 1K vectors/month
- **62 entities × 3 types = 186 vectors = $0.00007/month**

**Total Stage 4 Cost:** **FREE**

---

## ChromaDB Cloud Setup

### Create Collection

```python
from src.vectordb.chroma_client import ChromaClient

chroma = ChromaClient.initialize_from_env()
chroma.create_collection(
    name="travel_entities",
    embedding_dimension=768,
    metadata={"description": "TravelAI entity embeddings with enhanced metadata"}
)
```

### Query Collection

```python
# Semantic search
results = chroma.query(
    collection_name="travel_entities",
    query_texts=["find authentic street food in Bangkok"],
    n_results=20,
    where={
        "city": "Bangkok",
        "entity_type": "restaurant",
        "booking_required": False
    }
)
```

**See:** [chromadb.md](../05-infrastructure/chromadb.md) for full setup guide

---

## Error Handling

### Common Errors

**1. ChromaDB Connection Failed**
```
ConnectionError: Could not connect to ChromaDB
```
**Solution:**
- Verify `CHROMA_API_KEY` and `CHROMA_SERVER_URL` in `.env`
- Check Chroma Cloud dashboard: https://app.trychroma.com/

**2. Metadata Too Large**
```
MetadataError: Metadata exceeds 4KB limit
```
**Solution:**
- Automatic truncation of long fields
- Logged with warning for review

**3. Embedding Model Not Found**
```
ModelNotFoundError: gte-large not downloaded
```
**Solution:**
- First run downloads model automatically (~500MB)
- Ensure sufficient disk space

---

## Configuration

### Environment Variables

```bash
# ChromaDB Configuration
CHROMA_MODE=cloud                          # Options: local, cloud
CHROMA_API_KEY=your_chroma_api_key_here
CHROMA_SERVER_URL=https://api.trychroma.com

# Embedding Configuration
EMBEDDING_MODEL=gte-large                  # Local model
EMBEDDING_BATCH_SIZE=32                    # Batch size for efficiency

# Geohash Configuration
GEOHASH_PRECISION=7                        # Street-level precision
GEOHASH_REGION_PRECISION=4                 # Regional precision
```

---

## Quality Assurance

### Verify Embeddings

```bash
# Check embedding statistics
./crawl.sh stage4-stats

# Test search
./crawl.sh search-test --query "street food Bangkok"

# Verify geohash distribution
./crawl.sh stage4-stats --geohash
```

### Expected Output

```
Stage 4 Statistics:
✅ Total entities: 62
✅ Embeddings generated: 186 (62 × 3 types)
✅ Average metadata size: 2.1 KB (< 4KB limit)
✅ Geohash coverage: 100%

Geohash Distribution:
  w4r (Bangkok): 48 entities
  w3q (Phuket): 8 entities
  w4s (Pattaya): 6 entities
```

---

## Best Practices

### 1. Generate All 3 Embedding Types
- Full context: General queries
- Experience: Vibe-based queries
- Logistics: Practical queries

### 2. Verify Geohash Coverage
- Check all entities have coordinates
- Verify geohash prefixes make sense

### 3. Monitor Metadata Size
- Keep under 4KB per embedding
- Truncate long text fields if needed

### 4. Use Chroma Cloud
- More reliable than local ChromaDB
- Better performance for production
- Automatic backups

---

## Output Schema

**ChromaDB Collection:** `travel_entities`

```typescript
{
  id: string                    // "canonical_place_001_full_context"
  embedding: number[]           // 768-dimensional vector
  metadata: {
    // See "Enhanced Metadata Schema" section above
  }
}
```

**Total Vectors:** 62 entities × ~2.8 avg (some lack experience/logistics) = 175 vectors

---

## Next Stage

Once Stage 4 completes:
- ✅ Embeddings indexed in ChromaDB
- ✅ Enhanced metadata for filtering
- ✅ Geohash for geospatial search
- ➡️ **Ready for Stage 5:** [RAG Itinerary Generation](stage5-rag.md)

---

## References

- **Implementation:** [`src/processors/embedding_generator.py`](../../src/processors/embedding_generator.py), [`src/processors/vector_indexer.py`](../../src/processors/vector_indexer.py)
- **ChromaDB Client:** [`src/vectordb/chroma_client.py`](../../src/vectordb/chroma_client.py)
- **CLI Command:** [`cli/process_stage4.py`](../../cli/process_stage4.py)
- **ChromaDB Setup:** [chromadb.md](../05-infrastructure/chromadb.md)
- **gte-large Model:** https://huggingface.co/thenlper/gte-large

---

**Stage 4 complete!** Next: [Stage 5: RAG Itinerary Generation](stage5-rag.md)
