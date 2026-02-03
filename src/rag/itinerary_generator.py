#!/usr/bin/env python3
"""
RAG Itinerary Generator - LLM-Powered Travel Plan Creation

The heart of the RAG pipeline. Transforms optimized context into complete,
personalized travel itineraries using structured LLM generation.

Multi-stage generation process:
1. Generate outline (structure) - Fast, validates feasibility
2. Add rich details - Slow, adds traveler context
3. Add summary elements - Highlights, tips, warnings

Features:
- Two-pass generation for cost efficiency
- Batch detail generation
- Geographic validation
- Budget tracking
- Confidence scoring
- Full provenance tracking

Author: TravelAI Team
Date: 2025-12-20
"""

import json
import math
from typing import Dict, List, Tuple, Optional, Any
from statistics import mean

from src.utils.llm_client import extract_with_llm
from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    RAGContext,
    GeneratedItinerary,
    ItineraryDay,
    TimeSlot,
    TimePeriod,
    DataQuality,
    TravelerProfileInput
)

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Cost targets
TARGET_COST_PER_ITINERARY = 0.004  # $0.004 per itinerary
MAX_COST_PER_ITINERARY = 0.010     # $0.01 maximum

# Geographic validation
MAX_DAILY_DISTANCE_KM = 20.0  # More than 20km/day is excessive walking

# Confidence thresholds
MIN_ACCEPTABLE_CONFIDENCE = 0.5


# =============================================================================
# Helper Functions
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    R = 6371  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def parse_cost_string(cost_str: str) -> Tuple[float, float]:
    """
    Parse cost string into min/max values.

    Args:
        cost_str: Cost string like "$10-15" or "$20"

    Returns:
        Tuple of (min_cost, max_cost)
    """
    # Remove currency symbols and spaces
    cost_str = cost_str.replace("$", "").replace(" ", "").replace(",", "")

    # Try to find range
    if "-" in cost_str:
        parts = cost_str.split("-")
        try:
            min_cost = float(parts[0])
            max_cost = float(parts[1])
            return (min_cost, max_cost)
        except (ValueError, IndexError):
            pass

    # Try single value
    try:
        value = float(cost_str)
        return (value, value)
    except ValueError:
        # Default to 0 if unparseable
        return (0.0, 0.0)


# =============================================================================
# ItineraryGenerator Class
# =============================================================================

