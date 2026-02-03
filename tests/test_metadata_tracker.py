"""
Test suite for MetadataTracker (src/utils/metadata_tracker.py).

Tests metadata tracking system with mocked S3 storage.

Run with:
    pytest tests/test_metadata_tracker.py -v
    pytest tests/test_metadata_tracker.py::test_register_content -v
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.utils.metadata_tracker import MetadataTracker
from src.storage.s3 import S3Storage


################################################################################
# Fixtures
################################################################################

@pytest.fixture
def mock_s3_storage():
    """Create mock S3Storage instance."""
    storage = Mock(spec=S3Storage)
    storage.bucket_name = "test-bucket"
    storage.upload_jsonl = Mock(return_value="s3://test-bucket/metadata/processing_status.jsonl")
    storage.download_jsonl = Mock(return_value=[])
    return storage


@pytest.fixture
def tracker(mock_s3_storage):
    """Create MetadataTracker instance with mocked S3."""
    # Mock the load_from_s3 method to avoid S3 calls during initialization
    with patch.object(MetadataTracker, 'load_from_s3'):
        tracker = MetadataTracker(mock_s3_storage)
        # Clear cache to start fresh
        tracker._cache = {}
        return tracker


################################################################################
# Test: register_content
################################################################################

def test_register_content_new(tracker):
    """Test registering new content."""
    content_id = "youtube_test123"
    source = "youtube"
    source_url = "https://youtube.com/watch?v=test123"

    tracker.register_content(content_id, source, source_url)

    # Verify content is in cache
    assert content_id in tracker._cache

    # Verify structure
    entry = tracker._cache[content_id]
    assert entry["content_id"] == content_id
    assert entry["source"] == source
    assert entry["source_url"] == source_url
    assert "added_at" in entry
    assert "last_updated" in entry
    assert "pipeline_status" in entry
    assert entry["total_error_count"] == 0

    # Verify all stages initialized under "stages" key
    assert "stages" in entry
    for stage in tracker.STAGES:
        assert stage in entry["stages"]
        assert entry["stages"][stage]["status"] == "not_started"
        assert entry["stages"][stage]["retry_count"] == 0
        assert entry["stages"][stage]["s3_paths"] == []


def test_register_content_existing(tracker):
    """Test that registering existing content doesn't overwrite."""
    content_id = "youtube_test123"

    # Register first time
    tracker.register_content(content_id, "youtube", "https://url1.com")
    original_timestamp = tracker._cache[content_id]["added_at"]

    # Try to register again with different URL
    tracker.register_content(content_id, "youtube", "https://url2.com")

    # Verify URL not changed
    assert tracker._cache[content_id]["source_url"] == "https://url1.com"
    assert tracker._cache[content_id]["added_at"] == original_timestamp


def test_register_content_multiple_sources(tracker):
    """Test registering content from different sources."""
    tracker.register_content("youtube_abc123", "youtube", "https://youtube.com/watch?v=abc123")
    tracker.register_content("reddit_t3_xyz789", "reddit", "https://reddit.com/r/travel/comments/xyz789")
    tracker.register_content("blog_a1b2c3d4", "blog", "https://blog.example.com/post")

    assert len(tracker._cache) == 3
    assert tracker._cache["youtube_abc123"]["source"] == "youtube"
    assert tracker._cache["reddit_t3_xyz789"]["source"] == "reddit"
    assert tracker._cache["blog_a1b2c3d4"]["source"] == "blog"


################################################################################
# Test: content_exists
################################################################################

def test_content_exists_true(tracker):
    """Test checking if content exists returns True."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    assert tracker.content_exists(content_id) is True


def test_content_exists_false(tracker):
    """Test checking if content exists returns False."""
    assert tracker.content_exists("youtube_nonexistent") is False


################################################################################
# Test: get_content_info
################################################################################

def test_get_content_info_exists(tracker):
    """Test getting info for existing content."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    info = tracker.get_content_info(content_id)

    assert info is not None
    assert info["content_id"] == content_id
    assert info["source"] == "youtube"


def test_get_content_info_not_exists(tracker):
    """Test getting info for non-existent content."""
    with pytest.raises(ValueError, match="Content not found"):
        tracker.get_content_info("youtube_nonexistent")


################################################################################
# Test: start_stage
################################################################################

def test_start_stage_basic(tracker):
    """Test starting a stage."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    tracker.start_stage(content_id, "stage_1_crawl")

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "pending"
    assert stage_info["started_at"] is not None
    assert stage_info["retry_count"] == 0


def test_start_stage_increment_retry(tracker):
    """Test that starting a failed stage increments retry count."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    # Fail the stage first
    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.fail_stage(content_id, "stage_1_crawl", "Test error")

    # Start again
    tracker.start_stage(content_id, "stage_1_crawl")

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "pending"
    # retry_count increments on both fail (1) and restart (2)
    assert stage_info["retry_count"] == 2


