"""
LLM Prompt Templates for Stage 2 Entity Extraction

Provides structured prompts for extracting travel information from video transcripts.
Two main strategies:
1. SINGLE_PASS_PROMPT: For short videos (< 15 minutes, < 6k tokens)
2. HIERARCHICAL_PROMPT: For long videos (chunked processing)

Output format matches Stage2Output schema:
- traveler_profile: TravelerProfile object
- entities: List[EntityExperience] objects
"""

# =============================================================================
# Single-Pass Extraction Prompt (Short Videos)
# =============================================================================

SINGLE_PASS_PROMPT = """You are a travel content analyzer. Extract structured travel information from the video transcript below.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}

**Transcript:**
{transcript}

**Instructions:**
Extract the following information and return as JSON:

1. **Traveler Profile:**
Extract traveler characteristics using EVIDENCE-BASED inference:

   - traveler_type: "solo", "couple", "family", "group", or "unknown"
     * Listen for: "I traveled alone", "my partner and I", "with kids", "group of friends"

   - age_range: "18-25", "26-35", "36-50", "50+", or "unknown"
     * Infer from: lifestyle mentions, activity choices, references to career/retirement

   - budget_tier: "budget", "mid-range", "luxury", or "unknown"
     * Infer from: accommodation type (hostel=budget, 4-star=mid, 5-star=luxury)
     * Transport: public=budget, taxis=mid, private drivers=luxury
     * Food: street food=budget, casual dining=mid, fine dining=luxury

   - travel_style: Array of tags (e.g., ["adventure", "cultural", "foodie", "relaxation", "nightlife"])
     * Match activities to styles: hiking=adventure, museums=cultural, food tours=foodie

   - confidence_score: 0.1-1.0 (REQUIRED - NEVER omit. Use 0.7+ for explicit, 0.4-0.6 for inferred, 0.3 if very uncertain)

2. **Entities (Places, Activities, Experiences):**
Extract the TOP 40-50 MOST IMPORTANT entities mentioned. Focus on:
- Places that received significant discussion (not just passing mentions)
- Activities with detailed experiences or recommendations
- Restaurants/hotels that were specifically reviewed
- Attractions that were visited and described

For each entity, extract:

**Core Fields (REQUIRED):**
   - entity_name: Name of the place/activity (required)
   - entity_type: "destination", "restaurant", "hotel", "activity", "attraction", "transportation", "shopping", "unknown"
   - location: City/area where it's located (optional)
   - experience: Concise description of the experience (10-300 chars, keep it brief!)
   - sentiment: "positive", "negative", "neutral", or "mixed"
   - confidence_score: 0.1-1.0 (REQUIRED - NEVER omit! 0.9-1.0=explicit details, 0.7-0.9=clear mention, 0.5-0.7=implied, 0.3-0.5=vague, 0.1-0.3=very uncertain)

**Temporal Information (extract when mentioned):**
   - best_time_to_visit: Array of best times (e.g., ["summer", "december", "early_morning", "shoulder_season"])
   - visit_duration: How long to spend (e.g., "2-3 hours", "half day", "full day")
   - time_of_day: Best time (e.g., "morning", "sunset", "night", "avoid_midday")
   - seasonal_notes: Season-specific tips (e.g., "crowded in summer", "closed in winter")

**Cost Information (extract when mentioned):**
   - cost_mentioned: Any cost info (e.g., "500 baht", "free", "expensive") - KEEP BRIEF, max 100 chars!
   - price_range: "free", "budget", "mid", "high"
   - specific_prices: Dict with prices (e.g., {{"entrance": 15, "tour": 50, "currency": "USD"}})
   - value_rating: "worth_it", "overpriced", "good_value", "skip"

**Practical Logistics (extract when mentioned):**
   - booking_info: How to book (e.g., "book online 1 week ahead", "walk-in only")
   - accessibility: Access details (e.g., "wheelchair accessible", "steep stairs")
   - transport_access: How to reach (e.g., "Metro line 4", "10 min walk from station")
   - insider_tips: Array of tips (e.g., ["bring water", "dress modestly", "cash only"])
   - warnings: Array of warnings (e.g., ["closed Mondays", "watch for pickpockets"])

   - timestamp_start: Starting timestamp in seconds (if identifiable)

**Output Format:**
Return ONLY valid JSON with this exact structure (no markdown, no explanations):

{{
  "traveler_profile": {{
    "traveler_type": "solo",
    "age_range": "26-35",
    "budget_tier": "mid-range",
    "travel_style": ["adventure", "foodie"],
    "confidence_score": 0.85
  }},
  "entities": [
    {{
      "entity_name": "Patong Beach",
      "entity_type": "destination",
      "location": "Phuket",
      "experience": "Beautiful beach with clear water. Great for swimming and water sports. Can get crowded during peak season.",
      "sentiment": "positive",
      "confidence_score": 0.9,
      "best_time_to_visit": ["early_morning", "sunset", "november-march"],
      "time_of_day": "early_morning",
      "seasonal_notes": "Very crowded in summer, best in winter months",
      "price_range": "free",
      "transport_access": "15 min walk from town center, tuk-tuk 100 baht",
      "insider_tips": ["arrive before 8am to avoid crowds", "bring reef-safe sunscreen"],
      "warnings": ["watch belongings, pickpockets active"],
      "timestamp_start": 45.0
    }},
    {{
      "entity_name": "Street Food Near Big Buddha",
      "entity_type": "restaurant",
      "location": "Phuket",
      "experience": "Amazing pad thai and mango sticky rice. Very affordable and authentic. Vendor friendly, speaks English.",
      "sentiment": "positive",
      "confidence_score": 0.85,
      "cost_mentioned": "100 baht per dish",
      "price_range": "budget",
      "specific_prices": {{"pad_thai": 60, "mango_sticky_rice": 80, "currency": "THB"}},
      "value_rating": "worth_it",
      "visit_duration": "30-45 minutes",
      "insider_tips": ["cash only", "most popular items sell out by 7pm"],
      "timestamp_start": 120.5
    }}
  ]
}}

**Important Guidelines:**

**Mandatory:**
- **CRITICAL: ALWAYS provide confidence_score (0.1-1.0) for EVERY entity and traveler_profile - NEVER omit!**
- Extract TOP 40-50 entities maximum (prioritize most important/discussed items)
- Skip passing mentions - focus on places/activities that got detailed coverage
- Keep experience descriptions CONCISE (under 300 characters each)

**Enhanced Extraction (HIGH VALUE - extract when mentioned):**
- **Temporal data**: Best seasons, visit duration, time of day recommendations
- **Cost details**: Price ranges, specific prices with currency, value assessments
- **Practical tips**: Booking requirements, accessibility, transport, insider tips
- **Warnings**: Important alerts travelers should know

**Field Rules:**
- Omit optional fields if NOT mentioned in transcript (don't guess or hallucinate)
- Only use "unknown" for traveler profile fields, not entity fields
- For temporal/cost/practical fields: extract if mentioned, omit if not
- Be conservative with confidence scores (0.7-0.9 is typical for good quality)

**Focus:**
- ACTIONABLE information that helps travelers make decisions
- PRACTICAL details (when, how much, how to book, how to get there)
- TIPS that save time, money, or hassle
- Quality over quantity - 30 rich entities > 50 sparse ones

Now analyze the transcript and return the JSON:"""


