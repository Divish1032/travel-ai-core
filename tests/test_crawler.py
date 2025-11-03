"""
Test suite for YouTube crawler functionality.

Tests cover:
- Video ID extraction from various URL formats
- Video metadata fetching
- Transcript fetching
- End-to-end crawling
- Schema validation
- S3 storage operations (mocked)

Run with:
    pytest tests/test_crawler.py -v
    pytest tests/test_crawler.py::test_extract_video_id -v
"""
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from pydantic import ValidationError
from moto import mock_aws
import boto3

from src.crawlers.youtube import (
    extract_video_id,
    fetch_video_metadata,
    fetch_transcript,
    crawl_video
)
from src.utils.schemas import (
    YouTubeVideo,
    TranscriptSegment,
    VideoMetadata,
    Provenance
)
from src.storage.s3 import S3Storage


################################################################################
# Fixtures
################################################################################

@pytest.fixture
def sample_video_id():
    """Sample YouTube video ID for testing."""
    # Using "Rick Astley - Never Gonna Give You Up" - reliable English transcript
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_youtube_url(sample_video_id):
    """Sample YouTube URL for testing."""
    return f"https://www.youtube.com/watch?v={sample_video_id}"


@pytest.fixture
def sample_transcript_segments():
    """Sample transcript segments for testing."""
    return [
        TranscriptSegment(text="Welcome to Boracay", start=0.0, duration=2.5),
        TranscriptSegment(text="The best beach in the Philippines", start=2.5, duration=3.0),
        TranscriptSegment(text="Let me show you around", start=5.5, duration=2.0)
    ]


@pytest.fixture
def sample_video_metadata():
    """Sample video metadata for testing."""
    return VideoMetadata(
        view_count=15420,
        like_count=892,
        comment_count=45,
        tags=["boracay", "travel", "philippines", "beach"],
        transcript_type="auto-generated"
    )


@pytest.fixture
def sample_video_data(sample_video_id, sample_transcript_segments, sample_video_metadata):
    """Complete sample YouTubeVideo object."""
    return YouTubeVideo(
        source="youtube",
        source_id=sample_video_id,
        source_url=f"https://www.youtube.com/watch?v={sample_video_id}",
        content_type="vlog",
        title="Best of Boracay 2024 - Philippines Travel Guide",
        author="TravelVlogger",
        author_url="https://youtube.com/@travelvlogger",
        published_date="2024-03-15",
        duration_seconds=847,
        language="en",
        transcript=sample_transcript_segments,
        metadata=sample_video_metadata,
        provenance=Provenance(),
        fetched_at=datetime.now(timezone.utc),
        fetched_by="crawler_v1"
    )


################################################################################
# Test: extract_video_id
################################################################################

def test_extract_video_id_standard_url():
    """Test extraction from standard YouTube URL."""
    url = "https://www.youtube.com/watch?v=abc123xyz"
    video_id = extract_video_id(url)
    assert video_id == "abc123xyz"


def test_extract_video_id_short_url():
    """Test extraction from short youtu.be URL."""
    url = "https://youtu.be/abc123xyz"
    video_id = extract_video_id(url)
    assert video_id == "abc123xyz"


def test_extract_video_id_embed_url():
    """Test extraction from embed URL."""
    url = "https://www.youtube.com/embed/abc123xyz"
    video_id = extract_video_id(url)
    assert video_id == "abc123xyz"


def test_extract_video_id_mobile_url():
    """Test extraction from mobile URL."""
    url = "https://m.youtube.com/watch?v=abc123xyz"
    video_id = extract_video_id(url)
    assert video_id == "abc123xyz"


def test_extract_video_id_with_parameters():
    """Test extraction from URL with additional parameters."""
    url = "https://www.youtube.com/watch?v=abc123xyz&t=30s&list=PLxxx"
    video_id = extract_video_id(url)
    assert video_id == "abc123xyz"


def test_extract_video_id_invalid_url():
    """Test that invalid URL raises ValueError."""
    url = "https://vimeo.com/123456"
    with pytest.raises(ValueError, match="Could not extract video ID"):
        extract_video_id(url)


