#!/usr/bin/env python3
"""
RAG Narrative Generator - Transform Structured Itineraries into Engaging Stories

Converts JSON itinerary structure into human-readable, personalized narratives
that make travelers excited about their trip. Uses LLM to create flowing
storytelling while maintaining accuracy to source data.

Components:
- Title generation (catchy, personalized)
- Introduction (set expectations, build excitement)
- Day-by-day narratives (flowing storytelling)
- Conclusion (recap and encouragement)

Features:
- Tone adaptation (enthusiastic, romantic, practical, sophisticated)
- Traveler quote integration
- Length optimization
- Cost-efficient generation

Author: TravelAI Team
Date: 2025-12-20
"""


from src.utils.llm_client import extract_with_llm
from src.utils.logging import get_logger
from src.utils.schemas import (
    GeneratedItinerary,
    ItineraryDay,
    ItineraryNarrative,
    UserIntent,
    TravelerProfileInput
)

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Target lengths
TARGET_TOTAL_WORDS = 1500
TARGET_DAY_NARRATIVE_WORDS = 250

# Cost optimization
DEFAULT_PROVIDER = "deepseek"  # Cheaper for longer outputs


# =============================================================================
# NarrativeGenerator Class
# =============================================================================

class NarrativeGenerator:
    """
    Generate engaging narratives from structured itineraries.

    Transforms JSON itinerary data into flowing, personalized storytelling
    that makes travelers excited about their trip.

    Example:
        >>> generator = NarrativeGenerator()
        >>> narrative = generator.generate_narrative(itinerary, intent)
        >>> narrative.title
        'Your 5-Day Bangkok Party & Food Adventure'
        >>> len(narrative.day_narratives)
        5
    """

    def __init__(self, provider: str = DEFAULT_PROVIDER):
        """
        Initialize narrative generator.

        Args:
            provider: LLM provider ("deepseek" or "gemini")
        """
        self.provider = provider
        self.total_cost = 0.0

        logger.info("NarrativeGenerator initialized")
        logger.info(f"   Provider: {provider}")

    def generate_narrative(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent
    ) -> ItineraryNarrative:
        """
        Generate complete narrative from structured itinerary.

        Args:
            itinerary: Generated itinerary
            user_intent: User intent

        Returns:
            Complete narrative with title, intro, day narratives, and conclusion
        """
        logger.info("=" * 80)
        logger.info("📖 GENERATING NARRATIVE")
        logger.info("=" * 80)
        logger.info(f"Destination: {itinerary.destination}")
        logger.info(f"Duration: {itinerary.duration_days} days")

        start_cost = self.total_cost

        # Determine tone based on traveler profile
        tone = self.determine_tone(user_intent.traveler_profile)
        logger.info(f"Narrative tone: {tone}")

        # Part 1: Title
        logger.info("\n📝 Generating title...")
        title = self.generate_title(itinerary, user_intent)
        logger.info(f"   Title: {title}")

        # Part 2: Introduction
        logger.info("\n📝 Generating introduction...")
        introduction = self.generate_introduction(itinerary, user_intent, tone)
        logger.info(f"   Introduction: {len(introduction.split())} words")

        # Part 3: Day Narratives
        logger.info("\n📝 Generating day narratives...")
        day_narratives = []
        for day in itinerary.days:
            logger.info(f"   Day {day.day_number}: {day.theme}")
            narrative = self.generate_day_narrative(day, user_intent.traveler_profile, tone)
            day_narratives.append(narrative)
            logger.info(f"      {len(narrative.split())} words")

        # Part 4: Conclusion
        logger.info("\n📝 Generating conclusion...")
        conclusion = self.generate_conclusion(itinerary, user_intent, tone)
        logger.info(f"   Conclusion: {len(conclusion.split())} words")

        # Build narrative object
        narrative = ItineraryNarrative(
            title=title,
            introduction=introduction,
            day_narratives=day_narratives,
            conclusion=conclusion,
            tone=tone
        )

        # Calculate word count
        narrative.compute_word_count()

        # Optimize length if needed
        if narrative.word_count > TARGET_TOTAL_WORDS * 1.2:
            logger.info(f"\n⚠️  Narrative too long ({narrative.word_count} words), optimizing...")
            narrative = self.optimize_narrative_length(narrative, TARGET_TOTAL_WORDS)

        generation_cost = self.total_cost - start_cost

        logger.info("\n" + "=" * 80)
        logger.info("✅ NARRATIVE GENERATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Word count: {narrative.word_count}")
        logger.info(f"Tone: {narrative.tone}")
        logger.info(f"Generation cost: ${generation_cost:.6f}")

        return narrative

    def generate_title(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent
    ) -> str:
        """
        Generate catchy, personalized title.

        Args:
            itinerary: Generated itinerary
            user_intent: User intent

        Returns:
            Title string
        """
        # Build prompt
        profile_desc = self._build_profile_description(user_intent.traveler_profile)

        prompt = f"""Create an exciting, personalized title for this travel itinerary:

- Traveler: {profile_desc}
- Destination: {itinerary.destination}
- Duration: {itinerary.duration_days} days
- Vibe: {itinerary.overall_vibe}
- Highlights: {', '.join(itinerary.highlights[:3])}

Format: "Your X-Day [Destination] [Vibe] Adventure"

Examples:
- "Your 5-Day Bangkok Party & Food Adventure"
- "Your Romantic 3-Day Phuket Beach Escape"
- "Your Cultural 7-Day Northern Thailand Journey"

Make it personal (use "Your"), exciting, and specific.

Return as JSON with a single field "title" containing just the title string."""

        # Call LLM
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            temperature=0.7,
            max_tokens=50
        )

        self.total_cost += result['cost_usd']

        if result['success']:
            # Extract clean title from JSON response
            data = result.get('data', '')
            # Handle both string and dict responses
            if isinstance(data, dict):
                # If it's a dict, look for common keys
                title = data.get('title') or data.get('response') or data.get('text') or str(data)
            else:
                # If it's a string, use it directly
                title = str(data)

            # Remove quotes if present
            title = title.strip().strip('"').strip("'").strip()
            return title
        else:
            # Fallback
            return f"Your {itinerary.duration_days}-Day {itinerary.destination} Adventure"

    def generate_introduction(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent,
        tone: str
    ) -> str:
        """
        Generate personalized introduction.

        Args:
            itinerary: Generated itinerary
            user_intent: User intent
            tone: Narrative tone

        Returns:
            Introduction text (2-3 paragraphs)
        """
        profile_desc = self._build_profile_description(user_intent.traveler_profile)
        highlights = ', '.join(itinerary.highlights[:5])

        prompt = f"""Write a personalized introduction (2-3 paragraphs) for this travel itinerary:

Traveler profile: {profile_desc}
Destination: {itinerary.destination}
Duration: {itinerary.duration_days} days
Key experiences: {highlights}
Budget: {itinerary.total_budget_estimate}
Vibe: {itinerary.overall_vibe}
Data quality: Based on {itinerary.sources_used} traveler experiences

Structure:
1. Acknowledge who they are and what they want
2. Preview what makes this itinerary special FOR THEM
3. Set expectations (vibe, pace, budget)

Tone: {tone}
Use "you" to make it personal. Reference their specific interests.

Example:
"You're a solo traveler on a budget who loves to party and meet people - this Bangkok itinerary is designed specifically for travelers like you. Over 5 days, you'll experience the best of Bangkok's legendary nightlife scene while staying well within your $50/day budget. Based on experiences from 15 fellow solo travelers, this plan balances late-night parties with amazing street food and just enough culture to round things out.

Expect a fast-paced, social adventure where you'll make friends from around the world. We've built in hostel stays in the heart of the action and picked places where other backpackers gather. Get ready for an unforgettable trip!"

Write 2-3 paragraphs for this traveler.

Return as JSON with a single field "introduction" containing the full introduction text."""

        # Call LLM
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            temperature=0.7,
            max_tokens=300
        )

        self.total_cost += result['cost_usd']

        if result['success']:
            # Extract introduction from JSON response
            data = result.get('data', '')
            # Handle both string and dict responses
            if isinstance(data, dict):
                intro = data.get('introduction') or data.get('intro') or data.get('response') or data.get('text') or str(data)
            else:
                intro = str(data)

            return intro.strip()
        else:
            # Fallback
            return f"This {itinerary.duration_days}-day {itinerary.destination} itinerary is designed for {profile_desc}. You'll experience {highlights} while staying within your budget."

    def generate_day_narrative(
        self,
        day: ItineraryDay,
        profile: TravelerProfileInput,
        tone: str
    ) -> str:
        """
        Generate engaging narrative for a single day.

        Args:
            day: Itinerary day
            profile: Traveler profile
            tone: Narrative tone

        Returns:
            Day narrative text
        """
        # Format activities
        activities_text = self.format_day_activities(day)
        profile_desc = self._build_profile_description(profile)

        prompt = f"""Write an engaging narrative for Day {day.day_number} of a trip.

Day theme: {day.theme}
Budget: {day.daily_budget_estimate}

Activities:
{activities_text}

Traveler profile: {profile_desc}

Structure:
- Start with day theme/overview (1 sentence)
- Flow through activities naturally (morning → afternoon → evening → night)
- For each activity:
  * What you'll do
  * Why it's great for THIS traveler
  * Include traveler quotes when available
  * Practical tips
- End with what makes this day special

Tone: {tone}, conversational, use "you"
Length: 200-300 words

Return as JSON with a single field "narrative" containing the full day narrative text."""

        # Call LLM
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            temperature=0.7,
            max_tokens=400
        )

        self.total_cost += result['cost_usd']

        if result['success']:
            # Extract day narrative from JSON response
            data = result.get('data', '')
            # Handle both string and dict responses
            if isinstance(data, dict):
                narrative = data.get('narrative') or data.get('response') or data.get('text') or str(data)
            else:
                narrative = str(data)

            return narrative.strip()
        else:
            # Fallback - template-based
            return self._generate_day_narrative_template(day, profile)

    def generate_conclusion(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent,
        tone: str
    ) -> str:
        """
        Generate conclusion wrapping up the itinerary.

        Args:
            itinerary: Generated itinerary
            user_intent: User intent
            tone: Narrative tone

        Returns:
            Conclusion text (2 paragraphs)
        """
        profile_desc = self._build_profile_description(user_intent.traveler_profile)
        highlights = ', '.join(itinerary.highlights[:3])

        prompt = f"""Write a conclusion (2 paragraphs) wrapping up this {itinerary.duration_days}-day itinerary.

Destination: {itinerary.destination}
Highlights covered: {highlights}
Traveler profile: {profile_desc}
Budget: {itinerary.total_budget_estimate}

Structure:
1. Recap what makes this itinerary special
2. Final practical tips and encouragement
3. Invite them to adjust based on their energy/mood

Tone: {tone}, encouraging, practical, personal

Example:
"This itinerary packs the best of Bangkok's party scene and street food into 5 unforgettable days, all while keeping you well under budget. You'll experience the places that solo travelers like you consistently rave about, from the social chaos of Khao San Road to the rooftop bars of Sukhumvit.

Remember, this is a guide, not a rigid schedule. If you meet amazing people and want to change plans, do it! That's what solo travel is about. Just keep your budget in mind, stay safe (always watch your drinks), and embrace the adventure. Fellow travelers have walked this path before you and loved it - now it's your turn. Have an incredible trip!"

Write 2 paragraphs.

Return as JSON with a single field "conclusion" containing the full conclusion text."""

        # Call LLM
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            temperature=0.7,
            max_tokens=250
        )

        self.total_cost += result['cost_usd']

        if result['success']:
            # Extract conclusion from JSON response
            data = result.get('data', '')
            # Handle both string and dict responses
            if isinstance(data, dict):
                conclusion = data.get('conclusion') or data.get('response') or data.get('text') or str(data)
            else:
                conclusion = str(data)

            return conclusion.strip()
        else:
            # Fallback
            return f"This {itinerary.duration_days}-day itinerary offers the best of {itinerary.destination} tailored to your interests. Enjoy your adventure!"

    def determine_tone(self, profile: TravelerProfileInput) -> str:
        """
        Determine narrative tone based on traveler profile.

        Args:
            profile: Traveler profile

        Returns:
            Tone string
        """
        # Check travel style
        travel_style = [s.lower() for s in profile.travel_style]

        if "party" in travel_style or "nightlife" in travel_style:
            return "enthusiastic"
        elif profile.traveler_type == "couple":
            return "romantic"
        elif profile.traveler_type == "family":
            return "practical"
        elif profile.budget_tier == "luxury":
            return "sophisticated"
        elif "adventure" in travel_style or "active" in travel_style:
            return "energetic"
        else:
            return "casual"

    def format_day_activities(self, day: ItineraryDay) -> str:
        """
        Format day activities for narrative generation.

        Args:
            day: Itinerary day

        Returns:
            Formatted activities text
        """
        lines = []

        for slot in day.get_time_slots():
            lines.append(f"{slot.time_period.value.title()}: {slot.entity_name} ({slot.entity_type})")
            lines.append(f"  - {slot.activity_description}")
            lines.append(f"  - Why: {slot.why_this_works}")
            lines.append(f"  - Duration: {slot.estimated_duration}")

            if slot.estimated_cost:
                lines.append(f"  - Cost: {slot.estimated_cost}")

            if slot.traveler_quotes:
                lines.append(f"  - Quote: {slot.traveler_quotes[0]}")

            if slot.tips:
                lines.append(f"  - Tips: {', '.join(slot.tips[:2])}")

            lines.append("")

        return "\n".join(lines)

    def optimize_narrative_length(
        self,
        narrative: ItineraryNarrative,
        target_words: int
    ) -> ItineraryNarrative:
        """
        Optimize narrative length to target word count.

        Args:
            narrative: Narrative to optimize
            target_words: Target word count

        Returns:
            Optimized narrative
        """
        current_words = narrative.word_count

        if current_words <= target_words:
            return narrative

        # Calculate reduction needed
        reduction_ratio = target_words / current_words

        logger.info(f"   Reducing from {current_words} to ~{target_words} words")

        # Reduce day narratives proportionally
        optimized_day_narratives = []
        for day_narrative in narrative.day_narratives:
            # Simple truncation (in production, would use LLM to compress intelligently)
            words = day_narrative.split()
            target_day_words = int(len(words) * reduction_ratio)
            optimized = ' '.join(words[:target_day_words])
            optimized_day_narratives.append(optimized)

        narrative.day_narratives = optimized_day_narratives
        narrative.compute_word_count()

        return narrative

    def _build_profile_description(self, profile: TravelerProfileInput) -> str:
        """Build human-readable profile description."""
        parts = []

        # Type and age
        if profile.age_range:
            parts.append(f"{profile.age_range} {profile.traveler_type}")
        else:
            parts.append(profile.traveler_type)

        # Budget
        parts.append(f"{profile.budget_tier} budget")

        # Style
        if profile.travel_style:
            styles = ', '.join(profile.travel_style[:2])
            parts.append(f"loves {styles}")

        return ' '.join(parts)

    def _generate_day_narrative_template(
        self,
        day: ItineraryDay,
        profile: TravelerProfileInput
    ) -> str:
        """Generate day narrative using template (fallback)."""
        narrative_parts = [f"Day {day.day_number}: {day.theme}"]

        slots = day.get_time_slots()

        for i, slot in enumerate(slots):
            period = slot.time_period.value.title()

            if i == 0:
                narrative_parts.append(
                    f"{period}: Start your day at {slot.entity_name}. {slot.activity_description}"
                )
            elif i == len(slots) - 1:
                narrative_parts.append(
                    f"{period}: End your day at {slot.entity_name}. {slot.activity_description}"
                )
            else:
                narrative_parts.append(
                    f"{period}: Next, visit {slot.entity_name}. {slot.activity_description}"
                )

            if slot.tips:
                narrative_parts.append(f"Tip: {slot.tips[0]}")

        narrative_parts.append(f"\nBudget for today: {day.daily_budget_estimate}")

        return " ".join(narrative_parts)


