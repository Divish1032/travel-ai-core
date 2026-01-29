# Stage 2: Entity Extraction

Stage 2 extracts structured travel entities from video transcripts using LLM-powered extraction with semantic chunking and fuzzy deduplication.

**Implementation:** [`src/processors/stage2_extractor.py`](../../src/processors/stage2_extractor.py), [`src/processors/extraction_prompts.py`](../../src/processors/extraction_prompts.py)

---

## Overview

### Purpose
Transform unstructured video transcripts into structured travel entities (places, restaurants, hotels, activities) with subjective experience data.

### Inputs
- Stage 1 transcripts with metadata
- Video metadata (title, duration, language)

### Outputs
- Traveler profile (VIBE dimensions)
- Extracted entities with sentiment and context
- Fuzzy-deduplicated entities per video

### Storage
- **S3 Path:** `s3://{bucket}/stage2_entities/{video_id}.json`
- **File Size:** ~45 KB per video

---

## Processing Pipeline

### 1. Transcript Loading & Validation

**Input Format:**
```json
{
  "video_id": "youtube_UEDeptPVNQA",
  "transcript": "Full transcript text...",
  "transcript_segments": [
    {"text": "...", "start": 0.0, "duration": 5.2}
  ],
  "duration_seconds": 895,
  "language": "en"
}
```

**Validation:**
- Check transcript is not empty
- Verify transcript segments exist
- Validate duration and language fields

---

### 2. Semantic Chunking (NOT Fixed-Time)

**Function:** `split_transcript_semantically()`

TravelAI uses **semantic chunking** based on topic boundary detection, not fixed-time windows.

**Key Improvement:**
Fixed-time chunking (e.g., every 5 minutes) often splits entities mid-sentence or breaks coherent sections. Semantic chunking identifies natural topic shifts.

#### Topic Shift Detection Patterns

**Day/Time Markers:**
- `day 1`, `day 2`, `first day`, `second day`
- `next day`, `the following day`, `the next morning`
- `in the morning`, `in the afternoon`, `in the evening`

**Location Transitions:**
- `now let's go to`, `heading to`, `next stop`
- `moving on to`, `next up`, `off to`
- `we arrived at`, `we got to`, `we reached`
- `after that`, `from there`, `then we`

**Topic Markers:**
- `for food`, `for accommodation`, `for activities`
- `when it comes to`, `speaking of`, `talking about`
- `one thing to know`, `tip number`, `my top tip`

**Section Markers:**
- `okay so`, `alright so`, `so anyway`
- `let me show you`, `let me tell you`

#### Chunking Parameters

```python
min_chunk_duration_seconds: 120   # Minimum 2 minutes
max_chunk_duration_seconds: 420   # Maximum 7 minutes
target_chunk_duration_seconds: 300 # Target 5 minutes
overlap_segments: 3                # 3 segments overlap between chunks
```

**Algorithm:**
1. Iterate through transcript segments
2. Check each segment for topic shift patterns
3. If topic shift detected AND chunk >= min_duration:
   - Finalize current chunk
   - Start new chunk (with overlap)
4. If chunk reaches max_duration:
   - Force split even without topic shift
5. If no topic shifts in entire video:
   - Fall back to time-based splitting

**Example:**
```
Transcript: "Today we're exploring Bangkok. [5 minutes]...
             Day 2, we headed to Phuket. [6 minutes]...
             On our third day, we visited temples. [4 minutes]"

Chunks:
- Chunk 1: "Today we're exploring Bangkok..." (5 min)
  └─ Split at "Day 2" topic shift
- Chunk 2: "Day 2, we headed to Phuket..." (6 min)
  └─ Split at "On our third day" topic shift
- Chunk 3: "On our third day, we visited temples..." (4 min)
```

**Benefits:**
- Entities stay within semantic context
- Better traveler profile inference per segment
- Reduced cross-chunk duplicate entities
- More accurate sentiment analysis

---

### 3. LLM Entity Extraction

**LLM Provider:** Configurable (Gemini, OpenAI, DeepSeek)
**Model:** `gemini-2.5-flash-lite` (default, cheapest)
**Prompt Template:** [`src/processors/extraction_prompts.py`](../../src/processors/extraction_prompts.py)

