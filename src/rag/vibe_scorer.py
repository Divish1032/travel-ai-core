#!/usr/bin/env python3
"""
Vibe Scorer for Intent Similarity Matching

Computes similarity scores between query vibes and entity vibes using
cosine similarity and weighted scoring strategies.

Features:
- Cosine similarity for vibe vectors
- Weighted vibe matching (configurable weights per dimension)
- Batch scoring for efficiency
- Normalization and ranking utilities

Example:
    >>> from src.rag.vibe_scorer import VibeScorer
    >>> from src.rag.vibe_extractor import VibeExtractor
    >>>
    >>> extractor = VibeExtractor()
    >>> scorer = VibeScorer()
    >>>
    >>> # Extract vibes
    >>> query_vibes = extractor.extract_query_vibes("beach party luxury")
    >>> entity_vibes = extractor.extract_entity_vibes(entity)
    >>>
    >>> # Compute similarity
    >>> score = scorer.compute_similarity(query_vibes, entity_vibes)
    >>> score
    0.87
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ScoredEntity:
    """Entity with vibe similarity score."""
    entity_id: str
    vibe_score: float
    query_vibes: Dict[str, float]
    entity_vibes: Dict[str, float]
    vibe_breakdown: Dict[str, float]  # Per-dimension contribution


class VibeScorer:
    """
    Computes vibe similarity scores for ranking and reranking.

    Uses cosine similarity between 12D vibe vectors with optional
    dimension weighting.
    """

    # Standard dimension order (must match VibeExtractor.VIBE_DIMENSIONS)
    VIBE_DIMENSIONS = [
        'adventure',
        'relaxation',
        'culture',
        'nightlife',
        'nature',
        'food',
        'shopping',
        'luxury',
        'budget',
        'social',
        'solo',
        'family'
    ]

    def __init__(self, dimension_weights: Optional[Dict[str, float]] = None):
        """
        Initialize vibe scorer.

        Args:
            dimension_weights: Optional weights per dimension (default: equal weights)
                               Useful for emphasizing certain vibes (e.g., 2x weight on 'food')

        Example:
            >>> # Emphasize nightlife and food
            >>> scorer = VibeScorer(dimension_weights={
            ...     'nightlife': 2.0,
            ...     'food': 2.0
            ... })
        """
        self.dimension_weights = dimension_weights or {dim: 1.0 for dim in self.VIBE_DIMENSIONS}

    def compute_similarity(
        self,
        query_vibes: Dict[str, float],
        entity_vibes: Dict[str, float],
        method: str = 'cosine'
    ) -> float:
        """
        Compute similarity between query and entity vibes.

        Args:
            query_vibes: Query vibe vector (12D dict)
            entity_vibes: Entity vibe vector (12D dict)
            method: Similarity method ('cosine', 'dot', 'weighted')

        Returns:
            Similarity score (0-1, higher = more similar)

        Example:
            >>> score = scorer.compute_similarity(query_vibes, entity_vibes)
            >>> score
            0.87
        """
        if method == 'cosine':
            return self._cosine_similarity(query_vibes, entity_vibes)
        elif method == 'dot':
            return self._dot_product(query_vibes, entity_vibes)
        elif method == 'weighted':
            return self._weighted_similarity(query_vibes, entity_vibes)
        else:
            logger.warning(f"Unknown method '{method}', using cosine")
            return self._cosine_similarity(query_vibes, entity_vibes)

    def compute_batch_similarity(
        self,
        query_vibes: Dict[str, float],
        entities_vibes: List[Dict[str, float]],
        method: str = 'cosine'
    ) -> List[float]:
        """
        Compute similarity for batch of entities (optimized).

        Args:
            query_vibes: Query vibe vector
            entities_vibes: List of entity vibe vectors
            method: Similarity method

        Returns:
            List of similarity scores

        Example:
            >>> scores = scorer.compute_batch_similarity(query_vibes, [e1_vibes, e2_vibes])
            >>> scores
            [0.87, 0.65]
        """
        # Convert to numpy for vectorized operations
        query_vec = self._vibes_to_array(query_vibes)

        scores = []
        for entity_vibes in entities_vibes:
            entity_vec = self._vibes_to_array(entity_vibes)

            if method == 'cosine':
                score = self._cosine_similarity_numpy(query_vec, entity_vec)
            elif method == 'dot':
                score = self._dot_product_numpy(query_vec, entity_vec)
            elif method == 'weighted':
                score = self._weighted_similarity_numpy(query_vec, entity_vec)
            else:
                score = self._cosine_similarity_numpy(query_vec, entity_vec)

            scores.append(float(score))

        return scores

    def rank_entities(
        self,
        query_vibes: Dict[str, float],
        entities: List[Dict[str, Any]],
        vibe_key: str = 'vibes',
        top_k: Optional[int] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Rank entities by vibe similarity to query.

        Args:
            query_vibes: Query vibe vector
            entities: List of entity dicts (must have vibe_key field)
            vibe_key: Key in entity dict containing vibes (default: 'vibes')
            top_k: Return only top K entities (default: all)

        Returns:
            List of (entity_id, score, entity) tuples, sorted by score (descending)

        Example:
            >>> ranked = scorer.rank_entities(query_vibes, entities, top_k=10)
            >>> ranked[0]
            ('entity_123', 0.92, {...})
        """
        scored_entities = []

        for entity in entities:
            entity_id = entity.get('entity_id', 'unknown')
            entity_vibes = entity.get(vibe_key, {})

            if not entity_vibes:
                logger.debug(f"Entity {entity_id} has no vibes, skipping")
                continue

            score = self.compute_similarity(query_vibes, entity_vibes)
            scored_entities.append((entity_id, score, entity))

        # Sort by score (descending)
        scored_entities.sort(key=lambda x: x[1], reverse=True)

        # Return top K if specified
        if top_k:
            return scored_entities[:top_k]

        return scored_entities

    def rerank_with_vibes(
        self,
        query_vibes: Dict[str, float],
        entities: List[Dict[str, Any]],
        base_scores: Optional[List[float]] = None,
        vibe_weight: float = 0.4,
        vibe_key: str = 'vibes'
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Rerank entities by combining base scores with vibe scores.

        Useful for reranking semantic search results with vibe matching.

        Args:
            query_vibes: Query vibe vector
            entities: List of entity dicts
            base_scores: Optional base scores (e.g., from semantic search)
                         If None, uses only vibe scores
            vibe_weight: Weight for vibe score (default: 0.4)
                         Final score = (1-vibe_weight)*base + vibe_weight*vibe
            vibe_key: Key in entity dict containing vibes

        Returns:
            List of (entity_id, combined_score, entity) tuples, sorted descending

        Example:
            >>> # Rerank semantic search results with vibes
            >>> reranked = scorer.rerank_with_vibes(
            ...     query_vibes,
            ...     semantic_results,
            ...     base_scores=semantic_scores,
            ...     vibe_weight=0.4
            ... )
        """
        reranked = []

        for i, entity in enumerate(entities):
            entity_id = entity.get('entity_id', 'unknown')
            entity_vibes = entity.get(vibe_key, {})

            # Compute vibe score
            vibe_score = self.compute_similarity(query_vibes, entity_vibes) if entity_vibes else 0.0

            # Combine with base score if provided
            if base_scores and i < len(base_scores):
                base_score = base_scores[i]
                combined_score = (1 - vibe_weight) * base_score + vibe_weight * vibe_score
            else:
                combined_score = vibe_score

            reranked.append((entity_id, combined_score, entity))

        # Sort by combined score (descending)
        reranked.sort(key=lambda x: x[1], reverse=True)

        return reranked

    def explain_vibe_match(
        self,
        query_vibes: Dict[str, float],
        entity_vibes: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Explain vibe matching with per-dimension breakdown.

        Args:
            query_vibes: Query vibe vector
            entity_vibes: Entity vibe vector

        Returns:
            Dict with overall score and per-dimension contributions

        Example:
            >>> explanation = scorer.explain_vibe_match(query_vibes, entity_vibes)
            >>> explanation
            {
                'overall_score': 0.87,
                'dimension_scores': {
                    'nightlife': {'query': 0.9, 'entity': 0.95, 'contribution': 0.15},
                    'food': {'query': 0.8, 'entity': 0.7, 'contribution': 0.12},
                    ...
                },
                'top_matches': ['nightlife', 'food', 'social'],
                'mismatches': ['relaxation', 'solo']
            }
        """
        overall_score = self.compute_similarity(query_vibes, entity_vibes)

        dimension_scores = {}
        contributions = []

        for dim in self.VIBE_DIMENSIONS:
            q_val = query_vibes.get(dim, 0.0)
            e_val = entity_vibes.get(dim, 0.0)

            # Contribution = product of query and entity scores (high both = high contribution)
            contribution = q_val * e_val

            dimension_scores[dim] = {
                'query': q_val,
                'entity': e_val,
                'contribution': contribution
            }

            contributions.append((dim, contribution))

        # Sort by contribution
        contributions.sort(key=lambda x: x[1], reverse=True)

        # Top matches (high contribution)
        top_matches = [dim for dim, contrib in contributions[:3] if contrib > 0.1]

        # Mismatches (high query, low entity or vice versa)
        mismatches = []
        for dim in self.VIBE_DIMENSIONS:
            q_val = query_vibes.get(dim, 0.0)
            e_val = entity_vibes.get(dim, 0.0)
            if abs(q_val - e_val) > 0.5 and max(q_val, e_val) > 0.5:
                mismatches.append(dim)

        return {
            'overall_score': overall_score,
            'dimension_scores': dimension_scores,
            'top_matches': top_matches,
            'mismatches': mismatches
        }

    # ========================================================================
    # INTERNAL METHODS
    # ========================================================================

    def _cosine_similarity(
        self,
        query_vibes: Dict[str, float],
        entity_vibes: Dict[str, float]
    ) -> float:
        """Cosine similarity between two vibe vectors."""
        query_vec = self._vibes_to_array(query_vibes)
        entity_vec = self._vibes_to_array(entity_vibes)

        return self._cosine_similarity_numpy(query_vec, entity_vec)

    def _cosine_similarity_numpy(
        self,
        query_vec: np.ndarray,
        entity_vec: np.ndarray
    ) -> float:
        """Cosine similarity using numpy."""
        # Cosine similarity = dot(A, B) / (||A|| * ||B||)
        dot = np.dot(query_vec, entity_vec)
        norm_q = np.linalg.norm(query_vec)
        norm_e = np.linalg.norm(entity_vec)

        if norm_q == 0 or norm_e == 0:
            return 0.0

        return dot / (norm_q * norm_e)

    def _dot_product(
        self,
        query_vibes: Dict[str, float],
        entity_vibes: Dict[str, float]
    ) -> float:
        """Dot product (not normalized)."""
        query_vec = self._vibes_to_array(query_vibes)
        entity_vec = self._vibes_to_array(entity_vibes)

        return self._dot_product_numpy(query_vec, entity_vec)

    def _dot_product_numpy(
        self,
        query_vec: np.ndarray,
        entity_vec: np.ndarray
    ) -> float:
        """Dot product using numpy."""
        return float(np.dot(query_vec, entity_vec))

    def _weighted_similarity(
        self,
        query_vibes: Dict[str, float],
        entity_vibes: Dict[str, float]
    ) -> float:
        """Weighted cosine similarity with dimension weights."""
        query_vec = self._vibes_to_array(query_vibes)
        entity_vec = self._vibes_to_array(entity_vibes)

        return self._weighted_similarity_numpy(query_vec, entity_vec)

    def _weighted_similarity_numpy(
        self,
        query_vec: np.ndarray,
        entity_vec: np.ndarray
    ) -> float:
        """Weighted similarity using numpy."""
        # Apply weights
        weights = np.array([self.dimension_weights.get(dim, 1.0) for dim in self.VIBE_DIMENSIONS])

        query_weighted = query_vec * weights
        entity_weighted = entity_vec * weights

        # Cosine similarity on weighted vectors
        dot = np.dot(query_weighted, entity_weighted)
        norm_q = np.linalg.norm(query_weighted)
        norm_e = np.linalg.norm(entity_weighted)

        if norm_q == 0 or norm_e == 0:
            return 0.0

        return dot / (norm_q * norm_e)

    def _vibes_to_array(
        self,
        vibes: Dict[str, float]
    ) -> np.ndarray:
        """Convert vibe dict to numpy array in canonical order."""
        return np.array([vibes.get(dim, 0.0) for dim in self.VIBE_DIMENSIONS], dtype=np.float32)
