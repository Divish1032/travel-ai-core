#!/usr/bin/env python3
"""
Command-Line Interface for Testing Semantic Search

Provides interactive and command-line search capabilities for testing
the TravelAI semantic search system.

Usage:
    # Basic search
    python search_test.py --query "beach parties"

    # Personalized search
    python search_test.py --query "places to stay" --profile solo_budget_party

    # Filtered search
    python search_test.py --query "romantic dinner" --city Bangkok --type restaurant

    # With reranking
    python search_test.py --query "restaurants" --rerank quality

    # Interactive mode
    python search_test.py --interactive

Author: TravelAI Team
Date: 2025-12-14
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.vectordb.search_api import SemanticSearchAPI, SearchResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SearchCLI:
    """Command-line interface for semantic search testing."""

    def __init__(self):
        """Initialize search CLI."""
        self.api: Optional[SemanticSearchAPI] = None

    def initialize(self) -> bool:
        """
        Initialize search API.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing Semantic Search API...")
            self.api = SemanticSearchAPI()
            logger.info("✅ Search API initialized successfully\n")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize search API: {e}")
            import traceback
            traceback.print_exc()
            return False

    def format_result(
        self,
        result: SearchResult,
        index: int,
        show_explanation: bool = False,
        show_metadata: bool = False
    ) -> None:
        """
        Format and display a single search result.

        Args:
            result: SearchResult object
            index: Result index (1-based)
            show_explanation: Whether to show match explanation
            show_metadata: Whether to show additional metadata
        """
        # Header
        logger.info(f"\n{'=' * 80}")
        logger.info(f"#{index}. {result.canonical_name}")
        logger.info(f"{'=' * 80}")

        # Basic info
        logger.info(f"📍 Location: {result.location}")
        logger.info(f"🏷️  Type: {result.entity_type.title()}")
        logger.info(f"⭐ Relevance Score: {result.relevance_score:.1f}%")

        # Rating and mentions
        if result.overall_rating:
            stars = '★' * int(result.overall_rating)
            logger.info(f"⭐ Rating: {result.overall_rating:.1f}/5 {stars}")

        if result.total_mentions > 0:
            logger.info(f"💬 Mentions: {result.total_mentions}")

        # Enriched metadata
        if 'distance_from_user' in result.metadata:
            dist = result.metadata['distance_from_user']
            cat = result.metadata.get('distance_category', 'unknown')
            logger.info(f"📏 Distance: {dist}km ({cat})")

        if 'price_category' in result.metadata:
            price = result.metadata['price_category']
            emoji = {'budget': '💰', 'mid-range': '💰💰', 'luxury': '💰💰💰'}
            logger.info(f"💵 Price: {price.title()} {emoji.get(price, '')}")

        if 'activity_categories' in result.metadata:
            activities = ', '.join(result.metadata['activity_categories'])
            logger.info(f"🎯 Activities: {activities}")

        # Explanation
        if show_explanation and result.explanation:
            logger.info(f"\n💡 Why this matches:")
            logger.info(f"   {result.explanation}")

        # Additional metadata
        if show_metadata:
            logger.info(f"\n📊 Additional Metadata:")
            for key, value in result.metadata.items():
                if key not in ['entity_id', 'lat', 'lon', 'embedding_vector']:
                    logger.info(f"   {key}: {value}")

    def execute_search(
        self,
        query: str,
        profile: Optional[str] = None,
        city: Optional[str] = None,
        entity_type: Optional[str] = None,
        top_k: int = 10,
        rerank_strategy: Optional[str] = None,
        show_explanation: bool = False,
        show_metadata: bool = False,
        user_location: Optional[tuple] = None
    ) -> List[SearchResult]:
        """
        Execute search with given parameters.

        Args:
            query: Search query
            profile: Optional traveler profile key
            city: Optional city filter
            entity_type: Optional entity type filter
            top_k: Number of results
            rerank_strategy: Optional reranking strategy
            show_explanation: Whether to show explanations
            show_metadata: Whether to show metadata
            user_location: Optional (lat, lon) tuple

        Returns:
            List of SearchResult objects
        """
        logger.info("=" * 80)
        logger.info("🔍 EXECUTING SEARCH")
        logger.info("=" * 80)
        logger.info(f"Query: '{query}'")
        if profile:
            logger.info(f"Profile: {profile}")
        if city:
            logger.info(f"City: {city}")
        if entity_type:
            logger.info(f"Type: {entity_type}")
        if rerank_strategy:
            logger.info(f"Rerank: {rerank_strategy}")
        logger.info(f"Results: {top_k}")
        logger.info("")

        # Build filters
        filters = {}
        if city:
            filters['city'] = city
        if entity_type:
            filters['entity_type'] = entity_type

        # Execute search based on profile
        if profile:
            # Personalized search
            traveler_profile = self._parse_profile(profile)
            results = self.api.personalized_search(
                query_text=query,
                traveler_profile=traveler_profile,
                filters=filters,
                top_k=top_k
            )
        else:
            # Regular entity search
            results = self.api.search_entities(
                query_text=query,
                filters=filters,
                top_k=top_k
            )

        # Apply reranking if specified
        if rerank_strategy and results:
            logger.info(f"\n🔄 Applying '{rerank_strategy}' reranking...")
            results = self.api.rerank_results(
                results,
                rerank_strategy=rerank_strategy,
                user_location=user_location
            )

        # Enrich results
        if results:
            logger.info(f"\n💎 Enriching results...")
            results = self.api.enrich_results(results, user_location=user_location)

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info(f"📊 SEARCH RESULTS ({len(results)} found)")
        logger.info("=" * 80)

        if not results:
            logger.info("📭 No results found for your query.")
            return []

        # Generate summary
        summary = self.api.generate_result_summary(results, query)
        logger.info(f"\n📝 Summary: {summary}\n")

        # Display each result
        for idx, result in enumerate(results, 1):
            self.format_result(
                result,
                idx,
                show_explanation=show_explanation,
                show_metadata=show_metadata
            )

        return results

    def _parse_profile(self, profile_str: str) -> Dict[str, Any]:
        """
        Parse profile string into profile dict.

        Args:
            profile_str: Profile key (e.g., "solo_budget_party") or JSON

        Returns:
            Profile dictionary
        """
        import json

        # Try to parse as JSON
        if profile_str.startswith('{'):
            try:
                return json.loads(profile_str)
            except:
                pass

        # Parse profile key
        parts = profile_str.split('_')

        profile = {}

        # Extract traveler type
        if 'solo' in parts:
            profile['traveler_type'] = 'solo'
        elif 'couple' in parts:
            profile['traveler_type'] = 'couple'
        elif 'family' in parts:
            profile['traveler_type'] = 'family'
        elif 'group' in parts:
            profile['traveler_type'] = 'group'

        # Extract budget tier
        if 'budget' in parts:
            profile['budget_tier'] = 'budget'
        elif 'midrange' in parts or 'mid-range' in profile_str:
            profile['budget_tier'] = 'mid-range'
        elif 'luxury' in parts:
            profile['budget_tier'] = 'luxury'

        # Extract travel style
        style = []
        style_keywords = ['party', 'cultural', 'adventure', 'romantic', 'social', 'backpacker']
        for keyword in style_keywords:
            if keyword in parts or keyword in profile_str:
                style.append(keyword)

        if style:
            profile['travel_style'] = style

        return profile

    def interactive_mode(self):
        """Run interactive search mode."""
        logger.info("=" * 80)
        logger.info("🎯 INTERACTIVE SEARCH MODE")
        logger.info("=" * 80)
        logger.info("\nCommands:")
        logger.info("  search <query>           - Basic search")
        logger.info("  profile <key>            - Set traveler profile")
        logger.info("  city <name>              - Set city filter")
        logger.info("  type <type>              - Set entity type filter")
        logger.info("  rerank <strategy>        - Set reranking strategy")
        logger.info("  location <lat> <lon>     - Set user location")
        logger.info("  clear                    - Clear all filters")
        logger.info("  explain on/off           - Toggle explanations")
        logger.info("  help                     - Show commands")
        logger.info("  quit                     - Exit")
        logger.info("")

        # State
        profile = None
        city = None
        entity_type = None
        rerank_strategy = None
        user_location = None
        show_explanation = False

        while True:
            try:
                # Show current settings
                logger.info("\n" + "-" * 80)
                logger.info("Current settings:")
                logger.info(f"  Profile: {profile or 'None'}")
                logger.info(f"  City: {city or 'Any'}")
                logger.info(f"  Type: {entity_type or 'Any'}")
                logger.info(f"  Rerank: {rerank_strategy or 'None'}")
                logger.info(f"  Location: {user_location or 'None'}")
                logger.info(f"  Explanations: {'On' if show_explanation else 'Off'}")
                logger.info("-" * 80)

                # Get input
                command = input("\n> ").strip()

                if not command:
                    continue

                # Parse command
                parts = command.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                # Execute command
                if cmd == 'quit' or cmd == 'exit':
                    logger.info("👋 Goodbye!")
                    break

                elif cmd == 'help':
                    logger.info("\nAvailable commands:")
                    logger.info("  search <query>           - Execute search")
                    logger.info("  profile <key>            - Set profile (e.g., solo_budget_party)")
                    logger.info("  city <name>              - Filter by city (e.g., Bangkok)")
                    logger.info("  type <type>              - Filter by type (e.g., restaurant)")
                    logger.info("  rerank <strategy>        - Set reranking (balanced/quality/popular/distance)")
                    logger.info("  location <lat> <lon>     - Set user location")
                    logger.info("  clear                    - Clear all filters")
                    logger.info("  explain on/off           - Toggle explanations")
                    logger.info("  quit                     - Exit")

                elif cmd == 'search':
                    if not args:
                        logger.warning("⚠️  Please provide a search query")
                        continue

                    self.execute_search(
                        query=args,
                        profile=profile,
                        city=city,
                        entity_type=entity_type,
                        rerank_strategy=rerank_strategy,
                        show_explanation=show_explanation,
                        user_location=user_location
                    )

                elif cmd == 'profile':
                    profile = args if args else None
                    logger.info(f"✅ Profile set to: {profile or 'None'}")

                elif cmd == 'city':
                    city = args if args else None
                    logger.info(f"✅ City set to: {city or 'Any'}")

                elif cmd == 'type':
                    entity_type = args if args else None
                    logger.info(f"✅ Type set to: {entity_type or 'Any'}")

                elif cmd == 'rerank':
                    if args.lower() in ['balanced', 'quality', 'popular', 'distance']:
                        rerank_strategy = args.lower()
                        logger.info(f"✅ Reranking set to: {rerank_strategy}")
                    else:
                        logger.warning("⚠️  Invalid strategy. Use: balanced, quality, popular, or distance")

                elif cmd == 'location':
                    try:
                        coords = args.split()
                        if len(coords) == 2:
                            user_location = (float(coords[0]), float(coords[1]))
                            logger.info(f"✅ Location set to: {user_location}")
                        else:
                            logger.warning("⚠️  Please provide latitude and longitude")
                    except:
                        logger.warning("⚠️  Invalid coordinates. Use: location <lat> <lon>")

                elif cmd == 'clear':
                    profile = None
                    city = None
                    entity_type = None
                    rerank_strategy = None
                    user_location = None
                    logger.info("✅ All filters cleared")

                elif cmd == 'explain':
                    if args.lower() == 'on':
                        show_explanation = True
                        logger.info("✅ Explanations enabled")
                    elif args.lower() == 'off':
                        show_explanation = False
                        logger.info("✅ Explanations disabled")
                    else:
                        logger.warning("⚠️  Use: explain on/off")

                else:
                    logger.warning(f"⚠️  Unknown command: {cmd}. Type 'help' for available commands.")

            except KeyboardInterrupt:
                logger.info("\n\n👋 Goodbye!")
                break
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Semantic Search CLI for TravelAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  python search_test.py --query "beach parties"

  # Personalized search
  python search_test.py --query "places to stay" --profile solo_budget_party

  # Filtered search
  python search_test.py --query "romantic dinner" --city Bangkok --type restaurant

  # With reranking
  python search_test.py --query "restaurants" --city Bangkok --rerank quality

  # With location
  python search_test.py --query "temples" --city Bangkok --location 13.7563 100.5018

  # Interactive mode
  python search_test.py --interactive
        """
    )

    parser.add_argument(
        '--query', '-q',
        type=str,
        help='Search query'
    )

    parser.add_argument(
        '--profile', '-p',
        type=str,
        help='Traveler profile (e.g., solo_budget_party, couple_luxury)'
    )

    parser.add_argument(
        '--city', '-c',
        type=str,
        help='Filter by city (e.g., Bangkok, Chiang Mai)'
    )

    parser.add_argument(
        '--type', '-t',
        type=str,
        dest='entity_type',
        help='Filter by entity type (e.g., restaurant, attraction, hotel)'
    )

    parser.add_argument(
        '--top-k', '-k',
        type=int,
        default=10,
        help='Number of results to return (default: 10)'
    )

    parser.add_argument(
        '--rerank', '-r',
        type=str,
        choices=['balanced', 'quality', 'popular', 'distance'],
        help='Reranking strategy'
    )

    parser.add_argument(
        '--location', '-l',
        type=float,
        nargs=2,
        metavar=('LAT', 'LON'),
        help='User location (latitude longitude)'
    )

    parser.add_argument(
        '--explain', '-e',
        action='store_true',
        help='Show match explanations'
    )

    parser.add_argument(
        '--metadata', '-m',
        action='store_true',
        help='Show detailed metadata'
    )

    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Set logging level'
    )

    args = parser.parse_args()

    # Set log level
    import logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Initialize CLI
    cli = SearchCLI()
    if not cli.initialize():
        sys.exit(1)

    # Run interactive mode or single search
    if args.interactive:
        cli.interactive_mode()
    elif args.query:
        user_location = tuple(args.location) if args.location else None

        cli.execute_search(
            query=args.query,
            profile=args.profile,
            city=args.city,
            entity_type=args.entity_type,
            top_k=args.top_k,
            rerank_strategy=args.rerank,
            show_explanation=args.explain,
            show_metadata=args.metadata,
            user_location=user_location
        )
    else:
        parser.print_help()
        logger.info("\n💡 Tip: Use --interactive for interactive mode")
        logger.info("💡 Tip: Use --query for one-time search")


if __name__ == '__main__':
    main()