#### Extraction Strategy

**Short Videos (< 20 minutes):**
- **Single-Pass Extraction:** Process entire transcript in one LLM call
- **Prompt:** `SINGLE_PASS_PROMPT`

**Long Videos (>= 20 minutes):**
- **Hierarchical Extraction:**
  1. Split transcript into semantic chunks
  2. Extract entities from each chunk separately
  3. Extract traveler profile from first chunk
  4. Merge results and deduplicate across chunks
- **Prompts:** `HIERARCHICAL_CHUNK_PROMPT` + `HIERARCHICAL_MERGE_PROMPT`

#### Entity Types Extracted

**Valid Entity Types:**
- `destination` - Cities, regions, neighborhoods, areas
- `restaurant` - Restaurants, cafes, street food stalls
- `hotel` - Hotels, hostels, guesthouses, resorts
- `activity` - Tours, experiences, adventure activities
- `attraction` - Museums, temples, parks, monuments
- `transportation` - Specific transport services (e.g., Airport Rail Link)
- `shopping` - Markets, malls, shops
- `unknown` - Unclear category

**Entity Fields:**
```json
{
  "entity_name": "Grand Palace",
  "entity_type": "attraction",
  "sentiment": "positive",
  "context": "An absolute must-see with intricate temple details",
  "vibe": {
    "touristiness": 9,
    "adventure_level": 2,
    "budget_level": 6,
    "pace": "slow"
  },
  "location": {
    "city": "Bangkok",
    "country": "Thailand",
    "neighborhood": "Phra Nakhon"
  },
  "mentions": 3,
  "timestamp_start": 135.0,
  "confidence_score": 0.94
}
```

#### Extraction Guardrails

**Critical Rule:** Extract **subjective experiences**, NOT objective facts.

**❌ DO NOT EXTRACT:**
- **Apps & Websites:** Grab, Bolt, Booking.com, Agoda, 12goasia
- **Packing Items:** Travel adapter, charger, SIM card, sunscreen
- **Generic Chains:** 7-Eleven, Starbucks (unless notable landmark)
- **Generic Transport:** "taxi", "bus", "flight" (only specific services like "Airport Rail Link")
- **Services:** Visa service, insurance, currency exchange
- **Travel Tips:** "bring cash", "book in advance", "download app"

**✅ DO EXTRACT:**
- **Specific Places:** "Chatuchak Market", "Jay Fai Restaurant"
- **Experiences:** "Phi Phi Island boat tour", "Thai cooking class"
- **Subjective Context:** "Amazing views", "long queues", "worth the wait"
- **Vibe Indicators:** Budget level, touristiness, pace

**Why This Matters:**
- **Stage 2 Focus:** Subjective experiences from travelers
- **Stage 3 Focus:** Objective facts via geocoding and enrichment
- **Prevents Data Pollution:** No apps, packing lists, or generic advice

**Example:**
```
❌ Extracted: "Grab app" → WRONG (app, not a place)
✅ Extracted: "Jay Fai" → CORRECT (restaurant with experience context)

❌ Extracted: "bring sunscreen" → WRONG (packing tip)
✅ Extracted: "Patong Beach" → CORRECT (place with experience context)
```

---

### 4. Traveler Profile Inference (VIBE Framework)

**Framework:** 5-dimensional preference system

**VIBE Dimensions:**

1. **Touristiness** (0-10)
   - 0: Completely off-the-beaten-path
   - 5: Balanced (some popular, some hidden gems)
   - 10: All major tourist attractions

2. **Adventure Level** (0-10)
   - 0: Relaxation-only
   - 5: Mix of relaxation and adventure
   - 10: Extreme adventure activities

3. **Budget Level** (1-10)
   - 1-3: Budget traveler (hostels, street food)
   - 4-6: Mid-range (3-star hotels, casual dining)
   - 7-10: Luxury (5-star hotels, fine dining)

4. **Pace** (string)
   - `slow`: 1-2 activities per day
   - `moderate`: 3-4 activities per day
   - `fast`: 5+ activities per day

5. **Food Focus** (0-10)
   - 0: Food is just fuel
   - 5: Normal interest in food
   - 10: Food-centric trip

