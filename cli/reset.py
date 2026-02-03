#!/usr/bin/env python3
"""
Reset Pipeline Stage Data

Unified reset script for all pipeline stages. Resets one stage at a time.

Stages:
  2        - Stage 2 (Entity Extraction): Delete extracted entities from PostgreSQL
  3        - Stage 3 (Deduplication): Delete canonical entities from PostgreSQL
  insights - Insights Pipeline: Delete insights from PostgreSQL
  4        - Stage 4 (Vector DB): Delete ChromaDB collections and metadata

Usage:
    # Dry run to preview changes
    python cli/reset.py --stage 2 --dry-run

    # Reset Stage 2 data
    python cli/reset.py --stage 2

    # Reset specific videos for Stage 2
    python cli/reset.py --stage 2 --video-ids abc123,xyz789

    # Reset Stage 3 data
    python cli/reset.py --stage 3

    # Reset insights data
    python cli/reset.py --stage insights

    # Reset Stage 4 vector database
    python cli/reset.py --stage 4

Examples:
    # Preview Stage 2 reset
    ./crawl.sh reset --stage 2 --dry-run

    # Reset Stage 3 for all videos
    ./crawl.sh reset --stage 3

    # Reset insights for specific videos
    ./crawl.sh reset --stage insights --video-ids abc123,xyz789

    # Reset Stage 4 ChromaDB collections
    ./crawl.sh reset --stage 4 --collections entities,profiles
"""

import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import SessionLocal
from src.database.models import (
    Video, ExtractedEntity, CanonicalEntity, EntityExperience,
    Insight, InsightMention, InsightRelatedEntity, StageStatus
)
from src.utils.logging import get_logger, setup_logging

# Stage 4 imports (only loaded when needed)
try:
    from src.vectordb import ChromaDBClient
    STAGE4_AVAILABLE = True
except ImportError:
    STAGE4_AVAILABLE = False

logger = get_logger(__name__)
console = Console()


def get_db():
    """Get PostgreSQL database session."""
    return SessionLocal()


