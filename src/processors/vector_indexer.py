#!/usr/bin/env python3
"""
Vector Indexer for Stage 4

Handles indexing of embeddings into ChromaDB for all three embedding strategies:
1. Entity-level embeddings (Type 1) - General entity search
2. Profile-consensus embeddings (Type 2) - Profile-specific recommendations
3. Experience-level embeddings (Type 3) - Individual traveler stories

Features:
- Batch processing for efficiency
- Progress tracking with tqdm
- Error handling and retry logic
- Metadata validation
- Verification tools

Example:
    >>> from src.vectordb import ChromaDBClient
    >>> from src.utils.embedding_client import EmbeddingClient
    >>> from src.storage.stage3_storage import Stage3Storage
    >>>
    >>> # Initialize clients
    >>> chromadb = ChromaDBClient.initialize_from_env()
    >>> embedding_client = EmbeddingClient()
    >>> stage3 = Stage3Storage()
    >>>
    >>> # Load entities
    >>> entities = stage3.load_all_canonical_entities()
    >>>
    >>> # Index entity-level embeddings
    >>> stats = index_entity_embeddings(entities, chromadb, embedding_client)
"""

import json
import time
import random
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import numpy as np

from tqdm import tqdm

from src.utils.logging import get_logger
from src.utils.metadata_utils import validate_metadata_size, log_metadata_stats
from src.processors.embedding_generator import (
    generate_entity_embedding_text,
    batch_generate_entity_texts,
    generate_profile_consensus_text,
    batch_generate_profile_consensus_texts,
    generate_experience_text,
    batch_generate_experience_texts
)

logger = get_logger(__name__)