# =============================================================================
# Hierarchical Extraction Prompt (Long Videos - Chunk Processing)
# =============================================================================

HIERARCHICAL_CHUNK_PROMPT = """You are a travel content analyzer. Extract structured travel information from this video transcript CHUNK.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}
- Chunk: {chunk_number} of {total_chunks}

**Transcript Chunk:**
{transcript_chunk}

**Instructions:**
This is part {chunk_number} of a {duration_minutes}-minute video. Extract entities from THIS CHUNK ONLY.

Extract the following:

1. **Partial Traveler Profile Signals:**
   - Any hints about traveler_type, age_range, budget_tier, travel_style
   - Return partial data (will be merged later)

2. **Entities in This Chunk:**
For EACH place, restaurant, hotel, activity, or attraction mentioned in this chunk:

**Core Fields:**
   - entity_name: Name (required)
   - entity_type: "destination", "restaurant", "hotel", "activity", "attraction", "transportation", "shopping", "unknown"
   - location: City/area (optional)
   - experience: Description (10-2000 chars)
   - sentiment: "positive", "negative", "neutral", "mixed"
   - confidence_score: 0.1-1.0 (REQUIRED - NEVER omit! Minimum 0.1, use 0.3-0.5 if very uncertain)

**Enhanced Fields (extract when mentioned in chunk):**
   - best_time_to_visit, visit_duration, time_of_day, seasonal_notes (temporal)
   - cost_mentioned, price_range, specific_prices, value_rating (cost)
   - booking_info, accessibility, transport_access, insider_tips, warnings (practical)
   - timestamp_start: Starting timestamp in seconds (if identifiable)

**Output Format:**
Return ONLY valid JSON (no markdown, no explanations):

{{
  "chunk_number": {chunk_number},
  "traveler_profile_signals": {{
    "traveler_type": "solo",
    "budget_tier": "budget",
    "travel_style": ["adventure"],
    "confidence_score": 0.5
  }},
  "entities": [
    {{
      "entity_name": "...",
      "entity_type": "...",
      "location": "...",
      "experience": "...",
      "sentiment": "...",
      "cost_mentioned": "...",
      "timestamp_start": 0.0,
      "confidence_score": 0.8
    }}
  ]
}}

**Guidelines:**
- **CRITICAL: ALWAYS provide confidence_score (0.1-1.0) for EVERY entity - NEVER omit!**
- Focus ONLY on this chunk (don't infer from other parts)
- Extract ALL entities mentioned in this chunk with ALL available details
- **Extract enhanced fields**: temporal, cost, practical info when mentioned
- Keep confidence scores conservative (0.5-0.8 typical for chunks)
- Omit optional enhanced fields if not mentioned (don't guess)
- If no traveler signals in chunk, return empty traveler_profile_signals
- Minimum confidence_score is 0.1 (use 0.3-0.5 if very uncertain)

Now analyze this chunk and return the JSON:"""