def test_start_stage_invalid_stage(tracker):
    """Test that invalid stage raises ValueError."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    with pytest.raises(ValueError, match="Invalid stage"):
        tracker.start_stage(content_id, "invalid_stage")


def test_start_stage_content_not_registered(tracker):
    """Test that starting stage for unregistered content raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        tracker.start_stage("youtube_nonexistent", "stage_1_crawl")


################################################################################
# Test: complete_stage
################################################################################

def test_complete_stage_basic(tracker):
    """Test completing a stage."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")
    tracker.start_stage(content_id, "stage_1_crawl")

    s3_paths = ["s3://bucket/youtube/youtube_test123.jsonl"]
    metadata = {"video_count": 1, "total_duration": 300}

    tracker.complete_stage(content_id, "stage_1_crawl", s3_paths, metadata)

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "complete"
    assert stage_info["completed_at"] is not None
    assert stage_info["duration_seconds"] is not None
    assert stage_info["s3_paths"] == s3_paths
    assert stage_info["metadata"] == metadata


def test_complete_stage_calculates_duration(tracker):
    """Test that complete_stage calculates duration correctly."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    # Manually set started_at to known time
    start_time = "2024-01-15T10:00:00Z"
    tracker._cache[content_id]["stages"]["stage_1_crawl"]["status"] = "pending"
    tracker._cache[content_id]["stages"]["stage_1_crawl"]["started_at"] = start_time

    # Mock datetime to control completed_at time
    from datetime import timezone as tz
    with patch('src.utils.metadata_tracker.datetime') as mock_datetime:
        # Mock datetime.now(timezone.utc) to return a specific time
        mock_datetime.now.return_value = datetime(2024, 1, 15, 10, 5, 0, tzinfo=tz.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat

        tracker.complete_stage(content_id, "stage_1_crawl", [], {})

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    # Duration should be 5 minutes = 300 seconds
    assert stage_info["duration_seconds"] == 300


def test_complete_stage_without_start(tracker):
    """Test completing stage without starting it first."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    # Complete without starting
    tracker.complete_stage(content_id, "stage_1_crawl", [], {})

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "complete"
    # Duration should be None since no start time
    assert stage_info["duration_seconds"] is None


################################################################################
# Test: fail_stage
################################################################################

def test_fail_stage_basic(tracker):
    """Test failing a stage."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")
    tracker.start_stage(content_id, "stage_1_crawl")

    error_msg = "Connection timeout"
    tracker.fail_stage(content_id, "stage_1_crawl", error_msg)

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "failed"
    assert stage_info["error"] == error_msg


def test_fail_stage_multiple_times(tracker):
    """Test that failing stage multiple times updates error message."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")

    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.fail_stage(content_id, "stage_1_crawl", "First error")

    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.fail_stage(content_id, "stage_1_crawl", "Second error")

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["error"] == "Second error"
    # fail (1) + restart (2) + fail again (3) = 3
    assert stage_info["retry_count"] == 3


################################################################################
# Test: reset_stage
################################################################################

def test_reset_stage_basic(tracker):
    """Test resetting a failed stage."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")
    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.fail_stage(content_id, "stage_1_crawl", "Error")

    tracker.reset_stage(content_id, "stage_1_crawl")

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    assert stage_info["status"] == "not_started"
    assert stage_info["started_at"] is None
    assert stage_info["error"] is None
    # Retry count is preserved (was 1 after failure)
    assert stage_info["retry_count"] == 1


def test_reset_stage_clears_metadata(tracker):
    """Test that reset clears timestamps and errors but preserves retry_count."""
    content_id = "youtube_test123"
    tracker.register_content(content_id, "youtube", "https://youtube.com")
    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.complete_stage(content_id, "stage_1_crawl", ["s3://path"], {"key": "value"})

    tracker.reset_stage(content_id, "stage_1_crawl")

    stage_info = tracker._cache[content_id]["stages"]["stage_1_crawl"]
    # reset() only clears status, timestamps, and error
    # s3_paths and metadata are NOT cleared (would need manual clear)
    assert stage_info["status"] == "not_started"
    assert stage_info["started_at"] is None
    assert stage_info["duration_seconds"] is None
    assert stage_info["error"] is None


################################################################################
# Test: get_pending_content
################################################################################

