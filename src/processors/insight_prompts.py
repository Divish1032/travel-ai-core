"""
LLM Prompt Templates for Insights Pipeline

Provides structured prompts for extracting travel insights (services, tips, logistics)
from two sources:
1. PASS1_ENTITY_ENRICHMENT_PROMPT: Extract insights from filtered non-place entities
2. PASS2_TRANSCRIPT_EXTRACTION_PROMPT: Extract insights from info-only video transcripts

Output format matches TravelInsight schema with 8 categories:
- services: Apps, booking platforms, tools
- logistics: How-to guides, visa processes
- tips: Practical travel advice
- regional: Area-specific knowledge
- cultural: Customs, etiquette
- safety: Security, scams, health
- cost_info: Price ranges, budget advice
- seasonal: Weather, best times to visit

CRITICAL: All prompts are destination-agnostic (work globally, not Thailand-specific)
"""

# =============================================================================
# Pass 1: Entity Enrichment Prompt (Filtered Entities)
# =============================================================================

PASS1_ENTITY_ENRICHMENT_PROMPT = """You are a travel knowledge extractor. Extract reusable travel insights from the filtered entity below.

**Context:**
This entity was filtered out of the main place entity pipeline because it's not a physical location.
However, it may contain valuable travel knowledge like:
- Useful services/apps (e.g., "12goasia for booking buses")
- Practical tips (e.g., "Pack Type C adapter")
- Logistics advice (e.g., "Visa on arrival process")

**Filtered Entity:**
- Name: {entity_name}
- Type: {entity_type}
- Filter Reason: {filter_reason}
- Location Context: {location_context}
- Experience Description: {experience_description}

**Video Metadata:**
- Title: {video_title}
- Duration: {duration_minutes} minutes
- Description: {video_description}
- Destination: {destination}

**Instructions:**
Extract 1-3 actionable travel insights from this entity. Each insight should be:
- Destination-agnostic (avoid city/country names unless essential for scope)
- Reusable across multiple trips
- Practical and actionable

**Output Format:**
Return ONLY valid JSON with this exact structure (no markdown, no explanations):

{{
  "insights": [
    {{
      "category": "services",
      "content": "Use 12goasia.com to book intercity buses and trains in Southeast Asia. Shows real-time availability and prices from multiple operators.",
      "title": "12goasia for bus/train booking",
      "details": "Website and mobile app. Compare prices across operators. Payment via credit card. E-tickets sent via email. Popular in Thailand, Vietnam, Cambodia.",
      "scope": {{
        "destination_type": "region",
        "region": "Southeast Asia"
      }},
      "confidence_score": 0.90,
      "tags": ["booking", "transportation", "website"]
    }},
    {{
      "category": "tips",
      "content": "Pack a Type C or Type F power adapter for travel to European countries. Most hotels don't provide adapters.",
      "title": "Power adapter for Europe",
      "details": "Type C (2 round pins) works in most European countries. Type F (2 round pins with grounding clips) works in Germany, Austria, Netherlands. Check specific country requirements before traveling.",
      "scope": {{
        "destination_type": "region",
        "region": "Europe"
      }},
      "confidence_score": 0.85,
      "tags": ["packing", "electricity", "adapter"]
    }}
  ]
}}

**Insight Categories:**

1. **services** - Apps, booking platforms, tools
   - Examples: "Bolt for ride-hailing", "Grab app", "WhatsApp for local communication"
   - When to use: Entity is a digital service/tool that helps travelers

2. **logistics** - How-to guides, visa processes, getting around
   - Examples: "Visa on arrival process at Bangkok airport", "How to take train from airport to city"
   - When to use: Entity describes a process or logistical advice

3. **tips** - Practical travel advice, packing, money, local customs
   - Examples: "Pack mosquito repellent", "Bring cash for street food", "Download offline maps"
   - When to use: Entity is practical advice for travelers

4. **regional** - Area-specific knowledge (neighborhoods, traffic, local quirks)
   - Examples: "Bangkok traffic worst 5-7pm", "Khao San Road busy on weekends"
   - When to use: Entity is location-specific information (use city/area in scope)

5. **cultural** - Customs, etiquette, dos/don'ts
   - Examples: "Remove shoes before entering temples", "Dress modestly at religious sites"
   - When to use: Entity is cultural advice or etiquette

6. **safety** - Security, scams, health warnings
   - Examples: "Watch for taxi meter scams at airport", "Get travel insurance"
   - When to use: Entity is safety/security advice

7. **cost_info** - Price ranges, budget advice, value for money
   - Examples: "Street food costs $1-3 per meal", "Budget $30-50/day for mid-range travel"
   - When to use: Entity mentions costs or budget advice

8. **seasonal** - Weather, best times to visit, seasonal considerations
   - Examples: "Rainy season June-October", "Book 3 months ahead for peak season"
   - When to use: Entity mentions weather, seasons, or timing

**Scope Guidelines (Destination-Agnostic):**

The scope field defines where the insight applies. Use the most general scope possible:

- **global**: Applies everywhere (e.g., "Get travel insurance", "Download offline maps")
- **region**: Applies to a geographic region (e.g., "Southeast Asia", "Europe", "Caribbean")
- **country**: Applies to a specific country (e.g., "Thailand", "Japan", "Italy")
- **city**: Applies to a specific city (e.g., "Bangkok", "Tokyo", "Rome")
- **area**: Applies to a specific neighborhood/area (e.g., "Khao San Road", "Shibuya", "Trastevere")

Examples:
- "Pack Type C adapter" → region: Europe (not global, only works in Europe)
- "Use Grab app" → region: Southeast Asia (only available in SEA)
- "Bangkok traffic worst 5-7pm" → city: Bangkok (specific to that city)
- "Get travel insurance" → global (applies everywhere)

**Quality Guidelines:**

✅ **EXTRACT These:**
- Specific, actionable advice
- Service/app recommendations with use cases
- Practical packing tips
- Visa/entry requirements
- Safety warnings/scams to avoid
- Cultural etiquette rules
- Price ranges and budget advice
- Seasonal weather patterns

❌ **DO NOT EXTRACT These:**
- Generic advice ("be respectful", "have fun")
- Obvious information ("bring passport")
- Personal opinions without context
- Place-specific info that belongs in entity pipeline (restaurants, hotels, attractions)

**Confidence Score Guidelines:**
- 0.9-1.0: Explicit, detailed advice with context
- 0.7-0.9: Clear mention with some details
- 0.5-0.7: Implied or brief mention
- 0.3-0.5: Vague or uncertain
- 0.1-0.3: Very uncertain, may not be useful

**CRITICAL:**
- If no useful insights can be extracted, return {{"insights": []}}
- Do not fabricate insights not present in the entity
- Keep content field concise (10-200 words)
- Use details field for additional context
- Assign appropriate scope (avoid "global" unless truly universal)
"""


