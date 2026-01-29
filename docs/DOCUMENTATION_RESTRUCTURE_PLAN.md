# Documentation Restructure Plan

## Overview

This document describes the plan to restructure the TravelAI documentation into a clear, navigable format that allows new contributors to easily understand the project.

**Current Problem:**
- Documentation files are scattered in docs/ folder without clear structure
- Files are outdated and not updated with recent changes
- No consistent format or organization
- Mix of operational, technical, product, and development docs without separation
- Difficult for newcomers to know where to start

**Solution:**
- Implement two-tier documentation structure
- Project root README.md for quick overview and basic commands
- Detailed documentation in docs/ folder with numbered sections for progressive learning

---

## Structure Design

### Root Level

```
/README.md                          # High-level overview + quick commands
```

**Content:**
- 2-3 sentence project description (what TravelAI does)
- Key features (bullet points)
- **Quick Commands** section with common operations:
  - Run Stage 1 (YouTube crawl)
  - Run Stage 2 (Entity extraction)
  - Run Stage 3 (Enrichment)
  - Run Stage 4 (Vectorization)
  - Run Stage 5 (RAG itinerary generation)
  - Start Streamlit Dashboard
  - Start Web Application
- Prerequisites (Python version, AWS credentials, API keys)
- Link to detailed documentation: `📚 See detailed documentation in docs/`
- No depth - keep it concise and welcoming

### Docs Folder Structure

```
/docs/
├── README.md                       # Navigation guide for detailed documentation
│
├── 01-getting-started/
│   ├── installation.md             # Environment setup, dependencies, credentials
│   ├── quickstart.md               # End-to-end example to run pipeline
│   └── project-structure.md        # Codebase layout explanation
│
├── 02-architecture/
│   ├── system-architecture.md      # High-level system design & component relationships
│   ├── pipeline-overview.md        # 5-stage main pipeline + insights pipeline
│   ├── data-flow.md                # How data transforms through stages
│   └── vibe-framework.md           # VIBE traveler preference framework
│
├── 03-pipeline-stages/
│   ├── stage1-crawling.md          # YouTube crawling & Whisper transcription
│   ├── stage2-extraction.md        # LLM entity extraction (semantic chunking, fuzzy dedup)
│   ├── stage3-enrichment.md        # Deduplication, canonicalization, consensus + enrichment
│   ├── stage4-vectorization.md     # Embeddings & ChromaDB (geohash search, enhanced metadata)
│   ├── stage5-rag.md               # RAG itinerary generation (7 phases)
│   └── insights-pipeline.md        # Parallel insights generation pipeline from Stage 1
│
├── 04-reference/
│   ├── cli-commands.md             # Complete CLI reference
│   ├── api-reference.md            # FastAPI endpoints documentation
│   ├── data-schemas.md             # Entity types, profiles, all schemas
│   ├── configuration.md            # Config files, environment variables
│   ├── entity-lifecycle.md         # Entity state management
│   └── entity-filtering.md         # Entity filtering capabilities
│
├── 05-infrastructure/
│   ├── s3-storage.md               # S3 structure & file formats
│   ├── chromadb.md                 # Vector database setup & collections (Chroma Cloud)
│   ├── deployment.md               # Docker, nginx, production deployment
│   └── monitoring.md               # Logging, cost tracking, metrics
│
├── 06-operations/
│   ├── runbook.md                  # Day-to-day operations guide
│   ├── troubleshooting.md          # Common issues & solutions
│   ├── backup-recovery.md          # Data backup & disaster recovery
│   └── error-handling.md           # Error patterns & retry strategies
│
├── 07-development/
│   ├── contributing.md             # How to contribute, code style
│   ├── testing.md                  # Test strategy & running tests
│   ├── adding-new-stages.md        # Extending the pipeline
│   └── llm-providers.md            # DeepSeek, Gemini, OpenAI configuration
│
└── archive/                        # Old docs preserved for reference
    ├── AUDIT_FINDINGS.md
    ├── IMPROVEMENT_PLAN.md
    ├── PLAN_INCREMENTAL_STAGE3.md
    ├── STAGE3_IMPROVEMENTS_COMPLETED.md
    ├── STAGE4_ANALYSIS_AND_IMPROVEMENT_PLAN.md
    └── travel-ai-guide.txt
```