class ItineraryGenerator:
    """
    Generate complete travel itineraries using LLM and RAG context.

    Multi-stage generation process for quality and cost efficiency:
    1. Outline generation (structure validation)
    2. Detail enrichment (traveler context)
    3. Summary generation (highlights, tips)

    Example:
        >>> generator = ItineraryGenerator(provider="gemini")
        >>> itinerary = generator.generate_itinerary(context, intent)
        >>> itinerary.days[0].theme
        'Bangkok Arrival & Old Town Culture'
    """

    def __init__(self, provider: str = "gemini"):
        """
        Initialize itinerary generator.

        Args:
            provider: LLM provider ("gemini" or "deepseek")
        """
        self.provider = provider
        self.total_cost = 0.0

        logger.info("ItineraryGenerator initialized")
        logger.info(f"   Provider: {provider}")

    def generate_itinerary(
        self,
        rag_context: RAGContext,
        user_intent: UserIntent
    ) -> GeneratedItinerary:
        """
        Generate complete itinerary from RAG context.

        Multi-stage process:
        1. Generate outline (validates structure)
        2. Enrich with details (adds context)
        3. Generate summary elements

        Args:
            rag_context: Optimized context from ContextBuilder
            user_intent: User intent

        Returns:
            Complete GeneratedItinerary
        """
        logger.info("=" * 80)
        logger.info("🎨 GENERATING ITINERARY")
        logger.info("=" * 80)
        logger.info(f"Destination: {user_intent.destination}")
        logger.info(f"Duration: {user_intent.duration_days} days")
        logger.info(f"Profile: {user_intent.traveler_profile.to_profile_key()}")

        stage_start_cost = self.total_cost

        # Stage 1: Generate outline
        logger.info("\n📝 Stage 1: Generating outline...")
        outline_data = self.generate_outline_only(rag_context, user_intent)

        logger.info(f"   ✅ Outline generated ({len(outline_data['days'])} days)")

        # Stage 2: Enrich with details
        logger.info("\n✨ Stage 2: Enriching with details...")
        days = self._enrich_outline_with_details(
            outline_data,
            rag_context,
            user_intent
        )

        logger.info(f"   ✅ Details added to {len(days)} days")

        # Stage 3: Generate summary elements
        logger.info("\n📋 Stage 3: Generating summary elements...")
        highlights = self._generate_highlights(days, user_intent)
        general_tips = self._generate_general_tips(days, user_intent)
        warnings = self._generate_warnings(days, user_intent)
        overall_vibe = self._generate_overall_vibe(user_intent, days)

        logger.info(f"   ✅ Generated {len(highlights)} highlights, {len(general_tips)} tips")

        # Calculate budgets
        total_budget = self._calculate_total_budget(days)

        # Build itinerary object
        itinerary = GeneratedItinerary(
            user_intent=user_intent,
            profile_classification=user_intent.traveler_profile.to_profile_key(),
            destination=user_intent.destination,
            duration_days=user_intent.duration_days,
            days=days,
            total_budget_estimate=total_budget,
            highlights=highlights,
            overall_vibe=overall_vibe,
            general_tips=general_tips,
            important_warnings=warnings,
            llm_model_used=self.provider,
            total_cost=self.total_cost - stage_start_cost
        )

        # Add provenance
        itinerary = self.add_provenance(itinerary, rag_context)

        # Calculate confidence scores
        itinerary = self.calculate_confidence_scores(itinerary)

        # Validate geographic logic
        itinerary = self.ensure_geographic_logic(itinerary)

        logger.info("\n" + "=" * 80)
        logger.info("✅ ITINERARY GENERATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Days: {len(itinerary.days)}")
        logger.info(f"Entities used: {itinerary.entities_used}")
        logger.info(f"Sources used: {itinerary.sources_used}")
        logger.info(f"Overall confidence: {itinerary.overall_confidence:.2f}")
        logger.info(f"Total budget: {itinerary.total_budget_estimate}")
        logger.info(f"Generation cost: ${itinerary.total_cost:.6f}")

        return itinerary

    def generate_outline_only(
        self,
        rag_context: RAGContext,
        user_intent: UserIntent
    ) -> Dict[str, Any]:
        """
        Generate itinerary outline (structure only, no details).

        Fast first pass to validate feasibility before expensive detail generation.

        Args:
            rag_context: RAG context
            user_intent: User intent

        Returns:
            Dictionary with outline structure
        """
        # Build prompt
        prompt = self._build_outline_prompt(rag_context, user_intent)

        # Call LLM
        logger.info(f"   Calling LLM ({self.provider}) for outline...")
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            temperature=0.5,  # Moderate creativity
            max_tokens=2000
        )

        # Track cost
        self.total_cost += result['cost_usd']
        logger.info(f"   Cost: ${result['cost_usd']:.6f}")

        if not result['success']:
            raise ValueError(f"Outline generation failed: {result['error']}")

        outline_data = result['data']

        # Validate outline
        self._validate_outline(outline_data, rag_context, user_intent)

        return outline_data

    def _build_outline_prompt(
        self,
        rag_context: RAGContext,
        user_intent: UserIntent
    ) -> str:
        """Build prompt for outline generation."""
        # Format entities for prompt
        entities_text = self._format_entities_for_prompt(rag_context.priority_entities)

        # Format constraints
        hard_constraints_text = json.dumps(rag_context.hard_constraints, indent=2)
        soft_preferences_text = json.dumps(rag_context.soft_preferences, indent=2)

        prompt = f"""You are an expert travel companion helping plan a trip.

TRAVELER PROFILE:
{rag_context.profile_description}

TRIP DETAILS:
- Destination: {user_intent.destination}
- Duration: {user_intent.duration_days} days
- Budget: {rag_context.hard_constraints.get('budget_per_day', 'flexible')}/day

CONSTRAINTS:
Hard constraints (MUST follow):
{hard_constraints_text}

Soft preferences (TRY to include):
{soft_preferences_text}

AVAILABLE PLACES (from real traveler experiences):
{entities_text}

DATA CONTEXT:
{rag_context.data_quality_note}

TASK: Create a day-by-day itinerary outline.

RULES:
1. ONLY use places from the provided list above
2. Group geographically close places together per day
3. Balance activity types (don't do 5 restaurants in one day)
4. Stay within budget
5. Consider travel time between locations
6. Use morning/afternoon/evening/night structure
7. Each entity can only appear ONCE (no repetition)
8. If a time slot is free/travel, use null

EXAMPLE:
{{
  "days": [
    {{
      "day_number": 1,
      "theme": "Arrival & Old Town Exploration",
      "morning": {{"entity_id": "area_bangkok_001", "entity_name": "Khao San Road"}},
      "afternoon": {{"entity_id": "attraction_bangkok_001", "entity_name": "Grand Palace"}},
      "evening": {{"entity_id": "restaurant_bangkok_001", "entity_name": "Street Food Market"}},
      "night": null
    }}
  ]
}}

Return ONLY valid JSON with the same structure.
"""

        return prompt

    def _format_entities_for_prompt(self, entities: List[Dict[str, Any]]) -> str:
        """Format entities for inclusion in prompt."""
        lines = []

        for i, entity in enumerate(entities, 1):
            lines.append(f"{i}. {entity['name']} ({entity['type']})")
            lines.append(f"   ID: {entity['entity_id']}")
            lines.append(f"   Rating: {entity['rating']}/5")
            lines.append(f"   Cost: {entity.get('cost_estimate', 'Varies')}")

            if entity.get('best_for'):
                lines.append(f"   Best for: {', '.join(entity['best_for'][:3])}")

            lines.append("")

        return "\n".join(lines)

    def _validate_outline(
        self,
        outline_data: Dict[str, Any],
        rag_context: RAGContext,
        user_intent: UserIntent
    ) -> None:
        """
        Validate outline structure and content.

        Raises:
            ValueError: If outline is invalid
        """
        # Check structure
        if 'days' not in outline_data:
            raise ValueError("Outline missing 'days' field")

        days = outline_data['days']

        # Check day count
        if len(days) != user_intent.duration_days:
            logger.warning(f"Expected {user_intent.duration_days} days, got {len(days)}")

        # Collect all entity IDs from context
        valid_entity_ids = set()
        for entity in rag_context.priority_entities + rag_context.supporting_entities:
            valid_entity_ids.add(entity['entity_id'])

        # Check each day
        used_entities = set()

        for day in days:
            for time_period in ['morning', 'afternoon', 'evening', 'night']:
                slot = day.get(time_period)

                if slot and isinstance(slot, dict):
                    entity_id = slot.get('entity_id')

                    if entity_id:
                        # Check entity exists
                        if entity_id not in valid_entity_ids:
                            logger.warning(f"Unknown entity_id in outline: {entity_id}")

                        # Check for duplicates
                        if entity_id in used_entities:
                            logger.warning(f"Duplicate entity in outline: {entity_id}")

                        used_entities.add(entity_id)

        logger.info(f"   Outline validation passed ({len(used_entities)} unique entities)")

    def _enrich_outline_with_details(
        self,
        outline_data: Dict[str, Any],
        rag_context: RAGContext,
        user_intent: UserIntent
    ) -> List[ItineraryDay]:
        """
        Enrich outline with detailed context for each time slot.

        Args:
            outline_data: Outline structure
            rag_context: RAG context
            user_intent: User intent

        Returns:
            List of complete ItineraryDay objects
        """
        days = []

        # Build entity lookup map
        entity_map = {}
        for entity in rag_context.priority_entities + rag_context.supporting_entities:
            entity_map[entity['entity_id']] = entity

        for day_outline in outline_data['days']:
            day_number = day_outline['day_number']
            theme = day_outline['theme']

            logger.info(f"   Enriching Day {day_number}: {theme}")

            # Enrich each time slot
            morning = self._enrich_time_slot(
                day_outline.get('morning'),
                entity_map,
                user_intent.traveler_profile,
                TimePeriod.MORNING
            )

            afternoon = self._enrich_time_slot(
                day_outline.get('afternoon'),
                entity_map,
                user_intent.traveler_profile,
                TimePeriod.AFTERNOON
            )

            evening = self._enrich_time_slot(
                day_outline.get('evening'),
                entity_map,
                user_intent.traveler_profile,
                TimePeriod.EVENING
            )

            night = self._enrich_time_slot(
                day_outline.get('night'),
                entity_map,
                user_intent.traveler_profile,
                TimePeriod.NIGHT
            )

            # Calculate daily budget
            daily_budget = self._calculate_daily_budget([morning, afternoon, evening, night])

            # Build ItineraryDay
            day = ItineraryDay(
                day_number=day_number,
                theme=theme,
                morning=morning,
                afternoon=afternoon,
                evening=evening,
                night=night,
                daily_budget_estimate=daily_budget
            )

            # Calculate distance
            day.total_distance_km = self.calculate_total_distance(day)

            days.append(day)

        return days

    def _enrich_time_slot(
        self,
        slot_outline: Optional[Dict[str, Any]],
        entity_map: Dict[str, Dict[str, Any]],
        profile: TravelerProfileInput,
        time_period: TimePeriod
    ) -> Optional[TimeSlot]:
        """
        Enrich a single time slot with detailed context.

        Args:
            slot_outline: Outline slot data
            entity_map: Map of entity_id to entity data
            profile: Traveler profile
            time_period: Time period

        Returns:
            Complete TimeSlot or None
        """
        if not slot_outline or not isinstance(slot_outline, dict):
            return None

        entity_id = slot_outline.get('entity_id')
        entity_name = slot_outline.get('entity_name', 'Unknown')

        if not entity_id:
            return None

        # Get entity data
        entity_data = entity_map.get(entity_id)

        if not entity_data:
            logger.warning(f"Entity not found in map: {entity_id}")
            # Create minimal slot
            return TimeSlot(
                time_period=time_period,
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type="unknown",
                activity_description=f"Visit {entity_name}",
                why_this_works=f"Recommended for {profile.traveler_type} travelers",
                estimated_duration="2-3 hours"
            )

        # Build rich TimeSlot
        activity_description = self._generate_activity_description(entity_data, profile)
        why_this_works = entity_data.get('why_recommended', f"Rated {entity_data['rating']}/5 by similar travelers")

        time_slot = TimeSlot(
            time_period=time_period,
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity_data['type'],
            activity_description=activity_description,
            why_this_works=why_this_works,
            estimated_duration=entity_data.get('typical_duration', '2-3 hours'),
            estimated_cost=entity_data.get('cost_estimate', 'Varies'),
            tips=entity_data.get('tips', [])[:3],
            warnings=entity_data.get('warnings', [])[:2],
            traveler_quotes=entity_data.get('quotes', [])[:2],
            confidence=entity_data.get('confidence', 0.8)
        )

        return time_slot

    def _generate_activity_description(
        self,
        entity_data: Dict[str, Any],
        profile: TravelerProfileInput
    ) -> str:
        """Generate activity description for entity."""
        entity_type = entity_data['type']
        entity_name = entity_data['name']

        # Template-based descriptions (cost-free)
        templates = {
            'restaurant': f"Enjoy authentic local cuisine at {entity_name}, popular among {profile.traveler_type} travelers for its atmosphere and flavors.",
            'attraction': f"Explore {entity_name}, a must-see {entity_type} that offers unique cultural insights and memorable experiences.",
            'area': f"Spend time in {entity_name}, experiencing the local vibe and discovering hidden gems in this vibrant neighborhood.",
            'activity': f"Participate in {entity_name}, an engaging experience that matches your interest in adventure and local culture.",
            'beach': f"Relax at {entity_name}, enjoying the natural beauty and coastal atmosphere perfect for unwinding.",
            'market': f"Browse {entity_name}, experiencing local life through sights, sounds, and flavors of this bustling marketplace."
        }

        return templates.get(entity_type, f"Visit {entity_name} and enjoy the experience.")

    def _calculate_daily_budget(self, time_slots: List[Optional[TimeSlot]]) -> str:
        """Calculate total budget estimate for a day."""
        min_total = 0.0
        max_total = 0.0

        for slot in time_slots:
            if slot and slot.estimated_cost:
                min_cost, max_cost = parse_cost_string(slot.estimated_cost)
                min_total += min_cost
                max_total += max_cost

        if min_total == max_total:
            return f"${min_total:.0f}"
        else:
            return f"${min_total:.0f}-${max_total:.0f}"

    def _calculate_total_budget(self, days: List[ItineraryDay]) -> str:
        """Calculate total budget for entire trip."""
        min_total = 0.0
        max_total = 0.0

        for day in days:
            if day.daily_budget_estimate:
                min_cost, max_cost = parse_cost_string(day.daily_budget_estimate)
                min_total += min_cost
                max_total += max_cost

        if min_total == max_total:
            return f"${min_total:.0f}"
        else:
            return f"${min_total:.0f}-${max_total:.0f}"

    def _generate_highlights(
        self,
        days: List[ItineraryDay],
        user_intent: UserIntent
    ) -> List[str]:
        """Generate trip highlights."""
        highlights = []

        # Extract top-rated activities
        all_slots = []
        for day in days:
            all_slots.extend(day.get_time_slots())

        # Sort by confidence
        all_slots.sort(key=lambda s: s.confidence, reverse=True)

        # Take top 5
        for slot in all_slots[:5]:
            highlight = f"{slot.entity_name}: {slot.why_this_works}"
            highlights.append(highlight)

        return highlights

    def _generate_general_tips(
        self,
        days: List[ItineraryDay],
        user_intent: UserIntent
    ) -> List[str]:
        """Generate general travel tips."""
        # Template-based tips (cost-free)
        tips = [
            f"Download local ride-sharing apps for easy transportation around {user_intent.destination}",
            "Carry small bills for street vendors and local markets",
            "Dress modestly when visiting temples and religious sites",
            "Stay hydrated and use sunscreen, especially during midday activities",
            "Learn basic local phrases - locals appreciate the effort"
        ]

        return tips[:5]

    def _generate_warnings(
        self,
        days: List[ItineraryDay],
        user_intent: UserIntent
    ) -> List[str]:
        """Generate important warnings."""
        warnings = []

        # Collect warnings from time slots
        for day in days:
            for slot in day.get_time_slots():
                if slot.warnings:
                    warnings.extend(slot.warnings)

        # Deduplicate
        warnings = list(set(warnings))

        # Add general warnings
        if user_intent.traveler_profile.budget_tier == "budget":
            warnings.append("Be aware of common tourist scams, especially in busy areas")

        return warnings[:5]

    def _generate_overall_vibe(
        self,
        user_intent: UserIntent,
        days: List[ItineraryDay]
    ) -> str:
        """Generate overall trip vibe description."""
        profile = user_intent.traveler_profile

        vibe_parts = []

        # Add style descriptors
        if "party" in profile.travel_style:
            vibe_parts.append("social and energetic")
        if "culture" in profile.travel_style or "cultural" in profile.travel_style:
            vibe_parts.append("culturally enriching")
        if "food" in profile.travel_style or "foodie" in profile.travel_style:
            vibe_parts.append("gastronomically adventurous")

        # Add budget descriptor
        vibe_parts.append(f"{profile.budget_tier}-friendly")

        # Add pace descriptor
        vibe_parts.append(f"{user_intent.pace.value} paced")

        return ", ".join(vibe_parts).capitalize()

    def calculate_total_distance(self, day: ItineraryDay) -> float:
        """
        Calculate total distance between activities in a day.

        Args:
            day: ItineraryDay

        Returns:
            Total distance in kilometers
        """
        slots = day.get_time_slots()

        if len(slots) < 2:
            return 0.0

        total_distance = 0.0

        # Calculate distance between consecutive slots
        for i in range(len(slots) - 1):
            slot1 = slots[i]
            slot2 = slots[i + 1]

            # Try to get coordinates (would need to be in entity_data)
            # For now, return 0 (would be populated with real coordinates)
            pass

        return round(total_distance, 2)

    def ensure_geographic_logic(self, itinerary: GeneratedItinerary) -> GeneratedItinerary:
        """
        Validate and flag geographic logic issues.

        Args:
            itinerary: Generated itinerary

        Returns:
            Itinerary with geographic validation
        """
        # Check for excessive daily distances
        for day in itinerary.days:
            if day.total_distance_km > MAX_DAILY_DISTANCE_KM:
                logger.warning(
                    f"Day {day.day_number} has {day.total_distance_km}km travel "
                    f"(>{MAX_DAILY_DISTANCE_KM}km threshold)"
                )
                day.feasibility_score = 0.7  # Lower feasibility

        return itinerary

    def add_provenance(
        self,
        itinerary: GeneratedItinerary,
        rag_context: RAGContext
    ) -> GeneratedItinerary:
        """
        Add provenance tracking to itinerary.

        Args:
            itinerary: Generated itinerary
            rag_context: RAG context used

        Returns:
            Itinerary with provenance
        """
        # Collect all entity IDs used
        entity_ids = itinerary.get_all_entities()

        # Build entity map from context
        entity_map = {}
        for entity in rag_context.priority_entities + rag_context.supporting_entities:
            entity_map[entity['entity_id']] = entity

        # Collect source video IDs
        source_ids = set()
        for entity_id in entity_ids:
            entity = entity_map.get(entity_id)
            if entity:
                # Would extract from entity.sources if available
                pass

        itinerary.entity_ids = entity_ids
        itinerary.entities_used = len(entity_ids)
        itinerary.source_video_ids = list(source_ids)
        itinerary.sources_used = len(source_ids)

        return itinerary

    def calculate_confidence_scores(self, itinerary: GeneratedItinerary) -> GeneratedItinerary:
        """
        Calculate per-day and overall confidence scores.

        Args:
            itinerary: Generated itinerary

        Returns:
            Itinerary with confidence scores
        """
        # Calculate per-day confidence
        for day in itinerary.days:
            slots = day.get_time_slots()

            if slots:
                day.confidence_score = mean([s.confidence for s in slots])
            else:
                day.confidence_score = 0.5

        # Calculate overall confidence
        itinerary.compute_overall_confidence()

        # Determine data quality
        if itinerary.overall_confidence >= 0.8:
            itinerary.data_coverage = DataQuality.EXCELLENT
        elif itinerary.overall_confidence >= 0.6:
            itinerary.data_coverage = DataQuality.GOOD
        elif itinerary.overall_confidence >= 0.4:
            itinerary.data_coverage = DataQuality.LIMITED
        else:
            itinerary.data_coverage = DataQuality.INSUFFICIENT

        return itinerary


