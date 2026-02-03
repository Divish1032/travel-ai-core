#!/usr/bin/env python3
"""
RAG Pipeline - Complete Orchestration of Itinerary Generation

Main entry point for the RAG system. Coordinates all 7 phases:
1. Intent parsing
2. Entity retrieval
3. Re-ranking
4. Context building
5. Itinerary generation
6. Validation
7. Narrative generation
8. Formatting

Features:
- Single-function API for itinerary generation
- Automatic validation and retry logic
- Cost tracking and performance metrics
- Error recovery and graceful degradation
- Optional caching layer

Author: TravelAI Team
Date: 2025-12-20
"""

import time
import hashlib
import json
from typing import Dict, List, Optional, Generator, Any
from collections import defaultdict

from src.rag.intent_parser import IntentParser
from src.rag.retriever import RAGRetriever
from src.rag.reranker import LLMReranker
from src.rag.context_builder import ContextBuilder
from src.rag.itinerary_generator import ItineraryGenerator
from src.rag.validator import ItineraryValidator
from src.rag.narrative_generator import NarrativeGenerator
from src.rag.formatter import ItineraryFormatter
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class InsufficientDataError(Exception):
    """Raised when not enough data available for destination"""
    pass


class ValidationError(Exception):
    """Raised when generated itinerary fails validation"""
    pass


class PipelineError(Exception):
    """Generic pipeline error"""
    pass


# =============================================================================
# RAG Pipeline
# =============================================================================

