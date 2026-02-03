#!/usr/bin/env python3
"""
Intent Parser for RAG Pipeline

Converts natural language travel queries into structured UserIntent objects.
This is the ENTRY POINT of the RAG pipeline - everything flows from here.

Handles diverse query styles:
- "Plan 5 days in Bangkok"
- "Romantic beachside dining in Phuket for couple, $100/day"
- "Best nightlife for solo budget travelers"

Features:
- DeepSeek LLM for cost-efficient parsing ($0.0001 per query)
- Intelligent default inference
- Ambiguity resolution
- Profile classification matching Stage 3 data
- Comprehensive validation and enrichment

Author: TravelAI Team
Date: 2025-12-20
"""

import json
import re
from typing import Dict, List, Tuple, Any

from src.utils.llm_client import extract_with_llm
from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    TravelerProfileInput,
    Pace,
    Flexibility
)

logger = get_logger(__name__)


# Profile classification buckets from Stage 3
PROFILE_BUCKETS = {
    # Solo travelers
    "solo_budget_party": ["solo", "budget", "party", "nightlife", "social"],
    "solo_budget_culture": ["solo", "budget", "cultural", "museum", "temple"],
    "solo_mid_adventure": ["solo", "mid-range", "adventure", "hiking", "nature"],

    # Couples
    "couple_budget_backpack": ["couple", "budget", "backpack", "hostel", "adventure"],
    "couple_mid_romantic": ["couple", "mid-range", "romantic", "beach", "resort"],
    "couple_luxury_honeymoon": ["couple", "luxury", "honeymoon", "resort", "spa"],

    # Families
    "family_budget_cultural": ["family", "budget", "cultural", "kid-friendly", "educational"],
    "family_mid_beach": ["family", "mid-range", "beach", "resort", "pool"],

    # Groups
    "group_budget_party": ["group", "budget", "party", "nightlife", "social"],
    "group_mid_adventure": ["group", "mid-range", "adventure", "activities", "tours"],
}

# Budget tier defaults (USD per day)
BUDGET_DEFAULTS = {
    "budget": {"min": 30, "max": 50},
    "mid-range": {"min": 50, "max": 150},
    "luxury": {"min": 150, "max": 500}
}


