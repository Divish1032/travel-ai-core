# TravelAI

**Transform YouTube travel vlogs into personalized itineraries.** TravelAI extracts structured travel data from YouTube videos and generates customized travel plans using AI-powered RAG (Retrieval Augmented Generation).

---

## Key Features

- **YouTube Content Intelligence**: Automatically crawls and transcribes travel vlogs using Whisper AI
- **Entity Extraction**: Extracts places, restaurants, hotels, and activities from travel-video transcripts
- **Smart Deduplication**: 4-tier canonicalization with geocoding and enrichment
- **Semantic Search**: FREE local embeddings with ChromaDB vector database
- **RAG Itinerary Generation**: Natural language queries → personalized day-by-day itineraries
- **Cost-Effective**: ~$0.01-0.02 per itinerary using optimized LLM providers
- **Operational Pipeline**: S3 data lake, metadata tracking, monitoring, and error handling

---

## Quick Commands

### Setup
```bash
# Clone and install
git clone https://github.com/Divish1032/travel-ai-core.git
cd travel-ai-core
./setup.sh

# Configure credentials
cp .env.example .env
# Edit .env with your AWS, YouTube, and LLM API keys
```

### Run Pipeline
```bash
# Stage 1: Crawl YouTube videos
./crawl.sh youtube --input urls.txt

# Stage 2: Extract entities
./crawl.sh process-stage2

# Stage 3: Deduplicate & enrich
./crawl.sh process-stage3

# Stage 4: Generate embeddings
./crawl.sh process-stage4 --embedding-types all

# Stage 5: Generate itinerary
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget party"
```

### Monitoring
```bash
# View pipeline status
./crawl.sh status

# Launch dashboard at http://localhost:8501
./crawl.sh dashboard

# Search entities
./crawl.sh search --query "best street food" --city Bangkok
```

---

## Prerequisites

- **Python 3.11+**
- **AWS Account** with S3 access
- **API Keys**:
  - YouTube Data API (crawling)
  - Gemini / OpenAI / DeepSeek (entity extraction, RAG)
  - Optional: Google Maps Geocoding (enrichment fallback)

---

## Dashboard

Interactive Streamlit dashboard for exploring entities and monitoring pipeline:

```bash
./crawl.sh dashboard
```

**URL**: http://localhost:8501

**Features**: Video explorer, entity search, analytics, metadata viewer

---

## Documentation

📚 **For complete documentation, see [docs/](docs/README.md)**

**Quick Links**:
- [Installation Guide](docs/01-getting-started/installation.md)
- [Quickstart Tutorial](docs/01-getting-started/quickstart.md)
- [System Architecture](docs/02-architecture/system-architecture.md)
- [Pipeline Stages](docs/03-pipeline-stages/)
- [CLI Commands Reference](docs/04-reference/cli-commands.md)
- [Configuration Guide](docs/04-reference/configuration.md)

---

## Project Stats

- **Videos Processed**: 117 (all 5 stages complete)
- **Entities Extracted**: 5,000+ raw → 1,200+ canonical
- **Vector Embeddings**: 13,000+ indexed in ChromaDB
- **Pipeline Cost**: ~$0.30 total for all data
- **Per-Itinerary Cost**: ~$0.01-0.02

---

## Quick Example

```bash
# Generate itinerary from natural language
./crawl.sh generate-itinerary -q "3 days Phuket couple mid-range beach relaxation"

# Output: Day-by-day itinerary with:
# - Personalized recommendations
# - Cost breakdown
# - Travel tips
# - Validated against 1,200+ entities
```

---

## License

MIT License - See LICENSE file for details

---

## Support

- **Issues**: [GitHub Issues](https://github.com/Divish1032/travel-ai-core/issues)
- **Documentation**: [docs/](docs/README.md)
- **CLI Reference**: [COMMANDS.md](docs/04-reference/cli-commands.md)
