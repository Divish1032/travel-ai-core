# Stage 5: RAG Itinerary Generation

Stage 5 generates personalized day-by-day itineraries from natural language queries using a 7-phase RAG (Retrieval Augmented Generation) pipeline.

**Implementation:** [`src/rag/pipeline.py`](../../src/rag/pipeline.py)

---

## Overview

### Purpose
Transform user travel queries into validated, personalized itineraries using entity retrieval and LLM generation.

### Key Features
- **7-phase pipeline** with validation loops
- **VIBE-based re-ranking** for personalization
- **Geospatial filtering** via geohash
- **Cost tracking** per phase
- **Validation & retry** for quality assurance

### Inputs
- Natural language query (e.g., "5 days Bangkok solo budget street food")
- ChromaDB vector embeddings from Stage 4

### Outputs
- Day-by-day itinerary with timing
- Budget breakdown
- Travel tips and cultural notes
- Cost report (~$0.01-0.02 per itinerary)

---

## 7-Phase RAG Pipeline

### Phase 1: Intent Parsing

**Module:** [`src/rag/intent_parser.py`](../../src/rag/intent_parser.py)

**Purpose:** Extract structured intent from natural language query

**LLM Extraction:**
```
Input: "5 days Bangkok solo budget street food"

Output:
{
  "destination": "Bangkok, Thailand",
  "duration_days": 5,
  "travel_style": "solo",
  "vibe": {
    "touristiness": 4,
    "adventure_level": 5,
    "budget_level": 3,
    "pace": "moderate",
    "food_focus": 9
  },
  "constraints": ["budget", "street food focus"],
  "preferences": ["authentic local experiences", "food-centric"]
}
```

**VIBE Inference:** Analyzes query keywords to assign VIBE dimensions
**Cost:** ~$0.0001 (small prompt, fast LLM call)

---

### Phase 2: Retrieval

**Module:** [`src/rag/retriever.py`](../../src/rag/retriever.py)

**Purpose:** Query ChromaDB to retrieve relevant entities

**Query Strategy:**
```python
# 1. Generate query embedding
query_text = f"{destination} {constraints} {preferences}"
query_embedding = embedding_model.encode(query_text)

# 2. Query with filters
results = chromadb.query(
    query_embeddings=[query_embedding],
    n_results=50,
    where={
        "city": destination_city,
        "country": destination_country,
        "vibe_budget": {"$lte": budget_level + 2},  # Allow some flexibility
        "booking_required": False  # For budget/spontaneous travel
    }
)
```

**Geospatial Filtering:**
- Uses geohash prefix for region filtering
- Example: All Bangkok entities start with `w4r*`

**Temporal Filtering:**
- Filters by best_months if user specifies travel dates
- Avoids entities closed during travel period

**Results:** 50 entities retrieved
**Cost:** FREE (ChromaDB query, no LLM)

---

### Phase 3: Re-ranking

**Module:** [`src/rag/reranker.py`](../../src/rag/reranker.py)

**Purpose:** Score entities by VIBE match and relevance

**Scoring Algorithm:**
```python
def score_entity(entity, user_vibe):
    score = 0.0

    # 1. VIBE match (60% weight)
    vibe_similarity = calculate_vibe_distance(entity.vibe, user_vibe)
    score += vibe_similarity * 0.6

    # 2. Constraint match (20% weight)
    if matches_constraints(entity, user_constraints):
        score += 0.2

    # 3. Popularity (10% weight)
    score += (entity.popularity_score / 100) * 0.1

    # 4. Data freshness (10% weight)
    score += (entity.data_freshness / 100) * 0.1

    return score
```

**VIBE Distance Calculation:**
```python
# Penalize mismatches
touristiness_diff = abs(entity.vibe.touristiness - user_vibe.touristiness)
budget_diff = abs(entity.vibe.budget - user_vibe.budget)
food_focus_diff = abs(entity.vibe.food_focus - user_vibe.food_focus)

# Weighted distance
distance = (
    touristiness_diff * 0.3 +
    budget_diff * 0.3 +
    food_focus_diff * 0.4  # Higher weight for food_focus if user query mentions food
)

similarity = 1.0 - (distance / 30)  # Normalize to 0-1
```