HIERARCHICAL_MERGE_PROMPT = """You are a travel content analyzer. Merge extracted entities from multiple video chunks into a final cohesive output.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}
- Total Chunks: {total_chunks}

**Chunk Extractions:**
{chunk_results}

**Instructions:**
Merge the chunk results into a single final output:

1. **Traveler Profile:**
   - Combine traveler_profile_signals from all chunks
   - Determine final traveler_type, age_range, budget_tier, travel_style
   - Weight confidence by number of supporting signals
   - If conflicting signals, choose most common or most confident

2. **Entities:**
   - Combine all entities from all chunks
   - Remove duplicates (same entity mentioned multiple times)
   - For duplicates, merge experiences and keep highest confidence
   - Sort by timestamp_start (if available)

**Output Format:**
Return ONLY valid JSON matching Stage2Output structure:

{{
  "traveler_profile": {{
    "traveler_type": "solo",
    "age_range": "26-35",
    "budget_tier": "mid-range",
    "travel_style": ["adventure", "foodie", "cultural"],
    "confidence_score": 0.85
  }},
  "entities": [
    {{
      "entity_name": "...",
      "entity_type": "...",
      "location": "...",
      "experience": "...",
      "sentiment": "...",
      "cost_mentioned": "...",
      "timestamp_start": 0.0,
      "confidence_score": 0.9
    }}
  ]
}}

**Merging Guidelines:**
- For duplicate entities, combine experiences: "Experience 1. Experience 2."
- Keep highest confidence_score and earliest timestamp_start
- If same entity has conflicting sentiment, use "mixed"
- Traveler profile should reflect overall video, not just one chunk
- Final entity list should be comprehensive but deduplicated

Now merge the chunks and return the final JSON:"""


# =============================================================================
# Split Prompts (Improved Accuracy)
# =============================================================================
# These focused prompts can improve extraction accuracy by giving the LLM
# clearer, more focused instructions for each task.

