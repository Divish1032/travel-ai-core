#!/usr/bin/env python3
"""
LLM-Based Re-ranker for RAG Pipeline

Improves entity selection beyond vector similarity using semantic understanding.
Re-ranks retrieval candidates based on profile fit, vibe match, and practical value.

Features:
- Batch LLM scoring for cost efficiency
- Semantic "fit" evaluation
- Constraint enforcement (must-include, must-avoid)
- Unique experience boosting
- Redundancy penalization
- Explainable rankings

Cost: ~$0.0003 per itinerary (DeepSeek)

Author: TravelAI Team
Date: 2025-12-20
"""

import json
import math
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict

from src.utils.llm_client import extract_with_llm
from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    RetrievalCandidate,
    TravelerProfileInput
)

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# LLM re-ranking weights
RERANKING_WEIGHTS = {
    "llm_relevance": 0.6,     # LLM semantic understanding
    "profile_rating": 0.2,     # User profile rating
    "similarity": 0.1,         # Vector similarity
    "popularity": 0.1,         # Mention popularity
}

# Bonus/penalty factors
HIDDEN_GEM_BONUS = 0.15        # Boost for unique, high-quality entities
SPECIALTY_BONUS = 0.10         # Boost for special attributes
REDUNDANCY_PENALTY = 0.30      # Penalty for similar entities


# =============================================================================
# LLM Re-ranker
# =============================================================================