# =============================================================================
# Pass 2: Transcript Extraction Prompt (Info-Only Videos)
# =============================================================================

PASS2_TRANSCRIPT_EXTRACTION_PROMPT = """You are a travel knowledge extractor. Extract reusable travel insights from the video transcript below.

**Context:**
This video has very few place entities (<5), suggesting it's primarily an informational video with:
- Travel tips and advice
- Service/app recommendations
- Logistics and how-to guides
- Cultural etiquette
- Safety warnings
- Budget advice

**Video Metadata:**
- Title: {title}
- Duration: {duration_minutes} minutes
- Description: {description}
- Destination: {destination}

**Transcript Chunk:**
{transcript_chunk}

**Instructions:**
Extract 5-15 actionable travel insights from this transcript. Each insight should be:
- Destination-agnostic (avoid city/country names unless essential for scope)
- Reusable across multiple trips
- Practical and actionable

Focus on:
- Services and apps mentioned (with use cases)
- Practical packing/preparation tips
- Visa and entry requirements
- Cultural etiquette and customs
- Safety warnings and scam alerts
- Budget advice and cost information
- Weather and seasonal considerations

**Output Format:**
Return ONLY valid JSON with this exact structure (no markdown, no explanations):

{{
  "insights": [
    {{
      "category": "services",
      "content": "Use 12goasia.com to book intercity buses and trains in Southeast Asia. Shows real-time availability and prices from multiple operators.",
      "title": "12goasia for bus/train booking",
      "details": "Website and mobile app. Compare prices across operators. Payment via credit card. E-tickets sent via email. Popular in Thailand, Vietnam, Cambodia.",
      "scope": {{
        "destination_type": "region",
        "region": "Southeast Asia"
      }},
      "confidence_score": 0.90,
      "tags": ["booking", "transportation", "website"]
    }},
    {{
      "category": "tips",
      "content": "Download Google Maps offline maps before traveling to save on data usage and navigate without internet.",
      "title": "Download offline maps",
      "details": "In Google Maps app, search for destination, tap name at bottom, select 'Download offline map'. Maps stay available for 30 days. Update periodically.",
      "scope": {{
        "destination_type": "global"
      }},
      "confidence_score": 0.95,
      "tags": ["apps", "navigation", "data-saving"]
    }},
    {{
      "category": "cultural",
      "content": "Remove shoes before entering temples and private homes. It's considered disrespectful to keep them on.",
      "title": "Shoe removal etiquette",
      "details": "Look for shoe racks at entrances. Temple staff may remind you. Bring slip-on shoes for convenience. Socks are usually fine indoors.",
      "scope": {{
        "destination_type": "country",
        "country": "Thailand"
      }},
      "confidence_score": 0.92,
      "tags": ["etiquette", "temples", "culture"]
    }},
    {{
      "category": "safety",
      "content": "Watch for taxi scams at airports. Insist on using the meter or agree on a price before starting the ride.",
      "title": "Airport taxi meter scams",
      "details": "Common scam: driver claims meter is broken and quotes inflated price. Counter: walk to official taxi stand or use ride-hailing apps (Grab, Bolt). Official taxis must use meter by law in most countries.",
      "scope": {{
        "destination_type": "region",
        "region": "Southeast Asia"
      }},
      "confidence_score": 0.88,
      "tags": ["scams", "transportation", "airport"]
    }}
  ]
}}

**Insight Categories:**

1. **services** - Apps, booking platforms, tools
   - Examples: "Bolt for ride-hailing", "Grab app", "WhatsApp for local communication", "12goasia for buses"

2. **logistics** - How-to guides, visa processes, getting around
   - Examples: "Visa on arrival process", "How to take train from airport", "Buy SIM card at arrival"

3. **tips** - Practical travel advice, packing, money, local tips
   - Examples: "Pack mosquito repellent", "Bring cash for markets", "Download offline maps"

4. **regional** - Area-specific knowledge (neighborhoods, traffic, local quirks)
   - Examples: "Traffic worst during rush hour", "Markets busiest on weekends"

5. **cultural** - Customs, etiquette, dos/don'ts
   - Examples: "Remove shoes at temples", "Dress modestly", "Don't touch people's heads"

6. **safety** - Security, scams, health warnings
   - Examples: "Taxi meter scams", "Get travel insurance", "Drink bottled water"

7. **cost_info** - Price ranges, budget advice, value for money
   - Examples: "Street food $1-3", "Budget $40-60/day mid-range", "Negotiate tuk-tuk prices"

8. **seasonal** - Weather, best times to visit, seasonal considerations
   - Examples: "Rainy season June-October", "Book 3 months ahead for peak", "Hot season March-May"

**Scope Guidelines (Destination-Agnostic):**

Use the most general scope that accurately describes where the insight applies:

- **global**: Applies everywhere (e.g., "Get travel insurance")
- **region**: Applies to a region (e.g., "Southeast Asia", "Europe")
- **country**: Applies to a country (e.g., "Thailand", "Japan")
- **city**: Applies to a city (e.g., "Bangkok", "Tokyo")
- **area**: Applies to a neighborhood (e.g., "Khao San Road", "Shibuya")

**Quality Guidelines:**

✅ **EXTRACT These:**
- Specific, actionable advice with context
- Service/app recommendations (with use cases)
- Practical packing tips (with reasons)
- Visa/entry requirements (with process)
- Safety warnings (with prevention)
- Cultural rules (with explanation)
- Price ranges (with context)
- Weather patterns (with timing)

❌ **DO NOT EXTRACT These:**
- Generic advice ("be respectful", "have fun")
- Obvious information ("bring passport", "book flights")
- Personal opinions without context ("I loved it", "best place ever")
- Place-specific info (restaurants, hotels, attractions) - those go to entity pipeline
- Travel blogger self-promotion

**Confidence Score Guidelines:**
- 0.9-1.0: Explicit, detailed advice with clear context
- 0.7-0.9: Clear mention with some details
- 0.5-0.7: Implied or brief mention
- 0.3-0.5: Vague or uncertain
- 0.1-0.3: Very uncertain (avoid extracting these)

**CRITICAL:**
- Extract 5-15 insights (not too many, focus on quality)
- If <5 useful insights, return only those found
- Do not fabricate insights not in transcript
- Keep content field concise (10-200 words)
- Use details field for additional context
- Assign appropriate scope (be as general as possible)
- Avoid duplicate insights (e.g., don't extract "use Grab" twice)
"""


