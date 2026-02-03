"""
Stage 3 Semantic Embeddings: Tier 3 Matching with Local Embeddings

Implements semantic similarity matching using local sentence-transformers.
This is completely FREE - no API calls, runs locally on CPU.

Uses 'all-MiniLM-L6-v2' model:
- 384 dimensions
- Fast inference (~50ms per entity)
- Good quality for semantic matching
- Small size (~90MB)

Usage:
    from src.processors.embeddings import (
        generate_entity_embedding,
        calculate_semantic_similarity,
        find_semantic_candidates
    )

    # Generate embeddings
    embedding = generate_entity_embedding(entity)

    # Calculate similarity
    similarity = calculate_semantic_similarity(emb1, emb2)

    # Find semantic match candidates
    candidates = find_semantic_candidates(entities, threshold=0.85)
"""

from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import numpy as np
import pickle
import hashlib
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Global Model and Cache
# =============================================================================

# Lazy-loaded global model
_MODEL = None
_EMBEDDING_CACHE = {}


def get_model() -> SentenceTransformer:
    """
    Get or load the sentence-transformers model.

    Uses lazy loading to avoid loading model at import time.
    Model is cached globally for reuse.

    Returns:
        SentenceTransformer model instance
    """
    global _MODEL
    if _MODEL is None:
        logger.info("Loading sentence-transformers model: all-MiniLM-L6-v2")
        logger.info("This may take a few seconds on first run (downloads ~90MB)...")
        _MODEL = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Model loaded successfully (384 dimensions)")
    return _MODEL


# =============================================================================
# Entity Text Representation
# =============================================================================


def create_entity_text(entity: Dict[str, Any]) -> str:
    """
    Create a rich text representation of an entity for embedding.

    Combines multiple fields to capture semantic meaning:
    - Name and location (primary identifiers)
    - Entity type (category)
    - Key attributes from experience (extracted keywords)
    - Sentiment and cost signals

    Args:
        entity: Entity dict from stage3_loader

    Returns:
        Text representation for embedding

    Examples:
        >>> entity = {
        ...     'original_name': 'Khao San Road',
        ...     'original_location': 'Bangkok Old Town',
        ...     'entity': {
        ...         'entity_type': 'destination',
        ...         'experience': 'Famous backpacker street with bars, hostels...',
        ...         'sentiment': 'positive',
        ...         'cost_mentioned': 'budget'
        ...     }
        ... }
        >>> text = create_entity_text(entity)
        >>> print(text)
        'Khao San Road area in Bangkok Old Town destination nightlife budget party backpacker'
    """
    # Primary identifiers
    name = entity.get('original_name', '').strip()
    location = (entity.get('original_location') or '').strip()

    # Entity metadata
    entity_data = entity.get('entity', {})
    entity_type = entity_data.get('entity_type', '').strip()
    experience = entity_data.get('experience', '').strip()
    sentiment = entity_data.get('sentiment', '').strip()
    cost = (entity_data.get('cost_mentioned') or '').strip()

    # Build text components
    components = []

    # Name and location (most important)
    if name:
        components.append(name)
    if location:
        components.append(f"in {location}")

    # Entity type
    if entity_type:
        components.append(entity_type)

    # Extract keywords from experience (limit to avoid noise)
    if experience:
        keywords = extract_keywords(experience, max_keywords=10)
        components.extend(keywords)

    # Sentiment signal
    if sentiment and sentiment != 'neutral':
        components.append(sentiment)

    # Cost signal (simplified)
    if cost:
        cost_lower = cost.lower()
        if 'free' in cost_lower:
            components.append('free')
        elif 'cheap' in cost_lower or 'budget' in cost_lower:
            components.append('budget')
        elif 'expensive' in cost_lower or 'luxury' in cost_lower:
            components.append('expensive')

    # Join into single text
    text = ' '.join(components)

    return text


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """
    Extract meaningful keywords from experience description.

    Simple keyword extraction:
    - Remove common stop words
    - Keep words > 3 characters
    - Limit to max_keywords

    Args:
        text: Experience description
        max_keywords: Maximum keywords to extract

    Returns:
        List of keywords
    """
    # Common stop words to filter out
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may',
        'this', 'that', 'these', 'those', 'very', 'also', 'just', 'only',
        'there', 'here', 'when', 'where', 'why', 'how', 'all', 'each', 'every',
        'some', 'many', 'much', 'more', 'most', 'other', 'another', 'such'
    }

    # Tokenize and filter
    words = text.lower().split()
    keywords = []

    for word in words:
        # Remove punctuation
        word = ''.join(c for c in word if c.isalnum() or c == '-')

        # Filter stop words and short words
        if word and len(word) > 3 and word not in stop_words:
            keywords.append(word)

        if len(keywords) >= max_keywords:
            break

    return keywords


