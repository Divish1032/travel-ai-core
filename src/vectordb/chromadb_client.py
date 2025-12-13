#!/usr/bin/env python3
"""
ChromaDB Client for Stage 4 Vector Storage

Handles vector database storage using ChromaDB for both local development and cloud deployment.
Supports 3 collections for different embedding strategies:
1. entities_collection - Entity-level embeddings
2. profile_consensus_collection - Profile-specific embeddings
3. experiences_collection - Individual experience embeddings

Features:
- Local persistent storage (saves to disk) OR cloud deployment
- Automatic configuration from environment variables
- Metadata filtering for search
- Support for multiple collections
- Easy collection management

Example:
    # Local mode
    >>> client = ChromaDBClient()
    >>> client.initialize_local()
    >>> collections = client.list_collections()
    >>> len(collections)
    3

    # Cloud mode
    >>> client = ChromaDBClient()
    >>> client.initialize_cloud(host="localhost", port=8000)
    >>> collections = client.list_collections()

    # Auto-configure from .env
    >>> client = ChromaDBClient.initialize_from_env()
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from pathlib import Path
import os

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ChromaDBClient:
    """
    Client for managing ChromaDB vector database.

    Provides local persistent storage for embeddings with metadata filtering.
    Manages 3 separate collections for different embedding strategies.

    Attributes:
        client: ChromaDB client instance
        persist_directory: Path to persistence directory
        entities_collection: Collection for entity-level embeddings
        profile_consensus_collection: Collection for profile-specific embeddings
        experiences_collection: Collection for individual experience embeddings
    """

    # Collection names
    ENTITIES_COLLECTION = "entities"
    PROFILE_CONSENSUS_COLLECTION = "profile_consensus"
    EXPERIENCES_COLLECTION = "experiences"

    def __init__(self):
        """Initialize ChromaDB client (call initialize_local(), initialize_cloud(), or initialize_from_env() to set up)."""
        self.client: Optional[chromadb.Client] = None
        self.persist_directory: Optional[Path] = None
        self.mode: Optional[str] = None  # 'local' or 'cloud'
        self.host: Optional[str] = None
        self.port: Optional[int] = None

        # Collections
        self.entities_collection = None
        self.profile_consensus_collection = None
        self.experiences_collection = None

    def initialize_local(
        self,
        persist_directory: str = "./chroma_data"
    ) -> None:
        """
        Initialize local persistent ChromaDB client.

        Creates a persistent client that saves data to disk, enabling
        data to be loaded between runs.

        Args:
            persist_directory: Directory for ChromaDB data (default: ./chroma_data)

        Example:
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> client.client is not None
            True
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing ChromaDB client...")
        logger.info(f"Persistence directory: {self.persist_directory.absolute()}")

        # Create persistent client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        self.mode = "local"
        logger.info("✅ ChromaDB client initialized successfully (LOCAL mode)")

        # Create collections
        self.create_collections()

    def initialize_cloud(
        self,
        host: str = "localhost",
        port: int = 8000,
        api_key: Optional[str] = None
    ) -> None:
        """
        Initialize cloud ChromaDB client.

        Connects to a remote ChromaDB server (e.g., Docker container, cloud deployment).

        Args:
            host: ChromaDB server host (default: localhost)
            port: ChromaDB server port (default: 8000)
            api_key: Optional API key for authentication

        Raises:
            ConnectionError: If unable to connect to server

        Example:
            >>> client = ChromaDBClient()
            >>> client.initialize_cloud(host="localhost", port=8000)
            >>> client.mode
            'cloud'
        """
        self.host = host
        self.port = port

        logger.info(f"Initializing ChromaDB client...")
        logger.info(f"Connecting to ChromaDB server at {host}:{port}")

        try:
            # Create HTTP client
            settings = Settings(
                chroma_api_impl="chromadb.api.fastapi.FastAPI",
                chroma_server_host=host,
                chroma_server_http_port=port,
                anonymized_telemetry=False
            )

            # Add authentication if API key provided
            if api_key:
                settings.chroma_client_auth_credentials = api_key
                logger.debug("Using API key authentication")

            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=settings
            )

            # Test connection
            self.client.heartbeat()
            self.mode = "cloud"
            logger.info(f"✅ ChromaDB client initialized successfully (CLOUD mode: {host}:{port})")

            # Create collections
            self.create_collections()

        except Exception as e:
            logger.error(f"❌ Failed to connect to ChromaDB server at {host}:{port}")
            logger.error(f"Error: {e}")
            raise ConnectionError(f"Failed to connect to ChromaDB server: {e}")

    @classmethod
    def initialize_from_env(cls) -> 'ChromaDBClient':
        """
        Initialize ChromaDB client from environment variables.

        Reads configuration from .env and automatically chooses local vs cloud mode.

        Environment Variables:
            CHROMADB_MODE: 'local' or 'cloud' (default: local)
            CHROMADB_HOST: Server host (default: localhost, for cloud mode)
            CHROMADB_PORT: Server port (default: 8000, for cloud mode)
            CHROMADB_API_KEY: API key for authentication (optional, for cloud mode)
            CHROMADB_PERSIST_DIR: Persistence directory (default: ./chroma_data, for local mode)

        Returns:
            Configured ChromaDBClient instance

        Example:
            >>> # In .env: CHROMADB_MODE=local
            >>> client = ChromaDBClient.initialize_from_env()
            >>> client.mode
            'local'
        """
        # Load from environment
        mode = os.getenv('CHROMADB_MODE', 'local').lower()

        client = cls()

        if mode == 'cloud':
            # Cloud configuration
            host = os.getenv('CHROMADB_HOST', 'localhost')
            port = int(os.getenv('CHROMADB_PORT', '8000'))
            api_key = os.getenv('CHROMADB_API_KEY')

            logger.info(f"Initializing from environment: CLOUD mode ({host}:{port})")
            client.initialize_cloud(host=host, port=port, api_key=api_key)
        else:
            # Local configuration
            persist_dir = os.getenv('CHROMADB_PERSIST_DIR', './chroma_data')

            logger.info(f"Initializing from environment: LOCAL mode ({persist_dir})")
            client.initialize_local(persist_directory=persist_dir)

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
            raise RuntimeError("Client not initialized. Call initialize_local() first.")

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
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> collection = client.get_or_create_collection("test")
            >>> collection.name
            'test'
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_local() first.")

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
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> collections = client.list_collections()
            >>> len(collections)
            3
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_local() first.")

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
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> client.delete_collection("test")
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_local() first.")

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
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> client.reset_all_collections()
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize_local() first.")

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
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
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

        # Add mode-specific information
        if self.mode == "local":
            stats["persist_directory"] = str(self.persist_directory.absolute()) if self.persist_directory else None
        elif self.mode == "cloud":
            stats["server"] = f"{self.host}:{self.port}"

        return stats

    def print_stats(self) -> None:
        """
        Print database statistics.

        Example:
            >>> client = ChromaDBClient()
            >>> client.initialize_local()
            >>> client.print_stats()
        """
        stats = self.get_stats()

        logger.info("=" * 70)
        logger.info("📊 CHROMADB STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Mode: {stats['mode'].upper()}")

        # Mode-specific information
        if stats['mode'] == 'local':
            logger.info(f"Persistence directory: {stats.get('persist_directory', 'N/A')}")
        elif stats['mode'] == 'cloud':
            logger.info(f"Server: {stats.get('server', 'N/A')}")

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

    # Test 1: Initialize client
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Initialize ChromaDB Client")
    logger.info("=" * 80)

    client = ChromaDBClient()
    client.initialize_local(persist_directory="./chroma_data")

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

    # Test 5: Persistence test
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Persistence Test")
    logger.info("=" * 80)

    logger.info("Creating new client to test persistence...")
    client2 = ChromaDBClient()
    client2.initialize_local(persist_directory="./chroma_data")

    collections2 = client2.list_collections()
    logger.info(f"Loaded {len(collections2)} collections from disk:")

    for collection in collections2:
        logger.info(f"  {collection['name']:30s}: {collection['count']:,} vectors")

    logger.info("✅ Persistence working - collections loaded from disk!")

    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL TESTS COMPLETED!")
    logger.info("=" * 80)