class IntentParser:
    """
    Parse natural language travel queries into structured UserIntent.

    This is the entry point of the RAG pipeline. All downstream processes
    depend on accurate intent parsing.

    Example:
        >>> parser = IntentParser()
        >>> intent = parser.parse_query(
        ...     "Plan 5 days in Bangkok for solo budget traveler who loves parties"
        ... )
        >>> intent.destination
        'Bangkok'
        >>> intent.duration_days
        5
    """

    def __init__(self):
        """
        Initialize intent parser.

        Uses DeepSeek LLM for cost-efficient parsing (~$0.0001 per query).
        """
        self.total_cost = 0.0

        logger.info("IntentParser initialized")

    def parse_query(self, query: str) -> UserIntent:
        """
        Parse natural language query into structured UserIntent.

        Main entry point for intent parsing. Handles:
        - Information extraction via LLM
        - Default inference
        - Validation
        - Enrichment

        Args:
            query: Natural language travel query

        Returns:
            Structured UserIntent object

        Example:
            >>> intent = parser.parse_query("Weekend trip to Phuket")
            >>> intent.duration_days
            2  # Inferred from "weekend"
        """
        logger.info("=" * 80)
        logger.info("PARSING USER QUERY")
        logger.info("=" * 80)
        logger.info(f"Query: {query}")

        # Detect query type
        query_type = self._detect_query_type(query)
        logger.info(f"Query type: {query_type}")

        # Extract intent using LLM
        raw_intent = self._extract_intent_with_llm(query)

        # Build UserIntent object
        intent = self._build_user_intent(query, raw_intent)

        # Enrich with defaults
        intent = self.enrich_intent_with_defaults(intent)

        # Handle ambiguity
        intent = self.handle_ambiguity(query, intent)

        # Validate
        is_valid, issues = self.validate_intent(intent)

        if not is_valid:
            logger.warning(f"Intent validation issues: {issues}")
            # Try to fix issues
            intent = self._fix_validation_issues(intent, issues)

        logger.info("\n✅ Parsed intent:")
        logger.info(f"   Destination: {intent.destination}")
        logger.info(f"   Duration: {intent.duration_days} days")
        logger.info(f"   Profile: {intent.traveler_profile.traveler_type} ({intent.traveler_profile.budget_tier})")
        logger.info(f"   Confidence: {intent.confidence:.2f}")
        logger.info("=" * 80)

        return intent

    def _detect_query_type(self, query: str) -> str:
        """
        Detect type of travel query.

        Args:
            query: User query

        Returns:
            Query type: "itinerary" | "recommendation" | "question"
        """
        query_lower = query.lower()

        # Itinerary indicators
        itinerary_keywords = [
            "plan", "itinerary", "schedule", "trip", "visit",
            "days", "week", "weekend", "travel to"
        ]

        # Recommendation indicators
        recommendation_keywords = [
            "best", "top", "recommend", "suggest", "where to",
            "what to do", "places for", "good for"
        ]

        # Question indicators
        question_keywords = ["is", "are", "does", "can", "should", "how"]

        # Check for matches
        if any(kw in query_lower for kw in itinerary_keywords):
            return "itinerary"
        elif any(kw in query_lower for kw in recommendation_keywords):
            return "recommendation"
        elif any(query_lower.startswith(kw) for kw in question_keywords):
            return "question"
        else:
            # Default to itinerary
            return "itinerary"

    def _extract_intent_with_llm(self, query: str) -> Dict[str, Any]:
        """
        Extract travel intent using LLM.

        Uses DeepSeek for cost-efficient parsing.

        Args:
            query: User query

        Returns:
            Parsed intent dictionary
        """
        # Build extraction prompt
        prompt = f"""Extract travel intent from this query:
"{query}"

Return ONLY valid JSON (no markdown, no code blocks) with this exact structure:
{{
  "destination": "city or country name",
  "duration_days": integer or null,
  "traveler_profile": {{
    "traveler_type": "solo|couple|family|group",
    "budget_tier": "budget|mid-range|luxury",
    "travel_style": ["party", "cultural", "foodie", "adventure", "relaxation", etc.]
  }},
  "interests": ["food", "nightlife", "culture", "nature", "shopping", etc.],
  "budget_per_day": {{"min": X, "max": Y}} or null,
  "must_include": ["entity1", "entity2", ...] or [],
  "must_avoid": ["entity1", "entity2", ...] or [],
  "pace": "relaxed|balanced|packed",
  "flexibility": "low|medium|high",
  "confidence": 0.0-1.0
}}

Guidelines:
- If info is missing, use null or reasonable defaults
- Infer traveler_type from context (default: "solo")
- Budget tier: <$50/day=budget, $50-150=mid-range, >$150=luxury
- Duration: "weekend"=2, "week"=7, "few days"=3
- confidence: how certain you are (0.5-1.0)
- Return ONLY the JSON object, nothing else

JSON:"""

        try:
            # Call LLM (DeepSeek for cost efficiency)
            result = extract_with_llm(
                prompt=prompt,
                provider="deepseek",
                temperature=0.3,  # Low temp for consistent parsing
                max_tokens=500
            )

            # Track cost
            self.total_cost += result['cost_usd']
            tokens_used = result['tokens_used']['total']

            logger.info(f"LLM extraction: {tokens_used} tokens, ${result['cost_usd']:.6f}")

            # Check if extraction succeeded
            if not result['success']:
                logger.error(f"LLM extraction failed: {result['error']}")
                raise ValueError(f"LLM extraction failed: {result['error']}")

            # Get parsed JSON data (already parsed by extract_with_llm)
            intent_dict = result['data']

            return intent_dict

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to extract intent with LLM: {e}")

            # Retry with clarification
            logger.info("Retrying with simpler prompt...")
            return self._extract_with_fallback(query)

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_with_fallback(query)

    def _clean_json_response(self, response: str) -> str:
        """
        Clean LLM response to extract pure JSON.

        Handles cases where LLM wraps JSON in markdown or adds commentary.

        Args:
            response: Raw LLM response

        Returns:
            Clean JSON string
        """
        # Remove markdown code blocks
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()

        # Remove any text before first {
        if "{" in response:
            response = response[response.find("{"):]

        # Remove any text after last }
        if "}" in response:
            response = response[:response.rfind("}") + 1]

        return response.strip()

    def _extract_with_fallback(self, query: str) -> Dict[str, Any]:
        """
        Fallback extraction using simple pattern matching.

        Used when LLM fails or returns invalid JSON.

        Args:
            query: User query

        Returns:
            Basic intent dictionary
        """
        logger.warning("Using fallback extraction (pattern matching)")

        query_lower = query.lower()

        # Extract destination (first proper noun or known city)
        destination = self._extract_destination(query)

        # Extract duration
        duration = self._extract_duration(query_lower)

        # Infer traveler type
        if any(word in query_lower for word in ["couple", "romantic", "honeymoon"]):
            traveler_type = "couple"
        elif any(word in query_lower for word in ["family", "kids", "children"]):
            traveler_type = "family"
        elif any(word in query_lower for word in ["group", "friends"]):
            traveler_type = "group"
        else:
            traveler_type = "solo"

        # Infer budget tier
        if any(word in query_lower for word in ["budget", "cheap", "backpack", "hostel"]):
            budget_tier = "budget"
        elif any(word in query_lower for word in ["luxury", "resort", "spa", "5-star"]):
            budget_tier = "luxury"
        else:
            budget_tier = "mid-range"

        # Infer travel style
        travel_style = []
        if any(word in query_lower for word in ["party", "nightlife", "club"]):
            travel_style.append("party")
        if any(word in query_lower for word in ["culture", "temple", "museum"]):
            travel_style.append("cultural")
        if any(word in query_lower for word in ["food", "restaurant", "eat"]):
            travel_style.append("foodie")
        if any(word in query_lower for word in ["adventure", "hike", "trek"]):
            travel_style.append("adventure")
        if any(word in query_lower for word in ["beach", "relax", "spa"]):
            travel_style.append("relaxation")

        if not travel_style:
            travel_style = ["balanced"]

        return {
            "destination": destination,
            "duration_days": duration,
            "traveler_profile": {
                "traveler_type": traveler_type,
                "budget_tier": budget_tier,
                "travel_style": travel_style
            },
            "interests": travel_style,
            "budget_per_day": None,
            "must_include": [],
            "must_avoid": [],
            "pace": "balanced",
            "flexibility": "medium",
            "confidence": 0.6  # Lower confidence for fallback
        }

    def _extract_destination(self, query: str) -> str:
        """Extract destination from query using pattern matching"""
        # Known destinations
        known_cities = [
            "Bangkok", "Phuket", "Chiang Mai", "Krabi", "Pattaya",
            "Koh Samui", "Hua Hin", "Ayutthaya", "Chiang Rai"
        ]

        for city in known_cities:
            if city.lower() in query.lower():
                return city

        # Look for "to/in X" pattern
        patterns = [
            r"to ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"in ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"visit ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)

        # Default
        return "Thailand"

    def _extract_duration(self, query_lower: str) -> int:
        """Extract trip duration from query"""
        # Look for explicit numbers
        duration_patterns = [
            (r"(\d+)\s*days?", lambda m: int(m.group(1))),
            (r"(\d+)\s*weeks?", lambda m: int(m.group(1)) * 7),
            (r"(\d+)-day", lambda m: int(m.group(1))),
        ]

        for pattern, extractor in duration_patterns:
            match = re.search(pattern, query_lower)
            if match:
                return extractor(match)

        # Keyword-based
        if "weekend" in query_lower:
            return 2
        elif "week" in query_lower:
            return 7
        elif "few days" in query_lower:
            return 3

        # Default
        return 3

    def _build_user_intent(self, query: str, raw_intent: Dict[str, Any]) -> UserIntent:
        """
        Build UserIntent object from raw parsed data.

        Args:
            query: Original query
            raw_intent: Parsed intent dictionary

        Returns:
            UserIntent object
        """
        # Build traveler profile
        profile_data = raw_intent.get('traveler_profile', {})

        profile = TravelerProfileInput(
            traveler_type=profile_data.get('traveler_type', 'solo'),
            group_size=self._infer_group_size(profile_data.get('traveler_type', 'solo')),
            age_range=None,  # Not inferred from query
            budget_tier=profile_data.get('budget_tier', 'mid-range'),
            travel_style=profile_data.get('travel_style', [])
        )

        # Handle pace (with None safety)
        pace_str = raw_intent.get('pace') or 'balanced'
        pace = Pace(pace_str) if pace_str else Pace.BALANCED

        # Handle flexibility (with None safety)
        flex_str = raw_intent.get('flexibility') or 'medium'
        flexibility = Flexibility(flex_str) if flex_str else Flexibility.MEDIUM

        # Build UserIntent
        intent = UserIntent(
            destination=raw_intent.get('destination', 'Unknown'),
            duration_days=raw_intent.get('duration_days') or 3,
            traveler_profile=profile,
            budget_per_day=raw_intent.get('budget_per_day'),
            interests=raw_intent.get('interests', []),
            must_include=raw_intent.get('must_include', []),
            must_avoid=raw_intent.get('must_avoid', []),
            pace=pace,
            flexibility=flexibility,
            query_text=query,
            confidence=raw_intent.get('confidence', 0.8)
        )

        return intent

    def _infer_group_size(self, traveler_type: str) -> int:
        """Infer group size from traveler type"""
        if traveler_type == "solo":
            return 1
        elif traveler_type == "couple":
            return 2
        elif traveler_type == "family":
            return 4  # Typical family
        elif traveler_type == "group":
            return 6  # Typical group
        else:
            return 1

    def classify_traveler_profile(self, profile: TravelerProfileInput) -> str:
        """
        Classify traveler profile to match Stage 3 data buckets.

        Maps parsed profile to predefined buckets used in Stage 3 consensus.
        Enables personalized retrieval from vector DB.

        Args:
            profile: Parsed traveler profile

        Returns:
            Profile key (e.g., "solo_budget_party")

        Example:
            >>> profile = TravelerProfileInput(
            ...     traveler_type="solo",
            ...     budget_tier="budget",
            ...     travel_style=["party", "nightlife"]
            ... )
            >>> parser.classify_traveler_profile(profile)
            'solo_budget_party'
        """
        # Build search terms from profile
        search_terms = [
            profile.traveler_type,
            profile.budget_tier,
            *profile.travel_style
        ]

        # Find best matching bucket
        best_match = None
        best_score = 0

        for bucket_key, bucket_keywords in PROFILE_BUCKETS.items():
            # Calculate match score
            score = sum(1 for term in search_terms if any(kw in term for kw in bucket_keywords))

            if score > best_score:
                best_score = score
                best_match = bucket_key

        if best_match:
            logger.info(f"Classified profile as: {best_match} (score: {best_score})")
            return best_match

        # Fallback to generic bucket
        fallback = f"{profile.traveler_type}_{profile.budget_tier}_general"
        logger.warning(f"No exact match, using fallback: {fallback}")
        return fallback

    def extract_constraints(self, query: str, intent: UserIntent) -> Dict[str, Any]:
        """
        Extract hard vs soft constraints from intent.

        Hard constraints MUST be followed (budget limits, must-include, dates).
        Soft preferences are nice to have (pace, interests).

        Args:
            query: Original query
            intent: Parsed intent

        Returns:
            Dict with "hard" and "soft" constraint lists
        """
        hard_constraints = {}
        soft_preferences = {}

        # Hard constraints
        if intent.budget_per_day:
            hard_constraints['budget_per_day'] = intent.budget_per_day

        if intent.must_include:
            hard_constraints['must_include'] = intent.must_include

        if intent.must_avoid:
            hard_constraints['must_avoid'] = intent.must_avoid

        if intent.dates:
            hard_constraints['dates'] = intent.dates

        hard_constraints['duration'] = intent.duration_days
        hard_constraints['destination'] = intent.destination

        # Soft preferences
        soft_preferences['pace'] = intent.pace
        soft_preferences['interests'] = intent.interests
        soft_preferences['flexibility'] = intent.flexibility

        if intent.accommodation_preference:
            soft_preferences['accommodation'] = intent.accommodation_preference

        return {
            "hard": hard_constraints,
            "soft": soft_preferences
        }

    def validate_intent(self, intent: UserIntent) -> Tuple[bool, List[str]]:
        """
        Validate that intent is actionable.

        Checks minimum requirements for itinerary generation.

        Args:
            intent: Parsed intent

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Must have destination
        if not intent.destination or intent.destination == "Unknown":
            issues.append("Missing destination")

        # Must have duration
        if not intent.duration_days or intent.duration_days < 1:
            issues.append("Invalid duration")

        # Must have valid profile
        if not intent.traveler_profile:
            issues.append("Missing traveler profile")

        # Duration should be reasonable
        if intent.duration_days > 30:
            issues.append(f"Duration too long ({intent.duration_days} days)")

        # Confidence should be reasonable
        if intent.confidence < 0.5:
            issues.append(f"Low parsing confidence ({intent.confidence:.2f})")

        is_valid = len(issues) == 0

        return is_valid, issues

    def enrich_intent_with_defaults(self, intent: UserIntent) -> UserIntent:
        """
        Fill gaps in intent with intelligent defaults.

        Args:
            intent: Parsed intent

        Returns:
            Enriched intent
        """
        logger.info("Enriching intent with defaults...")

        # Add budget defaults if missing
        if not intent.budget_per_day:
            budget_tier = intent.traveler_profile.budget_tier
            if budget_tier in BUDGET_DEFAULTS:
                intent.budget_per_day = BUDGET_DEFAULTS[budget_tier]
                logger.info(f"   Added budget: ${intent.budget_per_day['min']}-${intent.budget_per_day['max']}/day")

        # Add travel style defaults
        if not intent.traveler_profile.travel_style:
            # Infer from traveler type
            if intent.traveler_profile.traveler_type == "couple":
                intent.traveler_profile.travel_style = ["romantic", "relaxation"]
            elif intent.traveler_profile.traveler_type == "family":
                intent.traveler_profile.travel_style = ["cultural", "kid-friendly"]
            else:
                intent.traveler_profile.travel_style = ["balanced"]

            logger.info(f"   Added travel style: {intent.traveler_profile.travel_style}")

        # Sync interests with travel style if empty
        if not intent.interests:
            intent.interests = intent.traveler_profile.travel_style.copy()
            logger.info("   Synced interests from travel style")

        return intent

    def handle_ambiguity(self, query: str, intent: UserIntent) -> UserIntent:
        """
        Resolve ambiguous queries with reasonable assumptions.

        Args:
            query: Original query
            intent: Parsed intent

        Returns:
            Clarified intent
        """
        query_lower = query.lower()

        # "Beach trip" → infer coastal preference
        if "beach" in query_lower and "beach" not in intent.interests:
            intent.interests.append("beach")
            logger.info("   Ambiguity: 'beach' → added to interests")

        # "Backpacking" → budget + hostel
        if "backpack" in query_lower:
            if "hostel" not in (intent.accommodation_preference or ""):
                intent.accommodation_preference = "hostel"
            intent.traveler_profile.budget_tier = "budget"
            logger.info("   Ambiguity: 'backpacking' → budget tier + hostel")

        # "Honeymoon" → couple + romantic + mid-range
        if "honeymoon" in query_lower:
            intent.traveler_profile.traveler_type = "couple"
            if "romantic" not in intent.traveler_profile.travel_style:
                intent.traveler_profile.travel_style.append("romantic")
            if intent.traveler_profile.budget_tier == "budget":
                intent.traveler_profile.budget_tier = "mid-range"
            logger.info("   Ambiguity: 'honeymoon' → couple + romantic + mid-range")

        # "Foodie" → add food interest
        if any(word in query_lower for word in ["foodie", "culinary", "eat", "restaurant"]):
            if "food" not in intent.interests:
                intent.interests.append("food")
                logger.info("   Ambiguity: food-related → added 'food' interest")

        return intent

    def _fix_validation_issues(self, intent: UserIntent, issues: List[str]) -> UserIntent:
        """
        Attempt to fix validation issues.

        Args:
            intent: Intent with validation issues
            issues: List of issue descriptions

        Returns:
            Fixed intent
        """
        for issue in issues:
            if "Missing destination" in issue:
                intent.destination = "Thailand"  # Default destination
                logger.warning("   Fixed: Set default destination to Thailand")

            elif "Invalid duration" in issue:
                intent.duration_days = 3  # Default duration
                logger.warning("   Fixed: Set default duration to 3 days")

            elif "Low parsing confidence" in issue:
                # Can't fix low confidence, but log it
                logger.warning(f"   Cannot fix: {issue}")

        return intent

    def get_cost_stats(self) -> Dict[str, float]:
        """
        Get cost statistics for parsing operations.

        Returns:
            Dict with total cost and average per query
        """
        return {
            "total_cost_usd": self.total_cost,
            "model": "deepseek-chat"
        }


# =============================================================================
# Testing and Examples
# =============================================================================

def test_intent_parser():
    """Test intent parser with various queries"""
    logger.info("=" * 80)
    logger.info("TESTING INTENT PARSER")
    logger.info("=" * 80)

    parser = IntentParser()

    test_queries = [
        "Plan 5 days in Bangkok for solo budget traveler who loves parties",
        "Romantic weekend in Phuket for couple, beach resorts",
        "I'm backpacking Thailand for 2 weeks, need budget hostels and nightlife",
        "Family trip to Chiang Mai, kid-friendly, mid-range, 4 days",
        "Best food places in Bangkok",
        "What should I do in Krabi?",
        "Honeymoon in Koh Samui, luxury resort, 1 week",
        "Weekend beach trip, cheap accommodation"
    ]

    for query in test_queries:
        print("\n" + "=" * 80)
        print(f"Query: {query}")
        print("=" * 80)

        try:
            intent = parser.parse_query(query)

            print("\nParsed Intent:")
            print(f"  Destination: {intent.destination}")
            print(f"  Duration: {intent.duration_days} days")
            print(f"  Traveler: {intent.traveler_profile.traveler_type} ({intent.traveler_profile.budget_tier})")
            print(f"  Style: {intent.traveler_profile.travel_style}")
            print(f"  Interests: {intent.interests}")
            print(f"  Pace: {intent.pace}")
            print(f"  Confidence: {intent.confidence:.2f}")

            # Classify profile
            profile_key = parser.classify_traveler_profile(intent.traveler_profile)
            print(f"  Profile Classification: {profile_key}")

            # Extract constraints
            constraints = parser.extract_constraints(query, intent)
            print(f"  Hard Constraints: {list(constraints['hard'].keys())}")
            print(f"  Soft Preferences: {list(constraints['soft'].keys())}")

            # Validate
            is_valid, issues = parser.validate_intent(intent)
            print(f"  Valid: {is_valid}")
            if issues:
                print(f"  Issues: {issues}")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

    # Print cost stats
    print("\n" + "=" * 80)
    print("COST STATISTICS")
    print("=" * 80)
    stats = parser.get_cost_stats()
    print(f"Total cost: ${stats['total_cost_usd']:.6f}")
    print(f"Model: {stats['model']}")
    print(f"Average per query: ${stats['total_cost_usd'] / len(test_queries):.6f}")


if __name__ == '__main__':
    test_intent_parser()
