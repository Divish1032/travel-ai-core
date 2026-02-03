#!/usr/bin/env python3
"""
RAG Retriever - Intelligent Multi-Stage Retrieval

Retrieves diverse, relevant entities from Stage 4 vector database for itinerary generation.
Uses multi-stage pipeline to ensure quality, diversity, and geographic coherence.

Features:
- Profile-personalized semantic search
- Entity type diversification
- Geographic clustering for day planning
- Budget filtering and quality thresholds
- Similarity search for alternatives
- Context enrichment

Author: TravelAI Team
Date: 2025-12-20
"""

import json
import math
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional, Any

from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    RetrievalCandidate,
    TravelerProfileInput
)
from src.rag.vibe_extractor import VibeExtractor
from src.rag.vibe_scorer import VibeScorer

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Target entity type distribution for diversity
TARGET_DISTRIBUTION = {
    "area": 0.30,           # Neighborhoods, areas (context, where to stay)
    "activity": 0.25,       # Things to do
    "restaurant": 0.25,     # Food, dining
    "beach": 0.10,          # Beaches (if coastal)
    "attraction": 0.10,     # Temples, museums, landmarks
}

# Minimum quality thresholds
MIN_PROFILE_RATING = 3.0  # Minimum 3.0/5.0 stars
MIN_MENTION_COUNT = 2     # Mentioned by at least 2 travelers

# Geographic clustering radius (km)
GEO_CLUSTER_RADIUS_KM = 2.0


# =============================================================================
# Helper Functions
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two geographic points in kilometers.

    Uses Haversine formula for great-circle distance.

    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates

    Returns:
        Distance in kilometers
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


def classify_traveler_profile(profile: TravelerProfileInput) -> str:
    """
    Convert TravelerProfileInput to Stage 3 profile key.

    Args:
        profile: Traveler profile from user intent

    Returns:
        Profile key string (e.g., "solo_26-35_budget")
    """
    age = profile.age_range or "all"
    return f"{profile.traveler_type}_{age}_{profile.budget_tier}"


# =============================================================================
# RAG Retriever
# =============================================================================

