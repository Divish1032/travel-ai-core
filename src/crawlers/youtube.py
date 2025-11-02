"""
YouTube crawler implementation for Travel AI project.

Crawls YouTube videos to extract metadata and transcripts, validates the data
with Pydantic schemas, and handles errors gracefully with retry logic.

Features:
- Fetches video metadata using pytube
- Fetches transcripts using youtube-transcript-api
- Rate limiting and retry logic
- Progress tracking with tqdm
- Comprehensive error handling
- Data validation with Pydantic

Usage:
    from src.crawlers.youtube import crawl_videos, crawl_video

    # Crawl single video
    video = crawl_video("https://youtube.com/watch?v=abc123")
    if video:
        print(f"Crawled: {video.title}")

    # Crawl multiple videos
    urls = [
        "https://youtube.com/watch?v=abc123",
        "https://youtube.com/watch?v=xyz789"
    ]
    successful, failed = crawl_videos(urls)
    print(f"Success: {len(successful)}, Failed: {len(failed)}")
"""
import re
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from pytube import YouTube
from pytube.exceptions import PytubeError, VideoUnavailable, RegexMatchError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable as TranscriptVideoUnavailable
)
from tqdm import tqdm

from src.crawlers.base import BaseCrawler, FetchError, ParseError
from src.utils.schemas import YouTubeVideo, TranscriptSegment, VideoMetadata, Provenance
from src.utils.config import config
from src.utils.logging import get_logger


logger = get_logger(__name__)