class RAGPipeline:
    """
    Complete RAG pipeline orchestration.

    Coordinates all phases from query parsing to formatted output.
    Includes validation loops, error recovery, and performance tracking.

    Example:
        >>> pipeline = RAGPipeline()
        >>> result = pipeline.generate("5 days Bangkok solo budget party")
        >>> print(result['formatted_output'])
        >>> print(f"Cost: ${result['metadata']['total_cost']:.4f}")
    """

    def __init__(
        self,
        chromadb_client: Optional[ChromaDBClient] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        enable_cache: bool = False
    ):
        """
        Initialize RAG pipeline.

        Args:
            chromadb_client: ChromaDB client (optional, will initialize if not provided)
            embedding_client: Embedding client (optional, will initialize if not provided)
            enable_cache: Enable result caching (default: False)
        """
        logger.info("=" * 80)
        logger.info("🚀 INITIALIZING RAG PIPELINE")
        logger.info("=" * 80)

        # Initialize database clients if not provided
        if chromadb_client is None:
            logger.info("Initializing ChromaDB client...")
            chromadb_client = ChromaDBClient.initialize_from_env()

        if embedding_client is None:
            logger.info("Initializing embedding client...")
            embedding_client = EmbeddingClient()

        # Initialize all components
        logger.info("Initializing pipeline components...")
        self.intent_parser = IntentParser()
        self.retriever = RAGRetriever(chromadb_client, embedding_client)
        self.reranker = LLMReranker()
        self.context_builder = ContextBuilder()
        self.generator = ItineraryGenerator()
        self.validator = ItineraryValidator()
        self.narrative_gen = NarrativeGenerator()
        self.formatter = ItineraryFormatter()

        # Cache
        self.enable_cache = enable_cache
        self.cache = {} if enable_cache else None
        self.cache_metadata = defaultdict(dict)

        logger.info("✅ Pipeline initialized successfully")
        logger.info("=" * 80 + "\n")

    def generate(
        self,
        query: str,
        max_retries: int = 2,
        output_format: str = 'markdown',
        skip_narrative: bool = False
    ) -> Dict[str, Any]:
        """
        Main pipeline: Query → Itinerary

        Args:
            query: Natural language travel query
            max_retries: Maximum validation retry attempts (default: 2)
            output_format: Output format ('json', 'markdown', 'html', 'text')
            skip_narrative: Skip narrative generation for faster output

        Returns:
            Dict containing:
            {
                'itinerary': GeneratedItinerary object,
                'narrative': ItineraryNarrative object (or None if skipped),
                'validation_report': ValidationReport object,
                'formatted_output': str (formatted itinerary),
                'metadata': {
                    'query': str,
                    'total_cost': float (USD),
                    'processing_time': float (seconds),
                    'phases_completed': int,
                    'retries_used': int,
                    'validation_score': float,
                    'entities_retrieved': int,
                    'entities_used': int
                }
            }

        Raises:
            InsufficientDataError: Not enough data for destination
            ValidationError: Generated itinerary invalid after all retries
            PipelineError: Other pipeline errors
        """
        logger.info("=" * 80)
        logger.info("🌍 RAG PIPELINE - GENERATING ITINERARY")
        logger.info("=" * 80)
        logger.info(f"Query: {query}")
        logger.info(f"Output format: {output_format}")
        logger.info(f"Skip narrative: {skip_narrative}")
        logger.info("")

        start_time = time.time()
        total_cost = 0.0
        phases_completed = 0

        try:
            # ========================================
            # PHASE 1: Parse Intent
            # ========================================
            logger.info("📋 Phase 1/7: Parsing query...")
            intent = self.intent_parser.parse_query(query)
            total_cost += self.intent_parser.total_cost
            phases_completed += 1

            logger.info(f"   Destination: {intent.destination}")
            logger.info(f"   Duration: {intent.duration_days} days")
            logger.info(f"   Profile: {intent.traveler_profile.to_profile_key()}")
            logger.info("")

            # ========================================
            # PHASE 2: Retrieve Entities
            # ========================================
            logger.info("🔍 Phase 2/7: Retrieving entities...")
            candidates = self.retriever.retrieve_for_itinerary(intent, top_k=20)
            phases_completed += 1

            if len(candidates) == 0:
                raise InsufficientDataError(
                    f"No data found for {intent.destination}. "
                    f"Try a different destination or broader search."
                )

            logger.info(f"   Retrieved: {len(candidates)} entities")
            logger.info("")

            # ========================================
            # PHASE 3: Re-rank
            # ========================================
            logger.info("⭐ Phase 3/7: Personalizing recommendations...")
            reranked = self.reranker.rerank_candidates(
                candidates,
                intent,
                top_k=min(12, len(candidates))
            )
            total_cost += self.reranker.total_cost
            phases_completed += 1

            logger.info(f"   Top candidates: {len(reranked)}")
            logger.info("")

            # ========================================
            # PHASE 4: Build Context
            # ========================================
            logger.info("📚 Phase 4/7: Building context...")
            context = self.context_builder.build_rag_context(reranked, intent)
            phases_completed += 1

            logger.info(f"   Context size: ~{context.estimated_tokens} tokens")
            logger.info("")

            # ========================================
            # PHASE 5-6: Generate with Validation Loop
            # ========================================
            logger.info("✨ Phase 5-6/7: Generating and validating...")

            itinerary = None
            report = None
            attempt = 0

            for attempt in range(max_retries):
                # Generate
                logger.info(f"   Attempt {attempt + 1}/{max_retries}: Generating itinerary...")
                itinerary = self.generator.generate_itinerary(context, intent)
                total_cost += self.generator.total_cost

                # Validate
                logger.info(f"   Validating (attempt {attempt + 1})...")
                report = self.validator.validate_itinerary(itinerary, context, intent)

                logger.info(f"   Validation score: {report.overall_score:.2f}/1.0")
                logger.info(f"   Issues: {len(report.issues)} ({sum(1 for i in report.issues if i.severity == 'error')} errors)")

                # If valid or last attempt, proceed
                if report.is_valid or attempt == max_retries - 1:
                    break

                logger.warning("   Validation failed, retrying...")

            phases_completed += 2  # Generation + Validation

            if not report.is_valid and max_retries > 0:
                logger.warning(
                    f"⚠️  Validation failed after {max_retries} attempts. "
                    f"Proceeding with best-effort itinerary (score: {report.overall_score:.2f})"
                )

            logger.info("")

            # ========================================
            # PHASE 7: Generate Narrative (Optional)
            # ========================================
            narrative = None
            if not skip_narrative:
                logger.info("📝 Phase 7/7: Generating narrative...")
                narrative = self.narrative_gen.generate_narrative(itinerary, intent)
                total_cost += self.narrative_gen.total_cost
                phases_completed += 1

                logger.info(f"   Narrative: {narrative.word_count} words")
                logger.info("")
            else:
                logger.info("⏭️  Phase 7/7: Skipped narrative generation")
                phases_completed += 1

            # ========================================
            # PHASE 8: Format Output
            # ========================================
            logger.info("🎨 Formatting output...")
            if output_format == 'json':
                formatted = json.dumps(
                    self.formatter.format_json(itinerary, narrative),
                    indent=2
                )
            elif output_format == 'markdown':
                formatted = self.formatter.format_markdown(itinerary, narrative)
            elif output_format == 'html':
                formatted = self.formatter.format_html(itinerary, narrative)
            else:  # text
                formatted = self.formatter.format_text_summary(itinerary)

            # ========================================
            # Compile Result
            # ========================================
            processing_time = time.time() - start_time

            result = {
                'itinerary': itinerary,
                'narrative': narrative,
                'validation_report': report,
                'formatted_output': formatted,
                'metadata': {
                    'query': query,
                    'total_cost': total_cost,
                    'processing_time': processing_time,
                    'phases_completed': phases_completed,
                    'retries_used': attempt,
                    'validation_score': report.overall_score,
                    'validation_passed': report.is_valid,
                    'entities_retrieved': len(candidates),
                    'entities_used': len(itinerary.days) * 3,  # Rough estimate
                    'output_format': output_format,
                    'narrative_generated': not skip_narrative
                }
            }

            logger.info("=" * 80)
            logger.info("✅ PIPELINE COMPLETE")
            logger.info("=" * 80)
            logger.info(f"Duration: {intent.duration_days} days in {itinerary.destination}")
            logger.info(f"Processing time: {processing_time:.2f}s")
            logger.info(f"Total cost: ${total_cost:.4f}")
            logger.info(f"Validation: {'✅ Passed' if report.is_valid else '⚠️  Warnings'} ({report.overall_score:.2f}/1.0)")
            logger.info("=" * 80 + "\n")

            return result

        except InsufficientDataError as e:
            logger.error(f"❌ Insufficient data: {e}")
            raise

        except Exception as e:
            logger.error(f"❌ Pipeline error: {e}", exc_info=True)
            raise PipelineError(f"Generation failed: {str(e)}") from e

    def generate_cached(
        self,
        query: str,
        cache_ttl: int = 3600,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate with caching.

        Same queries within TTL return cached results.

        Args:
            query: Travel query
            cache_ttl: Cache time-to-live in seconds (default: 3600)
            **kwargs: Additional arguments passed to generate()

        Returns:
            Same as generate()
        """
        if not self.enable_cache:
            logger.warning("Cache not enabled, generating fresh result")
            return self.generate(query, **kwargs)

        # Generate cache key
        cache_key = hashlib.md5(
            f"{query}:{json.dumps(kwargs, sort_keys=True)}".encode()
        ).hexdigest()

        # Check cache
        if cache_key in self.cache:
            cached_result = self.cache[cache_key]
            cache_age = time.time() - self.cache_metadata[cache_key]['timestamp']

            if cache_age < cache_ttl:
                logger.info(f"✅ Cache hit (age: {cache_age:.0f}s)")
                cached_result['metadata']['cached'] = True
                cached_result['metadata']['cache_age'] = cache_age
                return cached_result
            else:
                logger.info(f"⏰ Cache expired (age: {cache_age:.0f}s > {cache_ttl}s)")

        # Generate fresh
        logger.info("🔄 Cache miss, generating fresh result")
        result = self.generate(query, **kwargs)

        # Cache result
        self.cache[cache_key] = result
        self.cache_metadata[cache_key] = {
            'timestamp': time.time(),
            'query': query
        }

        result['metadata']['cached'] = False

        return result

    def generate_streaming(
        self,
        query: str,
        **kwargs
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate with streaming progress updates.

        Useful for UI progress bars and real-time feedback.

        Args:
            query: Travel query
            **kwargs: Additional arguments passed to generate()

        Yields:
            Progress updates:
            {
                'phase': str (e.g., 'parsing', 'retrieval'),
                'status': str ('started', 'complete'),
                'data': Any (phase-specific data),
                'progress': float (0.0-1.0)
            }

            Final result:
            {
                'phase': 'complete',
                'result': Dict (same as generate())
            }
        """
        total_phases = 7 if not kwargs.get('skip_narrative', False) else 6

        try:
            # Phase 1: Parsing
            yield {'phase': 'parsing', 'status': 'started', 'progress': 0.0}
            intent = self.intent_parser.parse_query(query)
            yield {
                'phase': 'parsing',
                'status': 'complete',
                'data': {
                    'destination': intent.destination,
                    'duration': intent.duration_days
                },
                'progress': 1 / total_phases
            }

            # Phase 2: Retrieval
            yield {'phase': 'retrieval', 'status': 'started', 'progress': 1 / total_phases}
            # Continue generation but yield progress...
            # (Simplified for brevity - full implementation would yield at each phase)

            # For now, just run full pipeline and yield final result
            result = self.generate(query, **kwargs)
            yield {'phase': 'complete', 'result': result, 'progress': 1.0}

        except Exception as e:
            yield {
                'phase': 'error',
                'error': str(e),
                'progress': -1
            }

    def generate_batch(
        self,
        queries: List[str],
        parallel: bool = False,
        max_workers: int = 3,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple itineraries.

        Args:
            queries: List of travel queries
            parallel: Run in parallel (default: False)
            max_workers: Max parallel workers (default: 3)
            **kwargs: Additional arguments passed to generate()

        Returns:
            List of results (same format as generate())
        """
        logger.info(f"📦 Batch generation: {len(queries)} queries (parallel={parallel})")

        if parallel:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_query = {
                    executor.submit(self.generate, q, **kwargs): q
                    for q in queries
                }

                for i, future in enumerate(as_completed(future_to_query)):
                    query = future_to_query[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.info(f"   ✅ Completed {i + 1}/{len(queries)}: {query[:50]}...")
                    except Exception as e:
                        logger.error(f"   ❌ Failed {i + 1}/{len(queries)}: {query[:50]}... - {e}")
                        results.append({
                            'error': str(e),
                            'query': query,
                            'metadata': {'status': 'failed'}
                        })

            return results
        else:
            results = []
            for i, query in enumerate(queries, 1):
                logger.info(f"   Processing {i}/{len(queries)}: {query[:50]}...")
                try:
                    result = self.generate(query, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"   ❌ Failed: {e}")
                    results.append({
                        'error': str(e),
                        'query': query,
                        'metadata': {'status': 'failed'}
                    })

            return results

    def clear_cache(self):
        """Clear result cache."""
        if self.cache:
            self.cache.clear()
            self.cache_metadata.clear()
            logger.info("🗑️  Cache cleared")
        else:
            logger.warning("Cache not enabled")


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("RAG Pipeline Test")
    print("=" * 70)

    # Initialize pipeline
    pipeline = RAGPipeline(enable_cache=True)

    # Test query
    test_query = "5 days Bangkok solo budget party"

    print(f"\nQuery: {test_query}\n")

    # Generate itinerary
    result = pipeline.generate(
        query=test_query,
        output_format='markdown',
        skip_narrative=True  # Skip for faster testing
    )

    # Print result
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(result['formatted_output'])
    print("\n" + "=" * 70)
    print("METADATA")
    print("=" * 70)
    for key, value in result['metadata'].items():
        print(f"  {key}: {value}")
    print("=" * 70)
