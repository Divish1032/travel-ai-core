"""
Semantic Search API for TravelAI Vector Database

Provides semantic search capabilities over indexed travel entities using ChromaDB.
Supports filtering, ranking, and result explanation.

Author: TravelAI Team
Date: 2025-12-13
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.utils.logging import get_logger
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """
    Structured search result from semantic search.

    Attributes:
        entity_id: Unique entity identifier
        canonical_name: Entity name
        entity_type: Type (restaurant, attraction, etc.)
        location: Full location string
        city: City name
        country: Country name
        overall_rating: Average rating
        total_mentions: Number of mentions
        distance: Similarity distance (lower is better)
        relevance_score: Computed relevance (0-100)
        embedding_type: Type of embedding (entity, profile, experience)
        metadata: Full metadata dict
        entity_data: Full entity JSON
        explanation: Why this result matched
    """
    entity_id: str
    canonical_name: str
    entity_type: str
    location: str
    city: str
    country: str
    overall_rating: Optional[float] = None
    total_mentions: int = 0
    distance: float = 0.0
    relevance_score: float = 0.0
    embedding_type: str = 'entity'
    metadata: Dict[str, Any] = field(default_factory=dict)
    entity_data: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ''

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'entity_id': self.entity_id,
            'canonical_name': self.canonical_name,
            'entity_type': self.entity_type,
            'location': self.location,
            'city': self.city,
            'country': self.country,
            'overall_rating': self.overall_rating,
            'total_mentions': self.total_mentions,
            'distance': self.distance,
            'relevance_score': self.relevance_score,
            'embedding_type': self.embedding_type,
            'explanation': self.explanation
        }


class SemanticSearchAPI:
    """
    Semantic search API for TravelAI vector database.

    Provides methods for searching entities, profiles, and experiences
    using natural language queries with optional metadata filtering.

    Example:
        >>> api = SemanticSearchAPI()
        >>> results = api.search_entities("beach parties in Thailand", top_k=10)
        >>> for result in results:
        ...     print(f"{result.canonical_name} - {result.relevance_score:.1f}%")
    """

    def __init__(
        self,
        chromadb_client: Optional[ChromaDBClient] = None,
        embedding_client: Optional[EmbeddingClient] = None
    ):
        """
        Initialize semantic search API.

        Args:
            chromadb_client: ChromaDB client (auto-initializes if None)
            embedding_client: Embedding client (auto-initializes if None)
        """
        logger.info("Initializing SemanticSearchAPI...")

        # Initialize ChromaDB client
        if chromadb_client is None:
            self.chromadb = ChromaDBClient.initialize_from_env()
            logger.info("✅ ChromaDB client initialized from environment")
        else:
            self.chromadb = chromadb_client
            logger.info("✅ Using provided ChromaDB client")

        # Initialize embedding client
        if embedding_client is None:
            self.embedding_client = EmbeddingClient()
            logger.info("✅ Embedding client initialized")
        else:
            self.embedding_client = embedding_client
            logger.info("✅ Using provided embedding client")

        # Print collection stats
        stats = self.chromadb.get_stats()
        logger.info(f"\n📊 Vector Database Stats:")
        logger.info(f"   Entities: {stats.get('entities', 0):,} vectors")
        logger.info(f"   Profiles: {stats.get('profile_consensus', 0):,} vectors")
        logger.info(f"   Experiences: {stats.get('experiences', 0):,} vectors")
        logger.info(f"   Total: {stats.get('total', 0):,} vectors")

    def search_entities(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        min_relevance: float = 0.0
    ) -> List[SearchResult]:
        """
        Semantic search on entities collection.

        Embeds the query text and searches for similar entities in the vector database.
        Supports metadata filtering for precise results.

        Args:
            query_text: Natural language search query
            top_k: Number of results to return (default: 10)
            filters: Optional metadata filters (ChromaDB where clause)
            min_relevance: Minimum relevance score (0-100, default: 0)

        Returns:
            List of SearchResult objects, sorted by relevance

        Example:
            >>> results = api.search_entities(
            ...     "romantic restaurants in Bangkok",
            ...     top_k=5,
            ...     filters={"city": "Bangkok", "entity_type": "restaurant"}
            ... )

        Filter Examples:
            - {"city": "Bangkok", "entity_type": "restaurant"}
            - {"country": "Thailand", "overall_rating": {"$gte": 4.0}}
            - {"entity_type": {"$in": ["restaurant", "cafe"]}}
        """
        logger.info(f"\n🔍 Searching entities: '{query_text}'")
        logger.info(f"   Top K: {top_k}")
        if filters:
            logger.info(f"   Filters: {filters}")

        # Step 1: Generate embedding for query
        try:
            query_embedding = self.embedding_client.embed_text(query_text, use_cache=False)
            logger.info(f"✅ Generated query embedding ({len(query_embedding)} dims)")
        except Exception as e:
            logger.error(f"❌ Failed to generate query embedding: {e}")
            return []

        # Step 2: Query ChromaDB
        try:
            collection = self.chromadb.entities_collection

            if collection is None:
                logger.error("❌ Entities collection not initialized")
                return []

            # Build query parameters
            query_params = {
                'query_embeddings': [query_embedding],
                'n_results': top_k,
                'include': ['embeddings', 'metadatas', 'documents', 'distances']
            }

            # Add filters if provided
            if filters:
                # ChromaDB requires $and for multiple conditions
                if len(filters) > 1:
                    query_params['where'] = {'$and': [{k: v} for k, v in filters.items()]}
                else:
                    query_params['where'] = filters

            # Execute query
            raw_results = collection.query(**query_params)

            logger.info(f"✅ Query executed successfully")

        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            import traceback
            traceback.print_exc()
            return []

        # Step 3: Format results
        results = self.format_search_results(raw_results, query_text)

        # Step 4: Filter by minimum relevance
        if min_relevance > 0:
            results = [r for r in results if r.relevance_score >= min_relevance]
            logger.info(f"📊 Filtered to {len(results)} results (min relevance: {min_relevance}%)")

        logger.info(f"📊 Found {len(results)} results")

        return results

    def format_search_results(
        self,
        raw_results: Dict[str, Any],
        query_text: str = ''
    ) -> List[SearchResult]:
        """
        Format ChromaDB query results into SearchResult objects.

        Parses ChromaDB's nested result structure and calculates relevance scores.

        Args:
            raw_results: Raw results from ChromaDB query
            query_text: Original query text (for explanation)

        Returns:
            List of formatted SearchResult objects
        """
        formatted_results = []

        # ChromaDB returns results in nested lists
        if not raw_results or 'ids' not in raw_results:
            return []

        ids = raw_results['ids'][0] if raw_results['ids'] else []
        metadatas = raw_results['metadatas'][0] if 'metadatas' in raw_results else []
        documents = raw_results['documents'][0] if 'documents' in raw_results else []
        distances = raw_results['distances'][0] if 'distances' in raw_results else []

        for idx, entity_id in enumerate(ids):
            try:
                metadata = metadatas[idx] if idx < len(metadatas) else {}
                document = documents[idx] if idx < len(documents) else ''
                distance = distances[idx] if idx < len(distances) else 1.0

                # Parse entity JSON from metadata
                entity_json_str = metadata.get('entity_json', '{}')
                entity_data = json.loads(entity_json_str) if isinstance(entity_json_str, str) else entity_json_str

                # Extract key fields
                canonical_name = metadata.get('canonical_name', 'Unknown')
                entity_type = metadata.get('entity_type', 'unknown')
                location = metadata.get('location', 'Unknown')
                city = metadata.get('city', 'Unknown')
                country = metadata.get('country', 'Unknown')
                overall_rating = metadata.get('overall_rating')
                total_mentions = metadata.get('total_mentions', 0)
                embedding_type = metadata.get('embedding_type', 'entity')

                # Calculate relevance score (0-100)
                # Distance ranges from 0 (perfect match) to 2 (opposite)
                # Convert to 0-100 scale (100 = perfect match, 0 = no match)
                relevance_score = max(0, min(100, (1 - distance / 2) * 100))

                # Create search result
                result = SearchResult(
                    entity_id=entity_id,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    location=location,
                    city=city,
                    country=country,
                    overall_rating=overall_rating,
                    total_mentions=total_mentions,
                    distance=distance,
                    relevance_score=relevance_score,
                    embedding_type=embedding_type,
                    metadata=metadata,
                    entity_data=entity_data
                )

                # Generate explanation
                result.explanation = self.explain_match(result, query_text)

                formatted_results.append(result)

            except Exception as e:
                logger.error(f"❌ Failed to format result {idx}: {e}")
                continue

        return formatted_results

    def explain_match(
        self,
        result: SearchResult,
        query_text: str = ''
    ) -> str:
        """
        Generate human-readable explanation of why a result matched.

        Analyzes the result's metadata and similarity score to create
        an explanation of the match quality.

        Args:
            result: SearchResult to explain
            query_text: Original query text

        Returns:
            Human-readable explanation string

        Example:
            >>> explanation = api.explain_match(result, "beach parties")
            >>> print(explanation)
            "High relevance (87.3%). Popular attraction in Phuket with 12 mentions
            and 4.5★ rating. Known for vibrant nightlife and beach activities."
        """
        parts = []

        # Relevance score
        if result.relevance_score >= 80:
            parts.append(f"High relevance ({result.relevance_score:.1f}%)")
        elif result.relevance_score >= 60:
            parts.append(f"Good match ({result.relevance_score:.1f}%)")
        elif result.relevance_score >= 40:
            parts.append(f"Moderate match ({result.relevance_score:.1f}%)")
        else:
            parts.append(f"Low relevance ({result.relevance_score:.1f}%)")

        # Entity type
        type_descriptions = {
            'restaurant': 'dining venue',
            'attraction': 'attraction',
            'activity': 'activity',
            'destination': 'destination',
            'shopping': 'shopping location',
            'hotel': 'accommodation'
        }
        type_desc = type_descriptions.get(result.entity_type, result.entity_type)
        parts.append(type_desc)

        # Location
        parts.append(f"in {result.city}")

        # Mentions
        if result.total_mentions > 0:
            if result.total_mentions >= 10:
                parts.append(f"with {result.total_mentions} mentions")
            elif result.total_mentions >= 5:
                parts.append(f"with {result.total_mentions} mentions")
            else:
                parts.append(f"({result.total_mentions} mention{'s' if result.total_mentions > 1 else ''})")

        # Rating
        if result.overall_rating and result.overall_rating > 0:
            stars = '★' * int(result.overall_rating)
            parts.append(f"rated {result.overall_rating:.1f}{stars}")

        # Combine parts
        explanation = '. '.join(parts[:3])  # First 3 parts as main sentence
        if len(parts) > 3:
            explanation += '. ' + ', '.join(parts[3:])  # Rest as additional info

        return explanation + '.'

    def search_by_profile(
        self,
        query_text: str,
        traveler_profile: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search profile-consensus embeddings for a specific traveler profile.

        Args:
            query_text: Natural language search query
            traveler_profile: Traveler profile key (e.g., "couple_26-35_mid-range")
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of SearchResult objects for the specified profile

        Example:
            >>> results = api.search_by_profile(
            ...     "romantic dinner spots",
            ...     traveler_profile="couple_26-35_mid-range",
            ...     top_k=5
            ... )
        """
        logger.info(f"\n🔍 Profile search: '{query_text}' for {traveler_profile}")

        # Generate query embedding
        try:
            query_embedding = self.embedding_client.embed_text(query_text, use_cache=False)
        except Exception as e:
            logger.error(f"❌ Failed to generate query embedding: {e}")
            return []

        # Query profile collection
        try:
            collection = self.chromadb.profile_consensus_collection

            if collection is None:
                logger.error("❌ Profile consensus collection not initialized")
                return []

            # Build filters
            where_clause = {'traveler_profile': traveler_profile}
            if filters:
                where_clause.update(filters)

            # Execute query
            raw_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause,
                include=['embeddings', 'metadatas', 'documents', 'distances']
            )

            logger.info(f"✅ Profile query executed")

        except Exception as e:
            logger.error(f"❌ Profile query failed: {e}")
            return []

        # Format results
        results = self.format_search_results(raw_results, query_text)
        logger.info(f"📊 Found {len(results)} profile-specific results")

        return results

    def search_experiences(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Search individual experience embeddings.

        Searches the most granular level - individual traveler experiences.
        Useful for finding specific stories and detailed accounts.

        Args:
            query_text: Natural language search query
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of SearchResult objects for individual experiences

        Example:
            >>> results = api.search_experiences(
            ...     "disappointing hotel experience",
            ...     filters={"sentiment": "negative"}
            ... )
        """
        logger.info(f"\n🔍 Experience search: '{query_text}'")

        # Generate query embedding
        try:
            query_embedding = self.embedding_client.embed_text(query_text, use_cache=False)
        except Exception as e:
            logger.error(f"❌ Failed to generate query embedding: {e}")
            return []

        # Query experiences collection
        try:
            collection = self.chromadb.experiences_collection

            if collection is None:
                logger.error("❌ Experiences collection not initialized")
                return []

            # Build query parameters
            query_params = {
                'query_embeddings': [query_embedding],
                'n_results': top_k,
                'include': ['embeddings', 'metadatas', 'documents', 'distances']
            }

            if filters:
                query_params['where'] = filters

            # Execute query
            raw_results = collection.query(**query_params)

            logger.info(f"✅ Experience query executed")

        except Exception as e:
            logger.error(f"❌ Experience query failed: {e}")
            return []

        # Format results
        results = self.format_search_results(raw_results, query_text)
        logger.info(f"📊 Found {len(results)} experience results")

        return results

    def print_results(
        self,
        results: List[SearchResult],
        show_explanation: bool = True,
        max_results: Optional[int] = None
    ):
        """
        Pretty print search results.

        Args:
            results: List of SearchResult objects
            show_explanation: Show match explanations (default: True)
            max_results: Maximum number of results to print (default: all)
        """
        if not results:
            logger.info("📭 No results found")
            return

        display_results = results[:max_results] if max_results else results

        logger.info(f"\n{'=' * 80}")
        logger.info(f"📊 SEARCH RESULTS ({len(results)} total)")
        logger.info(f"{'=' * 80}\n")

        for idx, result in enumerate(display_results, 1):
            logger.info(f"{idx}. {result.canonical_name}")
            logger.info(f"   Type: {result.entity_type.title()}")
            logger.info(f"   Location: {result.location}")
            logger.info(f"   Relevance: {result.relevance_score:.1f}%")

            if result.overall_rating:
                logger.info(f"   Rating: {result.overall_rating:.1f}★")

            if result.total_mentions > 0:
                logger.info(f"   Mentions: {result.total_mentions}")

            if show_explanation:
                logger.info(f"   💡 {result.explanation}")

            logger.info("")  # Blank line


if __name__ == '__main__':
    """
    Test semantic search with various queries.
    """
    logger.info("=" * 80)
    logger.info("TESTING SEMANTIC SEARCH API")
    logger.info("=" * 80)

    # Initialize API
    try:
        api = SemanticSearchAPI()
    except Exception as e:
        logger.error(f"❌ Failed to initialize API: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

    # Test queries
    test_queries = [
        {
            'query': "beach parties in Thailand",
            'filters': None,
            'description': "General search for beach party spots"
        },
        {
            'query': "romantic restaurants in Bangkok",
            'filters': {"city": "Bangkok", "entity_type": "restaurant"},
            'description': "Filtered search for Bangkok restaurants"
        },
        {
            'query': "budget hostels for backpackers",
            'filters': None,
            'description': "Budget accommodation search"
        },
        {
            'query': "temples and cultural sites",
            'filters': {"entity_type": "attraction"},
            'description': "Cultural attractions search"
        }
    ]

    # Run test queries
    for idx, test in enumerate(test_queries, 1):
        logger.info("\n" + "=" * 80)
        logger.info(f"TEST {idx}: {test['description']}")
        logger.info("=" * 80)
        logger.info(f"Query: '{test['query']}'")
        if test['filters']:
            logger.info(f"Filters: {test['filters']}")

        try:
            results = api.search_entities(
                query_text=test['query'],
                top_k=5,
                filters=test['filters']
            )

            api.print_results(results, show_explanation=True, max_results=5)

        except Exception as e:
            logger.error(f"❌ Test {idx} failed: {e}")
            import traceback
            traceback.print_exc()

    logger.info("\n" + "=" * 80)
    logger.info("✅ TESTING COMPLETE!")
    logger.info("=" * 80)