def extract_video_id(url: str) -> str:
    """
    Extract video ID from various YouTube URL formats.

    Supports formats:
    - https://youtube.com/watch?v=VIDEO_ID
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://youtube.com/embed/VIDEO_ID
    - https://m.youtube.com/watch?v=VIDEO_ID

    Args:
        url: YouTube URL

    Returns:
        Video ID string

    Raises:
        ValueError: If video ID cannot be extracted

    Example:
        >>> extract_video_id("https://youtube.com/watch?v=abc123")
        'abc123'
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            logger.debug(f"Extracted video ID: {video_id} from {url}")
            return video_id

    raise ValueError(f"Could not extract video ID from URL: {url}")


def fetch_video_metadata(video_id: str) -> Dict[str, Any]:
    """
    Fetch video metadata using pytube.

    Args:
        video_id: YouTube video ID

    Returns:
        Dictionary containing video metadata

    Raises:
        FetchError: If metadata fetch fails

    Example:
        >>> metadata = fetch_video_metadata("abc123")
        >>> print(metadata['title'])
    """
    try:
        url = f"https://youtube.com/watch?v={video_id}"
        logger.debug(f"Fetching metadata for video: {video_id}")

        yt = YouTube(url)

        # Extract metadata
        metadata = {
            'video_id': video_id,
            'url': url,
            'title': yt.title,
            'author': yt.author,
            'channel_url': yt.channel_url,
            'duration_seconds': yt.length,
            'published_date': yt.publish_date.strftime("%Y-%m-%d") if yt.publish_date else None,
            'view_count': yt.views or 0,
            'description': yt.description or "",
            'keywords': yt.keywords or [],
        }

        # Try to get additional metadata (may not always be available)
        try:
            metadata['like_count'] = None  # pytube doesn't provide likes reliably
            metadata['comment_count'] = None  # pytube doesn't provide comments
        except Exception as e:
            logger.debug(f"Could not fetch engagement metrics: {e}")

        logger.debug(f"Successfully fetched metadata for {video_id}: {metadata['title']}")
        return metadata

    except VideoUnavailable as e:
        raise FetchError(f"Video unavailable: {video_id}") from e
    except PytubeError as e:
        raise FetchError(f"Pytube error for {video_id}: {e}") from e
    except Exception as e:
        raise FetchError(f"Unexpected error fetching metadata for {video_id}: {e}") from e


def fetch_transcript(video_id: str, language: str = "en") -> Optional[List[Dict[str, Any]]]:
    """
    Fetch video transcript using youtube-transcript-api.

    Args:
        video_id: YouTube video ID
        language: Language code (default: 'en')

    Returns:
        List of transcript segments with text, start, and duration, or None if unavailable

    Raises:
        FetchError: If transcript fetch fails unexpectedly

    Example:
        >>> transcript = fetch_transcript("abc123")
        >>> if transcript:
        ...     print(transcript[0]['text'])
    """
    try:
        logger.debug(f"Fetching transcript for video: {video_id}")

        # Get transcript
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id,
            languages=[language]
        )

        if not transcript_list:
            logger.warning(f"Empty transcript for {video_id}")
            return None

        # Format transcript segments
        segments = []
        for segment in transcript_list:
            segments.append({
                'text': segment['text'],
                'start': segment['start'],
                'duration': segment['duration']
            })

        logger.debug(f"Successfully fetched {len(segments)} transcript segments for {video_id}")
        return segments

    except TranscriptsDisabled:
        logger.warning(f"Transcripts disabled for video: {video_id}")
        return None
    except NoTranscriptFound:
        logger.warning(f"No {language} transcript found for video: {video_id}")
        return None
    except TranscriptVideoUnavailable:
        logger.warning(f"Video unavailable for transcript: {video_id}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        return None


def crawl_video(
    url: str,
    max_retries: Optional[int] = None,
    language: str = "en"
) -> Optional[YouTubeVideo]:
    """
    Crawl a single YouTube video: fetch metadata + transcript and validate.

    Args:
        url: YouTube video URL
        max_retries: Maximum retry attempts (default: from config)
        language: Transcript language (default: 'en')

    Returns:
        YouTubeVideo object if successful, None if failed

    Example:
        >>> video = crawl_video("https://youtube.com/watch?v=abc123")
        >>> if video:
        ...     print(f"Title: {video.title}")
        ...     print(f"Duration: {video.duration_seconds}s")
        ...     print(f"Transcript segments: {len(video.transcript)}")
    """
    if max_retries is None:
        max_retries = config.MAX_RETRIES if config else 3

    logger.info(f"Crawling video: {url}")

    for attempt in range(1, max_retries + 1):
        try:
            # Extract video ID
            video_id = extract_video_id(url)

            # Fetch metadata
            metadata = fetch_video_metadata(video_id)

            # Fetch transcript
            transcript_data = fetch_transcript(video_id, language=language)

            if not transcript_data:
                logger.warning(f"No transcript available for {url}, skipping")
                return None

            # Validate and create transcript segments
            transcript_segments = []
            for segment in transcript_data:
                try:
                    ts = TranscriptSegment(
                        text=segment['text'],
                        start=segment['start'],
                        duration=segment['duration']
                    )
                    transcript_segments.append(ts)
                except Exception as e:
                    logger.warning(f"Invalid transcript segment, skipping: {e}")
                    continue

            if not transcript_segments:
                logger.warning(f"No valid transcript segments for {url}, skipping")
                return None

            # Build YouTubeVideo object
            video = YouTubeVideo(
                source="youtube",
                source_id=video_id,
                source_url=metadata['url'],
                content_type="vlog",  # Default, can be enhanced later
                title=metadata['title'],
                author=metadata['author'],
                author_url=metadata['channel_url'],
                published_date=metadata['published_date'],
                duration_seconds=metadata['duration_seconds'],
                language=language,
                transcript=transcript_segments,
                metadata=VideoMetadata(
                    view_count=metadata['view_count'],
                    like_count=metadata.get('like_count'),
                    comment_count=metadata.get('comment_count'),
                    tags=metadata.get('keywords', []),
                    transcript_type="auto-generated"  # YouTube transcripts are typically auto-generated
                ),
                provenance=Provenance(
                    can_redistribute=False,
                    attribution_required=True,
                    tos_version="youtube_tos_2024"
                ),
                fetched_at=datetime.utcnow(),
                fetched_by="crawler_v1"
            )

            logger.info(f"Successfully crawled video: {video.title} ({video_id})")
            return video

        except ValueError as e:
            # Invalid URL or video ID extraction failed
            logger.error(f"Invalid URL {url}: {e}")
            return None

        except FetchError as e:
            # Fetch error - retry with exponential backoff
            wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s
            logger.warning(f"Attempt {attempt}/{max_retries} failed for {url}: {e}")

            if attempt < max_retries:
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to crawl {url} after {max_retries} attempts")
                return None

        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error crawling {url}: {e}", exc_info=True)
            return None

    return None


def crawl_videos(
    urls: List[str],
    rate_limit: Optional[float] = None,
    max_retries: Optional[int] = None,
    language: str = "en"
) -> Tuple[List[YouTubeVideo], List[str]]:
    """
    Crawl multiple YouTube videos with progress tracking and rate limiting.

    Args:
        urls: List of YouTube URLs to crawl
        rate_limit: Seconds to wait between requests (default: from config)
        max_retries: Maximum retry attempts per video (default: from config)
        language: Transcript language (default: 'en')

    Returns:
        Tuple of (successful_videos, failed_urls)

    Example:
        >>> urls = [
        ...     "https://youtube.com/watch?v=abc123",
        ...     "https://youtube.com/watch?v=xyz789"
        ... ]
        >>> successful, failed = crawl_videos(urls)
        >>> print(f"Crawled {len(successful)} videos")
        >>> print(f"Failed: {len(failed)} videos")
        >>> for video in successful:
        ...     print(f"  - {video.title}")
    """
    if rate_limit is None:
        rate_limit = config.CRAWLER_RATE_LIMIT if config else 2.0

    if max_retries is None:
        max_retries = config.MAX_RETRIES if config else 3

    logger.info(f"Starting crawl of {len(urls)} videos (rate_limit={rate_limit}s, max_retries={max_retries})")

    successful_videos: List[YouTubeVideo] = []
    failed_urls: List[str] = []
    skipped_urls: List[str] = []

    # Progress bar with custom format
    with tqdm(total=len(urls), desc="Crawling videos", unit="video") as pbar:
        for i, url in enumerate(urls):
            # Update progress bar description
            pbar.set_description(
                f"Crawling | Success: {len(successful_videos)} | "
                f"Failed: {len(failed_urls)} | Skipped: {len(skipped_urls)}"
            )

            # Crawl video
            video = crawl_video(url, max_retries=max_retries, language=language)

            if video:
                successful_videos.append(video)
                logger.info(f"✓ [{i+1}/{len(urls)}] {video.title}")
            else:
                # Determine if failed or skipped (no transcript)
                try:
                    video_id = extract_video_id(url)
                    transcript = fetch_transcript(video_id, language=language)
                    if transcript is None:
                        skipped_urls.append(url)
                        logger.info(f"⊘ [{i+1}/{len(urls)}] Skipped (no transcript): {url}")
                    else:
                        failed_urls.append(url)
                        logger.error(f"✗ [{i+1}/{len(urls)}] Failed: {url}")
                except Exception:
                    failed_urls.append(url)
                    logger.error(f"✗ [{i+1}/{len(urls)}] Failed: {url}")

            # Update progress
            pbar.update(1)

            # Rate limiting (don't sleep after last video)
            if i < len(urls) - 1:
                time.sleep(rate_limit)

    # Final summary
    logger.info(
        f"Crawl complete: {len(successful_videos)} successful, "
        f"{len(failed_urls)} failed, {len(skipped_urls)} skipped"
    )

    return successful_videos, failed_urls


class YouTubeCrawler(BaseCrawler):
    """
    YouTube crawler implementation extending BaseCrawler.

    This class provides a structured crawler interface compatible with
    the BaseCrawler abstract class while using the functional crawling
    methods defined above.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize YouTube crawler with optional configuration."""
        super().__init__(config)
        self.language = self.config.get('language', 'en')
        logger.info(f"YouTubeCrawler initialized (language={self.language})")

    def fetch(self, url: str) -> Dict[str, Any]:
        """
        Fetch raw data from YouTube.

        Args:
            url: YouTube video URL

        Returns:
            Dictionary with metadata and transcript

        Raises:
            FetchError: If fetch fails
        """
        try:
            video_id = extract_video_id(url)
            metadata = fetch_video_metadata(video_id)
            transcript = fetch_transcript(video_id, language=self.language)

            return {
                'metadata': metadata,
                'transcript': transcript,
                'video_id': video_id
            }
        except Exception as e:
            raise FetchError(f"Failed to fetch {url}: {e}") from e

    def parse(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse raw data into structured format.

        Args:
            raw_data: Raw data from fetch()

        Returns:
            Dictionary containing parsed YouTubeVideo data

        Raises:
            ParseError: If parsing fails
        """
        try:
            if not raw_data.get('transcript'):
                raise ParseError("No transcript available")

            metadata = raw_data['metadata']
            transcript_data = raw_data['transcript']

            # Create transcript segments
            transcript_segments = []
            for segment in transcript_data:
                ts = TranscriptSegment(
                    text=segment['text'],
                    start=segment['start'],
                    duration=segment['duration']
                )
                transcript_segments.append(ts)

            # Build video object
            video = YouTubeVideo(
                source="youtube",
                source_id=raw_data['video_id'],
                source_url=metadata['url'],
                content_type="vlog",
                title=metadata['title'],
                author=metadata['author'],
                author_url=metadata['channel_url'],
                published_date=metadata['published_date'],
                duration_seconds=metadata['duration_seconds'],
                language=self.language,
                transcript=transcript_segments,
                metadata=VideoMetadata(
                    view_count=metadata['view_count'],
                    like_count=metadata.get('like_count'),
                    comment_count=metadata.get('comment_count'),
                    tags=metadata.get('keywords', []),
                    transcript_type="auto-generated"
                )
            )

            return video.to_dict()

        except Exception as e:
            raise ParseError(f"Failed to parse video data: {e}") from e

    def save(self, parsed_data: Dict[str, Any], destination: str) -> bool:
        """
        Save parsed data to destination.

        Args:
            parsed_data: Parsed video data
            destination: File path to save to

        Returns:
            True if successful

        Raises:
            SaveError: If save fails
        """
        import json
        from pathlib import Path

        try:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(dest_path, 'w', encoding='utf-8') as f:
                json.dump(parsed_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved video data to {destination}")
            return True

        except Exception as e:
            from src.crawlers.base import SaveError
            raise SaveError(f"Failed to save to {destination}: {e}") from e


# Example usage and testing
if __name__ == "__main__":
    from src.utils.logging import setup_logging

    # Setup logging
    setup_logging("INFO")

    print("=" * 70)
    print("YOUTUBE CRAWLER EXAMPLE")
    print("=" * 70)

    # Example URLs (replace with real URLs for testing)
    example_urls = [
        "https://youtube.com/watch?v=dQw4w9WgXcQ",  # Example URL
    ]

    print("\n1. Testing single video crawl...")
    print("-" * 70)
    video = crawl_video(example_urls[0])
    if video:
        print(f"✓ Successfully crawled video:")
        print(f"  Title: {video.title}")
        print(f"  Author: {video.author}")
        print(f"  Duration: {video.duration_seconds}s")
        print(f"  Language: {video.language}")
        print(f"  Transcript segments: {len(video.transcript)}")
        print(f"  View count: {video.metadata.view_count:,}")
        print(f"  Tags: {', '.join(video.metadata.tags[:5])}")
    else:
        print("✗ Failed to crawl video")

    print("\n2. Testing multiple video crawl...")
    print("-" * 70)
    successful, failed = crawl_videos(example_urls)
    print(f"\nResults:")
    print(f"  Successful: {len(successful)}")
    print(f"  Failed: {len(failed)}")

    if successful:
        print(f"\nSuccessfully crawled videos:")
        for v in successful:
            print(f"  - {v.title} ({v.duration_seconds}s, {len(v.transcript)} segments)")

    if failed:
        print(f"\nFailed URLs:")
        for url in failed:
            print(f"  - {url}")

    print("\n" + "=" * 70)
    print("Example complete!")
    print("=" * 70)