# =============================================================================
# Embedding Generation
# =============================================================================


def generate_entity_embedding(
    entity: Dict[str, Any],
    use_cache: bool = True
) -> np.ndarray:
    """
    Generate semantic embedding for an entity.

    Creates a rich text representation and embeds it using sentence-transformers.
    Embeddings are cached to avoid regeneration.

    Args:
        entity: Entity dict from stage3_loader
        use_cache: If True, use cached embeddings

    Returns:
        Embedding vector (384 dimensions for all-MiniLM-L6-v2)

    Example:
        >>> entity = {...}
        >>> embedding = generate_entity_embedding(entity)
        >>> embedding.shape
        (384,)
    """
    # Create cache key from entity
    cache_key = create_entity_cache_key(entity)

    # Check cache
    if use_cache and cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]

    # Create text representation
    text = create_entity_text(entity)

    # Generate embedding
    model = get_model()
    embedding = model.encode(text, convert_to_numpy=True)

    # Cache embedding
    if use_cache:
        _EMBEDDING_CACHE[cache_key] = embedding

    return embedding


def create_entity_cache_key(entity: Dict[str, Any]) -> str:
    """
    Create a unique cache key for an entity.

    Uses name + location + type as key.

    Args:
        entity: Entity dict

    Returns:
        Cache key string
    """
    name = entity.get('original_name', '')
    location = entity.get('original_location', '')
    entity_type = entity.get('entity', {}).get('entity_type', '')

    key_text = f"{name}||{location}||{entity_type}"
    return hashlib.md5(key_text.encode()).hexdigest()


# =============================================================================
# Similarity Calculation
# =============================================================================