def reset_stage2(video_ids: Optional[List[str]] = None, dry_run: bool = False) -> dict:
    """
    Reset Stage 2 data from PostgreSQL.

    This will:
    1. Delete all ExtractedEntity records (or for specific videos)
    2. Reset stage_2_status to NOT_STARTED in Video table

    Args:
        video_ids: Optional list of specific video IDs to reset
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    console.print("\n[bold blue]Stage 2 Reset: Entity Extraction[/bold blue]")
    console.print()

    db = get_db()
    try:
        # Get videos to reset
        if video_ids:
            videos = db.query(Video).filter(Video.video_id.in_(video_ids)).all()
            if len(videos) != len(video_ids):
                found_ids = {v.video_id for v in videos}
                missing_ids = set(video_ids) - found_ids
                console.print(f"[yellow]Warning: {len(missing_ids)} video(s) not found: {', '.join(missing_ids)}[/yellow]")
        else:
            videos = db.query(Video).all()

        if not videos:
            console.print("[yellow]No videos found to reset[/yellow]\n")
            return {'videos_reset': 0, 'entities_deleted': 0}

        video_id_list = [v.video_id for v in videos]

        # Count entities to delete
        entities_count = db.query(ExtractedEntity).filter(
            ExtractedEntity.video_id.in_(video_id_list)
        ).count()

        console.print(f"[cyan]Videos to reset:[/cyan] {len(videos)}")
        console.print(f"[cyan]Entities to delete:[/cyan] {entities_count:,}")
        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
            return {'videos_reset': len(videos), 'entities_deleted': entities_count}

        # Confirm
        if not click.confirm("Continue with reset?"):
            console.print("[yellow]Reset cancelled[/yellow]\n")
            return {'videos_reset': 0, 'entities_deleted': 0}

        # Delete entities
        console.print("[cyan]Deleting extracted entities...[/cyan]")
        deleted_count = db.query(ExtractedEntity).filter(
            ExtractedEntity.video_id.in_(video_id_list)
        ).delete(synchronize_session=False)

        # Reset video status
        console.print("[cyan]Resetting video stage_2_status...[/cyan]")
        for video in videos:
            video.stage_2_status = StageStatus.NOT_STARTED

        db.commit()

        console.print(f"\n[green]✓ Reset complete[/green]")
        console.print(f"  Videos reset: {len(videos)}")
        console.print(f"  Entities deleted: {deleted_count:,}\n")

        return {'videos_reset': len(videos), 'entities_deleted': deleted_count}

    except Exception as e:
        db.rollback()
        console.print(f"[red]✗ Reset failed: {e}[/red]\n")
        logger.exception(e)
        return {'videos_reset': 0, 'entities_deleted': 0, 'error': str(e)}
    finally:
        db.close()


def reset_stage3(video_ids: Optional[List[str]] = None, dry_run: bool = False) -> dict:
    """
    Reset Stage 3 data from PostgreSQL.

    This will:
    1. Delete all CanonicalEntity records (or for specific videos)
    2. Delete all EntityExperience records
    3. Reset stage_3_status to NOT_STARTED in Video table

    Note: When resetting specific videos, this still deletes ALL canonical entities
    since they are aggregated across multiple videos.

    Args:
        video_ids: Optional list of specific video IDs to reset
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    console.print("\n[bold blue]Stage 3 Reset: Entity Deduplication[/bold blue]")
    console.print()

    db = get_db()
    try:
        # Get videos to reset
        if video_ids:
            videos = db.query(Video).filter(Video.video_id.in_(video_ids)).all()
            if len(videos) != len(video_ids):
                found_ids = {v.video_id for v in videos}
                missing_ids = set(video_ids) - found_ids
                console.print(f"[yellow]Warning: {len(missing_ids)} video(s) not found: {', '.join(missing_ids)}[/yellow]")
        else:
            videos = db.query(Video).all()

        if not videos:
            console.print("[yellow]No videos found to reset[/yellow]\n")
            return {'videos_reset': 0, 'canonical_entities_deleted': 0, 'experiences_deleted': 0}

        # Count data to delete
        canonical_count = db.query(CanonicalEntity).count()
        experience_count = db.query(EntityExperience).count()

        console.print(f"[cyan]Videos to reset:[/cyan] {len(videos)}")
        console.print(f"[cyan]Canonical entities to delete:[/cyan] {canonical_count:,}")
        console.print(f"[cyan]Entity experiences to delete:[/cyan] {experience_count:,}")

        if video_ids:
            console.print(f"\n[yellow]Note: Canonical entities contain data from multiple videos.[/yellow]")
            console.print(f"[yellow]All {canonical_count:,} canonical entities will be deleted.[/yellow]")

        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
            return {
                'videos_reset': len(videos),
                'canonical_entities_deleted': canonical_count,
                'experiences_deleted': experience_count
            }

        # Confirm
        if not click.confirm("Continue with reset?"):
            console.print("[yellow]Reset cancelled[/yellow]\n")
            return {'videos_reset': 0, 'canonical_entities_deleted': 0, 'experiences_deleted': 0}

        # Delete entity experiences
        console.print("[cyan]Deleting entity experiences...[/cyan]")
        exp_deleted = db.query(EntityExperience).delete(synchronize_session=False)

        # Delete canonical entities
        console.print("[cyan]Deleting canonical entities...[/cyan]")
        canonical_deleted = db.query(CanonicalEntity).delete(synchronize_session=False)

        # Reset video status
        console.print("[cyan]Resetting video stage_3_status...[/cyan]")
        for video in videos:
            video.stage_3_status = StageStatus.NOT_STARTED

        db.commit()

        console.print(f"\n[green]✓ Reset complete[/green]")
        console.print(f"  Videos reset: {len(videos)}")
        console.print(f"  Canonical entities deleted: {canonical_deleted:,}")
        console.print(f"  Entity experiences deleted: {exp_deleted:,}\n")

        return {
            'videos_reset': len(videos),
            'canonical_entities_deleted': canonical_deleted,
            'experiences_deleted': exp_deleted
        }

    except Exception as e:
        db.rollback()
        console.print(f"[red]✗ Reset failed: {e}[/red]\n")
        logger.exception(e)
        return {'videos_reset': 0, 'canonical_entities_deleted': 0, 'experiences_deleted': 0, 'error': str(e)}
    finally:
        db.close()