def test_get_pending_content_stage_1(tracker):
    """Test getting pending content for stage 1 (no prerequisites)."""
    # Register 3 items
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    tracker.register_content("youtube_2", "youtube", "https://url2.com")
    tracker.register_content("youtube_3", "youtube", "https://url3.com")

    # Complete one, fail one, leave one not started
    tracker.start_stage("youtube_1", "stage_1_crawl")
    tracker.complete_stage("youtube_1", "stage_1_crawl", [], {})

    tracker.start_stage("youtube_2", "stage_1_crawl")
    tracker.fail_stage("youtube_2", "stage_1_crawl", "Error")

    # Get pending for stage 1
    pending = tracker.get_pending_content("stage_1_crawl")

    # Should return youtube_2 (failed, can retry) and youtube_3 (not started)
    assert set(pending) == {"youtube_2", "youtube_3"}


def test_get_pending_content_stage_2(tracker):
    """Test getting pending content for stage 2 (requires stage 1 complete)."""
    # Register 4 items
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    tracker.register_content("youtube_2", "youtube", "https://url2.com")
    tracker.register_content("youtube_3", "youtube", "https://url3.com")
    tracker.register_content("youtube_4", "youtube", "https://url4.com")

    # youtube_1: stage 1 complete, stage 2 not started -> should be included
    tracker.start_stage("youtube_1", "stage_1_crawl")
    tracker.complete_stage("youtube_1", "stage_1_crawl", [], {})

    # youtube_2: stage 1 complete, stage 2 complete -> should NOT be included
    tracker.start_stage("youtube_2", "stage_1_crawl")
    tracker.complete_stage("youtube_2", "stage_1_crawl", [], {})
    tracker.start_stage("youtube_2", "stage_2_chunk")
    tracker.complete_stage("youtube_2", "stage_2_chunk", [], {})

    # youtube_3: stage 1 complete, stage 2 failed -> should be included
    tracker.start_stage("youtube_3", "stage_1_crawl")
    tracker.complete_stage("youtube_3", "stage_1_crawl", [], {})
    tracker.start_stage("youtube_3", "stage_2_chunk")
    tracker.fail_stage("youtube_3", "stage_2_chunk", "Error")

    # youtube_4: stage 1 not complete -> should NOT be included
    tracker.start_stage("youtube_4", "stage_1_crawl")
    tracker.fail_stage("youtube_4", "stage_1_crawl", "Error")

    pending = tracker.get_pending_content("stage_2_chunk")

    assert set(pending) == {"youtube_1", "youtube_3"}


def test_get_pending_content_max_retries(tracker):
    """Test that items exceeding max retries are excluded."""
    tracker.register_content("youtube_1", "youtube", "https://url1.com")

    # Fail stage 1 three times
    for _ in range(3):
        tracker.start_stage("youtube_1", "stage_1_crawl")
        tracker.fail_stage("youtube_1", "stage_1_crawl", "Error")

    # After 3 fail cycles:
    # Cycle 1: fail (retry_count=1)
    # Cycle 2: start (retry_count=2), fail (retry_count=3)
    # Cycle 3: start (retry_count=4), fail (retry_count=5)
    # Final retry_count = 5

    # With max_retries=5, should still be included
    pending = tracker.get_pending_content("stage_1_crawl", max_retries=6)
    assert "youtube_1" in pending

    # But if max_retries=4, should be excluded
    pending = tracker.get_pending_content("stage_1_crawl", max_retries=4)
    assert "youtube_1" not in pending


def test_get_pending_content_empty(tracker):
    """Test getting pending content when none exist."""
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    tracker.start_stage("youtube_1", "stage_1_crawl")
    tracker.complete_stage("youtube_1", "stage_1_crawl", [], {})

    # No pending for stage 1 (all complete)
    pending = tracker.get_pending_content("stage_1_crawl")
    assert pending == []


################################################################################
# Test: get_stage_statistics
################################################################################

def test_get_stage_statistics_basic(tracker):
    """Test getting stage statistics."""
    # Register 5 items with different states
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    tracker.register_content("youtube_2", "youtube", "https://url2.com")
    tracker.register_content("youtube_3", "youtube", "https://url3.com")
    tracker.register_content("youtube_4", "youtube", "https://url4.com")
    tracker.register_content("youtube_5", "youtube", "https://url5.com")

    # youtube_1: not started
    # youtube_2: pending
    tracker.start_stage("youtube_2", "stage_1_crawl")
    # youtube_3: complete
    tracker.start_stage("youtube_3", "stage_1_crawl")
    tracker.complete_stage("youtube_3", "stage_1_crawl", [], {})
    # youtube_4: failed
    tracker.start_stage("youtube_4", "stage_1_crawl")
    tracker.fail_stage("youtube_4", "stage_1_crawl", "Error")
    # youtube_5: failed with retry
    tracker.start_stage("youtube_5", "stage_1_crawl")
    tracker.fail_stage("youtube_5", "stage_1_crawl", "Error")
    tracker.start_stage("youtube_5", "stage_1_crawl")
    tracker.fail_stage("youtube_5", "stage_1_crawl", "Error 2")

    stats = tracker.get_stage_statistics("stage_1_crawl")

    assert stats["total"] == 5
    assert stats["not_started"] == 1  # youtube_1
    assert stats["pending"] == 1      # youtube_2 (still pending)
    assert stats["complete"] == 1     # youtube_3
    assert stats["failed"] == 2       # youtube_4, youtube_5


