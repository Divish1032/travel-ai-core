"""
Pydantic schemas for validating YouTube crawler data.

Defines the data models for YouTube video content, transcripts, and metadata
with comprehensive validation rules to ensure data quality.

Usage:
    from src.utils.schemas import YouTubeVideo, TranscriptSegment

    # Create and validate video data
    video = YouTubeVideo(
        source_id="abc123",
        source_url="https://youtube.com/watch?v=abc123",
        title="Best of Boracay 2024",
        author="TravelVlogger",
        author_url="https://youtube.com/@travelvlogger",
        published_date="2024-03-15",
        duration_seconds=847,
        language="en",
        transcript=[...],
        metadata={...}
    )

    # Export to dict for saving as JSONL
    video_dict = video.to_dict()
"""
from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    HttpUrl,
    ConfigDict
)
import re


class TranscriptSegment(BaseModel):
    """
    Represents a single segment of video transcript.

    Attributes:
        text: The transcript text for this segment
        start: Start time in seconds from beginning of video
        duration: Duration of this segment in seconds
    """
    text: str = Field(
        ...,
        description="Transcript text for this segment",
        min_length=1
    )
    start: float = Field(
        ...,
        description="Start time in seconds",
        ge=0.0
    )
    duration: float = Field(
        ...,
        description="Duration in seconds",
        gt=0.0
    )

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        """Ensure text is not just whitespace."""
        if not v.strip():
            raise ValueError("Transcript text cannot be empty or whitespace only")
        return v.strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Welcome to Boracay, the best beach in the Philippines",
                "start": 0.0,
                "duration": 3.5
            }
        }
    )


