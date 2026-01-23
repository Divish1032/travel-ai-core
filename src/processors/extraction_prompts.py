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
- Description: {description}
- Tags: {tags}
- Views: {view_count:,}

**Transcript:**
{transcript}

**How to Use Video Metadata:**
- **Description**: Contains links, timestamps, location names, budget hints, and additional context not in transcript
- **Tags**: Indicate travel style (luxury/budget/backpacking), destination names, and activity types
- **Views**: High view count (>100k) can indicate popular/reliable destinations; use to boost confidence scores for well-known places

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

**Cost Information (extract when mentioned):**
   - cost_mentioned: Any cost info (e.g., "500 baht", "free", "expensive") - KEEP BRIEF, max 100 chars!

**Metadata:**
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

**CRITICAL: Entity Definition Rules - What IS an Entity:**
An entity must be a SPECIFIC, ACTIONABLE place or activity that a traveler can visit, book, or do.

✅ **EXTRACT These (Specific Places/Activities):**
- Specific attractions: "Grand Palace", "Wat Pho", "Big Buddha"
- Specific restaurants/food vendors: "Pad Thai at Thip Samai", "Som Tam stand on Soi 38", "Gaggan Restaurant"
- Specific hotels/hostels: "The Peninsula Bangkok", "Lub d Hostel", "Airbnb in Old Town"
- Specific activities: "Rock climbing at Railay", "Cooking class at Thai Farm", "Phi Phi Island hopping tour"
- Specific markets: "Chatuchak Weekend Market", "Night Bazaar", "Talad Rot Fai"
- Districts/neighborhoods/beaches: "Khao San Road", "Patong Beach", "Old Quarter", "RCA nightlife district"
- Specific shops: "Jim Thompson House & Store", "MBK Center mall"

❌ **DO NOT EXTRACT These (Too Generic/Broad):**
- City names alone: "Bangkok", "Phuket", "Chiang Mai", "Krabi"
- Country names: "Thailand", "Vietnam", "Indonesia"
- Regions: "Southeast Asia", "Northern Thailand", "Isaan region"
- Generic categories: "Thai food", "temples", "beaches", "nightlife", "street food"
- Generic activities without location: "scuba diving", "shopping", "eating"

**Entity Type Clarifications:**
- "destination" = Districts, beaches, islands, specific neighborhoods (NOT cities/countries)
  ✅ Good: "Phi Phi Islands", "Railay Beach", "Old Town Phuket", "Sukhumvit district"
  ❌ Bad: "Bangkok", "Thailand", "Phuket city"

**Rule of Thumb:** If you can't physically visit it as a specific location or specifically book/do it, it's NOT an entity. City/country names belong ONLY in the location field, not entity_name.

**What to Extract (HIGH VALUE):**
- **Personal experiences**: Traveler's direct observations and feelings
- **Cost mentions**: Specific prices mentioned by the traveler
- **Subjective opinions**: What they liked, disliked, or found noteworthy

**Field Rules:**
- Omit optional fields if NOT mentioned in transcript (don't guess or hallucinate)
- Only use "unknown" for traveler profile fields, not entity fields
- Extract cost_mentioned if prices are mentioned, omit if not
- Be conservative with confidence scores (0.7-0.9 is typical for good quality)

**Focus:**
- SUBJECTIVE traveler experiences and opinions (not generic facts)
- PERSONAL observations from their actual visit
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
- Description: {description}
- Tags: {tags}
- Views: {view_count:,}
- Chunk: {chunk_number} of {total_chunks}

**Transcript Chunk:**
{transcript_chunk}

**How to Use Video Metadata:**
- **Description**: Contains links, timestamps, location names, budget hints, and additional context
- **Tags**: Indicate travel style (luxury/budget/backpacking), destination names, activity types
- **Views**: High view count (>100k) suggests popular/reliable destinations

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

**Optional Fields (extract when mentioned in chunk):**
   - cost_mentioned: Brief cost info (e.g., "500 baht", "free")
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
- Extract ALL entities mentioned in this chunk with their personal experiences
- Extract cost info when mentioned
- Keep confidence scores conservative (0.5-0.8 typical for chunks)
- Omit optional fields if not mentioned (don't guess)
- If no traveler signals in chunk, return empty traveler_profile_signals
- Minimum confidence_score is 0.1 (use 0.3-0.5 if very uncertain)

**CRITICAL: Entity Definition Rules - What IS an Entity:**
✅ **EXTRACT:** Specific attractions ("Wat Pho"), specific restaurants ("Thip Samai"), specific hotels, specific activities with location, districts/beaches ("Patong Beach", "Khao San Road"), specific markets
❌ **DO NOT EXTRACT:** City names alone ("Bangkok", "Phuket"), country names ("Thailand"), regions ("Northern Thailand"), generic categories ("Thai food", "temples")
**Rule:** If it's not a specific location/business/activity you can visit or book, it's NOT an entity. Cities/countries go in location field only.

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
- Description: {description}
- Tags: {tags}
- Views: {view_count:,}

**How to Use Video Metadata:**
- **Description**: May contain creator bio, travel style hints, budget mentions
- **Tags**: Indicate travel style (luxury/budget/backpacking), activity preferences
- **Views**: Popular channels (>100k views) often have consistent travel style

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
- Description: {description}
- Tags: {tags}
- Views: {view_count:,}

**How to Use Video Metadata:**
- **Description**: May contain links to places, timestamps with locations, additional entity names
- **Tags**: Destination names, activity types (hiking, foodie, beach)
- **Views**: High view count (>100k) can boost confidence for well-known places

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

**Cost Information (if mentioned):**
- cost_mentioned: "500 baht", "free", "expensive" (max 100 chars)
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
      "timestamp_start": 45.0
    }}
  ]
}}

