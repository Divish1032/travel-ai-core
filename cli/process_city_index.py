#!/usr/bin/env python3
"""
City Index Builder (Tier 1 for Stage 4)

Builds city-level index for Tier 1 destination selection in multi-day itineraries.
Aggregates entity-level data from Stage 3 to city level, generates embeddings,
and indexes to ChromaDB city_destinations collection.

Usage:
    python cli/process_city_index.py
    python cli/process_city_index.py --min-entities 10
    python cli/process_city_index.py --verify-only

    # Via crawl.sh
    ./crawl.sh process-city-index
    ./crawl.sh process-city-index --min-entities 10

Process:
1. Load entities from Stage 3
2. Aggregate to city level (city_aggregator.py)
3. Generate city embeddings (same model as entities: gte-large-en-v1.5)
4. Index to ChromaDB city_destinations collection
5. Verify index with sample queries

Features:
- Automatic city aggregation with configurable thresholds
- Cost estimation (FREE for local model!)
- Progress tracking with detailed statistics
- Index verification
- Metadata tracking

Environment Variables:
    CHROMADB_TENANT: Chroma Cloud tenant ID (required)
    CHROMADB_DATABASE: Chroma Cloud database name (default: default_database)
    CHROMADB_API_KEY: Chroma Cloud API key (required)
    EMBEDDING_MODEL: Model to use (default: gte-large)
"""

import click
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import sys
import time

from src.utils.logging import get_logger
from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.processors.city_aggregator import CityAggregator
from src.processors.city_indexer import index_city_embeddings, verify_city_index

logger = get_logger(__name__)


