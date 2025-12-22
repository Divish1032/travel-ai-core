# TravelAI Types, Profiles & Assumptions

A comprehensive guide to understanding all data types, profiles, and assumptions used in the TravelAI pipeline from Stage 1 to Stage 5.

---

## Table of Contents

1. [Overview](#overview)
2. [Entity Types](#entity-types)
3. [Traveler Profiles](#traveler-profiles)
4. [Budget Tiers](#budget-tiers)
5. [Sentiment Types](#sentiment-types)
6. [Query Intent Types](#query-intent-types)
7. [Time & Schedule Types](#time--schedule-types)
8. [Validation Types](#validation-types)
9. [Stage-by-Stage Process](#stage-by-stage-process)
10. [Key Assumptions](#key-assumptions)

---

## Overview

TravelAI transforms YouTube travel videos into structured, queryable travel intelligence through a 5-stage pipeline:

```
Stage 1: Crawl YouTube videos → Extract transcripts
Stage 2: Extract entities → Identify experiences
Stage 3: Deduplicate → Canonicalize → Build consensus
Stage 4: Generate embeddings → Index in vector DB
Stage 5: RAG pipeline → Generate itineraries
```

Each stage uses specific data types and makes certain assumptions about the data.

---

## Entity Types

### Definition
Entities are the core elements extracted from travel videos - places, activities, and services that travelers experience.

### Supported Entity Types

| Type | Description | Examples |
|------|-------------|----------|
| `destination` | Cities, regions, countries | Bangkok, Phuket, Thailand |
| `restaurant` | Eating establishments | Street food stalls, cafes, fine dining |
| `hotel` | Accommodation | Hotels, hostels, resorts, guesthouses |
| `activity` | Things to do | Snorkeling, temple visits, cooking classes |
| `attraction` | Tourist sites | Grand Palace, beaches, viewpoints |
| `transportation` | Getting around | Tuk-tuks, boats, buses, trains |
| `shopping` | Markets and stores | Night markets, malls, local shops |
| `unknown` | Unclassified entities | Fallback for unclear mentions |

### Assumptions
- **Single classification**: Each entity belongs to exactly one type
- **Type inference**: LLM determines type based on context
- **Priority order**: If ambiguous, uses: attraction > activity > restaurant > hotel
- **Unknown fallback**: When LLM is uncertain, marks as "unknown"

---

## Traveler Profiles

### Definition
Traveler profiles capture WHO is traveling and their characteristics, extracted from video content or user queries.

### 1. Traveler Type

| Type | Description | Query Examples |
|------|-------------|----------------|
| `solo` | Single traveler | "solo trip to Bangkok" |
| `couple` | Two travelers (romantic or friends) | "romantic getaway", "couple vacation" |
| `family` | Parents with children | "family-friendly", "with kids" |
| `group` | 3+ people | "group tour", "friends trip" |
| `unknown` | Cannot determine | Vague or missing information |

**Assumptions:**
- Default to `unknown` if not specified
- "Couple" includes both romantic partners and close friends
- "Group" is 3+ people; 2 people = couple

### 2. Age Range

| Range | Description | Inferred From |
|-------|-------------|---------------|
| `18-25` | Young adults, students | Mentions of backpacking, hostels, party scenes |
| `26-35` | Young professionals | Mid-range budgets, work-life balance mentions |
| `36-50` | Established adults | Higher budgets, comfort preferences |
| `50+` | Mature travelers | Luxury travel, relaxed pace, cultural focus |
| `unknown` | Cannot determine | No clear indicators |

**Assumptions:**
- Age inferred from travel style, budget, and activities mentioned
- Not always accurate (young person can afford luxury)
- Default to `unknown` if unclear

### 3. Budget Tier

| Tier | Daily Budget Range | Characteristics |
|------|-------------------|------------------|
| `budget` | $30-$50/day | Hostels, street food, free activities, public transport |
| `mid-range` | $50-$150/day | Hotels, local restaurants, paid tours, mix of transport |
| `luxury` | $150+/day | Resorts, fine dining, private tours, premium experiences |
| `unknown` | Unspecified | No cost information mentioned |

**Assumptions:**
- Budget tier based on mentioned costs and accommodation types
- Ranges are flexible and destination-dependent
- Bangkok budget ≠ Tokyo budget (purchasing power differs)
- Default to `mid-range` if user doesn't specify

### 4. Travel Style

| Style | Description | Indicators |
|-------|-------------|------------|
| `adventure` | Thrill-seeking, outdoors | Hiking, diving, extreme sports |
| `relaxation` | Rest and rejuvenation | Beaches, spas, slow pace |
| `cultural` | History and traditions | Temples, museums, local customs |
| `foodie` | Culinary experiences | Food markets, cooking classes, restaurants |
| `party` | Nightlife and social | Clubs, bars, beach parties |
| `nature` | Wildlife and scenery | National parks, eco-tours, wildlife |
| `shopping` | Retail therapy | Markets, malls, local crafts |
| `photography` | Photo opportunities | Scenic spots, sunrise/sunset locations |

**Assumptions:**
- Multiple styles can apply (e.g., "adventure + foodie")
- Extracted as list, not single value
- Missing styles don't mean "not interested" - just not mentioned

---

## Budget Tiers

### Daily Budget Ranges (USD)

These are **baseline assumptions** adjusted by destination purchasing power:

| Tier | Bangkok | Phuket | Tokyo | Paris |
|------|---------|--------|-------|-------|
| Budget | $30-50 | $40-60 | $60-80 | $70-90 |
| Mid-range | $50-150 | $80-180 | $100-200 | $120-250 |
| Luxury | $150+ | $200+ | $250+ | $300+ |

### Cost Tier (for entities)

Individual entities are tagged with cost tiers:

| Tier | Description | Examples |
|------|-------------|----------|
| `free` | No cost | Public beaches, temples (free entry), viewpoints |
| `budget` | Low cost | Street food ($2-5), local transport ($1-3) |
| `mid-range` | Moderate cost | Casual restaurants ($10-30), paid attractions ($5-15) |
| `luxury` | High cost | Fine dining ($50+), private tours ($100+) |
| `unknown` | Cost not mentioned | No pricing information available |

**Assumptions:**
- Cost tier inferred from mentioned prices or entity type
- "Free" doesn't always mean $0 (may have optional donations)
- Cost tier helps with budget filtering during retrieval

---

## Sentiment Types

### Definition
Sentiment captures how travelers FEEL about their experiences.

### Sentiment Values

| Sentiment | Description | Indicators |
|-----------|-------------|------------|
| `positive` | Good experience | "Amazing", "loved it", "highly recommend", 5-star |
| `negative` | Bad experience | "Disappointing", "avoid", "terrible", "waste of money" |
| `neutral` | No strong opinion | "It was okay", "nothing special", factual description |
| `mixed` | Both good and bad | "Great food but slow service", "beautiful but crowded" |

**Assumptions:**
- Default to `positive` for vlogs (creators highlight good experiences)
- Negative sentiment is rare in travel vlogs (selection bias)
- Mixed sentiment often reveals authentic experiences
- Sentiment affects ranking (positive experiences ranked higher)

---

## Query Intent Types

### Definition
When a user asks for an itinerary, we parse their natural language query into structured intent.

### Core Intent Components

| Component | Type | Required | Examples |
|-----------|------|----------|----------|
| `destination` | String | Yes | "Bangkok", "Thailand", "Southeast Asia" |
| `duration_days` | Integer (1-30) | Yes | "5 days", "weekend", "week" |
| `traveler_profile` | Profile object | Yes | "solo", "couple", "family" |
| `budget_per_day` | Dict or None | No | "$50 per day", "budget trip" |
| `dates` | Dict or None | No | "December 2025", "next month" |
| `must_include` | List[string] | No | "Grand Palace", "floating market" |
| `must_avoid` | List[string] | No | "spicy food", "crowded places" |
| `interests` | List[string] | No | "nightlife", "temples", "food" |
| `pace` | Enum | No | "relaxed", "balanced", "packed" |
| `flexibility` | Enum | No | "low", "medium", "high" |

### Pace Preference

| Pace | Description | Daily Activities |
|------|-------------|------------------|
| `relaxed` | Slow, restful | 1-2 major activities, lots of free time |
| `balanced` | Moderate pace | 3-4 activities, some downtime |
| `packed` | Busy, maximize experiences | 5-6 activities, tight schedule |

**Default**: `balanced`

### Flexibility Level

| Level | Description | Behavior |
|-------|-------------|----------|
| `low` | Stick to preferences | Only suggest exact matches to interests |
| `medium` | Some exploration | Mix of requested + similar experiences |
| `high` | Open to anything | Include diverse, unexpected recommendations |

**Default**: `medium`

**Assumptions:**
- Users rarely specify all fields (only destination + duration are required)
- Missing fields filled with intelligent defaults
- LLM extracts intent from natural language ("budget party trip" → budget tier + party interest)

---

## Time & Schedule Types

### Time Periods (for day structure)

| Period | Time Range | Typical Activities |
|--------|------------|-------------------|
| `morning` | 6:00 - 12:00 | Breakfast, temples, markets, tours |
| `afternoon` | 12:00 - 18:00 | Lunch, museums, activities, shopping |
| `evening` | 18:00 - 22:00 | Dinner, sunset spots, shows |
| `night` | 22:00 - 02:00 | Nightlife, bars, clubs (optional) |

**Assumptions:**
- Each day has 4 time slots
- Not all slots must be filled (relaxed pace may skip night)
- Morning start time varies by travel style (party: 10am, cultural: 7am)
- Night slot only for party/nightlife interests

### Activity Duration Estimates

| Entity Type | Assumed Duration | Notes |
|-------------|------------------|-------|
| Restaurant | 1-2 hours | Includes travel time |
| Attraction | 2-4 hours | Depends on size |
| Activity | 2-6 hours | Varies widely (tour vs. quick visit) |
| Hotel | Evening/night | Check-in/out logistics |
| Shopping | 1-3 hours | Flexible |
| Transportation | Variable | Between activities |

**Assumptions:**
- Durations are estimates for scheduling
- Activities can overlap time periods
- Buffer time included for travel between locations

---

## Validation Types

### Definition
After generating an itinerary, we validate it for quality and accuracy.

### Validation Categories

| Type | Checks For | Severity |
|------|-----------|----------|
| `HALLUCINATION` | Entity IDs not in retrieved context | ERROR |
| `LOGISTICS` | Impossible schedules (too many activities) | ERROR |
| `BUDGET` | Exceeds daily budget limits | WARNING |
| `TIMING` | Activities at wrong time of day | WARNING |
| `FEASIBILITY` | Geographic issues (too far apart) | WARNING |
| `DATA_QUALITY` | Low confidence entities used | INFO |

### Severity Levels

| Severity | Action | Description |
|----------|--------|-------------|
| `ERROR` | Retry generation | Critical issue, unusable itinerary |
| `WARNING` | Proceed with caution | Potential issue, user should know |
| `INFO` | No action | Informational, doesn't affect quality |

### Validation Score

- **Range**: 0.0 to 1.0
- **Threshold**: 0.7 (below triggers retry)
- **Calculation**: `1.0 - (errors * 0.5 + warnings * 0.2)`
- **Max Retries**: 2 attempts

**Assumptions:**
- Hallucinations are the worst error (invalidates entire itinerary)
- Budget violations are acceptable if slight (10% over)
- Low validation score = regenerate with stricter constraints
- After 2 retries, return best-effort itinerary with warnings

---

## Stage-by-Stage Process

### Stage 1: YouTube Crawling

**Input**: YouTube video URL or search query

**Process**:
1. Download video metadata (title, author, views, etc.)
2. Extract audio
3. Transcribe using Whisper AI (auto-detect language)
4. Store transcript with timestamps

**Output**:
- `stage1-crawl/{video_id}.jsonl` (video metadata + transcript)
- Stored in S3

**Assumptions**:
- Transcripts are 90%+ accurate (Whisper quality)
- Language detection is correct
- Videos are travel-related (not verified until Stage 2)

---

### Stage 2: Entity Extraction

**Input**: Video transcript from Stage 1

**Process**:
1. Classify video type (short <35min vs long >=35min)
2. Extract traveler profile (type, age, budget, style)
3. Extract entities:
   - **Short videos**: Single-pass extraction
   - **Long videos**: Chunked extraction (5min chunks, 1min overlap)
4. Deduplicate entities within video
5. Calculate confidence scores
6. Assess extraction quality

**Output**:
- `stage2-extracted/{video_id}.jsonl` (profile + entities)
- Stored in S3

**Assumptions**:
- LLM can accurately identify entity types
- Chunking doesn't miss entities (overlap prevents this)
- Confidence scores reflect actual quality
- Traveler profile applies to entire video

**Entity Quality Assessment**:
- **High**: 80%+ entities with confidence >0.7
- **Medium**: 50-80% good entities
- **Low**: <50% good entities

---

### Stage 3: Deduplication & Canonicalization

**Input**: All extracted entities from Stage 2 (across all videos)

**Process**:
1. **Deduplication** (4-tier matching):
   - Tier 1: Exact name match (case-insensitive)
   - Tier 2: Fuzzy match (90% similarity, handles typos)
   - Tier 3: Semantic match (embedding similarity >0.85)
   - Tier 4: Location proximity (same coords, different names)

2. **Canonicalization**:
   - Group duplicates
   - Select canonical name (most common variant)
   - Merge all experiences
   - Geocode location (lat/lon)

3. **Consensus Building**:
   - Average sentiment across all mentions
   - Count mentions per profile type
   - Extract common themes (LLM)
   - Calculate aggregate confidence

**Output**:
- `stage3-canonical/entities_all.jsonl` (canonical entities)
- `stage3-canonical/by_city/{city}.jsonl` (grouped by location)
- `stage3-canonical/by_type/{type}.jsonl` (grouped by entity type)
- Stored in S3

**Assumptions**:
- Same-named entities in same city are the same place
- Geocoding provides accurate coordinates (90% accurate)
- Consensus sentiment is representative
- More mentions = higher quality entity

**Deduplication Example**:
```
Video 1: "Chatuchak Market" (exact match)
Video 2: "Chatuchak Weekend Market" (fuzzy match)
Video 3: "JJ Market" (semantic match - local nickname)
→ Canonical: "Chatuchak Weekend Market" (most descriptive)
```

---

### Stage 4: Vector Embeddings

**Input**: Canonical entities from Stage 3

**Process**:
1. Generate embeddings using Alibaba-NLP/gte-large (1024-dim)
2. Create 3 types of embeddings per entity:
   - **Entity**: General description for semantic search
   - **Profile-specific**: Customized for each traveler profile
   - **Experience**: Individual traveler experiences
3. Index in ChromaDB (3 collections)
4. Add metadata for filtering (city, type, cost, etc.)
5. Track provenance (map embeddings → source videos)

**Output**:
- ChromaDB collections: `entities`, `profile_consensus`, `experiences`
- `metadata/embedding_provenance.jsonl` (provenance mapping)
- Local storage in `./chroma_data/` or cloud deployment

**Assumptions**:
- Embedding model quality is sufficient (better than OpenAI small)
- 1024 dimensions capture semantic meaning
- Cosine similarity is appropriate metric
- Profile-specific embeddings improve personalization

**Embedding Strategies**:

1. **Entity Strategy**:
   - Text: `{name}, {type} in {city}. {description}. Popular with {profiles}. Cost: {tier}.`
   - Use: General semantic search

2. **Profile Consensus Strategy**:
   - Text: `{name} for {profile}. {profile_specific_themes}. {profile_consensus_description}.`
   - Use: Personalized recommendations

3. **Experience Strategy**:
   - Text: Individual traveler experience descriptions
   - Use: Detailed exploration, finding specific experiences

---

### Stage 5: RAG Itinerary Generation

**Input**: Natural language query (e.g., "5 days Bangkok solo budget party")

**Process** (7 phases):

#### Phase 1: Intent Parsing
- Extract destination, duration, budget, traveler profile
- Parse must-include, must-avoid, interests
- Fill missing fields with defaults
- Validate intent structure

**Assumptions**:
- LLM can parse natural language queries accurately
- Missing fields can use intelligent defaults
- Duration is in days (not weeks/months)

#### Phase 2: Retrieval
- Build search query from intent
- Semantic search in ChromaDB (profile-specific collection)
- Apply metadata filters (city, type, budget tier)
- Retrieve top-K candidates (K=20 default)

**Assumptions**:
- Profile-specific embeddings improve relevance
- Top-20 entities contain enough diversity
- Metadata filters are accurate

#### Phase 3: Re-ranking
- LLM scores each candidate for personalization
- Considers: budget match, interest alignment, diversity
- Boosts unique experiences
- Penalizes redundancy (similar entities)
- Returns top-N (N=12) for context

**Assumptions**:
- LLM ranking aligns with user preferences
- Diversity improves itinerary quality
- 12 entities are enough for multi-day itinerary

#### Phase 4: Context Building
- Group entities by priority (must-include > high-score > diverse)
- Build rich context with:
  - Entity details (name, type, location, cost, description)
  - Consensus data (themes, sentiment, traveler tips)
  - Provenance (source videos)
- Fit within token budget (3000 tokens)

**Assumptions**:
- 3000 tokens are sufficient for generation
- Richer context = better itineraries
- Provenance adds credibility

#### Phase 5: Itinerary Generation
- LLM generates day-by-day itinerary
- Structured output: days → time slots → activities
- Each activity references a context entity ID
- Includes: activity description, estimated cost, practical tips

**Assumptions**:
- LLM follows structured format
- Entity IDs match context (no hallucinations)
- Activity timing is realistic
- Daily budgets are reasonable

#### Phase 6: Validation
- Check for hallucinations (unknown entity IDs)
- Validate logistics (schedule feasibility)
- Check budget compliance
- Verify geographic sensibility (not too spread out)
- Calculate validation score

**If score < 0.7**: Regenerate with stricter prompt (max 2 retries)

**Assumptions**:
- Validation can catch most quality issues
- Regeneration improves quality
- After 2 retries, accept best-effort result

#### Phase 7: Narrative Generation (Optional)
- Generate engaging introduction
- Create day narratives (storytelling)
- Write conclusion with travel tips
- Add highlights and warnings

**Can be skipped** for faster generation (--skip-narrative)

**Assumptions**:
- Narrative adds value for end users
- Skipping narrative doesn't affect itinerary quality
- LLM can write engaging travel content

**Output**:
- Formatted itinerary (Markdown, HTML, JSON, or text)
- Metadata: cost breakdown, validation score, entities used
- Can be cached for duplicate queries

**Cost Tracking**:
- Intent parsing: ~$0.0001
- Re-ranking: ~$0.0015
- Generation: ~$0.0025
- Validation: ~$0.0008 (per attempt)
- Narrative: ~$0.0035 (if enabled)
- **Total**: ~$0.005-0.008 per itinerary

**Time**:
- Without narrative: 35-50 seconds
- With narrative: 50-70 seconds

---

## Key Assumptions

### Data Quality Assumptions

1. **YouTube transcripts are accurate** (90%+ from Whisper)
2. **LLM extractions are reliable** (confidence scores indicate quality)
3. **Geocoding is accurate** (90% with Nominatim + Google fallback)
4. **Entity deduplication doesn't merge different places** (tiered matching prevents this)
5. **Consensus sentiment represents reality** (more mentions = more accurate)

### User Behavior Assumptions

1. **Users provide meaningful queries** (not random/spam)
2. **Destination is a known city/region** (in our dataset)
3. **Duration is 1-30 days** (not months/years)
4. **Budget is reasonable** (not $1/day or $10,000/day)
5. **Users tolerate 30-60 second generation time**

### LLM Assumptions

1. **LLMs follow structured output formats** (Pydantic validation)
2. **LLMs don't hallucinate entity IDs** (validation catches this)
3. **LLM quality is consistent** (Gemini/DeepSeek reliability)
4. **Fallback LLMs work if primary fails** (redundancy)
5. **Cost optimization doesn't harm quality** (DeepSeek vs OpenAI)

### System Assumptions

1. **S3 is reliable** (AWS 99.99% uptime)
2. **ChromaDB handles 10K+ vectors** (tested up to 100K)
3. **Embedding model runs on CPU** (no GPU required)
4. **Network latency is acceptable** (<500ms for API calls)
5. **Concurrent requests don't degrade performance** (within limits)

### Business Logic Assumptions

1. **Travel styles can be multi-valued** (adventure + foodie)
2. **Budget tiers are destination-dependent** (Bangkok ≠ Paris)
3. **Free time is valuable** (relaxed pace > packed)
4. **Diversity improves itineraries** (not 5 temples in one day)
5. **Authentic experiences matter** (real traveler reviews > marketing)

### Edge Cases & Fallbacks

1. **Unknown destination** → Inform user, suggest alternatives
2. **Insufficient data** → Generate with warnings, lower confidence
3. **Budget impossible** → Warn user, suggest budget increase
4. **Conflicting constraints** → Prioritize must-include > budget > interests
5. **LLM failure** → Retry with fallback model, max 3 attempts

---

## Profile Combination Examples

### Understanding Profile Identifiers

Profiles are combined as: `{traveler_type}_{travel_style}_{budget_tier}`

Examples:
- `solo_all_budget` - Solo traveler, any style, budget tier
- `couple_adventure_mid-range` - Couple, adventure style, mid-range
- `family_cultural_luxury` - Family, cultural focus, luxury tier
- `solo_party_budget` - Solo traveler, party style, budget

**Special value**: `all` means "any" or "not specified"

### Common Profile Combinations

| Query | Profile Identifier | Characteristics |
|-------|-------------------|-----------------|
| "solo backpacker Bangkok" | `solo_all_budget` | Young, hostels, street food, social |
| "couple honeymoon Phuket" | `couple_relaxation_luxury` | Romance, resorts, fine dining, privacy |
| "family Disney Tokyo" | `family_all_mid-range` | Kid-friendly, hotels, flexible schedule |
| "group party Bali" | `group_party_budget` | Nightlife, shared rooms, social activities |
| "retirement cruise" | `couple_relaxation_luxury` | 50+, slow pace, comfort, culture |
| "digital nomad Chiang Mai" | `solo_cultural_mid-range` | Coworking, cafes, local immersion |

---

## Cost Assumptions & Budgeting

### Entity-Level Costs

When LLM extracts costs from videos:
- **Exact mention**: "$15 pad thai" → stored as-is
- **Range**: "$10-20 restaurant" → stored as range
- **Free**: "free temple" → cost_tier = "free"
- **No mention**: cost_tier = "unknown"

### Daily Budget Breakdown

Typical mid-range budget ($100/day) allocation:
- Accommodation: 35% ($35)
- Food: 30% ($30)
- Activities: 20% ($20)
- Transport: 10% ($10)
- Shopping/misc: 5% ($5)

**Assumptions**:
- Budget includes everything (meals, transport, activities, accommodation)
- Not including flights or pre-trip costs
- Flexible allocation (foodie trip may spend 50% on food)

### Currency Handling

- All costs normalized to USD
- Exchange rates not real-time (assumed stable)
- Local currency mentions converted using LLM knowledge
- "$", "฿", "¥", "€" symbols recognized

---

## Data Freshness & Updates

### Assumptions on Temporal Validity

| Data Type | Freshness | Assumption |
|-----------|-----------|------------|
| Restaurant | 1-2 years | Menu/quality relatively stable |
| Hotel | 1-3 years | Property doesn't change dramatically |
| Attraction | 3-5 years | Landmarks are permanent |
| Activity | 1-2 years | Tour operators may change |
| Prices | 6-12 months | Inflation, seasonal variation |
| Reviews | 1-2 years | Recent enough to be relevant |

**Important**: TravelAI doesn't automatically update data. Videos crawled in 2024 reflect 2024 experiences.

**Recommendation**: Re-crawl popular destinations annually.

---

## Limitations & Known Issues

### Current Limitations

1. **Geographic coverage**: Only locations in crawled videos
2. **Language bias**: Primarily English content (Whisper translates, but biased)
3. **Temporal bias**: Recent videos over-represented
4. **Creator bias**: Popular vloggers over-represented
5. **Seasonal bias**: Some destinations only covered in peak season

### Quality Variability

- **High confidence** (>0.8): Very reliable, use without hesitation
- **Medium confidence** (0.5-0.8): Generally reliable, minor issues possible
- **Low confidence** (<0.5): Use with caution, validate with user

### Entity Extraction Challenges

- **Ambiguous names**: "Central" (Central World mall or central area?)
- **Language mixing**: "Chatuchak" vs "จตุจักร" (same market, different script)
- **Typos**: "Pattya" instead of "Pattaya"
- **Nicknames**: "JJ Market" for Chatuchak

**Mitigation**: Deduplication + geocoding catches most issues

---

## Future Enhancements

### Planned Improvements

1. **Real-time pricing**: Integration with booking APIs
2. **Seasonality**: Adjust recommendations by travel month
3. **User feedback loop**: Collect ratings on generated itineraries
4. **Multi-destination**: Support for region tours (Thailand + Vietnam)
5. **Collaborative filtering**: "Users like you also visited..."

### Potential New Types

- `visa_requirements`: Visa information per nationality
- `health_safety`: Medical, safety, scam warnings
- `environmental_impact`: Eco-friendliness ratings
- `accessibility`: Wheelchair access, disability-friendly

---

## Glossary

| Term | Definition |
|------|------------|
| **Entity** | A place, activity, or service extracted from videos |
| **Canonical entity** | Deduplicated, merged representation of an entity |
| **Profile** | Traveler characteristics (type, budget, style) |
| **Intent** | Structured representation of user query |
| **Context** | Selected entities used for itinerary generation |
| **Retrieval** | Finding relevant entities from vector DB |
| **Re-ranking** | LLM-based personalization of candidates |
| **Validation** | Quality checking of generated itineraries |
| **Hallucination** | LLM inventing entities not in context |
| **Provenance** | Tracing data back to source videos |
| **Consensus** | Aggregate sentiment/rating across videos |
| **Embedding** | Vector representation for semantic search |
| **RAG** | Retrieval-Augmented Generation |

---

## Summary

TravelAI makes deliberate assumptions to balance:
- **Quality** vs **Coverage**: Require minimum confidence scores
- **Accuracy** vs **Speed**: Use efficient but capable LLMs
- **Cost** vs **Quality**: Optimize for budget without sacrificing much
- **Simplicity** vs **Flexibility**: Support common cases well, edge cases gracefully

These assumptions are encoded in:
- **Data schemas** (Pydantic models in `src/utils/schemas.py`)
- **Pipeline logic** (Stage 1-5 implementations)
- **Validation rules** (Confidence thresholds, quality checks)
- **Default values** (Budget ranges, profile combinations)

Understanding these assumptions helps you:
1. Interpret generated itineraries correctly
2. Debug quality issues effectively
3. Extend the system thoughtfully
4. Set user expectations appropriately

For implementation details, see source code and stage-specific documentation.

---

*Last Updated: December 2024*
*TravelAI Version: 1.0*