class RAGRetriever:
    """
    Intelligent multi-stage retrieval for RAG itinerary generation.

    Retrieves diverse, relevant entities from Stage 4 vector database
    with profile personalization, diversification, and geographic clustering.

    Example:
        >>> retriever = RAGRetriever(chromadb_client, embedding_client)
        >>> candidates = retriever.retrieve_for_itinerary(user_intent, top_k=20)
        >>> print(f"Retrieved {len(candidates)} diverse entities")
    """

    def __init__(
        self,
        chromadb_client: ChromaDBClient,
        embedding_client: EmbeddingClient,
        min_quality_rating: float = MIN_PROFILE_RATING,
        min_mentions: int = MIN_MENTION_COUNT,
        enable_hybrid_search: bool = True
    ):
        """
        Initialize RAG retriever.

        Args:
            chromadb_client: ChromaDB client from Stage 4
            embedding_client: Embedding client from Stage 4
            min_quality_rating: Minimum profile rating threshold
            min_mentions: Minimum mention count threshold
            enable_hybrid_search: Enable hybrid semantic+keyword search (Phase 3)
        """
        self.chromadb = chromadb_client
        self.embedding_client = embedding_client
        self.min_quality_rating = min_quality_rating
        self.min_mentions = min_mentions
        self.enable_hybrid_search = enable_hybrid_search

        # Initialize vibe matching (Phase 2)
        self.vibe_extractor = VibeExtractor(use_llm=False)  # Keyword-based for speed
        self.vibe_scorer = VibeScorer()

        logger.info("RAGRetriever initialized")
        logger.info(f"   Quality threshold: {min_quality_rating}/5.0")
        logger.info(f"   Min mentions: {min_mentions}")
        logger.info("   Vibe matching: Enabled (12D keyword-based)")
        logger.info(f"   Hybrid search: {'Enabled' if enable_hybrid_search else 'Disabled'} (Phase 3)")

    # =========================================================================
    # PHASE 3: Hybrid Search Methods
    # =========================================================================

    def build_metadata_filter(
        self,
        user_intent: UserIntent,
        entity_types: Optional[List[str]] = None,
        budget_tier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build ChromaDB metadata filter for pre-filtering (Phase 3).

        Reduces search space before semantic search by filtering on:
        - Entity type (if specified)
        - Budget range (if specified)
        - City (from user intent)

        Args:
            user_intent: User's parsed intent
            entity_types: Optional list of entity types to filter
            budget_tier: Optional budget tier filter

        Returns:
            ChromaDB where clause dict

        Example:
            >>> filter = retriever.build_metadata_filter(
            ...     intent,
            ...     entity_types=['restaurant', 'cafe'],
            ...     budget_tier='budget'
            ... )
            >>> # Use in query: collection.query(..., where=filter)
        """
        conditions = []

        # City filter (always apply)
        conditions.append({"city": {"$eq": user_intent.destination}})

        # Quality filter
        conditions.append({"profile_rating": {"$gte": self.min_quality_rating}})

        # Entity type filter (if specified)
        if entity_types:
            if len(entity_types) == 1:
                conditions.append({"entity_type": {"$eq": entity_types[0]}})
            else:
                # Multiple types: use $in operator
                conditions.append({"entity_type": {"$in": entity_types}})

        # Budget tier filter (if specified)
        if budget_tier:
            # Map budget tier to price levels
            budget_map = {
                'budget': ['$', '$$'],
                'mid-range': ['$$', '$$$'],
                'luxury': ['$$$', '$$$$']
            }
            if budget_tier in budget_map:
                price_levels = budget_map[budget_tier]
                if len(price_levels) == 1:
                    conditions.append({"price_level": {"$eq": price_levels[0]}})
                else:
                    conditions.append({"price_level": {"$in": price_levels}})

        # Combine with AND
        if len(conditions) == 1:
            return conditions[0]
        else:
            return {"$and": conditions}

    def keyword_search(
        self,
        query_text: str,
        collection,
        top_k: int = 50,
        where_filter: Optional[Dict] = None
    ) -> List[Tuple[str, float, Dict]]:
        """
        Perform keyword-based search on document text (Phase 3).

        Simulates BM25-like search by matching keywords in entity documents.
        ChromaDB doesn't have built-in BM25, so we use document text matching.

        Args:
            query_text: Search query
            collection: ChromaDB collection to search
            top_k: Number of results
            where_filter: Optional metadata filter

        Returns:
            List of (entity_id, score, metadata) tuples
        """
        # Extract keywords from query (simple tokenization)
        keywords = set(query_text.lower().split())

        # Query collection with semantic search first (no better option in ChromaDB)
        # Then re-score based on keyword matches in document text
        try:
            query_embedding = self.embedding_client.embed_text(query_text)

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2,  # Get more, will re-score
                where=where_filter,
                include=["metadatas", "distances", "documents"]
            )

            if not results or not results['ids'] or len(results['ids'][0]) == 0:
                return []

            # Re-score based on keyword matches
            scored_results = []

            for i in range(len(results['ids'][0])):
                entity_id = results['ids'][0][i]
                metadata = results['metadatas'][0][i]
                document = results['documents'][0][i] if results['documents'] else ""

                # Count keyword matches in document
                doc_lower = document.lower()
                keyword_matches = sum(1 for kw in keywords if kw in doc_lower)

                # Keyword score (normalized by query length)
                keyword_score = keyword_matches / max(len(keywords), 1)

                scored_results.append((entity_id, keyword_score, metadata))

            # Sort by keyword score
            scored_results.sort(key=lambda x: x[1], reverse=True)

            return scored_results[:top_k]

        except Exception as e:
            logger.error(f"❌ Keyword search failed: {e}")
            return []

    def reciprocal_rank_fusion(
        self,
        semantic_results: List[Tuple[str, float, Dict]],
        keyword_results: List[Tuple[str, float, Dict]],
        k: int = 60
    ) -> List[Tuple[str, float, Dict]]:
        """
        Merge semantic and keyword results using Reciprocal Rank Fusion (Phase 3).

        RRF formula: score(d) = Σ 1 / (k + rank_i(d))
        where k=60 is a constant, rank_i is the rank in list i.

        Args:
            semantic_results: Results from semantic search (id, score, metadata)
            keyword_results: Results from keyword search (id, score, metadata)
            k: RRF constant (default: 60)

        Returns:
            Fused results sorted by RRF score

        Example:
            >>> semantic = [('e1', 0.9, {}), ('e2', 0.8, {})]
            >>> keyword = [('e2', 0.95, {}), ('e3', 0.85, {})]
            >>> fused = retriever.reciprocal_rank_fusion(semantic, keyword)
            >>> # e2 ranks high in both, so gets highest RRF score
        """
        # Build rank maps
        semantic_ranks = {entity_id: rank for rank, (entity_id, _, _) in enumerate(semantic_results)}
        keyword_ranks = {entity_id: rank for rank, (entity_id, _, _) in enumerate(keyword_results)}

        # Collect all unique entities
        all_entities = {}
        for entity_id, score, metadata in semantic_results:
            all_entities[entity_id] = metadata

        for entity_id, score, metadata in keyword_results:
            if entity_id not in all_entities:
                all_entities[entity_id] = metadata

        # Calculate RRF scores
        rrf_scores = []

        for entity_id, metadata in all_entities.items():
            rrf_score = 0.0

            # Add semantic rank contribution
            if entity_id in semantic_ranks:
                rrf_score += 1.0 / (k + semantic_ranks[entity_id])

            # Add keyword rank contribution
            if entity_id in keyword_ranks:
                rrf_score += 1.0 / (k + keyword_ranks[entity_id])

            rrf_scores.append((entity_id, rrf_score, metadata))

        # Sort by RRF score (descending)
        rrf_scores.sort(key=lambda x: x[1], reverse=True)

        return rrf_scores

    def hybrid_retrieve(
        self,
        user_intent: UserIntent,
        top_k: int = 60,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> List[RetrievalCandidate]:
        """
        Hybrid retrieval combining semantic search + keyword search + RRF (Phase 3).

        Pipeline:
        1. Build metadata pre-filter (reduces search space)
        2. Semantic search with filter
        3. Keyword search with filter
        4. Reciprocal Rank Fusion to merge results
        5. Convert to RetrievalCandidate

        Args:
            user_intent: User's parsed intent
            top_k: Number of entities to retrieve
            semantic_weight: Weight for semantic search (default: 0.7)
            keyword_weight: Weight for keyword search (default: 0.3)

        Returns:
            List of hybrid-retrieved candidates

        Example:
            >>> candidates = retriever.hybrid_retrieve(intent, top_k=20)
            >>> print(f"Retrieved {len(candidates)} via hybrid search")
        """
        if not self.enable_hybrid_search:
            # Fall back to semantic-only retrieval
            logger.info("   Hybrid search disabled, using semantic-only")
            return self._retrieve_broad(user_intent, top_k=top_k)

        logger.info("   🔄 Phase 3: Hybrid Search (Semantic + Keyword + RRF)")

        # Build query text
        query_parts = []
        if user_intent.interests:
            query_parts.extend(user_intent.interests)
        if user_intent.traveler_profile.travel_style:
            query_parts.extend(user_intent.traveler_profile.travel_style)
        query_parts.append(user_intent.destination)
        if user_intent.must_include:
            query_parts.extend(user_intent.must_include)

        query_text = " ".join(query_parts)

        # Step 1: Build metadata filter
        metadata_filter = self.build_metadata_filter(
            user_intent,
            budget_tier=user_intent.traveler_profile.budget_tier
        )
        logger.info(f"   Metadata filter: {list(metadata_filter.keys())}")

        # Step 2: Semantic search
        try:
            query_embedding = self.embedding_client.embed_text(query_text)

            semantic_results_raw = self.chromadb.profile_consensus_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=metadata_filter,
                include=["metadatas", "distances", "documents"]
            )

            semantic_results = []
            if semantic_results_raw and semantic_results_raw['ids'] and len(semantic_results_raw['ids'][0]) > 0:
                for i in range(len(semantic_results_raw['ids'][0])):
                    entity_id = semantic_results_raw['ids'][0][i]
                    metadata = semantic_results_raw['metadatas'][0][i]
                    distance = semantic_results_raw['distances'][0][i] if semantic_results_raw['distances'] else 0.5
                    score = 1.0 - distance  # Convert distance to similarity
                    semantic_results.append((entity_id, score, metadata))

            logger.info(f"   Semantic search: {len(semantic_results)} results")

        except Exception as e:
            logger.error(f"   ❌ Semantic search failed: {e}")
            semantic_results = []

        # Step 3: Keyword search
        keyword_results = self.keyword_search(
            query_text,
            self.chromadb.profile_consensus_collection,
            top_k=top_k,
            where_filter=metadata_filter
        )
        logger.info(f"   Keyword search: {len(keyword_results)} results")

        # Step 4: Reciprocal Rank Fusion
        if semantic_results and keyword_results:
            fused_results = self.reciprocal_rank_fusion(semantic_results, keyword_results)
            logger.info(f"   RRF fusion: {len(fused_results)} unique entities")
        elif semantic_results:
            fused_results = semantic_results
            logger.info("   Using semantic-only (no keyword results)")
        elif keyword_results:
            fused_results = keyword_results
            logger.info("   Using keyword-only (no semantic results)")
        else:
            logger.warning("   ⚠️  No results from hybrid search")
            return []

        # Step 5: Convert to RetrievalCandidate
        candidates = []
        for entity_id, rrf_score, metadata in fused_results[:top_k]:
            entity_data = json.loads(metadata.get('entity_json', '{}'))

            candidate = RetrievalCandidate(
                entity_id=entity_id,
                canonical_name=metadata.get('canonical_name', 'Unknown'),
                entity_type=metadata.get('entity_type', 'unknown'),
                city=metadata.get('city', user_intent.destination),
                similarity_score=rrf_score,  # Use RRF score as similarity
                profile_rating=float(metadata.get('profile_rating', 3.0)),
                mention_count=int(metadata.get('mention_count', 1)),
                entity_data=entity_data,
                profile_consensus=json.loads(metadata.get('consensus_json', '{}')),
                coordinates={
                    'lat': float(metadata.get('latitude', 0.0)),
                    'lon': float(metadata.get('longitude', 0.0))
                } if metadata.get('latitude') else {},
                source_video_ids=metadata.get('source_videos', '').split(','),
                best_for=metadata.get('best_for', '').split(',')
            )
            candidates.append(candidate)

        logger.info(f"   ✅ Hybrid retrieve: {len(candidates)} candidates")

        return candidates

    # =========================================================================
    # END PHASE 3: Hybrid Search Methods
    # =========================================================================

    def retrieve_for_itinerary(
        self,
        user_intent: UserIntent,
        top_k: int = 20
    ) -> List[RetrievalCandidate]:
        """
        Main retrieval orchestration for itinerary generation.

        Multi-stage pipeline:
        1. Profile-personalized broad retrieval
        2. Entity type diversification
        3. Geographic clustering
        4. Budget filtering
        5. Relevance ranking

        Args:
            user_intent: User's parsed intent
            top_k: Number of entities to retrieve

        Returns:
            List of diverse, relevant retrieval candidates
        """
        logger.info("=" * 80)
        logger.info("🔍 RAG RETRIEVAL PIPELINE")
        logger.info("=" * 80)
        logger.info(f"Destination: {user_intent.destination}")
        logger.info(f"Profile: {user_intent.traveler_profile.to_profile_key()}")
        logger.info(f"Target: {top_k} entities")

        # STAGE 1: Profile-personalized broad retrieval
        logger.info("\n📥 Stage 1: Profile-Personalized Retrieval")
        broad_candidates = self._retrieve_broad(user_intent, top_k=top_k * 3)

        logger.info(f"   Retrieved {len(broad_candidates)} candidates")

        # Trigger fallback if insufficient results (< 25% of target)
        min_acceptable = max(5, top_k // 4)  # At least 5 entities or 25% of target
        if len(broad_candidates) < min_acceptable:
            logger.warning(f"⚠️  Only {len(broad_candidates)} candidates found (need {min_acceptable}+) - trying fallback retrieval")
            fallback_candidates = self._fallback_retrieval(user_intent, top_k=top_k * 2)

            # Merge with existing candidates (deduplicate by entity_id)
            existing_ids = {c.entity_id for c in broad_candidates}
            for candidate in fallback_candidates:
                if candidate.entity_id not in existing_ids:
                    broad_candidates.append(candidate)
                    existing_ids.add(candidate.entity_id)

            logger.info(f"   After fallback: {len(broad_candidates)} total candidates")

        # STAGE 2: Diversification
        logger.info("\n🎨 Stage 2: Entity Type Diversification")
        diverse_candidates = self._diversify_by_type(broad_candidates, top_k=top_k)
        logger.info(f"   Diversified to {len(diverse_candidates)} entities")

        # Log type distribution
        type_dist = Counter([c.entity_type for c in diverse_candidates])
        for etype, count in type_dist.most_common():
            pct = (count / len(diverse_candidates)) * 100
            logger.info(f"   - {etype}: {count} ({pct:.1f}%)")

        # STAGE 3: Geographic clustering
        logger.info("\n🗺️  Stage 3: Geographic Clustering")
        geo_clusters = self._cluster_by_geography(diverse_candidates)
        logger.info(f"   Identified {len(geo_clusters)} geographic clusters")
        for cluster_name, entities in geo_clusters.items():
            logger.info(f"   - {cluster_name}: {len(entities)} entities")

        # STAGE 4: Budget filtering
        if user_intent.budget_per_day:
            logger.info("\n💰 Stage 4: Budget Filtering")
            diverse_candidates = self._filter_by_budget(
                diverse_candidates,
                user_intent.budget_per_day,
                user_intent.traveler_profile.budget_tier
            )
            logger.info(f"   After budget filter: {len(diverse_candidates)} entities")

        # STAGE 5: Add context entities
        logger.info("\n📚 Stage 5: Context Enrichment")
        diverse_candidates = self.add_context_entities(diverse_candidates, user_intent)
        logger.info(f"   After context enrichment: {len(diverse_candidates)} entities")

        # STAGE 5.5: Vibe Reranking (NEW! - Phase 2)
        logger.info("\n🎭 Stage 5.5: Vibe-Based Reranking")
        diverse_candidates = self._rerank_by_vibes(diverse_candidates, user_intent)
        logger.info("   Reranked with vibe matching")

        # STAGE 6: Final relevance ranking
        logger.info("\n⭐ Stage 6: Relevance Ranking")
        ranked_candidates = self.rank_by_relevance(diverse_candidates, user_intent)

        # Take top_k
        final_candidates = ranked_candidates[:top_k]

        # Calculate final metrics
        diversity_score = self.calculate_diversity_score(final_candidates)

        logger.info("\n" + "=" * 80)
        logger.info("✅ RETRIEVAL COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Final count: {len(final_candidates)} entities")
        logger.info(f"Diversity score: {diversity_score:.2f}")
        logger.info(f"Avg relevance: {sum(c.relevance_score or 0 for c in final_candidates) / len(final_candidates):.2f}")

        return final_candidates

    def _retrieve_broad(
        self,
        user_intent: UserIntent,
        top_k: int = 60
    ) -> List[RetrievalCandidate]:
        """
        Stage 1: Broad profile-personalized retrieval.

        Uses hybrid search (Phase 3) if enabled, otherwise falls back to
        semantic-only search.

        Args:
            user_intent: User intent
            top_k: Number to retrieve

        Returns:
            List of broad retrieval candidates
        """
        # PHASE 3: Try hybrid search first if enabled
        if self.enable_hybrid_search:
            try:
                logger.info("   Using hybrid search (semantic + keyword + RRF)")
                return self.hybrid_retrieve(user_intent, top_k=top_k)
            except Exception as e:
                logger.warning(f"   Hybrid search failed, falling back to semantic-only: {e}")
                # Continue to semantic-only below

        # Build semantic query
        query_parts = []

        # Interests
        if user_intent.interests:
            query_parts.extend(user_intent.interests)

        # Travel style
        if user_intent.traveler_profile.travel_style:
            query_parts.extend(user_intent.traveler_profile.travel_style)

        # Destination
        query_parts.append(user_intent.destination)

        # Must-include keywords
        if user_intent.must_include:
            query_parts.extend(user_intent.must_include)

        query_text = " ".join(query_parts)
        logger.info(f"   Query: {query_text}")

        # Classify profile
        profile_key = classify_traveler_profile(user_intent.traveler_profile)
        logger.info(f"   Profile: {profile_key}")

        # Search profile consensus collection
        try:
            # Get embedding
            query_embedding = self.embedding_client.embed_text(query_text)

            # Search with filters (case-insensitive city matching)
            results = self.chromadb.profile_consensus_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={
                    "$and": [
                        {"city": {"$eq": user_intent.destination}},  # Try exact match first
                        {"profile_rating": {"$gte": self.min_quality_rating}}
                    ]
                },
                include=["metadatas", "distances"]
            )

            # If no results, try case-insensitive search
            if not results or not results['ids'] or len(results['ids'][0]) == 0:
                logger.info(f"   No exact match for '{user_intent.destination}', trying case-insensitive...")
                # Remove city filter and filter manually
                results = self.chromadb.profile_consensus_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k * 2,  # Get more to filter manually
                    where={"profile_rating": {"$gte": self.min_quality_rating}},
                    include=["metadatas", "distances"]
                )

                # Manually filter by case-insensitive city match
                if results and results['ids'] and len(results['ids'][0]) > 0:
                    filtered_ids = []
                    filtered_metadatas = []
                    filtered_distances = []

                    dest_lower = user_intent.destination.lower()
                    for i in range(len(results['ids'][0])):
                        city = results['metadatas'][0][i].get('city', '')
                        if dest_lower in city.lower():  # Case-insensitive partial match
                            filtered_ids.append(results['ids'][0][i])
                            filtered_metadatas.append(results['metadatas'][0][i])
                            if results['distances']:
                                filtered_distances.append(results['distances'][0][i])

                    # Reconstruct results
                    if filtered_ids:
                        results = {
                            'ids': [filtered_ids[:top_k]],
                            'metadatas': [filtered_metadatas[:top_k]],
                            'distances': [filtered_distances[:top_k]] if filtered_distances else None
                        }
                        logger.info(f"   Found {len(filtered_ids)} case-insensitive matches")
                    else:
                        results = {'ids': [[]], 'metadatas': [[]], 'distances': None}

            # Convert to RetrievalCandidate
            candidates = []

            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    entity_id = results['ids'][0][i]
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i] if results['distances'] else 0.5

                    # Convert distance to similarity (cosine distance → similarity)
                    similarity_score = 1.0 - distance

                    # Parse entity data
                    entity_data = json.loads(metadata.get('entity_json', '{}'))

                    candidate = RetrievalCandidate(
                        entity_id=entity_id,
                        canonical_name=metadata.get('canonical_name', 'Unknown'),
                        entity_type=metadata.get('entity_type', 'unknown'),
                        city=metadata.get('city', user_intent.destination),
                        similarity_score=similarity_score,
                        profile_rating=float(metadata.get('profile_rating', 3.0)),
                        mention_count=int(metadata.get('mention_count', 1)),
                        entity_data=entity_data,
                        profile_consensus=json.loads(metadata.get('consensus_json', '{}')),
                        coordinates={
                            'lat': float(metadata.get('latitude', 0.0)),
                            'lon': float(metadata.get('longitude', 0.0))
                        } if metadata.get('latitude') else {},
                        source_video_ids=metadata.get('source_videos', '').split(','),
                        best_for=metadata.get('best_for', '').split(',')
                    )

                    candidates.append(candidate)

            return candidates

        except Exception as e:
            logger.error(f"❌ Broad retrieval failed: {e}")
            return []

    def _fallback_retrieval(
        self,
        user_intent: UserIntent,
        top_k: int = 40
    ) -> List[RetrievalCandidate]:
        """
        Fallback retrieval when main retrieval fails.

        Tries multiple strategies:
        1. Profile consensus with relaxed filters
        2. Main entities collection (broader, has more data)

        Args:
            user_intent: User intent
            top_k: Number to retrieve

        Returns:
            List of fallback candidates
        """
        logger.info("   🔄 Fallback: Trying multiple retrieval strategies")

        candidates = []

        # Strategy 1: Profile consensus with no quality filter
        try:
            logger.info("   Strategy 1: Profile consensus (no quality filter)")
            query_text = user_intent.destination
            query_embedding = self.embedding_client.embed_text(query_text)

            # Search profile consensus without quality filter
            results = self.chromadb.profile_consensus_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "distances"]
            )

            # Filter manually by destination (case-insensitive)
            if results and results['ids'] and len(results['ids'][0]) > 0:
                dest_lower = user_intent.destination.lower()
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    city = metadata.get('city', '')

                    if dest_lower in city.lower():
                        entity_id = results['ids'][0][i]
                        distance = results['distances'][0][i] if results['distances'] else 0.5
                        similarity_score = 1.0 - distance
                        entity_data = json.loads(metadata.get('entity_json', '{}'))

                        candidate = RetrievalCandidate(
                            entity_id=entity_id,
                            canonical_name=metadata.get('canonical_name', 'Unknown'),
                            entity_type=metadata.get('entity_type', 'unknown'),
                            city=metadata.get('city', user_intent.destination),
                            similarity_score=similarity_score,
                            profile_rating=float(metadata.get('profile_rating', 3.0)),
                            mention_count=int(metadata.get('mention_count', 1)),
                            entity_data=entity_data,
                            coordinates={
                                'lat': float(metadata.get('latitude', 0.0)),
                                'lon': float(metadata.get('longitude', 0.0))
                            } if metadata.get('latitude') else {},
                            source_video_ids=metadata.get('source_videos', '').split(',')
                        )
                        candidates.append(candidate)

                logger.info(f"   Retrieved {len(candidates)} from profile consensus")

        except Exception as e:
            logger.warning(f"   Strategy 1 failed: {e}")

        # Strategy 2: Main entities collection (if still need more)
        if len(candidates) < top_k // 2:
            try:
                logger.info("   Strategy 2: Main entities collection")

                # Build richer query
                query_parts = [user_intent.destination]
                if user_intent.interests:
                    query_parts.extend(user_intent.interests[:3])
                query_text = " ".join(query_parts)

                query_embedding = self.embedding_client.embed_text(query_text)

                # Search main entities collection
                results = self.chromadb.entities_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["metadatas", "distances"]
                )

                # Filter by destination (case-insensitive)
                if results and results['ids'] and len(results['ids'][0]) > 0:
                    dest_lower = user_intent.destination.lower()
                    for i in range(len(results['ids'][0])):
                        metadata = results['metadatas'][0][i]
                        city = metadata.get('city', '')

                        if dest_lower in city.lower():
                            entity_id = results['ids'][0][i]
                            distance = results['distances'][0][i] if results['distances'] else 0.5
                            similarity_score = 1.0 - distance
                            entity_data = json.loads(metadata.get('entity_json', '{}'))

                            candidate = RetrievalCandidate(
                                entity_id=entity_id,
                                canonical_name=metadata.get('canonical_name', 'Unknown'),
                                entity_type=metadata.get('entity_type', 'unknown'),
                                city=metadata.get('city', user_intent.destination),
                                similarity_score=similarity_score,
                                profile_rating=float(metadata.get('consensus_rating', 3.5)),  # Use consensus_rating for entities
                                mention_count=int(metadata.get('mention_count', 1)),
                                entity_data=entity_data,
                                coordinates={
                                    'lat': float(metadata.get('latitude', 0.0)),
                                    'lon': float(metadata.get('longitude', 0.0))
                                } if metadata.get('latitude') else {},
                                source_video_ids=metadata.get('source_videos', '').split(',')
                            )
                            candidates.append(candidate)

                    logger.info(f"   Retrieved {len(candidates)} total (including {len(candidates) - len([c for c in candidates if 'profile' in str(c)])} from entities)")

            except Exception as e:
                logger.warning(f"   Strategy 2 failed: {e}")

        logger.info(f"   ✅ Fallback retrieved {len(candidates)} total candidates")
        return candidates

    def _rerank_by_vibes(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent
    ) -> List[RetrievalCandidate]:
        """
        Stage 5.5: Rerank candidates by vibe matching (NEW! - Phase 2).

        Combines semantic similarity with 12D vibe similarity for better
        intent matching.

        Args:
            candidates: Input candidates with semantic scores
            user_intent: User's parsed intent

        Returns:
            Reranked candidates with updated relevance scores
        """
        # Extract query vibes from user intent
        query_text = user_intent.query_text or ""
        if not query_text:
            # Fallback: construct from intent
            query_text = f"{user_intent.destination} {' '.join(user_intent.interests or [])}"

        query_vibes = self.vibe_extractor.extract_query_vibes(query_text)

        # Extract vibes from each candidate and compute vibe scores
        for candidate in candidates:
            # Try to get vibes from metadata (if already extracted in Stage 4)
            entity_vibes = None
            if hasattr(candidate, 'metadata') and candidate.metadata:
                vibes_json = candidate.metadata.get('vibes_json')
                if vibes_json:
                    try:
                        entity_vibes = json.loads(vibes_json)
                    except:
                        pass

            # If no vibes in metadata, extract from entity data
            if not entity_vibes:
                # Create entity dict from candidate
                entity_dict = {
                    'entity_id': candidate.entity_id,
                    'entity_type': candidate.entity_type,
                    'attributes': candidate.metadata or {},
                    'experiences': []  # Not available in candidate
                }
                entity_vibes = self.vibe_extractor.extract_entity_vibes(entity_dict, use_experiences=False)

            # Compute vibe similarity
            vibe_score = self.vibe_scorer.compute_similarity(query_vibes, entity_vibes)

            # Combine with existing similarity score (weighted)
            # 60% semantic similarity + 40% vibe similarity
            original_score = candidate.similarity_score or 0.5
            combined_score = 0.6 * original_score + 0.4 * vibe_score

            # Update relevance score
            candidate.relevance_score = combined_score

            # Store vibe score for debugging
            if not candidate.metadata:
                candidate.metadata = {}
            candidate.metadata['vibe_score'] = vibe_score
            candidate.metadata['combined_score'] = combined_score

        # Sort by updated relevance score
        candidates.sort(key=lambda c: c.relevance_score or 0, reverse=True)

        # Log top vibes
        logger.info(f"   Query vibes: {', '.join([f'{k}={v:.2f}' for k, v in query_vibes.items() if v > 0.3])}")
        logger.info(f"   Vibe scores: min={min(c.metadata.get('vibe_score', 0) for c in candidates):.2f}, "
                   f"max={max(c.metadata.get('vibe_score', 0) for c in candidates):.2f}, "
                   f"avg={sum(c.metadata.get('vibe_score', 0) for c in candidates) / len(candidates):.2f}")

        return candidates

    def _diversify_by_type(
        self,
        candidates: List[RetrievalCandidate],
        top_k: int = 20
    ) -> List[RetrievalCandidate]:
        """
        Stage 2: Ensure entity type diversity.

        Samples from each entity type proportionally to target distribution.

        Args:
            candidates: Input candidates
            top_k: Target number of diverse entities

        Returns:
            Diversified list of candidates
        """
        # Group by type
        by_type = defaultdict(list)
        for candidate in candidates:
            by_type[candidate.entity_type].append(candidate)

        # Calculate target counts per type
        target_counts = {}
        for etype, proportion in TARGET_DISTRIBUTION.items():
            target_counts[etype] = int(top_k * proportion)

        # Sample from each type
        diverse = []

        for etype, target_count in target_counts.items():
            available = by_type.get(etype, [])

            # Sort by relevance (similarity * rating)
            available.sort(
                key=lambda c: c.similarity_score * (c.profile_rating / 5.0),
                reverse=True
            )

            # Take top N
            sampled = available[:target_count]
            diverse.extend(sampled)

        # If we don't have enough, add remaining from all types
        if len(diverse) < top_k:
            remaining = [c for c in candidates if c not in diverse]
            remaining.sort(
                key=lambda c: c.similarity_score * (c.profile_rating / 5.0),
                reverse=True
            )
            diverse.extend(remaining[:top_k - len(diverse)])

        return diverse[:top_k]

    def _cluster_by_geography(
        self,
        candidates: List[RetrievalCandidate]
    ) -> Dict[str, List[RetrievalCandidate]]:
        """
        Stage 3: Group entities by geographic location.

        Simple clustering based on distance threshold.
        Helps with day-by-day planning (group nearby entities per day).

        Args:
            candidates: Input candidates

        Returns:
            Dict mapping cluster name to entities
        """
        clusters = {}
        cluster_id = 0
        assigned = set()

        for candidate in candidates:
            if candidate.entity_id in assigned:
                continue

            # Skip if no coordinates
            if not candidate.coordinates or 'lat' not in candidate.coordinates:
                cluster_name = f"cluster_{cluster_id}"
                clusters[cluster_name] = [candidate]
                assigned.add(candidate.entity_id)
                cluster_id += 1
                continue

            # Start new cluster
            cluster_name = f"cluster_{cluster_id}"
            cluster = [candidate]
            assigned.add(candidate.entity_id)

            lat1 = candidate.coordinates['lat']
            lon1 = candidate.coordinates['lon']

            # Find nearby entities
            for other in candidates:
                if other.entity_id in assigned:
                    continue

                if not other.coordinates or 'lat' not in other.coordinates:
                    continue

                lat2 = other.coordinates['lat']
                lon2 = other.coordinates['lon']

                distance = haversine_distance(lat1, lon1, lat2, lon2)

                if distance <= GEO_CLUSTER_RADIUS_KM:
                    cluster.append(other)
                    assigned.add(other.entity_id)

            clusters[cluster_name] = cluster
            cluster_id += 1

        return clusters

    def _filter_by_budget(
        self,
        candidates: List[RetrievalCandidate],
        budget_per_day: Dict[str, float],
        budget_tier: str
    ) -> List[RetrievalCandidate]:
        """
        Stage 4: Filter entities by budget constraints.

        Args:
            candidates: Input candidates
            budget_per_day: Budget range per day
            budget_tier: Budget tier (budget/mid-range/luxury)

        Returns:
            Budget-filtered candidates
        """
        # For now, simple tier-based filtering
        # In production, would parse actual costs from entity_data

        filtered = []

        for candidate in candidates:
            # Check if entity has budget tier info
            entity_tier = candidate.entity_data.get('budget_tier', budget_tier)

            # Keep if matches or is more budget-friendly
            tier_order = {'budget': 0, 'mid-range': 1, 'luxury': 2}
            user_tier_level = tier_order.get(budget_tier, 1)
            entity_tier_level = tier_order.get(entity_tier, 1)

            if entity_tier_level <= user_tier_level + 1:  # Allow one tier up
                filtered.append(candidate)

        return filtered

    def add_context_entities(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent
    ) -> List[RetrievalCandidate]:
        """
        Stage 5: Add contextual background entities.

        Adds helpful context entities based on user intent:
        - Arrival/logistics info
        - Getting around tips
        - General city context

        Args:
            candidates: Current candidates
            user_intent: User intent

        Returns:
            Candidates with context entities added
        """
        # For now, just return as-is
        # In production, would query for specific context entities
        # e.g., "getting to Bangkok", "Bangkok arrival tips"

        return candidates

    def rank_by_relevance(
        self,
        candidates: List[RetrievalCandidate],
        user_intent: UserIntent
    ) -> List[RetrievalCandidate]:
        """
        Stage 6: Rank candidates by multi-dimensional relevance.

        Scoring formula:
        Score = 0.4 * similarity_score
              + 0.3 * (profile_rating / 5.0)
              + 0.2 * log(mention_count + 1) / 3.0
              + 0.1 * interests_match

        Args:
            candidates: Candidates to rank
            user_intent: User intent for interest matching

        Returns:
            Ranked candidates (sorted descending by relevance)
        """
        for candidate in candidates:
            # Calculate interests match
            interests_match = self._calculate_interests_match(candidate, user_intent)

            # Normalized popularity (log scale)
            normalized_popularity = min(
                math.log(candidate.mention_count + 1) / 3.0,
                1.0
            )

            # Normalized rating
            normalized_rating = candidate.profile_rating / 5.0

            # Combined relevance score
            relevance = (
                0.4 * candidate.similarity_score +
                0.3 * normalized_rating +
                0.2 * normalized_popularity +
                0.1 * interests_match
            )

            candidate.relevance_score = round(relevance, 3)

            # Set ranking reason
            candidate.ranking_reason = (
                f"Similarity: {candidate.similarity_score:.2f}, "
                f"Rating: {candidate.profile_rating:.1f}/5.0, "
                f"Mentions: {candidate.mention_count}, "
                f"Interests: {interests_match:.2f}"
            )

        # Sort by relevance
        candidates.sort(key=lambda c: c.relevance_score or 0, reverse=True)

        return candidates

    def _calculate_interests_match(
        self,
        candidate: RetrievalCandidate,
        user_intent: UserIntent
    ) -> float:
        """
        Calculate how well entity matches user interests.

        Args:
            candidate: Retrieval candidate
            user_intent: User intent

        Returns:
            Interest match score (0-1)
        """
        if not user_intent.interests:
            return 0.5  # Neutral

        # Get entity attributes
        entity_attrs = set(candidate.attributes)
        entity_attrs.update(candidate.best_for)

        # Convert to lowercase
        entity_attrs = {attr.lower() for attr in entity_attrs}
        user_interests = {interest.lower() for interest in user_intent.interests}

        # Calculate overlap
        overlap = entity_attrs.intersection(user_interests)

        if not user_interests:
            return 0.5

        match_score = len(overlap) / len(user_interests)

        return min(match_score, 1.0)

    def calculate_diversity_score(
        self,
        candidates: List[RetrievalCandidate]
    ) -> float:
        """
        Calculate diversity score for retrieval set.

        Measures:
        - Entity type diversity (0-1)
        - Geographic diversity (0-1)
        - Rating diversity (0-1)

        Args:
            candidates: List of candidates

        Returns:
            Overall diversity score (0-1)
        """
        if not candidates:
            return 0.0

        # Type diversity (Shannon entropy)
        type_counts = Counter([c.entity_type for c in candidates])
        total = len(candidates)

        type_entropy = 0.0
        for count in type_counts.values():
            p = count / total
            if p > 0:
                type_entropy -= p * math.log(p)

        # Normalize by max entropy (log of number of types)
        max_entropy = math.log(len(type_counts)) if len(type_counts) > 1 else 1.0
        type_diversity = type_entropy / max_entropy if max_entropy > 0 else 0.0

        # Geographic diversity (average pairwise distance)
        geo_diversity = 0.0
        valid_coords = [
            c for c in candidates
            if c.coordinates and 'lat' in c.coordinates
        ]

        if len(valid_coords) >= 2:
            distances = []
            for i, c1 in enumerate(valid_coords):
                for c2 in valid_coords[i+1:]:
                    dist = haversine_distance(
                        c1.coordinates['lat'], c1.coordinates['lon'],
                        c2.coordinates['lat'], c2.coordinates['lon']
                    )
                    distances.append(dist)

            if distances:
                avg_distance = sum(distances) / len(distances)
                # Normalize to 0-1 (10km = high diversity)
                geo_diversity = min(avg_distance / 10.0, 1.0)

        # Rating diversity (standard deviation)
        ratings = [c.profile_rating for c in candidates]
        if len(ratings) > 1:
            mean_rating = sum(ratings) / len(ratings)
            variance = sum((r - mean_rating) ** 2 for r in ratings) / len(ratings)
            stddev = math.sqrt(variance)
            # Normalize (stddev of 1.0 = good diversity)
            rating_diversity = min(stddev, 1.0)
        else:
            rating_diversity = 0.0

        # Combined diversity
        overall_diversity = (
            0.5 * type_diversity +
            0.3 * geo_diversity +
            0.2 * rating_diversity
        )

        return round(overall_diversity, 2)

    def retrieve_similar_entities(
        self,
        entity_id: str,
        top_k: int = 5
    ) -> List[RetrievalCandidate]:
        """
        Find entities similar to a given entity.

        Useful for "places like X" or suggesting alternatives.

        Args:
            entity_id: Entity ID to find similar entities for
            top_k: Number of similar entities to retrieve

        Returns:
            List of similar entities
        """
        try:
            # Get entity embedding from entities collection
            results = self.chromadb.entities_collection.get(
                ids=[f"entity_{entity_id}"]
            )

            if not results or not results['embeddings']:
                logger.warning(f"Entity {entity_id} not found")
                return []

            entity_embedding = results['embeddings'][0]

            # Search for similar entities
            similar_results = self.chromadb.entities_collection.query(
                query_embeddings=[entity_embedding],
                n_results=top_k + 1  # +1 to exclude self
            )

            # Convert to candidates
            candidates = []

            if similar_results and similar_results['ids']:
                for i in range(len(similar_results['ids'][0])):
                    result_id = similar_results['ids'][0][i]

                    # Skip self
                    if result_id == f"entity_{entity_id}":
                        continue

                    metadata = similar_results['metadatas'][0][i]
                    distance = similar_results['distances'][0][i] if similar_results['distances'] else 0.5

                    similarity_score = 1.0 - distance
                    entity_data = json.loads(metadata.get('entity_json', '{}'))

                    candidate = RetrievalCandidate(
                        entity_id=result_id.replace('entity_', ''),
                        canonical_name=metadata.get('canonical_name', 'Unknown'),
                        entity_type=metadata.get('entity_type', 'unknown'),
                        city=metadata.get('city', ''),
                        similarity_score=similarity_score,
                        profile_rating=float(metadata.get('avg_rating', 3.0)),
                        mention_count=int(metadata.get('mention_count', 1)),
                        entity_data=entity_data,
                        coordinates={
                            'lat': float(metadata.get('latitude', 0.0)),
                            'lon': float(metadata.get('longitude', 0.0))
                        } if metadata.get('latitude') else {}
                    )

                    candidates.append(candidate)

            return candidates[:top_k]

        except Exception as e:
            logger.error(f"❌ Similar entity retrieval failed: {e}")
            return []

    def retrieve_by_category(
        self,
        category: str,
        user_intent: UserIntent,
        top_k: int = 10
    ) -> List[RetrievalCandidate]:
        """
        Retrieve entities by specific category.

        Categories:
        - "accommodation" → hotels, hostels, guesthouses
        - "food" → restaurants, street food, markets
        - "nightlife" → bars, clubs, party areas

        Args:
            category: Category name
            user_intent: User intent for filtering
            top_k: Number to retrieve

        Returns:
            Category-filtered entities
        """
        # Map category to entity types
        category_types = {
            "accommodation": ["hotel", "hostel", "guesthouse", "resort"],
            "food": ["restaurant", "street_food", "market", "cafe"],
            "nightlife": ["bar", "club", "nightlife_area"],
            "activities": ["activity", "tour", "experience"],
            "attractions": ["attraction", "temple", "museum", "landmark"]
        }

        target_types = category_types.get(category.lower(), [category])

        try:
            # Build query
            query_text = f"{category} {user_intent.destination}"
            query_embedding = self.embedding_client.embed_text(query_text)

            # Search entities collection
            results = self.chromadb.entities_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2,  # Retrieve more, filter later
                where={"city": {"$eq": user_intent.destination}}
            )

            # Convert and filter
            candidates = []

            if results and results['ids']:
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    entity_type = metadata.get('entity_type', '')

                    # Check if matches category
                    if entity_type not in target_types:
                        continue

                    entity_id = results['ids'][0][i].replace('entity_', '')
                    distance = results['distances'][0][i] if results['distances'] else 0.5

                    similarity_score = 1.0 - distance
                    entity_data = json.loads(metadata.get('entity_json', '{}'))

                    candidate = RetrievalCandidate(
                        entity_id=entity_id,
                        canonical_name=metadata.get('canonical_name', 'Unknown'),
                        entity_type=entity_type,
                        city=metadata.get('city', user_intent.destination),
                        similarity_score=similarity_score,
                        profile_rating=float(metadata.get('avg_rating', 3.0)),
                        mention_count=int(metadata.get('mention_count', 1)),
                        entity_data=entity_data,
                        coordinates={
                            'lat': float(metadata.get('latitude', 0.0)),
                            'lon': float(metadata.get('longitude', 0.0))
                        } if metadata.get('latitude') else {}
                    )

                    candidates.append(candidate)

            # Sort by relevance
            candidates.sort(
                key=lambda c: c.similarity_score * (c.profile_rating / 5.0),
                reverse=True
            )

            return candidates[:top_k]

        except Exception as e:
            logger.error(f"❌ Category retrieval failed: {e}")
            return []


# =============================================================================
# Testing
# =============================================================================

def test_retriever():
    """Test RAG retriever with different user intents."""
    from src.utils.schemas import example_stage5_user_intent

    logger.info("=" * 80)
    logger.info("🧪 TESTING RAG RETRIEVER")
    logger.info("=" * 80)

    # Initialize clients
    try:
        chromadb = ChromaDBClient.initialize_from_env()
        embedding_client = EmbeddingClient()

        logger.info("✅ Clients initialized")

    except Exception as e:
        logger.error(f"❌ Failed to initialize: {e}")
        return

    # Create retriever
    retriever = RAGRetriever(chromadb, embedding_client)

    # Test with example intent
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Solo Budget Party Trip")
    logger.info("=" * 80)

    intent = example_stage5_user_intent()

    try:
        candidates = retriever.retrieve_for_itinerary(intent, top_k=15)

        logger.info(f"\n✅ Retrieved {len(candidates)} entities")

        # Show type distribution
        type_dist = Counter([c.entity_type for c in candidates])
        logger.info("\nType distribution:")
        for etype, count in type_dist.most_common():
            logger.info(f"   {etype}: {count}")

        # Show top 5
        logger.info("\nTop 5 entities:")
        for i, c in enumerate(candidates[:5], 1):
            logger.info(f"   {i}. {c.canonical_name} ({c.entity_type})")
            logger.info(f"      Relevance: {c.relevance_score:.2f}, Rating: {c.profile_rating:.1f}/5.0")

        # Calculate diversity
        diversity = retriever.calculate_diversity_score(candidates)
        logger.info(f"\nDiversity score: {diversity:.2f}")

    except Exception as e:
        logger.error(f"❌ Retrieval test failed: {e}")
        import traceback
        traceback.print_exc()

    logger.info("\n" + "=" * 80)
    logger.info("✅ RETRIEVER TESTING COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    test_retriever()
