#!/usr/bin/env python3
"""
RAG Context Builder - Token-Efficient Context for Itinerary Generation

Converts re-ranked entities into optimized context for LLM generation.
Balances detail vs token cost through tiered prioritization and compression.

Features:
- Tiered entity prioritization (priority/supporting/background)
- Token budget management and compression
- Geographic clustering for day planning
- Data quality context
- Smart token optimization

Author: TravelAI Team
Date: 2025-12-20
"""

import json
import math
from collections import defaultdict
from typing import Dict, List, Any
from statistics import mean

from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    RetrievalCandidate,
    RAGContext
)

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Token budget guidelines
TOKEN_BUDGETS = {
    "small": 2000,    # 1-3 day trips
    "medium": 3000,   # 4-6 day trips
    "large": 4000     # 7+ day trips
}

# Tokens per entity tier
TOKENS_PER_PRIORITY_ENTITY = 200
TOKENS_PER_SUPPORTING_ENTITY = 50
TOKENS_PER_BACKGROUND_ENTITY = 20

# Entity tier sizes
MAX_PRIORITY_ENTITIES = 5
MAX_SUPPORTING_ENTITIES = 5
MAX_BACKGROUND_ENTITIES = 5

# Data quality thresholds
HIGH_QUALITY_MENTIONS = 3
MODERATE_QUALITY_MENTIONS = 2


