#!/usr/bin/env python3
"""
GTE-Large Embedding Client for Stage 4

Handles text embedding generation using Alibaba's gte-large-en-v1.5 model.
Implements batching, caching, and progress tracking.

Features:
- Batch embedding (GPU accelerated if available)
- Local caching for performance
- Progress bars for large batches
- FREE (no API costs)
- Better quality than OpenAI text-embedding-3-small

Model: Alibaba-NLP/gte-large-en-v1.5
- Dimensions: 1024
- Cost: FREE (runs locally)
- Better performance than OpenAI's model
- Source: https://huggingface.co/Alibaba-NLP/gte-large-en-v1.5

Example:
    >>> client = EmbeddingClient()
    >>> vector = client.embed_text("romantic beach restaurant in Phuket")
    >>> len(vector)
    1024
    >>> vectors = client.embed_batch(["text1", "text2", "text3"])
    >>> len(vectors)
    3
"""

import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from sentence_transformers import SentenceTransformer

from src.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingClient:
    """
    Client for generating gte-large embeddings with caching.

    Attributes:
        model: SentenceTransformer model instance
        dimensions: Vector dimensions (1024)
        cache: In-memory embedding cache
        cache_file: Path to cache file
    """

    # Model configuration
    MODEL = "Alibaba-NLP/gte-large-en-v1.5"
    DIMENSIONS = 1024
    MAX_BATCH_SIZE = 100  # Process in batches for progress tracking

    def __init__(
        self,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize the embedding client.

        Args:
            cache_dir: Directory for cache file (default: project root)
        """
        # Load SentenceTransformer model
        logger.info(f"Loading model: {self.MODEL}...")
        self.model = SentenceTransformer(self.MODEL, trust_remote_code=True)
        logger.info("✅ Model loaded successfully")

        # Cache setup
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_file = cache_dir / "embeddings_cache.json"
        self.cache: Dict[str, List[float]] = {}

        # Load existing cache
        self._load_cache()

        logger.info(f"EmbeddingClient initialized with model: {self.MODEL}")
        logger.info(f"Cache loaded: {len(self.cache)} embeddings")

    def _load_cache(self) -> None:
        """Load embeddings cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                logger.debug(f"Loaded {len(self.cache)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}. Starting with empty cache.")
                self.cache = {}
        else:
            logger.debug("No cache file found. Starting with empty cache.")
            self.cache = {}

    def _save_cache(self) -> None:
        """Save embeddings cache to disk."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
            logger.debug(f"Saved {len(self.cache)} embeddings to cache")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _get_cache_key(self, text: str) -> str:
        """
        Generate cache key for text.

        Args:
            text: Input text

        Returns:
            MD5 hash of text
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _get_from_cache(self, text: str) -> Optional[List[float]]:
        """
        Get embedding from cache if available.

        Args:
            text: Input text

        Returns:
            Cached embedding vector or None
        """
        cache_key = self._get_cache_key(text)
        return self.cache.get(cache_key)

    def _add_to_cache(self, text: str, embedding: List[float]) -> None:
        """
        Add embedding to cache.

        Args:
            text: Input text
            embedding: Embedding vector
        """
        cache_key = self._get_cache_key(text)
        self.cache[cache_key] = embedding

    def embed_text(
        self,
        text: str,
        use_cache: bool = True
    ) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed
            use_cache: Whether to use cache (default: True)

        Returns:
            1024-dimensional embedding vector

        Raises:
            ValueError: If text is empty

        Example:
            >>> client = EmbeddingClient()
            >>> vector = client.embed_text("Bangkok night market")
            >>> len(vector)
            1024
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        text = text.strip()

        # Check cache first
        if use_cache:
            cached = self._get_from_cache(text)
            if cached is not None:
                logger.debug("Cache hit")
                return cached

        # Generate embedding using local model
        logger.debug(f"Generating embedding for text (length: {len(text)})")
        embedding = self.model.encode(text, convert_to_numpy=True).tolist()

        # Validate
        if not self.validate_embedding(embedding):
            raise ValueError("Generated embedding failed validation")

        # Cache the result
        if use_cache:
            self._add_to_cache(text, embedding)
            self._save_cache()

        return embedding

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
        use_cache: bool = True,
        show_progress: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing (default 100)
            use_cache: Whether to use cache (default: True)
            show_progress: Show progress bar (default: True)

        Returns:
            List of embedding vectors in same order as input

        Raises:
            ValueError: If texts is empty or batch_size invalid

        Example:
            >>> client = EmbeddingClient()
            >>> texts = ["text1", "text2", "text3"]
            >>> vectors = client.embed_batch(texts)
            >>> len(vectors) == len(texts)
            True
        """
        if not texts:
            raise ValueError("Texts list cannot be empty")

        if batch_size < 1 or batch_size > self.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size must be between 1 and {self.MAX_BATCH_SIZE}")

        # Remove empty texts and track indices
        valid_indices = []
        valid_texts = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_indices.append(i)
                valid_texts.append(text.strip())

        if not valid_texts:
            raise ValueError("All texts are empty")

        logger.info(f"Generating embeddings for {len(valid_texts)} texts (batch_size={batch_size})")

        # Initialize results array with None
        results = [None] * len(texts)

        # Check cache first
        uncached_indices = []
        uncached_texts = []
        cache_hits = 0

        if use_cache:
            for i, text in zip(valid_indices, valid_texts):
                cached = self._get_from_cache(text)
                if cached is not None:
                    results[i] = cached
                    cache_hits += 1
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)

            logger.info(f"Cache hits: {cache_hits}/{len(valid_texts)}")
        else:
            uncached_indices = valid_indices
            uncached_texts = valid_texts

        # Process uncached texts
        if uncached_texts:
            logger.debug(f"Generating {len(uncached_texts)} new embeddings")

            # Generate all embeddings at once using model.encode
            # The model handles batching internally for efficiency
            embeddings = self.model.encode(
                uncached_texts,
                convert_to_numpy=True,
                show_progress_bar=show_progress,
                batch_size=batch_size
            )

            # Convert to list and store results
            for original_idx, text, embedding in zip(uncached_indices, uncached_texts, embeddings):
                embedding_list = embedding.tolist()

                # Validate
                if not self.validate_embedding(embedding_list):
                    raise ValueError(f"Generated embedding failed validation for text at index {original_idx}")

                results[original_idx] = embedding_list

                if use_cache:
                    self._add_to_cache(text, embedding_list)

            # Save cache after batch processing
            if use_cache:
                self._save_cache()

        # Verify all results are filled
        for i, result in enumerate(results):
            if result is None:
                raise RuntimeError(f"Failed to generate embedding for text at index {i}")

        logger.info(f"✅ Generated {len(results)} embeddings")

        return results

    def validate_embedding(self, embedding: List[float]) -> bool:
        """
        Validate embedding vector.

        Args:
            embedding: Embedding vector to validate

        Returns:
            True if valid, False otherwise

        Checks:
        - Correct dimensions (1024)
        - No NaN values
        - Not all zeros
        """
        # Check dimensions
        if len(embedding) != self.DIMENSIONS:
            logger.error(f"Invalid dimensions: {len(embedding)} (expected {self.DIMENSIONS})")
            return False

        # Check for NaN
        if any(x != x for x in embedding):  # NaN check
            logger.error("Embedding contains NaN values")
            return False

        # Check not all zeros
        if all(x == 0.0 for x in embedding):
            logger.error("Embedding is all zeros")
            return False

        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.

        Returns:
            Dict with model info and cache stats
        """
        return {
            'model': self.MODEL,
            'dimensions': self.DIMENSIONS,
            'cache_size': len(self.cache),
            'cache_file': str(self.cache_file)
        }

    def print_stats(self) -> None:
        """Print usage statistics."""
        stats = self.get_stats()

        logger.info("=" * 60)
        logger.info("📊 EMBEDDING CLIENT STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Model: {stats['model']}")
        logger.info(f"Dimensions: {stats['dimensions']}")
        logger.info("Cost: FREE (local model)")
        logger.info(f"Cache size: {stats['cache_size']:,} embeddings")
        logger.info(f"Cache file: {stats['cache_file']}")
        logger.info("=" * 60)

    def get_cost_savings(self, num_embeddings: int, avg_tokens_per_text: int = 50) -> Dict[str, Any]:
        """
        Calculate cost savings vs OpenAI's text-embedding-3-small.

        Args:
            num_embeddings: Number of embeddings generated
            avg_tokens_per_text: Average tokens per text (default: 50)

        Returns:
            Dict with cost comparison data
        """
        # OpenAI pricing
        openai_cost_per_million = 0.02  # $0.02 per 1M tokens
        total_tokens = num_embeddings * avg_tokens_per_text
        openai_cost = (total_tokens / 1_000_000) * openai_cost_per_million

        return {
            'num_embeddings': num_embeddings,
            'avg_tokens_per_text': avg_tokens_per_text,
            'total_tokens': total_tokens,
            'openai_cost_usd': round(openai_cost, 6),
            'gte_large_cost_usd': 0.0,
            'savings_usd': round(openai_cost, 6),
            'quality': 'Better than OpenAI text-embedding-3-small'
        }


if __name__ == '__main__':
    """
    Test embedding client with sample texts.
    """
    logger.info("=" * 80)
    logger.info("TESTING EMBEDDING CLIENT")
    logger.info("=" * 80)

    # Initialize client
    logger.info("\n🔧 Initializing EmbeddingClient...")
    client = EmbeddingClient()

    # Test 1: Single text embedding
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Single Text Embedding")
    logger.info("=" * 80)

    test_text = "A romantic beachfront restaurant in Phuket serving fresh seafood with stunning sunset views"
    logger.info(f"Input: {test_text}")

    try:
        embedding = client.embed_text(test_text)
        logger.info(f"✅ Generated embedding: {len(embedding)} dimensions")
        logger.info(f"First 5 values: {embedding[:5]}")
        logger.info(f"Validation: {'✅ PASS' if client.validate_embedding(embedding) else '❌ FAIL'}")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")

    # Test 2: Batch embedding
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Batch Text Embedding (10 samples)")
    logger.info("=" * 80)

    sample_texts = [
        "Authentic Thai street food market in Bangkok with local vendors",
        "Luxury beach resort in Krabi with infinity pool and spa",
        "Ancient temple complex in Ayutthaya with historical significance",
        "Budget hostel in Chiang Mai near night market",
        "Elephant sanctuary in northern Thailand with ethical practices",
        "Rooftop bar in Bangkok with panoramic city views",
        "Island hopping tour in Phi Phi Islands with snorkeling",
        "Cooking class in Phuket learning traditional Thai cuisine",
        "Wat Pho temple featuring the famous reclining Buddha statue",
        "Floating market in Damnoen Saduak with boat vendors"
    ]

    logger.info(f"Generating embeddings for {len(sample_texts)} texts...")

    try:
        embeddings = client.embed_batch(sample_texts, batch_size=5, show_progress=True)

        logger.info(f"\n✅ Generated {len(embeddings)} embeddings")
        logger.info(f"All embeddings have {len(embeddings[0])} dimensions")

        # Validate all
        all_valid = all(client.validate_embedding(emb) for emb in embeddings)
        logger.info(f"Validation: {'✅ ALL PASS' if all_valid else '❌ SOME FAILED'}")

        # Show sample
        logger.info("\nSample embedding (first text):")
        logger.info(f"  Text: {sample_texts[0]}")
        logger.info(f"  First 10 values: {embeddings[0][:10]}")

    except Exception as e:
        logger.error(f"❌ Failed: {e}")

    # Test 3: Cache test
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Cache Performance")
    logger.info("=" * 80)

    logger.info("Re-embedding the same text to test cache...")

    try:
        # First call (should be cached from Test 1)
        start_time = time.time()
        embedding1 = client.embed_text(test_text)
        cached_time = time.time() - start_time

        logger.info(f"✅ Cache retrieval time: {cached_time*1000:.2f}ms")
        logger.info(f"Embedding matches original: {embedding1 == embedding}")

    except Exception as e:
        logger.error(f"❌ Failed: {e}")

    # Test 4: Cost savings
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Cost Savings vs OpenAI")
    logger.info("=" * 80)

    try:
        savings = client.get_cost_savings(num_embeddings=10, avg_tokens_per_text=50)
        logger.info(f"Number of embeddings: {savings['num_embeddings']}")
        logger.info(f"OpenAI cost: ${savings['openai_cost_usd']:.6f}")
        logger.info(f"gte-large cost: ${savings['gte_large_cost_usd']:.6f}")
        logger.info(f"✅ Savings: ${savings['savings_usd']:.6f}")
        logger.info(f"Quality: {savings['quality']}")
    except Exception as e:
        logger.error(f"❌ Failed: {e}")

    # Print final statistics
    logger.info("\n" + "=" * 80)
    logger.info("FINAL STATISTICS")
    logger.info("=" * 80)
    client.print_stats()

    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL TESTS COMPLETED!")
    logger.info("=" * 80)