---

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Numbered folders** | Clear navigation order - newcomers start at 01, progress sequentially |
| **Single responsibility** | Each file covers one topic completely |
| **Progressive disclosure** | Start high-level (getting-started), go deeper (pipeline-stages, reference) |
| **Audience separation** | Separate operations, development, and reference documentation |
| **Archive old docs** | Preserve historical context without cluttering main docs |
| **Two-tier approach** | Root README for quick start, docs/ for depth |

---

## Content Migration Plan

### Existing Files → New Locations

| Existing File | → New Location | Notes |
|--------------|----------------|-------|
| `travel_ai_product_contract.md` | → `02-architecture/system-architecture.md` | Merge mission/product info into architecture overview |
| `travel_ai_internal_vibe_framework_v_1_spec.md` | → `02-architecture/vibe-framework.md` | Keep as-is, just move |
| `COMMANDS.md` | → `04-reference/cli-commands.md` | Keep comprehensive CLI reference |
| `TYPES_AND_ASSUMPTIONS.md` | → `04-reference/data-schemas.md` | All entity types, profiles, schemas |
| `ENTITY_LIFECYCLE.md` | → `04-reference/entity-lifecycle.md` | Move as-is |
| `ENTITY_FILTERING.md` | → `04-reference/entity-filtering.md` | Move as-is |
| `S3_STORAGE.md` | → `05-infrastructure/s3-storage.md` | Keep structure documentation |
| `CHROMADB.md` | → `05-infrastructure/chromadb.md` | Vector DB setup & collections (Chroma Cloud) |
| `PRODUCTION_RUNBOOK.md` | → `06-operations/runbook.md` | Day-to-day operations |
| `ERROR_HANDLING.md` | → `06-operations/error-handling.md` | Error patterns & strategies |
| `COST_TRACKING.md` | → `05-infrastructure/monitoring.md` | Merge into monitoring guide |
| `INSIGHTS_PIPELINE.md` | → `03-pipeline-stages/insights-pipeline.md` | Move as-is |
| `STAGE2_GUARDRAILS.md` | → Merge into `03-pipeline-stages/stage2-extraction.md` | Key improvements to document in stage2 |
| `STAGE4_ANALYSIS_AND_IMPROVEMENT_PLAN.md` | → `archive/` | Analysis complete, improvements implemented |
| `AUDIT_FINDINGS.md` | → `archive/` | Historical audit |
| `IMPROVEMENT_PLAN.md` | → `archive/` | Historical plan |
| `PLAN_INCREMENTAL_STAGE3.md` | → `archive/` | Implemented plan |
| `STAGE3_IMPROVEMENTS_COMPLETED.md` | → `archive/` | Historical record |
| `travel-ai-guide.txt` | → `archive/` | Original concepts |

---

## New Content to Create

These files don't exist in current documentation and need to be written:

### Root Level
1. **`/README.md`** - Project overview with quick commands

### Getting Started
2. **`installation.md`** - Complete setup guide (Python env, dependencies, AWS setup, API keys, Chroma Cloud)
3. **`quickstart.md`** - End-to-end example: crawl video → extract entities → generate itinerary
4. **`project-structure.md`** - Explain cli/, src/ organization (webapp/ and dashboard/ have separate repos/docs)

### Architecture
6. **`system-architecture.md`** - Component diagram, how pieces fit together (merge product contract)
7. **`pipeline-overview.md`** - Summary of all 5 main stages + insights pipeline
8. **`data-flow.md`** - How data transforms from YouTube video → entities → vectors → itinerary

### Pipeline Stages
9. **`stage1-crawling.md`** - YouTube API, Whisper transcription, output format
10. **`stage2-extraction.md`** - LLM entity extraction with semantic chunking, fuzzy dedup, subjective data focus (merge key points from STAGE2_GUARDRAILS.md)
11. **`stage3-enrichment.md`** - 4-tier deduplication, canonicalization, consensus + enrichment (temporal_info, logistics_info, popularity_score, data_freshness)
12. **`stage4-vectorization.md`** - gte-large embeddings, ChromaDB indexing, enhanced metadata schema, geohash geospatial search
13. **`stage5-rag.md`** - 7-phase RAG pipeline with intent parsing, retrieval, re-ranking, validation

