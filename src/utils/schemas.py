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
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    HttpUrl,
    ConfigDict
)
import re


def _utc_now() -> datetime:
    """Helper function to get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


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
    transcript_type: Literal["manual", "auto-generated", "whisper", "unknown"] = Field(
        default="unknown",
        description="Type of transcript available (whisper = generated with OpenAI Whisper)"
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
        default_factory=_utc_now,
        description="Timestamp when data was fetched (timezone-aware UTC)"
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


# ============================================================================
# STAGE 2 SCHEMAS: Entity Extraction Output
# ============================================================================

class TravelerProfile(BaseModel):
    """
    Represents the traveler profile extracted from video content.

    Captures demographics and travel preferences of the vlogger.
    """
    traveler_type: Literal["solo", "couple", "family", "group", "unknown"] = Field(
        default="unknown",
        description="Type of traveler (solo, couple, family, group)"
    )

    age_range: Optional[Literal["18-25", "26-35", "36-50", "50+", "unknown"]] = Field(
        default="unknown",
        description="Estimated age range of traveler"
    )

    budget_tier: Literal["budget", "mid-range", "luxury", "unknown"] = Field(
        default="unknown",
        description="Budget tier based on mentioned costs and activities"
    )

    travel_style: List[str] = Field(
        default_factory=list,
        description="Travel style tags (e.g., adventure, relaxation, cultural, foodie)"
    )

    confidence_score: float = Field(
        ge=0.1,
        le=1.0,
        description="LLM confidence score for profile extraction (0.1-1.0). REQUIRED. Minimum 0.1 (0.0 reserved for errors)."
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )


class EntityExperience(BaseModel):
    """
    Represents a single entity (place, activity) mentioned in the video.

    Captures location, experience details, and sentiment.
    """
    entity_name: str = Field(
        min_length=1,
        max_length=500,
        description="Name of the entity (place, restaurant, activity)"
    )

    entity_type: Literal[
        "destination",
        "restaurant",
        "hotel",
        "activity",
        "attraction",
        "transportation",
        "shopping",
        "unknown"
    ] = Field(
        description="Type of entity"
    )

    location: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Location/address of entity (city, country)"
    )

    experience: str = Field(
        min_length=10,
        max_length=2000,
        description="Summary of experience at this entity"
    )

    sentiment: Literal["positive", "negative", "neutral", "mixed"] = Field(
        description="Sentiment about the experience"
    )

    cost_mentioned: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Cost mentioned (e.g., '$50', '₹2000', 'free')"
    )

    timestamp_start: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Timestamp in video where entity is mentioned (seconds)"
    )

    confidence_score: float = Field(
        ge=0.1,
        le=1.0,
        description="LLM confidence score for entity extraction (0.1-1.0). REQUIRED. Minimum 0.1 (0.0 reserved for errors)."
    )

    # =============================================================================
    # HIGH-VALUE ENHANCEMENTS: Temporal, Cost, and Practical Information
    # =============================================================================

    # Temporal Information
    best_time_to_visit: Optional[List[str]] = Field(
        default=None,
        description="Best seasons/months/times: ['summer', 'december', 'early_morning', 'shoulder_season']"
    )

    visit_duration: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Recommended time to spend: '2-3 hours', 'half day', 'full day', '2 days'"
    )

    time_of_day: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Best time: 'morning', 'sunset', 'night', 'avoid_midday', 'early_morning'"
    )

    seasonal_notes: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Season-specific tips: 'crowded in summer', 'closed in winter', 'best in fall'"
    )

    # Cost Information
    price_range: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Budget tier: 'free', 'budget' (<$20), 'mid' ($20-100), 'high' (>$100)"
    )

    specific_prices: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Specific prices: {'entrance': 15, 'guided_tour': 50, 'currency': 'USD'}"
    )

    value_rating: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Value assessment: 'worth_it', 'overpriced', 'good_value', 'skip'"
    )

    # Practical Logistics
    booking_info: Optional[str] = Field(
        default=None,
        max_length=300,
        description="How to book: 'book online in advance', 'walk-in only', 'reserve 1 week ahead'"
    )

    accessibility: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Accessibility: 'wheelchair accessible', 'steep stairs', 'elevator available'"
    )

    transport_access: Optional[str] = Field(
        default=None,
        max_length=300,
        description="How to reach: 'Metro line 4', '10 min walk from station', 'taxi recommended'"
    )

    insider_tips: Optional[List[str]] = Field(
        default=None,
        description="Practical tips: ['bring water', 'dress modestly', 'cash only', 'arrive early']"
    )

    # Safety & Warnings
    warnings: Optional[List[str]] = Field(
        default=None,
        description="Important warnings: ['closed Mondays', 'cash only', 'watch for pickpockets']"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )


class Stage2Output(BaseModel):
    """
    Complete output from Stage 2 entity extraction.

    Contains metadata, traveler profile, and all extracted entities.
    """
    # Source metadata
    content_id: str = Field(
        pattern=r"^youtube_[a-zA-Z0-9_-]{6,15}$",
        description="Content ID (e.g., youtube_abc123)"
    )

    source_id: str = Field(
        min_length=6,
        max_length=15,
        description="YouTube video ID"
    )

    language: str = Field(
        pattern=r"^[a-z]{2}$",
        description="ISO 639-1 language code (e.g., en, hi, es)"
    )

    # Processing metadata
    processed_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when extraction was completed"
    )

    llm_model: str = Field(
        min_length=1,
        max_length=100,
        description="LLM model used for extraction (e.g., gpt-4, claude-3-sonnet)"
    )

    tokens_used: int = Field(
        default=0,
        ge=0,
        description="Total tokens used for this extraction"
    )

    cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Estimated cost in USD for LLM API call"
    )

    # Extracted data
    traveler_profile: TravelerProfile = Field(
        description="Extracted traveler profile"
    )

    entities: List[EntityExperience] = Field(
        default_factory=list,
        description="List of extracted entities (places, activities, etc.)"
    )

    # Quality metadata
    extraction_quality: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="Overall quality of extraction based on confidence scores"
    )

    processing_notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Notes about processing (warnings, issues, etc.)"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "content_id": "youtube_tq6cVSO1EO0",
                "source_id": "tq6cVSO1EO0",
                "language": "hi",
                "processed_at": "2025-11-04T13:00:00Z",
                "llm_model": "gpt-4-turbo",
                "tokens_used": 8500,
                "cost_usd": 0.085,
                "traveler_profile": {
                    "traveler_type": "couple",
                    "age_range": "26-35",
                    "budget_tier": "mid-range",
                    "travel_style": ["adventure", "cultural", "foodie"],
                    "confidence_score": 0.85
                },
                "entities": [
                    {
                        "entity_name": "Phuket Old Town",
                        "entity_type": "attraction",
                        "location": "Phuket, Thailand",
                        "experience": "Explored colorful Sino-Portuguese buildings",
                        "sentiment": "positive",
                        "cost_mentioned": "free",
                        "timestamp_start": 145.5,
                        "confidence_score": 0.9
                    }
                ],
                "extraction_quality": "high",
                "processing_notes": None
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        # Ensure datetime is ISO format string
        if isinstance(data.get('processed_at'), datetime):
            data['processed_at'] = data['processed_at'].isoformat()
        return data


# =============================================================================
# Stage 3: Entity Normalization & Consensus Schemas
# =============================================================================


class Coordinates(BaseModel):
    """
    Geographic coordinates with geocoding metadata.

    Represents the precise location of an entity with confidence
    and provenance tracking.
    """
    latitude: float = Field(
        ge=-90.0,
        le=90.0,
        description="Latitude in decimal degrees"
    )

    longitude: float = Field(
        ge=-180.0,
        le=180.0,
        description="Longitude in decimal degrees"
    )

    geocoding_provider: str = Field(
        description="Provider used for geocoding (e.g., 'google_maps', 'nominatim', 'mapbox')"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for geocoding accuracy"
    )

    place_id: Optional[str] = Field(
        default=None,
        description="Provider-specific place ID for reference"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "latitude": 13.7563,
                "longitude": 100.5018,
                "geocoding_provider": "google_maps",
                "confidence": 0.95,
                "place_id": "ChIJ5UT7K_uNAiIRZTTnN"
            }
        }
    )


class EntityLocation(BaseModel):
    """
    Normalized location information for an entity.

    Provides hierarchical location data from country down to coordinates.
    """
    country: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Country name (normalized)"
    )

    city: Optional[str] = Field(
        default=None,
        max_length=200,
        description="City or town name (normalized)"
    )

    area: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Neighborhood, district, or area within city"
    )

    coordinates: Optional[Coordinates] = Field(
        default=None,
        description="Geographic coordinates if geocoded"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "country": "Thailand",
                "city": "Bangkok",
                "area": "Khao San Road",
                "coordinates": {
                    "latitude": 13.7563,
                    "longitude": 100.5018,
                    "geocoding_provider": "google_maps",
                    "confidence": 0.95,
                    "place_id": "ChIJ5UT7K_uNAiIRZTTnN"
                }
            }
        }
    )


class ConsensusMetrics(BaseModel):
    """
    Consensus metrics aggregated from multiple mentions.

    Tracks patterns and consensus across multiple traveler experiences
    for the same entity.
    """
    mention_count: int = Field(
        ge=1,
        description="Number of times entity was mentioned across videos"
    )

    avg_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Average rating if ratings are available"
    )

    sentiment_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of sentiments (positive: N, negative: M, etc.)"
    )

    avg_cost: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Average or typical cost mentioned"
    )

    common_themes: List[str] = Field(
        default_factory=list,
        description="Common themes extracted from experiences (e.g., 'crowded', 'authentic', 'romantic')"
    )

    common_tips: List[str] = Field(
        default_factory=list,
        description="Recurring tips from travelers (e.g., 'arrive early', 'book ahead')"
    )

    common_warnings: List[str] = Field(
        default_factory=list,
        description="Common warnings or things to avoid (e.g., 'touristy', 'overpriced')"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in consensus metrics"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "mention_count": 15,
                "avg_rating": 4.3,
                "sentiment_distribution": {"positive": 12, "negative": 1, "neutral": 2},
                "avg_cost": "300-500 baht",
                "common_themes": ["authentic", "delicious", "crowded"],
                "common_tips": ["arrive before 6pm", "try the pad thai"],
                "common_warnings": ["very busy on weekends", "no reservations"],
                "confidence": 0.85
            }
        }
    )


class ProfileConsensus(BaseModel):
    """
    Consensus metrics grouped by traveler profile.

    Allows filtering recommendations based on traveler type, budget, etc.
    """
    all_travelers: ConsensusMetrics = Field(
        description="Consensus across all traveler profiles"
    )

    by_traveler_type: Dict[str, ConsensusMetrics] = Field(
        default_factory=dict,
        description="Consensus by traveler type (solo, couple, family, group)"
    )

    by_budget_tier: Dict[str, ConsensusMetrics] = Field(
        default_factory=dict,
        description="Consensus by budget tier (budget, mid-range, luxury)"
    )

    by_travel_style: Dict[str, ConsensusMetrics] = Field(
        default_factory=dict,
        description="Consensus by travel style (adventure, cultural, foodie, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "all_travelers": {
                    "mention_count": 15,
                    "avg_rating": 4.3,
                    "sentiment_distribution": {"positive": 12, "negative": 1, "neutral": 2},
                    "avg_cost": "300-500 baht",
                    "common_themes": ["authentic", "delicious"],
                    "common_tips": ["arrive early"],
                    "common_warnings": ["crowded on weekends"],
                    "confidence": 0.85
                },
                "by_traveler_type": {
                    "solo": {
                        "mention_count": 5,
                        "sentiment_distribution": {"positive": 5},
                        "confidence": 0.8
                    }
                }
            }
        }
    )


class CanonicalEntity(BaseModel):
    """
    Canonical (normalized and deduplicated) entity with consensus.

    Represents a single real-world entity that may have been mentioned
    multiple times across different videos with variations in naming.
    """
    # Identity
    entity_id: str = Field(
        pattern=r"^[a-z0-9_-]{8,64}$",
        description="Permanent unique identifier for this canonical entity"
    )

    canonical_name: str = Field(
        min_length=1,
        max_length=500,
        description="Normalized, canonical name for this entity"
    )

    aliases: List[str] = Field(
        default_factory=list,
        description="All name variations found across mentions (including original)"
    )

    entity_type: Literal[
        "destination",
        "restaurant",
        "hotel",
        "activity",
        "attraction",
        "transportation",
        "shopping",
        "unknown"
    ] = Field(
        description="Type of entity"
    )

    # Location
    location: EntityLocation = Field(
        description="Normalized location with coordinates"
    )

    # Attributes (preserved from Stage 2)
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional attributes (opening hours, website, phone, etc.)"
    )

    # Complete experiences from all mentions
    experiences: List[EntityExperience] = Field(
        default_factory=list,
        description="All original EntityExperience objects from Stage 2 (preserves complete data)"
    )

    # Consensus from multiple mentions
    consensus: ProfileConsensus = Field(
        description="Aggregated consensus metrics across all mentions"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processing metadata (source_videos, created_at, processing_version, etc.)"
    )

    total_mentions: int = Field(
        ge=1,
        description="Total number of mentions across all videos"
    )

    best_for: List[str] = Field(
        default_factory=list,
        description="Traveler profiles this entity is best suited for"
    )

    not_recommended_for: List[str] = Field(
        default_factory=list,
        description="Traveler profiles this entity is not recommended for"
    )

    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in this canonical entity"
    )

    deduplication_method: str = Field(
        description="Method used for deduplication (e.g., 'name_location_match', 'fuzzy_match')"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "entity_id": "bangkok_khao_san_rd_street_food",
                "canonical_name": "Khao San Road Street Food",
                "aliases": ["Khao San Road", "Khaosan Road street food", "KSR food stalls"],
                "entity_type": "restaurant",
                "location": {
                    "country": "Thailand",
                    "city": "Bangkok",
                    "area": "Khao San Road",
                    "coordinates": {
                        "latitude": 13.7563,
                        "longitude": 100.5018,
                        "geocoding_provider": "google_maps",
                        "confidence": 0.95
                    }
                },
                "attributes": {},
                "experiences": [],
                "consensus": {
                    "all_travelers": {
                        "mention_count": 15,
                        "sentiment_distribution": {"positive": 12, "neutral": 3},
                        "avg_cost": "50-100 baht",
                        "common_themes": ["authentic", "cheap"],
                        "common_tips": ["try the pad thai"],
                        "common_warnings": ["can be touristy"],
                        "confidence": 0.85
                    },
                    "by_traveler_type": {},
                    "by_budget_tier": {},
                    "by_travel_style": {}
                },
                "metadata": {
                    "source_videos": ["youtube_abc123", "youtube_xyz789"],
                    "created_at": "2025-11-04T10:00:00Z",
                    "processing_version": "1.0",
                    "geocoding_attempts": 1
                },
                "total_mentions": 15,
                "best_for": ["budget", "foodie"],
                "not_recommended_for": [],
                "confidence_score": 0.85,
                "deduplication_method": "name_location_match"
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode='json')


class Stage3Output(BaseModel):
    """
    Stage 3 output: Normalized and deduplicated canonical entities.

    Contains all canonical entities for a batch, with complete provenance
    tracking back to Stage 2 data.
    """
    # Batch metadata
    batch_id: str = Field(
        description="Unique identifier for this normalization batch"
    )

    processed_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp when normalization was completed"
    )

    processing_version: str = Field(
        default="1.0",
        description="Version of Stage 3 processing pipeline"
    )

    # Source tracking
    source_video_ids: List[str] = Field(
        default_factory=list,
        description="All source video IDs included in this batch"
    )

    total_stage2_entities: int = Field(
        ge=0,
        description="Total number of Stage 2 entities processed"
    )

    # Canonical entities
    canonical_entities: List[CanonicalEntity] = Field(
        default_factory=list,
        description="All canonical entities after normalization and deduplication"
    )

    # Statistics
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processing statistics (entities_merged, geocoding_success_rate, etc.)"
    )

    # Processing metadata
    geocoding_provider: Optional[str] = Field(
        default=None,
        description="Geocoding service used (if any)"
    )

    deduplication_algorithm: str = Field(
        description="Algorithm used for entity deduplication"
    )

    processing_notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Notes about processing (warnings, issues, skipped items)"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "batch_id": "batch_20251104_120000",
                "processed_at": "2025-11-04T12:00:00Z",
                "processing_version": "1.0",
                "source_video_ids": ["youtube_abc123", "youtube_xyz789"],
                "total_stage2_entities": 150,
                "canonical_entities": [],
                "stats": {
                    "entities_merged": 45,
                    "geocoding_success_rate": 0.87,
                    "total_canonical_entities": 105
                },
                "geocoding_provider": "google_maps",
                "deduplication_algorithm": "fuzzy_name_location_match",
                "processing_notes": None
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        # Ensure datetime is ISO format string
        if isinstance(data.get('processed_at'), datetime):
            data['processed_at'] = data['processed_at'].isoformat()
        return data


# =============================================================================
# Stage 4: Embeddings & Vector Search Schemas
# =============================================================================


class EmbeddingMetadata(BaseModel):
    """
    Metadata about the embedding generation process.

    Tracks which model was used, dimensions, costs, and when embeddings were created.
    """
    model: str = Field(
        description="Embedding model used (e.g., 'text-embedding-3-small', 'text-embedding-3-large')"
    )

    dimensions: int = Field(
        ge=1,
        description="Vector dimensions (e.g., 1536 for text-embedding-3-small)"
    )

    embedding_strategy: Literal[
        "entity_level",
        "experience_level",
        "profile_aware",
        "hybrid"
    ] = Field(
        description="Strategy used for creating embeddings"
    )

    created_at: datetime = Field(
        default_factory=_utc_now,
        description="When embeddings were generated"
    )

    tokens_used: int = Field(
        default=0,
        ge=0,
        description="Total tokens used for embedding generation"
    )

    cost_usd: float = Field(
        default=0.0,
        ge=0.0,
        description="Cost in USD for embedding API calls"
    )

    processing_version: str = Field(
        default="1.0",
        description="Version of Stage 4 embedding pipeline"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model": "text-embedding-3-small",
                "dimensions": 1536,
                "embedding_strategy": "experience_level",
                "created_at": "2025-12-10T17:00:00Z",
                "tokens_used": 45000,
                "cost_usd": 0.009,
                "processing_version": "1.0"
            }
        }
    )


class VectorRecord(BaseModel):
    """
    Complete vector record for storage in vector database.

    Contains the embedding vector plus all metadata needed for search,
    filtering, and retrieval.
    """
    # Vector ID
    vector_id: str = Field(
        pattern=r"^vec_[a-z0-9_-]{8,128}$",
        description="Unique identifier for this vector (e.g., vec_entity_bangkok_001_exp_0)"
    )

    # Core entity information
    entity_id: str = Field(
        description="Reference to canonical entity from Stage 3"
    )

    canonical_name: str = Field(
        min_length=1,
        max_length=500,
        description="Canonical name of the entity"
    )

    entity_type: Literal[
        "destination",
        "restaurant",
        "hotel",
        "activity",
        "attraction",
        "transportation",
        "shopping",
        "unknown"
    ] = Field(
        description="Type of entity"
    )

    # Embedding vector
    embedding: List[float] = Field(
        description="Embedding vector (length must match EmbeddingMetadata.dimensions)"
    )

    # Text that was embedded
    embedded_text: str = Field(
        min_length=1,
        description="The actual text that was embedded (for debugging/inspection)"
    )

    # Location for geo-filtering
    location: str = Field(
        description="Location string (e.g., 'Bangkok, Thailand')"
    )

    normalized_location: str = Field(
        description="Normalized lowercase location for filtering (e.g., 'bangkok')"
    )

    coordinates: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Lat/lon coordinates for geo-proximity search"
    )

    # Consensus metrics for filtering
    mention_count: int = Field(
        ge=1,
        description="Number of mentions across all videos"
    )

    avg_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Average rating"
    )

    sentiment_score: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Overall sentiment (-1 negative to +1 positive)"
    )

    # Profile-specific data (if using profile-aware strategy)
    traveler_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Traveler profile this embedding is specific to (if profile-aware)"
    )

    # Experience-specific data (if using experience-level strategy)
    experience_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Index of specific experience in entity.experiences array (if experience-level)"
    )

    source_video_id: Optional[str] = Field(
        default=None,
        description="Video ID this experience came from (if experience-level)"
    )

    # Search filtering attributes
    themes: List[str] = Field(
        default_factory=list,
        description="Common themes for filtering (e.g., 'authentic', 'romantic', 'crowded')"
    )

    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords extracted for filtering"
    )

    cost_tier: Optional[Literal["free", "budget", "mid-range", "luxury", "unknown"]] = Field(
        default=None,
        description="Cost tier for budget filtering"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (processing info, provenance, etc.)"
    )

    created_at: datetime = Field(
        default_factory=_utc_now,
        description="When this vector record was created"
    )

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimensions(cls, v: List[float]) -> List[float]:
        """Ensure embedding is not empty and has reasonable dimensions."""
        if not v:
            raise ValueError("Embedding vector cannot be empty")

        # Common embedding dimensions
        valid_dims = {384, 512, 768, 1024, 1536, 3072}
        if len(v) not in valid_dims:
            # Warning but not error - allow custom dimensions
            pass

        return v

    @field_validator("normalized_location")
    @classmethod
    def validate_normalized_location(cls, v: str) -> str:
        """Ensure normalized location is lowercase."""
        return v.lower().strip()

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        json_schema_extra={
            "example": {
                "vector_id": "vec_attraction_huahin_001_exp_0",
                "entity_id": "attraction_huahin_001",
                "canonical_name": "Wat Huai Mong Koon",
                "entity_type": "attraction",
                "embedding": [0.023, -0.145, 0.678],  # Truncated for example
                "embedded_text": "Features a giant statue of Luang Ta Tuit, a revered figure in Thai Buddhism. Offers a serene ambiance with peaceful villages and pineapple plantations.",
                "location": "Hua Hin, Thailand",
                "normalized_location": "hua hin",
                "coordinates": {
                    "lat": 12.5699326,
                    "lon": 99.9573437
                },
                "mention_count": 1,
                "avg_rating": 3.0,
                "sentiment_score": 0.5,
                "traveler_profile": {
                    "traveler_type": "unknown",
                    "travel_style": ["cultural", "adventure", "relaxation"]
                },
                "experience_index": 0,
                "source_video_id": "youtube_-3cCpu5fPzg",
                "themes": ["features", "giant", "statue", "buddhism", "serene"],
                "keywords": ["temple", "buddha", "peaceful"],
                "cost_tier": "free",
                "metadata": {
                    "stage3_provenance": "stage3_deduplication",
                    "geocoding_confidence": 0.3
                },
                "created_at": "2025-12-10T17:00:00Z"
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        # Ensure datetime is ISO format string
        if isinstance(data.get('created_at'), datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


class SearchQuery(BaseModel):
    """
    Search query for semantic vector search.

    Supports text queries with optional filters for entity type,
    location, traveler profile, and other attributes.
    """
    # Query text
    query_text: str = Field(
        min_length=1,
        max_length=1000,
        description="Natural language search query (e.g., 'romantic beach restaurant in Phuket')"
    )

    # Search parameters
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of results to return"
    )

    min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity threshold (0-1)"
    )

    # Filters
    entity_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by entity types (e.g., ['restaurant', 'hotel'])"
    )

    locations: Optional[List[str]] = Field(
        default=None,
        description="Filter by locations (e.g., ['Bangkok', 'Phuket'])"
    )

    min_mentions: Optional[int] = Field(
        default=None,
        ge=1,
        description="Filter by minimum mention count"
    )

    min_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=5.0,
        description="Filter by minimum average rating"
    )

    cost_tiers: Optional[List[str]] = Field(
        default=None,
        description="Filter by cost tiers (e.g., ['budget', 'mid-range'])"
    )

    traveler_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Filter/rank by traveler profile match"
    )

    # Geo-proximity search
    geo_center: Optional[Dict[str, float]] = Field(
        default=None,
        description="Center point for geo-proximity search (e.g., {'lat': 13.75, 'lon': 100.5})"
    )

    geo_radius_km: Optional[float] = Field(
        default=None,
        ge=0.1,
        description="Radius in kilometers for geo-proximity search"
    )

    # Search metadata
    search_id: Optional[str] = Field(
        default=None,
        description="Optional search ID for tracking/analytics"
    )

    user_id: Optional[str] = Field(
        default=None,
        description="Optional user ID for personalization"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "query_text": "romantic beach restaurant with fresh seafood",
                "top_k": 10,
                "min_similarity": 0.7,
                "entity_types": ["restaurant"],
                "locations": ["Phuket", "Krabi"],
                "min_mentions": 2,
                "min_rating": 4.0,
                "cost_tiers": ["mid-range", "luxury"],
                "traveler_profile": {
                    "traveler_type": "couple",
                    "budget_tier": "mid-range",
                    "travel_style": ["foodie", "relaxation"]
                },
                "geo_center": {
                    "lat": 7.8804,
                    "lon": 98.3923
                },
                "geo_radius_km": 10.0,
                "search_id": "search_20251210_170000",
                "user_id": "user_123"
            }
        }
    )


class SearchResult(BaseModel):
    """
    Single search result from vector search.

    Contains the matched entity with similarity score and all relevant metadata.
    """
    # Match information
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Cosine similarity score (0-1)"
    )

    rank: int = Field(
        ge=1,
        description="Rank in search results (1 = best match)"
    )

    # Entity information (from VectorRecord)
    vector_id: str = Field(
        description="ID of the matched vector record"
    )

    entity_id: str = Field(
        description="Canonical entity ID"
    )

    canonical_name: str = Field(
        description="Canonical name of the entity"
    )

    entity_type: str = Field(
        description="Type of entity"
    )

    location: str = Field(
        description="Location of entity"
    )

    # Matched text snippet
    matched_text: str = Field(
        description="The text that was matched (embedded_text from VectorRecord)"
    )

    # Consensus metrics
    mention_count: int = Field(
        ge=1,
        description="Number of mentions"
    )

    avg_rating: Optional[float] = Field(
        default=None,
        description="Average rating"
    )

    sentiment_score: Optional[float] = Field(
        default=None,
        description="Overall sentiment score"
    )

    # Attributes for display
    themes: List[str] = Field(
        default_factory=list,
        description="Common themes"
    )

    cost_tier: Optional[str] = Field(
        default=None,
        description="Cost tier"
    )

    coordinates: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Coordinates for map display"
    )

    # Distance (if geo-proximity search was used)
    distance_km: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Distance from search center in kilometers"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata from VectorRecord"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "similarity_score": 0.87,
                "rank": 1,
                "vector_id": "vec_restaurant_phuket_001_exp_0",
                "entity_id": "restaurant_phuket_001",
                "canonical_name": "The Boathouse Wine & Grill",
                "entity_type": "restaurant",
                "location": "Phuket, Thailand",
                "matched_text": "Romantic beachfront restaurant with excellent seafood and extensive wine list. Perfect sunset views.",
                "mention_count": 8,
                "avg_rating": 4.5,
                "sentiment_score": 0.85,
                "themes": ["romantic", "beachfront", "seafood", "wine"],
                "cost_tier": "luxury",
                "coordinates": {
                    "lat": 7.8804,
                    "lon": 98.3923
                },
                "distance_km": 2.5,
                "metadata": {
                    "source_videos": ["youtube_abc123", "youtube_xyz789"],
                    "geocoding_confidence": 0.95
                }
            }
        }
    )


class SearchResponse(BaseModel):
    """
    Complete search response with results and metadata.

    Contains all matched results, search metadata, and processing info.
    """
    # Search metadata
    query: SearchQuery = Field(
        description="Original search query"
    )

    # Results
    results: List[SearchResult] = Field(
        default_factory=list,
        description="List of search results, ordered by relevance"
    )

    total_results: int = Field(
        ge=0,
        description="Total number of results found (before top_k limit)"
    )

    # Processing metadata
    search_duration_ms: float = Field(
        ge=0.0,
        description="Time taken to execute search in milliseconds"
    )

    embedding_duration_ms: float = Field(
        ge=0.0,
        description="Time taken to generate query embedding in milliseconds"
    )

    processed_at: datetime = Field(
        default_factory=_utc_now,
        description="When search was processed"
    )

    # Index statistics
    total_vectors_searched: int = Field(
        ge=0,
        description="Total number of vectors searched"
    )

    filters_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of filters that were applied"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": {
                    "query_text": "romantic beach restaurant",
                    "top_k": 10,
                    "entity_types": ["restaurant"]
                },
                "results": [],
                "total_results": 15,
                "search_duration_ms": 45.3,
                "embedding_duration_ms": 12.1,
                "processed_at": "2025-12-10T17:00:00Z",
                "total_vectors_searched": 1655,
                "filters_applied": {
                    "entity_types": ["restaurant"],
                    "min_similarity": 0.7
                }
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        # Ensure datetime is ISO format string
        if isinstance(data.get('processed_at'), datetime):
            data['processed_at'] = data['processed_at'].isoformat()
        return data


# =============================================================================
# Stage 5: RAG Pipeline - Itinerary Generation Schemas
# =============================================================================
# Production-grade schemas designed to scale from 400 to 10,000+ entities
# Author: TravelAI Team
# Date: 2025-12-20
# =============================================================================


class Pace(str, Enum):
    """Itinerary pacing preference"""
    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class Flexibility(str, Enum):
    """User flexibility level for recommendations"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TimePeriod(str, Enum):
    """Time slots for activities in a day"""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class DataQuality(str, Enum):
    """Quality of data coverage for generation"""
    EXCELLENT = "excellent"
    GOOD = "good"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"


