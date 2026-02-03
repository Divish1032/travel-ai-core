#!/usr/bin/env python3
"""
Vibe Extractor for Multi-Dimensional Intent Matching

Extracts 12-dimensional vibe vectors from entities and queries to enable
nuanced intent matching beyond simple 2D profiles (solo/family, budget/luxury).

12 Vibe Dimensions:
1. Adventure (0-1): Hiking, extreme sports, outdoor activities
2. Relaxation (0-1): Spas, beaches, slow pace
3. Culture (0-1): Museums, temples, history, art
4. Nightlife (0-1): Bars, clubs, entertainment
5. Nature (0-1): Parks, wildlife, natural beauty
6. Food (0-1): Culinary experiences, markets, restaurants
7. Shopping (0-1): Markets, malls, local crafts
8. Luxury (0-1): High-end experiences, premium services
9. Budget (0-1): Cost-conscious, free activities
10. Social (0-1): Group activities, meeting people
11. Solo (0-1): Solo-friendly, introspective
12. Family (0-1): Kid-friendly, family activities

Features:
- Entity type → vibe mapping (rule-based)
- Experience description → vibe extraction (LLM-powered)
- Query → vibe extraction (LLM-powered)
- Vibe normalization and validation
- Cosine similarity for vibe matching

Example:
    >>> from src.rag.vibe_extractor import VibeExtractor
    >>> extractor = VibeExtractor()
    >>>
    >>> # Extract from entity
    >>> entity = load_entity("nightclub_bangkok_001")
    >>> vibes = extractor.extract_entity_vibes(entity)
    >>> vibes['nightlife']
    0.95
    >>>
    >>> # Extract from query
    >>> query = "5 days Bangkok party and food budget"
    >>> query_vibes = extractor.extract_query_vibes(query)
    >>> query_vibes
    {'nightlife': 0.8, 'food': 0.9, 'budget': 0.9, ...}
"""

import json
from typing import Dict, Any, List
import re

from src.utils.logging import get_logger
from src.utils.llm_client import LLMClient

logger = get_logger(__name__)