class CityIndexBuilder:
    """Orchestrates city-level index building process."""

    def __init__(
        self,
        s3_storage: S3Storage,
        min_entities_per_city: int = 5,
        batch_size: int = 50
    ):
        """
        Initialize city index builder.

        Args:
            s3_storage: S3 storage instance
            min_entities_per_city: Minimum entities required per city (default: 5)
            batch_size: Batch size for embedding generation (default: 50)
        """
        self.s3 = s3_storage
        self.min_entities_per_city = min_entities_per_city
        self.batch_size = batch_size

        self.stage3_storage = Stage3Storage(s3_storage)
        self.city_aggregator = CityAggregator()
        self.chromadb_client = None
        self.embedding_client = None

        self.stats = {
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'entities_loaded': 0,
            'cities_aggregated': 0,
            'cities_indexed': 0,
            'cities_failed': 0
        }

    def run(self, verify_only: bool = False) -> Dict:
        """
        Run city index building process.

        Args:
            verify_only: If True, only verify existing index (skip building)

        Returns:
            Dict with processing statistics
        """
        self.stats['start_time'] = datetime.now()
        start_time = time.time()

        logger.info("=" * 80)
        logger.info("🏙️  CITY-LEVEL INDEX BUILDER (TIER 1)")
        logger.info("=" * 80)

        try:
            # Initialize clients
            logger.info("\n📋 Step 1: Initializing clients...")
            self._initialize_clients()

            if verify_only:
                # Only verify existing index
                logger.info("\n🔍 Verifying existing city index...")
                result = verify_city_index(self.chromadb_client)

                if result['success']:
                    logger.info(f"✅ Verification successful: {result['total_cities']} cities indexed")
                else:
                    logger.error(f"❌ Verification failed: {result.get('error')}")

                return {
                    'success': result['success'],
                    'verification': result
                }

            # Load entities
            logger.info("\n📦 Step 2: Loading entities from Stage 3...")
            entities = self._load_entities()
            self.stats['entities_loaded'] = len(entities)

            # Aggregate to cities
            logger.info(f"\n🏙️  Step 3: Aggregating {len(entities)} entities to city level...")
            cities = self._aggregate_cities(entities)
            self.stats['cities_aggregated'] = len(cities)

            # Index cities
            logger.info(f"\n💾 Step 4: Indexing {len(cities)} cities to ChromaDB...")
            index_stats = self._index_cities(cities)
            self.stats['cities_indexed'] = index_stats['successful']
            self.stats['cities_failed'] = index_stats['failed']

            # Verify index
            logger.info("\n🔍 Step 5: Verifying city index...")
            verify_result = verify_city_index(self.chromadb_client)

            # Final stats
            self.stats['end_time'] = datetime.now()
            self.stats['duration_seconds'] = time.time() - start_time

            self._print_summary()

            return {
                'success': True,
                'stats': self.stats,
                'verification': verify_result
            }

        except Exception as e:
            logger.error(f"\n❌ City index building failed: {e}")
            logger.exception(e)

            self.stats['end_time'] = datetime.now()
            self.stats['duration_seconds'] = time.time() - start_time

            return {
                'success': False,
                'error': str(e),
                'stats': self.stats
            }

    def _initialize_clients(self):
        """Initialize ChromaDB and embedding clients."""
        # Initialize ChromaDB client
        self.chromadb_client = ChromaDBClient.initialize_from_env()
        logger.info(f"✅ ChromaDB initialized")

        # Initialize embedding client
        self.embedding_client = EmbeddingClient()
        logger.info(f"✅ Embedding client initialized")
        logger.info(f"   Model: {self.embedding_client.MODEL}")
        logger.info(f"   Dimensions: {self.embedding_client.DIMENSIONS}")

    def _load_entities(self):
        """Load and merge entities from Stage 3.

        Uses smart merging to handle multiple Stage 3 runs where the same
        entity may appear in multiple files with different data (new experiences,
        updated consensus, enriched attributes).
        """
        entities = self.stage3_storage.load_and_merge_all_entities()

        if not entities:
            raise RuntimeError("No entities found in Stage 3. Run Stage 3 first.")

        logger.info(f"✅ Loaded {len(entities)} entities from Stage 3 (with smart deduplication)")

        return entities

    def _aggregate_cities(self, entities):
        """Aggregate entities to city level."""
        cities = self.city_aggregator.aggregate_cities(
            entities=entities,
            min_entities_per_city=self.min_entities_per_city
        )

        if not cities:
            raise RuntimeError(
                f"No cities found with at least {self.min_entities_per_city} entities. "
                f"Try lowering --min-entities threshold."
            )

        logger.info(f"✅ Aggregated to {len(cities)} cities")

        # Log top cities
        logger.info("\nTop 10 cities by entity count:")
        for i, city in enumerate(cities[:10], 1):
            logger.info(
                f"  {i}. {city['city']}, {city['country']}: "
                f"{city['entity_count']} entities, "
                f"rating {city.get('avg_rating', 'N/A')}"
            )

        return cities

    def _index_cities(self, cities):
        """Index cities to ChromaDB."""
        index_stats = index_city_embeddings(
            cities=cities,
            chromadb_client=self.chromadb_client,
            embedding_client=self.embedding_client,
            batch_size=self.batch_size,
            show_progress=True
        )

        return index_stats

    def _print_summary(self):
        """Print final summary statistics."""
        logger.info("\n" + "=" * 80)
        logger.info("📊 CITY INDEX BUILDING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"⏱️  Duration: {self.stats['duration_seconds']:.2f}s")
        logger.info(f"📦 Entities loaded: {self.stats['entities_loaded']}")
        logger.info(f"🏙️  Cities aggregated: {self.stats['cities_aggregated']}")
        logger.info(f"✅ Cities indexed: {self.stats['cities_indexed']}")
        logger.info(f"❌ Cities failed: {self.stats['cities_failed']}")

        if self.stats['cities_indexed'] > 0:
            avg_time_per_city = self.stats['duration_seconds'] / self.stats['cities_indexed']
            logger.info(f"⚡ Avg time per city: {avg_time_per_city:.2f}s")

        logger.info("=" * 80)


@click.command()
@click.option(
    '--min-entities',
    type=int,
    default=5,
    help='Minimum entities required per city (default: 5)'
)
@click.option(
    '--batch-size',
    type=int,
    default=50,
    help='Batch size for embedding generation (default: 50)'
)
@click.option(
    '--verify-only',
    is_flag=True,
    help='Only verify existing index (skip building)'
)
def main(min_entities, batch_size, verify_only):
    """
    Build city-level index for Tier 1 destination selection.

    Aggregates entity-level data to city level and indexes to ChromaDB.
    """
    logger.info("🚀 Starting City Index Builder...")

    try:
        # Initialize S3 storage
        s3_storage = S3Storage()

        # Initialize builder
        builder = CityIndexBuilder(
            s3_storage=s3_storage,
            min_entities_per_city=min_entities,
            batch_size=batch_size
        )

        # Run
        result = builder.run(verify_only=verify_only)

        if result['success']:
            logger.info("\n✅ City index building completed successfully!")
            sys.exit(0)
        else:
            logger.error(f"\n❌ City index building failed: {result.get('error')}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Fatal error: {e}")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