################################################################################
# Test: fetch_video_metadata
################################################################################

def test_fetch_video_metadata_success_mocked():
    """Test fetching video metadata with mocked YouTube API v3 response."""
    video_id = "dQw4w9WgXcQ"

    # Mock YouTube API v3 response
    mock_api_response = {
        'items': [{
            'id': video_id,
            'snippet': {
                'title': 'Rick Astley - Never Gonna Give You Up',
                'channelTitle': 'Rick Astley',
                'channelId': 'UCuAXFkgsw1L7xaCfnd5JJOw',
                'publishedAt': '2009-10-25T06:57:33Z',
                'description': 'The official video for "Never Gonna Give You Up"',
                'tags': ['Rick Astley', 'Never Gonna Give You Up', 'Music']
            },
            'contentDetails': {
                'duration': 'PT3M33S'  # 3 minutes 33 seconds = 213 seconds
            },
            'statistics': {
                'viewCount': '1000000000',
                'likeCount': '15000000',
                'commentCount': '2500000'
            }
        }]
    }

    # Mock config to have API key
    mock_config_obj = MagicMock()
    mock_config_obj.YOUTUBE_API_KEY = 'test_api_key'

    # Mock the YouTube API client
    with patch('src.crawlers.youtube.build') as mock_build:
        mock_youtube = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()

        mock_list.execute.return_value = mock_api_response
        mock_videos.list.return_value = mock_list
        mock_youtube.videos.return_value = mock_videos
        mock_build.return_value = mock_youtube

        with patch('src.utils.config.config', mock_config_obj):
            metadata = fetch_video_metadata(video_id)

    # Check all fields
    assert metadata['video_id'] == video_id
    assert metadata['title'] == 'Rick Astley - Never Gonna Give You Up'
    assert metadata['author'] == 'Rick Astley'
    assert metadata['channel_url'] == 'https://youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw'
    assert metadata['duration_seconds'] == 213  # 3:33
    assert metadata['published_date'] == '2009-10-25'
    assert metadata['view_count'] == 1000000000
    assert metadata['like_count'] == 15000000  # New with official API!
    assert metadata['comment_count'] == 2500000  # New with official API!
    assert 'Never Gonna Give You Up' in metadata['description']
    assert 'Rick Astley' in metadata['keywords']


@pytest.mark.integration
def test_fetch_video_metadata_success_real(sample_video_id):
    """
    Test fetching real video metadata using actual YouTube API v3.

    Note: This is an integration test that makes real API calls.
    Requires YOUTUBE_API_KEY in .env - will be skipped if not present
    """
    from src.utils.config import config

    # Skip if API key not configured
    if not config or not config.YOUTUBE_API_KEY:
        pytest.skip("YouTube API key not configured. Set YOUTUBE_API_KEY in .env to run this test.")

    metadata = fetch_video_metadata(sample_video_id)

    # Check required fields
    assert metadata['video_id'] == sample_video_id
    assert metadata['title'] is not None
    assert len(metadata['title']) > 0
    assert metadata['author'] is not None
    assert metadata['duration_seconds'] > 0
    assert metadata['view_count'] >= 0
    assert metadata['like_count'] >= 0  # New field!
    assert metadata['published_date'] is not None


def test_fetch_video_metadata_no_api_key():
    """Test that missing API key raises clear error."""
    from src.crawlers.base import FetchError

    mock_config_obj = MagicMock()
    mock_config_obj.YOUTUBE_API_KEY = None

    with patch('src.utils.config.config', mock_config_obj):
        with pytest.raises(FetchError, match="YouTube API key not configured"):
            fetch_video_metadata("dQw4w9WgXcQ")


def test_fetch_video_metadata_invalid_id():
    """Test that invalid video ID raises FetchError."""
    from src.crawlers.base import FetchError

    # Mock API response for non-existent video
    mock_api_response = {'items': []}  # Empty response = video not found

    mock_config_obj = MagicMock()
    mock_config_obj.YOUTUBE_API_KEY = 'test_api_key'

    with patch('src.crawlers.youtube.build') as mock_build:
        mock_youtube = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()

        mock_list.execute.return_value = mock_api_response
        mock_videos.list.return_value = mock_list
        mock_youtube.videos.return_value = mock_videos
        mock_build.return_value = mock_youtube

        with patch('src.utils.config.config', mock_config_obj):
            with pytest.raises(FetchError, match="Video not found"):
                fetch_video_metadata("INVALID_VIDEO_ID_12345")