PROFILE_ONLY_PROMPT = """You are a travel content analyzer. Extract ONLY the traveler profile from this video transcript.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}

**Transcript:**
{transcript}

**Instructions:**
Extract traveler characteristics using EVIDENCE-BASED inference:

1. **traveler_type**: "solo", "couple", "family", "group", or "unknown"
   - Listen for: "I traveled alone", "my partner and I", "with kids", "group of friends"

2. **age_range**: "18-25", "26-35", "36-50", "50+", or "unknown"
   - Infer from: lifestyle mentions, activity choices, career/retirement references

3. **budget_tier**: "budget", "mid-range", "luxury", or "unknown"
   - Accommodation: hostel=budget, 4-star=mid, 5-star=luxury
   - Transport: public=budget, taxis=mid, private drivers=luxury
   - Food: street food=budget, casual dining=mid, fine dining=luxury

4. **travel_style**: Array of tags
   - Examples: ["adventure", "cultural", "foodie", "relaxation", "nightlife", "photography"]
   - Match activities to styles: hiking=adventure, museums=cultural, food tours=foodie

5. **confidence_score**: 0.1-1.0 (REQUIRED)
   - 0.7+: Explicit evidence in transcript
   - 0.4-0.6: Reasonable inference from context
   - 0.3: Very uncertain

**Output Format:**
Return ONLY valid JSON (no markdown, no explanations):

{{
  "traveler_profile": {{
    "traveler_type": "solo",
    "age_range": "26-35",
    "budget_tier": "mid-range",
    "travel_style": ["adventure", "foodie"],
    "confidence_score": 0.85
  }}
}}

Now analyze the transcript and return the JSON:"""


ENTITIES_ONLY_PROMPT = """You are a travel content analyzer. Extract ONLY travel entities (places, activities, restaurants, hotels) from this video transcript.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}

**Transcript:**
{transcript}

**Instructions:**
Extract the TOP 40-50 MOST IMPORTANT entities mentioned. Focus on:
- Places with significant discussion (not passing mentions)
- Activities with detailed experiences or recommendations
- Restaurants/hotels that were specifically reviewed
- Attractions that were visited and described

**For each entity, extract:**

**Core Fields (REQUIRED):**
- entity_name: Name of the place/activity
- entity_type: "destination", "restaurant", "hotel", "activity", "attraction", "transportation", "shopping", "unknown"
- location: City/area where it's located
- experience: Concise description (10-300 chars)
- sentiment: "positive", "negative", "neutral", "mixed"
- confidence_score: 0.1-1.0 (REQUIRED)

**Temporal Information (if mentioned):**
- best_time_to_visit: Array ["summer", "december", "early_morning"]
- visit_duration: "2-3 hours", "half day", "full day"
- time_of_day: "morning", "sunset", "night"
- seasonal_notes: "crowded in summer", "closed in winter"

**Cost Information (if mentioned):**
- cost_mentioned: "500 baht", "free", "expensive" (max 100 chars)
- price_range: "free", "budget", "mid", "high"
- specific_prices: {{"entrance": 15, "tour": 50, "currency": "USD"}}
- value_rating: "worth_it", "overpriced", "good_value", "skip"

**Practical Logistics (if mentioned):**
- booking_info: "book online 1 week ahead", "walk-in only"
- accessibility: "wheelchair accessible", "steep stairs"
- transport_access: "Metro line 4", "10 min walk from station"
- insider_tips: ["bring water", "dress modestly", "cash only"]
- warnings: ["closed Mondays", "watch for pickpockets"]
- timestamp_start: Starting timestamp in seconds

**Confidence Score Guide:**
- 0.9-1.0: Explicit details (name, price, duration mentioned)
- 0.7-0.9: Clear mention with some specifics
- 0.5-0.7: Implied but reasonable inference
- 0.3-0.5: Vague references
- 0.1-0.3: Very uncertain

**Output Format:**
Return ONLY valid JSON (no markdown, no explanations):

{{
  "entities": [
    {{
      "entity_name": "Patong Beach",
      "entity_type": "destination",
      "location": "Phuket",
      "experience": "Beautiful beach with clear water. Great for swimming.",
      "sentiment": "positive",
      "confidence_score": 0.9,
      "best_time_to_visit": ["early_morning", "sunset"],
      "price_range": "free",
      "transport_access": "15 min walk from town center",
      "insider_tips": ["arrive before 8am to avoid crowds"],
      "timestamp_start": 45.0
    }}
  ]
}}

**Important:**
- ALWAYS provide confidence_score for EVERY entity
- Skip passing mentions - focus on detailed coverage
- Omit optional fields if NOT mentioned (don't guess)
- Quality over quantity - 30 rich entities > 50 sparse ones

Now analyze the transcript and return the JSON:"""


