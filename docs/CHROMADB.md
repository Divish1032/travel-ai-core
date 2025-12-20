# ChromaDB Vector Database Configuration

**TravelAI Stage 4: Vector Storage & Semantic Search**

This document describes the ChromaDB vector database implementation for TravelAI's Stage 4 pipeline. ChromaDB stores embeddings for semantic search, entity matching, and personalized travel recommendations.

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration](#configuration)
3. [Collection Architecture](#collection-architecture)
4. [Metadata Schemas](#metadata-schemas)
5. [Embedding Model](#embedding-model)
6. [Usage Examples](#usage-examples)
7. [Data Management](#data-management)
8. [Performance & Scaling](#performance--scaling)

---

## Overview

### What is ChromaDB?

[ChromaDB](https://www.trychroma.com/) is an open-source vector database optimized for AI applications. It provides:

- **Vector storage** with efficient similarity search
- **Metadata filtering** for precise query targeting
- **Persistent storage** (local disk or cloud deployment)
- **Cosine similarity search** for semantic matching
- **FREE** for local development with unlimited vectors

### Why ChromaDB for TravelAI?

**Stage 4 Requirements:**
- Store embeddings for 5,000+ canonical travel entities
- Support 3 different embedding strategies (entity, profile-consensus, experience)
- Enable fast semantic search (<100ms for queries)
- Filter by location, traveler profile, cost tier, themes
- Scale to 100,000+ entities without performance degradation

**ChromaDB Advantages:**
- Fully managed Chroma Cloud service
- Metadata filtering without external tools
- Simple Python API
- Auto-scaling and high availability
- No infrastructure to maintain

---

## Configuration

### Chroma Cloud Setup

TravelAI uses **Chroma Cloud** (www.trychroma.com) - the official managed ChromaDB service.

**Benefits:**
- **Fully managed**: No infrastructure to maintain
- **Auto-scaling**: Handles load automatically
- **High availability**: Built-in redundancy and backups
- **Team collaboration**: Shared access with API keys
- **Global CDN**: Low latency worldwide

### Environment Variables

Configuration is managed through `.env` file:

```bash
# ChromaDB Configuration (Stage 4)
# Chroma Cloud (www.trychroma.com) - managed ChromaDB service
CHROMADB_TENANT=your-tenant-id        # From Chroma Cloud dashboard
CHROMADB_DATABASE=default_database    # Your database name
CHROMADB_API_KEY=your-api-key         # From Chroma Cloud dashboard

# Embedding Model Configuration
EMBEDDING_MODEL=gte-large  # Alibaba-NLP/gte-large-en-v1.5
```

### Setup Steps

```bash
# 1. Sign up at www.trychroma.com
#    - Create account
#    - Create a database
#    - Get your tenant ID and API key from dashboard

# 2. Configure .env with your Chroma Cloud credentials
CHROMADB_TENANT=your-tenant-id
CHROMADB_DATABASE=default_database
CHROMADB_API_KEY=your-api-key

# 3. Run Stage 4 (will sync to Chroma Cloud)
./crawl.sh process-stage4 --embedding-types all
```

---

## Collection Architecture

### Three-Collection Strategy

TravelAI uses **3 separate collections** for different embedding granularities:

| Collection | Granularity | Use Case | Example |
|------------|-------------|----------|---------|
| **entities** | Entity-level (Type 1) | General search, entity discovery | "restaurants in Bangkok" |
| **profile_consensus** | Profile-specific (Type 2) | Personalized search | "restaurants for couples on budget" |
| **experiences** | Individual experiences (Type 3) | Detailed exploration, provenance | "what solo travelers said about X" |

### Why 3 Collections?

**1. Entities Collection (General Search)**
- Aggregates all experiences into one embedding per entity
- Fast search across all entities
- Good for: "Find all attractions in Phuket"

**2. Profile Consensus Collection (Personalized Search)**
- One embedding per (entity, traveler_profile) combination
- Captures profile-specific perspectives
- Good for: "Find budget hotels recommended by solo travelers"

**3. Experiences Collection (Detailed Exploration)**
- One embedding per individual traveler's experience
- Full provenance to source video
- Good for: "Show me what specific travelers said about this place"

### Collection Statistics

After processing entities:

```bash
./crawl.sh stage4-stats

# Example output:
Collections:
  entities                      : 1,234 vectors   # 1 per unique entity
  profile_consensus            : 3,567 vectors   # 1 per entity-profile combo
  experiences                  : 8,921 vectors   # 1 per individual experience

Total vectors: 13,722
```

**Storage Efficiency:**
- Entities: ~6MB (1,234 × 5KB)
- Profile Consensus: ~18MB (3,567 × 5KB)
- Experiences: ~45MB (8,921 × 5KB)
- **Total: ~69MB** for 1,234 canonical entities

---

## Metadata Schemas

Each collection has a specific metadata schema optimized for filtering and search.

### 1. Entities Collection Schema

**Purpose:** Entity-level embeddings with consensus data

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `entity_id` | string | Unique entity ID | `ATT_001` |
| `entity_type` | string | Type of entity | `restaurant`, `hotel`, `attraction` |
| `canonical_name` | string | Official entity name | `Grand Palace` |
| `city` | string | City location | `Bangkok` |
| `country` | string | Country location | `Thailand` |
| `normalized_location` | string | Full location | `Bangkok, Thailand` |
| `latitude` | float | Latitude coordinate | 13.7563 |
| `longitude` | float | Longitude coordinate | 100.5018 |
| `mention_count` | int | Total mentions across videos | 42 |
| `avg_rating` | float | Average rating (0-5) | 4.8 |
| `sentiment_score` | float | Sentiment score (-1 to 1) | 0.85 |
| `cost_tier` | string | Cost category | `free`, `budget`, `mid-range`, `luxury` |
| `themes` | string | Comma-separated themes | `cultural,historical,photography` |
| `created_at` | string | ISO timestamp | `2025-12-14T10:30:00Z` |

**Embedding Text Format:**
```
Grand Palace, Bangkok, Thailand (attraction)
Stunning royal palace complex with intricate Thai architecture. Must-visit cultural landmark.
Mentioned by 42 travelers | Rating: 4.8/5 | Sentiment: positive
Themes: cultural, historical, photography
Cost: Mid-range (200 THB entrance)
```

**Filter Examples:**
```python
# Find restaurants in Bangkok
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={"entity_type": "restaurant", "city": "Bangkok"}
)

# Find budget attractions
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={"entity_type": "attraction", "cost_tier": "budget"}
)

# Find highly-rated entities (rating >= 4.5)
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={"avg_rating": {"$gte": 4.5}}
)
```

---

### 2. Profile Consensus Collection Schema

**Purpose:** Profile-specific embeddings for personalized search

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `entity_id` | string | Unique entity ID | `RES_042` |
| `entity_type` | string | Type of entity | `restaurant` |
| `canonical_name` | string | Official entity name | `Som Tam Nua` |
| `city` | string | City location | `Bangkok` |
| `country` | string | Country location | `Thailand` |
| `normalized_location` | string | Full location | `Bangkok, Thailand` |
| `latitude` | float | Latitude coordinate | 13.7440 |
| `longitude` | float | Longitude coordinate | 100.5410 |
| `profile_key` | string | Profile identifier | `solo_26-35_budget` |
| `traveler_type` | string | Type of traveler | `solo`, `couple`, `family` |
| `age_range` | string | Age demographic | `18-25`, `26-35`, `36-50`, `50+` |
| `budget_tier` | string | Budget category | `budget`, `mid-range`, `luxury` |
| `profile_mention_count` | int | Mentions by this profile | 12 |
| `profile_avg_rating` | float | Profile-specific rating | 4.9 |
| `profile_sentiment_score` | float | Profile-specific sentiment | 0.92 |
| `cost_tier` | string | Cost category | `budget` |
| `themes` | string | Themes | `foodie,authentic,local` |
| `created_at` | string | ISO timestamp | `2025-12-14T10:30:00Z` |

**Embedding Text Format:**
```
Som Tam Nua, Bangkok, Thailand (restaurant)
From perspective of: Solo travelers, 26-35 years old, Budget tier

Authentic Thai street food with amazing papaya salad. Super cheap and delicious.
Mentioned by 12 solo budget travelers | Rating: 4.9/5 | Sentiment: very positive
Themes: foodie, authentic, local
Cost: Budget (60-100 THB per meal)
```

**Filter Examples:**
```python
# Find restaurants for solo budget travelers in Bangkok
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={
        "entity_type": "restaurant",
        "city": "Bangkok",
        "traveler_type": "solo",
        "budget_tier": "budget"
    }
)

# Find hotels recommended by couples (mid-range budget)
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={
        "entity_type": "hotel",
        "traveler_type": "couple",
        "budget_tier": "mid-range"
    }
)
```

---

### 3. Experiences Collection Schema

**Purpose:** Individual traveler experiences with full provenance

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `entity_id` | string | Unique entity ID | `ACT_099` |
| `entity_type` | string | Type of entity | `activity` |
| `canonical_name` | string | Official entity name | `Phi Phi Island Tour` |
| `city` | string | City location | `Phuket` |
| `country` | string | Country location | `Thailand` |
| `normalized_location` | string | Full location | `Phuket, Thailand` |
| `latitude` | float | Latitude coordinate | 7.8804 |
| `longitude` | float | Longitude coordinate | 98.3923 |
| `experience_index` | int | Experience number | 0, 1, 2, ... |
| `source_video_id` | string | Source video ID | `youtube_abc123` |
| `traveler_type` | string | Traveler type | `couple` |
| `age_range` | string | Age range | `26-35` |
| `budget_tier` | string | Budget tier | `mid-range` |
| `travel_style` | string | Comma-separated styles | `adventure,photography` |
| `sentiment` | string | Experience sentiment | `positive`, `negative`, `neutral`, `mixed` |
| `confidence_score` | float | Confidence (0-1) | 0.87 |
| `cost_mentioned` | string | Cost details | `1,800 THB per person` |
| `cost_tier` | string | Cost category | `mid-range` |
| `themes` | string | Themes | `snorkeling,beach,island-hopping` |
| `language` | string | Video language | `en` |
| `timestamp_start` | float | Video timestamp (seconds) | 145.2 |
| `created_at` | string | ISO timestamp | `2025-12-14T10:30:00Z` |

**Embedding Text Format:**
```
Phi Phi Island Tour, Phuket, Thailand (activity)
Traveler: Couple, 26-35 years old, Mid-range budget, Adventure & Photography style

"Amazing day trip! The snorkeling was incredible with crystal clear water.
Maya Bay is stunning but crowded. Worth every baht. Highly recommend booking
early morning tour to avoid crowds."

Sentiment: positive | Cost: 1,800 THB per person
Themes: snorkeling, beach, island-hopping
Source: youtube_abc123 @ 145.2s
```

**Filter Examples:**
```python
# Find experiences from specific video
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={"source_video_id": "youtube_abc123"}
)

# Find positive experiences about activities in Phuket
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={
        "entity_type": "activity",
        "city": "Phuket",
        "sentiment": "positive"
    }
)

# Find budget-friendly experiences from solo travelers
collection.query(
    query_embeddings=[embedding],
    n_results=10,
    where={
        "traveler_type": "solo",
        "cost_tier": "budget"
    }
)
```

---

## Embedding Model

### Model Selection: Alibaba-NLP/gte-large-en-v1.5

**Why this model?**

| Model | Dimensions | MTEB Score | Speed | Cost |
|-------|-----------|------------|-------|------|
| **gte-large (selected)** | 1024 | 65.39 | Fast | FREE |
| OpenAI text-embedding-3-small | 1536 | 62.28 | API latency | $0.02/1M tokens |
| OpenAI text-embedding-3-large | 3072 | 64.59 | API latency | $0.13/1M tokens |

**Advantages:**
- **FREE** (runs locally, no API costs)
- **Better quality** than OpenAI's small model
- **Fast inference** (~50ms per embedding on CPU)
- **Open source** (Hugging Face)
- **1024 dimensions** (good balance of quality vs size)

**Performance Benchmarks:**

```bash
# Embedding generation speed
Entity-level embeddings: ~20 entities/second (CPU)
Profile embeddings: ~15 embeddings/second (CPU)
Experience embeddings: ~10 embeddings/second (CPU)

# Search performance
Query latency: <100ms for 10,000 vectors (local)
Throughput: 100+ queries/second

# Storage efficiency
1,024 dimensions × 4 bytes (float32) = 4KB per vector
+ metadata (~1KB) = ~5KB total per entity
```

### Embedding Model Configuration

```bash
# In .env
EMBEDDING_MODEL=gte-large

# Model auto-downloaded from Hugging Face on first use
# Cached in: ~/.cache/huggingface/hub/
# Size: ~1.5GB (one-time download)
```

**Alternative Models** (if needed):

```bash
# Smaller model (faster, slightly lower quality)
EMBEDDING_MODEL=gte-small  # 384 dimensions

# Larger model (slower, higher quality)
EMBEDDING_MODEL=gte-large-zh  # Multilingual support
```

---

## Usage Examples

### Initialize ChromaDB

```python
from src.vectordb import ChromaDBClient

# Auto-configure from .env
client = ChromaDBClient.initialize_from_env()

# Or manual initialization
client = ChromaDBClient()
client.initialize_local(persist_directory="./chroma_data")

# Check stats
client.print_stats()
```

### Process Stage 4

```bash
# Index all canonical entities (all 3 embedding types)
./crawl.sh process-stage4 --embedding-types all

# Index specific embedding types only
./crawl.sh process-stage4 --embedding-types entity
./crawl.sh process-stage4 --embedding-types profile,experience

# Test with limited entities
./crawl.sh process-stage4 --embedding-types all --limit 10
```

### Search Examples

```python
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient

# Initialize
chroma_client = ChromaDBClient.initialize_from_env()
embedding_client = EmbeddingClient()

# Generate query embedding
query = "best street food in Bangkok"
query_embedding = embedding_client.generate_embedding(query)

# Search entities collection
results = chroma_client.entities_collection.query(
    query_embeddings=[query_embedding],
    n_results=10,
    where={"city": "Bangkok", "entity_type": "restaurant"}
)

# Print results
for i, (id, distance, metadata) in enumerate(zip(
    results['ids'][0],
    results['distances'][0],
    results['metadatas'][0]
)):
    print(f"{i+1}. {metadata['canonical_name']} (similarity: {1-distance:.3f})")
```

### Semantic Search CLI

```bash
# Search for entities
./crawl.sh search --query "romantic restaurants with sunset view" \
    --city Bangkok \
    --entity-type restaurant \
    --top-k 10

# Personalized search
./crawl.sh search --query "adventure activities" \
    --profile solo_budget \
    --city Phuket \
    --top-k 5

# Filter by cost
./crawl.sh search --query "luxury hotels" \
    --cost-tier luxury \
    --top-k 10
```

---

## Data Management

### Backup & Restore

#### Local Mode Backup

```bash
# Backup ChromaDB data
tar -czf chroma_backup_$(date +%Y%m%d).tar.gz chroma_data/

# List backups
ls -lh chroma_backup_*.tar.gz

# Restore from backup
tar -xzf chroma_backup_20251214.tar.gz

# Upload to S3 (recommended)
./crawl.sh backup-vectors --destination s3
```

#### S3 Backup Integration

```bash
# Automatic S3 backup (built-in)
./crawl.sh backup-vectors --destination s3

# Outputs:
# s3://your-bucket/stage4-vectors/backup_YYYYMMDD_HHMMSS/chroma_data.tar.gz

# Restore from S3
./crawl.sh restore-vectors --source s3 --backup-id backup_20251214_103000
```

### Sync to Cloud ChromaDB

```bash
# Deploy local data to cloud ChromaDB server
./crawl.sh sync-to-cloud --source local --destination cloud

# Sync cloud data to local (download)
./crawl.sh sync-to-cloud --source cloud --destination local
```

### Reset Collections

```bash
# Reset Stage 4 (delete all embeddings)
./crawl.sh reset --stage stage_4_vectorize --all

# Confirm deletion
# WARNING: This will delete all vector data!
# Type 'yes' to confirm: yes

# Rebuild embeddings
./crawl.sh process-stage4 --embedding-types all
```

---

## Performance & Scaling

### Chroma Cloud Performance

**Indexing Performance:**
```
Entity embeddings:     ~20 entities/second
Profile embeddings:    ~15 embeddings/second
Experience embeddings: ~10 embeddings/second

1,000 entities (all types): ~5 minutes
10,000 entities:             ~50 minutes
```

**Query Performance:**
- Chroma Cloud automatically handles scaling
- Typical query latency: 50-200ms depending on region
- Built-in load balancing and auto-scaling

**Storage:**
```
1,000 entities:    ~15MB (all 3 collections)
10,000 entities:   ~150MB
100,000 entities:  ~1.5GB
1,000,000+ entities: ~15GB+ (auto-scaling)
```

### Chroma Cloud Advantages

- **Automatic horizontal scaling** - Handles growing vector counts automatically
- **Built-in load balancing** - High throughput for concurrent queries
- **Team collaboration** - Shared database with API keys
- **Global API endpoints** - Low latency worldwide
- **No infrastructure management** - Fully managed service

### Scaling

Chroma Cloud automatically scales to handle any vector count:

| Entities | Vectors | Storage | Performance |
|----------|---------|---------|-------------|
| <10K | <30K | <150MB | Excellent |
| 10K-100K | 30K-300K | 150MB-1.5GB | Excellent |
| 100K-1M | 300K-3M | 1.5GB-15GB | Auto-scaling |
| >1M | >3M | >15GB | Auto-scaling |

---

## Monitoring & Statistics

### Check Vector Database Stats

```bash
# Overall Stage 4 statistics
./crawl.sh stage4-stats

# Detailed breakdown
./crawl.sh stage4-stats --detailed

# Export to JSON
./crawl.sh stage4-stats --json > stage4_report.json
```

### Monitor Stage 4 Progress

```bash
# Real-time monitoring during indexing
./crawl.sh monitor-stage4

# Updates every 10 seconds showing:
# - Entities processed
# - Embeddings generated
# - Current collection counts
# - Estimated time remaining
```

### Collection Statistics

```python
from src.vectordb import ChromaDBClient

client = ChromaDBClient.initialize_from_env()

# Get collection counts
print(f"Entities: {client.entities_collection.count()}")
print(f"Profiles: {client.profile_consensus_collection.count()}")
print(f"Experiences: {client.experiences_collection.count()}")

# Get full stats
stats = client.get_stats()
print(f"Total vectors: {stats['total_vectors']}")
print(f"Mode: {stats['mode']}")
```

---

## Troubleshooting

### ChromaDB Not Initializing

```bash
# Check if chroma_data directory exists
ls -la chroma_data/

# Remove corrupted database
rm -rf chroma_data/

# Reinitialize
./crawl.sh process-stage4 --embedding-types all
```

### Slow Query Performance

```bash
# Check collection sizes
./crawl.sh stage4-stats

# If >1M vectors in local mode, consider:
# 1. Switch to cloud mode with better hardware
# 2. Add metadata filters to narrow search
# 3. Reduce n_results parameter
```

### Out of Memory

```bash
# Reduce batch size during indexing
# Edit cli/process_stage4.py:
# batch_size=100  →  batch_size=50

# Or process in smaller chunks
./crawl.sh process-stage4 --embedding-types entity --limit 1000
./crawl.sh process-stage4 --embedding-types profile --limit 1000
./crawl.sh process-stage4 --embedding-types experience --limit 1000
```

---

## Summary

**ChromaDB Configuration:**
- ✅ Local mode (FREE) for development
- ✅ Cloud mode for production deployment
- ✅ 3 collections for different granularities
- ✅ Comprehensive metadata schemas
- ✅ FREE local embedding model (gte-large)
- ✅ Built-in backup/restore
- ✅ Scales to millions of vectors

**Next Steps:**
1. Configure `.env` with `CHROMADB_MODE=local`
2. Run `./crawl.sh process-stage4 --embedding-types all`
3. Test search with `./crawl.sh search --query "your query"`
4. Monitor with `./crawl.sh stage4-stats`

For detailed commands, see [COMMANDS.md](COMMANDS.md) - Stage 4 section.

For production deployment guide, see [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md).
