#!/usr/bin/env python3
"""
ChromaDB Client for Stage 4 Vector Storage

Handles vector database storage using Chroma Cloud (www.trychroma.com).
Supports 4 collections for different embedding strategies:
1. entities_collection - Entity-level embeddings (Tier 2)
2. profile_consensus_collection - Profile-specific embeddings
3. experiences_collection - Individual experience embeddings
4. city_destinations_collection - City-level embeddings (Tier 1, NEW)

Features:
- Chroma Cloud hosted service
- Automatic configuration from environment variables
- Metadata filtering for search
- Support for multiple collections
- Easy collection management
- Two-tier retrieval: Cities (Tier 1) → Entities (Tier 2)

Example:
    # Initialize from .env
    >>> client = ChromaDBClient.initialize_from_env()
    >>> collections = client.list_collections()
    >>> len(collections)
    3

    # Or initialize directly
    >>> client = ChromaDBClient()
    >>> client.initialize_cloud(
    ...     tenant="my-tenant",
    ...     database="my-database",
    ...     api_key="sk-..."
    ... )
"""

import chromadb
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

from src.utils.logging import get_logger

# Load .env file for environment variables
load_dotenv()

logger = get_logger(__name__)


class ChromaDBClient:
    """
    Client for managing ChromaDB vector database on Chroma Cloud.

    Connects to Chroma Cloud hosted service for vector storage with metadata filtering.
    Manages 4 separate collections for different embedding strategies.

    Attributes:
        client: ChromaDB CloudClient instance
        mode: Always 'cloud' for Chroma Cloud
        entities_collection: Collection for entity-level embeddings (Tier 2)
        profile_consensus_collection: Collection for profile-specific embeddings
        experiences_collection: Collection for individual experience embeddings
        city_destinations_collection: Collection for city-level embeddings (Tier 1)
    """

    # Collection names
    ENTITIES_COLLECTION = "entities"
    PROFILE_CONSENSUS_COLLECTION = "profile_consensus"
    EXPERIENCES_COLLECTION = "experiences"
    CITY_DESTINATIONS_COLLECTION = "city_destinations"

    def __init__(self):
        """Initialize ChromaDB client (call initialize_cloud() or initialize_from_env() to set up)."""
        self.client: Optional[chromadb.Client] = None
        self.mode: Optional[str] = None  # Always 'cloud'

        # Collections
        self.entities_collection = None
        self.profile_consensus_collection = None
        self.experiences_collection = None
        self.city_destinations_collection = None

    def initialize_cloud(
        self,
        tenant: Optional[str] = None,
        database: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> None:
        """
        Initialize Chroma Cloud client (www.trychroma.com).

        Connects to Chroma Cloud hosted service using tenant, database, and API key.

        Args:
            tenant: Chroma Cloud tenant ID
            database: Chroma Cloud database name (default: default_database)
            api_key: Chroma Cloud API key (required)

        Raises:
            ValueError: If API key is missing
            ConnectionError: If unable to connect to Chroma Cloud

        Example:
            >>> client = ChromaDBClient()
            >>> client.initialize_cloud(
            ...     tenant="my-tenant",
            ...     database="my-database",
            ...     api_key="sk-..."
            ... )
            >>> client.mode
            'cloud'
        """
        if not api_key:
            raise ValueError("API key is required for Chroma Cloud connection")

        if not tenant:
            raise ValueError("Tenant ID is required for Chroma Cloud connection")

        # Default database if not specified
        if not database:
            database = "default_database"

        logger.info(f"Initializing ChromaDB client...")
        logger.info(f"Connecting to Chroma Cloud (tenant: {tenant}, database: {database})")

        try:
            # Create Chroma Cloud client
            self.client = chromadb.CloudClient(
                tenant=tenant,
                database=database,
                api_key=api_key
            )

            # Test connection
            self.client.heartbeat()
            self.mode = "cloud"
            logger.info(f"✅ ChromaDB client initialized successfully (CHROMA CLOUD: {tenant}/{database})")

            # Create collections
            self.create_collections()

        except Exception as e:
            logger.error(f"❌ Failed to connect to Chroma Cloud")
            logger.error(f"Error: {e}")
            raise ConnectionError(f"Failed to connect to Chroma Cloud: {e}")

    @classmethod
    def initialize_from_env(cls) -> 'ChromaDBClient':
        """
        Initialize ChromaDB client from environment variables.

        Reads Chroma Cloud configuration from .env file.

        Environment Variables:
            CHROMADB_TENANT: Chroma Cloud tenant ID (required)
            CHROMADB_DATABASE: Chroma Cloud database name (default: default_database)
            CHROMADB_API_KEY: API key for authentication (required)

        Returns:
            Configured ChromaDBClient instance

        Example:
            >>> # In .env with Chroma Cloud credentials
            >>> client = ChromaDBClient.initialize_from_env()
            >>> client.mode
            'cloud'
        """
        # Chroma Cloud configuration (www.trychroma.com)
        tenant = os.getenv('CHROMADB_TENANT')
        database = os.getenv('CHROMADB_DATABASE', 'default_database')
        api_key = os.getenv('CHROMADB_API_KEY')

        client = cls()
        logger.info(f"Initializing from environment: Chroma Cloud ({tenant}/{database})")
        client.initialize_cloud(tenant=tenant, database=database, api_key=api_key)

        return client

    def create_collections(self) -> None:
        """
        Create all 3 collections with appropriate metadata schemas.

        Collections:
        1. entities - Entity-level embeddings (Type 1)
        2. profile_consensus - Profile-specific embeddings (Type 2)
        3. experiences - Individual experience embeddings (Type 3)

        Each collection has its own metadata schema optimized for filtering.
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_cloud() or initialize_from_env() first.")

        logger.info("Creating/loading collections...")

        # 1. Entities Collection (Type 1: Entity-level)
        self.entities_collection = self.get_or_create_collection(
            name=self.ENTITIES_COLLECTION,
            metadata_schema={
                # Entity identity
                "entity_id": "string",
                "entity_type": "string",  # restaurant, hotel, attraction, etc.
                "canonical_name": "string",

                # Location
                "city": "string",
                "country": "string",
                "normalized_location": "string",
                "latitude": "float",
                "longitude": "float",

                # Consensus metrics
                "mention_count": "int",
                "avg_rating": "float",
                "sentiment_score": "float",

                # Attributes
                "cost_tier": "string",  # free, budget, mid-range, luxury
                "themes": "string",  # Comma-separated for filtering

                # Metadata
                "created_at": "string"
            }
        )
        logger.info(f"   ✅ {self.ENTITIES_COLLECTION}: {self.entities_collection.count()} vectors")

        # 2. Profile Consensus Collection (Type 2: Profile-specific)
        self.profile_consensus_collection = self.get_or_create_collection(
            name=self.PROFILE_CONSENSUS_COLLECTION,
            metadata_schema={
                # Entity identity
                "entity_id": "string",
                "entity_type": "string",
                "canonical_name": "string",

                # Location
                "city": "string",
                "country": "string",
                "normalized_location": "string",
                "latitude": "float",
                "longitude": "float",

                # Profile information
                "profile_key": "string",  # e.g., couple_26-35_mid-range
                "traveler_type": "string",  # couple, solo, family, etc.
                "age_range": "string",  # 18-25, 26-35, etc.
                "budget_tier": "string",  # budget, mid-range, luxury

                # Profile-specific metrics
                "profile_mention_count": "int",
                "profile_avg_rating": "float",
                "profile_sentiment_score": "float",

                # Attributes
                "cost_tier": "string",
                "themes": "string",

                # Metadata
                "created_at": "string"
            }
        )
        logger.info(f"   ✅ {self.PROFILE_CONSENSUS_COLLECTION}: {self.profile_consensus_collection.count()} vectors")

        # 3. Experiences Collection (Type 3: Individual experiences)
        self.experiences_collection = self.get_or_create_collection(
            name=self.EXPERIENCES_COLLECTION,
            metadata_schema={
                # Entity identity
                "entity_id": "string",
                "entity_type": "string",
                "canonical_name": "string",

                # Location
                "city": "string",
                "country": "string",
                "normalized_location": "string",
                "latitude": "float",
                "longitude": "float",

                # Experience details
                "experience_index": "int",
                "source_video_id": "string",

                # Traveler profile
                "traveler_type": "string",
                "age_range": "string",
                "budget_tier": "string",
                "travel_style": "string",  # Comma-separated

                # Experience metrics
                "sentiment": "string",  # positive, negative, neutral, mixed
                "confidence_score": "float",
                "cost_mentioned": "string",

                # Attributes
                "cost_tier": "string",
                "themes": "string",
                "language": "string",

                # Metadata
                "timestamp_start": "float",
                "created_at": "string"
            }
        )
        logger.info(f"   ✅ {self.EXPERIENCES_COLLECTION}: {self.experiences_collection.count()} vectors")

        # 4. City Destinations Collection (NEW: Tier 1 for multi-day trips)
        self.city_destinations_collection = self.get_or_create_collection(
            name=self.CITY_DESTINATIONS_COLLECTION,
            metadata_schema={
                # City identity
                "city_id": "string",
                "city": "string",
                "country": "string",

                # Entity counts
                "entity_count": "int",
                "restaurant_count": "int",
                "attraction_count": "int",
                "hotel_count": "int",
                "activity_count": "int",

                # Budget profile
                "dominant_budget": "string",  # budget, mid-range, luxury
                "budget_pct": "float",
                "midrange_pct": "float",
                "luxury_pct": "float",

                # Quality
                "avg_rating": "float",

                # Temporal
                "best_seasons": "string",  # Comma-separated months

                # Location
                "lat": "float",
                "lon": "float",

                # Recommendations
                "recommended_days": "string"  # e.g., "3-4"
            }
        )
        logger.info(f"   ✅ {self.CITY_DESTINATIONS_COLLECTION}: {self.city_destinations_collection.count()} vectors")

        logger.info("✅ All collections created/loaded successfully")

    def get_or_create_collection(
        self,
        name: str,
        metadata_schema: Optional[Dict[str, str]] = None
    ) -> chromadb.Collection:
        """
        Get existing collection or create new one.

        Args:
            name: Collection name
            metadata_schema: Optional metadata schema for filtering

        Returns:
            Collection object

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> collection = client.get_or_create_collection("test")
            >>> collection.name
            'test'
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_cloud() or initialize_from_env() first.")

        try:
            # Try to get existing collection
            collection = self.client.get_collection(name=name)
            logger.debug(f"Loaded existing collection: {name}")
        except Exception:
            # Create new collection
            collection = self.client.create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}  # Use cosine similarity
            )
            logger.debug(f"Created new collection: {name}")

        return collection

    def list_collections(self) -> List[Dict[str, Any]]:
        """
        List all collections with their stats.

        Returns:
            List of dicts with collection info:
            [{"name": str, "count": int}, ...]

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> collections = client.list_collections()
            >>> len(collections)
            3
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_cloud() or initialize_from_env() first.")

        collections = []

        for collection in self.client.list_collections():
            collections.append({
                "name": collection.name,
                "count": collection.count()
            })

        return collections

    def delete_collection(self, name: str) -> None:
        """
        Delete a collection.

        Args:
            name: Collection name to delete

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> client.delete_collection("test")
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_cloud() or initialize_from_env() first.")

        try:
            self.client.delete_collection(name=name)
            logger.info(f"Deleted collection: {name}")
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")

    def reset_all_collections(self) -> None:
        """
        Delete all collections and recreate them.

        Warning: This deletes all data!

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> client.reset_all_collections()
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_cloud() or initialize_from_env() first.")

        logger.warning("Resetting all collections (deleting all data)...")

        # Delete all collections
        for collection_name in [
            self.ENTITIES_COLLECTION,
            self.PROFILE_CONSENSUS_COLLECTION,
            self.EXPERIENCES_COLLECTION
        ]:
            self.delete_collection(collection_name)

        # Recreate collections
        self.create_collections()

        logger.info("✅ All collections reset")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dict with stats for all collections

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> stats = client.get_stats()
            >>> stats['total_vectors']
            0
        """
        if not self.client:
            raise RuntimeError("Client not initialized.")

        entities_count = self.entities_collection.count() if self.entities_collection else 0
        profiles_count = self.profile_consensus_collection.count() if self.profile_consensus_collection else 0
        experiences_count = self.experiences_collection.count() if self.experiences_collection else 0

        stats = {
            "mode": self.mode,
            "collections": {
                self.ENTITIES_COLLECTION: entities_count,
                self.PROFILE_CONSENSUS_COLLECTION: profiles_count,
                self.EXPERIENCES_COLLECTION: experiences_count
            },
            "total_vectors": entities_count + profiles_count + experiences_count
        }

        return stats

    def print_stats(self) -> None:
        """
        Print database statistics.

        Example:
            >>> client = ChromaDBClient.initialize_from_env()
            >>> client.print_stats()
        """
        stats = self.get_stats()

        logger.info("=" * 70)
        logger.info("📊 CHROMADB STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Mode: CHROMA CLOUD")

        logger.info(f"\nCollections:")

        for collection_name, count in stats['collections'].items():
            logger.info(f"  {collection_name:30s}: {count:,} vectors")

        logger.info(f"\nTotal vectors: {stats['total_vectors']:,}")
        logger.info("=" * 70)