def reset_insights(video_ids: Optional[List[str]] = None, dry_run: bool = False) -> dict:
    """
    Reset Insights Pipeline data from PostgreSQL.

    This will:
    1. Delete all Insight records (or for specific videos)
    2. Delete all InsightMention records
    3. Delete all InsightRelatedEntity records
    4. Reset insights_pipeline_status to NOT_STARTED in Video table

    Args:
        video_ids: Optional list of specific video IDs to reset
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    console.print("\n[bold blue]Insights Pipeline Reset[/bold blue]")
    console.print()

    db = get_db()
    try:
        # Get videos to reset
        if video_ids:
            videos = db.query(Video).filter(Video.video_id.in_(video_ids)).all()
            if len(videos) != len(video_ids):
                found_ids = {v.video_id for v in videos}
                missing_ids = set(video_ids) - found_ids
                console.print(f"[yellow]Warning: {len(missing_ids)} video(s) not found: {', '.join(missing_ids)}[/yellow]")
        else:
            videos = db.query(Video).all()

        if not videos:
            console.print("[yellow]No videos found to reset[/yellow]\n")
            return {'videos_reset': 0, 'insights_deleted': 0, 'mentions_deleted': 0, 'related_entities_deleted': 0}

        video_id_list = [v.video_id for v in videos]

        # Count data to delete
        insights = db.query(Insight).filter(Insight.video_id.in_(video_id_list)).all()
        insight_ids = [i.id for i in insights]

        insights_count = len(insights)
        mentions_count = db.query(InsightMention).filter(
            InsightMention.insight_id.in_(insight_ids)
        ).count() if insight_ids else 0

        related_entities_count = db.query(InsightRelatedEntity).filter(
            InsightRelatedEntity.insight_id.in_(insight_ids)
        ).count() if insight_ids else 0

        console.print(f"[cyan]Videos to reset:[/cyan] {len(videos)}")
        console.print(f"[cyan]Insights to delete:[/cyan] {insights_count:,}")
        console.print(f"[cyan]Insight mentions to delete:[/cyan] {mentions_count:,}")
        console.print(f"[cyan]Related entities to delete:[/cyan] {related_entities_count:,}")
        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
            return {
                'videos_reset': len(videos),
                'insights_deleted': insights_count,
                'mentions_deleted': mentions_count,
                'related_entities_deleted': related_entities_count
            }

        # Confirm
        if not click.confirm("Continue with reset?"):
            console.print("[yellow]Reset cancelled[/yellow]\n")
            return {'videos_reset': 0, 'insights_deleted': 0, 'mentions_deleted': 0, 'related_entities_deleted': 0}

        # Delete related entities
        if insight_ids:
            console.print("[cyan]Deleting insight related entities...[/cyan]")
            related_deleted = db.query(InsightRelatedEntity).filter(
                InsightRelatedEntity.insight_id.in_(insight_ids)
            ).delete(synchronize_session=False)

            # Delete mentions
            console.print("[cyan]Deleting insight mentions...[/cyan]")
            mentions_deleted = db.query(InsightMention).filter(
                InsightMention.insight_id.in_(insight_ids)
            ).delete(synchronize_session=False)

            # Delete insights
            console.print("[cyan]Deleting insights...[/cyan]")
            insights_deleted = db.query(Insight).filter(
                Insight.video_id.in_(video_id_list)
            ).delete(synchronize_session=False)
        else:
            related_deleted = 0
            mentions_deleted = 0
            insights_deleted = 0

        # Reset video status
        console.print("[cyan]Resetting video insights_pipeline_status...[/cyan]")
        for video in videos:
            video.insights_pipeline_status = StageStatus.NOT_STARTED

        db.commit()

        console.print(f"\n[green]✓ Reset complete[/green]")
        console.print(f"  Videos reset: {len(videos)}")
        console.print(f"  Insights deleted: {insights_deleted:,}")
        console.print(f"  Mentions deleted: {mentions_deleted:,}")
        console.print(f"  Related entities deleted: {related_deleted:,}\n")

        return {
            'videos_reset': len(videos),
            'insights_deleted': insights_deleted,
            'mentions_deleted': mentions_deleted,
            'related_entities_deleted': related_deleted
        }

    except Exception as e:
        db.rollback()
        console.print(f"[red]✗ Reset failed: {e}[/red]\n")
        logger.exception(e)
        return {'videos_reset': 0, 'insights_deleted': 0, 'mentions_deleted': 0, 'related_entities_deleted': 0, 'error': str(e)}
    finally:
        db.close()


def reset_stage4(collections: Optional[List[str]] = None, dry_run: bool = False) -> dict:
    """
    Reset Stage 4 ChromaDB collections.

    This will delete ChromaDB collections and recreate them empty.

    Args:
        collections: List of collection names to reset (entities, profile_consensus, experiences, city_destinations)
                    If None, resets all collections
        dry_run: If True, only show what would be reset

    Returns:
        Dict with reset results
    """
    if not STAGE4_AVAILABLE:
        console.print("[red]✗ Stage 4 (ChromaDB) not available. Check dependencies.[/red]\n")
        return {'error': 'Stage 4 not available'}

    console.print("\n[bold blue]Stage 4 Reset: Vector Database[/bold blue]")
    console.print()

    try:
        # Initialize ChromaDB client
        console.print("[cyan]Connecting to ChromaDB...[/cyan]")
        chroma_client = ChromaDBClient.initialize_from_env()

        # Determine collections to reset
        all_collections = ['entities', 'profile_consensus', 'experiences', 'city_destinations']

        if collections:
            collections_to_reset = []
            name_map = {
                'entities': 'entities',
                'entity': 'entities',
                'profiles': 'profile_consensus',
                'profile': 'profile_consensus',
                'profile_consensus': 'profile_consensus',
                'experiences': 'experiences',
                'experience': 'experiences',
                'exp': 'experiences',
                'cities': 'city_destinations',
                'city': 'city_destinations',
                'city_destinations': 'city_destinations'
            }

            for coll in collections:
                full_name = name_map.get(coll.lower())
                if full_name:
                    collections_to_reset.append(full_name)
                else:
                    console.print(f"[yellow]Warning: Unknown collection '{coll}', skipping[/yellow]")
        else:
            collections_to_reset = all_collections

        # Get current stats
        stats = {}
        for coll_name in collections_to_reset:
            try:
                if coll_name == 'entities' and chroma_client.entities_collection:
                    stats[coll_name] = chroma_client.entities_collection.count()
                elif coll_name == 'profile_consensus' and chroma_client.profile_consensus_collection:
                    stats[coll_name] = chroma_client.profile_consensus_collection.count()
                elif coll_name == 'experiences' and chroma_client.experiences_collection:
                    stats[coll_name] = chroma_client.experiences_collection.count()
                elif coll_name == 'city_destinations' and chroma_client.city_destinations_collection:
                    stats[coll_name] = chroma_client.city_destinations_collection.count()
                else:
                    stats[coll_name] = 0
            except Exception:
                stats[coll_name] = 0

        console.print(f"[cyan]Collections to reset:[/cyan] {len(collections_to_reset)}")
        for coll_name in collections_to_reset:
            console.print(f"  - {coll_name}: {stats.get(coll_name, 0):,} vectors")
        console.print()

        if dry_run:
            console.print("[yellow]DRY RUN - No changes will be made[/yellow]\n")
            return {'collections_reset': len(collections_to_reset), 'vectors_deleted': sum(stats.values())}

        # Confirm
        if not click.confirm("Continue with reset?"):
            console.print("[yellow]Reset cancelled[/yellow]\n")
            return {'collections_reset': 0, 'vectors_deleted': 0}

        # Reset collections
        for coll_name in collections_to_reset:
            console.print(f"[cyan]Resetting collection: {coll_name}...[/cyan]")
            try:
                # Delete collection
                chroma_client.client.delete_collection(coll_name)

                # Recreate empty collection
                if coll_name == 'entities':
                    chroma_client.entities_collection = chroma_client.client.get_or_create_collection(
                        name='entities',
                        metadata={"hnsw:space": "cosine"}
                    )
                elif coll_name == 'profile_consensus':
                    chroma_client.profile_consensus_collection = chroma_client.client.get_or_create_collection(
                        name='profile_consensus',
                        metadata={"hnsw:space": "cosine"}
                    )
                elif coll_name == 'experiences':
                    chroma_client.experiences_collection = chroma_client.client.get_or_create_collection(
                        name='experiences',
                        metadata={"hnsw:space": "cosine"}
                    )
                elif coll_name == 'city_destinations':
                    chroma_client.city_destinations_collection = chroma_client.client.get_or_create_collection(
                        name='city_destinations',
                        metadata={"hnsw:space": "cosine"}
                    )

                console.print(f"  [green]✓ Reset {coll_name}[/green]")
            except Exception as e:
                console.print(f"  [red]✗ Failed to reset {coll_name}: {e}[/red]")

        console.print(f"\n[green]✓ Reset complete[/green]")
        console.print(f"  Collections reset: {len(collections_to_reset)}")
        console.print(f"  Vectors deleted: {sum(stats.values()):,}\n")

        return {'collections_reset': len(collections_to_reset), 'vectors_deleted': sum(stats.values())}

    except Exception as e:
        console.print(f"[red]✗ Reset failed: {e}[/red]\n")
        logger.exception(e)
        return {'collections_reset': 0, 'vectors_deleted': 0, 'error': str(e)}


@click.command()
@click.option(
    '--stage',
    type=click.Choice(['2', '3', 'insights', '4'], case_sensitive=False),
    required=True,
    help='Stage to reset (2=extract, 3=deduplicate, insights=insights, 4=vectordb)'
)
@click.option(
    '--video-ids',
    type=str,
    help='Comma-separated list of video IDs to reset (only for stages 2, 3, insights)'
)
@click.option(
    '--collections',
    type=str,
    help='Comma-separated list of collections to reset (only for stage 4: entities,profiles,experiences,cities)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be reset without actually resetting'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Logging level (default: INFO)'
)
def main(stage: str, video_ids: Optional[str], collections: Optional[str], dry_run: bool, log_level: str):
    """
    Reset pipeline stage data.

    Resets one stage at a time. Use --stage to specify which stage to reset.

    Examples:

        # Reset Stage 2 (Entity Extraction)
        python cli/reset.py --stage 2

        # Reset Stage 3 (Deduplication) - dry run
        python cli/reset.py --stage 3 --dry-run

        # Reset insights for specific videos
        python cli/reset.py --stage insights --video-ids abc123,xyz789

        # Reset Stage 4 (Vector DB) specific collections
        python cli/reset.py --stage 4 --collections entities,profiles
    """
    # Setup logging
    setup_logging(log_level=log_level)

    console.print()
    console.print(Panel.fit(
        "[bold cyan]Travel AI Pipeline Reset[/bold cyan]",
        border_style="cyan"
    ))

    # Parse video IDs
    video_id_list = None
    if video_ids:
        if stage == '4':
            console.print("[red]✗ --video-ids not supported for Stage 4[/red]\n")
            sys.exit(1)
        video_id_list = [vid.strip() for vid in video_ids.split(',')]

    # Parse collections
    collection_list = None
    if collections:
        if stage != '4':
            console.print("[red]✗ --collections only supported for Stage 4[/red]\n")
            sys.exit(1)
        collection_list = [coll.strip() for coll in collections.split(',')]

    try:
        # Execute reset based on stage
        if stage == '2':
            result = reset_stage2(video_ids=video_id_list, dry_run=dry_run)
        elif stage == '3':
            result = reset_stage3(video_ids=video_id_list, dry_run=dry_run)
        elif stage == 'insights':
            result = reset_insights(video_ids=video_id_list, dry_run=dry_run)
        elif stage == '4':
            result = reset_stage4(collections=collection_list, dry_run=dry_run)

        # Check for errors
        if 'error' in result:
            sys.exit(1)

        # Success message
        if not dry_run:
            console.print("[green]Next steps:[/green]")
            if stage == '2':
                console.print("  Run: ./crawl.sh process-stage2")
            elif stage == '3':
                console.print("  Run: ./crawl.sh process-stage3")
            elif stage == 'insights':
                console.print("  Run: ./crawl.sh process-insights")
            elif stage == '4':
                console.print("  Run: ./crawl.sh process-stage4")
            console.print()

        sys.exit(0)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted by user[/yellow]\n")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]✗ Reset failed: {e}[/red]\n")
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