# =============================================================================
# Helper Functions
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two geographic points in kilometers.

    Uses Haversine formula for great-circle distance.
    """
    R = 6371  # Earth radius in km

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for text.

    Uses simple heuristic: ~1.3 tokens per word.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    if isinstance(text, dict):
        text = json.dumps(text)

    word_count = len(str(text).split())
    return int(word_count * 1.3)


def compress_text(text: str, max_length: int = 100) -> str:
    """
    Compress text to fit within length limit.

    Args:
        text: Text to compress
        max_length: Maximum character length

    Returns:
        Compressed text
    """
    if len(text) <= max_length:
        return text

    # Truncate and add ellipsis
    return text[:max_length - 3] + "..."


def optimize_field_value(value: Any, field_name: str) -> Any:
    """
    Optimize field value for token efficiency.

    Args:
        value: Field value
        field_name: Field name

    Returns:
        Optimized value
    """
    if isinstance(value, str):
        # Remove redundant words
        value = value.replace("highly recommended", "recommended")
        value = value.replace("very good", "good")
        value = value.replace("very popular", "popular")

        # Use abbreviations
        value = value.replace(" per night", "/night")
        value = value.replace(" per day", "/day")
        value = value.replace(" per person", "/person")

    return value


# =============================================================================
# ContextBuilder Class
# =============================================================================

class ContextBuilder:
    """
    Build token-efficient context for LLM itinerary generation.

    Converts re-ranked entities into optimized RAGContext with tiered
    prioritization and token budget management.

    Features:
    - Tiered entity prioritization
    - Token budget tracking
    - Geographic clustering
    - Data quality context
    - Smart compression

    Example:
        >>> builder = ContextBuilder()
        >>> context = builder.build_rag_context(
        ...     candidates=reranked_entities,
        ...     user_intent=intent,
        ...     token_budget=3000
        ... )
        >>> context.estimated_tokens
        2847
    """

    def __init__(self):
        """Initialize context builder."""
        logger.info("ContextBuilder initialized")

    def build_rag_context(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent,
        token_budget: int = 3000
    ) -> RAGContext:
        """
        Build optimized RAG context from re-ranked candidates.

        Main context building pipeline:
        1. Prioritize entities (priority/supporting/background)
        2. Extract detailed context for each tier
        3. Create profile description
        4. Create constraint summary
        5. Add geographic clusters
        6. Add data quality context
        7. Optimize token usage
        8. Compress if needed

        Args:
            candidates: Re-ranked retrieval candidates
            user_intent: User intent
            token_budget: Maximum tokens allowed

        Returns:
            Optimized RAGContext
        """
        logger.info("=" * 80)
        logger.info("🔨 BUILDING RAG CONTEXT")
        logger.info("=" * 80)
        logger.info(f"Input candidates: {len(candidates)}")
        logger.info(f"Token budget: {token_budget}")

        # Step 1: Prioritize entities
        priority_entities = candidates[:MAX_PRIORITY_ENTITIES]
        supporting_entities = candidates[MAX_PRIORITY_ENTITIES:MAX_PRIORITY_ENTITIES + MAX_SUPPORTING_ENTITIES]
        background_entities = candidates[MAX_PRIORITY_ENTITIES + MAX_SUPPORTING_ENTITIES:MAX_PRIORITY_ENTITIES + MAX_SUPPORTING_ENTITIES + MAX_BACKGROUND_ENTITIES]

        logger.info("\n📊 Entity Prioritization:")
        logger.info(f"   Priority entities: {len(priority_entities)} (full context)")
        logger.info(f"   Supporting entities: {len(supporting_entities)} (summary)")
        logger.info(f"   Background entities: {len(background_entities)} (minimal)")

        # Step 2: Extract context for each tier
        priority_context = self._extract_priority_context(priority_entities)
        supporting_context = self._extract_supporting_context(supporting_entities)
        background_context = self._extract_background_context(background_entities)

        # Step 3: Create profile description
        profile_desc = self.create_profile_description(user_intent)

        # Step 4: Create constraint summary
        constraints = self.create_constraint_summary(user_intent)

        # Step 5: Create geographic clusters
        geographic_clusters = self.create_geographic_clusters(candidates)

        # Step 6: Add data quality context
        data_quality_note = self.add_data_quality_context(candidates)

        # Step 7: Create user intent summary
        intent_summary = self._create_intent_summary(user_intent)

        # Step 8: Build RAGContext
        context = RAGContext(
            user_intent_summary=intent_summary,
            profile_description=profile_desc,
            priority_entities=priority_context,
            supporting_entities=supporting_context,
            background_entities=background_context,
            hard_constraints=constraints["hard_constraints"],
            soft_preferences=constraints["soft_preferences"],
            total_entities=len(candidates),
            coverage_areas=list(geographic_clusters.keys()),
            data_quality_note=data_quality_note
        )

        # Step 9: Estimate tokens
        initial_tokens = context.estimate_tokens()
        logger.info("\n💰 Token Usage:")
        logger.info(f"   Initial estimate: {initial_tokens} tokens")

        # Step 10: Compress if needed
        if initial_tokens > token_budget:
            logger.info(f"   ⚠️  Over budget by {initial_tokens - token_budget} tokens")
            logger.info("   Compressing context...")
            context = self.compress_context(context, token_budget)
            final_tokens = context.estimate_tokens()
            logger.info(f"   After compression: {final_tokens} tokens")
        else:
            logger.info(f"   ✅ Within budget ({token_budget - initial_tokens} tokens remaining)")

        logger.info("\n" + "=" * 80)
        logger.info("✅ CONTEXT BUILDING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Final token count: {context.estimated_tokens}")
        logger.info(f"Compression level: {context.compression_level}")
        logger.info(f"Coverage areas: {len(context.coverage_areas)}")

        return context

    def _extract_priority_context(
        self,
        candidates: List[RetrievalCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Extract full context for priority entities.

        Priority entities get the most detail (~200 tokens each):
        - Complete entity info
        - Traveler quotes
        - Tips and warnings
        - Nearby entities

        Args:
            candidates: Priority candidates

        Returns:
            List of detailed entity contexts
        """
        contexts = []

        for candidate in candidates:
            entity_data = candidate.entity_data

            # Extract coordinates
            coords = candidate.coordinates or {}
            lat = coords.get('lat', 0.0)
            lon = coords.get('lon', 0.0)

            # Build context
            context = {
                "entity_id": candidate.entity_id,
                "name": candidate.canonical_name,
                "type": candidate.entity_type,
                "location": {
                    "city": candidate.city,
                    "area": entity_data.get("area", ""),
                    "coordinates": {"lat": lat, "lon": lon} if lat and lon else None
                },

                # Core info
                "rating": round(candidate.profile_rating, 1),
                "mention_count": candidate.mention_count,
                "similarity_score": round(candidate.similarity_score, 2),
                "relevance_score": round(candidate.relevance_score or 0, 2),
                "why_recommended": candidate.ranking_reason or f"Rated {candidate.profile_rating:.1f}/5 by similar travelers",

                # Practical details
                "cost_estimate": entity_data.get("typical_cost", "Varies"),
                "best_time": entity_data.get("best_time_to_visit", "Anytime"),
                "typical_duration": entity_data.get("typical_visit_duration", "Varies"),

                # Traveler voices (limit to 2-3 best quotes)
                "quotes": self._extract_best_quotes(entity_data, max_quotes=3),

                # Tips & warnings
                "tips": entity_data.get("tips", [])[:3],  # Max 3 tips
                "warnings": entity_data.get("warnings", [])[:2],  # Max 2 warnings

                # Attributes
                "attributes": candidate.attributes[:5] if candidate.attributes else [],
                "best_for": candidate.best_for[:3] if candidate.best_for else [],

                # Confidence
                "confidence": round(candidate.relevance_score or 0.8, 2),
                "data_quality": "high" if candidate.mention_count >= HIGH_QUALITY_MENTIONS else "moderate"
            }

            # Optimize values
            context = {k: optimize_field_value(v, k) for k, v in context.items()}

            contexts.append(context)

        return contexts

    def _extract_supporting_context(
        self,
        candidates: List[RetrievalCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Extract summary context for supporting entities.

        Supporting entities get moderate detail (~50 tokens each):
        - Basic info
        - One-line summary
        - Cost and tip

        Args:
            candidates: Supporting candidates

        Returns:
            List of summary entity contexts
        """
        contexts = []

        for candidate in candidates:
            entity_data = candidate.entity_data

            # Create one-line summary
            one_line = f"{candidate.entity_type.title()}, {candidate.profile_rating:.1f}/5 rating"
            if candidate.mention_count > 1:
                one_line += f", {candidate.mention_count} mentions"

            context = {
                "entity_id": candidate.entity_id,
                "name": candidate.canonical_name,
                "type": candidate.entity_type,
                "one_line": one_line,
                "cost": entity_data.get("typical_cost", "Varies"),
                "tip": entity_data.get("tips", [""])[0] if entity_data.get("tips") else ""
            }

            contexts.append(context)

        return contexts

    def _extract_background_context(
        self,
        candidates: List[RetrievalCandidate]
    ) -> List[Dict[str, Any]]:
        """
        Extract minimal context for background entities.

        Background entities get minimal detail (~20 tokens each):
        - Name, type, rating

        Args:
            candidates: Background candidates

        Returns:
            List of minimal entity contexts
        """
        contexts = []

        for candidate in candidates:
            context = {
                "name": candidate.canonical_name,
                "type": candidate.entity_type,
                "note": f"{candidate.profile_rating:.1f}/5"
            }

            contexts.append(context)

        return contexts

    def _extract_best_quotes(
        self,
        entity_data: Dict[str, Any],
        max_quotes: int = 3
    ) -> List[str]:
        """
        Extract best traveler quotes from entity data.

        Args:
            entity_data: Entity data
            max_quotes: Maximum quotes to include

        Returns:
            List of best quotes
        """
        quotes = []

        # Get experiences from entity data
        experiences = entity_data.get("experiences", [])

        for exp in experiences[:max_quotes]:
            # Extract quote from experience
            quote_text = exp.get("what_they_said", "")
            traveler_info = exp.get("traveler_profile", "traveler")

            if quote_text:
                # Compress quote if too long
                quote_text = compress_text(quote_text, max_length=150)
                quotes.append(f'"{quote_text}" - {traveler_info}')

        return quotes

    def create_profile_description(self, intent: UserIntent) -> str:
        """
        Create human-readable traveler profile description.

        Args:
            intent: User intent

        Returns:
            Profile description string
        """
        profile = intent.traveler_profile

        # Build profile description
        parts = []

        # Age and type
        age = profile.age_range or "any age"
        parts.append(f"a {age} {profile.traveler_type} traveler")

        # Budget
        parts.append(f"on a {profile.budget_tier} budget")

        # Travel style
        if profile.travel_style:
            styles = ", ".join(profile.travel_style[:3])
            parts.append(f"who loves {styles}")

        # Interests
        if intent.interests:
            interests = ", ".join(intent.interests[:3])
            parts.append(f"You're interested in {interests}")

        description = "You're " + " ".join(parts) + "."

        return description

    def create_constraint_summary(self, intent: UserIntent) -> Dict[str, Any]:
        """
        Extract actionable constraints from user intent.

        Args:
            intent: User intent

        Returns:
            Dictionary with hard_constraints and soft_preferences
        """
        hard_constraints = {}
        soft_preferences = {}

        # Hard constraints (must follow)
        if intent.budget_per_day:
            min_budget = intent.budget_per_day.get("min", 0)
            max_budget = intent.budget_per_day.get("max", 0)
            hard_constraints["budget_per_day"] = f"${min_budget:.0f}-${max_budget:.0f}"

        if intent.must_include:
            hard_constraints["must_include"] = intent.must_include

        if intent.must_avoid:
            hard_constraints["must_avoid"] = intent.must_avoid

        hard_constraints["duration"] = f"{intent.duration_days} days"

        if intent.dates:
            hard_constraints["dates"] = intent.dates

        # Soft preferences (should try to follow)
        soft_preferences["pace"] = intent.pace.value

        if intent.accommodation_preference:
            soft_preferences["accommodation"] = intent.accommodation_preference

        if intent.interests:
            soft_preferences["interests"] = intent.interests

        soft_preferences["flexibility"] = intent.flexibility.value

        return {
            "hard_constraints": hard_constraints,
            "soft_preferences": soft_preferences
        }

    def add_data_quality_context(
        self,
        candidates: List[RetrievalCandidate]
    ) -> str:
        """
        Provide LLM with data coverage information.

        Helps LLM calibrate confidence based on data quality.

        Args:
            candidates: Retrieval candidates

        Returns:
            Data quality context string
        """
        if not candidates:
            return "Limited data available."

        # Calculate stats
        total_sources = len(set([
            vid
            for c in candidates
            for vid in c.source_video_ids
        ]))

        avg_mentions = mean([c.mention_count for c in candidates])

        # Determine quality
        if avg_mentions >= HIGH_QUALITY_MENTIONS:
            quality = "high"
        elif avg_mentions >= MODERATE_QUALITY_MENTIONS:
            quality = "moderate"
        else:
            quality = "limited"

        # Build context
        context = (
            f"This itinerary is based on {total_sources} traveler experiences. "
            f"Places have been visited by {avg_mentions:.0f} travelers on average. "
            f"Data quality: {quality}."
        )

        return context

    def create_geographic_clusters(
        self,
        candidates: List[RetrievalCandidate]
    ) -> Dict[str, List[str]]:
        """
        Group entities by geographic area for day planning.

        Helps LLM plan logical day-by-day routes.

        Args:
            candidates: Retrieval candidates

        Returns:
            Dictionary mapping area names to entity names
        """
        clusters = defaultdict(list)

        for candidate in candidates:
            # Try to get area from entity data
            area = candidate.entity_data.get("area", "unknown")

            # If no area, try to infer from name or type
            if area == "unknown" or not area:
                # Use entity type as fallback
                area = f"{candidate.entity_type}s"

            clusters[area].append(candidate.canonical_name)

        return dict(clusters)

    def compress_context(
        self,
        context: RAGContext,
        target_tokens: int
    ) -> RAGContext:
        """
        Compress context to fit token budget.

        Progressively reduces context detail until target is met.

        Compression strategy:
        1. Light: Move supporting → background
        2. Medium: Reduce all tier sizes
        3. Heavy: Keep only priority entities

        Args:
            context: RAGContext to compress
            target_tokens: Target token count

        Returns:
            Compressed RAGContext (modified in place)
        """
        logger.info(f"\n🗜️  Compressing context to {target_tokens} tokens")

        current_tokens = context.estimate_tokens()

        if current_tokens <= target_tokens:
            context.compression_level = "none"
            return context

        # Light compression: move supporting → background
        if len(context.supporting_entities) > 5:
            logger.info("   Light compression: reducing supporting entities")
            # Convert excess supporting to background format
            excess = context.supporting_entities[5:]
            background_additions = [
                {
                    "name": e["name"],
                    "type": e["type"],
                    "note": e.get("one_line", "")
                }
                for e in excess
            ]
            context.supporting_entities = context.supporting_entities[:5]
            context.background_entities.extend(background_additions)
            context.compression_level = "light"

        # Medium compression: reduce all tiers
        if context.estimate_tokens() > target_tokens:
            logger.info("   Medium compression: reducing all tiers")
            context.priority_entities = context.priority_entities[:5]
            context.supporting_entities = context.supporting_entities[:3]
            context.background_entities = context.background_entities[:2]
            context.compression_level = "medium"

        # Heavy compression: keep only priority, compress quotes
        if context.estimate_tokens() > target_tokens:
            logger.info("   Heavy compression: minimal context only")
            # Compress priority entities
            for entity in context.priority_entities:
                # Reduce quotes
                if "quotes" in entity and len(entity["quotes"]) > 1:
                    entity["quotes"] = entity["quotes"][:1]
                # Reduce tips
                if "tips" in entity and len(entity["tips"]) > 2:
                    entity["tips"] = entity["tips"][:2]
                # Remove warnings
                entity.pop("warnings", None)

            # Remove supporting and background
            context.supporting_entities = []
            context.background_entities = []
            context.compression_level = "heavy"

        final_tokens = context.estimate_tokens()
        logger.info(f"   Final: {final_tokens} tokens ({context.compression_level} compression)")

        return context

    def _create_intent_summary(self, intent: UserIntent) -> str:
        """
        Create concise intent summary.

        Args:
            intent: User intent

        Returns:
            Summary string
        """
        parts = [
            f"{intent.duration_days}-day",
            intent.traveler_profile.budget_tier,
            intent.traveler_profile.traveler_type,
            "trip to",
            intent.destination
        ]

        return " ".join(parts)

    def optimize_token_usage(self, context: RAGContext) -> RAGContext:
        """
        Apply smart token optimizations to context.

        Args:
            context: RAGContext to optimize

        Returns:
            Optimized RAGContext (modified in place)
        """
        # Optimize all entity contexts
        for entity_list in [context.priority_entities, context.supporting_entities]:
            for entity in entity_list:
                for key, value in entity.items():
                    entity[key] = optimize_field_value(value, key)

        return context


# =============================================================================
# Testing Function
# =============================================================================

def test_context_builder():
    """Test ContextBuilder with sample data."""
    from src.rag.retriever import RAGRetriever
    from src.rag.reranker import LLMReranker
    from src.rag.intent_parser import IntentParser
    from src.vectordb import ChromaDBClient
    from src.utils.embedding_client import EmbeddingClient

    logger.info("=" * 80)
    logger.info("🧪 TESTING CONTEXT BUILDER")
    logger.info("=" * 80)

    # Initialize clients
    chromadb = ChromaDBClient.initialize_from_env()
    embedding_client = EmbeddingClient()

    # Step 1: Parse intent
    parser = IntentParser()
    query = "Plan 5 days in Bangkok for solo budget traveler who loves parties"

    logger.info(f"\nParsing query: {query}")
    intent = parser.parse_query(query)

    logger.info(f"✅ Intent parsed: {intent.destination}, {intent.duration_days} days")

    # Step 2: Retrieve candidates
    retriever = RAGRetriever(chromadb, embedding_client)
    candidates = retriever.retrieve_for_itinerary(intent, top_k=20)

    logger.info(f"✅ Retrieved {len(candidates)} candidates")

    # Step 3: Re-rank
    reranker = LLMReranker(provider="deepseek")
    reranked = reranker.rerank_candidates(candidates, intent, top_k=12)

    logger.info(f"✅ Re-ranked to {len(reranked)} candidates")

    # Step 4: Build context
    builder = ContextBuilder()
    context = builder.build_rag_context(
        candidates=reranked,
        user_intent=intent,
        token_budget=3000
    )

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("📋 CONTEXT SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Intent: {context.user_intent_summary}")
    logger.info(f"Profile: {context.profile_description}")
    logger.info("\nEntities:")
    logger.info(f"   Priority: {len(context.priority_entities)}")
    logger.info(f"   Supporting: {len(context.supporting_entities)}")
    logger.info(f"   Background: {len(context.background_entities)}")
    logger.info(f"   Total: {context.total_entities}")
    logger.info("\nConstraints:")
    logger.info(f"   Hard: {context.hard_constraints}")
    logger.info(f"   Soft: {context.soft_preferences}")
    logger.info("\nCoverage:")
    logger.info(f"   Areas: {context.coverage_areas}")
    logger.info(f"   Quality: {context.data_quality_note}")
    logger.info("\nToken Usage:")
    logger.info(f"   Estimated: {context.estimated_tokens} tokens")
    logger.info(f"   Compression: {context.compression_level}")

    # Show sample priority entity
    if context.priority_entities:
        logger.info("\nSample Priority Entity:")
        sample = context.priority_entities[0]
        logger.info(f"   Name: {sample['name']}")
        logger.info(f"   Type: {sample['type']}")
        logger.info(f"   Rating: {sample['rating']}/5")
        logger.info(f"   Why: {sample['why_recommended']}")
        if sample.get('quotes'):
            logger.info(f"   Quote: {sample['quotes'][0]}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ CONTEXT BUILDER TESTING COMPLETE")
    logger.info("=" * 80)
    logger.info("Ready for itinerary generation!")

    return context


if __name__ == "__main__":
    test_context_builder()
