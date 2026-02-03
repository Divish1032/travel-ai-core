#!/usr/bin/env python3
"""
City Indexer for Stage 4 Tier 1

Indexes city-level aggregations to ChromaDB for destination selection.
This enables Tier 1 city search for multi-day itinerary planning.

Features:
- Embeds city summary texts using same model as entities (gte-large-en-v1.5)
- Creates separate `city_destinations` collection in ChromaDB
- Stores city-level metadata for filtering and ranking
- Batch processing for efficiency
- Progress tracking and error handling

Architecture Context:
- Input: City aggregations from city_aggregator.py
- Output: City embeddings indexed to ChromaDB (city_destinations collection)
- Purpose: Enable Tier 1 semantic search for city selection
- Next Step: City selector queries this index (city_selector.py)

Example:
    >>> from src.processors.city_aggregator import CityAggregator
    >>> from src.vectordb import ChromaDBClient
    >>> from src.utils.embedding_client import EmbeddingClient
    >>>
    >>> # Initialize
    >>> chromadb = ChromaDBClient.initialize_from_env()
    >>> embedding_client = EmbeddingClient()
    >>> aggregator = CityAggregator()
    >>>
    >>> # Aggregate and index
    >>> cities = aggregator.aggregate_cities(entities)
    >>> stats = index_city_embeddings(cities, chromadb, embedding_client)
    >>> stats['successful']
    25
"""

import time
from typing import List, Dict, Any

from tqdm import tqdm

from src.utils.logging import get_logger

logger = get_logger(__name__)