# =============================================================================
# Testing Function
# =============================================================================

def test_narrative_generator():
    """Test narrative generator with sample itinerary."""
    from src.utils.schemas import example_stage5_generated_itinerary

    logger.info("=" * 80)
    logger.info("🧪 TESTING NARRATIVE GENERATOR")
    logger.info("=" * 80)

    # Create sample itinerary
    itinerary = example_stage5_generated_itinerary()

    # Initialize generator
    generator = NarrativeGenerator(provider="gemini")

    # Generate narrative
    narrative = generator.generate_narrative(itinerary, itinerary.user_intent)

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("📖 GENERATED NARRATIVE")
    logger.info("=" * 80)
    logger.info(f"\nTitle: {narrative.title}")
    logger.info(f"Tone: {narrative.tone}")
    logger.info(f"Word count: {narrative.word_count}")

    logger.info(f"\nIntroduction ({len(narrative.introduction.split())} words):")
    logger.info(narrative.introduction[:200] + "...")

    logger.info("\nDay Narratives:")
    for i, day_narrative in enumerate(narrative.day_narratives, 1):
        word_count = len(day_narrative.split())
        logger.info(f"   Day {i}: {word_count} words")
        logger.info(f"   {day_narrative[:100]}...")

    logger.info(f"\nConclusion ({len(narrative.conclusion.split())} words):")
    logger.info(narrative.conclusion[:200] + "...")

    logger.info(f"\nTotal cost: ${generator.total_cost:.6f}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ NARRATIVE GENERATOR TESTING COMPLETE")
    logger.info("=" * 80)

    # Validation
    assert narrative.title
    assert len(narrative.introduction) > 50
    assert len(narrative.day_narratives) == itinerary.duration_days
    assert len(narrative.conclusion) > 50
    assert narrative.word_count > 0

    logger.info("\n✅ All validation checks passed")

    return narrative


if __name__ == "__main__":
    test_narrative_generator()
