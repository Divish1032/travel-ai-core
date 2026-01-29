# Project Structure

This document explains how the TravelAI codebase is organized to help you navigate and understand the project.

---

## Directory Overview

```
TravelAI/
├── cli/                    # Command-line interface scripts
├── src/                    # Core pipeline implementation
├── docs/                   # Documentation (you are here)
├── tests/                  # Test suite
├── data/                   # Local data cache
├── logs/                   # Pipeline execution logs
├── samples/                # Example files and test data
├── notebooks/              # Jupyter notebooks for analysis
├── stage4-vectors/         # Local vector storage cache
├── .env                    # Environment variables (not in git)
├── .env.example            # Environment template
├── requirements.txt        # Python dependencies
├── setup.sh                # Automated setup script
└── crawl.sh                # Main CLI entry point

Note: webapp/ and dashboard/ are separate projects with their own documentation
```

---

## CLI Directory (`cli/`)

Command-line interface implementations. Each file corresponds to a `./crawl.sh` command.

### Pipeline Commands
```
cli/
├── crawl.py                # Stage 1: YouTube crawling
├── process_stage2.py       # Stage 2: Entity extraction
├── process_stage3.py       # Stage 3: Deduplication & enrichment
├── process_stage4.py       # Stage 4: Vector embeddings
└── generate_itinerary.py   # Stage 5: RAG itinerary generation
```

### Insights Pipeline
```
cli/
├── process_insights.py     # Insights extraction
├── insights_stats.py       # Insights statistics
└── reset_insights.py       # Reset insights pipeline
```

### Utility Commands
```
cli/
├── tracking.py             # Pipeline status
├── search_entities.py      # Entity search
├── show_entity.py          # Show entity details
├── stage3_stats.py         # Stage 3 statistics
├── stage4_stats.py         # Stage 4 statistics
├── validate_stage3.py      # Validate Stage 3 output
├── audit_s3.py             # Audit S3 storage
├── sync_to_cloud.py        # Sync to ChromaDB Cloud
├── backup_vectors.py       # Backup vector database
└── monitor_stage4.py       # Monitor Stage 4 progress
```

### Reset Commands
```
cli/
├── reset_stage2.py         # Reset Stage 2
├── reset_stage3.py         # Reset Stage 3
├── reset_stage4.py         # Reset Stage 4
├── reset_all_stages.py     # Reset all stages (keeps Stage 1)
└── reset_insights.py       # Reset insights
```

**Usage Example:**
```bash
# CLI commands are invoked via ./crawl.sh
./crawl.sh youtube --input urls.txt     # Runs cli/crawl.py
./crawl.sh status                       # Runs cli/tracking.py
./crawl.sh search --query "temples"     # Runs cli/search_entities.py
```

---

## Source Directory (`src/`)

Core pipeline implementation organized by functionality.

### Overall Structure
```
src/
├── crawlers/               # Stage 1: Video crawling
├── processors/             # Stages 2-4: Processing logic
├── rag/                    # Stage 5: RAG pipeline
├── storage/                # S3 and file storage
├── vectordb/               # ChromaDB integration
├── llm/                    # LLM provider abstractions
└── utils/                  # Shared utilities
```

---

## Stage 1: Crawlers (`src/crawlers/`)

YouTube video crawling and transcription.

```
src/crawlers/
├── __init__.py
├── base.py                 # BaseCrawler abstract class
└── youtube.py              # YouTubeCrawler implementation
```

**Key Classes:**
- `YouTubeCrawler`: Downloads videos, transcribes with Whisper, uploads to S3
- Handles: YouTube API, yt-dlp, Whisper models

**See:** [stage1-crawling.md](../03-pipeline-stages/stage1-crawling.md)

---

## Stage 2-4: Processors (`src/processors/`)

Entity extraction, deduplication, enrichment, and vectorization.

### Stage 2: Entity Extraction
```
src/processors/
├── stage2_extractor.py     # Main Stage 2 orchestrator
├── extraction_prompts.py   # LLM prompts for entity extraction
└── transcript_corrector.py # Transcript quality improvement
```

**Key Classes:**
- `Stage2Extractor`: Semantic chunking, entity extraction, fuzzy deduplication
- `ExtractionPrompts`: Prompt templates for LLM calls

**See:** [stage2-extraction.md](../03-pipeline-stages/stage2-extraction.md)

### Stage 3: Deduplication & Enrichment
```
src/processors/
├── stage3_enrichment.py    # Main Stage 3 orchestrator
├── stage3_loader.py        # Load entities from Stage 2
├── deduplication.py        # 4-tier deduplication
├── canonicalization.py     # Canonical ID assignment
├── consensus.py            # LLM consensus for ambiguous duplicates
├── entity_merger.py        # Merge duplicate entities
├── llm_enrichment.py       # Enrich with temporal/logistics info
└── geolocation.py          # Geocoding and geohash generation
```