class ValidationSeverity(str, Enum):
    """Severity level for validation issues"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationType(str, Enum):
    """Type of validation issue detected"""
    HALLUCINATION = "hallucination"
    LOGISTICS = "logistics"
    BUDGET = "budget"
    TIMING = "timing"
    FEASIBILITY = "feasibility"
    DATA_QUALITY = "data_quality"


class TravelerProfileInput(BaseModel):
    """
    User's traveler profile for itinerary generation.

    Captures demographics and preferences to personalize recommendations.

    Example:
        >>> profile = TravelerProfileInput(
        ...     traveler_type="solo",
        ...     budget_tier="budget",
        ...     travel_style=["party", "food"]
        ... )
        >>> profile.to_profile_key()
        'solo_all_budget'
    """
    traveler_type: Literal["solo", "couple", "family", "group"] = Field(
        description="Type of traveler"
    )

    group_size: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Number of travelers in the group"
    )

    age_range: Optional[str] = Field(
        default=None,
        description="Age range (e.g., '26-35')"
    )

    budget_tier: Literal["budget", "mid-range", "luxury"] = Field(
        description="Budget category"
    )

    travel_style: List[str] = Field(
        default_factory=list,
        description="Travel style preferences (e.g., 'party', 'cultural', 'foodie')"
    )

    @field_validator('age_range')
    @classmethod
    def validate_age_range(cls, v):
        """Validate age range format"""
        if v is None:
            return v
        valid_ranges = ["18-25", "26-35", "36-50", "50+"]
        if v not in valid_ranges:
            raise ValueError(f"Age range must be one of: {valid_ranges}")
        return v

    def to_profile_key(self) -> str:
        """
        Convert to profile key for matching Stage 3 data.

        Returns:
            Profile key string (e.g., "solo_26-35_budget")
        """
        age = self.age_range or "all"
        return f"{self.traveler_type}_{age}_{self.budget_tier}"

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "traveler_type": "solo",
                "group_size": 1,
                "age_range": "26-35",
                "budget_tier": "budget",
                "travel_style": ["party", "food", "nightlife"]
            }
        }
    )


class UserIntent(BaseModel):
    """
    Complete user intent for itinerary generation.

    Captures all requirements, constraints, and preferences from user query.
    Designed to scale to complex multi-constraint queries.

    Example:
        >>> intent = UserIntent(
        ...     destination="Bangkok",
        ...     duration_days=5,
        ...     traveler_profile=profile,
        ...     query_text="5-day budget party trip to Bangkok"
        ... )
    """
    # Core requirements
    destination: str = Field(
        description="Destination (city, country, or region)"
    )

    duration_days: int = Field(
        ge=1,
        le=30,
        description="Trip duration in days"
    )

    traveler_profile: TravelerProfileInput = Field(
        description="Traveler demographics and preferences"
    )

    # Budget constraints
    budget_per_day: Optional[Dict[str, float]] = Field(
        default=None,
        description="Daily budget range ({'min': 30, 'max': 50})"
    )

    # Date constraints
    dates: Optional[Dict[str, str]] = Field(
        default=None,
        description="Trip dates ({'start': '2025-12-01', 'end': '2025-12-06'})"
    )

    # Must include/avoid
    must_include: List[str] = Field(
        default_factory=list,
        description="Entities/activities that must be included"
    )

    must_avoid: List[str] = Field(
        default_factory=list,
        description="Entities/activities to avoid"
    )

    # Preferences
    pace: Pace = Field(
        default=Pace.BALANCED,
        description="Itinerary pacing preference"
    )

    interests: List[str] = Field(
        default_factory=list,
        description="Interest areas (food, nightlife, culture, nature, etc.)"
    )

    accommodation_preference: Optional[str] = Field(
        default=None,
        description="Accommodation type (hostel, hotel, resort, etc.)"
    )

    # Flexibility
    flexibility: Flexibility = Field(
        default=Flexibility.MEDIUM,
        description="How flexible user is with suggestions"
    )

    # Metadata
    query_text: str = Field(
        description="Original user query text"
    )

    parsed_at: datetime = Field(
        default_factory=_utc_now,
        description="When query was parsed"
    )

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in parsing accuracy (0-1)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "destination": "Bangkok",
                "duration_days": 5,
                "traveler_profile": {
                    "traveler_type": "solo",
                    "group_size": 1,
                    "age_range": "26-35",
                    "budget_tier": "budget",
                    "travel_style": ["party", "food"]
                },
                "budget_per_day": {"min": 30, "max": 50},
                "must_include": ["Grand Palace"],
                "pace": "balanced",
                "interests": ["food", "nightlife", "culture"],
                "query_text": "Plan a 5-day party trip to Bangkok on a budget",
                "confidence": 0.95
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        if isinstance(data.get('parsed_at'), datetime):
            data['parsed_at'] = data['parsed_at'].isoformat()
        return data


class RetrievalCandidate(BaseModel):
    """
    Entity retrieved from vector database for itinerary consideration.

    Represents a candidate place/activity with multi-dimensional scoring.
    Optimized for ranking and filtering at scale (10,000+ entities).

    Example:
        >>> candidate = RetrievalCandidate(
        ...     entity_id="restaurant_bangkok_001",
        ...     canonical_name="Khao San Road Food Stalls",
        ...     similarity_score=0.89,
        ...     profile_rating=4.5,
        ...     mention_count=42
        ... )
    """
    # Identity
    entity_id: str = Field(description="Canonical entity ID")
    canonical_name: str = Field(description="Entity name")
    entity_type: str = Field(description="Entity type")
    city: str = Field(description="City location")

    # Relevance scoring (multi-dimensional)
    similarity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Vector similarity to query (0-1)"
    )

    profile_rating: float = Field(
        ge=0.0,
        le=5.0,
        description="Rating from user's traveler profile"
    )

    mention_count: int = Field(
        ge=0,
        description="Number of traveler mentions across videos"
    )

    # Full entity data (from Stage 3)
    entity_data: Dict[str, Any] = Field(
        description="Complete canonical entity from Stage 3"
    )

    profile_consensus: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Profile-specific consensus data"
    )

    # Metadata for ranking
    coordinates: Dict[str, float] = Field(
        default_factory=dict,
        description="Geographic coordinates for proximity scoring"
    )

    attributes: List[str] = Field(
        default_factory=list,
        description="Entity attributes/tags for filtering"
    )

    best_for: List[str] = Field(
        default_factory=list,
        description="Best suited for these traveler profiles"
    )

    # Provenance (for debugging/transparency)
    source_video_ids: List[str] = Field(
        default_factory=list,
        description="Source video IDs this entity appeared in"
    )

    # Computed fields (populated during ranking)
    relevance_score: Optional[float] = Field(
        default=None,
        description="Final relevance score after re-ranking (0-1)"
    )

    ranking_reason: Optional[str] = Field(
        default=None,
        description="Explanation for why this entity ranked here"
    )

    def compute_relevance(
        self,
        similarity_weight: float = 0.4,
        rating_weight: float = 0.3,
        popularity_weight: float = 0.3
    ) -> float:
        """
        Compute combined relevance score from multiple signals.

        Args:
            similarity_weight: Weight for vector similarity
            rating_weight: Weight for profile rating
            popularity_weight: Weight for mention popularity

        Returns:
            Combined relevance score (0-1)
        """
        # Normalize mention count (sigmoid-like scaling)
        normalized_popularity = min(self.mention_count / 100.0, 1.0)

        # Normalize rating (0-5 → 0-1)
        normalized_rating = self.profile_rating / 5.0

        # Weighted combination
        score = (
            similarity_weight * self.similarity_score +
            rating_weight * normalized_rating +
            popularity_weight * normalized_popularity
        )

        self.relevance_score = round(score, 3)
        return self.relevance_score

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_id": "restaurant_bangkok_001",
                "canonical_name": "Khao San Road Food Stalls",
                "entity_type": "restaurant",
                "city": "Bangkok",
                "similarity_score": 0.89,
                "profile_rating": 4.5,
                "mention_count": 42,
                "entity_data": {},
                "coordinates": {"lat": 13.7563, "lon": 100.5018},
                "best_for": ["budget", "party", "solo"],
                "source_video_ids": ["youtube_abc123"],
                "relevance_score": 0.87
            }
        }
    )


class TimeSlot(BaseModel):
    """
    Single time slot/activity in an itinerary day.

    Represents one place to visit with all practical details and context.
    Includes traveler quotes for authenticity.

    Example:
        >>> slot = TimeSlot(
        ...     time_period="morning",
        ...     entity_name="Grand Palace",
        ...     activity_description="Explore historic palace complex"
        ... )
    """
    # Timing
    time_period: TimePeriod = Field(description="Time slot in day")
    start_time: Optional[str] = Field(default=None, description="Start time (HH:MM)")
    end_time: Optional[str] = Field(default=None, description="End time (HH:MM)")

    # Entity reference
    entity_id: str = Field(description="Entity ID from Stage 3")
    entity_name: str = Field(description="Entity name")
    entity_type: str = Field(description="Entity type")

    # Content
    activity_description: str = Field(description="What to do here")
    why_this_works: str = Field(description="Why it's good for this profile")

    # Practical details
    estimated_duration: str = Field(description="Time needed (e.g., '2-3 hours')")
    estimated_cost: Optional[str] = Field(default=None, description="Cost estimate")
    tips: List[str] = Field(default_factory=list, description="Practical tips")
    warnings: List[str] = Field(default_factory=list, description="Important warnings")

    # Traveler voices (adds authenticity)
    traveler_quotes: List[str] = Field(
        default_factory=list,
        description="Quotes from real travelers (from video transcripts)"
    )

    # Provenance
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in recommendation (0-1)"
    )

    sources: List[str] = Field(
        default_factory=list,
        description="Source video IDs"
    )

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v):
        """Validate HH:MM time format"""
        if v is None:
            return v

        if len(v) != 5 or v[2] != ':':
            raise ValueError("Time must be in HH:MM format")

        try:
            hours, minutes = v.split(':')
            h, m = int(hours), int(minutes)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError("Invalid time")
        except (ValueError, AttributeError):
            raise ValueError("Time must be in HH:MM format")

        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "time_period": "morning",
                "start_time": "09:00",
                "end_time": "12:00",
                "entity_id": "attraction_bangkok_001",
                "entity_name": "Grand Palace",
                "entity_type": "attraction",
                "activity_description": "Explore the historic Grand Palace complex",
                "why_this_works": "Perfect for culture lovers and history enthusiasts",
                "estimated_duration": "2-3 hours",
                "estimated_cost": "$15",
                "tips": ["Dress modestly", "Arrive early"],
                "traveler_quotes": ["Absolutely stunning!"],
                "confidence": 0.95,
                "sources": ["youtube_abc123"]
            }
        }
    )


class ItineraryDay(BaseModel):
    """
    Complete structure for a single day in the itinerary.

    Contains all activities, logistics, and quality metrics.
    Supports 1-4 time slots per day for flexibility.

    Example:
        >>> day = ItineraryDay(
        ...     day_number=1,
        ...     theme="Bangkok Arrival & Cultural Intro",
        ...     daily_budget_estimate="$40-50"
        ... )
    """
    # Day info
    day_number: int = Field(ge=1, description="Day number in itinerary")
    date: Optional[str] = Field(default=None, description="Date if dates provided")
    theme: str = Field(description="Day theme/title")

    # Time slots (flexible - user may have 1-4 activities per day)
    morning: Optional[TimeSlot] = Field(default=None, description="Morning activity")
    afternoon: Optional[TimeSlot] = Field(default=None, description="Afternoon activity")
    evening: Optional[TimeSlot] = Field(default=None, description="Evening activity")
    night: Optional[TimeSlot] = Field(default=None, description="Night activity")

    # Logistics
    daily_budget_estimate: str = Field(description="Budget for this day")
    total_distance_km: float = Field(
        default=0.0,
        ge=0.0,
        description="Total distance between activities (km)"
    )
    accommodation_suggestion: Optional[str] = Field(
        default=None,
        description="Where to stay this night"
    )

    # Quality metrics
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Average confidence of all activities"
    )

    feasibility_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Logistics feasibility (timing, distances, etc.)"
    )

    def get_time_slots(self) -> List[TimeSlot]:
        """Get all non-null time slots for this day"""
        slots = []
        for slot in [self.morning, self.afternoon, self.evening, self.night]:
            if slot is not None:
                slots.append(slot)
        return slots

    def get_all_entity_ids(self) -> List[str]:
        """Get all entity IDs used in this day"""
        return [slot.entity_id for slot in self.get_time_slots()]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "day_number": 1,
                "theme": "Bangkok Arrival & Cultural Introduction",
                "morning": {},
                "afternoon": {},
                "daily_budget_estimate": "$40-50",
                "total_distance_km": 8.5,
                "confidence_score": 0.92,
                "feasibility_score": 0.95
            }
        }
    )


class ItineraryNarrative(BaseModel):
    """
    Human-readable narrative version of itinerary.

    Converts structured data into flowing storytelling format.
    Optimized for user engagement and readability.

    Example:
        >>> narrative = ItineraryNarrative(
        ...     title="Your 5-Day Bangkok Adventure",
        ...     introduction="Get ready for an epic journey..."
        ... )
    """
    # Content
    title: str = Field(description="Catchy, personalized itinerary title")
    introduction: str = Field(description="Personalized intro paragraph")
    day_narratives: List[str] = Field(description="One flowing narrative per day")
    conclusion: str = Field(description="Wrap-up with final tips and encouragement")

    # Style metadata
    tone: str = Field(
        default="casual",
        description="Narrative tone (casual/professional/enthusiastic)"
    )

    word_count: int = Field(default=0, ge=0, description="Total word count")

    def compute_word_count(self) -> int:
        """Compute total word count of narrative"""
        all_text = ' '.join([
            self.title,
            self.introduction,
            *self.day_narratives,
            self.conclusion
        ])
        self.word_count = len(all_text.split())
        return self.word_count

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Your 5-Day Bangkok Party & Food Adventure",
                "introduction": "Get ready for an epic adventure through Bangkok...",
                "day_narratives": ["Day 1: You'll start your journey..."],
                "conclusion": "This itinerary balances culture, nightlife, and food...",
                "tone": "casual",
                "word_count": 1200
            }
        }
    )


class GeneratedItinerary(BaseModel):
    """
    Complete generated itinerary with all data and metadata.

    This is the final output from Stage 5 RAG pipeline.
    Includes structured data, narrative version, quality metrics, and full provenance.

    Production features:
    - Complete provenance tracking
    - Quality metrics for confidence scoring
    - Cost tracking
    - Validation support

    Example:
        >>> itinerary = GeneratedItinerary(
        ...     destination="Bangkok",
        ...     duration_days=5,
        ...     days=[day1, day2, day3, day4, day5]
        ... )
    """
    # User context
    user_intent: UserIntent = Field(description="Original user intent")
    profile_classification: str = Field(description="Matched profile key")

    # Itinerary structure
    destination: str = Field(description="Destination")
    duration_days: int = Field(ge=1, le=30, description="Trip duration")
    days: List[ItineraryDay] = Field(description="Day-by-day itinerary")

    # Narrative version
    narrative: Optional[ItineraryNarrative] = Field(
        default=None,
        description="Human-readable narrative version"
    )

    # Summary
    total_budget_estimate: str = Field(description="Total budget estimate")
    highlights: List[str] = Field(description="Top 3-5 trip highlights")
    overall_vibe: str = Field(description="Overall trip vibe/feeling")

    # Practical info
    general_tips: List[str] = Field(
        default_factory=list,
        description="General travel tips"
    )

    important_warnings: List[str] = Field(
        default_factory=list,
        description="Important warnings/safety info"
    )

    packing_suggestions: List[str] = Field(
        default_factory=list,
        description="What to pack"
    )

    # Quality metrics
    overall_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0-1)"
    )

    data_coverage: DataQuality = Field(
        default=DataQuality.GOOD,
        description="Quality of data coverage"
    )

    # Provenance (for transparency and debugging)
    entities_used: int = Field(default=0, ge=0, description="Number of unique entities used")
    sources_used: int = Field(default=0, ge=0, description="Number of source videos referenced")
    source_video_ids: List[str] = Field(default_factory=list, description="All source video IDs")
    entity_ids: List[str] = Field(default_factory=list, description="All entity IDs used")

    # Generation metadata
    generated_at: datetime = Field(
        default_factory=_utc_now,
        description="When itinerary was generated"
    )

    generation_version: str = Field(
        default="v1.0",
        description="Generation pipeline version"
    )

    llm_model_used: str = Field(
        default="deepseek-chat",
        description="LLM model used for generation"
    )

    total_cost: float = Field(default=0.0, ge=0.0, description="Generation cost (USD)")

    @field_validator('days')
    @classmethod
    def validate_days_count(cls, v, values):
        """Ensure days count matches duration"""
        duration = values.data.get('duration_days')
        if duration and len(v) != duration:
            raise ValueError(f"Number of days ({len(v)}) must match duration ({duration})")
        return v

    def compute_overall_confidence(self) -> float:
        """Compute average confidence across all days"""
        if not self.days:
            return 0.0
        self.overall_confidence = sum(day.confidence_score for day in self.days) / len(self.days)
        return self.overall_confidence

    def get_all_entities(self) -> List[str]:
        """Get all unique entity IDs used in itinerary"""
        entity_ids = set()
        for day in self.days:
            entity_ids.update(day.get_all_entity_ids())
        self.entity_ids = sorted(list(entity_ids))
        self.entities_used = len(self.entity_ids)
        return self.entity_ids

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_intent": {},
                "profile_classification": "solo_26-35_budget",
                "destination": "Bangkok",
                "duration_days": 5,
                "days": [],
                "total_budget_estimate": "$200-250",
                "highlights": ["Grand Palace", "Khao San Road nightlife"],
                "overall_vibe": "Social, adventurous, budget-friendly",
                "overall_confidence": 0.92,
                "data_coverage": "excellent",
                "entities_used": 15,
                "sources_used": 8,
                "llm_model_used": "deepseek-chat",
                "total_cost": 0.05
            }
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = self.model_dump(mode='json')
        if isinstance(data.get('generated_at'), datetime):
            data['generated_at'] = data['generated_at'].isoformat()
        return data


class RAGContext(BaseModel):
    """
    Optimized context for LLM generation (token-efficient).

    Contains compressed and prioritized entity data for prompt.
    Designed to fit within LLM context windows at scale.

    Token optimization strategies:
    - Tiered entity prioritization (full/summary/minimal)
    - Compression levels (none/light/heavy)
    - Automatic token estimation

    Example:
        >>> context = RAGContext(
        ...     user_intent_summary="5-day budget party trip",
        ...     profile_description="Solo budget traveler, loves parties"
        ... )
        >>> context.estimate_tokens()
        2543
    """
    # User context (compressed for efficiency)
    user_intent_summary: str = Field(description="Concise intent description")
    profile_description: str = Field(description="Traveler profile summary")

    # Retrieved entities (tiered by priority for token management)
    priority_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top 5-10 entities with full context"
    )

    supporting_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Next 5-10 entities with summarized context"
    )

    background_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Remaining entities with minimal context (names only)"
    )

    # Constraints
    hard_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Must follow constraints (budget, dates, must-include)"
    )

    soft_preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="Should try to follow (pace, interests)"
    )

    # Metadata for generation
    total_entities: int = Field(default=0, ge=0, description="Total entities available")
    coverage_areas: List[str] = Field(
        default_factory=list,
        description="Geographic areas covered by data"
    )
    data_quality_note: str = Field(
        default="",
        description="Data quality description for context"
    )

    # Token budget tracking
    estimated_tokens: int = Field(default=0, ge=0, description="Estimated token count")
    compression_level: str = Field(
        default="none",
        description="Compression applied (none/light/heavy)"
    )

    def estimate_tokens(self) -> int:
        """
        Estimate token count for this context.

        Uses rough heuristic: ~1.3 tokens per word.

        Returns:
            Estimated token count
        """
        import json
        json_str = json.dumps(self.model_dump())
        word_count = len(json_str.split())
        self.estimated_tokens = int(word_count * 1.3)
        return self.estimated_tokens

    def compress(self, target_tokens: int = 4000) -> 'RAGContext':
        """
        Compress context to fit token budget.

        Progressively reduces entity tiers until target is met.

        Args:
            target_tokens: Target token count

        Returns:
            Compressed RAGContext (self, modified in place)
        """
        current_tokens = self.estimate_tokens()

        if current_tokens <= target_tokens:
            self.compression_level = "none"
            return self

        # Light compression: move supporting → background
        if len(self.supporting_entities) > 5:
            moved = self.supporting_entities[5:]
            self.supporting_entities = self.supporting_entities[:5]
            self.background_entities.extend(moved)
            self.compression_level = "light"

        # Heavy compression: reduce all tiers
        if self.estimate_tokens() > target_tokens:
            self.priority_entities = self.priority_entities[:5]
            self.supporting_entities = self.supporting_entities[:3]
            self.background_entities = self.background_entities[:2]
            self.compression_level = "heavy"

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_intent_summary": "5-day budget party trip to Bangkok",
                "profile_description": "Solo budget traveler (26-35) who loves parties",
                "priority_entities": [],
                "hard_constraints": {"budget_per_day": 50, "duration": 5},
                "total_entities": 15,
                "coverage_areas": ["Bangkok"],
                "data_quality_note": "Based on 42 traveler experiences",
                "estimated_tokens": 2000,
                "compression_level": "none"
            }
        }
    )


class ValidationIssue(BaseModel):
    """
    Single validation issue found during fact-checking.

    Represents one problem with the generated itinerary.
    Used for quality assurance and hallucination detection.

    Example:
        >>> issue = ValidationIssue(
        ...     severity="warning",
        ...     type="timing",
        ...     description="Activity duration may be insufficient"
        ... )
    """
    severity: ValidationSeverity = Field(description="Issue severity level")
    type: ValidationType = Field(description="Issue type/category")
    description: str = Field(description="Detailed issue description")

    affected_day: Optional[int] = Field(default=None, description="Day number affected")
    affected_entity: Optional[str] = Field(default=None, description="Entity ID affected")

    suggested_fix: Optional[str] = Field(default=None, description="Suggested resolution")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "severity": "warning",
                "type": "timing",
                "description": "Chatuchak Market visit may need more time",
                "affected_day": 2,
                "affected_entity": "shopping_bangkok_002",
                "suggested_fix": "Allocate 4-5 hours instead of 3"
            }
        }
    )


class ValidationReport(BaseModel):
    """
    Complete validation report for generated itinerary.

    Contains all validation results, quality scores, and recommendations.
    Critical for production deployment - prevents hallucinations and ensures quality.

    Validation checks:
    - Hallucination detection (entity existence, fact accuracy)
    - Logistics feasibility (timing, distances, opening hours)
    - Budget compliance (cost estimates vs. constraints)
    - Data quality (coverage, confidence levels)

    Example:
        >>> report = ValidationReport(
        ...     is_valid=True,
        ...     overall_score=0.92,
        ...     no_hallucinations=True,
        ...     logistics_feasible=True
        ... )
    """
    # Overall status
    is_valid: bool = Field(description="Whether itinerary passes validation")
    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall quality score (0-1)"
    )

    # Issues found
    issues: List[ValidationIssue] = Field(
        default_factory=list,
        description="All validation issues (errors + warnings + info)"
    )

    # Specific validation checks
    no_hallucinations: bool = Field(
        description="No hallucinated entities or facts"
    )

    logistics_feasible: bool = Field(
        description="Timing, distances, logistics are realistic"
    )

    budget_compliant: bool = Field(
        description="Meets user budget constraints"
    )

    timing_realistic: bool = Field(
        description="Activity durations and transitions are realistic"
    )

    # Improvement suggestions
    improvement_suggestions: List[str] = Field(
        default_factory=list,
        description="Suggestions to improve quality"
    )

    regeneration_needed: bool = Field(
        default=False,
        description="Whether itinerary needs regeneration"
    )

    def get_errors(self) -> List[ValidationIssue]:
        """Get only error-level issues"""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    def get_warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues"""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_valid": True,
                "overall_score": 0.92,
                "issues": [],
                "no_hallucinations": True,
                "logistics_feasible": True,
                "budget_compliant": True,
                "timing_realistic": True,
                "improvement_suggestions": ["Add buffer time between activities"],
                "regeneration_needed": False
            }
        }
    )


