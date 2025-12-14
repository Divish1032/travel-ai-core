#!/usr/bin/env python3
"""
Stage 4: Vector Indexing Processor

Generates and indexes embeddings for canonical entities into ChromaDB.
Supports three embedding strategies:
1. Entity-level embeddings (Type 1) - One embedding per entity
2. Profile-consensus embeddings (Type 2) - One embedding per entity-profile combination
3. Experience-level embeddings (Type 3) - One embedding per individual experience

Usage:
    python cli/process_stage4.py --embedding-types all
    python cli/process_stage4.py --embedding-types entity --limit 10
    python cli/process_stage4.py --embedding-types profile,experience

    # Via crawl.sh
    ./crawl.sh process-stage4 --embedding-types all
    ./crawl.sh process-stage4 --embedding-types entity --limit 10

Features:
- Cost estimation before indexing (FREE for local model!)
- Batch processing for efficiency
- Progress tracking with detailed statistics
- Verification of indexed embeddings
- Metadata tracking and persistence
- Retry logic for transient failures

Environment Variables:
    CHROMADB_MODE: 'local' or 'cloud' (default: local)
    CHROMADB_PERSIST_DIR: Local ChromaDB directory (default: ./chroma_data)
    CHROMADB_HOST: Cloud ChromaDB host (for cloud mode)
    CHROMADB_PORT: Cloud ChromaDB port (for cloud mode)
    EMBEDDING_MODEL: Model to use (default: gte-large)
"""

import click
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import sys
import time

from src.utils.logging import get_logger
from src.storage.s3 import S3Storage
from src.storage.stage3_storage import Stage3Storage
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.utils.metadata_tracker import MetadataTracker
from src.utils.stage4_tracker import Stage4Tracker
from src.processors.vector_indexer import (
    index_entity_embeddings,
    index_profile_consensus_embeddings,
    index_experience_embeddings,
    estimate_indexing_scope,
    verify_indexing
)

logger = get_logger(__name__)


