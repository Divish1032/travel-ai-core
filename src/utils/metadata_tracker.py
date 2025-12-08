"""
Metadata Tracking System for Travel AI Pipeline

Tracks processing status and metadata for content items across all pipeline stages.
Provides centralized state management with S3 persistence and in-memory caching.

Metadata Schema:
    {
        "content_id": "youtube_abc123",
        "source": "youtube",
        "source_url": "https://...",
        "title": "Optional title",
        "added_at": "ISO timestamp",
        "stages": {
            "stage_1_crawl": {
                "status": "complete",
                "started_at": "ISO timestamp",
                "completed_at": "ISO timestamp",
                "duration_seconds": 120,
                "s3_paths": ["s3://..."],
                "metadata": {"transcript_length": 5000},
                "error": null,
                "retry_count": 0
            },
            "stage_2_extract": {...},
            "stage_3_normalize": {...},
            "stage_4_embed": {...},
            "stage_5_index": {...}
        },
        "pipeline_status": "stage_2_pending",
        "last_updated": "ISO timestamp",
        "total_error_count": 0,
        "tags": []
    }

Storage:
    S3: metadata/processing_status.jsonl

Usage:
    from src.storage.s3 import S3Storage
    from src.utils.metadata_tracker import MetadataTracker

    # Initialize tracker
    storage = S3Storage()
    tracker = MetadataTracker(storage)

    # Register and process content
    tracker.register_content(
        content_id="youtube_abc123",
        source="youtube",
        source_url="https://youtube.com/watch?v=abc123",
        title="Best of Boracay 2024"
    )

    # Start stage 1
    tracker.start_stage("youtube_abc123", "stage_1_crawl")

    # Complete stage 1
    tracker.complete_stage(
        content_id="youtube_abc123",
        stage="stage_1_crawl",
        s3_paths=["s3://bucket/raw/youtube/videos/batch.jsonl"],
        metadata={"transcript_length": 5000}
    )

    # Get pending content for stage 2
    pending = tracker.get_pending_content("stage_2_extract")
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from src.storage.s3 import S3Storage, S3StorageError
from src.utils.logging import get_logger


logger = get_logger(__name__)


class MetadataTracker:
    """
    Tracks processing status and metadata for content items across pipeline stages.

    Provides centralized state management with S3 persistence and in-memory caching
    for efficient access to content processing status.
    """

    # S3 paths
    METADATA_PATH = "metadata/processing_status.jsonl"

    # Pipeline stages
    STAGES = [
        "stage_1_crawl",
        "stage_2_extract",  # Entity extraction with LLM
        "stage_3_normalize",  # Normalize and deduplicate entities
        "stage_4_embed",  # Generate embeddings
        "stage_5_index"  # Index for search
    ]

    # Valid stage statuses
    VALID_STATUSES = {"not_started", "pending", "complete", "failed"}

    # Stage dependencies (which stage must complete before this one)
    STAGE_DEPENDENCIES = {
        "stage_1_crawl": None,  # No dependencies
        "stage_2_extract": "stage_1_crawl",  # Requires transcribed videos
        "stage_3_normalize": "stage_2_extract",  # Requires extracted entities
        "stage_4_embed": "stage_3_normalize",  # Requires normalized data
        "stage_5_index": "stage_4_embed"  # Requires embeddings
    }

    def __init__(self, s3_storage: S3Storage):
        """
        Initialize metadata tracker with S3 storage.

        Args:
            s3_storage: S3Storage instance for persistence

        Example:
            >>> from src.storage.s3 import S3Storage
            >>> storage = S3Storage()
            >>> tracker = MetadataTracker(storage)
        """
        self.s3_storage = s3_storage
        self._cache: Dict[str, Dict[str, Any]] = {}

        logger.info("Initializing MetadataTracker")

        # Load existing metadata from S3
        self.load_from_s3()

        logger.info(
            f"MetadataTracker initialized with {len(self._cache)} content items"
        )

    def _validate_stage(self, stage: str) -> None:
        """Validate stage name."""
        if stage not in self.STAGES:
            raise ValueError(
                f"Invalid stage: {stage}. Must be one of: {', '.join(self.STAGES)}"
            )

    def _validate_content_exists(self, content_id: str) -> None:
        """Validate content exists in cache."""
        if content_id not in self._cache:
            raise ValueError(
                f"Content not found: {content_id}. "
                f"Use register_content() to add it first."
            )

    def _update_last_modified(self, content_id: str) -> None:
        """Update last_updated timestamp for content."""
        self._cache[content_id]["last_updated"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def _update_pipeline_status(self, content_id: str) -> None:
        """
        Update overall pipeline status based on stage completion.

        Sets pipeline_status to "stage_N_pending" for the next incomplete stage,
        or "complete" if all stages are done.
        """
        stages = self._cache[content_id]["stages"]

        # Check each stage in order
        for stage in self.STAGES:
            stage_status = stages[stage]["status"]

            if stage_status == "not_started":
                # This stage hasn't started, so it's pending
                self._cache[content_id]["pipeline_status"] = f"{stage}_pending"
                return
            elif stage_status == "pending":
                # This stage is currently running
                self._cache[content_id]["pipeline_status"] = f"{stage}_running"
                return
            elif stage_status == "failed":
                # This stage has failed
                self._cache[content_id]["pipeline_status"] = f"{stage}_failed"
                return
            # If "complete", continue to next stage

        # All stages complete
        self._cache[content_id]["pipeline_status"] = "complete"

    def _migrate_stage_names(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate old stage names to new ones for backward compatibility.

        Old stages -> New stages:
        - stage_2_chunk -> stage_2_extract
        - stage_3_extract -> stage_3_normalize
        - stage_4_normalize -> stage_4_embed
        - stage_5_embed -> stage_5_index
        """
        OLD_TO_NEW = {
            "stage_2_chunk": "stage_2_extract",
            "stage_3_extract": "stage_3_normalize",
            "stage_4_normalize": "stage_4_embed",
            "stage_5_embed": "stage_5_index"
        }

        stages = item.get("stages", {})

        # Check if migration needed
        needs_migration = any(old_name in stages for old_name in OLD_TO_NEW.keys())

        if needs_migration:
            new_stages = {}

            # Migrate stage_1 (no change)
            if "stage_1_crawl" in stages:
                new_stages["stage_1_crawl"] = stages["stage_1_crawl"]

            # Migrate other stages with new names
            for old_name, new_name in OLD_TO_NEW.items():
                if old_name in stages:
                    new_stages[new_name] = stages[old_name]
                elif new_name not in new_stages:
                    # Initialize new stage if it doesn't exist
                    new_stages[new_name] = {
                        "status": "not_started",
                        "started_at": None,
                        "completed_at": None,
                        "duration_seconds": None,
                        "s3_paths": [],
                        "metadata": {},
                        "error": None,
                        "retry_count": 0
                    }

            item["stages"] = new_stages

            # Update pipeline_status if it references old stage names
            pipeline_status = item.get("pipeline_status", "")
            for old_name, new_name in OLD_TO_NEW.items():
                if old_name in pipeline_status:
                    item["pipeline_status"] = pipeline_status.replace(old_name, new_name)
                    break

        return item

    def load_from_s3(self) -> None:
        """
        Load metadata from S3 into in-memory cache.

        Downloads metadata/processing_status.jsonl from S3 and parses JSONL
        into dictionary keyed by content_id. If file doesn't exist in S3,
        starts with empty cache.

        Raises:
            S3StorageError: If S3 download fails (non-404 errors)

        Example:
            >>> tracker.load_from_s3()
            # INFO: Loaded 100 content items from S3
        """
        logger.info(f"Loading metadata from S3: {self.METADATA_PATH}")

        try:
            # Build S3 URI
            s3_uri = self.s3_storage._generate_s3_uri(self.METADATA_PATH)

            # Check if file exists
            if not self.s3_storage.file_exists(s3_uri):
                logger.info(
                    "Metadata file does not exist in S3, starting with empty cache"
                )
                self._cache = {}
                return

            # Download JSONL data
            data = self.s3_storage.download_jsonl(s3_uri)

            # Parse into cache keyed by content_id
            self._cache = {}
            for item in data:
                content_id = item.get("content_id")
                if content_id:
                    # Migrate old stage names to new ones
                    item = self._migrate_stage_names(item)
                    self._cache[content_id] = item
                else:
                    logger.warning(f"Skipping item without content_id: {item}")

            logger.info(f"Loaded {len(self._cache)} content items from S3")

        except S3StorageError as e:
            # If file doesn't exist (404), start with empty cache
            if "not found" in str(e).lower() or "404" in str(e):
                logger.info(
                    "Metadata file not found in S3, starting with empty cache"
                )
                self._cache = {}
            else:
                # Other S3 errors should be raised
                logger.error(f"Failed to load metadata from S3: {e}")
                raise

        except Exception as e:
            logger.error(f"Unexpected error loading metadata from S3: {e}")
            # Start with empty cache on unexpected errors
            self._cache = {}

    def save_to_s3(self) -> None:
        """
        Save in-memory cache to S3 as JSONL.

        Uploads metadata to metadata/processing_status.jsonl.

        Raises:
            S3StorageError: If S3 upload fails

        Example:
            >>> tracker.save_to_s3()
            # INFO: Saved 100 items to S3
        """
        logger.info(f"Saving metadata to S3: {self.METADATA_PATH}")

        try:
            # Convert cache to list for JSONL
            data = list(self._cache.values())

            if not data:
                logger.warning("No data to save (empty cache)")
                return

            # Upload to primary location
            s3_uri = self.s3_storage.upload_jsonl(
                data=data,
                source="metadata",
                data_type="processing_status",
                custom_path=self.METADATA_PATH
            )

            logger.info(f"Saved {len(data)} items to S3: {s3_uri}")

        except S3StorageError as e:
            logger.error(f"Failed to save metadata to S3: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error saving metadata to S3: {e}")
            raise

    def register_content(
        self,
        content_id: str,
        source: str,
        source_url: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> None:
        """
        Register new content item in tracking system.

        Creates metadata entry with all pipeline stages initialized to
        "not_started" status. If content_id already exists, logs warning
        and skips registration.

        Args:
            content_id: Unique content identifier
            source: Content source type
            source_url: Original source URL
            title: Optional content title
            tags: Optional list of tags

        Raises:
            ValueError: If required fields are empty

        Example:
            >>> tracker.register_content(
            ...     content_id="youtube_abc123",
            ...     source="youtube",
            ...     source_url="https://youtube.com/watch?v=abc123",
            ...     title="Best of Boracay 2024"
            ... )
        """
        # Validate required fields
        if not content_id:
            raise ValueError("content_id cannot be empty")
        if not source:
            raise ValueError("source cannot be empty")
        if not source_url:
            raise ValueError("source_url cannot be empty")

        # Check if already exists
        if content_id in self._cache:
            logger.warning(
                f"Content {content_id} already registered, skipping registration"
            )
            return

        logger.info(f"Registering new content: {content_id}")

        # Get current timestamp
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        # Initialize stage metadata
        stages = {}
        for stage in self.STAGES:
            stages[stage] = {
                "status": "not_started",
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "s3_paths": [],
                "metadata": {},
                "error": None,
                "retry_count": 0
            }

        # Create metadata entry
        metadata = {
            "content_id": content_id,
            "source": source,
            "source_url": source_url,
            "title": title,
            "added_at": now,
            "stages": stages,
            "pipeline_status": "stage_1_pending",
            "last_updated": now,
            "total_error_count": 0,
            "tags": tags or []
        }

        # Add to cache
        self._cache[content_id] = metadata

        logger.info(
            f"Registered new content: {content_id} "
            f"(source={source}, title={title or 'N/A'})"
        )

        # Save to S3
        try:
            self.save_to_s3()
        except Exception as e:
            logger.error(f"Failed to save after registering {content_id}: {e}")
            # Remove from cache if save failed
            del self._cache[content_id]
            raise

    def content_exists(self, content_id: str) -> bool:
        """
        Check if content ID exists in tracking system.

        Args:
            content_id: Content identifier to check

        Returns:
            True if content exists, False otherwise
        """
        exists = content_id in self._cache
        logger.debug(f"Content exists check for {content_id}: {exists}")
        return exists

    def get_content_info(self, content_id: str) -> Dict[str, Any]:
        """
        Get complete metadata for content item.

        Args:
            content_id: Content identifier

        Returns:
            Dictionary containing complete metadata

        Raises:
            ValueError: If content_id not found
        """
        if content_id not in self._cache:
            raise ValueError(
                f"Content not found: {content_id}. "
                f"Use register_content() to add it first."
            )

        logger.debug(f"Retrieved content info for {content_id}")
        return self._cache[content_id].copy()

    def get_all_items(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all content items in the tracker.

        Returns:
            Dictionary mapping content_id to metadata for all tracked items
        """
        return self._cache

    def start_stage(self, content_id: str, stage: str, save_to_s3: bool = True) -> None:
        """
        Mark stage as started (status = "pending").

        Sets stage status to "pending" and records start timestamp.
        If stage was previously failed, increments retry count.

        Args:
            content_id: Content identifier
            stage: Stage name (e.g., "stage_1_crawl")
            save_to_s3: Whether to save metadata to S3 immediately (default: True)

        Raises:
            ValueError: If content or stage is invalid

        Example:
            >>> tracker.start_stage("youtube_abc123", "stage_1_crawl")
            # INFO: Started stage_1_crawl for youtube_abc123
        """
        self._validate_content_exists(content_id)
        self._validate_stage(stage)

        logger.info(f"Starting {stage} for {content_id}")

        stage_data = self._cache[content_id]["stages"][stage]

        # Increment retry count if previously failed
        if stage_data["status"] == "failed":
            stage_data["retry_count"] += 1
            logger.info(
                f"Retry #{stage_data['retry_count']} for {stage} on {content_id}"
            )

        # Set status and timestamp
        stage_data["status"] = "pending"
        stage_data["started_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        stage_data["error"] = None  # Clear previous error

        # Update timestamps
        self._update_last_modified(content_id)
        self._update_pipeline_status(content_id)

        # Save to S3 if requested
        if save_to_s3:
            self.save_to_s3()

        logger.info(f"Started {stage} for {content_id}")

    def complete_stage(
        self,
        content_id: str,
        stage: str,
        s3_paths: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        save_to_s3: bool = True
    ) -> None:
        """
        Mark stage as completed successfully.

        Sets stage status to "complete", records completion time, calculates
        duration, and stores output paths and metadata.

        Args:
            content_id: Content identifier
            stage: Stage name
            s3_paths: List of S3 URIs for stage outputs
            metadata: Optional stage-specific metadata
            save_to_s3: Whether to save metadata to S3 immediately (default: True)

        Raises:
            ValueError: If content or stage is invalid

        Example:
            >>> tracker.complete_stage(
            ...     content_id="youtube_abc123",
            ...     stage="stage_1_crawl",
            ...     s3_paths=["s3://bucket/raw/youtube/videos/batch.jsonl"],
            ...     metadata={"transcript_length": 5000, "duration": 847}
            ... )
        """
        self._validate_content_exists(content_id)
        self._validate_stage(stage)

        logger.info(f"Completing {stage} for {content_id}")

        stage_data = self._cache[content_id]["stages"][stage]

        # Set completion status
        stage_data["status"] = "complete"
        completed_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        stage_data["completed_at"] = completed_at

        # Calculate duration
        if stage_data["started_at"]:
            started = datetime.fromisoformat(stage_data["started_at"].replace("Z", ""))
            completed = datetime.fromisoformat(completed_at.replace("Z", ""))
            duration = (completed - started).total_seconds()
            stage_data["duration_seconds"] = duration
        else:
            logger.warning(f"No start time for {stage} on {content_id}")
            stage_data["duration_seconds"] = None

        # Store outputs and metadata
        stage_data["s3_paths"] = s3_paths
        stage_data["metadata"] = metadata or {}

        # Update timestamps
        self._update_last_modified(content_id)
        self._update_pipeline_status(content_id)

        # Save to S3 if requested
        if save_to_s3:
            self.save_to_s3()

        logger.info(
            f"Completed {stage} for {content_id} "
            f"(duration: {stage_data['duration_seconds']}s, outputs: {len(s3_paths)})"
        )

    def fail_stage(self, content_id: str, stage: str, error: str, save_to_s3: bool = True) -> None:
        """
        Mark stage as failed with error message.

        Sets stage status to "failed", stores error message, and increments
        retry and error counters.

        Args:
            content_id: Content identifier
            stage: Stage name
            error: Error message describing failure
            save_to_s3: Whether to save metadata to S3 immediately (default: True)

        Raises:
            ValueError: If content or stage is invalid

        Example:
            >>> tracker.fail_stage(
            ...     content_id="youtube_abc123",
            ...     stage="stage_1_crawl",
            ...     error="Video unavailable: 404"
            ... )
        """
        self._validate_content_exists(content_id)
        self._validate_stage(stage)

        logger.error(f"Failing {stage} for {content_id}: {error}")

        stage_data = self._cache[content_id]["stages"][stage]

        # Set failure status
        stage_data["status"] = "failed"
        stage_data["completed_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        stage_data["error"] = error
        stage_data["retry_count"] += 1

        # Increment total error count
        self._cache[content_id]["total_error_count"] += 1

        # Update timestamps
        self._update_last_modified(content_id)
        self._update_pipeline_status(content_id)

        # Save to S3 if requested
        if save_to_s3:
            self.save_to_s3()

        logger.error(
            f"Failed {stage} for {content_id} "
            f"(retry: {stage_data['retry_count']}, error: {error})"
        )

    def reset_stage(self, content_id: str, stage: str) -> None:
        """
        Reset stage to not_started status.

        Clears timestamps and error but preserves retry_count history.
        Useful for manually re-running a stage.

        Args:
            content_id: Content identifier
            stage: Stage name

        Raises:
            ValueError: If content or stage is invalid

        Example:
            >>> tracker.reset_stage("youtube_abc123", "stage_1_crawl")
        """
        self._validate_content_exists(content_id)
        self._validate_stage(stage)

        logger.info(f"Resetting {stage} for {content_id}")

        stage_data = self._cache[content_id]["stages"][stage]

        # Preserve retry count, reset everything else
        retry_count = stage_data["retry_count"]

        stage_data.update({
            "status": "not_started",
            "started_at": None,
            "completed_at": None,
            "duration_seconds": None,
            "error": None,
            "retry_count": retry_count  # Preserve history
        })

        # Update timestamps
        self._update_last_modified(content_id)
        self._update_pipeline_status(content_id)

        # Save to S3
        self.save_to_s3()

        logger.info(f"Reset {stage} for {content_id} (preserving retry_count={retry_count})")

    def get_pending_content(self, stage: str, max_retries: int = 3) -> List[str]:
        """
        Get list of content IDs ready to be processed by this stage.

        Returns content where:
        - Previous stage is complete (or no previous stage for stage_1)
        - Current stage is "not_started" or ("failed" with retry_count < max_retries)

        Args:
            stage: Stage name to check
            max_retries: Maximum retry attempts before giving up (default: 3)

        Returns:
            List of content IDs ready for processing

        Raises:
            ValueError: If stage is invalid

        Example:
            >>> pending = tracker.get_pending_content("stage_2_extract")
            >>> print(f"Found {len(pending)} items ready for extraction")
        """
        self._validate_stage(stage)

        logger.info(f"Finding pending content for {stage}")

        pending = []

        for content_id, content_data in self._cache.items():
            stages = content_data["stages"]
            current_stage = stages[stage]

            # Check if current stage is eligible
            stage_status = current_stage["status"]
            retry_count = current_stage["retry_count"]

            # Skip if complete or pending
            if stage_status == "complete" or stage_status == "pending":
                continue

            # Skip if failed too many times
            if stage_status == "failed" and retry_count >= max_retries:
                continue

            # For stage_1, no dependencies
            if stage == "stage_1_crawl":
                if stage_status in ("not_started", "failed"):
                    pending.append(content_id)
                continue

            # For other stages, check if previous stage is complete
            prev_stage = self.STAGE_DEPENDENCIES[stage]
            if prev_stage:
                prev_status = stages[prev_stage]["status"]
                if prev_status == "complete":
                    if stage_status in ("not_started", "failed"):
                        pending.append(content_id)

        logger.info(f"Found {len(pending)} pending items for {stage}")
        return pending

    def get_stage_statistics(self, stage: str) -> Dict[str, Any]:
        """
        Get statistics for a specific stage.

        Counts items by status and calculates average duration for
        completed items.

        Args:
            stage: Stage name

        Returns:
            Dictionary with statistics

        Raises:
            ValueError: If stage is invalid

        Example:
            >>> stats = tracker.get_stage_statistics("stage_1_crawl")
            >>> print(f"Complete: {stats['complete']}")
            >>> print(f"Avg duration: {stats['avg_duration_seconds']}s")
        """
        self._validate_stage(stage)

        logger.debug(f"Calculating statistics for {stage}")

        stats = {
            "total": 0,
            "not_started": 0,
            "pending": 0,
            "complete": 0,
            "failed": 0,
            "avg_duration_seconds": None
        }

        durations = []

        for content_data in self._cache.values():
            stage_data = content_data["stages"][stage]
            status = stage_data["status"]

            stats["total"] += 1
            stats[status] += 1

            # Collect durations for average
            if status == "complete" and stage_data["duration_seconds"] is not None:
                durations.append(stage_data["duration_seconds"])

        # Calculate average duration
        if durations:
            stats["avg_duration_seconds"] = sum(durations) / len(durations)

        logger.debug(f"Statistics for {stage}: {stats}")
        return stats


# Example usage and testing
if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()

    console.print("\n[bold blue]Metadata Tracker - Complete Example[/bold blue]\n")

    try:
        from src.storage.s3 import S3Storage

        # Initialize
        console.print("[cyan]1. Initializing tracker...[/cyan]")
        storage = S3Storage()
        tracker = MetadataTracker(storage)
        console.print(f"[green]✓ Initialized with {len(tracker._cache)} items[/green]\n")

        # Register content
        console.print("[cyan]2. Registering content...[/cyan]")
        content_id = "youtube_test_" + datetime.now(timezone.utc).strftime("%H%M%S")
        tracker.register_content(
            content_id=content_id,
            source="youtube",
            source_url="https://youtube.com/watch?v=test",
            title="Test Video",
            tags=["test"]
        )
        console.print(f"[green]✓ Registered: {content_id}[/green]\n")

        # Stage 1: Start
        console.print("[cyan]3. Starting stage 1...[/cyan]")
        tracker.start_stage(content_id, "stage_1_crawl")
        console.print("[green]✓ Stage 1 started[/green]\n")

        # Stage 1: Complete
        console.print("[cyan]4. Completing stage 1...[/cyan]")
        tracker.complete_stage(
            content_id=content_id,
            stage="stage_1_crawl",
            s3_paths=["s3://bucket/test.jsonl"],
            metadata={"transcript_length": 1000}
        )
        console.print("[green]✓ Stage 1 completed[/green]\n")

        # Get pending for stage 2
        console.print("[cyan]5. Checking pending for stage 2...[/cyan]")
        pending = tracker.get_pending_content("stage_2_extract")
        console.print(f"[green]✓ Found {len(pending)} items pending for stage 2[/green]\n")

        # Get statistics
        console.print("[cyan]6. Getting statistics...[/cyan]")
        stats = tracker.get_stage_statistics("stage_1_crawl")

        table = Table(title="Stage 1 Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        for key, value in stats.items():
            if key == "avg_duration_seconds" and value:
                table.add_row(key, f"{value:.2f}s")
            else:
                table.add_row(key, str(value))

        console.print(table)

        console.print("\n[green]✓ All operations completed![/green]\n")

    except Exception as e:
        console.print(f"\n[red]✗ Error: {e}[/red]\n")
