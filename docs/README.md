# TravelAI Documentation

Welcome to the TravelAI documentation. This guide will help you understand, use, and extend the TravelAI pipeline.

---

## Table of Contents

### 01. Getting Started
Start here if you're new to TravelAI.

- [**Installation**](01-getting-started/installation.md) - Environment setup, dependencies, AWS credentials, API keys
- [**Quickstart**](01-getting-started/quickstart.md) - End-to-end example: crawl → extract → generate itinerary
- [**Project Structure**](01-getting-started/project-structure.md) - Codebase organization (`cli/`, `src/`)

### 02. Architecture
Understand how TravelAI works.

- [**System Architecture**](02-architecture/system-architecture.md) - Product mission, components, data flow
- [**Pipeline Overview**](02-architecture/pipeline-overview.md) - 5-stage main pipeline + insights pipeline
- [**Data Flow**](02-architecture/data-flow.md) - How data transforms from YouTube → itinerary
- [**VIBE Framework**](02-architecture/vibe-framework.md) - 5-dimensional traveler preference system

### 03. Pipeline Stages
Deep dive into each pipeline stage.

- [**Stage 1: Crawling**](03-pipeline-stages/stage1-crawling.md) - YouTube API, Whisper transcription
- [**Stage 2: Extraction**](03-pipeline-stages/stage2-extraction.md) - LLM entity extraction, semantic chunking, fuzzy dedup
- [**Stage 3: Enrichment**](03-pipeline-stages/stage3-enrichment.md) - 4-tier dedup, canonicalization, temporal/logistics enrichment
- [**Stage 4: Vectorization**](03-pipeline-stages/stage4-vectorization.md) - gte-large embeddings, geohash search, ChromaDB
- [**Stage 5: RAG**](03-pipeline-stages/stage5-rag.md) - 7-phase RAG itinerary generation
- [**Insights Pipeline**](03-pipeline-stages/insights-pipeline.md) - Parallel insights generation from Stage 1

### 04. Reference
Quick reference for commands, schemas, and configurations.

- [**CLI Commands**](04-reference/cli-commands.md) - Complete command-line reference
- [**API Reference**](04-reference/api-reference.md) - FastAPI endpoints documentation
- [**Data Schemas**](04-reference/data-schemas.md) - Entity types, profiles, all schemas
- [**Configuration**](04-reference/configuration.md) - .env variables, config files, LLM settings
- [**Entity Lifecycle**](04-reference/entity-lifecycle.md) - Entity state management
- [**Entity Filtering**](04-reference/entity-filtering.md) - Filtering capabilities

### 05. Infrastructure
Setup and manage infrastructure components.

- [**S3 Storage**](05-infrastructure/s3-storage.md) - S3 structure, file formats
- [**ChromaDB**](05-infrastructure/chromadb.md) - Vector database setup (Chroma Cloud)
- [**Deployment**](05-infrastructure/deployment.md) - Docker, nginx, production deployment
- [**Monitoring**](05-infrastructure/monitoring.md) - Logging, cost tracking, metrics

### 06. Operations
Day-to-day operations and troubleshooting.

- [**Production Runbook**](06-operations/runbook.md) - Day-to-day operations guide
- [**Troubleshooting**](06-operations/troubleshooting.md) - Common issues and solutions
- [**Backup & Recovery**](06-operations/backup-recovery.md) - Data backup, disaster recovery
- [**Error Handling**](06-operations/error-handling.md) - Error patterns, retry strategies

### 07. Development
Contributing and extending TravelAI.

- [**Contributing**](07-development/contributing.md) - How to contribute, code style, PR process
- [**Testing**](07-development/testing.md) - Test strategy, running tests
- [**Adding New Stages**](07-development/adding-new-stages.md) - Extending the pipeline
- [**LLM Providers**](07-development/llm-providers.md) - DeepSeek, Gemini, OpenAI configuration

---

## Quick Navigation

### For New Developers
1. Start with [Installation](01-getting-started/installation.md)
2. Follow the [Quickstart](01-getting-started/quickstart.md)
3. Read [System Architecture](02-architecture/system-architecture.md)
4. Explore specific [Pipeline Stages](03-pipeline-stages/)

### For Operators
1. [Production Runbook](06-operations/runbook.md) for daily tasks
2. [Troubleshooting](06-operations/troubleshooting.md) for issues
3. [Monitoring](05-infrastructure/monitoring.md) for metrics

### For Quick Reference
1. [CLI Commands](04-reference/cli-commands.md) for command syntax
2. [Data Schemas](04-reference/data-schemas.md) for entity structures
3. [Configuration](04-reference/configuration.md) for settings

---

## Additional Resources

- **Root README**: [../README.md](../README.md) - Quick overview and commands
- **Archive**: [archive/](archive/) - Historical documentation and analysis

---

## Documentation Version

- **Version**: 2.0
- **Last Updated**: 2026-01-29
- **Status**: Complete for TravelAI v1

---

## Need Help?

- **GitHub Issues**: Report bugs or request features
- **CLI Help**: Run `./crawl.sh --help` for command help
- **Dashboard**: Launch `./crawl.sh dashboard` for visual exploration