**Key Classes:**
- `Stage3Enrichment`: 4-tier deduplication + enrichment pipeline
- `Deduplication`: Exact, fuzzy, geohash, LLM consensus
- `LLMEnrichment`: Adds `temporal_info`, `logistics_info`, `popularity_score`, `data_freshness`

**See:** [stage3-enrichment.md](../03-pipeline-stages/stage3-enrichment.md)

### Stage 4: Vectorization
```
src/processors/
├── embedding_generator.py  # Generate gte-large embeddings
├── vector_indexer.py       # Index in ChromaDB
└── entity_filter.py        # Filter entities for embeddings
```

**Key Classes:**
- `EmbeddingGenerator`: Creates 3 embedding types (full_context, experience, logistics)
- `VectorIndexer`: Uploads to ChromaDB with enhanced metadata (geohash, temporal, logistics)

**See:** [stage4-vectorization.md](../03-pipeline-stages/stage4-vectorization.md)

### Shared Processors
```
src/processors/
├── llm_verification.py     # LLM-based verification
└── geolocation.py          # Geocoding utilities (Nominatim + Google Maps)
```

---

## Stage 5: RAG Pipeline (`src/rag/`)

7-phase RAG itinerary generation.

```
src/rag/
├── pipeline.py             # Main RAG orchestrator
├── intent_parser.py        # Phase 1: Parse user query
├── retriever.py            # Phase 2: ChromaDB retrieval
├── reranker.py             # Phase 3: Re-rank by relevance
├── context_builder.py      # Phase 4: Build LLM context
├── itinerary_generator.py  # Phase 5: Generate itinerary
├── validator.py            # Phase 6: Validate feasibility
├── narrative_generator.py  # Phase 7: Add narrative & tips
├── error_handling.py       # Error handling and retries
└── formatter.py            # Output formatting
```

**Key Classes:**
- `RAGPipeline`: End-to-end itinerary generation
- `IntentParser`: Extract destination, duration, vibe, constraints
- `Retriever`: Query ChromaDB with geohash filters
- `Reranker`: Score entities by VIBE match
- `ItineraryGenerator`: LLM-based day-by-day planning
- `Validator`: Check feasibility (distances, timing, logistics)

**See:** [stage5-rag.md](../03-pipeline-stages/stage5-rag.md)

---

## Insights Pipeline (`src/processors/`)

Parallel pipeline for entity insights generation.

```
src/processors/
├── insights_extractor.py       # Extract insights from Stage 1
├── insight_prompts.py          # LLM prompts for insights
├── insight_deduplication.py    # Deduplicate insights
└── insight_canonicalization.py # Canonicalize insight entities
```

**See:** [insights-pipeline.md](../03-pipeline-stages/insights-pipeline.md)

---

## Storage (`src/storage/`)

S3 and local file management.

```
src/storage/
├── __init__.py
├── s3_client.py            # AWS S3 operations
├── metadata_tracker.py     # Track pipeline state (processing_status.jsonl)
└── local_cache.py          # Local file caching
```

**Key Classes:**
- `S3Storage`: Upload/download files to S3
- `MetadataTracker`: JSONL-based pipeline state tracking

**See:** [s3-storage.md](../05-infrastructure/s3-storage.md)

---

## Vector Database (`src/vectordb/`)

ChromaDB integration for semantic search.

```
src/vectordb/
├── __init__.py
├── chroma_client.py        # ChromaDB client (local + cloud)
├── collection_manager.py   # Collection setup and management
└── search.py               # Query interface with filters
```

**Key Classes:**
- `ChromaClient`: Connect to ChromaDB (local or Chroma Cloud)
- `CollectionManager`: Manage `travel_entities` collection
- `VectorSearch`: Query with geohash, temporal, logistics filters

**See:** [chromadb.md](../05-infrastructure/chromadb.md)

---

## LLM Providers (`src/llm/`)

Abstraction layer for multiple LLM providers.

```
src/llm/
├── __init__.py
├── base.py                 # BaseLLMProvider abstract class
├── gemini.py               # Gemini (Google AI Studio)
├── openai.py               # OpenAI API
├── deepseek.py             # DeepSeek API
└── factory.py              # LLM provider factory
```

**Key Classes:**
- `BaseLLMProvider`: Common interface for all providers
- `GeminiProvider`, `OpenAIProvider`, `DeepSeekProvider`: Provider implementations
- `LLMFactory`: Creates provider based on `.env` configuration

**Usage Example:**
```python
from src.llm.factory import LLMFactory

llm = LLMFactory.create()  # Reads LLM_PROVIDER from .env
response = llm.generate(prompt="Describe Bangkok in 50 words", max_tokens=100)
```