def test_get_stage_statistics_empty(tracker):
    """Test statistics for empty tracker."""
    stats = tracker.get_stage_statistics("stage_1_crawl")

    assert stats["total"] == 0
    assert stats["not_started"] == 0
    assert stats["pending"] == 0
    assert stats["complete"] == 0
    assert stats["failed"] == 0


def test_get_stage_statistics_all_complete(tracker):
    """Test statistics when all items complete."""
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    tracker.register_content("youtube_2", "youtube", "https://url2.com")

    tracker.start_stage("youtube_1", "stage_1_crawl")
    tracker.complete_stage("youtube_1", "stage_1_crawl", [], {})
    tracker.start_stage("youtube_2", "stage_1_crawl")
    tracker.complete_stage("youtube_2", "stage_1_crawl", [], {})

    stats = tracker.get_stage_statistics("stage_1_crawl")

    assert stats["total"] == 2
    assert stats["complete"] == 2


################################################################################
# Test: S3 Integration (with mocking)
################################################################################

def test_save_to_s3(tracker, mock_s3_storage):
    """Test saving metadata to S3."""
    tracker.register_content("youtube_1", "youtube", "https://url1.com")

    # Verify S3 upload was called (happens automatically in register_content)
    assert mock_s3_storage.upload_jsonl.called

    # Check that data was passed
    call_args = mock_s3_storage.upload_jsonl.call_args
    data = call_args[1]['data']
    assert len(data) >= 1


def test_load_from_s3(mock_s3_storage):
    """Test loading metadata from S3."""
    # Setup mock to return sample data
    sample_data = [
        {
            "content_id": "youtube_1",
            "source": "youtube",
            "source_url": "https://url1.com",
            "added_at": "2024-01-15T10:00:00Z",
            "stages": {
                "stage_1_crawl": {
                    "status": "complete",
                    "started_at": "2024-01-15T10:00:00Z",
                    "completed_at": "2024-01-15T10:05:00Z",
                    "retry_count": 0,
                    "error": None,
                    "duration_seconds": 300,
                    "s3_paths": ["s3://bucket/path"],
                    "metadata": {}
                },
                "stage_2_chunk": {
                    "status": "not_started",
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                    "error": None,
                    "duration_seconds": None,
                    "s3_paths": [],
                    "metadata": {}
                },
                "stage_3_extract": {
                    "status": "not_started",
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                    "error": None,
                    "duration_seconds": None,
                    "s3_paths": [],
                    "metadata": {}
                },
                "stage_4_normalize": {
                    "status": "not_started",
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                    "error": None,
                    "duration_seconds": None,
                    "s3_paths": [],
                    "metadata": {}
                },
                "stage_5_embed": {
                    "status": "not_started",
                    "started_at": None,
                    "completed_at": None,
                    "retry_count": 0,
                    "error": None,
                    "duration_seconds": None,
                    "s3_paths": [],
                    "metadata": {}
                }
            },
            "pipeline_status": "stage_2_pending",
            "last_updated": "2024-01-15T10:05:00Z",
            "total_error_count": 0,
            "tags": []
        }
    ]
    mock_s3_storage.download_jsonl.return_value = sample_data

    # Create tracker (will call load_from_s3)
    tracker = MetadataTracker(mock_s3_storage)

    # Verify data loaded
    assert len(tracker._cache) == 1
    assert "youtube_1" in tracker._cache
    assert tracker._cache["youtube_1"]["stages"]["stage_1_crawl"]["status"] == "complete"


def test_load_from_s3_not_found(mock_s3_storage):
    """Test loading when S3 file doesn't exist."""
    from src.storage.s3 import S3StorageError

    # Setup mock to raise error
    mock_s3_storage.download_jsonl.side_effect = S3StorageError("File not found")

    # Create tracker (should handle error gracefully)
    tracker = MetadataTracker(mock_s3_storage)

    # Should create empty cache
    assert tracker._cache == {}