if __name__ == '__main__':
    """
    Test ChromaDB client initialization and collection management.
    """
    logger.info("=" * 80)
    logger.info("TESTING CHROMADB CLIENT")
    logger.info("=" * 80)

    # Test 1: Initialize client from environment
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Initialize ChromaDB Client from Environment")
    logger.info("=" * 80)

    client = ChromaDBClient.initialize_from_env()

    # Test 2: List collections
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: List Collections")
    logger.info("=" * 80)

    collections = client.list_collections()
    logger.info(f"Found {len(collections)} collections:")

    for collection in collections:
        logger.info(f"  {collection['name']:30s}: {collection['count']:,} vectors")

    # Test 3: Get stats
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Database Statistics")
    logger.info("=" * 80)

    client.print_stats()

    # Test 4: Test collection access
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Collection Access")
    logger.info("=" * 80)

    logger.info(f"Entities collection: {client.entities_collection.name}")
    logger.info(f"  Count: {client.entities_collection.count()}")

    logger.info(f"Profile consensus collection: {client.profile_consensus_collection.name}")
    logger.info(f"  Count: {client.profile_consensus_collection.count()}")

    logger.info(f"Experiences collection: {client.experiences_collection.name}")
    logger.info(f"  Count: {client.experiences_collection.count()}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL TESTS COMPLETED!")
    logger.info("=" * 80)