def prepare_city_metadata(city: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare metadata for city embedding.

    ChromaDB metadata requirements:
    - Values must be: str, int, float, bool (no lists/dicts)
    - Arrays must be converted to JSON strings
    - Total metadata size must be under 4KB (Chroma Cloud limit)

    Args:
        city: City aggregation dict from city_aggregator

    Returns:
        Metadata dict compatible with ChromaDB

    Example:
        >>> city = aggregator.aggregate_cities(entities)[0]
        >>> metadata = prepare_city_metadata(city)
        >>> metadata['city']
        'Bangkok'
    """
    # Identity
    city_id = city.get('city_id', 'unknown')
    city_name = city.get('city', 'Unknown')
    country = city.get('country', 'Unknown')

    # Counts
    entity_count = city.get('entity_count', 0)
    entity_types = city.get('entity_types', {})

    # Budget distribution
    budget_dist = city.get('budget_distribution', {})
    dominant_budget = max(budget_dist.items(), key=lambda x: x[1])[0] if budget_dist else 'mid-range'

    # Rating
    avg_rating = city.get('avg_rating')

    # Seasons
    best_seasons = city.get('best_seasons', [])
    best_seasons_str = ", ".join(best_seasons) if best_seasons else ""

    # Coordinates
    coordinates = city.get('coordinates', {})
    lat = coordinates.get('lat')
    lon = coordinates.get('lon')

    # Recommended days
    recommended_days = city.get('recommended_days', '2-3')

    # Build metadata
    metadata = {
        # Identity
        'city_id': city_id,
        'city': city_name,
        'country': country,

        # Counts
        'entity_count': entity_count,
        'restaurant_count': entity_types.get('restaurant', 0),
        'attraction_count': entity_types.get('attraction', 0),
        'hotel_count': entity_types.get('hotel', 0),
        'activity_count': entity_types.get('activity', 0),

        # Budget
        'dominant_budget': dominant_budget,
        'budget_pct': float(budget_dist.get('budget', 0.0)),
        'midrange_pct': float(budget_dist.get('mid-range', 0.0)),
        'luxury_pct': float(budget_dist.get('luxury', 0.0)),

        # Quality
        'avg_rating': float(avg_rating) if avg_rating else 0.0,

        # Temporal
        'best_seasons': best_seasons_str,

        # Recommended
        'recommended_days': recommended_days,
    }

    # Optional coordinates
    if lat is not None:
        metadata['lat'] = float(lat)
    if lon is not None:
        metadata['lon'] = float(lon)

    # Phase 2: Add vibe metadata (12D vibe system)
    vibes = city.get('vibes', {})
    if vibes:
        # Add individual vibe dimensions (only non-zero values to save space)
        for vibe_dim, vibe_val in vibes.items():
            if vibe_val > 0.1:  # Only store significant vibes
                metadata[f'vibe_{vibe_dim}'] = float(vibe_val)

        # Also store complete vibes as JSON string for retrieval
        import json
        metadata['vibes_json'] = json.dumps(vibes)

    return metadata


def index_city_embeddings(
    cities: List[Dict[str, Any]],
    chromadb_client,
    embedding_client,
    batch_size: int = 50,
    show_progress: bool = True
) -> Dict[str, Any]:
    """
    Index city-level embeddings into ChromaDB.

    Process:
    1. Extract summary texts from cities
    2. Generate embeddings in batches
    3. Prepare metadata for each city
    4. Add to city_destinations collection
    5. Track progress and errors

    Args:
        cities: List of city aggregation dicts from city_aggregator
        chromadb_client: ChromaDBClient instance with city_destinations collection
        embedding_client: EmbeddingClient instance
        batch_size: Batch size for embedding generation (default: 50)
        show_progress: Show progress bars (default: True)

    Returns:
        Dict with indexing statistics:
        - total_cities: Total cities processed
        - successful: Successfully indexed
        - failed: Failed to index
        - errors: List of error messages
        - duration_seconds: Total processing time

    Example:
        >>> stats = index_city_embeddings(cities, chromadb, embedding_client)
        >>> stats['successful']
        25
    """
    logger.info("=" * 80)
    logger.info("🏙️  INDEXING CITY-LEVEL EMBEDDINGS (TIER 1)")
    logger.info("=" * 80)

    start_time = time.time()
    total_cities = len(cities)
    successful = 0
    failed = 0
    errors = []

    logger.info(f"Total cities to index: {total_cities}")
    logger.info(f"Batch size: {batch_size}")

    # Check if city_destinations collection exists
    if not hasattr(chromadb_client, 'city_destinations_collection'):
        error_msg = "city_destinations collection not found in ChromaDB client"
        logger.error(f"❌ {error_msg}")
        return {
            'total_cities': total_cities,
            'successful': 0,
            'failed': total_cities,
            'errors': [error_msg],
            'duration_seconds': time.time() - start_time
        }

    collection = chromadb_client.city_destinations_collection

    # Step 1: Extract summary texts
    logger.info("\n📝 Step 1: Extracting city summary texts...")
    city_texts = []
    city_ids = []

    for city in cities:
        city_id = city.get('city_id', 'unknown')
        summary_text = city.get('summary_text', '')

        if not summary_text:
            logger.warning(f"⚠️  No summary text for city {city_id}")
            continue

        city_texts.append(summary_text)
        city_ids.append(city_id)

    logger.info(f"✅ Extracted {len(city_texts)} summary texts")

    # Step 2: Generate embeddings in batches
    logger.info("\n🔢 Step 2: Generating embeddings...")
    all_embeddings = []

    # Create batches
    batches = []
    for i in range(0, len(city_texts), batch_size):
        batches.append(city_texts[i:i + batch_size])

    # Process batches with progress bar
    iterator = tqdm(batches, desc="Embedding batches") if show_progress else batches

    for batch in iterator:
        try:
            # Generate embeddings for this batch
            embeddings = embedding_client.embed_batch(batch)
            all_embeddings.extend(embeddings)

        except Exception as e:
            logger.error(f"❌ Failed to generate embeddings for batch: {e}")
            errors.append(f"Embedding generation error: {e}")
            # Add empty embeddings as placeholders
            all_embeddings.extend([None] * len(batch))

    logger.info(f"✅ Generated {len([e for e in all_embeddings if e is not None])} embeddings")

    # Step 3: Prepare metadata and index
    logger.info("\n💾 Step 3: Indexing to ChromaDB...")

    # Find cities by their ID
    city_lookup = {city['city_id']: city for city in cities}

    # Prepare batch data for ChromaDB
    batch_ids = []
    batch_embeddings = []
    batch_metadatas = []
    batch_documents = []

    for i, city_id in enumerate(city_ids):
        embedding = all_embeddings[i]

        if embedding is None:
            failed += 1
            continue

        city = city_lookup.get(city_id)
        if not city:
            failed += 1
            continue

        # Prepare metadata
        try:
            metadata = prepare_city_metadata(city)
        except Exception as e:
            logger.error(f"❌ Failed to prepare metadata for {city_id}: {e}")
            failed += 1
            errors.append(f"Metadata error for {city_id}: {e}")
            continue

        # Add to batch
        batch_ids.append(city_id)
        batch_embeddings.append(embedding)
        batch_metadatas.append(metadata)
        batch_documents.append(city['summary_text'])

    # Index to ChromaDB
    if batch_ids:
        try:
            collection.upsert(  # Changed from .add() to support incremental updates
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents
            )
            successful = len(batch_ids)
            logger.info(f"✅ Successfully indexed {successful} cities")

        except Exception as e:
            logger.error(f"❌ Failed to add cities to ChromaDB: {e}")
            failed = len(batch_ids)
            errors.append(f"ChromaDB add error: {e}")

    # Final stats
    duration = time.time() - start_time

    logger.info("\n" + "=" * 80)
    logger.info("📊 INDEXING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total cities: {total_cities}")
    logger.info(f"✅ Successful: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"⏱️  Duration: {duration:.2f}s")

    return {
        'total_cities': total_cities,
        'successful': successful,
        'failed': failed,
        'errors': errors,
        'duration_seconds': duration
    }


def verify_city_index(
    chromadb_client,
    sample_query: str = "vibrant nightlife and street food"
) -> Dict[str, Any]:
    """
    Verify city index by running a sample query.

    Args:
        chromadb_client: ChromaDBClient instance
        sample_query: Sample query text for testing

    Returns:
        Dict with verification results

    Example:
        >>> result = verify_city_index(chromadb, "beach and relaxation")
        >>> result['results']
        [{'city': 'Phuket', 'country': 'Thailand', 'distance': 0.45}]
    """
    logger.info(f"\n🔍 Verifying city index with query: '{sample_query}'")

    if not hasattr(chromadb_client, 'city_destinations_collection'):
        logger.error("❌ city_destinations collection not found")
        return {'success': False, 'error': 'Collection not found'}

    collection = chromadb_client.city_destinations_collection

    try:
        # Get total count
        total_cities = collection.count()
        logger.info(f"Total cities in index: {total_cities}")

        # Run sample query
        results = collection.query(
            query_texts=[sample_query],
            n_results=5
        )

        logger.info(f"✅ Query successful, found {len(results['ids'][0])} results")

        # Format results
        formatted_results = []
        for i in range(len(results['ids'][0])):
            formatted_results.append({
                'city_id': results['ids'][0][i],
                'city': results['metadatas'][0][i].get('city'),
                'country': results['metadatas'][0][i].get('country'),
                'distance': results['distances'][0][i] if 'distances' in results else None
            })

        logger.info("Top results:")
        for r in formatted_results:
            logger.info(f"  - {r['city']}, {r['country']} (distance: {r['distance']:.3f})")

        return {
            'success': True,
            'total_cities': total_cities,
            'query': sample_query,
            'results': formatted_results
        }

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return {'success': False, 'error': str(e)}