**Inference Method:**
- LLM analyzes transcript content
- Identifies mentioned entities and traveler behavior
- Assigns VIBE dimensions based on patterns
- Returns confidence score (0.0-1.0)

**Example Output:**
```json
{
  "traveler_profile": {
    "touristiness": 6,
    "adventure_level": 4,
    "budget_level": 5,
    "pace": "moderate",
    "food_focus": 8,
    "confidence": 0.82
  }
}
```

**See:** [vibe-framework.md](../02-architecture/vibe-framework.md)

---

### 5. Fuzzy Deduplication (Within Video)

**Function:** `merge_duplicate_entities()`

After extraction, entities are deduplicated within the same video using fuzzy string matching.

#### Deduplication Algorithm

**Strategy:** Union-Find clustering with fuzzy similarity

**Similarity Threshold:** **0.75 (75%)**

**Similarity Calculation:**
```python
def are_entities_similar(e1, e2, similarity_threshold=0.75):
    # 1. Type check: Same entity type required
    # 2. Name similarity: Fuzzy match on entity names
    # 3. Location match: If both have locations, compare cities
    # 4. Weighted average: name_sim * 0.7 + location_sim * 0.3
    # 5. Return: similarity >= threshold
```

**Examples:**

| Entity 1 | Entity 2 | Similarity | Merged? |
|----------|----------|------------|---------|
| "Patong Beach" | "Patong" | 0.82 | ✅ Yes |
| "Big Buddha" | "The Big Buddha Temple" | 0.88 | ✅ Yes |
| "Wat Chalong" | "Wat Chalong Temple" | 0.91 | ✅ Yes |
| "Chatuchak Market" | "JJ Market" | 0.45 | ❌ No |
| "Phi Phi Island" | "Phuket Island" | 0.52 | ❌ No |

#### Merging Strategy

When duplicates are found:
1. **Combine contexts:** Merge all context strings
2. **Sum mentions:** Add up mention counts
3. **Average scores:** Average confidence scores
4. **Keep earliest timestamp:** Preserve first mention timestamp
5. **Merge VIBE:** Average VIBE dimensions

**Example:**
```json
Before:
[
  {"entity_name": "Grand Palace", "mentions": 2, "context": "Must-see attraction"},
  {"entity_name": "The Grand Palace", "mentions": 1, "context": "Iconic landmark"}
]

After:
[
  {
    "entity_name": "Grand Palace",
    "mentions": 3,
    "context": "Must-see attraction. Iconic landmark.",
    "confidence_score": 0.93
  }
]
```

#### Deduplication Statistics

**Typical Results:**
- Raw entities extracted: 80-120 per video
- After deduplication: 60-80 per video
- **Reduction:** 20-30% duplicates removed

---

### 6. Thai Place Name Correction

**Problem:** Whisper often mis-transcribes Thai place names

**Solution:** Dictionary-based + fuzzy correction

**Corrector:** `TranscriptCorrector` from [`src/processors/transcript_corrector.py`](../../src/processors/transcript_corrector.py)

**Correction Types:**

1. **Dictionary Corrections:** Exact matches
   - "Pataya" → "Pattaya"
   - "Chalong Wat" → "Wat Chalong"

2. **Pattern Corrections:** Common patterns
   - "Bangkok Suvarnabhumi" → "Suvarnabhumi Airport"
   - Proper spacing for Thai names

3. **Fuzzy Corrections:** Similarity matching (85% threshold)
   - "Chatuchak Market" vs "Chatuchack Market"
   - "Phi Phi Island" vs "Pi Pi Island"

**Timing:**
- Stage 1: Basic corrections (dictionary + fuzzy only)
- Stage 2: Additional corrections if needed
- **LLM Proofreading:** Disabled at Stage 2 (too slow + expensive)

**Statistics:**
- Typical: 5-20 corrections per video
- Most common: Thai place names, temple names

---

## CLI Usage

### Process Stage 2

```bash
# Process all pending videos
./crawl.sh process-stage2

# Process specific limit
./crawl.sh process-stage2 --limit 10

# Process with specific LLM provider
./crawl.sh process-stage2 --limit 10 --provider gemini
```

### View Extracted Entities

