# TravelAI – Internal VIBE Framework (v1)

## Purpose of this Document
This document defines the **VIBE framework** used internally by TravelAI to translate user preferences into concrete itinerary decisions.

VIBE is not a personality quiz or a UI feature. It is a **decision constraint system** that guides what the AI includes, excludes, prioritizes, and how it explains recommendations.

This spec is meant for:
- Product alignment (founders, PMs)
- LLM prompt design
- Evaluation & metrics

---

## What VIBE Means at TravelAI

**VIBE = how a user wants their trip to *feel***.

It governs:
- Experience selection
- Daily pacing
- Transport choices
- Accommodation areas
- Tone and confidence of recommendations

**Key principle:**
> Two users visiting the same cities for the same duration should receive meaningfully different itineraries.

---

## VIBE Dimensions (v1 – Final)

TravelAI uses **five core VIBE dimensions** in v1. These are intentionally limited to avoid overfitting and user fatigue.

### 1. Trip Intent (Primary Driver)
**Question answered:** Why is the user traveling?

Possible intents:
- Calm & slow
- Explore & discover
- Food & cafes
- Scenic & nature
- Social & lively

**Used to decide:**
- Which experience categories dominate
- What to down-rank or exclude
- Crowd tolerance

---

### 2. Pace Preference
**Question answered:** How full should each day feel?

Spectrum:
- Very relaxed
- Balanced
- Packed

**Used to decide:**
- Number of activities per day
- Transit buffer times
- Early morning / late evening usage

---

### 3. Comfort vs Adventure
**Question answered:** How much uncertainty or friction does the user enjoy?

Spectrum:
- Comfort-first
- Balanced
- Adventure-seeking

**Used to decide:**
- Transport modes (flight vs overnight bus, train vs car)
- Accommodation areas (central vs remote)
- Activity risk level

---

### 4. Spending Philosophy
**Question answered:** How does the user emotionally relate to spending money?

Categories:
- Value-conscious but comfortable
- Mid-range, good experiences
- Willing to spend if it feels worth it

**Used to decide:**
- Restaurant tiers
- Hotel class
- Experience trade-offs

(Note: No absolute budgets are collected in v1.)

---

### 5. Structure Preference
**Question answered:** How planned does the user want the trip to feel?

Spectrum:
- Structured & planned
- Flexible framework
- Go-with-the-flow

**Used to decide:**
- Itinerary rigidity
- Presence of free exploration blocks
- How strongly recommendations are phrased

---

## How VIBE Is Represented Internally

Each user session generates a **VIBE profile**, expressed as structured signals (not shown to the user).

Example:
```json
{
  "primary_intent": "calm",
  "secondary_intents": ["food", "scenic"],
  "daily_activity_cap": 3,
  "buffer_time_multiplier": 1.4,
  "transport_risk_tolerance": "low",
  "price_sensitivity": "medium",
  "itinerary_rigidity": "medium"
}
```

This profile is passed as **hard constraints + soft biases** into itinerary generation.

---

## How VIBE Influences Itinerary Generation

### Hard Constraints
Applied deterministically or via rules:
- Maximum activities per day
- Minimum buffer times
- City sequencing feasibility

### Soft Biases
Applied via LLM prompting and re-ranking:
- Which experiences are prioritized
- Which attractions are avoided or softened
- Tone of explanation (assertive vs suggestive)

---

## What VIBE Is NOT

- ❌ Not a visible score
- ❌ Not a personality label
- ❌ Not a static user profile

VIBE is session-based and can change per trip.

---

## Product Principles Around VIBE

- Fewer questions > more inference
- Allow skipping; infer later if needed
- Always explain *why* something fits the user
- Prefer saying “this may not suit your vibe” over generic inclusion

---

## v1 Scope Guardrails

In v1, VIBE **will not**:
- Optimize purely for cost
- Guarantee popularity or must-see coverage
- Replace user control

In v1, VIBE **must**:
- Reduce planning effort
- Prevent obvious mismatches
- Feel human and thoughtful

---

## Success Criteria (Internal)

A VIBE-aligned plan is successful if:
- Users feel understood without over-explaining
- Regeneration requests decrease after edits
- Users accept exclusions (e.g., skipping hyped spots)
- Itineraries differ clearly across VIBE profiles

---

## Technical Implementation: 12D Vibe Matching System (Phase 2)

While the 5-dimension VIBE framework above defines user-facing preferences, TravelAI internally uses a **12-dimensional vibe matching system** to map user intent to entities in the vector database.

### Purpose

The 12D vibe system enables:
- **Nuanced intent matching** beyond simple 2D profiles (solo/family, budget/luxury)
- **Fast semantic reranking** of retrieval results
- **City-level vibe aggregation** for Tier 1 destination selection
- **Explainable recommendations** based on vibe alignment

### 12 Technical Vibe Dimensions

Each dimension represents a specific aspect of travel experience, scored 0.0-1.0:

| Dimension | Description | Example Keywords |
|-----------|-------------|------------------|
| **Adventure** | Hiking, extreme sports, outdoor activities | trekking, climbing, zipline, diving, rafting |
| **Relaxation** | Spas, beaches, slow pace | spa, massage, beach, chill, peaceful, zen |
| **Culture** | Museums, temples, history, art | temple, museum, palace, heritage, traditional |
| **Nightlife** | Bars, clubs, entertainment | party, club, bar, nightclub, dj, live music |
| **Nature** | Parks, wildlife, natural beauty | park, garden, forest, wildlife, waterfall, scenic |
| **Food** | Culinary experiences, markets | street food, restaurant, market, cuisine, foodie |
| **Shopping** | Markets, malls, local crafts | shopping, market, mall, boutique, souvenir, craft |
| **Luxury** | High-end experiences, premium | luxury, premium, exclusive, five-star, upscale |
| **Budget** | Cost-conscious, free activities | budget, cheap, affordable, free, backpack |
| **Social** | Group activities, meeting people | social, group, fun, lively, bustling, vibrant |
| **Solo** | Solo-friendly, introspective | solo, alone, peaceful, quiet, meditative, private |
| **Family** | Kid-friendly, family activities | family, kid, children, educational, playground |

### How It Works

#### 1. Entity Vibe Extraction

Each entity in Stage 3 gets a 12D vibe vector extracted during Stage 4 indexing:

```python
from src.rag.vibe_extractor import VibeExtractor

extractor = VibeExtractor()
vibes = extractor.extract_entity_vibes(entity)

# Example output
vibes = {
    'nightlife': 0.95,
    'food': 0.7,
    'social': 0.8,
    'culture': 0.3,
    # ... other dimensions
}
```

**Extraction Methods**:
- **Rule-based**: Entity type → vibe mapping (e.g., nightclub → nightlife=1.0)
- **Keyword-based**: Experience descriptions analyzed for vibe keywords
- **Attribute-based**: Price level → luxury/budget vibes

#### 2. Query Vibe Extraction

User queries are analyzed to extract intent across 12 dimensions:

```python
query = "5 days Bangkok party and food budget"
query_vibes = extractor.extract_query_vibes(query)

# Example output
query_vibes = {
    'nightlife': 0.8,  # "party"
    'food': 0.9,       # "food"
    'budget': 0.9,     # "budget"
    'social': 0.6,     # implied from "party"
    # ... other dimensions lower
}
```

#### 3. Vibe-Based Reranking

During Stage 5 retrieval, semantic search results are reranked using vibe similarity:

```python
from src.rag.vibe_scorer import VibeScorer

scorer = VibeScorer()
vibe_score = scorer.compute_similarity(query_vibes, entity_vibes)

# Combined score: 60% semantic + 40% vibe
final_score = 0.6 * semantic_similarity + 0.4 * vibe_score
```

**Similarity Method**: Cosine similarity between 12D vectors

#### 4. City-Level Vibe Aggregation

For Tier 1 city selection, entity vibes are averaged to create city-level profiles:

```python
# Bangkok city vibes (averaged from 245 entities)
bangkok_vibes = {
    'nightlife': 0.75,  # Strong nightlife presence
    'food': 0.90,       # Exceptional food scene
    'culture': 0.65,    # Rich cultural heritage
    'budget': 0.70,     # Budget-friendly
    'luxury': 0.30,     # Some luxury options
    # ...
}
```

This enables semantic city search: "Find cities with great nightlife and food" → Bangkok ranks high.

### Storage

**ChromaDB Metadata** (per entity):
```json
{
  "vibe_adventure": 0.2,
  "vibe_relaxation": 0.1,
  "vibe_culture": 0.7,
  "vibe_nightlife": 0.95,
  "vibe_food": 0.8,
  // ... other dimensions > 0.1
  "vibes_json": "{\"adventure\":0.2,\"relaxation\":0.1,...}"
}
```

**City Index** (city_destinations collection):
- Stores aggregated city vibes in metadata
- Enables city-level vibe filtering

### Performance Benefits

| Metric | Before (2D Profiles) | After (12D Vibes) | Improvement |
|--------|---------------------|-------------------|-------------|
| Vibe Match Accuracy | ~60% | ~85% | +25% |
| Intent Dimensions | 2 (solo/family, budget/luxury) | 12 | 6x more nuanced |
| Query Understanding | Basic | Rich multi-dimensional | Semantic |
| Reranking Quality | N/A | Cosine similarity | New capability |

### Integration with User VIBE Framework

The 5-dimension user VIBE framework (above) maps to technical 12D vibes:

| User VIBE Dimension | Technical Vibe Dimensions |
|---------------------|---------------------------|
| **Trip Intent** → Calm | relaxation=high, nature=high |
| **Trip Intent** → Food & cafes | food=high, social=medium |
| **Trip Intent** → Social & lively | nightlife=high, social=high |
| **Pace** → Relaxed | relaxation=high, adventure=low |
| **Comfort vs Adventure** | adventure=high/low, luxury=high/low |
| **Spending Philosophy** | luxury=high, budget=low (or inverse) |
| **Structure** | (Not directly mapped to vibes) |

### Implementation Files

- **Vibe Extraction**: [src/rag/vibe_extractor.py](../../src/rag/vibe_extractor.py)
- **Vibe Scoring**: [src/rag/vibe_scorer.py](../../src/rag/vibe_scorer.py)
- **Entity Indexing**: [src/processors/vector_indexer.py](../../src/processors/vector_indexer.py)
- **Retrieval Reranking**: [src/rag/retriever.py](../../src/rag/retriever.py)
- **City Aggregation**: [src/processors/city_aggregator.py](../../src/processors/city_aggregator.py)

---

**This document is the single source of truth for VIBE in v1.**

