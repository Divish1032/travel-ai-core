# Configuration Guide

Complete guide to configuring TravelAI via environment variables and configuration files.

---

## Environment Variables (.env)

All configuration is done through `.env` file in project root.

### Setup

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env  # or vim, code, etc.
```

---

## AWS Configuration (REQUIRED)

```bash
# AWS S3 Storage
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-travel-ai-data
```

**Get AWS Credentials:**
1. Go to https://console.aws.amazon.com/iam/
2. Create user with S3 permissions
3. Generate access key
4. Create S3 bucket: `aws s3 mb s3://your-travel-ai-data`

---

## YouTube API (REQUIRED for Stage 1)

```bash
YOUTUBE_API_KEY=your_youtube_api_key_here
```

**Get API Key:**
1. Go to https://console.cloud.google.com/apis/credentials
2. Create project and enable YouTube Data API v3
3. Create API key
4. **Quota:** 10,000 units/day (free) = ~3,000 videos/day

---

## LLM Provider (REQUIRED for Stages 2, 3, 5)

### Choose One Provider

```bash
# Provider selection
LLM_PROVIDER=gemini  # Options: gemini, openai, deepseek
```

### Gemini (Recommended - Cheapest)

```bash
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite
```

**Get API Key:** https://aistudio.google.com/app/apikey
**Cost:** Input $0.075/1M, Output $0.30/1M tokens

### OpenAI (Optional)

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

**Get API Key:** https://platform.openai.com/api-keys
**Cost:** Input $0.150/1M, Output $0.600/1M tokens

### DeepSeek (Optional)

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat
```

**Get API Key:** https://platform.deepseek.com/
**Cost:** Input $0.14/1M, Output $0.28/1M tokens

---

## ChromaDB (REQUIRED for Stage 4)

```bash
# Mode selection
CHROMADB_MODE=cloud  # Options: local, cloud

# Chroma Cloud (Recommended)
CHROMA_API_KEY=your_chroma_api_key_here
CHROMA_SERVER_URL=https://api.trychroma.com
```

**Get Chroma Cloud:**
1. Go to https://app.trychroma.com/
2. Create account
3. Create API key
4. **Free tier:** 1M vectors

**See:** [chromadb.md](../05-infrastructure/chromadb.md)

---

## Optional Configuration

### Google Maps Geocoding (Fallback for Stage 3)

```bash
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```

**Used:** 10% geocoding fallback when Nominatim fails
**Cost:** $5/1000 requests (free tier: $200/month credit)

### Logging

```bash
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/travelai.log
```

### Whisper Model (Stage 1)

```bash
WHISPER_MODEL=small  # Options: tiny, base, small, medium, large
```

---

## Processing Configuration

### Stage 2: Entity Extraction

```bash
# Semantic chunking
USE_SEMANTIC_CHUNKING=true
MIN_CHUNK_DURATION=120        # Minimum 2 minutes
MAX_CHUNK_DURATION=420        # Maximum 7 minutes
TARGET_CHUNK_DURATION=300     # Target 5 minutes

# Fuzzy deduplication
USE_FUZZY_DEDUP=true
FUZZY_THRESHOLD=0.75          # 75% similarity
```

### Stage 3: Canonicalization

```bash
# Deduplication thresholds
FUZZY_AUTO_THRESHOLD=0.90     # Auto-match without LLM
FUZZY_LLM_THRESHOLD=0.80      # LLM verification needed
SEMANTIC_THRESHOLD=0.85       # Semantic matching threshold
LLM_CONFIDENCE_MIN=0.70       # Minimum LLM confidence
```

### Stage 4: Vectorization

```bash
# Embedding configuration
EMBEDDING_MODEL=gte-large     # Local model
EMBEDDING_BATCH_SIZE=32       # Batch size

# Geohash configuration
GEOHASH_PRECISION=7           # Street-level (~150m)
GEOHASH_REGION_PRECISION=4    # Regional (~20km)
```

### Stage 5: RAG Generation

```bash
# Retrieval configuration
RAG_MAX_RETRIEVAL=50          # Max entities to retrieve
RAG_TOP_K=20                  # Top entities for context

# Cost and quality
RAG_BUDGET_LIMIT=0.10         # Max cost per query (USD)
RAG_VALIDATION_THRESHOLD=7.0  # Min validation score

# Output
RAG_OUTPUT_DIR=stage5_itineraries/
RAG_DEFAULT_FORMAT=markdown   # Options: json, markdown, html, text
```

---

## Complete .env Template

```bash
# ==================================================
# AWS Configuration (REQUIRED)
# ==================================================
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-travel-ai-data

# ==================================================
# YouTube API (REQUIRED for Stage 1)
# ==================================================
YOUTUBE_API_KEY=your_youtube_api_key_here

# ==================================================
# LLM Provider (REQUIRED for Stages 2, 3, 5)
# ==================================================
LLM_PROVIDER=gemini  # Options: gemini, openai, deepseek

# Gemini (Recommended)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

# OpenAI (Optional)
OPENAI_API_KEY=your_openai_api_key_here

# DeepSeek (Optional)
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat

# ==================================================
# ChromaDB (REQUIRED for Stage 4)
# ==================================================
CHROMADB_MODE=cloud  # Options: local, cloud
CHROMA_API_KEY=your_chroma_api_key_here
CHROMA_SERVER_URL=https://api.trychroma.com

# ==================================================
# Optional Configuration
# ==================================================

# Google Maps (Geocoding fallback)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/travelai.log

# Whisper Model
WHISPER_MODEL=small

# Stage 2: Entity Extraction
USE_SEMANTIC_CHUNKING=true
USE_FUZZY_DEDUP=true
FUZZY_THRESHOLD=0.75

# Stage 3: Canonicalization
FUZZY_AUTO_THRESHOLD=0.90
FUZZY_LLM_THRESHOLD=0.80
SEMANTIC_THRESHOLD=0.85
LLM_CONFIDENCE_MIN=0.70

# Stage 4: Vectorization
EMBEDDING_MODEL=gte-large
EMBEDDING_BATCH_SIZE=32
GEOHASH_PRECISION=7
GEOHASH_REGION_PRECISION=4

# Stage 5: RAG
RAG_MAX_RETRIEVAL=50
RAG_TOP_K=20
RAG_BUDGET_LIMIT=0.10
RAG_VALIDATION_THRESHOLD=7.0
RAG_OUTPUT_DIR=stage5_itineraries/
RAG_DEFAULT_FORMAT=markdown
```

---

## Validation

### Check Configuration

```bash
# Test configuration loading
python -c "from src.utils.config import config; print(config)"

# Verify AWS credentials
aws s3 ls

# Test LLM provider
./crawl.sh quick-test
```

---

## References

- **Installation:** [installation.md](../01-getting-started/installation.md)
- **LLM Providers:** [llm-providers.md](../07-development/llm-providers.md)
- **ChromaDB Setup:** [chromadb.md](../05-infrastructure/chromadb.md)
