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
   - traveler_type: "solo", "couple", "family", "group", or "unknown"
   - age_range: "18-25", "26-35", "36-50", "50+", or "unknown"
   - budget_tier: "budget", "mid-range", "luxury", or "unknown"
   - travel_style: Array of tags (e.g., ["adventure", "cultural", "foodie", "relaxation", "nightlife"])
   - confidence_score: 0.0-1.0 (how confident are you in this profile?)

2. **Entities (Places, Activities, Experiences):**
For EACH mentioned place, restaurant, hotel, activity, or attraction, extract:
   - entity_name: Name of the place/activity (required)
   - entity_type: "destination", "restaurant", "hotel", "activity", "attraction", "transport", "other"
   - location: City/area where it's located (optional)
   - experience: Detailed description of the experience (10-2000 chars)
   - sentiment: "positive", "negative", "neutral", or "mixed"
   - cost_mentioned: Any cost info mentioned (e.g., "500 baht", "free", "expensive")
   - timestamp_start: Starting timestamp in seconds (if identifiable)
   - confidence_score: 0.0-1.0

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
      "experience": "Beautiful beach with clear water. Great for swimming and water sports. Can get crowded during peak season. Best visited early morning or sunset.",
      "sentiment": "positive",
      "cost_mentioned": "free entry",
      "timestamp_start": 45.0,
      "confidence_score": 0.9
    }},
    {{
      "entity_name": "Street Food Near Big Buddha",
      "entity_type": "restaurant",
      "location": "Phuket",
      "experience": "Amazing pad thai and mango sticky rice. Very affordable and authentic. The vendor is friendly and speaks some English.",
      "sentiment": "positive",
      "cost_mentioned": "100 baht per dish",
      "timestamp_start": 120.5,
      "confidence_score": 0.85
    }}
  ]
}}

**Important Guidelines:**
- Extract ALL mentioned places, activities, and experiences (don't skip minor mentions)
- If traveler profile is unclear, use "unknown" and low confidence_score
- For sentiment, consider tone, recommendations, and warnings
- Include practical details: costs, tips, warnings, best times to visit
- If no cost mentioned, omit the "cost_mentioned" field
- If timestamp unclear, omit the "timestamp_start" field
- Be conservative with confidence scores (0.7-0.9 is typical)
- Focus on ACTIONABLE information that helps future travelers

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
   - entity_name: Name (required)
   - entity_type: "destination", "restaurant", "hotel", "activity", "attraction", "transport", "other"
   - location: City/area (optional)
   - experience: Description (10-2000 chars)
   - sentiment: "positive", "negative", "neutral", "mixed"
   - cost_mentioned: Any cost info (optional)
   - timestamp_start: Starting timestamp in seconds (optional)
   - confidence_score: 0.0-1.0

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
- Focus ONLY on this chunk (don't infer from other parts)
- Extract ALL entities mentioned in this chunk
- Keep confidence scores conservative
- If no traveler signals in chunk, return empty traveler_profile_signals

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