def prepare_profile_metadata(
    entity: Dict[str, Any],
    profile_key: str,
    profile_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Prepare metadata for profile-consensus embedding.

    ChromaDB metadata requirements:
    - Values must be: str, int, float, bool (no lists/dicts)
    - Arrays must be converted to JSON strings

    Args:
        entity: Canonical entity dict from Stage 3
        profile_key: Profile key (e.g., "couple_26-35_mid-range")
        profile_data: Profile-specific metrics from consensus

    Returns:
        Metadata dict compatible with ChromaDB

    Example:
        >>> entity = load_canonical_entity("restaurant_bangkok_001")
        >>> profile_data = entity['consensus']['profile_metrics']['couple_26-35_mid-range']
        >>> metadata = prepare_profile_metadata(entity, 'couple_26-35_mid-range', profile_data)
        >>> metadata['traveler_profile']
        'couple_26-35_mid-range'
    """
    entity_id = entity.get('entity_id', 'unknown')
    canonical_name = entity.get('canonical_name', 'Unknown')
    entity_type = entity.get('entity_type', 'unknown')
    location = entity.get('location', 'Unknown')

    # Extract location components
    location_parts = location.split(', ') if location else []
    city = location_parts[0] if len(location_parts) > 0 else 'Unknown'
    country = location_parts[-1] if len(location_parts) > 1 else 'Unknown'

    # Coordinates
    coordinates = entity.get('coordinates', {})
    lat = coordinates.get('lat')
    lon = coordinates.get('lon')

    # Profile-specific metrics
    profile_rating = profile_data.get('avg_rating')
    profile_mentions = profile_data.get('mention_count', 0)

    # Profile sentiment distribution
    sentiment_dist = profile_data.get('sentiment_dist', {})
    positive = sentiment_dist.get('positive', 0)
    negative = sentiment_dist.get('negative', 0)
    neutral = sentiment_dist.get('neutral', 0)

    # Determine dominant sentiment
    if positive > negative and positive > neutral:
        dominant_sentiment = 'positive'
    elif negative > positive and negative > neutral:
        dominant_sentiment = 'negative'
    else:
        dominant_sentiment = 'neutral'

    # Attributes
    attributes = entity.get('attributes', {})
    travel_style = attributes.get('travel_style', [])
    profile_themes = profile_data.get('common_themes', [])

    # Build metadata
    metadata = {
        'embedding_id': f"profile_{entity_id}_{profile_key}",
        'embedding_type': 'profile_consensus',
        'entity_id': entity_id,
        'canonical_name': canonical_name,
        'entity_type': entity_type,
        'location': location,
        'city': city,
        'country': country,
        'traveler_profile': profile_key,
        'profile_mentions': profile_mentions,
        'profile_sentiment': dominant_sentiment,
    }

    # Optional fields
    if lat is not None:
        metadata['lat'] = float(lat)
    if lon is not None:
        metadata['lon'] = float(lon)
    if profile_rating is not None:
        metadata['profile_rating'] = float(profile_rating)

    # Arrays as JSON strings (truncated to avoid size limits)
    if travel_style:
        # Limit to top 5 items to reduce metadata size
        truncated_style = travel_style[:5] if len(travel_style) > 5 else travel_style
        metadata['travel_style'] = json.dumps(truncated_style)
    if profile_themes:
        # Limit to top 10 themes
        truncated_themes = profile_themes[:10] if len(profile_themes) > 10 else profile_themes
        metadata['profile_themes'] = json.dumps(truncated_themes)

    # Sentiment distribution as compact JSON (only counts, not full details)
    metadata['sentiment_positive'] = sentiment_dist.get('positive', 0)
    metadata['sentiment_negative'] = sentiment_dist.get('negative', 0)
    metadata['sentiment_neutral'] = sentiment_dist.get('neutral', 0)

    # NOTE: Removed consensus_json and entity_json backup fields to comply with Chroma Cloud 4KB metadata limit
    # Full data can be retrieved from S3 if needed using entity_id

    # Validate metadata size (auto-truncate if needed)
    metadata = validate_metadata_size(metadata, entity_id=f"{entity_id}_{profile_key}", auto_truncate=True)

    return metadata


def prepare_entity_metadata(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare metadata for entity-level embedding.

    ChromaDB metadata requirements:
    - Values must be: str, int, float, bool (no lists/dicts)
    - Arrays must be converted to JSON strings

    Args:
        entity: Canonical entity dict from Stage 3

    Returns:
        Metadata dict compatible with ChromaDB

    Example:
        >>> entity = load_canonical_entity("area_bangkok_001")
        >>> metadata = prepare_entity_metadata(entity)
        >>> metadata['entity_type']
        'area'
    """
    entity_id = entity.get('entity_id', 'unknown')
    canonical_name = entity.get('canonical_name', 'Unknown')
    entity_type = entity.get('entity_type', 'unknown')
    location = entity.get('location', 'Unknown')

    # Extract location components
    location_parts = location.split(', ') if location else []
    city = location_parts[0] if len(location_parts) > 0 else 'Unknown'
    country = location_parts[-1] if len(location_parts) > 1 else 'Unknown'

    # Coordinates
    coordinates = entity.get('coordinates', {})
    lat = coordinates.get('lat')
    lon = coordinates.get('lon')

    # Consensus data
    consensus = entity.get('consensus', {})
    overall_rating = consensus.get('avg_rating')
    mention_count = consensus.get('mention_count', 0)

    # Attributes (convert list to JSON string)
    attributes = entity.get('attributes', {})
    travel_style = attributes.get('travel_style', [])
    best_for = consensus.get('best_for', [])
    not_recommended_for = consensus.get('not_recommended_for', [])

    # Build metadata
    metadata = {
        'embedding_id': f"entity_{entity_id}",
        'embedding_type': 'entity',
        'entity_id': entity_id,
        'canonical_name': canonical_name,
        'entity_type': entity_type,
        'location': location,
        'city': city,
        'country': country,
        'mention_count': mention_count,
    }

    # Optional fields
    if lat is not None:
        metadata['lat'] = float(lat)
    if lon is not None:
        metadata['lon'] = float(lon)
    if overall_rating is not None:
        metadata['overall_rating'] = float(overall_rating)

    # Arrays as JSON strings (truncated to avoid size limits)
    if travel_style:
        # Limit to top 10 items to reduce metadata size
        truncated_style = travel_style[:10] if len(travel_style) > 10 else travel_style
        metadata['travel_style'] = json.dumps(truncated_style)
    if best_for:
        # Limit to top 10 items
        truncated_best = best_for[:10] if len(best_for) > 10 else best_for
        metadata['best_for'] = json.dumps(truncated_best)
    if not_recommended_for:
        # Limit to top 10 items
        truncated_not_rec = not_recommended_for[:10] if len(not_recommended_for) > 10 else not_recommended_for
        metadata['not_recommended_for'] = json.dumps(truncated_not_rec)

    # NOTE: Removed entity_json backup field to comply with Chroma Cloud 4KB metadata limit
    # Full entity data can be retrieved from S3 if needed using entity_id

    # Validate metadata size (auto-truncate if needed)
    metadata = validate_metadata_size(metadata, entity_id=entity_id, auto_truncate=True)

    return metadata


def index_entity_embeddings(
    entities: List[Dict[str, Any]],
    chromadb_client,
    embedding_client,
    batch_size: int = 100,
    show_progress: bool = True,
    tracker = None
) -> Dict[str, Any]:
    """
    Index entity-level embeddings into ChromaDB.

    Process:
    1. Generate embedding texts for all entities
    2. Generate embeddings in batches
    3. Prepare metadata for each entity
    4. Add to entities_collection
    5. Track progress and errors

    Args:
        entities: List of canonical entity dicts from Stage 3
        chromadb_client: ChromaDBClient instance
        embedding_client: EmbeddingClient instance
        batch_size: Batch size for embedding generation (default: 100)
        show_progress: Show progress bars (default: True)
        tracker: Optional Stage4Tracker instance for metrics tracking

    Returns:
        Dict with indexing statistics:
        - total_entities: Total entities processed
        - successful: Successfully indexed
        - failed: Failed to index
        - errors: List of error messages
        - duration_seconds: Total processing time

    Example:
        >>> stats = index_entity_embeddings(entities, chromadb, embedding_client)
        >>> stats['successful']
        1536
    """
    logger.info("=" * 80)
    logger.info("🚀 INDEXING ENTITY-LEVEL EMBEDDINGS")
    logger.info("=" * 80)

    start_time = time.time()
    total_entities = len(entities)
    successful = 0
    failed = 0
    errors = []

    logger.info(f"Total entities to index: {total_entities}")
    logger.info(f"Batch size: {batch_size}")

    # Step 1: Generate embedding texts
    logger.info("\n📝 Step 1: Generating embedding texts...")
    entity_texts = batch_generate_entity_texts(entities, show_progress=show_progress)

    if not entity_texts:
        logger.error("❌ No valid embedding texts generated")
        return {
            'total_entities': total_entities,
            'successful': 0,
            'failed': total_entities,
            'errors': ['No valid embedding texts generated'],
            'duration_seconds': time.time() - start_time
        }

    logger.info(f"✅ Generated {len(entity_texts)} embedding texts")

    # Create mapping from entity_id to text
    entity_text_map = {entity_id: text for entity_id, text in entity_texts}

    # Step 2: Generate embeddings
    logger.info("\n🔢 Step 2: Generating embeddings...")

    # Prepare ordered list of texts
    ordered_entity_ids = [entity_id for entity_id, _ in entity_texts]
    ordered_texts = [text for _, text in entity_texts]

    embedding_start_time = time.time()
    try:
        # Generate all embeddings in batches
        embeddings = embedding_client.embed_batch(
            texts=ordered_texts,
            batch_size=batch_size,
            use_cache=True,
            show_progress=show_progress
        )
        embedding_duration = time.time() - embedding_start_time
        logger.info(f"✅ Generated {len(embeddings)} embeddings")

        # Track embedding generation
        if tracker:
            # Local model (gte-large) - no tokens or cost
            tracker.track_embedding_generation(
                embedding_type='entity_level',
                count=len(embeddings),
                tokens=0,  # Local model doesn't count tokens
                cost=0.0,  # FREE - local model
                duration_seconds=embedding_duration
            )

    except Exception as e:
        logger.error(f"❌ Failed to generate embeddings: {e}")
        return {
            'total_entities': total_entities,
            'successful': 0,
            'failed': total_entities,
            'errors': [f'Embedding generation failed: {e}'],
            'duration_seconds': time.time() - start_time
        }

    # Create mapping from entity_id to embedding
    entity_embedding_map = {
        entity_id: embedding
        for entity_id, embedding in zip(ordered_entity_ids, embeddings)
    }

    # Step 3: Prepare and index into ChromaDB
    logger.info("\n💾 Step 3: Indexing into ChromaDB...")

    # Get collection
    collection = chromadb_client.entities_collection

    if collection is None:
        logger.error("❌ Entities collection not initialized")
        return {
            'total_entities': total_entities,
            'successful': 0,
            'failed': total_entities,
            'errors': ['Entities collection not initialized'],
            'duration_seconds': time.time() - start_time
        }

    # Process in batches
    progress_bar = tqdm(
        total=len(entities),
        desc="Indexing entities",
        disable=not show_progress
    )

    batch_ids = []
    batch_embeddings = []
    batch_metadatas = []
    batch_documents = []

    for entity in entities:
        entity_id = entity.get('entity_id', 'unknown')

        # Skip if no text or embedding generated
        if entity_id not in entity_text_map or entity_id not in entity_embedding_map:
            failed += 1
            errors.append(f"Missing text or embedding for entity {entity_id}")
            progress_bar.update(1)
            continue

        try:
            # Get text and embedding
            text = entity_text_map[entity_id]
            embedding = entity_embedding_map[entity_id]

            # Prepare metadata
            metadata = prepare_entity_metadata(entity)

            # Add to batch
            vector_id = f"entity_{entity_id}"
            batch_ids.append(vector_id)
            batch_embeddings.append(embedding)
            batch_metadatas.append(metadata)
            batch_documents.append(text)

            # Add batch when full
            if len(batch_ids) >= batch_size:
                try:
                    collection.upsert(
                        ids=batch_ids,
                        embeddings=batch_embeddings,
                        metadatas=batch_metadatas,
                        documents=batch_documents
                    )
                    successful += len(batch_ids)
                    progress_bar.update(len(batch_ids))

                    # Clear batch
                    batch_ids = []
                    batch_embeddings = []
                    batch_metadatas = []
                    batch_documents = []

                except Exception as e:
                    logger.error(f"❌ Failed to add batch: {e}")
                    failed += len(batch_ids)
                    errors.append(f"Batch add failed: {e}")

                    # Clear batch
                    batch_ids = []
                    batch_embeddings = []
                    batch_metadatas = []
                    batch_documents = []
                    progress_bar.update(batch_size)

        except Exception as e:
            failed += 1
            errors.append(f"Failed to prepare entity {entity_id}: {e}")
            logger.error(f"❌ Failed to prepare entity {entity_id}: {e}")
            progress_bar.update(1)

    # Add remaining batch
    if batch_ids:
        try:
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents
            )
            successful += len(batch_ids)
            progress_bar.update(len(batch_ids))

        except Exception as e:
            logger.error(f"❌ Failed to upsert final batch: {e}")
            failed += len(batch_ids)
            errors.append(f"Final batch upsert failed: {e}")
            progress_bar.update(len(batch_ids))

    progress_bar.close()

    # Calculate stats
    duration = time.time() - start_time

    # Track indexing
    if tracker:
        tracker.track_indexing(
            collection='entities',
            entities_processed=total_entities,
            embeddings_created=successful,
            duration_seconds=duration
        )

    logger.info("\n" + "=" * 80)
    logger.info("📊 INDEXING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total entities: {total_entities}")
    logger.info(f"✅ Successfully indexed: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"⏱️  Duration: {duration:.2f}s")
    logger.info(f"📈 Rate: {successful / duration:.1f} entities/second")

    if errors:
        logger.warning(f"\n⚠️  {len(errors)} errors occurred")
        logger.warning("First 5 errors:")
        for error in errors[:5]:
            logger.warning(f"  - {error}")

    logger.info("=" * 80)

    return {
        'total_entities': total_entities,
        'successful': successful,
        'failed': failed,
        'errors': errors,
        'duration_seconds': duration,
        'rate_per_second': successful / duration if duration > 0 else 0
    }


def verify_indexing(
    chromadb_client,
    collection_name: str = 'entities',
    sample_size: int = 10
) -> Dict[str, Any]:
    """
    Verify indexing by querying random samples.

    Checks:
    - Collection exists and has vectors
    - Metadata is correct
    - Embeddings exist
    - Documents are stored
    - Random queries return results

    Args:
        chromadb_client: ChromaDBClient instance
        collection_name: Collection to verify (default: 'entities')
        sample_size: Number of samples to verify (default: 10)

    Returns:
        Dict with verification results:
        - collection_exists: bool
        - total_vectors: int
        - samples_verified: int
        - metadata_valid: bool
        - queries_successful: bool
        - sample_results: List of sample query results

    Example:
        >>> results = verify_indexing(chromadb, sample_size=10)
        >>> results['metadata_valid']
        True
    """
    logger.info("=" * 80)
    logger.info("🔍 VERIFYING INDEXING")
    logger.info("=" * 80)

    results = {
        'collection_exists': False,
        'total_vectors': 0,
        'samples_verified': 0,
        'metadata_valid': True,
        'queries_successful': True,
        'sample_results': []
    }

    # Get collection
    if collection_name == 'entities':
        collection = chromadb_client.entities_collection
    elif collection_name == 'profile_consensus':
        collection = chromadb_client.profile_consensus_collection
    elif collection_name == 'experiences':
        collection = chromadb_client.experiences_collection
    else:
        logger.error(f"❌ Unknown collection: {collection_name}")
        return results

    if collection is None:
        logger.error(f"❌ Collection '{collection_name}' not initialized")
        return results

    results['collection_exists'] = True

    # Get total count
    total_count = collection.count()
    results['total_vectors'] = total_count
    logger.info(f"Collection: {collection_name}")
    logger.info(f"Total vectors: {total_count:,}")

    if total_count == 0:
        logger.warning("⚠️  Collection is empty")
        return results

    # Get all IDs for sampling
    try:
        all_data = collection.get()
        all_ids = all_data['ids']
        logger.info(f"Retrieved {len(all_ids)} IDs")

    except Exception as e:
        logger.error(f"❌ Failed to retrieve IDs: {e}")
        results['queries_successful'] = False
        return results

    # Sample random IDs
    sample_ids = random.sample(all_ids, min(sample_size, len(all_ids)))
    logger.info(f"\n🎲 Verifying {len(sample_ids)} random samples...")

    for idx, vector_id in enumerate(sample_ids, 1):
        try:
            # Get by ID
            result = collection.get(ids=[vector_id], include=['embeddings', 'metadatas', 'documents'])

            # Check if result is valid (avoid array boolean evaluation)
            if result is None or 'ids' not in result:
                logger.error(f"❌ Sample {idx}: ID {vector_id} not found")
                results['metadata_valid'] = False
                continue

            try:
                ids_len = len(result['ids'])
                if ids_len == 0:
                    logger.error(f"❌ Sample {idx}: ID {vector_id} not found")
                    results['metadata_valid'] = False
                    continue
            except (TypeError, AttributeError, KeyError):
                logger.error(f"❌ Sample {idx}: Invalid result for {vector_id}")
                results['metadata_valid'] = False
                continue

            # Verify embedding exists
            embeddings = result.get('embeddings', [])
            # Check if embeddings is valid (avoid array boolean evaluation)
            if embeddings is None:
                logger.error(f"❌ Sample {idx}: No embedding for {vector_id}")
                results['metadata_valid'] = False
                continue

            try:
                embeddings_len = len(embeddings)
                if embeddings_len == 0:
                    logger.error(f"❌ Sample {idx}: No embedding for {vector_id}")
                    results['metadata_valid'] = False
                    continue
            except (TypeError, AttributeError):
                logger.error(f"❌ Sample {idx}: Invalid embeddings type for {vector_id}")
                results['metadata_valid'] = False
                continue

            embedding = embeddings[0]
            # Check if embedding is valid (not None and has content)
            if embedding is None:
                logger.error(f"❌ Sample {idx}: No embedding for {vector_id}")
                results['metadata_valid'] = False
                continue

            try:
                embedding_len = len(embedding)
                if embedding_len == 0:
                    logger.error(f"❌ Sample {idx}: Empty embedding for {vector_id}")
                    results['metadata_valid'] = False
                    continue
            except (TypeError, AttributeError):
                logger.error(f"❌ Sample {idx}: Invalid embedding type for {vector_id}")
                results['metadata_valid'] = False
                continue

            # Verify metadata exists
            metadatas = result.get('metadatas', [])
            # Check if metadatas is valid (avoid array boolean evaluation)
            if metadatas is None:
                logger.error(f"❌ Sample {idx}: No metadata for {vector_id}")
                results['metadata_valid'] = False
                continue

            try:
                metadatas_len = len(metadatas)
                if metadatas_len == 0:
                    logger.error(f"❌ Sample {idx}: No metadata for {vector_id}")
                    results['metadata_valid'] = False
                    continue
            except (TypeError, AttributeError):
                logger.error(f"❌ Sample {idx}: Invalid metadatas type for {vector_id}")
                results['metadata_valid'] = False
                continue

            metadata = metadatas[0]
            if metadata is None:
                logger.error(f"❌ Sample {idx}: No metadata for {vector_id}")
                results['metadata_valid'] = False
                continue

            # Verify document exists
            documents = result.get('documents', [])
            # Check if documents is valid (avoid numpy array boolean evaluation)
            if documents is None:
                logger.error(f"❌ Sample {idx}: No document for {vector_id}")
                results['metadata_valid'] = False
                continue

            try:
                doc_len = len(documents)
                if doc_len == 0:
                    logger.error(f"❌ Sample {idx}: No document for {vector_id}")
                    results['metadata_valid'] = False
                    continue
            except (TypeError, AttributeError):
                logger.error(f"❌ Sample {idx}: Invalid documents type for {vector_id}")
                results['metadata_valid'] = False
                continue

            document = documents[0]
            if document is None:
                logger.error(f"❌ Sample {idx}: No document for {vector_id}")
                results['metadata_valid'] = False
                continue

            # Verify metadata fields
            required_fields = ['embedding_id', 'embedding_type', 'entity_id']
            missing_fields = [f for f in required_fields if f not in metadata]

            if missing_fields:
                logger.error(f"❌ Sample {idx}: Missing metadata fields: {missing_fields}")
                results['metadata_valid'] = False
                continue

            # Log sample
            logger.info(f"\n✅ Sample {idx}: {vector_id}")
            logger.info(f"   Entity: {metadata.get('canonical_name', 'Unknown')}")
            logger.info(f"   Type: {metadata.get('entity_type', 'unknown')}")
            logger.info(f"   Location: {metadata.get('location', 'Unknown')}")
            logger.info(f"   Rating: {metadata.get('overall_rating', 'N/A')}")
            logger.info(f"   Mentions: {metadata.get('mention_count', 0)}")
            logger.info(f"   Embedding dims: {len(embedding)}")
            logger.info(f"   Document length: {len(document)} chars")

            results['samples_verified'] += 1

            # Store sample result
            results['sample_results'].append({
                'id': vector_id,
                'entity_id': metadata.get('entity_id'),
                'canonical_name': metadata.get('canonical_name'),
                'entity_type': metadata.get('entity_type'),
                'location': metadata.get('location'),
                'embedding_dims': len(embedding),
                'document_length': len(document)
            })

        except Exception as e:
            logger.error(f"❌ Sample {idx}: Verification failed: {e}")
            results['queries_successful'] = False

    # Test similarity search with existing vectors
    logger.info(f"\n🔎 Testing similarity search...")

    # Use a random vector from the collection as a test query
    try:
        if all_ids:
            test_id = random.choice(all_ids)
            test_vector_data = collection.get(ids=[test_id], include=['embeddings'])

            if (test_vector_data and 'embeddings' in test_vector_data and
                len(test_vector_data['embeddings']) > 0):
                test_embedding = test_vector_data['embeddings'][0]
                # Validate test embedding
                if test_embedding is None:
                    logger.warning(f"⚠️  Could not get valid test embedding")
                    results['queries_successful'] = False
                else:
                    try:
                        test_len = len(test_embedding)
                        if test_len == 0:
                            logger.warning(f"⚠️  Test embedding is empty")
                            results['queries_successful'] = False
                            test_embedding = None
                    except (TypeError, AttributeError):
                        logger.warning(f"⚠️  Invalid test embedding type")
                        results['queries_successful'] = False
                        test_embedding = None

                if test_embedding is not None:

                    # Query using this embedding
                    results_data = collection.query(
                        query_embeddings=[test_embedding],
                        n_results=5
                    )

                    if (results_data and 'ids' in results_data and
                        len(results_data['ids']) > 0 and len(results_data['ids'][0]) > 0):
                        num_results = len(results_data['ids'][0])
                        logger.info(f"✅ Similarity search using vector {test_id}")
                        logger.info(f"   Found {num_results} similar results")

                        # Show top 3 results
                        if 'metadatas' in results_data and len(results_data['metadatas']) > 0:
                            for i in range(min(3, num_results)):
                                metadata = results_data['metadatas'][0][i]
                                result_id = results_data['ids'][0][i]
                                logger.info(f"   {i+1}. {metadata.get('canonical_name', 'Unknown')} (ID: {result_id})")
                    else:
                        logger.warning(f"⚠️  Query returned no results")
                        results['queries_successful'] = False
    except Exception as e:
        logger.error(f"❌ Similarity search failed: {e}")
        results['queries_successful'] = False

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 VERIFICATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Collection exists: {'✅' if results['collection_exists'] else '❌'}")
    logger.info(f"Total vectors: {results['total_vectors']:,}")
    logger.info(f"Samples verified: {results['samples_verified']}/{len(sample_ids)}")
    logger.info(f"Metadata valid: {'✅' if results['metadata_valid'] else '❌'}")
    logger.info(f"Queries successful: {'✅' if results['queries_successful'] else '❌'}")
    logger.info("=" * 80)

    return results


def index_profile_consensus_embeddings(
    entities: List[Dict[str, Any]],
    chromadb_client,
    embedding_client,
    batch_size: int = 100,
    show_progress: bool = True,
    tracker = None
) -> Dict[str, Any]:
    """
    Index profile-consensus embeddings into ChromaDB.

    For each entity, creates separate embeddings for each active traveler profile
    (profiles with mention_count > 0).

    Process:
    1. Generate profile-specific embedding texts for all entities and profiles
    2. Generate embeddings in batches
    3. Prepare metadata for each profile
    4. Add to profile_consensus_collection
    5. Track progress and errors by profile type

    Args:
        entities: List of canonical entity dicts from Stage 3
        chromadb_client: ChromaDBClient instance
        embedding_client: EmbeddingClient instance
        batch_size: Batch size for embedding generation (default: 100)
        show_progress: Show progress bars (default: True)

    Returns:
        Dict with indexing statistics:
        - total_entities: Total entities processed
        - total_profiles: Total profile embeddings created
        - successful: Successfully indexed
        - failed: Failed to index
        - by_profile: Stats broken down by profile type
        - errors: List of error messages
        - duration_seconds: Total processing time

    Example:
        >>> stats = index_profile_consensus_embeddings(entities, chromadb, embedding_client)
        >>> stats['total_profiles']
        1580
    """
    logger.info("=" * 80)
    logger.info("🚀 INDEXING PROFILE-CONSENSUS EMBEDDINGS")
    logger.info("=" * 80)

    start_time = time.time()
    total_entities = len(entities)
    total_profiles = 0
    successful = 0
    failed = 0
    errors = []
    by_profile = {}  # Track stats by profile type

    logger.info(f"Total entities to process: {total_entities}")
    logger.info(f"Batch size: {batch_size}")

    # Step 1: Generate profile-specific embedding texts
    logger.info("\n📝 Step 1: Generating profile-specific embedding texts...")
    profile_texts = batch_generate_profile_consensus_texts(entities, show_progress=show_progress)

    if not profile_texts:
        logger.error("❌ No valid profile embedding texts generated")
        return {
            'total_entities': total_entities,
            'total_profiles': 0,
            'successful': 0,
            'failed': 0,
            'by_profile': {},
            'errors': ['No valid profile embedding texts generated'],
            'duration_seconds': time.time() - start_time
        }

    logger.info(f"✅ Generated {len(profile_texts)} profile-specific texts")
    total_profiles = len(profile_texts)

    # Step 2: Generate embeddings
    logger.info("\n🔢 Step 2: Generating embeddings...")

    # Prepare ordered list of texts
    ordered_keys = [(entity_id, profile_key) for entity_id, profile_key, _ in profile_texts]
    ordered_texts = [text for _, _, text in profile_texts]

    embedding_start_time = time.time()
    try:
        # Generate all embeddings in batches
        embeddings = embedding_client.embed_batch(
            texts=ordered_texts,
            batch_size=batch_size,
            use_cache=True,
            show_progress=show_progress
        )
        embedding_duration = time.time() - embedding_start_time
        logger.info(f"✅ Generated {len(embeddings)} embeddings")

        # Track embedding generation
        if tracker:
            tracker.track_embedding_generation(
                embedding_type='profile_consensus',
                count=len(embeddings),
                tokens=0,  # Local model doesn't count tokens
                cost=0.0,  # FREE - local model
                duration_seconds=embedding_duration
            )

    except Exception as e:
        logger.error(f"❌ Failed to generate embeddings: {e}")
        return {
            'total_entities': total_entities,
            'total_profiles': total_profiles,
            'successful': 0,
            'failed': total_profiles,
            'by_profile': {},
            'errors': [f'Embedding generation failed: {e}'],
            'duration_seconds': time.time() - start_time
        }

    # Create mapping from (entity_id, profile_key) to embedding and text
    profile_data_map = {
        (entity_id, profile_key): (embedding, text)
        for (entity_id, profile_key), embedding, text in zip(ordered_keys, embeddings, ordered_texts)
    }

    # Step 3: Prepare and index into ChromaDB
    logger.info("\n💾 Step 3: Indexing into ChromaDB...")

    # Get collection
    collection = chromadb_client.profile_consensus_collection

    if collection is None:
        logger.error("❌ Profile consensus collection not initialized")
        return {
            'total_entities': total_entities,
            'total_profiles': total_profiles,
            'successful': 0,
            'failed': total_profiles,
            'by_profile': {},
            'errors': ['Profile consensus collection not initialized'],
            'duration_seconds': time.time() - start_time
        }

    # Process in batches
    progress_bar = tqdm(
        total=len(entities),
        desc="Indexing profiles",
        disable=not show_progress
    )

    batch_ids = []
    batch_embeddings = []
    batch_metadatas = []
    batch_documents = []

    for entity in entities:
        entity_id = entity.get('entity_id', 'unknown')

        # Get all profiles for this entity
        consensus = entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        for profile_key, profile_data in profile_metrics.items():
            mention_count = profile_data.get('mention_count', 0)

            # Skip profiles with no mentions
            if mention_count == 0:
                continue

            # Check if we have embedding for this profile
            if (entity_id, profile_key) not in profile_data_map:
                failed += 1
                errors.append(f"Missing embedding for entity {entity_id}, profile {profile_key}")
                continue

            try:
                # Get embedding and text
                embedding, text = profile_data_map[(entity_id, profile_key)]

                # Prepare metadata
                metadata = prepare_profile_metadata(entity, profile_key, profile_data)

                # Add to batch
                vector_id = f"profile_{entity_id}_{profile_key}"
                batch_ids.append(vector_id)
                batch_embeddings.append(embedding)
                batch_metadatas.append(metadata)
                batch_documents.append(text)

                # Track by profile type
                if profile_key not in by_profile:
                    by_profile[profile_key] = {'count': 0, 'failed': 0}
                by_profile[profile_key]['count'] += 1

                # Add batch when full
                if len(batch_ids) >= batch_size:
                    try:
                        collection.upsert(
                            ids=batch_ids,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas,
                            documents=batch_documents
                        )
                        successful += len(batch_ids)

                        # Clear batch
                        batch_ids = []
                        batch_embeddings = []
                        batch_metadatas = []
                        batch_documents = []

                    except Exception as e:
                        logger.error(f"❌ Failed to upsert batch: {e}")
                        failed += len(batch_ids)
                        errors.append(f"Batch upsert failed: {e}")

                        # Update profile stats
                        for bid in batch_ids:
                            prof_key = bid.split('_')[-1]  # Extract profile from ID
                            if prof_key in by_profile:
                                by_profile[prof_key]['failed'] += 1

                        # Clear batch
                        batch_ids = []
                        batch_embeddings = []
                        batch_metadatas = []
                        batch_documents = []

            except Exception as e:
                failed += 1
                errors.append(f"Failed to prepare profile {entity_id}_{profile_key}: {e}")
                logger.error(f"❌ Failed to prepare profile {entity_id}_{profile_key}: {e}")

                if profile_key in by_profile:
                    by_profile[profile_key]['failed'] += 1

        progress_bar.update(1)

    # Add remaining batch
    if batch_ids:
        try:
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents
            )
            successful += len(batch_ids)

        except Exception as e:
            logger.error(f"❌ Failed to upsert final batch: {e}")
            failed += len(batch_ids)
            errors.append(f"Final batch upsert failed: {e}")

            # Update profile stats
            for bid in batch_ids:
                prof_key = '_'.join(bid.split('_')[2:])  # Extract profile from ID
                if prof_key in by_profile:
                    by_profile[prof_key]['failed'] += 1

    progress_bar.close()

    # Calculate stats
    duration = time.time() - start_time

    # Track indexing
    if tracker:
        tracker.track_indexing(
            collection='profile_consensus',
            entities_processed=total_entities,
            embeddings_created=successful,
            duration_seconds=duration
        )

    logger.info("\n" + "=" * 80)
    logger.info("📊 INDEXING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total entities: {total_entities}")
    logger.info(f"Total profile embeddings: {total_profiles}")
    logger.info(f"✅ Successfully indexed: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"⏱️  Duration: {duration:.2f}s")
    logger.info(f"📈 Rate: {successful / duration:.1f} profiles/second")

    # Show top profiles
    logger.info(f"\n📊 Top 10 Profile Types:")
    sorted_profiles = sorted(by_profile.items(), key=lambda x: x[1]['count'], reverse=True)
    for idx, (profile_key, stats) in enumerate(sorted_profiles[:10], 1):
        logger.info(f"  {idx}. {profile_key:40s}: {stats['count']:4d} embeddings")

    if errors:
        logger.warning(f"\n⚠️  {len(errors)} errors occurred")
        logger.warning("First 5 errors:")
        for error in errors[:5]:
            logger.warning(f"  - {error}")

    logger.info("=" * 80)

    return {
        'total_entities': total_entities,
        'total_profiles': total_profiles,
        'successful': successful,
        'failed': failed,
        'by_profile': by_profile,
        'errors': errors,
        'duration_seconds': duration,
        'rate_per_second': successful / duration if duration > 0 else 0
    }


def prepare_experience_metadata(
    entity: Dict[str, Any],
    experience: Dict[str, Any],
    experience_index: int
) -> Dict[str, Any]:
    """
    Prepare metadata for individual experience embedding.

    ChromaDB metadata requirements:
    - Values must be: str, int, float, bool (no lists/dicts)
    - Arrays must be converted to JSON strings

    Args:
        entity: Canonical entity dict from Stage 3
        experience: Individual experience dict
        experience_index: Index of this experience in the entity's experiences array

    Returns:
        Metadata dict compatible with ChromaDB

    Example:
        >>> entity = load_canonical_entity("restaurant_bangkok_001")
        >>> experience = entity['experiences'][0]
        >>> metadata = prepare_experience_metadata(entity, experience, 0)
        >>> metadata['embedding_type']
        'experience'
    """
    entity_id = entity.get('entity_id', 'unknown')
    canonical_name = entity.get('canonical_name', 'Unknown')
    entity_type = entity.get('entity_type', 'unknown')
    location = entity.get('location', 'Unknown')

    # Extract location components
    location_parts = location.split(', ') if location else []
    city = location_parts[0] if len(location_parts) > 0 else 'Unknown'
    country = location_parts[-1] if len(location_parts) > 1 else 'Unknown'

    # Coordinates
    coordinates = entity.get('coordinates', {})
    lat = coordinates.get('lat')
    lon = coordinates.get('lon')

    # Experience-specific data
    source_video_id = experience.get('source_video_id', 'unknown')
    traveler_type = experience.get('traveler_type', 'unknown')
    budget_tier = experience.get('budget_tier', 'unknown')
    travel_style = experience.get('travel_style', [])
    sentiment = experience.get('sentiment', 'neutral')
    rating = experience.get('rating')

    # Build metadata
    metadata = {
        'embedding_id': f"exp_{entity_id}_{experience_index}",
        'embedding_type': 'experience',
        'entity_id': entity_id,
        'canonical_name': canonical_name,
        'entity_type': entity_type,
        'location': location,
        'city': city,
        'country': country,
        'experience_index': experience_index,
        'source_video_id': source_video_id,
        'traveler_type': traveler_type,
        'budget_tier': budget_tier,
        'sentiment': sentiment,
    }

    # Optional fields
    if lat is not None:
        metadata['lat'] = float(lat)
    if lon is not None:
        metadata['lon'] = float(lon)
    if rating is not None:
        metadata['rating'] = int(rating)

    # Arrays as JSON strings (truncated to avoid size limits)
    if travel_style:
        # Limit to top 5 items to reduce metadata size
        truncated_style = travel_style[:5] if len(travel_style) > 5 else travel_style
        metadata['travel_style'] = json.dumps(truncated_style)

    # NOTE: Removed experience_json and entity_json backup fields to comply with Chroma Cloud 4KB metadata limit
    # Full data can be retrieved from S3 if needed using entity_id and source_video_id

    # Validate metadata size (auto-truncate if needed)
    metadata = validate_metadata_size(metadata, entity_id=f"{entity_id}_exp{experience_index}", auto_truncate=True)

    return metadata


def index_experience_embeddings(
    entities: List[Dict[str, Any]],
    chromadb_client,
    embedding_client,
    batch_size: int = 100,
    show_progress: bool = True,
    tracker = None
) -> Dict[str, Any]:
    """
    Index individual experience embeddings into ChromaDB.

    For each entity, creates separate embeddings for each individual experience.
    This is the most granular embedding strategy (Type 3).

    Process:
    1. Generate experience-specific embedding texts for all experiences
    2. Generate embeddings in batches
    3. Prepare metadata for each experience
    4. Add to experiences_collection
    5. Track progress and errors

    Args:
        entities: List of canonical entity dicts from Stage 3
        chromadb_client: ChromaDBClient instance
        embedding_client: EmbeddingClient instance
        batch_size: Batch size for embedding generation (default: 100)
        show_progress: Show progress bars (default: True)

    Returns:
        Dict with indexing statistics:
        - total_entities: Total entities processed
        - total_experiences: Total experience embeddings created
        - successful: Successfully indexed
        - failed: Failed to index
        - errors: List of error messages
        - duration_seconds: Total processing time

    Example:
        >>> stats = index_experience_embeddings(entities, chromadb, embedding_client)
        >>> stats['total_experiences']
        15234
    """
    logger.info("=" * 80)
    logger.info("🚀 INDEXING EXPERIENCE-LEVEL EMBEDDINGS")
    logger.info("=" * 80)

    start_time = time.time()
    total_entities = len(entities)
    total_experiences = 0
    successful = 0
    failed = 0
    errors = []

    logger.info(f"Total entities to process: {total_entities}")
    logger.info(f"Batch size: {batch_size}")

    # Step 1: Generate experience-specific embedding texts
    logger.info("\n📝 Step 1: Generating experience-specific embedding texts...")
    experience_texts = batch_generate_experience_texts(entities, show_progress=show_progress)

    if not experience_texts:
        logger.error("❌ No valid experience embedding texts generated")
        return {
            'total_entities': total_entities,
            'total_experiences': 0,
            'successful': 0,
            'failed': 0,
            'errors': ['No valid experience embedding texts generated'],
            'duration_seconds': time.time() - start_time
        }

    logger.info(f"✅ Generated {len(experience_texts)} experience-specific texts")
    total_experiences = len(experience_texts)

    # Step 2: Generate embeddings
    logger.info("\n🔢 Step 2: Generating embeddings...")

    # Prepare ordered list of texts
    ordered_keys = [(entity_id, exp_idx) for entity_id, exp_idx, _ in experience_texts]
    ordered_texts = [text for _, _, text in experience_texts]

    embedding_start_time = time.time()
    try:
        # Generate all embeddings in batches
        embeddings = embedding_client.embed_batch(
            texts=ordered_texts,
            batch_size=batch_size,
            use_cache=True,
            show_progress=show_progress
        )
        embedding_duration = time.time() - embedding_start_time
        logger.info(f"✅ Generated {len(embeddings)} embeddings")

        # Track embedding generation
        if tracker:
            tracker.track_embedding_generation(
                embedding_type='experiences',
                count=len(embeddings),
                tokens=0,  # Local model doesn't count tokens
                cost=0.0,  # FREE - local model
                duration_seconds=embedding_duration
            )

    except Exception as e:
        logger.error(f"❌ Failed to generate embeddings: {e}")
        return {
            'total_entities': total_entities,
            'total_experiences': total_experiences,
            'successful': 0,
            'failed': total_experiences,
            'errors': [f'Embedding generation failed: {e}'],
            'duration_seconds': time.time() - start_time
        }

    # Create mapping from (entity_id, exp_idx) to embedding and text
    experience_data_map = {
        (entity_id, exp_idx): (embedding, text)
        for (entity_id, exp_idx), embedding, text in zip(ordered_keys, embeddings, ordered_texts)
    }

    # Step 3: Prepare and index into ChromaDB
    logger.info("\n💾 Step 3: Indexing into ChromaDB...")

    # Get collection
    collection = chromadb_client.experiences_collection

    if collection is None:
        logger.error("❌ Experiences collection not initialized")
        return {
            'total_entities': total_entities,
            'total_experiences': total_experiences,
            'successful': 0,
            'failed': total_experiences,
            'errors': ['Experiences collection not initialized'],
            'duration_seconds': time.time() - start_time
        }

    # Process in batches
    progress_bar = tqdm(
        total=len(entities),
        desc="Indexing experiences",
        disable=not show_progress
    )

    batch_ids = []
    batch_embeddings = []
    batch_metadatas = []
    batch_documents = []

    for entity in entities:
        entity_id = entity.get('entity_id', 'unknown')
        experiences = entity.get('experiences', [])

        for exp_idx, experience in enumerate(experiences):
            # Check if we have embedding for this experience
            if (entity_id, exp_idx) not in experience_data_map:
                failed += 1
                errors.append(f"Missing embedding for entity {entity_id}, experience {exp_idx}")
                continue

            try:
                # Get embedding and text
                embedding, text = experience_data_map[(entity_id, exp_idx)]

                # Prepare metadata
                metadata = prepare_experience_metadata(entity, experience, exp_idx)

                # Add to batch
                vector_id = f"exp_{entity_id}_{exp_idx}"
                batch_ids.append(vector_id)
                batch_embeddings.append(embedding)
                batch_metadatas.append(metadata)
                batch_documents.append(text)

                # Add batch when full
                if len(batch_ids) >= batch_size:
                    try:
                        collection.upsert(
                            ids=batch_ids,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas,
                            documents=batch_documents
                        )
                        successful += len(batch_ids)

                        # Clear batch
                        batch_ids = []
                        batch_embeddings = []
                        batch_metadatas = []
                        batch_documents = []

                    except Exception as e:
                        logger.error(f"❌ Failed to upsert batch: {e}")
                        failed += len(batch_ids)
                        errors.append(f"Batch upsert failed: {e}")

                        # Clear batch
                        batch_ids = []
                        batch_embeddings = []
                        batch_metadatas = []
                        batch_documents = []

            except Exception as e:
                failed += 1
                errors.append(f"Failed to prepare experience {entity_id}_{exp_idx}: {e}")
                logger.error(f"❌ Failed to prepare experience {entity_id}_{exp_idx}: {e}")

        progress_bar.update(1)

    # Add remaining batch
    if batch_ids:
        try:
            collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents
            )
            successful += len(batch_ids)

        except Exception as e:
            logger.error(f"❌ Failed to upsert final batch: {e}")
            failed += len(batch_ids)
            errors.append(f"Final batch upsert failed: {e}")

    progress_bar.close()

    # Calculate stats
    duration = time.time() - start_time

    # Track indexing
    if tracker:
        tracker.track_indexing(
            collection='experiences',
            entities_processed=total_entities,
            embeddings_created=successful,
            duration_seconds=duration
        )

    logger.info("\n" + "=" * 80)
    logger.info("📊 INDEXING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total entities: {total_entities}")
    logger.info(f"Total experience embeddings: {total_experiences}")
    logger.info(f"✅ Successfully indexed: {successful}")
    logger.info(f"❌ Failed: {failed}")
    logger.info(f"⏱️  Duration: {duration:.2f}s")
    logger.info(f"📈 Rate: {successful / duration:.1f} experiences/second")

    if errors:
        logger.warning(f"\n⚠️  {len(errors)} errors occurred")
        logger.warning("First 5 errors:")
        for error in errors[:5]:
            logger.warning(f"  - {error}")

    logger.info("=" * 80)

    return {
        'total_entities': total_entities,
        'total_experiences': total_experiences,
        'successful': successful,
        'failed': failed,
        'errors': errors,
        'duration_seconds': duration,
        'rate_per_second': successful / duration if duration > 0 else 0
    }