def calculate_semantic_similarity(
    embedding1: np.ndarray,
    embedding2: np.ndarray
) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector

    Returns:
        Similarity score from 0.0 to 1.0

    Examples:
        >>> emb1 = generate_entity_embedding(entity1)
        >>> emb2 = generate_entity_embedding(entity2)
        >>> similarity = calculate_semantic_similarity(emb1, emb2)
        >>> print(f"Similarity: {similarity:.2f}")
    """
    # Reshape for sklearn (expects 2D arrays)
    emb1_2d = embedding1.reshape(1, -1)
    emb2_2d = embedding2.reshape(1, -1)

    # Calculate cosine similarity
    similarity = cosine_similarity(emb1_2d, emb2_2d)[0][0]

    # Ensure in range [0, 1] (cosine can be -1 to 1, but embeddings are usually positive)
    similarity = max(0.0, min(1.0, similarity))

    return float(similarity)


# =============================================================================
# Semantic Candidate Finding
# =============================================================================


def find_semantic_candidates(
    entities: List[Dict[str, Any]],
    threshold: float = 0.85,
    exclude_matched_pairs: Optional[List[Tuple[str, str]]] = None,
    show_progress: bool = True
) -> List[Tuple[Dict[str, Any], Dict[str, Any], float]]:
    """
    Find entity pairs with high semantic similarity.

    Generates embeddings for all entities and finds pairs above threshold.
    Only compares entities within same city and entity type.

    Args:
        entities: List of entity dicts from stage3_loader
        threshold: Minimum similarity score (0.0-1.0)
        exclude_matched_pairs: List of (name1, name2) pairs already matched
        show_progress: Show progress bar if True

    Returns:
        List of tuples: [(entity1, entity2, similarity_score), ...]
        Sorted by similarity score (highest first)

    Example:
        >>> entities = load_all_stage2_entities(s3)['all_entities']
        >>> candidates = find_semantic_candidates(entities, threshold=0.85)
        >>> print(f"Found {len(candidates)} semantic match candidates")
        >>> for e1, e2, score in candidates[:5]:
        ...     print(f"{e1['original_name']} ~ {e2['original_name']}: {score:.2f}")
    """
    logger.info(f"Finding semantic match candidates (threshold={threshold:.2f})...")
    logger.info("This may take a few minutes on first run (generates embeddings)...")

    # Step 1: Group entities by (location, type) for efficient comparison
    location_type_groups = defaultdict(list)

    for entity in entities:
        location = entity.get('normalized_location', '').strip().lower() if entity.get('normalized_location') else ''
        entity_type = entity.get('entity', {}).get('entity_type', '').strip().lower()

        key = f"{location}||{entity_type}"
        location_type_groups[key].append(entity)

    logger.info(f"   Grouped into {len(location_type_groups)} location-type combinations")

    # Step 2: Create set of excluded pairs
    excluded_pairs = set()
    if exclude_matched_pairs:
        for name1, name2 in exclude_matched_pairs:
            # Normalize names
            n1 = name1.lower().strip()
            n2 = name2.lower().strip()
            # Add both orderings
            excluded_pairs.add((n1, n2))
            excluded_pairs.add((n2, n1))

    # Step 3: Generate embeddings for all entities
    logger.info(f"Generating embeddings for {len(entities)} entities...")

    entity_embeddings = {}
    batch_size = 100

    # Progress tracking
    if show_progress:
        try:
            from tqdm import tqdm
            entity_iterator = tqdm(entities, desc="Generating embeddings", unit="entity")
        except ImportError:
            entity_iterator = entities
    else:
        entity_iterator = entities

    for entity in entity_iterator:
        entity_id = id(entity)  # Use object id as key
        entity_embeddings[entity_id] = generate_entity_embedding(entity)

    logger.info(f"   Generated {len(entity_embeddings)} embeddings")

    # Step 4: Compare entities within each group
    logger.info("Comparing entities for semantic similarity...")

    semantic_candidates = []
    total_comparisons = 0

    for key, group_entities in location_type_groups.items():
        if len(group_entities) < 2:
            continue  # No pairs to compare

        # Compare all pairs within this group
        for i in range(len(group_entities)):
            for j in range(i + 1, len(group_entities)):
                entity1 = group_entities[i]
                entity2 = group_entities[j]

                total_comparisons += 1

                # Check if pair is excluded
                name1 = entity1.get('normalized_name', '').lower().strip()
                name2 = entity2.get('normalized_name', '').lower().strip()

                if (name1, name2) in excluded_pairs or (name2, name1) in excluded_pairs:
                    continue

                # Get embeddings
                emb1 = entity_embeddings[id(entity1)]
                emb2 = entity_embeddings[id(entity2)]

                # Calculate similarity
                similarity = calculate_semantic_similarity(emb1, emb2)

                if similarity >= threshold:
                    semantic_candidates.append((entity1, entity2, similarity))

    # Sort by similarity (highest first)
    semantic_candidates.sort(key=lambda x: x[2], reverse=True)

    # Log statistics
    logger.info("✅ Semantic matching complete:")
    logger.info(f"   Total comparisons: {total_comparisons:,}")
    logger.info(f"   Semantic candidates found: {len(semantic_candidates)}")
    logger.info(f"   Threshold: {threshold:.2f}")
    logger.info(f"   Embeddings cached: {len(_EMBEDDING_CACHE)}")

    # Log examples
    if semantic_candidates:
        logger.info("")
        logger.info("Top 10 semantic match candidates:")
        for i, (e1, e2, score) in enumerate(semantic_candidates[:10], 1):
            name1 = e1.get('original_name', 'Unknown')
            name2 = e2.get('original_name', 'Unknown')
            location = e1.get('original_location') or 'Unknown'
            entity_type = e1.get('entity', {}).get('entity_type', 'unknown')

            logger.info(
                f"   {i}. [{entity_type}] {name1} ~ {name2} "
                f"({location}) - {score:.3f}"
            )
    else:
        logger.info("   No semantic candidates found above threshold")

    return semantic_candidates


# =============================================================================
# Cache Management
# =============================================================================


def save_embedding_cache(cache_path: str) -> None:
    """
    Save embedding cache to disk.

    Args:
        cache_path: Path to save cache file
    """
    cache_file = Path(cache_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    with open(cache_file, 'wb') as f:
        pickle.dump(_EMBEDDING_CACHE, f)

    logger.info(f"Saved {len(_EMBEDDING_CACHE)} embeddings to {cache_path}")


def load_embedding_cache(cache_path: str) -> None:
    """
    Load embedding cache from disk.

    Args:
        cache_path: Path to cache file
    """
    global _EMBEDDING_CACHE

    cache_file = Path(cache_path)

    if not cache_file.exists():
        logger.warning(f"Cache file not found: {cache_path}")
        return

    with open(cache_file, 'rb') as f:
        _EMBEDDING_CACHE = pickle.load(f)

    logger.info(f"Loaded {len(_EMBEDDING_CACHE)} embeddings from {cache_path}")


def clear_embedding_cache() -> None:
    """Clear the embedding cache."""
    global _EMBEDDING_CACHE
    _EMBEDDING_CACHE = {}
    logger.info("Embedding cache cleared")


# =============================================================================
# Testing and Validation
# =============================================================================


def test_embeddings_sample():
    """
    Test embeddings with sample entities.

    Tests semantic similarity matching with known similar/dissimilar pairs.
    """
    logger.info("Testing semantic embeddings with sample entities...")

    # Create sample entities
    sample_entities = [
        {
            'original_name': 'Khao San Road',
            'original_location': 'Bangkok',
            'normalized_name': 'khao san road',
            'normalized_location': 'bangkok',
            'entity': {
                'entity_type': 'destination',
                'experience': 'Famous backpacker street with bars, hostels, and nightlife. Very cheap and lively atmosphere.',
                'sentiment': 'positive',
                'cost_mentioned': 'budget'
            }
        },
        {
            'original_name': 'The backpacker street in Bangkok Old Town',
            'original_location': 'Bangkok',
            'normalized_name': 'the backpacker street in bangkok old town',
            'normalized_location': 'bangkok',
            'entity': {
                'entity_type': 'destination',
                'experience': 'Popular area for budget travelers with hostels, street food, and party scene.',
                'sentiment': 'positive',
                'cost_mentioned': 'cheap'
            }
        },
        {
            'original_name': 'Railay Beach',
            'original_location': 'Krabi',
            'normalized_name': 'railay beach',
            'normalized_location': 'krabi',
            'entity': {
                'entity_type': 'destination',
                'experience': 'Stunning beach accessible only by boat. Great for rock climbing and relaxation.',
                'sentiment': 'positive',
                'cost_mentioned': None
            }
        },
        {
            'original_name': 'Patong Beach',
            'original_location': 'Phuket',
            'normalized_name': 'patong beach',
            'normalized_location': 'phuket',
            'entity': {
                'entity_type': 'destination',
                'experience': 'Main tourist beach in Phuket with lots of hotels, restaurants, and nightlife.',
                'sentiment': 'positive',
                'cost_mentioned': None
            }
        },
    ]

    # Test 1: Entity text generation
    logger.info("\nTest 1: Entity text generation")
    for entity in sample_entities[:2]:
        text = create_entity_text(entity)
        name = entity['original_name']
        logger.info(f"  {name}: {text}")

    # Test 2: Embedding generation
    logger.info("\nTest 2: Embedding generation")
    embeddings = []
    for entity in sample_entities:
        emb = generate_entity_embedding(entity)
        embeddings.append(emb)
        name = entity['original_name']
        logger.info(f"  {name}: shape={emb.shape}, norm={np.linalg.norm(emb):.2f}")

    # Test 3: Semantic similarity
    logger.info("\nTest 3: Semantic similarity")

    # Similar pair (should be high similarity)
    sim_khao_san_backpacker = calculate_semantic_similarity(embeddings[0], embeddings[1])
    logger.info(f"  'Khao San Road' vs 'backpacker street': {sim_khao_san_backpacker:.3f} (expect HIGH)")

    # Dissimilar pair (should be low similarity)
    sim_railay_patong = calculate_semantic_similarity(embeddings[2], embeddings[3])
    logger.info(f"  'Railay Beach' vs 'Patong Beach': {sim_railay_patong:.3f} (expect LOW)")

    # Different entities, same type
    sim_khao_san_railay = calculate_semantic_similarity(embeddings[0], embeddings[2])
    logger.info(f"  'Khao San Road' vs 'Railay Beach': {sim_khao_san_railay:.3f} (expect MEDIUM)")

    # Test 4: Find semantic candidates
    logger.info("\nTest 4: Finding semantic candidates")
    candidates = find_semantic_candidates(sample_entities, threshold=0.75, show_progress=False)

    logger.info(f"Found {len(candidates)} candidates with threshold=0.75:")
    for e1, e2, score in candidates:
        logger.info(f"  {e1['original_name']} ~ {e2['original_name']}: {score:.3f}")

    logger.info("\n✅ Embeddings test complete!")

    # Return results for verification
    return {
        'khao_san_vs_backpacker': sim_khao_san_backpacker,
        'railay_vs_patong': sim_railay_patong,
        'candidates': candidates
    }


if __name__ == '__main__':
    # Run tests
    test_embeddings_sample()