ENTITY_ENRICHMENT_PROMPT = """You are a travel content analyzer. Enrich these extracted entities with additional practical details from the transcript.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}

**Previously Extracted Entities:**
{entities_json}

**Transcript:**
{transcript}

**Instructions:**
For each entity, find and add any MISSING practical information:

1. **Temporal details** (when to visit):
   - best_time_to_visit: Best seasons/times
   - visit_duration: How long to spend
   - time_of_day: Best time of day
   - seasonal_notes: Season-specific tips

2. **Cost details** (how much):
   - cost_mentioned: Any prices mentioned
   - price_range: Budget category
   - specific_prices: Exact prices with currency
   - value_rating: Worth it assessment

3. **Practical logistics** (how to):
   - booking_info: Reservation requirements
   - accessibility: Physical access details
   - transport_access: How to get there
   - insider_tips: Helpful tips
   - warnings: Important alerts

**Output Format:**
Return the SAME entities list with any new fields added:

{{
  "entities": [
    {{
      "entity_name": "Patong Beach",
      "entity_type": "destination",
      "location": "Phuket",
      "experience": "Beautiful beach...",
      "sentiment": "positive",
      "confidence_score": 0.9,
      "best_time_to_visit": ["early_morning"],
      "visit_duration": "2-3 hours",
      "cost_mentioned": "free entry, sunbed rental 100 baht",
      "transport_access": "15 min walk from town center, tuk-tuk 50 baht",
      "insider_tips": ["arrive before 8am", "bring reef-safe sunscreen"],
      "warnings": ["strong currents in monsoon season"]
    }}
  ]
}}

**Rules:**
- Only ADD fields that have evidence in transcript
- Don't remove or modify existing fields
- Don't guess or hallucinate information
- If no new info found for an entity, return it unchanged

Now enrich the entities and return the JSON:"""


def format_profile_only_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript: str
) -> str:
    """Format the profile-only extraction prompt."""
    return PROFILE_ONLY_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        transcript=transcript
    )


def format_entities_only_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript: str
) -> str:
    """Format the entities-only extraction prompt."""
    return ENTITIES_ONLY_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        transcript=transcript
    )


def format_entity_enrichment_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    entities_json: str,
    transcript: str
) -> str:
    """Format the entity enrichment prompt."""
    return ENTITY_ENRICHMENT_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        entities_json=entities_json,
        transcript=transcript
    )


# =============================================================================
# Example Input/Output (for documentation and testing)
# =============================================================================

EXAMPLE_INPUT = {
    "title": "Phuket Budget Travel Guide - 5 Days Itinerary",
    "duration_minutes": 12.5,
    "language": "en",
    "transcript": """
Hey guys! Today I'm sharing my 5-day budget trip to Phuket Thailand.
I traveled solo and spent around 15,000 baht total which is super affordable.

Day 1: I stayed at Patong Beach area. Found a decent hostel for 300 baht per night.
The beach is beautiful but quite touristy. Best time to visit is early morning.

For food, I loved the street food near Big Buddha. Pad thai was only 60 baht
and mango sticky rice was 80 baht. So delicious and authentic!

Day 2: Rented a scooter for 200 baht per day to explore the island.
Visited Karon Beach - much quieter than Patong. Also went to Wat Chalong temple,
which is free to enter. Very peaceful and beautiful architecture.

One thing to avoid - the beach club entry fees can be expensive, around 500-1000 baht.
I skipped those and just enjoyed the public beaches instead.

Day 3-4: Did a day trip to Phi Phi Islands for 1200 baht including lunch and snorkeling.
The water is incredibly clear! Best experience of the trip. Book through your hostel
for better prices.

Overall, Phuket is perfect for solo budget travelers. People are friendly, food is cheap,
and there's so much to explore. Highly recommend!
"""
}