**Example Scores:**
```
User VIBE: touristiness=4, budget=3, food_focus=9

Grand Palace:
- VIBE: touristiness=9, budget=6, food_focus=2
- Distance: High touristiness, low food focus
- Score: 4.2/10 → Ranked #35

Jay Fai (street food):
- VIBE: touristiness=8, budget=6, food_focus=10
- Distance: High food focus matches user
- Score: 8.5/10 → Ranked #3

Chatuchak Market:
- VIBE: touristiness=7, budget=3, food_focus=8
- Distance: Perfect budget match, great food
- Score: 9.2/10 → Ranked #1
```

**Results:** Top 20 entities selected
**Cost:** FREE (local computation)

---

### Phase 4: Context Building

**Module:** [`src/rag/context_builder.py`](../../src/rag/context_builder.py)

**Purpose:** Assemble retrieved entities into structured LLM context

**Context Structure:**
```
USER INTENT:
- Destination: Bangkok, Thailand
- Duration: 5 days
- Travel Style: Solo budget traveler
- VIBE: Low touristiness (4/10), High food focus (9/10)
- Constraints: Budget-conscious, street food focus
- Preferences: Authentic local experiences

RETRIEVED ENTITIES (Top 20):

[RESTAURANTS - 8 entities]
1. Chatuchak Weekend Market (restaurant/street_food)
   Score: 9.2/10 | Popularity: 87/100 | Freshness: 95/100
   Location: Bangkok (geohash: w4rqqq)
   VIBE: touristiness=7, budget=3, food_focus=8
   Context: "Endless street food stalls with incredible variety.
            Budget-friendly with most dishes under 100 THB. Local favorite."
   Temporal: Best on weekends, visit morning (9am-12pm)
   Logistics: No booking needed, cash only

2. Jay Fai (restaurant/street_food)
   Score: 8.5/10 | Popularity: 89/100 | Freshness: 92/100
   ...

[ATTRACTIONS - 7 entities]
...

[ACTIVITIES - 5 entities]
...

TASK: Generate a 5-day itinerary optimized for this traveler's vibe.
```

**Context Size:** 3,000-5,000 tokens
**Cost:** FREE (text assembly)

---

### Phase 5: Generation

**Module:** [`src/rag/itinerary_generator.py`](../../src/rag/itinerary_generator.py)

**Purpose:** LLM generates day-by-day itinerary

**LLM Prompt:**
```
You are a travel expert. Generate a {duration}-day itinerary for {destination}.

TRAVELER PROFILE:
- VIBE: [dimensions]
- Constraints: [constraints]
- Preferences: [preferences]

AVAILABLE ENTITIES:
[Top 20 entities with full context]

REQUIREMENTS:
1. Create {duration} days with 3-5 activities per day
2. Match traveler's VIBE (low touristiness, high food focus)
3. Respect budget constraints (budget tier: 3/10)
4. Include travel time between locations
5. Provide timing recommendations
6. Explain WHY each recommendation fits the traveler

OUTPUT FORMAT:
{
  "days": [
    {
      "day": 1,
      "theme": "Old Bangkok Street Food Discovery",
      "activities": [
        {
          "time": "09:00-12:00",
          "entity_id": "canonical_place_012",
          "entity_name": "Chatuchak Market",
          "description": "...",
          "why_recommended": "Perfect for budget + food focus",
          "estimated_cost": "$15",
          "duration_hours": 3
        }
      ],
      "daily_budget": "$45"
    }
  ]
}
```

**LLM Model:** Configurable (Gemini/OpenAI/DeepSeek)
**Output Tokens:** ~2,000-3,000
**Cost:** ~$0.006-0.012 (depending on provider)

---

### Phase 6: Validation

**Module:** [`src/rag/validator.py`](../../src/rag/validator.py)

**Purpose:** Check itinerary feasibility and quality

**Validation Checks:**