################################################################################
# Test: fetch_transcript
################################################################################

@pytest.mark.integration
def test_fetch_transcript_success(sample_video_id):
    """
    Test fetching real video transcript.

    Note: This is an integration test that makes real API calls.
    """
    transcript = fetch_transcript(sample_video_id, language="en")

    # Check transcript structure
    if transcript is not None:  # Some videos may not have transcripts
        assert isinstance(transcript, list)
        assert len(transcript) > 0

        # Check first segment structure
        first_segment = transcript[0]
        assert 'text' in first_segment
        assert 'start' in first_segment
        assert 'duration' in first_segment
        assert isinstance(first_segment['start'], (int, float))
        assert isinstance(first_segment['duration'], (int, float))


def test_fetch_transcript_no_transcript():
    """Test handling of video without transcript."""
    # Use a video ID that likely doesn't have transcripts
    video_id = "NOVIDEO12345"
    transcript = fetch_transcript(video_id)

    # Should return None for videos without transcripts
    assert transcript is None


################################################################################
# Test: crawl_video (end-to-end)
################################################################################

@pytest.mark.integration
@pytest.mark.slow
def test_crawl_video_success(sample_youtube_url):
    """
    Test end-to-end video crawling with real URL.

    Note: This is a slow integration test.
    Skip with: pytest -m "not slow"
    """
    video = crawl_video(sample_youtube_url, max_retries=2)

    if video is None:
        pytest.skip("Video doesn't have English transcript")

    # Validate result is YouTubeVideo instance
    assert isinstance(video, YouTubeVideo)

    # Check core fields
    assert video.source == "youtube"
    assert video.source_id is not None
    assert video.title is not None
    assert len(video.title) > 0
    assert video.author is not None
    assert video.duration_seconds > 0
    assert video.language == "en"

    # Check transcript
    assert len(video.transcript) > 0
    assert all(isinstance(seg, TranscriptSegment) for seg in video.transcript)

    # Check metadata
    assert video.metadata.view_count >= 0

    # Check transcript is sequential
    for i in range(len(video.transcript) - 1):
        current = video.transcript[i]
        next_seg = video.transcript[i + 1]
        assert next_seg.start >= current.start


def test_crawl_video_success_mocked():
    """Test end-to-end video crawling with mocked API calls (unit test)."""
    test_url = "https://youtube.com/watch?v=dQw4w9WgXcQ"

    # Mock fetch_video_metadata (with all required fields for new API)
    mock_metadata = {
        'video_id': 'dQw4w9WgXcQ',
        'url': test_url,
        'title': 'Rick Astley - Never Gonna Give You Up',
        'author': 'Rick Astley',
        'channel_url': 'https://youtube.com/@RickAstley',
        'duration_seconds': 213,
        'published_date': '2009-10-25',
        'view_count': 1000000,
        'like_count': 15000,  # Required for YouTube Data API v3
        'comment_count': 2500,  # Required for YouTube Data API v3
        'description': 'The official video',
        'keywords': ['music', 'pop', '80s']
    }

    # Mock fetch_transcript (Whisper-based format with float timestamps)
    mock_transcript = [
        {'text': 'We\'re no strangers to love', 'start': 0.0, 'duration': 2.5},
        {'text': 'You know the rules and so do I', 'start': 2.5, 'duration': 3.0},
        {'text': 'A full commitment\'s what I\'m thinking of', 'start': 5.5, 'duration': 3.5}
    ]

    with patch('src.crawlers.youtube.fetch_video_metadata', return_value=mock_metadata):
        with patch('src.crawlers.youtube.fetch_transcript', return_value=mock_transcript):
            video = crawl_video(test_url, max_retries=2, show_progress=False)

    # Validate result is YouTubeVideo instance
    assert video is not None
    assert isinstance(video, YouTubeVideo)

    # Check core fields
    assert video.source == "youtube"
    assert video.source_id == "dQw4w9WgXcQ"
    assert video.title == "Rick Astley - Never Gonna Give You Up"
    assert video.author == "Rick Astley"
    assert video.duration_seconds == 213
    assert video.language == "en"

    # Check transcript
    assert len(video.transcript) == 3
    assert all(isinstance(seg, TranscriptSegment) for seg in video.transcript)
    assert video.transcript[0].text == "We're no strangers to love"

    # Check metadata (including new fields)
    assert video.metadata.view_count == 1000000
    assert video.metadata.like_count == 15000
    assert video.metadata.comment_count == 2500
    assert video.metadata.transcript_type == "whisper"  # Whisper transcription

    # Check transcript is sequential
    for i in range(len(video.transcript) - 1):
        current = video.transcript[i]
        next_seg = video.transcript[i + 1]
        assert next_seg.start >= current.start