EXAMPLE_OUTPUT = {
    "traveler_profile": {
        "traveler_type": "solo",
        "age_range": "26-35",
        "budget_tier": "budget",
        "travel_style": ["adventure", "foodie", "cultural"],
        "confidence_score": 0.9
    },
    "entities": [
        {
            "entity_name": "Patong Beach",
            "entity_type": "destination",
            "location": "Phuket",
            "experience": "Beautiful beach but quite touristy. Best time to visit is early morning to avoid crowds. Good base for staying in Phuket.",
            "sentiment": "positive",
            "cost_mentioned": "free entry",
            "timestamp_start": None,
            "confidence_score": 0.9
        },
        {
            "entity_name": "Budget Hostel Patong",
            "entity_type": "hotel",
            "location": "Patong Beach, Phuket",
            "experience": "Decent budget accommodation in Patong Beach area. Good value for money.",
            "sentiment": "positive",
            "cost_mentioned": "300 baht per night",
            "timestamp_start": None,
            "confidence_score": 0.75
        },
        {
            "entity_name": "Street Food Near Big Buddha",
            "entity_type": "restaurant",
            "location": "Phuket",
            "experience": "Authentic Thai street food. Pad thai was delicious and mango sticky rice was amazing. Very affordable and authentic taste.",
            "sentiment": "positive",
            "cost_mentioned": "60 baht pad thai, 80 baht mango sticky rice",
            "timestamp_start": None,
            "confidence_score": 0.85
        },
        {
            "entity_name": "Karon Beach",
            "entity_type": "destination",
            "location": "Phuket",
            "experience": "Much quieter alternative to Patong Beach. More peaceful atmosphere. Good for those who want to avoid tourist crowds.",
            "sentiment": "positive",
            "cost_mentioned": "free entry",
            "timestamp_start": None,
            "confidence_score": 0.85
        },
        {
            "entity_name": "Wat Chalong Temple",
            "entity_type": "attraction",
            "location": "Phuket",
            "experience": "Free temple with beautiful architecture. Very peaceful atmosphere. Great cultural experience.",
            "sentiment": "positive",
            "cost_mentioned": "free entry",
            "timestamp_start": None,
            "confidence_score": 0.9
        },
        {
            "entity_name": "Scooter Rental",
            "entity_type": "transport",
            "location": "Phuket",
            "experience": "Affordable way to explore the island independently. Gives freedom to visit multiple beaches and attractions.",
            "sentiment": "positive",
            "cost_mentioned": "200 baht per day",
            "timestamp_start": None,
            "confidence_score": 0.8
        },
        {
            "entity_name": "Beach Clubs",
            "entity_type": "activity",
            "location": "Phuket",
            "experience": "Can be expensive with entry fees. Better to skip for budget travelers and enjoy public beaches instead.",
            "sentiment": "negative",
            "cost_mentioned": "500-1000 baht entry",
            "timestamp_start": None,
            "confidence_score": 0.75
        },
        {
            "entity_name": "Phi Phi Islands Day Trip",
            "entity_type": "activity",
            "location": "Phi Phi Islands",
            "experience": "Best experience of the trip. Incredibly clear water, includes lunch and snorkeling. Book through hostel for better prices than street vendors.",
            "sentiment": "positive",
            "cost_mentioned": "1200 baht including lunch and snorkeling",
            "timestamp_start": None,
            "confidence_score": 0.95
        }
    ]
}


# =============================================================================
# Helper Functions
# =============================================================================

def format_single_pass_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript: str
) -> str:
    """
    Format the single-pass extraction prompt with video data.

    Args:
        title: Video title
        duration_minutes: Video duration in minutes
        language: Language code (e.g., "en", "hi")
        transcript: Full transcript text

    Returns:
        Formatted prompt string ready for LLM
    """
    return SINGLE_PASS_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        transcript=transcript
    )


def format_hierarchical_chunk_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript_chunk: str,
    chunk_number: int,
    total_chunks: int
) -> str:
    """
    Format the hierarchical chunk extraction prompt.

    Args:
        title: Video title
        duration_minutes: Video duration in minutes
        language: Language code
        transcript_chunk: This chunk's transcript text
        chunk_number: Current chunk number (1-indexed)
        total_chunks: Total number of chunks

    Returns:
        Formatted prompt string for chunk extraction
    """
    return HIERARCHICAL_CHUNK_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        transcript_chunk=transcript_chunk,
        chunk_number=chunk_number,
        total_chunks=total_chunks
    )


def format_hierarchical_merge_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    chunk_results: str,
    total_chunks: int
) -> str:
    """
    Format the hierarchical merge prompt.

    Args:
        title: Video title
        duration_minutes: Video duration in minutes
        language: Language code
        chunk_results: JSON string of all chunk extractions
        total_chunks: Total number of chunks

    Returns:
        Formatted prompt string for merging chunks
    """
    return HIERARCHICAL_MERGE_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        chunk_results=chunk_results,
        total_chunks=total_chunks
    )