**See:** [llm-providers.md](../07-development/llm-providers.md)

---

## Utilities (`src/utils/`)

Shared helper functions and utilities.

```
src/utils/
├── __init__.py
├── rag_cost_tracker.py     # RAG cost tracking
├── logger.py               # Logging configuration
├── config.py               # Configuration management
└── validators.py           # Input validation utilities
```

**Key Utilities:**
- `RAGCostTracker`: Track LLM costs per RAG phase
- `setup_logging()`: Configure pipeline logging
- `load_config()`: Load `.env` configuration

**See:** [monitoring.md](../05-infrastructure/monitoring.md)

---

## Configuration Files

### Environment Configuration
```
.env                        # Your credentials (not in git)
.env.example                # Template with placeholders
```

**See:** [configuration.md](../04-reference/configuration.md)

### Python Configuration
```
requirements.txt            # Python dependencies
setup.sh                    # Automated setup script
```

---

## Data Directories

### Local Data Storage
```
data/                       # Local data cache
├── videos/                 # Downloaded videos (temporary)
└── cache/                  # Cached API responses

logs/                       # Pipeline execution logs
├── crawler.log
├── stage2.log
├── stage3.log
└── rag.log

stage4-vectors/             # Local vector cache
└── backups/                # Vector database backups
```

### S3 Storage Structure
```
s3://your-travel-ai-data/
├── stage1_transcripts/     # Video metadata + transcripts
├── stage2_entities/        # Extracted entities per video
├── stage3_canonical/       # Canonical entities
├── stage4_embeddings/      # Vector embeddings metadata
├── stage5_itineraries/     # Generated itineraries
├── insights/               # Insights pipeline outputs
└── metadata/               # Pipeline state tracking
    ├── processing_status.jsonl
    └── canonical_entities.json
```

**See:** [s3-storage.md](../05-infrastructure/s3-storage.md)

---

## Test Structure

```
tests/
├── unit/                   # Unit tests
│   ├── test_crawlers.py
│   ├── test_processors.py
│   └── test_rag.py
├── integration/            # Integration tests
│   ├── test_pipeline.py
│   └── test_s3_storage.py
└── fixtures/               # Test data
    ├── sample_transcripts/
    └── sample_entities/
```

**See:** [testing.md](../07-development/testing.md)

---

## Entry Points

### Main CLI
```bash
./crawl.sh                  # Main CLI wrapper script
```

**Internally:**
1. Sets `PYTHONPATH` to project root
2. Activates virtual environment
3. Routes commands to `cli/*.py` files

### Direct Python Execution
```bash
# If you need to run Python files directly
export PYTHONPATH=/Users/itachi/Documents/Github/TravelAI
python cli/crawl.py --help
```

---

## Code Organization Principles

### 1. Separation of Concerns
- **CLI** (`cli/`): User interface and command parsing
- **Core** (`src/`): Business logic and pipeline implementation
- **Tests** (`tests/`): Test suite

### 2. Pipeline Modularity
Each pipeline stage is independent:
- Reads from S3 (previous stage output)
- Processes data
- Writes to S3 (stage output)

### 3. Provider Abstraction
LLM providers are abstracted (`src/llm/`) for easy switching:
```python
# Change provider in .env
LLM_PROVIDER=gemini    # or openai, deepseek
```

### 4. Metadata Tracking
All pipeline state tracked in `metadata/processing_status.jsonl`:
```json
{"video_id": "youtube_123", "stage1_status": "completed", "stage2_status": "pending"}
```

---

## Navigation Tips

### Finding Code for a Command
```bash
# Command: ./crawl.sh process-stage3
# Implementation: cli/process_stage3.py → src/processors/stage3_enrichment.py
```

### Finding Code for a Stage
```
Stage 1: src/crawlers/youtube.py
Stage 2: src/processors/stage2_extractor.py
Stage 3: src/processors/stage3_enrichment.py
Stage 4: src/processors/embedding_generator.py, vector_indexer.py
Stage 5: src/rag/pipeline.py
```

### Finding Configuration
```
Environment: .env, .env.example
LLM Config: src/llm/factory.py
S3 Config: src/storage/s3_client.py
ChromaDB Config: src/vectordb/chroma_client.py
```

---

## Next Steps

- **Run the pipeline:** [Quickstart Guide](quickstart.md)
- **Understand architecture:** [System Architecture](../02-architecture/system-architecture.md)
- **Deep dive into stages:** [Pipeline Overview](../02-architecture/pipeline-overview.md)
- **CLI reference:** [CLI Commands](../04-reference/cli-commands.md)

---

**Project structure documented!** Next: [Architecture Overview](../02-architecture/system-architecture.md)