### Reference
14. **`api-reference.md`** - FastAPI endpoints documentation
15. **`configuration.md`** - .env variables, config files, LLM settings, Chroma Cloud config

### Infrastructure
16. **`deployment.md`** - Docker setup, nginx proxy, production deployment steps
17. **`monitoring.md`** - Logs, cost tracking, performance metrics (merge COST_TRACKING.md here)

### Operations
18. **`troubleshooting.md`** - Common issues & solutions
19. **`backup-recovery.md`** - S3 backup, ChromaDB backup, disaster recovery

### Development
20. **`contributing.md`** - How to contribute, code style, PR process
21. **`testing.md`** - Test strategy, running tests, coverage
22. **`adding-new-stages.md`** - How to extend the pipeline with new stages
23. **`llm-providers.md`** - DeepSeek, Gemini, OpenAI configuration & switching

### Navigation
24. **`/docs/README.md`** - Documentation index with links to all sections

---

## User Journeys

The structure supports three primary user types:

### 1. New Developer
**Path:**
- Start at `/README.md` (high-level overview)
- Go to `/docs/01-getting-started/installation.md`
- Read `/docs/01-getting-started/quickstart.md`
- Explore `/docs/02-architecture/` for system understanding
- Dive into specific `/docs/03-pipeline-stages/` as needed

### 2. Operator
**Path:**
- Quick reference at `/README.md` for commands
- Jump to `/docs/06-operations/runbook.md` for procedures
- Use `/docs/06-operations/troubleshooting.md` when issues arise
- Refer to `/docs/05-infrastructure/monitoring.md` for metrics

### 3. Reference Lookup
**Path:**
- Go directly to `/docs/04-reference/cli-commands.md` for CLI syntax
- Check `/docs/04-reference/data-schemas.md` for entity structures
- Use `/docs/04-reference/api-reference.md` for API endpoints

---

## Implementation Checklist

When implementing this restructure:

### Phase 1: Setup
- [x] Create folder structure in /docs/
- [x] Create /docs/archive/ folder
- [x] Move old files to archive (6 files moved)

### Phase 2: Migrate Existing Content
- [x] Migrate COMMANDS.md → 04-reference/cli-commands.md
- [x] Migrate TYPES_AND_ASSUMPTIONS.md → 04-reference/data-schemas.md
- [x] Migrate ENTITY_LIFECYCLE.md → 04-reference/entity-lifecycle.md
- [x] Migrate ENTITY_FILTERING.md → 04-reference/entity-filtering.md
- [x] Migrate S3_STORAGE.md → 05-infrastructure/s3-storage.md
- [x] Migrate CHROMADB.md → 05-infrastructure/chromadb.md
- [x] Migrate PRODUCTION_RUNBOOK.md → 06-operations/runbook.md
- [x] Migrate ERROR_HANDLING.md → 06-operations/error-handling.md
- [x] Migrate COST_TRACKING.md → 05-infrastructure/monitoring.md (merged)
- [x] Migrate INSIGHTS_PIPELINE.md → 03-pipeline-stages/insights-pipeline.md
- [x] Migrate travel_ai_internal_vibe_framework_v_1_spec.md → 02-architecture/vibe-framework.md
- [x] Migrate travel_ai_product_contract.md → 02-architecture/system-architecture.md (merged)
- [x] Archive STAGE2_GUARDRAILS.md (will merge key concepts into stage2-extraction.md in Phase 3)
- [x] Archive STAGE4_ANALYSIS_AND_IMPROVEMENT_PLAN.md
- [x] Archive AUDIT_FINDINGS.md
- [x] Archive IMPROVEMENT_PLAN.md
- [x] Archive PLAN_INCREMENTAL_STAGE3.md
- [x] Archive STAGE3_IMPROVEMENTS_COMPLETED.md
- [x] Archive travel-ai-guide.txt