class Stage4Processor:
    """Orchestrates Stage 4 vector indexing process."""

    def __init__(
        self,
        s3_storage: S3Storage,
        metadata_tracker: MetadataTracker,
        embedding_types: List[str],
        limit: Optional[int] = None,
        batch_size: int = 100
    ):
        """
        Initialize Stage 4 processor.

        Args:
            s3_storage: S3 storage instance
            metadata_tracker: Metadata tracker instance
            embedding_types: List of embedding types to process ['entity', 'profile', 'experience']
            limit: Optional limit on number of entities to process
            batch_size: Batch size for embedding generation
        """
        self.s3 = s3_storage
        self.metadata_tracker = metadata_tracker
        self.embedding_types = embedding_types
        self.limit = limit
        self.batch_size = batch_size

        self.stage3_storage = Stage3Storage(s3_storage)
        self.chromadb_client = None
        self.embedding_client = None
        self.stage4_tracker = Stage4Tracker()

        self.stats = {
            'start_time': None,
            'end_time': None,
            'duration_seconds': 0,
            'entities_processed': 0,
            'entity_embeddings': 0,
            'profile_embeddings': 0,
            'experience_embeddings': 0,
            'total_embeddings': 0,
            'total_cost': 0.0,
            'errors': []
        }

    def initialize_clients(self) -> None:
        """Initialize ChromaDB and embedding clients."""
        logger.info("=" * 80)
        logger.info("🔧 INITIALIZING CLIENTS")
        logger.info("=" * 80)

        # Initialize ChromaDB
        try:
            self.chromadb_client = ChromaDBClient.initialize_from_env()
            logger.info("✅ ChromaDB client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromaDB: {e}")
            raise

        # Initialize embedding client
        try:
            self.embedding_client = EmbeddingClient()
            logger.info("✅ Embedding client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize embedding client: {e}")
            raise

        logger.info("")

    def load_entities(self) -> List[Dict[str, Any]]:
        """
        Load canonical entities from Stage 3.

        Returns:
            List of canonical entity dicts
        """
        logger.info("=" * 80)
        logger.info("📥 LOADING CANONICAL ENTITIES")
        logger.info("=" * 80)

        try:
            entities = self.stage3_storage.load_all_canonical_entities()
            logger.info(f"✅ Loaded {len(entities)} canonical entities from Stage 3")

            if self.limit and self.limit < len(entities):
                logger.info(f"⚠️  Limiting to first {self.limit} entities (--limit={self.limit})")
                entities = entities[:self.limit]
                logger.info(f"📊 Processing {len(entities)} entities")

            logger.info("")
            return entities

        except Exception as e:
            logger.error(f"❌ Failed to load entities: {e}")
            raise

    def estimate_and_confirm(self, entities: List[Dict[str, Any]]) -> bool:
        """
        Estimate indexing scope and ask for user confirmation.

        Args:
            entities: List of entities to process

        Returns:
            True if user confirms, False otherwise
        """
        logger.info("=" * 80)
        logger.info("📊 ESTIMATING INDEXING SCOPE")
        logger.info("=" * 80)

        try:
            scope = estimate_indexing_scope(entities)

            # Filter by requested embedding types
            types_to_process = []
            estimated_count = 0

            if 'entity' in self.embedding_types:
                types_to_process.append(f"Entity-level: {scope['entity_embeddings']:,} embeddings")
                estimated_count += scope['entity_embeddings']

            if 'profile' in self.embedding_types:
                types_to_process.append(f"Profile-consensus: {scope['profile_embeddings']:,} embeddings")
                estimated_count += scope['profile_embeddings']

            if 'experience' in self.embedding_types:
                types_to_process.append(f"Experience-level: {scope['experience_embeddings']:,} embeddings")
                estimated_count += scope['experience_embeddings']

            logger.info("\n📋 Embedding Types to Process:")
            for item in types_to_process:
                logger.info(f"  • {item}")

            logger.info(f"\n📊 Total embeddings to generate: {estimated_count:,}")
            logger.info(f"💰 Estimated cost: ${scope['estimated_cost']:.2f} (FREE - local model!)")
            logger.info("")

            # Ask for confirmation (auto-confirm in non-interactive mode or if limit is set)
            if self.limit or not sys.stdin.isatty():
                logger.info("✅ Auto-confirming (limit set or non-interactive mode)")
                return True

            response = input("Proceed with indexing? [Y/n]: ").strip().lower()
            return response in ['', 'y', 'yes']

        except Exception as e:
            logger.error(f"❌ Scope estimation failed: {e}")
            return False

    def process_entity_embeddings(self, entities: List[Dict[str, Any]]) -> None:
        """Process entity-level embeddings."""
        if 'entity' not in self.embedding_types:
            logger.info("⏭️  Skipping entity-level embeddings (not requested)")
            return

        logger.info("=" * 80)
        logger.info("🚀 INDEXING ENTITY-LEVEL EMBEDDINGS")
        logger.info("=" * 80)

        try:
            stats = index_entity_embeddings(
                entities=entities,
                chromadb_client=self.chromadb_client,
                embedding_client=self.embedding_client,
                batch_size=self.batch_size,
                show_progress=True
            )

            # Update overall stats
            self.stats['entity_embeddings'] = stats['successful']
            self.stats['total_embeddings'] += stats['successful']

            if stats['errors']:
                self.stats['errors'].extend(stats['errors'][:10])  # Keep first 10 errors

            logger.info("\n📊 Entity-Level Summary:")
            logger.info(f"   ✅ Successful: {stats['successful']:,}")
            logger.info(f"   ❌ Failed: {stats['failed']:,}")
            logger.info(f"   ⏱️  Duration: {stats.get('duration_seconds', 0.0):.2f}s")
            if stats.get('rate_per_second', 0) > 0:
                logger.info(f"   📈 Rate: {stats['rate_per_second']:.1f} embeddings/second")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Entity indexing failed: {e}")
            self.stats['errors'].append(f"Entity indexing failed: {e}")
            raise

    def process_profile_embeddings(self, entities: List[Dict[str, Any]]) -> None:
        """Process profile-consensus embeddings."""
        if 'profile' not in self.embedding_types:
            logger.info("⏭️  Skipping profile-consensus embeddings (not requested)")
            return

        logger.info("=" * 80)
        logger.info("🚀 INDEXING PROFILE-CONSENSUS EMBEDDINGS")
        logger.info("=" * 80)

        try:
            stats = index_profile_consensus_embeddings(
                entities=entities,
                chromadb_client=self.chromadb_client,
                embedding_client=self.embedding_client,
                batch_size=self.batch_size,
                show_progress=True
            )

            # Update overall stats
            self.stats['profile_embeddings'] = stats['successful']
            self.stats['total_embeddings'] += stats['successful']

            if stats['errors']:
                self.stats['errors'].extend(stats['errors'][:10])  # Keep first 10 errors

            logger.info("\n📊 Profile-Consensus Summary:")
            logger.info(f"   ✅ Successful: {stats['successful']:,}")
            logger.info(f"   ❌ Failed: {stats['failed']:,}")
            logger.info(f"   ⏱️  Duration: {stats.get('duration_seconds', 0.0):.2f}s")
            if stats.get('rate_per_second', 0) > 0:
                logger.info(f"   📈 Rate: {stats['rate_per_second']:.1f} profiles/second")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Profile indexing failed: {e}")
            self.stats['errors'].append(f"Profile indexing failed: {e}")
            raise

    def process_experience_embeddings(self, entities: List[Dict[str, Any]]) -> None:
        """Process experience-level embeddings."""
        if 'experience' not in self.embedding_types:
            logger.info("⏭️  Skipping experience-level embeddings (not requested)")
            return

        logger.info("=" * 80)
        logger.info("🚀 INDEXING EXPERIENCE-LEVEL EMBEDDINGS")
        logger.info("=" * 80)

        try:
            stats = index_experience_embeddings(
                entities=entities,
                chromadb_client=self.chromadb_client,
                embedding_client=self.embedding_client,
                batch_size=self.batch_size,
                show_progress=True
            )

            # Update overall stats
            self.stats['experience_embeddings'] = stats['successful']
            self.stats['total_embeddings'] += stats['successful']

            if stats['errors']:
                self.stats['errors'].extend(stats['errors'][:10])  # Keep first 10 errors

            logger.info("\n📊 Experience-Level Summary:")
            logger.info(f"   ✅ Successful: {stats['successful']:,}")
            logger.info(f"   ❌ Failed: {stats['failed']:,}")
            logger.info(f"   ⏱️  Duration: {stats.get('duration_seconds', 0.0):.2f}s")
            if stats.get('rate_per_second', 0) > 0:
                logger.info(f"   📈 Rate: {stats['rate_per_second']:.1f} experiences/second")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Experience indexing failed: {e}")
            self.stats['errors'].append(f"Experience indexing failed: {e}")
            raise

    def verify_collections(self) -> None:
        """Verify indexed collections."""
        logger.info("=" * 80)
        logger.info("🔍 VERIFYING INDEXED COLLECTIONS")
        logger.info("=" * 80)

        collections_to_verify = []
        if 'entity' in self.embedding_types:
            collections_to_verify.append('entities')
        if 'profile' in self.embedding_types:
            collections_to_verify.append('profile_consensus')
        if 'experience' in self.embedding_types:
            collections_to_verify.append('experiences')

        for collection_name in collections_to_verify:
            logger.info(f"\n🔎 Verifying {collection_name} collection...")

            try:
                results = verify_indexing(
                    chromadb_client=self.chromadb_client,
                    collection_name=collection_name,
                    sample_size=5
                )

                if results['metadata_valid'] and results['queries_successful']:
                    logger.info(f"✅ {collection_name} verification passed!")
                else:
                    logger.warning(f"⚠️  Some {collection_name} verification checks failed")

            except Exception as e:
                logger.error(f"❌ {collection_name} verification failed: {e}")

        logger.info("")

    def save_metadata(self) -> None:
        """Save indexing statistics and metadata."""
        logger.info("=" * 80)
        logger.info("💾 SAVING METADATA")
        logger.info("=" * 80)

        try:
            # Create metadata directory
            metadata_dir = Path("stage4-vectors/metadata")
            metadata_dir.mkdir(parents=True, exist_ok=True)

            # Get ChromaDB stats
            chroma_stats = self.chromadb_client.get_stats()

            # Prepare metadata
            metadata = {
                'timestamp': datetime.now().isoformat(),
                'processing_stats': {
                    'start_time': self.stats['start_time'],
                    'end_time': self.stats['end_time'],
                    'duration_seconds': self.stats['duration_seconds'],
                    'entities_processed': self.stats['entities_processed']
                },
                'embedding_stats': {
                    'entity_embeddings': self.stats['entity_embeddings'],
                    'profile_embeddings': self.stats['profile_embeddings'],
                    'experience_embeddings': self.stats['experience_embeddings'],
                    'total_embeddings': self.stats['total_embeddings']
                },
                'cost': {
                    'total_cost_usd': self.stats['total_cost'],
                    'model': 'gte-large-en-v1.5',
                    'note': 'FREE - local model, no API costs'
                },
                'chromadb': {
                    'mode': chroma_stats['mode'],
                    'collections': chroma_stats['collections'],
                    'total_vectors': chroma_stats['total_vectors']
                },
                'configuration': {
                    'embedding_types': self.embedding_types,
                    'limit': self.limit,
                    'batch_size': self.batch_size
                },
                'errors': self.stats['errors'][:20]  # Keep first 20 errors
            }

            # Add mode-specific info
            if chroma_stats['mode'] == 'local':
                metadata['chromadb']['persist_directory'] = chroma_stats.get('persist_directory')
            elif chroma_stats['mode'] == 'cloud':
                metadata['chromadb']['server'] = chroma_stats.get('server')

            # Save to file
            metadata_file = metadata_dir / f"indexing_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"✅ Metadata saved to {metadata_file}")

            # Also save latest stats
            latest_file = metadata_dir / "indexing_stats_latest.json"
            with open(latest_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"✅ Latest stats saved to {latest_file}")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Failed to save metadata: {e}")
            # Don't raise - this is not critical

    def update_metadata_tracker(self) -> None:
        """
        Update metadata tracker with Stage 4 completion for each source video.

        This marks each video that contributed canonical entities as having
        completed Stage 4, enabling proper end-to-end tracking.
        """
        logger.info("=" * 80)
        logger.info("📝 UPDATING METADATA TRACKER")
        logger.info("=" * 80)

        try:
            # Get ChromaDB stats
            chroma_stats = self.chromadb_client.get_stats()

            # Get all videos with completed Stage 3 (ready for Stage 4)
            pending_videos = self.metadata_tracker.get_pending_content("stage_4_vectorize")

            if not pending_videos:
                logger.warning("⚠️  No videos found pending Stage 4")
                logger.info("   This may be normal if all videos already processed Stage 4")
                return

            logger.info(f"📊 Processing {len(pending_videos)} videos for Stage 4 tracking")

            videos_updated = 0

            # Update each video
            for video_id in pending_videos:
                try:
                    # Start Stage 4 (if not already started)
                    video_metadata = self.metadata_tracker.get_content_metadata(video_id)
                    stage_4_status = video_metadata.get('stages', {}).get('stage_4_vectorize', {}).get('status', 'not_started')

                    if stage_4_status == 'not_started':
                        self.metadata_tracker.start_stage(
                            content_id=video_id,
                            stage='stage_4_vectorize',
                            save_to_s3=False  # Batch save at end
                        )

                    # Get Stage 3 metadata to find canonical entities from this video
                    stage3_metadata = video_metadata.get('stages', {}).get('stage_3_deduplicate', {}).get('metadata', {})
                    canonical_entity_ids = stage3_metadata.get('canonical_entity_ids', [])

                    # Build Stage 4 metadata
                    stage4_metadata = {
                        'chromadb_mode': chroma_stats['mode'],
                        'embedding_types_indexed': self.embedding_types,
                        'canonical_entities_from_video': len(canonical_entity_ids),
                        'collections': {
                            'entities': 'entity' in self.embedding_types,
                            'profile_consensus': 'profile' in self.embedding_types,
                            'experiences': 'experience' in self.embedding_types
                        },
                        'total_embeddings_in_db': self.stats['total_embeddings']
                    }

                    # Add location/server info
                    if chroma_stats['mode'] == 'local':
                        stage4_metadata['chromadb_location'] = chroma_stats.get('persist_directory', './chroma_data')
                    elif chroma_stats['mode'] == 'cloud':
                        stage4_metadata['chromadb_server'] = chroma_stats.get('server', 'unknown')

                    # Mark Stage 4 as complete
                    self.metadata_tracker.complete_stage(
                        content_id=video_id,
                        stage='stage_4_vectorize',
                        s3_paths=[],  # Embeddings stored in ChromaDB, not S3
                        metadata=stage4_metadata,
                        save_to_s3=False  # Batch save at end
                    )

                    videos_updated += 1

                except Exception as e:
                    logger.warning(f"   Failed to update video {video_id}: {e}")
                    continue

            # Save all tracker updates to S3 in one batch
            self.metadata_tracker.save_to_s3()

            logger.info(f"✅ Updated {videos_updated}/{len(pending_videos)} videos in metadata tracker")
            logger.info(f"   Total embeddings: {self.stats['total_embeddings']:,}")
            logger.info(f"   ChromaDB mode: {chroma_stats['mode']}")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ Failed to update metadata tracker: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise - this is not critical for indexing success

    def print_summary(self) -> None:
        """Print final summary."""
        logger.info("=" * 80)
        logger.info("📊 STAGE 4 INDEXING COMPLETE!")
        logger.info("=" * 80)

        logger.info(f"\n⏱️  Processing Time:")
        logger.info(f"   Duration: {self.stats['duration_seconds']:.2f} seconds")
        logger.info(f"   Start: {self.stats['start_time']}")
        logger.info(f"   End: {self.stats['end_time']}")

        logger.info(f"\n📈 Embeddings Created:")
        logger.info(f"   Entity-level:      {self.stats['entity_embeddings']:8,}")
        logger.info(f"   Profile-consensus: {self.stats['profile_embeddings']:8,}")
        logger.info(f"   Experience-level:  {self.stats['experience_embeddings']:8,}")
        logger.info(f"   {'─' * 40}")
        logger.info(f"   Total:             {self.stats['total_embeddings']:8,}")

        logger.info(f"\n💰 Cost:")
        logger.info(f"   Total: ${self.stats['total_cost']:.2f} (FREE - local model!)")

        # Get and print ChromaDB stats
        chroma_stats = self.chromadb_client.get_stats()
        logger.info(f"\n🗄️  ChromaDB Statistics:")
        logger.info(f"   Mode: {chroma_stats['mode'].upper()}")
        if chroma_stats['mode'] == 'local':
            logger.info(f"   Location: {chroma_stats.get('persist_directory')}")
        else:
            logger.info(f"   Server: {chroma_stats.get('server')}")
        logger.info(f"   Total vectors: {chroma_stats['total_vectors']:,}")

        for collection_name, count in chroma_stats['collections'].items():
            logger.info(f"   - {collection_name}: {count:,}")

        if self.stats['errors']:
            logger.info(f"\n⚠️  Errors: {len(self.stats['errors'])}")
            logger.info("   First 5 errors:")
            for error in self.stats['errors'][:5]:
                logger.info(f"   - {error}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Stage 4 processing complete!")
        logger.info("=" * 80)

    def process(self) -> None:
        """Run the complete Stage 4 processing pipeline."""
        self.stats['start_time'] = datetime.now().isoformat()
        start_timestamp = time.time()

        try:
            # 1. Initialize clients
            self.initialize_clients()

            # 2. Load entities
            entities = self.load_entities()
            self.stats['entities_processed'] = len(entities)

            # 3. Estimate and confirm
            if not self.estimate_and_confirm(entities):
                logger.info("❌ User cancelled operation")
                sys.exit(0)

            # 4. Process embeddings by type
            self.process_entity_embeddings(entities)
            self.process_profile_embeddings(entities)
            self.process_experience_embeddings(entities)

            # 5. Verify collections
            self.verify_collections()

            # 6. Save metadata
            self.save_metadata()

            # 7. Update metadata tracker
            self.update_metadata_tracker()

            # Calculate duration
            self.stats['end_time'] = datetime.now().isoformat()
            self.stats['duration_seconds'] = time.time() - start_timestamp

            # 8. Print summary
            self.print_summary()

            # 9. Print Stage 4 tracker summary and save report
            self.stage4_tracker.print_summary()
            self.stage4_tracker.save_stage4_report()

        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Processing interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"\n❌ Stage 4 processing failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