################################################################################
# Integration Tests
################################################################################

def test_full_workflow_single_item(tracker):
    """Test complete workflow for single item through all stages."""
    content_id = "youtube_test123"

    # Register
    tracker.register_content(content_id, "youtube", "https://youtube.com")
    assert tracker.content_exists(content_id)

    # Process through all stages
    for stage in tracker.STAGES:
        # Check it's pending
        pending = tracker.get_pending_content(stage)
        assert content_id in pending

        # Start stage
        tracker.start_stage(content_id, stage)
        assert tracker._cache[content_id]["stages"][stage]["status"] == "pending"

        # Complete stage
        tracker.complete_stage(content_id, stage, [f"s3://bucket/{stage}"], {"stage": stage})
        assert tracker._cache[content_id]["stages"][stage]["status"] == "complete"

    # Verify all stages complete
    for stage in tracker.STAGES:
        stats = tracker.get_stage_statistics(stage)
        assert stats["complete"] == 1


def test_full_workflow_with_failure_and_retry(tracker):
    """Test workflow with failure and retry."""
    content_id = "youtube_test123"

    tracker.register_content(content_id, "youtube", "https://youtube.com")

    # Stage 1: Fail first, then succeed
    tracker.start_stage(content_id, "stage_1_crawl")
    tracker.fail_stage(content_id, "stage_1_crawl", "Network error")

    assert tracker._cache[content_id]["stages"]["stage_1_crawl"]["status"] == "failed"
    # After fail, retry_count is 1
    assert tracker._cache[content_id]["stages"]["stage_1_crawl"]["retry_count"] == 1

    # Retry
    tracker.start_stage(content_id, "stage_1_crawl")
    # After restart, retry_count is 2
    assert tracker._cache[content_id]["stages"]["stage_1_crawl"]["retry_count"] == 2

    tracker.complete_stage(content_id, "stage_1_crawl", [], {})
    assert tracker._cache[content_id]["stages"]["stage_1_crawl"]["status"] == "complete"

    # Stage 2 should now be available
    pending = tracker.get_pending_content("stage_2_chunk")
    assert content_id in pending


def test_multiple_items_different_progress(tracker):
    """Test multiple items at different stages of progress."""
    # Item 1: Complete through stage 3
    tracker.register_content("youtube_1", "youtube", "https://url1.com")
    for stage in ["stage_1_crawl", "stage_2_chunk", "stage_3_extract"]:
        tracker.start_stage("youtube_1", stage)
        tracker.complete_stage("youtube_1", stage, [], {})

    # Item 2: Complete stage 1, pending stage 2
    tracker.register_content("youtube_2", "youtube", "https://url2.com")
    tracker.start_stage("youtube_2", "stage_1_crawl")
    tracker.complete_stage("youtube_2", "stage_1_crawl", [], {})
    tracker.start_stage("youtube_2", "stage_2_chunk")

    # Item 3: Failed stage 1
    tracker.register_content("youtube_3", "youtube", "https://url3.com")
    tracker.start_stage("youtube_3", "stage_1_crawl")
    tracker.fail_stage("youtube_3", "stage_1_crawl", "Error")

    # Item 4: Not started
    tracker.register_content("youtube_4", "youtube", "https://url4.com")

    # Check statistics
    stats_1 = tracker.get_stage_statistics("stage_1_crawl")
    assert stats_1["complete"] == 2  # youtube_1, youtube_2
    assert stats_1["failed"] == 1    # youtube_3
    assert stats_1["not_started"] == 1  # youtube_4

    stats_2 = tracker.get_stage_statistics("stage_2_chunk")
    assert stats_2["complete"] == 1  # youtube_1
    assert stats_2["pending"] == 1   # youtube_2

    stats_3 = tracker.get_stage_statistics("stage_3_extract")
    assert stats_3["complete"] == 1  # youtube_1

    # Check pending for stage 2
    pending_2 = tracker.get_pending_content("stage_2_chunk")
    # youtube_3 failed on stage 1, so NOT eligible for stage 2 (needs stage 1 complete)
    # youtube_2 already started stage 2 (pending), so not in pending list
    # Only items with stage 1 complete and stage 2 not started would be here
    assert "youtube_3" not in pending_2  # Stage 1 failed, can't proceed to stage 2
    assert "youtube_2" not in pending_2  # Already started stage 2

    # Check pending for stage 4
    pending_4 = tracker.get_pending_content("stage_4_normalize")
    assert "youtube_1" in pending_4  # Stage 3 complete, stage 4 not started
    assert "youtube_2" not in pending_4  # Stage 2 not complete yet