def test_crawl_video_invalid_url():
    """Test that invalid URL returns None."""
    invalid_url = "https://vimeo.com/123456"
    video = crawl_video(invalid_url, max_retries=1)
    assert video is None


@pytest.mark.integration
def test_crawl_video_no_transcript():
    """Test handling of video without transcript."""
    # This would need a video ID known to not have transcripts
    # For now, we'll mock it
    with patch('src.crawlers.youtube.fetch_transcript', return_value=None):
        with patch('src.crawlers.youtube.fetch_video_metadata', return_value={
            'video_id': 'test123',
            'url': 'https://youtube.com/watch?v=test123',
            'title': 'Test Video',
            'author': 'Test Author',
            'channel_url': 'https://youtube.com/@test',
            'duration_seconds': 100,
            'published_date': '2024-01-01',
            'view_count': 1000,
            'like_count': 50,  # Required field
            'comment_count': 10,  # Required field
            'description': 'Test description',
            'keywords': []
        }):
            video = crawl_video("https://youtube.com/watch?v=test123", show_progress=False)
            assert video is None  # Should return None when no transcript


################################################################################
# Test: Schema Validation
################################################################################

def test_schema_validation_valid_data(sample_video_data):
    """Test that valid data passes schema validation."""
    # Should not raise any exceptions
    assert sample_video_data.source == "youtube"
    assert len(sample_video_data.transcript) == 3

    # Test serialization
    data_dict = sample_video_data.to_dict()
    assert isinstance(data_dict, dict)
    assert data_dict['source'] == "youtube"


def test_schema_validation_invalid_duration():
    """Test that invalid duration fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@test",
            published_date="2024-01-01",
            duration_seconds=0,  # Invalid: must be > 0
            language="en",
            transcript=[
                TranscriptSegment(text="Test", start=0.0, duration=1.0)
            ],
            metadata=VideoMetadata(view_count=100)
        )

    assert "duration_seconds" in str(exc_info.value)


def test_schema_validation_invalid_language():
    """Test that invalid language code fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@test",
            published_date="2024-01-01",
            duration_seconds=100,
            language="xyz",  # Invalid language code
            transcript=[
                TranscriptSegment(text="Test", start=0.0, duration=1.0)
            ],
            metadata=VideoMetadata(view_count=100)
        )

    assert "language" in str(exc_info.value)


def test_schema_validation_out_of_sequence_transcript():
    """Test that out-of-sequence transcript fails validation."""
    with pytest.raises(ValidationError) as exc_info:
        YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@test",
            published_date="2024-01-01",
            duration_seconds=100,
            language="en",
            transcript=[
                TranscriptSegment(text="First", start=0.0, duration=1.0),
                TranscriptSegment(text="Third", start=10.0, duration=1.0),
                TranscriptSegment(text="Second", start=5.0, duration=1.0)  # Out of order!
            ],
            metadata=VideoMetadata(view_count=100)
        )

    assert "not in order" in str(exc_info.value)


