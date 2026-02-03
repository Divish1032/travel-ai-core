#!/usr/bin/env python3
"""
Stage 4 Metrics Tracker

Tracks embedding generation costs, indexing statistics, and search performance
for the vector database pipeline.

Author: TravelAI Team
Date: 2025-12-14
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingStats:
    """Statistics for embedding generation."""
    count: int = 0
    tokens: int = 0
    cost: float = 0.0
    batches: int = 0
    duration_seconds: float = 0.0


@dataclass
class IndexingStats:
    """Statistics for vector indexing."""
    entities_processed: int = 0
    embeddings_created: int = 0
    duration_seconds: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def processing_rate(self) -> float:
        """Calculate embeddings per second."""
        if self.duration_seconds > 0:
            return self.embeddings_created / self.duration_seconds
        return 0.0


@dataclass
class SearchStats:
    """Statistics for search performance."""
    total_searches: int = 0
    total_duration_ms: float = 0.0
    total_results: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    queries: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def avg_query_time_ms(self) -> float:
        """Calculate average query time."""
        if self.total_searches > 0:
            return self.total_duration_ms / self.total_searches
        return 0.0

    @property
    def avg_results_per_query(self) -> float:
        """Calculate average results per query."""
        if self.total_searches > 0:
            return self.total_results / self.total_searches
        return 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total > 0:
            return self.cache_hits / total
        return 0.0


class Stage4Tracker:
    """
    Track Stage 4 vector database metrics.

    Monitors:
    - Embedding generation (costs, tokens, counts)
    - Indexing performance (entities, duration, rates)
    - Search performance (query time, results, cache)
    """

    def __init__(self, metadata_dir: str = "stage4-vectors/metadata"):
        """
        Initialize Stage 4 tracker.

        Args:
            metadata_dir: Directory to store tracking metadata
        """
        self.metadata_dir = Path(metadata_dir)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Tracking data
        self.embedding_stats: Dict[str, EmbeddingStats] = {
            'entity_level': EmbeddingStats(),
            'profile_consensus': EmbeddingStats(),
            'experiences': EmbeddingStats()
        }

        self.indexing_stats: Dict[str, IndexingStats] = {
            'entities': IndexingStats(),
            'profile_consensus': IndexingStats(),
            'experiences': IndexingStats()
        }

        self.search_stats: Dict[str, SearchStats] = {
            'entities': SearchStats(),
            'profile_consensus': SearchStats(),
            'experiences': SearchStats()
        }

        # Session metadata
        self.session_start = datetime.now()
        self.session_id = self.session_start.strftime("%Y%m%d_%H%M%S")

    def track_embedding_generation(
        self,
        embedding_type: str,
        count: int,
        tokens: int,
        cost: float,
        duration_seconds: float = 0.0
    ) -> None:
        """
        Track embedding generation for a batch.

        Args:
            embedding_type: Type of embedding (entity_level, profile_consensus, experiences)
            count: Number of embeddings generated
            tokens: Total tokens processed
            cost: Cost in USD
            duration_seconds: Time taken to generate embeddings
        """
        if embedding_type not in self.embedding_stats:
            logger.warning(f"Unknown embedding type: {embedding_type}")
            return

        stats = self.embedding_stats[embedding_type]
        stats.count += count
        stats.tokens += tokens
        stats.cost += cost
        stats.batches += 1
        stats.duration_seconds += duration_seconds

        logger.info(
            f"📊 Embedding batch tracked: {embedding_type} "
            f"({count} embeddings, {tokens:,} tokens, ${cost:.4f})"
        )

    def track_indexing(
        self,
        collection: str,
        entities_processed: int,
        embeddings_created: int,
        duration_seconds: float
    ) -> None:
        """
        Track indexing operation for a collection.

        Args:
            collection: Collection name (entities, profile_consensus, experiences)
            entities_processed: Number of entities processed
            embeddings_created: Number of embeddings indexed
            duration_seconds: Time taken for indexing
        """
        if collection not in self.indexing_stats:
            logger.warning(f"Unknown collection: {collection}")
            return

        stats = self.indexing_stats[collection]
        stats.entities_processed += entities_processed
        stats.embeddings_created += embeddings_created
        stats.duration_seconds += duration_seconds

        if stats.start_time is None:
            stats.start_time = time.time()
        stats.end_time = time.time()

        rate = embeddings_created / duration_seconds if duration_seconds > 0 else 0
        logger.info(
            f"📊 Indexing tracked: {collection} "
            f"({embeddings_created} embeddings, {rate:.1f} emb/sec)"
        )

    def start_indexing_session(self, collection: str) -> None:
        """
        Mark the start of an indexing session.

        Args:
            collection: Collection name
        """
        if collection in self.indexing_stats:
            self.indexing_stats[collection].start_time = time.time()

    def end_indexing_session(self, collection: str) -> None:
        """
        Mark the end of an indexing session.

        Args:
            collection: Collection name
        """
        if collection in self.indexing_stats:
            stats = self.indexing_stats[collection]
            if stats.start_time:
                stats.end_time = time.time()
                stats.duration_seconds = stats.end_time - stats.start_time

    def track_search(
        self,
        query: str,
        results_count: int,
        duration_ms: float,
        collection: str = 'entities',
        cache_hit: bool = False
    ) -> None:
        """
        Track search query performance.

        Args:
            query: Search query text
            results_count: Number of results returned
            duration_ms: Query duration in milliseconds
            collection: Collection searched
            cache_hit: Whether embedding was cached
        """
        if collection not in self.search_stats:
            self.search_stats[collection] = SearchStats()

        stats = self.search_stats[collection]
        stats.total_searches += 1
        stats.total_duration_ms += duration_ms
        stats.total_results += results_count

        if cache_hit:
            stats.cache_hits += 1
        else:
            stats.cache_misses += 1

        # Store query details (keep last 100)
        query_info = {
            'query': query[:100],  # Truncate long queries
            'results': results_count,
            'duration_ms': round(duration_ms, 2),
            'timestamp': datetime.now().isoformat()
        }
        stats.queries.append(query_info)

        # Keep only last 100 queries
        if len(stats.queries) > 100:
            stats.queries = stats.queries[-100:]

        logger.debug(
            f"🔍 Search tracked: '{query[:50]}...' "
            f"({results_count} results, {duration_ms:.1f}ms)"
        )

    def generate_stage4_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive Stage 4 report.

        Returns:
            Report dictionary with all metrics
        """
        # Calculate totals
        total_embedding_count = sum(stats.count for stats in self.embedding_stats.values())
        total_embedding_tokens = sum(stats.tokens for stats in self.embedding_stats.values())
        total_embedding_cost = sum(stats.cost for stats in self.embedding_stats.values())
        total_embedding_duration = sum(stats.duration_seconds for stats in self.embedding_stats.values())

        total_indexed = sum(stats.embeddings_created for stats in self.indexing_stats.values())
        total_indexing_duration = sum(stats.duration_seconds for stats in self.indexing_stats.values())

        total_searches = sum(stats.total_searches for stats in self.search_stats.values())
        total_search_duration = sum(stats.total_duration_ms for stats in self.search_stats.values())
        avg_search_time = total_search_duration / total_searches if total_searches > 0 else 0

        # Build report
        report = {
            'session_id': self.session_id,
            'session_start': self.session_start.isoformat(),
            'session_end': datetime.now().isoformat(),
            'embedding_generation': {
                'entity_level': {
                    'count': self.embedding_stats['entity_level'].count,
                    'tokens': self.embedding_stats['entity_level'].tokens,
                    'cost': round(self.embedding_stats['entity_level'].cost, 4),
                    'batches': self.embedding_stats['entity_level'].batches,
                    'duration_seconds': round(self.embedding_stats['entity_level'].duration_seconds, 2)
                },
                'profile_consensus': {
                    'count': self.embedding_stats['profile_consensus'].count,
                    'tokens': self.embedding_stats['profile_consensus'].tokens,
                    'cost': round(self.embedding_stats['profile_consensus'].cost, 4),
                    'batches': self.embedding_stats['profile_consensus'].batches,
                    'duration_seconds': round(self.embedding_stats['profile_consensus'].duration_seconds, 2)
                },
                'experiences': {
                    'count': self.embedding_stats['experiences'].count,
                    'tokens': self.embedding_stats['experiences'].tokens,
                    'cost': round(self.embedding_stats['experiences'].cost, 4),
                    'batches': self.embedding_stats['experiences'].batches,
                    'duration_seconds': round(self.embedding_stats['experiences'].duration_seconds, 2)
                },
                'totals': {
                    'count': total_embedding_count,
                    'tokens': total_embedding_tokens,
                    'cost': round(total_embedding_cost, 4),
                    'duration_seconds': round(total_embedding_duration, 2),
                    'embeddings_per_second': round(total_embedding_count / total_embedding_duration, 2) if total_embedding_duration > 0 else 0
                }
            },
            'indexing': {
                'entities_collection': {
                    'entities_processed': self.indexing_stats['entities'].entities_processed,
                    'embeddings_created': self.indexing_stats['entities'].embeddings_created,
                    'duration_seconds': round(self.indexing_stats['entities'].duration_seconds, 2),
                    'processing_rate': round(self.indexing_stats['entities'].processing_rate, 2)
                },
                'profile_consensus_collection': {
                    'entities_processed': self.indexing_stats['profile_consensus'].entities_processed,
                    'embeddings_created': self.indexing_stats['profile_consensus'].embeddings_created,
                    'duration_seconds': round(self.indexing_stats['profile_consensus'].duration_seconds, 2),
                    'processing_rate': round(self.indexing_stats['profile_consensus'].processing_rate, 2)
                },
                'experiences_collection': {
                    'entities_processed': self.indexing_stats['experiences'].entities_processed,
                    'embeddings_created': self.indexing_stats['experiences'].embeddings_created,
                    'duration_seconds': round(self.indexing_stats['experiences'].duration_seconds, 2),
                    'processing_rate': round(self.indexing_stats['experiences'].processing_rate, 2)
                },
                'totals': {
                    'embeddings_indexed': total_indexed,
                    'duration_seconds': round(total_indexing_duration, 2),
                    'avg_processing_rate': round(total_indexed / total_indexing_duration, 2) if total_indexing_duration > 0 else 0
                }
            },
            'search_performance': {
                'entities_collection': {
                    'total_searches': self.search_stats['entities'].total_searches,
                    'avg_query_time_ms': round(self.search_stats['entities'].avg_query_time_ms, 2),
                    'avg_results_per_query': round(self.search_stats['entities'].avg_results_per_query, 2),
                    'cache_hit_rate': round(self.search_stats['entities'].cache_hit_rate, 3)
                },
                'profile_consensus_collection': {
                    'total_searches': self.search_stats['profile_consensus'].total_searches,
                    'avg_query_time_ms': round(self.search_stats['profile_consensus'].avg_query_time_ms, 2),
                    'avg_results_per_query': round(self.search_stats['profile_consensus'].avg_results_per_query, 2),
                    'cache_hit_rate': round(self.search_stats['profile_consensus'].cache_hit_rate, 3)
                },
                'experiences_collection': {
                    'total_searches': self.search_stats['experiences'].total_searches,
                    'avg_query_time_ms': round(self.search_stats['experiences'].avg_query_time_ms, 2),
                    'avg_results_per_query': round(self.search_stats['experiences'].avg_results_per_query, 2),
                    'cache_hit_rate': round(self.search_stats['experiences'].cache_hit_rate, 3)
                },
                'totals': {
                    'total_searches': total_searches,
                    'avg_query_time_ms': round(avg_search_time, 2)
                }
            }
        }

        return report

    def save_stage4_report(self, path: Optional[str] = None) -> str:
        """
        Save Stage 4 report to JSON file.

        Args:
            path: Optional custom path. If None, uses default location.

        Returns:
            Path to saved report
        """
        if path is None:
            path = self.metadata_dir / f"stage4_report_{self.session_id}.json"
        else:
            path = Path(path)

        # Generate report
        report = self.generate_stage4_report()

        # Save to file
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"✅ Stage 4 report saved to: {path}")

        # Also save as "latest" for easy access
        latest_path = self.metadata_dir / "stage4_report_latest.json"
        with open(latest_path, 'w') as f:
            json.dump(report, f, indent=2)

        return str(path)

    def print_summary(self) -> None:
        """
        Print human-readable summary of Stage 4 metrics.
        """
        report = self.generate_stage4_report()

        logger.info("\n" + "=" * 80)
        logger.info("📊 STAGE 4 METRICS SUMMARY")
        logger.info("=" * 80)

        # Session info
        logger.info(f"\n📅 Session: {report['session_id']}")
        logger.info(f"   Started: {report['session_start']}")
        logger.info(f"   Ended: {report['session_end']}")

        # Embedding generation
        logger.info("\n" + "─" * 80)
        logger.info("💎 EMBEDDING GENERATION")
        logger.info("─" * 80)

        emb = report['embedding_generation']
        logger.info("\n🔹 Entity-Level Embeddings:")
        logger.info(f"   Count: {emb['entity_level']['count']:,}")
        logger.info(f"   Tokens: {emb['entity_level']['tokens']:,}")
        logger.info(f"   Cost: ${emb['entity_level']['cost']:.4f}")
        logger.info(f"   Batches: {emb['entity_level']['batches']}")
        logger.info(f"   Duration: {emb['entity_level']['duration_seconds']:.1f}s")

        logger.info("\n🔹 Profile Consensus Embeddings:")
        logger.info(f"   Count: {emb['profile_consensus']['count']:,}")
        logger.info(f"   Tokens: {emb['profile_consensus']['tokens']:,}")
        logger.info(f"   Cost: ${emb['profile_consensus']['cost']:.4f}")
        logger.info(f"   Batches: {emb['profile_consensus']['batches']}")
        logger.info(f"   Duration: {emb['profile_consensus']['duration_seconds']:.1f}s")

        logger.info("\n🔹 Experience Embeddings:")
        logger.info(f"   Count: {emb['experiences']['count']:,}")
        logger.info(f"   Tokens: {emb['experiences']['tokens']:,}")
        logger.info(f"   Cost: ${emb['experiences']['cost']:.4f}")
        logger.info(f"   Batches: {emb['experiences']['batches']}")
        logger.info(f"   Duration: {emb['experiences']['duration_seconds']:.1f}s")

        logger.info("\n💰 TOTAL EMBEDDING COSTS:")
        logger.info(f"   Embeddings: {emb['totals']['count']:,}")
        logger.info(f"   Tokens: {emb['totals']['tokens']:,}")
        logger.info(f"   Cost: ${emb['totals']['cost']:.4f}")
        logger.info(f"   Duration: {emb['totals']['duration_seconds']:.1f}s")
        logger.info(f"   Rate: {emb['totals']['embeddings_per_second']:.1f} emb/sec")

        # Indexing
        logger.info("\n" + "─" * 80)
        logger.info("🗂️  VECTOR INDEXING")
        logger.info("─" * 80)

        idx = report['indexing']
        logger.info("\n🔹 Entities Collection:")
        logger.info(f"   Entities: {idx['entities_collection']['entities_processed']:,}")
        logger.info(f"   Embeddings: {idx['entities_collection']['embeddings_created']:,}")
        logger.info(f"   Duration: {idx['entities_collection']['duration_seconds']:.1f}s")
        logger.info(f"   Rate: {idx['entities_collection']['processing_rate']:.1f} emb/sec")

        logger.info("\n🔹 Profile Consensus Collection:")
        logger.info(f"   Entities: {idx['profile_consensus_collection']['entities_processed']:,}")
        logger.info(f"   Embeddings: {idx['profile_consensus_collection']['embeddings_created']:,}")
        logger.info(f"   Duration: {idx['profile_consensus_collection']['duration_seconds']:.1f}s")
        logger.info(f"   Rate: {idx['profile_consensus_collection']['processing_rate']:.1f} emb/sec")

        logger.info("\n🔹 Experiences Collection:")
        logger.info(f"   Entities: {idx['experiences_collection']['entities_processed']:,}")
        logger.info(f"   Embeddings: {idx['experiences_collection']['embeddings_created']:,}")
        logger.info(f"   Duration: {idx['experiences_collection']['duration_seconds']:.1f}s")
        logger.info(f"   Rate: {idx['experiences_collection']['processing_rate']:.1f} emb/sec")

        logger.info("\n📊 TOTAL INDEXING:")
        logger.info(f"   Embeddings Indexed: {idx['totals']['embeddings_indexed']:,}")
        logger.info(f"   Duration: {idx['totals']['duration_seconds']:.1f}s")
        logger.info(f"   Avg Rate: {idx['totals']['avg_processing_rate']:.1f} emb/sec")

        # Search performance
        if report['search_performance']['totals']['total_searches'] > 0:
            logger.info("\n" + "─" * 80)
            logger.info("🔍 SEARCH PERFORMANCE")
            logger.info("─" * 80)

            search = report['search_performance']
            logger.info("\n🔹 Entities Collection:")
            logger.info(f"   Searches: {search['entities_collection']['total_searches']:,}")
            logger.info(f"   Avg Query Time: {search['entities_collection']['avg_query_time_ms']:.1f}ms")
            logger.info(f"   Avg Results: {search['entities_collection']['avg_results_per_query']:.1f}")
            logger.info(f"   Cache Hit Rate: {search['entities_collection']['cache_hit_rate']:.1%}")

            logger.info("\n🔹 Profile Consensus Collection:")
            logger.info(f"   Searches: {search['profile_consensus_collection']['total_searches']:,}")
            logger.info(f"   Avg Query Time: {search['profile_consensus_collection']['avg_query_time_ms']:.1f}ms")
            logger.info(f"   Avg Results: {search['profile_consensus_collection']['avg_results_per_query']:.1f}")
            logger.info(f"   Cache Hit Rate: {search['profile_consensus_collection']['cache_hit_rate']:.1%}")

            logger.info("\n🔹 Experiences Collection:")
            logger.info(f"   Searches: {search['experiences_collection']['total_searches']:,}")
            logger.info(f"   Avg Query Time: {search['experiences_collection']['avg_query_time_ms']:.1f}ms")
            logger.info(f"   Avg Results: {search['experiences_collection']['avg_results_per_query']:.1f}")
            logger.info(f"   Cache Hit Rate: {search['experiences_collection']['cache_hit_rate']:.1%}")

            logger.info("\n📊 TOTAL SEARCH PERFORMANCE:")
            logger.info(f"   Total Searches: {search['totals']['total_searches']:,}")
            logger.info(f"   Avg Query Time: {search['totals']['avg_query_time_ms']:.1f}ms")

        logger.info("\n" + "=" * 80)

    @staticmethod
    def load_report(path: str) -> Dict[str, Any]:
        """
        Load Stage 4 report from JSON file.

        Args:
            path: Path to report file

        Returns:
            Report dictionary
        """
        with open(path, 'r') as f:
            return json.load(f)

    def get_cost_breakdown(self) -> Dict[str, float]:
        """
        Get detailed cost breakdown by embedding type.

        Returns:
            Dictionary with costs per embedding type
        """
        return {
            'entity_level': self.embedding_stats['entity_level'].cost,
            'profile_consensus': self.embedding_stats['profile_consensus'].cost,
            'experiences': self.embedding_stats['experiences'].cost,
            'total': sum(stats.cost for stats in self.embedding_stats.values())
        }

    def get_storage_usage(self) -> Dict[str, int]:
        """
        Calculate estimated storage usage for vectors.

        Assumes:
        - 1024-dimensional embeddings
        - 4 bytes per float (float32)

        Returns:
            Dictionary with storage sizes in bytes
        """
        EMBEDDING_DIM = 1024
        BYTES_PER_FLOAT = 4

        bytes_per_embedding = EMBEDDING_DIM * BYTES_PER_FLOAT

        return {
            'entities': self.indexing_stats['entities'].embeddings_created * bytes_per_embedding,
            'profile_consensus': self.indexing_stats['profile_consensus'].embeddings_created * bytes_per_embedding,
            'experiences': self.indexing_stats['experiences'].embeddings_created * bytes_per_embedding,
            'total_bytes': sum(
                stats.embeddings_created * bytes_per_embedding
                for stats in self.indexing_stats.values()
            )
        }


if __name__ == '__main__':
    """
    Test Stage 4 tracker.
    """
    tracker = Stage4Tracker()

    # Simulate embedding generation
    tracker.track_embedding_generation('entity_level', 100, 50000, 0.001, 5.0)
    tracker.track_embedding_generation('profile_consensus', 50, 25000, 0.0005, 2.5)
    tracker.track_embedding_generation('experiences', 200, 100000, 0.002, 10.0)

    # Simulate indexing
    tracker.start_indexing_session('entities')
    tracker.track_indexing('entities', 100, 100, 5.0)
    tracker.end_indexing_session('entities')

    # Simulate searches
    tracker.track_search("temples in Bangkok", 5, 45.0, 'entities', cache_hit=False)
    tracker.track_search("restaurants", 10, 38.0, 'entities', cache_hit=True)

    # Print summary
    tracker.print_summary()

    # Save report
    report_path = tracker.save_stage4_report()
    logger.info(f"\n✅ Test report saved to: {report_path}")