```bash
# View entities for a specific video
./crawl.sh view-stage2 youtube_UEDeptPVNQA

# View with detailed metadata
./crawl.sh view-stage2 youtube_UEDeptPVNQA --verbose
```

### Check Status

```bash
./crawl.sh status
```

---

## Performance & Costs

### Processing Time
- **Short video (< 20 min):** ~30-60 seconds
- **Long video (>= 20 min):** ~2-5 minutes
- **Bottleneck:** LLM API calls

### LLM Token Usage

**Per Video:**
- Input tokens: ~3,000-5,000 (transcript + prompt)
- Output tokens: ~1,500-2,500 (entities JSON)
- **Total:** ~4,500-7,500 tokens per video

### Costs (Per Video)

**Gemini 2.5 Flash Lite (Recommended):**
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens
- **Per video:** ~$0.002-0.005

**OpenAI GPT-4o-mini:**
- Input: $0.150 per 1M tokens
- Output: $0.600 per 1M tokens
- **Per video:** ~$0.004-0.010

**DeepSeek Chat:**
- Input: $0.14 per 1M tokens
- Output: $0.28 per 1M tokens
- **Per video:** ~$0.003-0.007

**Recommendation:** Use Gemini for best cost/quality balance

### Batch Processing

**100 videos:**
- **Time:** ~1-2 hours
- **Cost:** ~$0.25-0.50 (Gemini)

---

## Error Handling

### Common Errors

**1. LLM API Rate Limit**
```
RateLimitError: Exceeded requests per minute
```
**Solution:**
- Automatic exponential backoff retry
- Max 3 retries per video
- Falls back to next provider if configured

**2. Invalid Entity Type**
```
ValidationError: entity_type 'food' not allowed
```
**Solution:**
- Automatic type normalization
- Maps invalid types to valid schema types
- Logs warning for review

**3. Empty Transcript**
```
ValueError: Transcript is empty or too short
```
**Solution:**
- Skips video gracefully
- Marks as failed in metadata tracker
- Logs reason for review

**4. JSON Parsing Error**
```
JSONDecodeError: LLM returned invalid JSON
```
**Solution:**
- Retries with clarified prompt
- Falls back to simpler extraction
- Logs full response for debugging

### Retry Logic
- **LLM API Failures:** 3 retries with exponential backoff (1s, 2s, 4s)
- **Parsing Errors:** 2 retries with prompt clarification
- **Network Errors:** 3 retries with 5-second delay

---

## Configuration

### Environment Variables

```bash
# LLM Provider Selection
LLM_PROVIDER=gemini          # Options: gemini, openai, deepseek

# Gemini Configuration
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

# OpenAI Configuration
OPENAI_API_KEY=your_key_here

# DeepSeek Configuration
DEEPSEEK_API_KEY=your_key_here
DEEPSEEK_MODEL=deepseek-chat

# Processing Options
USE_SEMANTIC_CHUNKING=true   # Enable semantic chunking (recommended)
USE_FUZZY_DEDUP=true         # Enable fuzzy deduplication (recommended)
FUZZY_THRESHOLD=0.75         # Fuzzy similarity threshold (0.0-1.0)
```

### Advanced Options

**Semantic Chunking Parameters:**
Edit `src/processors/stage2_extractor.py`:
```python
split_transcript_semantically(
    transcript,
    min_chunk_duration_seconds=120,   # Minimum 2 minutes
    max_chunk_duration_seconds=420,   # Maximum 7 minutes
    target_chunk_duration_seconds=300, # Target 5 minutes
    overlap_segments=3                 # Overlap 3 segments
)
```

**Fuzzy Deduplication Threshold:**
```python
merge_duplicate_entities(
    entities,
    use_fuzzy=True,
    similarity_threshold=0.75  # 75% similarity
)
```

---

## Quality Assurance

### Entity Quality Indicators

1. **Confidence Score:** 0.8+ indicates high-quality extraction
2. **Mention Count:** Higher is better (entity mentioned multiple times)
3. **Context Length:** Longer context = more detailed experience
4. **VIBE Completeness:** All 5 dimensions should be present

### Manual Verification

