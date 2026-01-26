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
│   ├── pipeline-overview.md        # 5-stage pipeline summary
│   ├── data-flow.md                # How data transforms through stages
│   └── vibe-framework.md           # VIBE traveler preference framework
│
├── 03-pipeline-stages/
│   ├── stage1-crawling.md          # YouTube crawling & Whisper transcription
│   ├── stage2-extraction.md        # LLM entity extraction
│   ├── stage3-enrichment.md        # Deduplication, canonicalization, consensus
│   ├── stage4-vectorization.md     # Embeddings & ChromaDB indexing
│   └── stage5-rag.md               # RAG itinerary generation (7 phases)
│
├── 04-reference/
│   ├── cli-commands.md             # Complete CLI reference
│   ├── api-reference.md            # FastAPI endpoints documentation
│   ├── data-schemas.md             # Entity types, profiles, all schemas
│   └── configuration.md            # Config files, environment variables
│
├── 05-infrastructure/
│   ├── s3-storage.md               # S3 structure & file formats
│   ├── chromadb.md                 # Vector database setup & collections
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
| `travel-ai-guide.txt` | → `archive/` | Original concepts, merge relevant parts into overview |
| `COMMANDS.md` | → `04-reference/cli-commands.md` | Keep comprehensive CLI reference |
| `TYPES_AND_ASSUMPTIONS.md` | → `04-reference/data-schemas.md` | All entity types, profiles, schemas |
| `S3_STORAGE.md` | → `05-infrastructure/s3-storage.md` | Keep structure documentation |
| `CHROMADB.md` | → `05-infrastructure/chromadb.md` | Vector DB setup & collections |
| `PRODUCTION_RUNBOOK.md` | → `06-operations/runbook.md` | Day-to-day operations |
| `ERROR_HANDLING.md` | → `06-operations/error-handling.md` | Error patterns & strategies |
| `COST_TRACKING.md` | → `05-infrastructure/monitoring.md` | Merge into monitoring guide |
| `AUDIT_FINDINGS.md` | → `archive/` | Historical audit |
| `IMPROVEMENT_PLAN.md` | → `archive/` | Historical plan |
| `PLAN_INCREMENTAL_STAGE3.md` | → `archive/` | Implemented plan |
| `STAGE3_IMPROVEMENTS_COMPLETED.md` | → `archive/` | Historical record |

---

## New Content to Create

These files don't exist in current documentation and need to be written:

### Root Level
1. **`/README.md`** - Project overview with quick commands

### Getting Started
2. **`installation.md`** - Complete setup guide (Python env, dependencies, AWS setup, API keys)
3. **`quickstart.md`** - End-to-end example: crawl video → extract entities → generate itinerary
4. **`project-structure.md`** - Explain cli/, src/, webapp/, dashboard/ organization

### Architecture
5. **`system-architecture.md`** - Component diagram, how pieces fit together
6. **`pipeline-overview.md`** - Summary of all 5 stages in one place
7. **`data-flow.md`** - How data transforms from YouTube video → entities → vectors → itinerary

### Pipeline Stages
8. **`stage1-crawling.md`** - YouTube API, Whisper transcription, output format
9. **`stage2-extraction.md`** - LLM entity extraction process, prompts, validation
10. **`stage3-enrichment.md`** - Deduplication algorithms, canonicalization, consensus building
11. **`stage4-vectorization.md`** - gte-large embeddings, ChromaDB indexing, metadata
12. **`stage5-rag.md`** - 7-phase RAG pipeline detail

### Reference
13. **`api-reference.md`** - FastAPI endpoints documentation
14. **`configuration.md`** - .env variables, config files, LLM settings

### Infrastructure
15. **`deployment.md`** - Docker setup, nginx proxy, production deployment steps
16. **`monitoring.md`** - Logs, cost tracking, performance metrics (merge COST_TRACKING.md here)

### Operations
17. **`troubleshooting.md`** - Common issues & solutions
18. **`backup-recovery.md`** - Data backup strategies, disaster recovery

### Development
19. **`contributing.md`** - How to contribute, code style, PR process
20. **`testing.md`** - Test strategy, running tests, coverage
21. **`adding-new-stages.md`** - How to extend the pipeline with new stages
22. **`llm-providers.md`** - DeepSeek, Gemini, OpenAI configuration & switching

### Navigation
23. **`/docs/README.md`** - Documentation index with links to all sections

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
- [ ] Create folder structure in /docs/
- [ ] Create /docs/archive/ folder
- [ ] Move old files to archive

### Phase 2: Migrate Existing Content
- [ ] Migrate COMMANDS.md → cli-commands.md
- [ ] Migrate TYPES_AND_ASSUMPTIONS.md → data-schemas.md
- [ ] Migrate S3_STORAGE.md → s3-storage.md
- [ ] Migrate CHROMADB.md → chromadb.md
- [ ] Migrate PRODUCTION_RUNBOOK.md → runbook.md
- [ ] Migrate ERROR_HANDLING.md → error-handling.md
- [ ] Migrate COST_TRACKING.md → monitoring.md (merge)
- [ ] Migrate VIBE framework → vibe-framework.md
- [ ] Migrate product contract → system-architecture.md (merge)

### Phase 3: Create New Content
- [ ] Write /README.md (root)
- [ ] Write /docs/README.md (navigation)
- [ ] Write all 01-getting-started/ files
- [ ] Write all 02-architecture/ files
- [ ] Write all 03-pipeline-stages/ files
- [ ] Write remaining 04-reference/ files
- [ ] Write remaining 05-infrastructure/ files
- [ ] Write remaining 06-operations/ files
- [ ] Write all 07-development/ files

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

**Document Version:** 1.0
**Date:** 2026-01-26
**Status:** Planning - Not Yet Implemented