1. **Entity Verification:**
   - All entity_ids exist in retrieved entities
   - No hallucinated entities

2. **Timing Feasibility:**
   - Activities don't overlap
   - Travel time between locations reasonable (<2 hours)
   - Opening hours match suggested times

3. **Budget Consistency:**
   - Daily budget sum matches total budget
   - Budget aligns with user's budget level

4. **VIBE Alignment:**
   - Selected entities match user VIBE
   - No high-touristiness entities for low-touristiness user

5. **Completeness:**
   - All days have activities
   - Each day has 3-5 activities
   - No empty days

**Validation Result:**
```json
{
  "valid": true,
  "issues": [],
  "warnings": [
    "Day 2 has 6 activities (exceeds recommended 5)"
  ],
  "score": 9.5
}
```

**Retry Logic:**
- If validation fails (score < 7.0), retry generation with feedback
- Max 2 retries
- Cost: ~$0.001 per validation (small LLM call)

---

### Phase 7: Narrative Generation

**Module:** [`src/rag/narrative_generator.py`](../../src/rag/narrative_generator.py)

**Purpose:** Add helpful narrative, tips, and context

**Generated Narrative:**
```
TRAVEL TIPS:
- Download Grab app for easy transport (~$3-5 per ride)
- Carry cash - most street vendors don't accept cards
- Jay Fai has long queues (2-3 hours), arrive before 11am

BUDGET BREAKDOWN:
- Accommodation: $75 (5 nights hostel in Sukhumvit)
- Food: $125 (street food focused)
- Transport: $25 (BTS + occasional Grab)
- Activities: $50 (entry fees, tours)
- Total: $275 for 5 days

CULTURAL NOTES:
- Remove shoes before entering temples
- Dress modestly when visiting religious sites
- Tipping not expected but appreciated for great service

ALTERNATIVE SUGGESTIONS:
- If Chatuchak is too crowded, try Or Tor Kor Market nearby
- For nightlife, check out Khao San Road (touristy but fun)
```

**Cost:** ~$0.002 (small LLM call)

---

## Cost Tracking

**Built-in RAGCostTracker:** [`src/utils/rag_cost_tracker.py`](../../src/utils/rag_cost_tracker.py)

**Per-Phase Tracking:**
```
Phase 1 (Intent Parsing):    $0.0001
Phase 2 (Retrieval):          $0.0000 (FREE)
Phase 3 (Re-ranking):         $0.0000 (FREE)
Phase 4 (Context Building):   $0.0000 (FREE)
Phase 5 (Generation):         $0.0087
Phase 6 (Validation):         $0.0012
Phase 7 (Narrative):          $0.0003
────────────────────────────────────
Total Cost:                   $0.0103
```

**Budget Limits:**
- Set max budget per query: `RAGCostTracker(budget_limit=0.10)`
- Raises `BudgetExceededError` if exceeded
- Tracks cumulative costs across retries

---

## CLI Usage

### Generate Itinerary

```bash
# Basic query
./crawl.sh generate-itinerary -q "5 days Bangkok solo budget"

# Specific query with details
./crawl.sh generate-itinerary -q "3 days Phuket couple mid-range beach relaxation"

# With custom output format
./crawl.sh generate-itinerary -q "7 days Chiang Mai family culture" --format json

# Save to file
./crawl.sh generate-itinerary -q "4 days Pattaya party" --output itinerary.md
```

### View Output

```bash
# View saved itinerary
cat stage5_itineraries/itinerary_2026-01-29_14-23-45.json
```

---

## Performance & Costs

### Processing Time
- Phase 1-4: ~5 seconds (parsing, retrieval, re-ranking, context)
- Phase 5: ~30 seconds (LLM generation)
- Phase 6-7: ~10 seconds (validation, narrative)
- **Total:** ~45-60 seconds per itinerary

### Costs (Per Itinerary)

**Gemini 2.5 Flash Lite (Recommended):**
- Total: ~$0.01-0.015

**OpenAI GPT-4o-mini:**
- Total: ~$0.02-0.025

**DeepSeek Chat:**
- Total: ~$0.012-0.018