# =============================================================================
# Helper Functions
# =============================================================================

def format_pass1_prompt(
    entity: dict,
    video_metadata: dict
) -> str:
    """
    Format Pass 1 prompt with entity and video context.

    Args:
        entity: Filtered entity dict with canonical_name, entity_type, etc.
        video_metadata: Video dict with title, description, duration, etc.

    Returns:
        Formatted prompt string
    """
    # Extract entity fields
    entity_name = entity.get('canonical_name', 'Unknown')
    entity_type = entity.get('entity_type', 'unknown')
    filter_reason = entity.get('filter_reason', 'unknown')

    # Build location context
    city = entity.get('city', '')
    country = entity.get('country', '')
    location = entity.get('location', '')
    location_context = ', '.join(filter(None, [location, city, country])) or 'Unknown'

    # Get experience description (from any available experience)
    experiences = entity.get('experiences', [])
    if experiences and experiences[0].get('experience'):
        experience_description = experiences[0]['experience']
    else:
        experience_description = 'No experience description available'

    # Extract video metadata
    video_title = video_metadata.get('title', 'Unknown')
    duration_minutes = round(video_metadata.get('duration', 0) / 60, 1)
    video_description = video_metadata.get('description', 'No description')

    # Build destination string
    destination_parts = []
    if city and city != 'Unknown':
        destination_parts.append(city)
    if country and country != 'Unknown':
        destination_parts.append(country)
    destination = ', '.join(destination_parts) or 'Unknown'

    return PASS1_ENTITY_ENRICHMENT_PROMPT.format(
        entity_name=entity_name,
        entity_type=entity_type,
        filter_reason=filter_reason,
        location_context=location_context,
        experience_description=experience_description,
        video_title=video_title,
        duration_minutes=duration_minutes,
        video_description=video_description[:500],  # Truncate long descriptions
        destination=destination
    )


def format_pass2_prompt(
    transcript_chunk: str,
    video_metadata: dict
) -> str:
    """
    Format Pass 2 prompt with transcript chunk and video context.

    Args:
        transcript_chunk: Transcript text (may be full transcript or chunk)
        video_metadata: Video dict with title, description, duration, etc.

    Returns:
        Formatted prompt string
    """
    # Extract video metadata
    title = video_metadata.get('title', 'Unknown')
    duration_minutes = round(video_metadata.get('duration', 0) / 60, 1)
    description = video_metadata.get('description', 'No description')

    # Build destination string from video metadata
    # Try to infer from tags or title
    tags = video_metadata.get('tags', [])
    destination_tags = [tag for tag in tags if len(tag) > 3]  # Filter short tags
    if destination_tags:
        destination = ', '.join(destination_tags[:3])  # Use first 3 tags
    else:
        destination = 'Various destinations'

    return PASS2_TRANSCRIPT_EXTRACTION_PROMPT.format(
        title=title,
        duration_minutes=duration_minutes,
        description=description[:500],  # Truncate long descriptions
        destination=destination,
        transcript_chunk=transcript_chunk
    )