### Phase 3: Create New Content
- [ ] Write /README.md (root) - include dashboard reference with URL
- [ ] Write /docs/README.md (navigation)
- [ ] Write 01-getting-started/installation.md
- [ ] Write 01-getting-started/quickstart.md
- [ ] Write 01-getting-started/project-structure.md (cli/, src/ only)
- [x] Write 02-architecture/system-architecture.md (merged product contract)
- [ ] Write 02-architecture/pipeline-overview.md
- [ ] Write 02-architecture/data-flow.md
- [ ] Write 03-pipeline-stages/stage1-crawling.md
- [ ] Write 03-pipeline-stages/stage2-extraction.md (include semantic chunking, fuzzy dedup concepts)
- [ ] Write 03-pipeline-stages/stage3-enrichment.md (include temporal/logistics enrichment)
- [ ] Write 03-pipeline-stages/stage4-vectorization.md (include geohash search, enhanced metadata)
- [ ] Write 03-pipeline-stages/stage5-rag.md
- [ ] Write 04-reference/api-reference.md
- [ ] Write 04-reference/configuration.md
- [ ] Write 05-infrastructure/deployment.md
- [x] Write 05-infrastructure/monitoring.md (merged COST_TRACKING.md)
- [ ] Write 06-operations/troubleshooting.md
- [ ] Write 06-operations/backup-recovery.md
- [ ] Write 07-development/contributing.md
- [ ] Write 07-development/testing.md
- [ ] Write 07-development/adding-new-stages.md
- [ ] Write 07-development/llm-providers.md

### Phase 4: Review & Links
- [ ] Add cross-references between related docs
- [ ] Verify all internal links work
- [ ] Update any code comments that reference old doc locations
- [ ] Test navigation flow for each user journey

---

## Notes for Implementation

1. **Consistency:** Use consistent formatting across all markdown files (headings, code blocks, tables)
2. **Code Examples:** Include working code examples with actual project paths
3. **Commands:** Test all commands in documentation before publishing
4. **Version Control:** Consider including version/last-updated date in each file
5. **Links:** Use relative links for internal documentation references
6. **Diagrams:** Consider adding mermaid diagrams for architecture and data flow
7. **Keep Updated:** Set up a process to update docs when code changes

---

## Benefits

After implementation:
- **Clear entry point** for new contributors
- **Logical progression** from basic to advanced topics
- **Quick reference** for experienced users
- **Separation of concerns** (getting started vs operations vs development)
- **Preservation** of historical context in archive
- **Maintainability** through organized structure

---

## Summary of Current TravelAI Features (v1)

This restructure plan reflects the **complete current state of TravelAI v1**, including:

### Main Pipeline (5 Stages)
1. **Stage 1: YouTube Crawling** - Whisper transcription, browser cookie support
2. **Stage 2: Entity Extraction** - Semantic chunking (not fixed-time), fuzzy deduplication, subjective data focus
3. **Stage 3: Canonicalization + Enrichment** - 4-tier dedup, temporal_info, logistics_info, popularity_score, data_freshness
4. **Stage 4: Vectorization** - gte-large embeddings (FREE), geohash geospatial search, enhanced metadata, Chroma Cloud
5. **Stage 5: RAG Generation** - 7-phase pipeline with validation and error handling

### Parallel Pipelines
- **Insights Pipeline** - Generates entity insights from Stage 1 data

### Infrastructure
- **S3 Storage** - Complete data lake with structured paths
- **ChromaDB** - Chroma Cloud hosted vector database
- **Streamlit Dashboard** - Entity visualization and exploration
- **Metadata Tracking** - Complete lifecycle tracking across all stages

### Product Features
- **VIBE Framework** - 5-dimensional traveler preference system
- **Entity Lifecycle** - State management for entities
- **Entity Filtering** - Advanced filtering capabilities
- **Cost Tracking** - Comprehensive cost tracking for LLM usage

---

**Document Version:** 2.0 (Updated with all v1 features)
**Date:** 2026-01-29
**Status:** Planning - Ready for Implementation