@click.command()
@click.option(
    '--embedding-types',
    type=str,
    default='all',
    help='Embedding types to process: "entity", "profile", "experience", "all", or comma-separated list (default: all)'
)
@click.option(
    '--limit',
    type=int,
    default=None,
    help='Limit processing to first N entities (for testing)'
)
@click.option(
    '--batch-size',
    type=int,
    default=100,
    help='Batch size for embedding generation (default: 100)'
)
def main(embedding_types: str, limit: Optional[int], batch_size: int):
    """
    Stage 4: Vector Indexing Processor

    Generate and index embeddings for canonical entities into ChromaDB.

    Examples:
        # Process all embedding types
        python cli/process_stage4.py --embedding-types all

        # Process only entity-level embeddings
        python cli/process_stage4.py --embedding-types entity

        # Process profiles and experiences
        python cli/process_stage4.py --embedding-types profile,experience

        # Test with limited entities
        python cli/process_stage4.py --embedding-types all --limit 10
    """
    logger.info("=" * 80)
    logger.info("STAGE 4: VECTOR INDEXING")
    logger.info("=" * 80)
    logger.info("")

    # Parse embedding types
    if embedding_types.lower() == 'all':
        types_list = ['entity', 'profile', 'experience']
    else:
        types_list = [t.strip().lower() for t in embedding_types.split(',')]

    # Validate embedding types
    valid_types = {'entity', 'profile', 'experience'}
    invalid_types = set(types_list) - valid_types
    if invalid_types:
        logger.error(f"❌ Invalid embedding types: {', '.join(invalid_types)}")
        logger.error(f"   Valid types: {', '.join(valid_types)} or 'all'")
        sys.exit(1)

    logger.info(f"📋 Configuration:")
    logger.info(f"   Embedding types: {', '.join(types_list)}")
    logger.info(f"   Limit: {limit if limit else 'None (process all)'}")
    logger.info(f"   Batch size: {batch_size}")
    logger.info("")

    try:
        # Initialize storage
        s3_storage = S3Storage()
        metadata_tracker = MetadataTracker(s3_storage)

        # Create processor
        processor = Stage4Processor(
            s3_storage=s3_storage,
            metadata_tracker=metadata_tracker,
            embedding_types=types_list,
            limit=limit,
            batch_size=batch_size
        )

        # Run processing
        processor.process()

    except Exception as e:
        logger.error(f"❌ Failed to initialize Stage 4 processor: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