def test_schema_validation_empty_transcript():
    """Test that empty transcript fails validation."""
    with pytest.raises(ValidationError):
        YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@test",
            published_date="2024-01-01",
            duration_seconds=100,
            language="en",
            transcript=[],  # Empty transcript
            metadata=VideoMetadata(view_count=100)
        )

    # Should fail validation
    assert True  # If we get here, validation failed as expected


################################################################################
# Test: S3 Storage (Mocked)
################################################################################

@mock_aws
def test_s3_upload_jsonl(sample_video_data):
    """Test uploading video data to S3 (mocked)."""
    # Create mock S3 bucket
    bucket_name = "test-travel-ai-bucket"
    conn = boto3.resource('s3', region_name='us-east-1')
    conn.create_bucket(Bucket=bucket_name)

    # Mock config
    with patch('src.storage.s3.config') as mock_config:
        mock_config.S3_BUCKET_NAME = bucket_name
        mock_config.AWS_REGION = 'us-east-1'
        mock_config.AWS_ACCESS_KEY_ID = 'test_key'
        mock_config.AWS_SECRET_ACCESS_KEY = 'test_secret'

        # Create storage instance
        storage = S3Storage()

        # Upload data
        video_dicts = [sample_video_data.to_dict()]
        s3_uri = storage.upload_jsonl(
            data=video_dicts,
            source="youtube",
            data_type="videos"
        )

        # Verify upload
        assert s3_uri.startswith(f"s3://{bucket_name}/raw/youtube/videos/")
        assert s3_uri.endswith(".jsonl")

        # Verify file exists
        assert storage.file_exists(s3_uri)


@mock_aws
def test_s3_download_jsonl(sample_video_data):
    """Test downloading video data from S3 (mocked)."""
    # Create mock S3 bucket
    bucket_name = "test-travel-ai-bucket"
    conn = boto3.resource('s3', region_name='us-east-1')
    conn.create_bucket(Bucket=bucket_name)

    # Mock config
    with patch('src.storage.s3.config') as mock_config:
        mock_config.S3_BUCKET_NAME = bucket_name
        mock_config.AWS_REGION = 'us-east-1'
        mock_config.AWS_ACCESS_KEY_ID = 'test_key'
        mock_config.AWS_SECRET_ACCESS_KEY = 'test_secret'

        storage = S3Storage()

        # Upload data
        video_dicts = [sample_video_data.to_dict()]
        s3_uri = storage.upload_jsonl(
            data=video_dicts,
            source="youtube",
            data_type="videos"
        )

        # Download data
        downloaded = storage.download_jsonl(s3_uri)

        # Verify downloaded data
        assert len(downloaded) == 1
        assert downloaded[0]['source_id'] == sample_video_data.source_id
        assert downloaded[0]['title'] == sample_video_data.title


@mock_aws
def test_s3_list_files():
    """Test listing files in S3 (mocked)."""
    # Create mock S3 bucket
    bucket_name = "test-travel-ai-bucket"
    conn = boto3.resource('s3', region_name='us-east-1')
    conn.create_bucket(Bucket=bucket_name)

    # Mock config
    with patch('src.storage.s3.config') as mock_config:
        mock_config.S3_BUCKET_NAME = bucket_name
        mock_config.AWS_REGION = 'us-east-1'
        mock_config.AWS_ACCESS_KEY_ID = 'test_key'
        mock_config.AWS_SECRET_ACCESS_KEY = 'test_secret'

        storage = S3Storage()

        # Upload multiple files with unique custom paths
        import time
        for i in range(3):
            data = [{'id': i, 'name': f'video_{i}'}]
            custom_path = f"raw/youtube/videos/2024-11/batch_test_{i}.jsonl"
            storage.upload_jsonl(data, source="youtube", data_type="videos", custom_path=custom_path)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # List files
        files = storage.list_files("raw/youtube/videos/")

        # Verify
        assert len(files) == 3
        assert all(f.startswith(f"s3://{bucket_name}/") for f in files)


################################################################################
# Test Markers Configuration
################################################################################

# To run only unit tests (fast):
#   pytest tests/test_crawler.py -m "not integration and not slow"
#
# To run all tests including integration:
#   pytest tests/test_crawler.py
#
# To run with verbose output:
#   pytest tests/test_crawler.py -v -s