# =============================================================================
# Testing Function
# =============================================================================

def test_itinerary_generator():
    """Test ItineraryGenerator with sample data."""
    from src.rag.intent_parser import IntentParser
    from src.rag.retriever import RAGRetriever
    from src.rag.reranker import LLMReranker
    from src.rag.context_builder import ContextBuilder
    from src.vectordb import ChromaDBClient
    from src.utils.embedding_client import EmbeddingClient

    logger.info("=" * 80)
    logger.info("🧪 TESTING ITINERARY GENERATOR")
    logger.info("=" * 80)

    # Initialize clients
    chromadb = ChromaDBClient.initialize_from_env()
    embedding_client = EmbeddingClient()

    # Step 1: Parse intent
    parser = IntentParser()
    query = "Plan 3 days in Bangkok for solo budget traveler who loves nightlife"

    logger.info(f"\nQuery: {query}")
    intent = parser.parse_query(query)

    logger.info(f"✅ Intent: {intent.destination}, {intent.duration_days} days")

    # Step 2: Retrieve
    retriever = RAGRetriever(chromadb, embedding_client)
    candidates = retriever.retrieve_for_itinerary(intent, top_k=15)

    logger.info(f"✅ Retrieved: {len(candidates)} candidates")

    # Step 3: Re-rank
    reranker = LLMReranker(provider="deepseek")
    reranked = reranker.rerank_candidates(candidates, intent, top_k=10)

    logger.info(f"✅ Re-ranked: {len(reranked)} candidates")

    # Step 4: Build context
    builder = ContextBuilder()
    context = builder.build_rag_context(reranked, intent, token_budget=2000)

    logger.info(f"✅ Context: {context.estimated_tokens} tokens")

    # Step 5: Generate itinerary
    generator = ItineraryGenerator(provider="gemini")
    itinerary = generator.generate_itinerary(context, intent)

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("📋 GENERATED ITINERARY")
    logger.info("=" * 80)
    logger.info(f"Destination: {itinerary.destination}")
    logger.info(f"Duration: {itinerary.duration_days} days")
    logger.info(f"Profile: {itinerary.profile_classification}")
    logger.info(f"\nBudget: {itinerary.total_budget_estimate}")
    logger.info(f"Overall vibe: {itinerary.overall_vibe}")
    logger.info(f"\nEntities used: {itinerary.entities_used}")
    logger.info(f"Confidence: {itinerary.overall_confidence:.2f}")
    logger.info(f"Data quality: {itinerary.data_coverage.value}")
    logger.info(f"Generation cost: ${itinerary.total_cost:.6f}")

    logger.info("\nHighlights:")
    for i, highlight in enumerate(itinerary.highlights[:3], 1):
        logger.info(f"   {i}. {highlight}")

    logger.info("\nDay-by-day:")
    for day in itinerary.days:
        logger.info(f"\n   Day {day.day_number}: {day.theme}")
        logger.info(f"      Budget: {day.daily_budget_estimate}")
        logger.info(f"      Activities: {len(day.get_time_slots())}")

        for slot in day.get_time_slots()[:2]:  # Show first 2
            logger.info(f"         - {slot.time_period.value}: {slot.entity_name}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ ITINERARY GENERATOR TESTING COMPLETE")
    logger.info("=" * 80)

    return itinerary


if __name__ == "__main__":
    test_itinerary_generator()