---

## Error Handling

### Common Errors

**1. Insufficient Data**
```
InsufficientDataError: Not enough entities for "Tokyo"
```
**Solution:**
- Run Stage 1-4 to crawl Tokyo videos first
- Or query different destination with more data

**2. Validation Failed**
```
ValidationError: Itinerary score 6.2/10 (threshold: 7.0)
Issues: Entity "ABC" not found, Day 2 timing overlap
```
**Solution:**
- Automatic retry with feedback (max 2 retries)
- Logs issues for review

**3. Budget Exceeded**
```
BudgetExceededError: Query cost $0.15 exceeds budget $0.10
```
**Solution:**
- Increase budget limit
- Use cheaper LLM provider (Gemini)

---

## Configuration

### Environment Variables

```bash
# LLM Provider
LLM_PROVIDER=gemini

# RAG Configuration
RAG_MAX_RETRIEVAL=50        # Max entities to retrieve
RAG_TOP_K=20                # Top entities for context
RAG_BUDGET_LIMIT=0.10       # Max cost per query (USD)
RAG_VALIDATION_THRESHOLD=7.0 # Min validation score

# Output
RAG_OUTPUT_DIR=stage5_itineraries/
RAG_DEFAULT_FORMAT=markdown
```

---

## Output Schema

**File:** `stage5_itineraries/itinerary_{timestamp}.json`

```typescript
{
  destination: string
  duration_days: number
  vibe_match_score: number       // 0-10
  user_intent: {
    vibe: {...}
    constraints: string[]
    preferences: string[]
  }
  days: Array<{
    day: number
    theme: string
    activities: Array<{
      time: string               // "09:00-12:00"
      entity_id: string
      entity_name: string
      entity_type: string
      description: string
      why_recommended: string    // Explains VIBE fit
      estimated_cost: string
      duration_hours: number
    }>
    daily_budget: string
    travel_between_locations: Array<{
      from: string
      to: string
      mode: string
      duration_minutes: number
      cost: string
    }>
  }>
  budget_estimate: {
    accommodation: string
    food: string
    transport: string
    activities: string
    total: string
  }
  travel_tips: string[]
  cultural_notes: string[]
  alternative_suggestions: string[]
  metadata: {
    generated_at: string
    total_cost: number           // USD
    phase_costs: {...}
    validation_score: number
    entities_retrieved: number
    entities_used: number
  }
}
```

---

## Best Practices

### 1. Use Specific Queries
```
❌ "Bangkok trip"
✅ "5 days Bangkok solo budget street food"
```

### 2. Include VIBE Indicators
- Budget level: "budget", "mid-range", "luxury"
- Pace: "relaxed", "moderate", "fast-paced"
- Style: "touristy", "off-the-beaten-path", "authentic"
- Focus: "food-focused", "adventure", "culture", "nightlife"

### 3. Monitor Costs
```bash
# Check cost reports
ls -lh stage5-costs/
cat stage5-costs/2026-01-29_14-23-45.json
```

### 4. Review Validation Scores
- Aim for scores ≥8.0
- Review issues if score <7.5

---

## References

- **Implementation:** [`src/rag/pipeline.py`](../../src/rag/pipeline.py)
- **Intent Parser:** [`src/rag/intent_parser.py`](../../src/rag/intent_parser.py)
- **Retriever:** [`src/rag/retriever.py`](../../src/rag/retriever.py)
- **Reranker:** [`src/rag/reranker.py`](../../src/rag/reranker.py)
- **Generator:** [`src/rag/itinerary_generator.py`](../../src/rag/itinerary_generator.py)
- **Validator:** [`src/rag/validator.py`](../../src/rag/validator.py)
- **CLI Command:** [`cli/generate_itinerary.py`](../../cli/generate_itinerary.py)
- **Cost Tracking:** [monitoring.md](../05-infrastructure/monitoring.md)
- **VIBE Framework:** [vibe-framework.md](../02-architecture/vibe-framework.md)

---

**Stage 5 complete!** You now have a complete RAG pipeline for personalized itinerary generation.
