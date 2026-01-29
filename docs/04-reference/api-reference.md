# API Reference

TravelAI is primarily a CLI-based pipeline. This document describes the Python API for programmatic usage.

---

## Core APIs

### Stage 1: YouTube Crawling

```python
from src.crawlers.youtube import YouTubeCrawler
from src.storage.s3 import S3Storage

# Initialize
storage = S3Storage()
crawler = YouTubeCrawler(storage)

# Crawl single video
result = crawler.crawl("https://youtube.com/watch?v=abc123")
print(f"Crawled: {result.title}")

# Crawl multiple videos
urls = ["https://youtube.com/watch?v=abc123", "..."]
results = crawler.crawl_batch(urls, limit=10)
```

---

### Stage 2: Entity Extraction

```python
from src.processors.stage2_extractor import extract_entities_from_video
from src.storage.s3 import S3Storage

storage = S3Storage()

# Extract from single video
result = extract_entities_from_video(
    video_id="youtube_abc123",
    storage=storage,
    use_semantic_chunking=True,
    use_fuzzy_deduplication=True
)

print(f"Extracted {len(result.entities)} entities")
print(f"Traveler profile: {result.traveler_profile}")
```

---

### Stage 3: Canonicalization

```python
from src.processors.stage3_enrichment import process_stage3
from src.storage.s3 import S3Storage

storage = S3Storage()

# Process all Stage 2 entities
result = process_stage3(storage)

print(f"Canonical entities: {result['canonical_count']}")
print(f"Deduplication rate: {result['dedup_rate']:.1%}")
```

---

### Stage 4: Vectorization

```python
from src.processors.vector_indexer import index_entity_embeddings
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.storage.stage3_storage import Stage3Storage

# Initialize clients
chromadb = ChromaDBClient.initialize_from_env()
embedding_client = EmbeddingClient()
stage3 = Stage3Storage()

# Load entities
entities = stage3.load_all_canonical_entities()

# Index embeddings
stats = index_entity_embeddings(
    entities=entities,
    chromadb=chromadb,
    embedding_client=embedding_client,
    embedding_types=["full_context", "experience", "logistics"]
)

print(f"Indexed {stats['total_indexed']} vectors")
```

---

### Stage 5: RAG Itinerary Generation

```python
from src.rag.pipeline import RAGPipeline

# Initialize pipeline
pipeline = RAGPipeline()

# Generate itinerary
result = pipeline.generate(
    query="5 days Bangkok solo budget street food",
    output_format="markdown"
)

print(result['formatted_output'])
print(f"Cost: ${result['metadata']['total_cost']:.4f}")
print(f"Vibe match: {result['vibe_match_score']}/10")
```

---

## Storage APIs

### S3Storage

```python
from src.storage.s3 import S3Storage

storage = S3Storage()

# Upload file
storage.upload_json(
    data={"key": "value"},
    s3_key="stage1_transcripts/youtube_abc123.json"
)

# Download file
data = storage.download_json("stage1_transcripts/youtube_abc123.json")

# List files
files = storage.list_files(prefix="stage2_entities/")
```

### MetadataTracker

```python
from src.utils.metadata_tracker import MetadataTracker
from src.storage.s3 import S3Storage

storage = S3Storage()
tracker = MetadataTracker(storage)

# Update status
tracker.update_status(
    video_id="youtube_abc123",
    stage="stage2_entities",
    status="completed"
)

# Get pending videos
pending = tracker.get_pending_videos(stage="stage2_entities")
```

---

## ChromaDB APIs

### Query Entities

```python
from src.vectordb import ChromaDBClient

chromadb = ChromaDBClient.initialize_from_env()

# Semantic search
results = chromadb.query(
    collection_name="travel_entities",
    query_texts=["best street food Bangkok"],
    n_results=20,
    where={
        "city": "Bangkok",
        "entity_type": "restaurant"
    }
)

# Get entity by ID
entity = chromadb.get(
    collection_name="travel_entities",
    ids=["canonical_place_001_full_context"]
)
```

---

## LLM APIs

### LLM Provider Factory

```python
from src.llm.factory import LLMFactory

# Create LLM client (reads from .env)
llm = LLMFactory.create()

# Generate response
response = llm.generate(
    prompt="Describe Bangkok in 50 words",
    max_tokens=100,
    temperature=0.7
)

print(response.text)
print(f"Cost: ${response.cost:.4f}")
```

### Specific Providers

```python
from src.llm.gemini import GeminiProvider
from src.llm.openai import OpenAIProvider

# Gemini
gemini = GeminiProvider(api_key="...", model="gemini-2.5-flash-lite")
response = gemini.generate(prompt="...")

# OpenAI
openai = OpenAIProvider(api_key="...")
response = openai.generate(prompt="...")
```

---

## Cost Tracking

### RAG Cost Tracker

```python
from src.utils.rag_cost_tracker import RAGCostTracker

tracker = RAGCostTracker(budget_limit=0.10)

# Track phase costs
tracker.track_phase(
    phase='intent_parsing',
    cost=0.0001,
    input_tokens=100,
    output_tokens=50
)

# Print summary
tracker.print_summary()

# Save report
tracker.save_report("stage5-costs/")
```

---

## Embedding APIs

### Generate Embeddings

```python
from src.utils.embedding_client import EmbeddingClient

client = EmbeddingClient()

# Single text
embedding = client.encode("Bangkok is an amazing city")
# Returns: numpy array (768,)

# Batch texts
embeddings = client.encode_batch([
    "Bangkok street food",
    "Phuket beaches",
    "Chiang Mai temples"
])
# Returns: numpy array (3, 768)
```

---

## Utility APIs

### Logging

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

logger.info("Processing started")
logger.error("Error occurred", exc_info=True)
```

### Configuration

```python
from src.utils.config import config

print(config.AWS_REGION)
print(config.LLM_PROVIDER)
print(config.S3_BUCKET_NAME)
```

---

## FastAPI Endpoints (Future)

**Note:** REST API is planned but not yet implemented in v1.

**Planned Endpoints:**

```
POST /api/v1/itinerary/generate
GET  /api/v1/entities/search
GET  /api/v1/pipeline/status
GET  /api/v1/videos/{video_id}
```

---

## References

- **CLI Commands:** [cli-commands.md](cli-commands.md)
- **Data Schemas:** [data-schemas.md](data-schemas.md)
- **Configuration:** [configuration.md](configuration.md)