class LLMReranker:
    """
    LLM-based re-ranker for semantic understanding of entity fit.

    Re-ranks retrieval candidates using LLM to evaluate semantic "fit"
    beyond just vector similarity. Considers profile match, vibe, uniqueness.

    Example:
        >>> reranker = LLMReranker()
        >>> reranked = reranker.rerank_candidates(candidates, user_intent, top_k=12)
        >>> print(reranked[0].ranking_reason)
        'Perfect for budget party travelers, social atmosphere (8.5/10)'
    """

    def __init__(self, provider: str = "deepseek", enable_caching: bool = True):
        """
        Initialize LLM re-ranker.

        Args:
            provider: LLM provider (default: deepseek for cost efficiency)
            enable_caching: Enable ranking caching for similar queries
        """
        self.provider = provider
        self.enable_caching = enable_caching
        self.ranking_cache = {}  # Cache for profile-based rankings
        self.total_cost = 0.0

        logger.info("LLMReranker initialized")
        logger.info(f"   Provider: {provider}")
        logger.info(f"   Caching: {'enabled' if enable_caching else 'disabled'}")

    def rerank_candidates(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent,
        top_k: int = 12
    ) -> List[RetrievalCandidate]:
        """
        Re-rank candidates using LLM semantic understanding.

        Uses batch scoring for cost efficiency: sends all candidates
        to LLM at once for relevance evaluation.

        Args:
            candidates: Candidates from retrieval
            user_intent: User's intent
            top_k: Number of top candidates to return

        Returns:
            Re-ranked candidates with updated scores and explanations
        """
        logger.info("=" * 80)
        logger.info("🔄 LLM RE-RANKING")
        logger.info("=" * 80)
        logger.info(f"Input candidates: {len(candidates)}")
        logger.info(f"Target output: {top_k}")

        if not candidates:
            logger.warning("⚠️  No candidates to re-rank")
            return []

        # Step 1: Apply hard constraints
        logger.info("\n🔒 Step 1: Applying hard constraints")
        filtered = self.filter_by_constraints(candidates, user_intent)
        logger.info(f"   After constraints: {len(filtered)} candidates")

        # Step 2: Pre-filter for LLM call (cost optimization)
        logger.info("\n💰 Step 2: Pre-filtering for LLM call")
        candidates_for_llm = self._prefilter_for_llm(filtered, top_k=20)
        logger.info(f"   Sending to LLM: {len(candidates_for_llm)} candidates")

        # Step 3: Get LLM rankings
        logger.info("\n🤖 Step 3: LLM Batch Scoring")
        llm_rankings = self._get_llm_rankings(candidates_for_llm, user_intent)

        # Step 4: Merge scores
        logger.info("\n⚖️  Step 4: Merging scores")
        scored_candidates = self._merge_scores(
            candidates_for_llm,
            llm_rankings,
            user_intent
        )

        # Step 5: Boost unique experiences
        logger.info("\n✨ Step 5: Boosting unique experiences")
        scored_candidates = self.boost_unique_experiences(scored_candidates)

        # Step 6: Penalize redundancy
        logger.info("\n🎯 Step 6: Penalizing redundancy")
        scored_candidates = self.penalize_redundancy(scored_candidates)

        # Step 7: Final sort and select top_k
        scored_candidates.sort(key=lambda c: c.relevance_score or 0, reverse=True)
        final = scored_candidates[:top_k]

        logger.info("\n" + "=" * 80)
        logger.info("✅ RE-RANKING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Final count: {len(final)}")
        logger.info(f"Total cost: ${self.total_cost:.6f}")

        # Show top 3
        logger.info("\nTop 3 after re-ranking:")
        for i, c in enumerate(final[:3], 1):
            logger.info(f"   {i}. {c.canonical_name} ({c.entity_type})")
            logger.info(f"      Score: {c.relevance_score:.2f} - {c.ranking_reason}")

        return final

    def filter_by_constraints(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent
    ) -> List[RetrievalCandidate]:
        """
        Apply hard constraints before re-ranking.

        Enforces must-include, must-avoid, budget constraints.

        Args:
            candidates: Input candidates
            user_intent: User intent with constraints

        Returns:
            Filtered candidates
        """
        filtered = list(candidates)

        # Must-avoid filter
        if user_intent.must_avoid:
            must_avoid_lower = [item.lower() for item in user_intent.must_avoid]
            original_count = len(filtered)

            filtered = [
                c for c in filtered
                if not any(
                    avoid in c.canonical_name.lower() or
                    avoid in c.entity_type.lower()
                    for avoid in must_avoid_lower
                )
            ]

            if len(filtered) < original_count:
                removed = original_count - len(filtered)
                logger.info(f"   Removed {removed} entities (must-avoid)")

        # Must-include boost (don't filter, just boost scores)
        if user_intent.must_include:
            must_include_lower = [item.lower() for item in user_intent.must_include]
            boosted = 0

            for candidate in filtered:
                if any(
                    include in candidate.canonical_name.lower()
                    for include in must_include_lower
                ):
                    # Give huge boost to ensure inclusion
                    candidate.similarity_score = min(candidate.similarity_score + 0.3, 1.0)
                    boosted += 1

            if boosted > 0:
                logger.info(f"   Boosted {boosted} entities (must-include)")

        return filtered

    def _prefilter_for_llm(
        self,
        candidates: List[RetrievalCandidate],
        top_k: int = 20
    ) -> List[RetrievalCandidate]:
        """
        Pre-filter candidates before LLM call to reduce cost.

        Only send high-quality candidates to LLM.

        Args:
            candidates: Input candidates
            top_k: Max candidates to send to LLM

        Returns:
            Filtered candidates for LLM ranking
        """
        # Remove obvious mismatches (low similarity AND low rating)
        filtered = [
            c for c in candidates
            if c.similarity_score > 0.4 or c.profile_rating > 3.5
        ]

        # Sort by combined metric
        filtered.sort(
            key=lambda c: c.similarity_score * (c.profile_rating / 5.0),
            reverse=True
        )

        # Take top_k
        return filtered[:top_k]

    def _get_llm_rankings(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get LLM relevance scores for candidates.

        Uses batch scoring for cost efficiency.

        Args:
            candidates: Candidates to rank
            user_intent: User intent for context

        Returns:
            Dict mapping entity_id to {relevance_score, reasoning, why_it_fits, concerns}
        """
        if not candidates:
            return {}

        # Build profile description
        profile = user_intent.traveler_profile
        profile_desc = f"{profile.traveler_type} {profile.budget_tier} traveler"
        if profile.age_range:
            profile_desc += f" ({profile.age_range})"
        if profile.travel_style:
            profile_desc += f", {', '.join(profile.travel_style[:2])}"

        # Build candidate list for prompt
        candidate_list = []
        for i, c in enumerate(candidates, 1):
            # Get one-line description from entity data
            description = c.entity_data.get('description', 'No description')
            if len(description) > 100:
                description = description[:97] + "..."

            candidate_text = f"{i}. {c.canonical_name} ({c.entity_type})\n"
            candidate_text += f"   {description}\n"
            candidate_text += f"   Rated {c.profile_rating:.1f}/5 by {profile.budget_tier} travelers\n"
            candidate_text += f"   Mentioned by {c.mention_count} travelers"

            candidate_list.append(candidate_text)

        candidates_text = "\n\n".join(candidate_list)

        # Build budget info
        budget_text = ""
        if user_intent.budget_per_day:
            budget_text = f"Budget: ${user_intent.budget_per_day.get('min', 30)}-${user_intent.budget_per_day.get('max', 50)}/day"
        else:
            budget_text = f"Budget: {profile.budget_tier}"

        # Build prompt
        prompt = f"""Rank these places for this traveler on relevance (0-10 scale, higher=better fit).

USER PROFILE:
- Type: {profile_desc}
- Destination: {user_intent.destination}
- Duration: {user_intent.duration_days} days
- Interests: {', '.join(user_intent.interests) if user_intent.interests else 'General travel'}
- {budget_text}
- Pace: {user_intent.pace.value}

PLACES TO RANK:

{candidates_text}

SCORING CRITERIA:
1. Budget fit (is it affordable for their tier?)
2. Vibe match (does it match their interests and style?)
3. Uniqueness (is it a must-see or generic?)
4. Practical value (useful for this trip length/pace?)

Return ONLY valid JSON (no markdown):
{{
  "rankings": [
    {{
      "entity_id": "{candidates[0].entity_id}",
      "relevance_score": 8.5,
      "reasoning": "Perfect for budget party travelers, highly social atmosphere",
      "why_it_fits": "Matches nightlife and social interests, affordable",
      "concerns": "Can be very loud and crowded"
    }}
  ]
}}

Return rankings for ALL {len(candidates)} places."""

        try:
            # Call LLM
            result = extract_with_llm(
                prompt=prompt,
                provider=self.provider,
                temperature=0.3,
                max_tokens=2000
            )

            # Track cost
            self.total_cost += result['cost_usd']
            logger.info(f"   LLM call cost: ${result['cost_usd']:.6f}")

            if not result['success']:
                logger.error(f"   LLM ranking failed: {result['error']}")
                return self._fallback_rankings(candidates)

            # Parse response
            rankings_data = result['data']

            if 'rankings' not in rankings_data:
                logger.error("   Invalid LLM response: missing 'rankings' key")
                return self._fallback_rankings(candidates)

            # Convert to dict by entity_id
            rankings_dict = {}
            for ranking in rankings_data['rankings']:
                entity_id = ranking.get('entity_id')
                if entity_id:
                    rankings_dict[entity_id] = {
                        'relevance_score': float(ranking.get('relevance_score', 5.0)),
                        'reasoning': ranking.get('reasoning', ''),
                        'why_it_fits': ranking.get('why_it_fits', ''),
                        'concerns': ranking.get('concerns', '')
                    }

            logger.info(f"   Received rankings for {len(rankings_dict)} entities")
            return rankings_dict

        except Exception as e:
            logger.error(f"   LLM ranking exception: {e}")
            return self._fallback_rankings(candidates)

    def _fallback_rankings(
        self,
        candidates: List[RetrievalCandidate]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fallback rankings when LLM fails.

        Uses profile rating as proxy for relevance.

        Args:
            candidates: Candidates to rank

        Returns:
            Fallback rankings dict
        """
        logger.warning("   Using fallback rankings (score-only)")

        rankings = {}
        for candidate in candidates:
            # Use profile rating as relevance proxy (0-5 → 0-10)
            relevance = (candidate.profile_rating / 5.0) * 10.0

            rankings[candidate.entity_id] = {
                'relevance_score': relevance,
                'reasoning': f"Rated {candidate.profile_rating:.1f}/5 by similar travelers",
                'why_it_fits': "Based on traveler profile ratings",
                'concerns': ""
            }

        return rankings

    def _merge_scores(
        self,
        candidates: List[RetrievalCandidate],
        llm_rankings: Dict[str, Dict[str, Any]],
        user_intent: UserIntent
    ) -> List[RetrievalCandidate]:
        """
        Merge LLM scores with existing metrics.

        Combines LLM relevance, profile rating, similarity, popularity.

        Args:
            candidates: Candidates with existing scores
            llm_rankings: LLM rankings dict
            user_intent: User intent

        Returns:
            Candidates with merged scores
        """
        scored = []

        for candidate in candidates:
            # Get LLM ranking
            llm_ranking = llm_rankings.get(candidate.entity_id, {})
            llm_relevance = llm_ranking.get('relevance_score', 5.0)

            # Normalize LLM score to 0-1
            normalized_llm = llm_relevance / 10.0

            # Normalize other metrics
            normalized_rating = candidate.profile_rating / 5.0
            normalized_popularity = min(
                math.log(candidate.mention_count + 1) / 3.0,
                1.0
            )

            # Weighted combination
            final_score = (
                RERANKING_WEIGHTS['llm_relevance'] * normalized_llm +
                RERANKING_WEIGHTS['profile_rating'] * normalized_rating +
                RERANKING_WEIGHTS['similarity'] * candidate.similarity_score +
                RERANKING_WEIGHTS['popularity'] * normalized_popularity
            )

            candidate.relevance_score = round(final_score, 3)

            # Set ranking reason
            reasoning = llm_ranking.get('reasoning', '')
            candidate.ranking_reason = f"{reasoning} ({llm_relevance:.1f}/10)"

            scored.append(candidate)

        return scored

    def boost_unique_experiences(
        self,
        candidates: List[RetrievalCandidate]
    ) -> List[RetrievalCandidate]:
        """
        Boost unique/hidden gem entities.

        Gives bonus to:
        - Low mention count but high rating (hidden gems)
        - Unique attributes/specialties
        - Off-beaten-path experiences

        Args:
            candidates: Input candidates

        Returns:
            Candidates with boosted scores
        """
        for candidate in candidates:
            bonus = 0.0

            # Hidden gem: <5 mentions but >4.0 rating
            if candidate.mention_count < 5 and candidate.profile_rating >= 4.0:
                bonus += HIDDEN_GEM_BONUS
                logger.debug(f"   Hidden gem bonus: {candidate.canonical_name}")

            # Specialty: has unique attributes
            if candidate.attributes:
                unique_attrs = [
                    attr for attr in candidate.attributes
                    if attr.lower() in ['unique', 'special', 'authentic', 'local', 'hidden']
                ]
                if unique_attrs:
                    bonus += SPECIALTY_BONUS
                    logger.debug(f"   Specialty bonus: {candidate.canonical_name}")

            # Apply bonus
            if bonus > 0 and candidate.relevance_score:
                candidate.relevance_score = min(candidate.relevance_score + bonus, 1.0)

        return candidates

    def penalize_redundancy(
        self,
        candidates: List[RetrievalCandidate]
    ) -> List[RetrievalCandidate]:
        """
        Penalize very similar entities to ensure variety.

        Reduces scores for:
        - Multiple entities of same type in same area
        - Very similar names

        Args:
            candidates: Input candidates

        Returns:
            Candidates with penalties applied
        """
        # Group by type
        by_type = defaultdict(list)
        for candidate in candidates:
            by_type[candidate.entity_type].append(candidate)

        # For each type with >2 entities, penalize lower-ranked ones
        for entity_type, entities in by_type.items():
            if len(entities) <= 2:
                continue

            # Sort by score
            entities.sort(key=lambda c: c.relevance_score or 0, reverse=True)

            # Penalize 3rd onward
            for i, entity in enumerate(entities):
                if i >= 2:  # Keep top 2, penalize rest
                    penalty = REDUNDANCY_PENALTY * (i - 1) / 10  # Increasing penalty
                    if entity.relevance_score:
                        entity.relevance_score = max(entity.relevance_score - penalty, 0.0)
                        logger.debug(f"   Redundancy penalty: {entity.canonical_name} (-{penalty:.2f})")

        return candidates

    def explain_ranking(
        self,
        candidate: RetrievalCandidate,
        user_intent: UserIntent
    ) -> str:
        """
        Generate human-readable explanation for ranking.

        Uses LLM to create 2-sentence explanation.

        Args:
            candidate: Candidate to explain
            user_intent: User intent for context

        Returns:
            Human-readable explanation string
        """
        # Build profile description
        profile = user_intent.traveler_profile
        profile_desc = f"{profile.traveler_type} {profile.budget_tier} traveler"
        if profile.travel_style:
            profile_desc += f" who loves {', '.join(profile.travel_style[:2])}"

        # Build entity details
        themes = candidate.entity_data.get('themes', [])
        themes_text = ', '.join(themes[:3]) if themes else 'various activities'

        cost = candidate.entity_data.get('estimated_cost', 'varies')

        prompt = f"""Explain in 2 sentences why "{candidate.canonical_name}" is recommended for:

{profile_desc}
Interests: {', '.join(user_intent.interests) if user_intent.interests else 'general travel'}

Entity details:
- Rated {candidate.profile_rating:.1f}/5 by {profile.budget_tier} travelers
- Common themes: {themes_text}
- Cost: {cost}

Focus on "why this matches their profile". Be specific and enthusiastic.

Return ONLY the 2-sentence explanation (no JSON, no markdown)."""

        try:
            result = extract_with_llm(
                prompt=prompt,
                provider=self.provider,
                temperature=0.5,  # Slightly higher for natural language
                max_tokens=150
            )

            self.total_cost += result['cost_usd']

            if result['success']:
                # Extract text (might be in JSON wrapper)
                explanation = result['data']
                if isinstance(explanation, dict):
                    explanation = explanation.get('explanation', str(explanation))
                return str(explanation).strip()

        except Exception as e:
            logger.error(f"Failed to generate explanation: {e}")

        # Fallback explanation
        return (
            f"{candidate.canonical_name} is highly rated ({candidate.profile_rating:.1f}/5) "
            f"by {profile.budget_tier} travelers and matches your interests."
        )


# =============================================================================
# Testing
# =============================================================================

def test_reranker():
    """Test LLM re-ranker with example data."""
    from src.rag.retriever import RAGRetriever
    from src.vectordb import ChromaDBClient
    from src.utils.embedding_client import EmbeddingClient
    from src.utils.schemas import example_stage5_user_intent

    logger.info("=" * 80)
    logger.info("🧪 TESTING LLM RE-RANKER")
    logger.info("=" * 80)

    # Initialize
    try:
        chromadb = ChromaDBClient.initialize_from_env()
        embedding_client = EmbeddingClient()
        retriever = RAGRetriever(chromadb, embedding_client)
        reranker = LLMReranker(provider="deepseek")

        logger.info("✅ Components initialized")

    except Exception as e:
        logger.error(f"❌ Failed to initialize: {e}")
        return

    # Get test intent
    intent = example_stage5_user_intent()

    # Retrieve candidates
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Retrieval")
    logger.info("=" * 80)

    try:
        candidates = retriever.retrieve_for_itinerary(intent, top_k=20)
        logger.info(f"✅ Retrieved {len(candidates)} candidates")

        logger.info("\nTop 5 before re-ranking:")
        for i, c in enumerate(candidates[:5], 1):
            logger.info(f"   {i}. {c.canonical_name} ({c.entity_type})")
            logger.info(f"      Sim: {c.similarity_score:.2f}, Rating: {c.profile_rating:.1f}")

    except Exception as e:
        logger.error(f"❌ Retrieval failed: {e}")
        return

    # Re-rank
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Re-ranking")
    logger.info("=" * 80)

    try:
        reranked = reranker.rerank_candidates(candidates, intent, top_k=10)

        logger.info("\n✅ Re-ranking complete")
        logger.info(f"Total cost: ${reranker.total_cost:.6f}")

        logger.info("\nTop 5 after re-ranking:")
        for i, c in enumerate(reranked[:5], 1):
            logger.info(f"   {i}. {c.canonical_name} ({c.entity_type})")
            logger.info(f"      Final score: {c.relevance_score:.2f}")
            logger.info(f"      Reason: {c.ranking_reason}")

    except Exception as e:
        logger.error(f"❌ Re-ranking failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test explanation
    if reranked:
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Explanation")
        logger.info("=" * 80)

        try:
            explanation = reranker.explain_ranking(reranked[0], intent)
            logger.info(f"\nExplanation for {reranked[0].canonical_name}:")
            logger.info(f"   {explanation}")

        except Exception as e:
            logger.error(f"❌ Explanation failed: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ RE-RANKER TESTING COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    test_reranker()
