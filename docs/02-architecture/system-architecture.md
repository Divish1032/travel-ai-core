# System Architecture

This document describes the high-level architecture of TravelAI, including the product mission, technical components, and how they work together.

---

## Table of Contents

1. [Product Mission](#product-mission)
2. [Core Problem](#core-problem)
3. [Solution Approach](#solution-approach)
4. [System Components](#system-components)
5. [Component Relationships](#component-relationships)
6. [Data Flow](#data-flow)

---

## Product Mission

**TravelAI helps travelers confidently plan multi-city trips that match their personal vibe by transforming chaotic travel content into structured, explainable, and optimized itineraries.**

### Product Promise

When a user completes planning with TravelAI:
1. They feel confident, not anxious
2. The plan feels personal, not generic
3. Every major decision is intentional and explainable
4. They no longer need to consult external platforms
5. They believe the plan fits how they like to travel

---

## Core Problem

### User Reality Today

Travel planning for international, multi-city trips is:
- **Fragmented** across YouTube, Instagram, Reddit, blogs, and booking sites
- **Optimized for hype**, not personal relevance
- **Mentally exhausting** and time-consuming
- **Prone to blind spots** such as route inefficiency, transport reliability, and attraction closures

Travelers are forced to:
- Watch 100+ videos
- Manually reconcile conflicting advice
- Simulate routes and permutations manually
- Still miss key experiences or make suboptimal choices

### Market Failure

Existing tools fail because:
- Google and YouTube surface content, not decisions
- OTAs optimize transactions, not journeys
- Influencers optimize views, not fit
- Planning tools require heavy manual input

**None answer:** "Given my vibe, what is the best way for me to experience this trip end-to-end?"

---

## Solution Approach

### Solution Pillars

**Pillar 1: Vibe-First Understanding**
- Infers a multi-dimensional travel vibe
- Treats vibe as a vector, not a label
- Filters all recommendations through this lens

**Pillar 2: Experience Intelligence**
- Extracts insights from vlogs, comments, Reddit, and communities
- Separates hype from lived experience
- Surfaces under-discovered, high-fit experiences

**Pillar 3: Route and Journey Optimization**
- Optimizes city sequence, entry/exit points, and transport modes
- Considers fatigue, reliability, and real-world constraints
- Explains why a route is recommended

**Pillar 4: Explainable Planning**
- Every recommendation answers "why this?"
- Distinguishes verified facts from community tips and inferred insights
- Uses empathetic, human language

---

## System Components

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Sources                              │
│  • YouTube Travel Vlogs   • Reddit Communities   • Reviews       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│                   Main Pipeline (5 Stages)                       │
│  Stage 1: Crawling → Stage 2: Extraction → Stage 3: Enrichment  │
│  → Stage 4: Vectorization → Stage 5: RAG Generation             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ├──────────────────────────────────┐
                     v                                  v
┌──────────────────────────────────┐  ┌──────────────────────────┐
│     Insights Pipeline             │  │    Data Storage          │
│  • Entity insights                │  │  • S3 (Structured data)  │
│  • Parallel from Stage 1          │  │  • ChromaDB (Vectors)    │
└──────────────────────────────────┘  └──────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────────┐
│                      User Interface                              │
│  • Streamlit Dashboard (Entity exploration)                      │
│  • CLI (Pipeline operations)                                     │
│  • Web App (User-facing, separate repo)                          │
└─────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. Main Pipeline Components

**Stage 1: YouTube Crawling**
- **Purpose:** Collect travel vlog content
- **Technology:** YouTube Data API v3, Whisper (transcription)
- **Output:** Video metadata + transcripts
- **Location:** `src/crawlers/`

**Stage 2: Entity Extraction**
- **Purpose:** Extract travel entities (places, activities, hotels, restaurants)
- **Technology:** LLM-based extraction, semantic chunking, fuzzy deduplication
- **Output:** Raw entities with metadata
- **Location:** `src/extractors/`

**Stage 3: Canonicalization + Enrichment**
- **Purpose:** Deduplicate and enrich entities
- **Technology:** 4-tier deduplication, consensus building, LLM enrichment
- **Features:**
  - `temporal_info` - Best time to visit
  - `logistics_info` - Practical details
  - `popularity_score` - Relative popularity
  - `data_freshness` - Recency score
- **Location:** `src/canonicalization/`, `src/enrichment/`

**Stage 4: Vectorization**
- **Purpose:** Create searchable vector embeddings
- **Technology:** gte-large embeddings (local, free), ChromaDB (Chroma Cloud)
- **Features:**
  - Geohash geospatial search
  - Enhanced metadata schema
  - Temporal and logistics filtering
- **Location:** `src/embeddings/`, `src/chroma/`

**Stage 5: RAG Itinerary Generation**
- **Purpose:** Generate personalized itineraries
- **Technology:** 7-phase RAG pipeline with validation
- **Phases:**
  1. Intent parsing
  2. Retrieval (vector search + filters)
  3. Re-ranking
  4. Context building
  5. Itinerary generation
  6. Validation
  7. Narrative generation
- **Location:** `src/rag/`

#### 2. Parallel Pipelines

**Insights Pipeline**
- **Purpose:** Generate entity-specific insights
- **Source:** Stage 1 data (parallel to main pipeline)
- **Output:** Curated insights per entity
- **Documentation:** [insights-pipeline.md](../03-pipeline-stages/insights-pipeline.md)

#### 3. Data Storage

**S3 Storage**
- **Purpose:** Data lake for all pipeline stages
- **Structure:** Organized by stage with metadata tracking
- **Documentation:** [s3-storage.md](../05-infrastructure/s3-storage.md)

**ChromaDB (Chroma Cloud)**
- **Purpose:** Vector database for semantic search
- **Collections:**
  - `travel_entities` - Main entity collection
  - Enhanced with geohash, temporal, and logistics metadata
- **Documentation:** [chromadb.md](../05-infrastructure/chromadb.md)

#### 4. Frameworks and Systems

**VIBE Framework**
- **Purpose:** 5-dimensional traveler preference system
- **Dimensions:** Touristiness, Adventure, Budget, Pace, Food Focus
- **Documentation:** [vibe-framework.md](vibe-framework.md)

**Entity Lifecycle**
- **Purpose:** State management for entities across pipeline stages
- **Documentation:** [entity-lifecycle.md](../04-reference/entity-lifecycle.md)

**Entity Filtering**
- **Purpose:** Advanced filtering capabilities for entities
- **Documentation:** [entity-filtering.md](../04-reference/entity-filtering.md)

**Cost Tracking**
- **Purpose:** Monitor LLM API costs
- **Documentation:** [monitoring.md](../05-infrastructure/monitoring.md)

---

## Component Relationships

### Pipeline Data Flow

```
YouTube Videos
    ↓ (Stage 1: Crawling)
Transcripts + Metadata
    ↓ (Stage 2: Extraction)
Raw Entities
    ↓ (Stage 3: Enrichment)
Canonical Entities (enriched)
    ↓ (Stage 4: Vectorization)
Vector Embeddings
    ↓ (Stage 5: RAG)
Personalized Itineraries
```

### Storage Integration

```
Each Stage
    ↓
S3 (Data Lake)
    • stage1_transcripts/
    • stage2_entities/
    • stage3_canonical/
    • stage4_vectors/
    • stage5_itineraries/

ChromaDB (Vectors)
    • travel_entities collection
    • Geohash + temporal + logistics metadata
```

### Component Dependencies

```
CLI Commands
    ↓
Pipeline Modules
    ↓
├── LLM Providers (DeepSeek, Gemini, OpenAI)
├── S3 Client (AWS SDK)
├── ChromaDB Client (Chroma Cloud)
├── YouTube API
└── Whisper API
```

---

## Data Flow

See [data-flow.md](data-flow.md) for detailed data transformation patterns.

**Summary:**
1. **Input:** YouTube video URLs
2. **Stage 1:** Video → Transcript
3. **Stage 2:** Transcript → Raw entities
4. **Stage 3:** Raw entities → Canonical + enriched entities
5. **Stage 4:** Canonical entities → Vector embeddings
6. **Stage 5:** User query + vectors → Personalized itinerary
7. **Output:** Structured itinerary with narrative

---

## Technology Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Language** | Python 3.11+ | Primary implementation language |
| **LLM Providers** | DeepSeek, Gemini, OpenAI | Entity extraction, enrichment, RAG |
| **Embeddings** | gte-large (local) | Vector embeddings (free) |
| **Vector DB** | ChromaDB (Chroma Cloud) | Semantic search |
| **Storage** | AWS S3 | Data lake |
| **Transcription** | OpenAI Whisper | Speech-to-text |
| **CLI Framework** | Click | Command-line interface |
| **Dashboard** | Streamlit | Entity visualization |

### Infrastructure

- **Deployment:** Docker, nginx
- **Monitoring:** Custom logging, cost tracking
- **CI/CD:** (To be configured)

---

## MVP Scope

### TravelAI Delivers (v1)

- ✅ Optimized city sequence and route
- ✅ Transport-aware itinerary
- ✅ Hotel recommendations aligned to vibe and location
- ✅ Curated attractions, cafes, restaurants, activities, and dishes
- ✅ Flexible day-wise travel flow
- ✅ Explainable recommendations

### TravelAI Does Not (MVP)

- ❌ Handle bookings
- ❌ Provide exhaustive price comparisons
- ❌ Offer infinite alternatives
- ❌ Serve every travel style

---

## Success Metrics

### North Star Metric
**Planning Completion Without External Tools**

Percentage of users ready to travel without consulting YouTube, Reddit, or Google again.

### Core Metrics

**Vibe Match Score**
- User rating: "Does this trip feel like you?" (1–5)
- Target: ≥ 4.0

**Surprise Value**
- Users marking at least one recommendation as unexpected
- Target: ≥ 60%

**Regeneration Rate**
- Percentage of plans regenerated
- Reasons tracked (pace, budget, touristiness, etc.)

**Time to Usable Plan**
- From first input to confident itinerary
- Target: < 10 minutes

### Guardrail Metrics
- Hallucination reports
- Incorrect factual claims
- Infeasible routes or days

**Target:** Near zero

---

## Design Principles

### 1. User Reacts. AI Reasons.

**User Responsibilities:**
- Describe intent naturally
- React to AI proposals
- Approve or reject suggestions

**AI Responsibilities:**
- Reason through trade-offs
- Optimize routes and pacing
- Filter noise
- Make confident recommendations

### 2. Trust and Safety

- Label verified facts vs inferred insights
- Provide provenance for key decisions
- Use conservative language when uncertain
- Avoid asserting unverifiable claims

### 3. Decision-Making, Not Browsing

TravelAI is a decision-making layer, not a content browser. Every feature should help users make confident decisions.

---

## References

- **Pipeline Overview:** [pipeline-overview.md](pipeline-overview.md)
- **Data Flow:** [data-flow.md](data-flow.md)
- **VIBE Framework:** [vibe-framework.md](vibe-framework.md)
- **CLI Reference:** [cli-commands.md](../04-reference/cli-commands.md)
- **Infrastructure:** [s3-storage.md](../05-infrastructure/s3-storage.md), [chromadb.md](../05-infrastructure/chromadb.md)