def estimate_indexing_scope(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Estimate the scope and cost of indexing all embeddings.

    Analyzes entities to count total embeddings needed for all three strategies.
    Note: Using local gte-large model means embeddings are FREE!

    Args:
        entities: List of canonical entity dicts from Stage 3

    Returns:
        Dict with scope estimates:
        - total_entities: Number of entities
        - entity_embeddings: Entity-level embeddings (Type 1)
        - profile_embeddings: Profile-consensus embeddings (Type 2)
        - experience_embeddings: Individual experience embeddings (Type 3)
        - total_embeddings: Sum of all embeddings
        - estimated_words: Rough word count estimate
        - estimated_cost: Cost in USD (FREE for local model!)

    Example:
        >>> scope = estimate_indexing_scope(entities)
        >>> scope['total_embeddings']
        25789
    """
    logger.info("=" * 80)
    logger.info("📊 ESTIMATING INDEXING SCOPE")
    logger.info("=" * 80)

    total_entities = len(entities)
    entity_embeddings = 0
    profile_embeddings = 0
    experience_embeddings = 0
    estimated_words = 0

    # Count entity-level embeddings (Type 1)
    entity_embeddings = total_entities

    # Count profile-consensus embeddings (Type 2)
    for entity in entities:
        consensus = entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        for profile_key, profile_data in profile_metrics.items():
            mention_count = profile_data.get('mention_count', 0)
            if mention_count > 0:
                profile_embeddings += 1

    # Count experience-level embeddings (Type 3)
    for entity in entities:
        experiences = entity.get('experiences', [])
        experience_embeddings += len(experiences)

    # Calculate total
    total_embeddings = entity_embeddings + profile_embeddings + experience_embeddings

    # Estimate words (rough: ~150 words per entity, ~120 per profile, ~100 per experience)
    estimated_words = (
        entity_embeddings * 150 +
        profile_embeddings * 120 +
        experience_embeddings * 100
    )

    # Cost calculation (FREE for local model!)
    estimated_cost = 0.0  # Local gte-large model is FREE!

    # Print statistics
    logger.info(f"Total entities: {total_entities:,}")
    logger.info(f"\n📈 Embedding Breakdown:")
    logger.info(f"  Type 1 - Entity-level:      {entity_embeddings:6,} embeddings (~150 words each)")
    logger.info(f"  Type 2 - Profile-consensus: {profile_embeddings:6,} embeddings (~120 words each)")
    logger.info(f"  Type 3 - Experience-level:  {experience_embeddings:6,} embeddings (~100 words each)")
    logger.info(f"  {'─' * 65}")
    logger.info(f"  Total embeddings:           {total_embeddings:6,}")
    logger.info(f"\n💰 Cost Estimate:")
    logger.info(f"  Estimated words: ~{estimated_words:,}")
    logger.info(f"  Estimated tokens: ~{int(estimated_words * 1.3):,}")
    logger.info(f"  Model: gte-large-en-v1.5 (local)")
    logger.info(f"  Cost: $0.00 (FREE - runs locally!)")
    logger.info("=" * 80)

    return {
        'total_entities': total_entities,
        'entity_embeddings': entity_embeddings,
        'profile_embeddings': profile_embeddings,
        'experience_embeddings': experience_embeddings,
        'total_embeddings': total_embeddings,
        'estimated_words': estimated_words,
        'estimated_tokens': int(estimated_words * 1.3),
        'estimated_cost': estimated_cost,
        'model': 'gte-large-en-v1.5'
    }


def calculate_profile_distribution(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate distribution of entities across traveler profiles.

    Analyzes which traveler profiles are most/least common in the dataset.
    Useful for understanding data coverage and identifying gaps.

    Args:
        entities: List of canonical entity dicts from Stage 3

    Returns:
        Dict with profile distribution statistics:
        - total_entities: Total entities analyzed
        - total_profile_segments: Total entity-profile combinations
        - profile_counts: Dict mapping profile_key to count
        - top_profiles: Top 10 most common profiles
        - rare_profiles: Profiles with < 5 entities
        - coverage: % of entities with each profile

    Example:
        >>> dist = calculate_profile_distribution(entities)
        >>> dist['top_profiles'][0]
        ('solo_26-35_budget', 156)
    """
    logger.info("=" * 80)
    logger.info("📊 CALCULATING PROFILE DISTRIBUTION")
    logger.info("=" * 80)

    total_entities = len(entities)
    profile_counts = {}
    total_segments = 0

    for entity in entities:
        consensus = entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        for profile_key, profile_data in profile_metrics.items():
            mention_count = profile_data.get('mention_count', 0)

            # Only count profiles with actual data
            if mention_count > 0:
                if profile_key not in profile_counts:
                    profile_counts[profile_key] = 0
                profile_counts[profile_key] += 1
                total_segments += 1

    # Sort by count
    sorted_profiles = sorted(profile_counts.items(), key=lambda x: x[1], reverse=True)

    # Top profiles
    top_profiles = sorted_profiles[:10]

    # Rare profiles (< 5 entities)
    rare_profiles = [(k, v) for k, v in sorted_profiles if v < 5]

    # Calculate coverage
    coverage = {
        profile_key: (count / total_entities) * 100
        for profile_key, count in profile_counts.items()
    }

    # Print statistics
    logger.info(f"Total entities: {total_entities:,}")
    logger.info(f"Total profile segments: {total_segments:,}")
    logger.info(f"Unique profiles: {len(profile_counts)}")
    logger.info(f"Avg profiles per entity: {total_segments / total_entities:.1f}")

    logger.info(f"\n🏆 Top 10 Most Common Profiles:")
    for idx, (profile_key, count) in enumerate(top_profiles, 1):
        pct = (count / total_entities) * 100
        logger.info(f"  {idx:2d}. {profile_key:40s}: {count:4d} entities ({pct:5.1f}%)")

    if rare_profiles:
        logger.info(f"\n⚠️  Rare Profiles (< 5 entities): {len(rare_profiles)}")
        for profile_key, count in rare_profiles[:5]:
            logger.info(f"  - {profile_key:40s}: {count} entities")

    logger.info("=" * 80)

    return {
        'total_entities': total_entities,
        'total_profile_segments': total_segments,
        'unique_profiles': len(profile_counts),
        'avg_profiles_per_entity': total_segments / total_entities if total_entities > 0 else 0,
        'profile_counts': profile_counts,
        'top_profiles': top_profiles,
        'rare_profiles': rare_profiles,
        'coverage': coverage
    }


if __name__ == '__main__':
    """
    Test vector indexing with all entities.
    """
    from src.vectordb import ChromaDBClient
    from src.utils.embedding_client import EmbeddingClient
    from src.storage.s3 import S3Storage
    from src.storage.stage3_storage import Stage3Storage

    logger.info("=" * 80)
    logger.info("TESTING VECTOR INDEXING")
    logger.info("=" * 80)

    # Initialize clients
    logger.info("\n🔧 Initializing clients...")

    try:
        chromadb = ChromaDBClient.initialize_from_env()
        logger.info("✅ ChromaDB client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize ChromaDB: {e}")
        exit(1)

    try:
        embedding_client = EmbeddingClient()
        logger.info("✅ Embedding client initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize embedding client: {e}")
        exit(1)

    try:
        s3 = S3Storage()
        stage3 = Stage3Storage(s3)
        logger.info("✅ Stage 3 storage initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Stage 3 storage: {e}")
        exit(1)

    # Load all canonical entities
    logger.info("\n📥 Loading canonical entities from Stage 3...")

    try:
        all_entities = stage3.load_all_canonical_entities()
        logger.info(f"✅ Loaded {len(all_entities)} canonical entities")
    except Exception as e:
        logger.error(f"❌ Failed to load entities: {e}")
        exit(1)

    # Estimate indexing scope
    logger.info("\n" + "=" * 80)
    logger.info("ESTIMATING INDEXING SCOPE")
    logger.info("=" * 80)

    try:
        scope = estimate_indexing_scope(all_entities)
    except Exception as e:
        logger.error(f"❌ Scope estimation failed: {e}")
        import traceback
        traceback.print_exc()

    # Calculate profile distribution
    logger.info("\n" + "=" * 80)
    logger.info("ANALYZING PROFILE DISTRIBUTION")
    logger.info("=" * 80)

    try:
        distribution = calculate_profile_distribution(all_entities)
    except Exception as e:
        logger.error(f"❌ Distribution calculation failed: {e}")
        import traceback
        traceback.print_exc()

    # Index entity-level embeddings
    logger.info("\n" + "=" * 80)
    logger.info("INDEXING ENTITY-LEVEL EMBEDDINGS")
    logger.info("=" * 80)

    try:
        entity_stats = index_entity_embeddings(
            entities=all_entities,
            chromadb_client=chromadb,
            embedding_client=embedding_client,
            batch_size=100,
            show_progress=True
        )

        logger.info("\n📊 Entity-Level Statistics:")
        logger.info(f"   Total entities: {entity_stats['total_entities']}")
        logger.info(f"   ✅ Successful: {entity_stats['successful']}")
        logger.info(f"   ❌ Failed: {entity_stats['failed']}")
        logger.info(f"   ⏱️  Duration: {entity_stats['duration_seconds']:.2f}s")
        logger.info(f"   📈 Rate: {entity_stats['rate_per_second']:.1f} entities/second")

    except Exception as e:
        logger.error(f"❌ Entity indexing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Index profile-consensus embeddings
    logger.info("\n" + "=" * 80)
    logger.info("INDEXING PROFILE-CONSENSUS EMBEDDINGS")
    logger.info("=" * 80)

    try:
        profile_stats = index_profile_consensus_embeddings(
            entities=all_entities,
            chromadb_client=chromadb,
            embedding_client=embedding_client,
            batch_size=100,
            show_progress=True
        )

        logger.info("\n📊 Profile-Consensus Statistics:")
        logger.info(f"   Total entities: {profile_stats['total_entities']}")
        logger.info(f"   Total profile embeddings: {profile_stats['total_profiles']}")
        logger.info(f"   ✅ Successful: {profile_stats['successful']}")
        logger.info(f"   ❌ Failed: {profile_stats['failed']}")
        logger.info(f"   ⏱️  Duration: {profile_stats['duration_seconds']:.2f}s")
        logger.info(f"   📈 Rate: {profile_stats['rate_per_second']:.1f} profiles/second")

    except Exception as e:
        logger.error(f"❌ Profile indexing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Index experience-level embeddings
    logger.info("\n" + "=" * 80)
    logger.info("INDEXING EXPERIENCE-LEVEL EMBEDDINGS")
    logger.info("=" * 80)

    try:
        experience_stats = index_experience_embeddings(
            entities=all_entities,
            chromadb_client=chromadb,
            embedding_client=embedding_client,
            batch_size=100,
            show_progress=True
        )

        logger.info("\n📊 Experience-Level Statistics:")
        logger.info(f"   Total entities: {experience_stats['total_entities']}")
        logger.info(f"   Total experience embeddings: {experience_stats['total_experiences']}")
        logger.info(f"   ✅ Successful: {experience_stats['successful']}")
        logger.info(f"   ❌ Failed: {experience_stats['failed']}")
        logger.info(f"   ⏱️  Duration: {experience_stats['duration_seconds']:.2f}s")
        logger.info(f"   📈 Rate: {experience_stats['rate_per_second']:.1f} experiences/second")

    except Exception as e:
        logger.error(f"❌ Experience indexing failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Verify entity indexing
    logger.info("\n" + "=" * 80)
    logger.info("VERIFYING ENTITY INDEXING")
    logger.info("=" * 80)

    try:
        entity_verification = verify_indexing(
            chromadb_client=chromadb,
            collection_name='entities',
            sample_size=5
        )

        if entity_verification['metadata_valid'] and entity_verification['queries_successful']:
            logger.info("\n✅ Entity verification passed!")
        else:
            logger.warning("\n⚠️  Some entity verification checks failed")

    except Exception as e:
        logger.error(f"❌ Entity verification failed: {e}")
        import traceback
        traceback.print_exc()

    # Verify profile indexing
    logger.info("\n" + "=" * 80)
    logger.info("VERIFYING PROFILE INDEXING")
    logger.info("=" * 80)

    try:
        profile_verification = verify_indexing(
            chromadb_client=chromadb,
            collection_name='profile_consensus',
            sample_size=5
        )

        if profile_verification['metadata_valid'] and profile_verification['queries_successful']:
            logger.info("\n✅ Profile verification passed!")
        else:
            logger.warning("\n⚠️  Some profile verification checks failed")

    except Exception as e:
        logger.error(f"❌ Profile verification failed: {e}")
        import traceback
        traceback.print_exc()

    # Verify experience indexing
    logger.info("\n" + "=" * 80)
    logger.info("VERIFYING EXPERIENCE INDEXING")
    logger.info("=" * 80)

    try:
        experience_verification = verify_indexing(
            chromadb_client=chromadb,
            collection_name='experiences',
            sample_size=5
        )

        if experience_verification['metadata_valid'] and experience_verification['queries_successful']:
            logger.info("\n✅ Experience verification passed!")
        else:
            logger.warning("\n⚠️  Some experience verification checks failed")

    except Exception as e:
        logger.error(f"❌ Experience verification failed: {e}")
        import traceback
        traceback.print_exc()

    # Print final ChromaDB stats
    logger.info("\n" + "=" * 80)
    logger.info("CHROMADB FINAL STATE")
    logger.info("=" * 80)
    chromadb.print_stats()

    logger.info("\n" + "=" * 80)
    logger.info("✅ TESTING COMPLETE!")
    logger.info("=" * 80)