class VideoMetadata(BaseModel):
    """
    Metadata about the YouTube video.

    Attributes:
        view_count: Number of views
        like_count: Number of likes (optional, may be hidden)
        comment_count: Number of comments (optional, may be disabled)
        tags: List of video tags
        transcript_type: Type of transcript (manual/auto-generated)
    """
    view_count: int = Field(
        ...,
        description="Number of video views",
        ge=0
    )
    like_count: Optional[int] = Field(
        default=None,
        description="Number of likes (may be hidden by creator)",
        ge=0
    )
    comment_count: Optional[int] = Field(
        default=None,
        description="Number of comments (may be disabled)",
        ge=0
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Video tags/keywords"
    )
    transcript_type: Literal["manual", "auto-generated", "unknown"] = Field(
        default="unknown",
        description="Type of transcript available"
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Clean and validate tags."""
        # Remove empty tags and strip whitespace
        cleaned = [tag.strip() for tag in v if tag.strip()]
        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in cleaned:
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)
        return unique_tags

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "view_count": 15420,
                "like_count": 892,
                "comment_count": 45,
                "tags": ["boracay", "travel", "philippines", "beach"],
                "transcript_type": "auto-generated"
            }
        }
    )


class Provenance(BaseModel):
    """
    Provenance and licensing information for the content.

    Attributes:
        can_redistribute: Whether content can be redistributed
        attribution_required: Whether attribution to original creator is required
        tos_version: Version of terms of service under which content was collected
    """
    can_redistribute: bool = Field(
        default=False,
        description="Whether this content can be redistributed"
    )
    attribution_required: bool = Field(
        default=True,
        description="Whether attribution to original creator is required"
    )
    tos_version: str = Field(
        default="youtube_tos_2024",
        description="Version of terms of service"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "can_redistribute": False,
                "attribution_required": True,
                "tos_version": "youtube_tos_2024"
            }
        }
    )


class YouTubeVideo(BaseModel):
    """
    Complete YouTube video data model with transcript and metadata.

    This model represents all data crawled from a YouTube video including
    the video metadata, transcript segments, and provenance information.
    """
    # Source information
    source: Literal["youtube"] = Field(
        default="youtube",
        description="Content source platform"
    )
    source_id: str = Field(
        ...,
        description="YouTube video ID",
        min_length=1
    )
    source_url: str = Field(
        ...,
        description="Full YouTube video URL"
    )

    # Content classification
    content_type: Literal["vlog", "documentary", "tutorial", "review", "other"] = Field(
        default="vlog",
        description="Type of travel content"
    )

    # Video information
    title: str = Field(
        ...,
        description="Video title",
        min_length=1
    )
    author: str = Field(
        ...,
        description="Channel/creator name",
        min_length=1
    )
    author_url: str = Field(
        ...,
        description="YouTube channel URL"
    )
    published_date: str = Field(
        ...,
        description="Publication date in YYYY-MM-DD format"
    )
    duration_seconds: int = Field(
        ...,
        description="Video duration in seconds",
        gt=0
    )
    language: str = Field(
        ...,
        description="ISO 639-1 language code (2 letters)",
        min_length=2,
        max_length=2
    )

    # Content
    transcript: List[TranscriptSegment] = Field(
        ...,
        description="List of transcript segments",
        min_length=1
    )

    # Metadata
    metadata: VideoMetadata = Field(
        ...,
        description="Video metadata and statistics"
    )

    # Provenance
    provenance: Provenance = Field(
        default_factory=Provenance,
        description="Content provenance and licensing information"
    )

    # Tracking
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when data was fetched"
    )
    fetched_by: str = Field(
        default="crawler_v1",
        description="Version of crawler that fetched this data"
    )

    @field_validator("source_url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        """Validate that the URL is a valid YouTube video URL."""
        youtube_patterns = [
            r'^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'^https?://(?:www\.)?youtu\.be/[\w-]+',
            r'^https?://(?:www\.)?youtube\.com/embed/[\w-]+'
        ]

        if not any(re.match(pattern, v) for pattern in youtube_patterns):
            raise ValueError(
                f"Invalid YouTube URL format: {v}. "
                "Expected format: https://youtube.com/watch?v=VIDEO_ID"
            )
        return v

    @field_validator("author_url")
    @classmethod
    def validate_channel_url(cls, v: str) -> str:
        """Validate that the author URL is a valid YouTube channel URL."""
        channel_patterns = [
            r'^https?://(?:www\.)?youtube\.com/@[\w-]+',
            r'^https?://(?:www\.)?youtube\.com/channel/[\w-]+',
            r'^https?://(?:www\.)?youtube\.com/c/[\w-]+',
            r'^https?://(?:www\.)?youtube\.com/user/[\w-]+'
        ]

        if not any(re.match(pattern, v) for pattern in channel_patterns):
            raise ValueError(
                f"Invalid YouTube channel URL format: {v}. "
                "Expected format: https://youtube.com/@channel or /channel/ID"
            )
        return v

    @field_validator("published_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate that published_date is in YYYY-MM-DD format."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"Invalid date format: {v}. Expected YYYY-MM-DD format"
            )
        return v

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        """Validate that language is a valid ISO 639-1 code."""
        # Common language codes - extend as needed
        valid_codes = {
            "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh",
            "ar", "hi", "nl", "sv", "no", "da", "fi", "pl", "tr", "id",
            "th", "vi", "ms", "tl", "el", "he", "cs", "ro", "hu", "uk"
        }

        v_lower = v.lower()
        if v_lower not in valid_codes:
            raise ValueError(
                f"Invalid language code: {v}. Must be valid ISO 639-1 code. "
                f"Common codes: {', '.join(sorted(list(valid_codes)[:10]))}, ..."
            )
        return v_lower

    @model_validator(mode="after")
    def validate_transcript_sequence(self) -> "YouTubeVideo":
        """Validate that transcript segments are in sequential order."""
        if not self.transcript:
            raise ValueError("Transcript cannot be empty")

        for i in range(len(self.transcript) - 1):
            current = self.transcript[i]
            next_segment = self.transcript[i + 1]

            # Next segment should start at or after current segment starts
            if next_segment.start < current.start:
                raise ValueError(
                    f"Transcript segments not in order: segment {i+1} starts at "
                    f"{next_segment.start}s but segment {i} starts at {current.start}s"
                )

        return self

    @model_validator(mode="after")
    def validate_source_id_matches_url(self) -> "YouTubeVideo":
        """Validate that source_id is present in source_url."""
        if self.source_id not in self.source_url:
            raise ValueError(
                f"source_id '{self.source_id}' not found in source_url '{self.source_url}'"
            )
        return self

    def to_dict(self) -> Dict[str, Any]:
        """
        Export model to dictionary for JSONL serialization.

        Returns:
            Dictionary representation with datetime converted to ISO format
        """
        data = self.model_dump()
        # Convert datetime to ISO string for JSON serialization
        data["fetched_at"] = self.fetched_at.isoformat() + "Z"
        return data

    def get_full_transcript_text(self) -> str:
        """
        Get complete transcript as a single string.

        Returns:
            Full transcript text with segments joined by spaces
        """
        return " ".join(segment.text for segment in self.transcript)

    def get_transcript_duration(self) -> float:
        """
        Calculate total duration covered by transcript segments.

        Returns:
            Total duration in seconds
        """
        if not self.transcript:
            return 0.0
        last_segment = self.transcript[-1]
        return last_segment.start + last_segment.duration

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "youtube",
                "source_id": "abc123xyz",
                "source_url": "https://youtube.com/watch?v=abc123xyz",
                "content_type": "vlog",
                "title": "Best of Boracay 2024 - Philippines Travel Guide",
                "author": "TravelVlogger",
                "author_url": "https://youtube.com/@travelvlogger",
                "published_date": "2024-03-15",
                "duration_seconds": 847,
                "language": "en",
                "transcript": [
                    {"text": "Welcome to Boracay", "start": 0.0, "duration": 2.5},
                    {"text": "The best beach in the Philippines", "start": 2.5, "duration": 3.0}
                ],
                "metadata": {
                    "view_count": 15420,
                    "like_count": 892,
                    "comment_count": 45,
                    "tags": ["boracay", "travel", "philippines"],
                    "transcript_type": "auto-generated"
                },
                "fetched_at": "2025-11-02T10:30:00Z",
                "fetched_by": "crawler_v1",
                "provenance": {
                    "can_redistribute": False,
                    "attribution_required": True,
                    "tos_version": "youtube_tos_2024"
                }
            }
        }
    )


# Example usage and testing
if __name__ == "__main__":
    from pydantic import ValidationError

    print("=" * 70)
    print("TESTING YOUTUBE VIDEO SCHEMAS")
    print("=" * 70)

    # Test 1: Valid video data
    print("\n1. Testing VALID video data...")
    try:
        valid_video = YouTubeVideo(
            source_id="abc123xyz",
            source_url="https://youtube.com/watch?v=abc123xyz",
            content_type="vlog",
            title="Best of Boracay 2024 - Philippines Travel Guide",
            author="TravelVlogger",
            author_url="https://youtube.com/@travelvlogger",
            published_date="2024-03-15",
            duration_seconds=847,
            language="en",
            transcript=[
                TranscriptSegment(text="Welcome to Boracay", start=0.0, duration=2.5),
                TranscriptSegment(text="The best beach in the Philippines", start=2.5, duration=3.0),
                TranscriptSegment(text="Let me show you around", start=5.5, duration=2.0)
            ],
            metadata=VideoMetadata(
                view_count=15420,
                like_count=892,
                comment_count=45,
                tags=["boracay", "travel", "philippines", "beach"],
                transcript_type="auto-generated"
            )
        )
        print("✓ Valid video created successfully!")
        print(f"  Title: {valid_video.title}")
        print(f"  Duration: {valid_video.duration_seconds}s")
        print(f"  Transcript segments: {len(valid_video.transcript)}")
        print(f"  Full text: {valid_video.get_full_transcript_text()[:50]}...")
        print(f"  Transcript duration: {valid_video.get_transcript_duration()}s")
    except ValidationError as e:
        print(f"✗ Unexpected validation error: {e}")

    # Test 2: Invalid duration (must be > 0)
    print("\n2. Testing INVALID duration (must be > 0)...")
    try:
        invalid_video = YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@testauthor",
            published_date="2024-01-01",
            duration_seconds=0,  # Invalid!
            language="en",
            transcript=[
                TranscriptSegment(text="Test", start=0.0, duration=1.0)
            ],
            metadata=VideoMetadata(view_count=100)
        )
        print("✗ Should have raised validation error!")
    except ValidationError as e:
        print(f"✓ Correctly rejected: duration must be > 0")

    # Test 3: Invalid language code
    print("\n3. Testing INVALID language code...")
    try:
        invalid_video = YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@testauthor",
            published_date="2024-01-01",
            duration_seconds=100,
            language="xyz",  # Invalid!
            transcript=[
                TranscriptSegment(text="Test", start=0.0, duration=1.0)
            ],
            metadata=VideoMetadata(view_count=100)
        )
        print("✗ Should have raised validation error!")
    except ValidationError as e:
        print(f"✓ Correctly rejected: invalid language code")

    # Test 4: Out of sequence transcript
    print("\n4. Testing OUT OF SEQUENCE transcript segments...")
    try:
        invalid_video = YouTubeVideo(
            source_id="test123",
            source_url="https://youtube.com/watch?v=test123",
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@testauthor",
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
        print("✗ Should have raised validation error!")
    except ValidationError as e:
        print(f"✓ Correctly rejected: transcript segments not sequential")

    # Test 5: Invalid YouTube URL
    print("\n5. Testing INVALID YouTube URL...")
    try:
        invalid_video = YouTubeVideo(
            source_id="test123",
            source_url="https://vimeo.com/123456",  # Not YouTube!
            title="Test Video",
            author="Test Author",
            author_url="https://youtube.com/@testauthor",
            published_date="2024-01-01",
            duration_seconds=100,
            language="en",
            transcript=[
                TranscriptSegment(text="Test", start=0.0, duration=1.0)
            ],
            metadata=VideoMetadata(view_count=100)
        )
        print("✗ Should have raised validation error!")
    except ValidationError as e:
        print(f"✓ Correctly rejected: invalid YouTube URL format")

    # Test 6: Export to dict
    print("\n6. Testing EXPORT to dict for JSONL...")
    video_dict = valid_video.to_dict()
    print(f"✓ Exported to dict with {len(video_dict)} keys")
    print(f"  Keys: {', '.join(list(video_dict.keys())[:5])}...")

    print("\n" + "=" * 70)
    print("All schema validation tests completed!")
    print("=" * 70)