**Important:**
- ALWAYS provide confidence_score for EVERY entity
- Skip passing mentions - focus on detailed coverage
- Omit optional fields if NOT mentioned (don't guess)
- Quality over quantity - 30 rich entities > 50 sparse ones

**CRITICAL: Entity Definition Rules - What IS an Entity:**
An entity must be SPECIFIC and ACTIONABLE (something you can visit, book, or do).

✅ **EXTRACT These:**
- Specific attractions: "Grand Palace", "Wat Pho", "Big Buddha"
- Specific restaurants: "Thip Samai Pad Thai", "Gaggan", "street vendor on Soi 38"
- Specific hotels: "The Peninsula Bangkok", "Lub d Hostel"
- Specific activities: "Rock climbing at Railay", "Thai cooking class at Farm"
- Districts/beaches: "Khao San Road", "Patong Beach", "Old Quarter"
- Specific markets: "Chatuchak Market", "Night Bazaar"

❌ **DO NOT EXTRACT These:**
- City names: "Bangkok", "Phuket", "Chiang Mai"
- Country names: "Thailand", "Vietnam"
- Generic categories: "Thai food", "temples", "beaches"
- Regions: "Northern Thailand", "Southeast Asia"

**Rule:** Cities/countries belong in the location field ONLY, not entity_name. Extract specific places within cities.

Now analyze the transcript and return the JSON:"""


ENTITY_ENRICHMENT_PROMPT = """You are a travel content analyzer. Enrich these extracted entities with any MISSING traveler insights from the transcript.

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Language: {language}
- Description: {description}
- Tags: {tags}
- Views: {view_count:,}

**How to Use Video Metadata:**
- **Description**: May contain additional context about places mentioned
- **Tags**: Can indicate activity types and destination characteristics

**Previously Extracted Entities:**
{entities_json}

**Transcript:**
{transcript}

**Instructions:**
For each entity, find and add any MISSING cost information:

1. **Cost mentions** (if not already present):
   - cost_mentioned: Any specific prices mentioned by traveler

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
      "cost_mentioned": "free entry, sunbed rental 100 baht"
    }}
  ]
}}

**Rules:**
- Only ADD fields that have evidence in transcript
- Don't remove or modify existing fields
- Don't guess or hallucinate information
- If no new info found for an entity, return it unchanged

**Note:** All entities should be specific places/activities (not city names). If you see a generic city name ("Bangkok") as an entity_name, flag it with low confidence_score.

Now enrich the entities and return the JSON:"""


def format_profile_only_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript: str,
    description: str = "",
    tags: list = None,
    view_count: int = 0
) -> str:
    """Format the profile-only extraction prompt."""
    tags_str = ", ".join(tags) if tags else "None"

    return PROFILE_ONLY_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        description=description[:500] if description else "N/A",
        tags=tags_str[:200] if tags_str else "None",
        view_count=view_count,
        transcript=transcript
    )


def format_entities_only_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript: str,
    description: str = "",
    tags: list = None,
    view_count: int = 0
) -> str:
    """Format the entities-only extraction prompt."""
    tags_str = ", ".join(tags) if tags else "None"

    return ENTITIES_ONLY_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        description=description[:500] if description else "N/A",
        tags=tags_str[:200] if tags_str else "None",
        view_count=view_count,
        transcript=transcript
    )


def format_entity_enrichment_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    entities_json: str,
    transcript: str,
    description: str = "",
    tags: list = None,
    view_count: int = 0
) -> str:
    """Format the entity enrichment prompt."""
    tags_str = ", ".join(tags) if tags else "None"

    return ENTITY_ENRICHMENT_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        description=description[:500] if description else "N/A",
        tags=tags_str[:200] if tags_str else "None",
        view_count=view_count,
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
    transcript: str,
    description: str = "",
    tags: list = None,
    view_count: int = 0
) -> str:
    """
    Format the single-pass extraction prompt with video data.

    Args:
        title: Video title
        duration_minutes: Video duration in minutes
        language: Language code (e.g., "en", "hi")
        transcript: Full transcript text
        description: Video description
        tags: List of video tags
        view_count: Number of views

    Returns:
        Formatted prompt string ready for LLM
    """
    tags_str = ", ".join(tags) if tags else "None"

    return SINGLE_PASS_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        description=description[:500] if description else "N/A",  # Limit description length
        tags=tags_str[:200] if tags_str else "None",  # Limit tags length
        view_count=view_count,
        transcript=transcript
    )


def format_hierarchical_chunk_prompt(
    title: str,
    duration_minutes: float,
    language: str,
    transcript_chunk: str,
    chunk_number: int,
    total_chunks: int,
    description: str = "",
    tags: list = None,
    view_count: int = 0
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
        description: Video description
        tags: List of video tags
        view_count: Number of views

    Returns:
        Formatted prompt string for chunk extraction
    """
    tags_str = ", ".join(tags) if tags else "None"

    return HIERARCHICAL_CHUNK_PROMPT.format(
        title=title,
        duration_minutes=f"{duration_minutes:.1f}",
        language=language,
        description=description[:500] if description else "N/A",
        tags=tags_str[:200] if tags_str else "None",
        view_count=view_count,
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