class VibeExtractor:
    """
    Extracts 12-dimensional vibe vectors from entities and queries.

    Combines rule-based extraction (entity types, attributes) with
    LLM-powered extraction (experiences, query text) for comprehensive
    vibe representation.
    """

    # 12 vibe dimensions
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

    # Entity type → vibe mappings (rule-based)
    ENTITY_TYPE_VIBES = {
        'attraction': {
            'culture': 0.7,
            'nature': 0.3
        },
        'restaurant': {
            'food': 1.0,
            'social': 0.4
        },
        'hotel': {
            'relaxation': 0.5
        },
        'activity': {
            'adventure': 0.6,
            'social': 0.5
        },
        'shopping': {
            'shopping': 1.0,
            'culture': 0.2
        },
        'transportation': {
            'budget': 0.3
        }
    }

    # Keywords → vibe mappings (for experience text)
    VIBE_KEYWORDS = {
        'adventure': [
            'hiking', 'trekking', 'climb', 'extreme', 'adventure', 'thrill',
            'zipline', 'diving', 'snorkel', 'surf', 'kayak', 'rafting',
            'mountain', 'trek', 'explore', 'wild', 'adrenaline'
        ],
        'relaxation': [
            'relax', 'spa', 'massage', 'beach', 'chill', 'peaceful', 'calm',
            'tranquil', 'serene', 'quiet', 'laid-back', 'zen', 'unwind',
            'lounge', 'slow', 'gentle'
        ],
        'culture': [
            'temple', 'museum', 'palace', 'historic', 'cultural', 'art',
            'gallery', 'architecture', 'traditional', 'heritage', 'ancient',
            'monument', 'cultural', 'religious', 'spiritual', 'shrine'
        ],
        'nightlife': [
            'nightlife', 'party', 'club', 'bar', 'pub', 'night', 'dance',
            'dj', 'music', 'entertainment', 'live music', 'rooftop bar',
            'cocktail', 'disco', 'nightclub', 'late night'
        ],
        'nature': [
            'nature', 'park', 'garden', 'forest', 'jungle', 'wildlife',
            'bird', 'animal', 'eco', 'green', 'tree', 'waterfall',
            'scenic', 'natural', 'outdoors', 'landscape'
        ],
        'food': [
            'food', 'restaurant', 'street food', 'market', 'cuisine',
            'delicious', 'tasty', 'eat', 'dining', 'chef', 'dish',
            'local food', 'foodie', 'culinary', 'flavor', 'meal'
        ],
        'shopping': [
            'shopping', 'market', 'mall', 'shop', 'store', 'boutique',
            'souvenir', 'craft', 'buy', 'bargain', 'vendor', 'retail',
            'market', 'bazaar', 'goods'
        ],
        'luxury': [
            'luxury', 'premium', 'high-end', 'exclusive', 'upscale',
            'five-star', 'elegant', 'sophisticated', 'lavish', 'posh',
            'deluxe', 'VIP', 'expensive', 'finest'
        ],
        'budget': [
            'budget', 'cheap', 'affordable', 'free', 'inexpensive',
            'value', 'economical', 'backpack', 'low-cost', 'bargain',
            'wallet-friendly', 'cost-effective'
        ],
        'social': [
            'social', 'group', 'meet', 'people', 'friendly', 'fun',
            'lively', 'bustling', 'crowded', 'popular', 'vibrant',
            'energetic', 'atmosphere', 'interactive'
        ],
        'solo': [
            'solo', 'alone', 'independent', 'self', 'individual',
            'peaceful', 'quiet', 'introspective', 'meditative',
            'personal', 'private'
        ],
        'family': [
            'family', 'kid', 'children', 'child-friendly', 'kids',
            'toddler', 'baby', 'playground', 'educational',
            'safe', 'wholesome', 'all-ages'
        ]
    }

    def __init__(self, use_llm: bool = False):
        """
        Initialize vibe extractor.

        Args:
            use_llm: Whether to use LLM for experience vibe extraction (default: False)
                     If False, uses keyword-based extraction only
        """
        self.use_llm = use_llm
        self.llm_client = LLMClient() if use_llm else None

    def extract_entity_vibes(
        self,
        entity: Dict[str, Any],
        use_experiences: bool = True
    ) -> Dict[str, float]:
        """
        Extract 12D vibe vector from entity.

        Combines:
        1. Entity type vibes (rule-based)
        2. Attribute vibes (price → luxury/budget)
        3. Experience vibes (keyword-based or LLM)

        Args:
            entity: Canonical entity dict
            use_experiences: Whether to analyze experiences (default: True)

        Returns:
            Dict with 12 vibe dimensions (0-1 scale)

        Example:
            >>> vibes = extractor.extract_entity_vibes(entity)
            >>> vibes
            {'adventure': 0.2, 'relaxation': 0.1, 'culture': 0.7, ...}
        """
        # Initialize vibes to 0
        vibes = {dim: 0.0 for dim in self.VIBE_DIMENSIONS}

        # 1. Entity type vibes
        entity_type = entity.get('entity_type', 'unknown')
        type_vibes = self.ENTITY_TYPE_VIBES.get(entity_type, {})
        for vibe, score in type_vibes.items():
            vibes[vibe] = max(vibes[vibe], score)

        # 2. Attribute vibes
        attribute_vibes = self._extract_attribute_vibes(entity)
        for vibe, score in attribute_vibes.items():
            vibes[vibe] = max(vibes[vibe], score)

        # 3. Experience vibes (if enabled)
        if use_experiences:
            experience_vibes = self._extract_experience_vibes(entity)
            # Average with existing vibes (weighted: 40% type, 60% experiences)
            for vibe, exp_score in experience_vibes.items():
                if exp_score > 0:
                    vibes[vibe] = 0.4 * vibes[vibe] + 0.6 * exp_score

        # Normalize to ensure [0, 1] range
        vibes = self._normalize_vibes(vibes)

        return vibes

    def extract_query_vibes(
        self,
        query: str,
        use_llm: bool = None
    ) -> Dict[str, float]:
        """
        Extract 12D vibe vector from natural language query.

        Uses keyword matching or LLM to identify user intent across
        12 vibe dimensions.

        Args:
            query: Natural language query (e.g., "5 days Bangkok party and food")
            use_llm: Override instance use_llm setting

        Returns:
            Dict with 12 vibe dimensions (0-1 scale)

        Example:
            >>> vibes = extractor.extract_query_vibes("beach relaxation luxury")
            >>> vibes
            {'relaxation': 0.9, 'luxury': 0.8, 'nature': 0.6, ...}
        """
        use_llm = use_llm if use_llm is not None else self.use_llm

        if use_llm and self.llm_client:
            return self._extract_query_vibes_llm(query)
        else:
            return self._extract_query_vibes_keywords(query)

    def _extract_attribute_vibes(
        self,
        entity: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Extract vibes from entity attributes.

        Focuses on:
        - Price level → luxury/budget vibes
        - Attributes → specific vibes

        Args:
            entity: Canonical entity dict

        Returns:
            Dict with vibe scores
        """
        vibes = {}
        attributes = entity.get('attributes', {})

        # Price level → luxury/budget
        price_level = attributes.get('price_level', '')
        if price_level:
            if price_level in ['$', '$$']:
                vibes['budget'] = 0.8
                vibes['luxury'] = 0.1
            elif price_level == '$$$':
                vibes['budget'] = 0.3
                vibes['luxury'] = 0.5
            elif price_level == '$$$$':
                vibes['budget'] = 0.1
                vibes['luxury'] = 0.9

        return vibes

    def _extract_experience_vibes(
        self,
        entity: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Extract vibes from entity experiences using keyword matching.

        Analyzes experience descriptions for vibe keywords.

        Args:
            entity: Canonical entity dict

        Returns:
            Dict with vibe scores
        """
        experiences = entity.get('experiences', [])
        if not experiences:
            return {}

        # Collect all experience texts
        texts = []
        for exp in experiences:
            description = exp.get('description', '')
            highlights = exp.get('highlights', [])
            texts.append(description)
            texts.extend(highlights)

        # Combine into single text
        combined_text = ' '.join(texts).lower()

        # Count keyword matches for each vibe
        vibe_scores = {}
        for vibe, keywords in self.VIBE_KEYWORDS.items():
            matches = sum(1 for keyword in keywords if keyword in combined_text)
            # Normalize by number of keywords (max score = 1.0 if all keywords present)
            score = min(1.0, matches / max(1, len(keywords) * 0.3))
            vibe_scores[vibe] = score

        return vibe_scores

    def _extract_query_vibes_keywords(
        self,
        query: str
    ) -> Dict[str, float]:
        """
        Extract vibes from query using keyword matching.

        Args:
            query: Natural language query

        Returns:
            Dict with 12 vibe dimensions
        """
        query_lower = query.lower()

        vibes = {}
        for vibe, keywords in self.VIBE_KEYWORDS.items():
            matches = sum(1 for keyword in keywords if keyword in query_lower)
            # Boost score if multiple keywords match
            score = min(1.0, matches / max(1, len(keywords) * 0.2))
            vibes[vibe] = score

        # Normalize
        vibes = self._normalize_vibes(vibes)

        return vibes

    def _extract_query_vibes_llm(
        self,
        query: str
    ) -> Dict[str, float]:
        """
        Extract vibes from query using LLM.

        Uses structured output to get vibe scores directly from LLM.

        Args:
            query: Natural language query

        Returns:
            Dict with 12 vibe dimensions
        """
        prompt = f"""Analyze the following travel query and extract intent across 12 vibe dimensions.
Rate each dimension from 0.0 (not relevant) to 1.0 (highly relevant).

Query: "{query}"

Vibe Dimensions:
1. Adventure: Hiking, extreme sports, outdoor activities
2. Relaxation: Spas, beaches, slow pace
3. Culture: Museums, temples, history, art
4. Nightlife: Bars, clubs, entertainment
5. Nature: Parks, wildlife, natural beauty
6. Food: Culinary experiences, markets, restaurants
7. Shopping: Markets, malls, local crafts
8. Luxury: High-end experiences, premium services
9. Budget: Cost-conscious, free activities
10. Social: Group activities, meeting people
11. Solo: Solo-friendly, introspective
12. Family: Kid-friendly, family activities

Return ONLY a JSON object with scores:
{{
    "adventure": 0.0,
    "relaxation": 0.0,
    "culture": 0.0,
    "nightlife": 0.0,
    "nature": 0.0,
    "food": 0.0,
    "shopping": 0.0,
    "luxury": 0.0,
    "budget": 0.0,
    "social": 0.0,
    "solo": 0.0,
    "family": 0.0
}}"""

        try:
            response = self.llm_client.generate(prompt, max_tokens=500)
            # Parse JSON from response
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                vibes = json.loads(json_match.group(0))
                # Validate and normalize
                vibes = self._normalize_vibes(vibes)
                return vibes
            else:
                logger.warning("LLM response did not contain valid JSON, falling back to keywords")
                return self._extract_query_vibes_keywords(query)

        except Exception as e:
            logger.error(f"LLM vibe extraction failed: {e}, falling back to keywords")
            return self._extract_query_vibes_keywords(query)

    def _normalize_vibes(
        self,
        vibes: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Normalize vibe scores to [0, 1] range.

        Ensures all dimensions are present and within valid range.

        Args:
            vibes: Raw vibe scores

        Returns:
            Normalized vibe scores
        """
        normalized = {}

        for dim in self.VIBE_DIMENSIONS:
            score = vibes.get(dim, 0.0)
            # Clamp to [0, 1]
            normalized[dim] = max(0.0, min(1.0, float(score)))

        return normalized

    def vibes_to_vector(
        self,
        vibes: Dict[str, float]
    ) -> List[float]:
        """
        Convert vibe dict to ordered vector.

        Args:
            vibes: Dict with vibe dimensions

        Returns:
            List of 12 floats in canonical order

        Example:
            >>> vec = extractor.vibes_to_vector(vibes)
            >>> len(vec)
            12
        """
        return [vibes.get(dim, 0.0) for dim in self.VIBE_DIMENSIONS]

    def vector_to_vibes(
        self,
        vector: List[float]
    ) -> Dict[str, float]:
        """
        Convert ordered vector to vibe dict.

        Args:
            vector: List of 12 floats

        Returns:
            Dict with vibe dimension names

        Example:
            >>> vibes = extractor.vector_to_vibes([0.5, 0.3, ...])
            >>> vibes['adventure']
            0.5
        """
        if len(vector) != 12:
            logger.warning(f"Expected 12 dimensions, got {len(vector)}")
            # Pad or truncate
            vector = (vector + [0.0] * 12)[:12]

        return {
            dim: float(vector[i])
            for i, dim in enumerate(self.VIBE_DIMENSIONS)
        }