# =============================================================================
# Stage 5 Testing Examples
# =============================================================================

def example_stage5_user_intent() -> UserIntent:
    """Create example UserIntent for Stage 5 testing"""
    profile = TravelerProfileInput(
        traveler_type="solo",
        group_size=1,
        age_range="26-35",
        budget_tier="budget",
        travel_style=["party", "food", "nightlife"]
    )

    intent = UserIntent(
        destination="Bangkok",
        duration_days=5,
        traveler_profile=profile,
        budget_per_day={"min": 30, "max": 50},
        must_include=["Grand Palace"],
        pace=Pace.BALANCED,
        interests=["food", "nightlife", "culture"],
        query_text="Plan a 5-day party trip to Bangkok on a budget",
        confidence=0.95
    )

    return intent


def example_stage5_generated_itinerary() -> GeneratedItinerary:
    """Create example GeneratedItinerary for Stage 5 testing"""
    intent = example_stage5_user_intent()

    # Create sample day
    morning_slot = TimeSlot(
        time_period=TimePeriod.MORNING,
        start_time="09:00",
        end_time="12:00",
        entity_id="attraction_bangkok_001",
        entity_name="Grand Palace",
        entity_type="attraction",
        activity_description="Explore the historic Grand Palace complex",
        why_this_works="Perfect for culture lovers",
        estimated_duration="2-3 hours",
        estimated_cost="$15",
        tips=["Dress modestly", "Arrive early"],
        confidence=0.95,
        sources=["youtube_abc123"]
    )

    day1 = ItineraryDay(
        day_number=1,
        theme="Bangkok Arrival & Cultural Introduction",
        morning=morning_slot,
        daily_budget_estimate="$40-50",
        total_distance_km=5.2,
        confidence_score=0.95
    )

    itinerary = GeneratedItinerary(
        user_intent=intent,
        profile_classification="solo_26-35_budget",
        destination="Bangkok",
        duration_days=1,  # Just 1 day for example
        days=[day1],
        total_budget_estimate="$40-50",
        highlights=["Grand Palace cultural experience"],
        overall_vibe="Cultural immersion with authentic experiences",
        general_tips=["Download Grab app", "Carry small bills"],
        data_coverage=DataQuality.EXCELLENT,
        entities_used=1,
        sources_used=1,
        llm_model_used="deepseek-chat",
        total_cost=0.02
    )

    return itinerary


# Print success message when schemas are loaded
if __name__ != "__main__":
    # Not in test mode - schemas loaded successfully
    pass