```bash
# View entities for review
./crawl.sh view-stage2 youtube_UEDeptPVNQA

# Check entity types distribution
./crawl.sh stage2-stats
```

---

## Best Practices

### 1. Use Semantic Chunking
- **Always enabled by default**
- Better than fixed-time chunking
- Preserves semantic context

### 2. Enable Fuzzy Deduplication
- **Always enabled by default**
- Reduces duplicates by 20-30%
- Uses reasonable 75% threshold

### 3. Choose Right LLM Provider
- **Gemini:** Best cost/quality balance (recommended)
- **DeepSeek:** Good alternative
- **OpenAI:** Highest quality, highest cost

### 4. Batch Processing
- Process in batches of 10-50 videos
- Monitor costs with built-in tracking
- Use `--limit` flag for testing

### 5. Monitor Extraction Quality
- Check confidence scores
- Review entity type distribution
- Verify traveler profiles make sense

---

## Troubleshooting

### High Costs

**Check:**
1. Are you using Gemini (cheapest)?
2. Are videos excessively long (>30 min)?
3. Are you re-processing already-completed videos?

**Solution:**
- Switch to Gemini: `LLM_PROVIDER=gemini`
- Limit video duration: `--max-duration 1800` (30 min)
- Check status before re-running: `./crawl.sh status`

### Low Entity Quality

**Check:**
1. Confidence scores < 0.7?
2. Many entities with type "unknown"?
3. Generic entities (apps, packing items)?

**Solution:**
- Use better LLM model (OpenAI GPT-4o-mini)
- Check transcript quality from Stage 1
- Review extraction prompts in `extraction_prompts.py`

### Too Many Duplicates

**Check:**
1. Is fuzzy deduplication enabled?
2. Is threshold too low (<0.70)?

**Solution:**
- Ensure `USE_FUZZY_DEDUP=true`
- Adjust threshold: `FUZZY_THRESHOLD=0.75` (default)

---

## Output Schema

**File:** `stage2_entities/{video_id}.json`

```typescript
{
  video_id: string
  processing_timestamp: string
  traveler_profile: {
    touristiness: number          // 0-10
    adventure_level: number        // 0-10
    budget_level: number           // 1-10
    pace: "slow" | "moderate" | "fast"
    food_focus: number             // 0-10
    confidence: number             // 0.0-1.0
  }
  entities: Array<{
    entity_id: string              // Unique ID per video
    entity_name: string
    entity_type: string            // destination, restaurant, hotel, etc.
    sentiment: "positive" | "negative" | "neutral" | "mixed"
    context: string                // Subjective experience description
    vibe: {
      touristiness?: number
      adventure_level?: number
      budget_level?: number
      pace?: string
      food_focus?: number
    }
    location: {
      city?: string
      country?: string
      neighborhood?: string
    }
    mentions: number               // Times mentioned in video
    timestamp_start?: number       // First mention timestamp (seconds)
    confidence_score: number       // 0.0-1.0
  }>
  entity_count: {
    destination: number
    restaurant: number
    hotel: number
    activity: number
    attraction: number
    transportation: number
    shopping: number
    unknown: number
    total: number
  }
  cost: {
    extraction_cost: number        // USD
    total_tokens: number
  }
}
```

---

## Next Stage

Once Stage 2 completes:
- ✅ Entities extracted per video
- ✅ Traveler profiles inferred
- ✅ Fuzzy deduplication within video
- ➡️ **Ready for Stage 3:** [Canonicalization & Enrichment](stage3-enrichment.md)

---

## References

- **Implementation:** [`src/processors/stage2_extractor.py`](../../src/processors/stage2_extractor.py)
- **Prompts:** [`src/processors/extraction_prompts.py`](../../src/processors/extraction_prompts.py)
- **CLI Command:** [`cli/process_stage2.py`](../../cli/process_stage2.py)
- **VIBE Framework:** [vibe-framework.md](../02-architecture/vibe-framework.md)
- **Data Schemas:** [data-schemas.md](../04-reference/data-schemas.md)
- **Pipeline Overview:** [pipeline-overview.md](../02-architecture/pipeline-overview.md)

---

**Stage 2 complete!** Next: [Stage 3: Canonicalization & Enrichment](stage3-enrichment.md)
