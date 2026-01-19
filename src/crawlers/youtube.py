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
import os
import subprocess
import tempfile
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tqdm import tqdm
import whisper

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
    - https://youtube.com/shorts/VIDEO_ID (YouTube Shorts)

    Args:
        url: YouTube URL

    Returns:
        Video ID string

    Raises:
        ValueError: If video ID cannot be extracted

    Example:
        >>> extract_video_id("https://youtube.com/watch?v=abc123")
        'abc123'
        >>> extract_video_id("https://youtube.com/shorts/abc123")
        'abc123'
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|m\.youtube\.com/watch\?v=|youtube\.com/shorts/)([a-zA-Z0-9_-]+)',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            # Allow flexible video ID lengths (typically 11, but allow 6-15)
            if 6 <= len(video_id) <= 15:
                logger.debug(f"Extracted video ID: {video_id} from {url}")
                return video_id

    raise ValueError(f"Could not extract video ID from URL: {url}")


def fetch_video_metadata(video_id: str) -> Dict[str, Any]:
    """
    Fetch video metadata using YouTube Data API v3.

    Args:
        video_id: YouTube video ID

    Returns:
        Dictionary containing video metadata including:
        - video_id, url, title, author, channel_url
        - duration_seconds, published_date, view_count
        - like_count, comment_count (new with official API!)
        - description, keywords

    Raises:
        FetchError: If metadata fetch fails or API key is missing

    Example:
        >>> metadata = fetch_video_metadata("abc123")
        >>> print(metadata['title'])
        >>> print(f"Likes: {metadata['like_count']}")

    Note:
        Requires YOUTUBE_API_KEY in environment variables.
        Get a free API key from: https://console.cloud.google.com/apis/credentials
    """
    # Import config inside function to allow mocking in tests
    from src.utils import config as config_module
    config = config_module.config

    if not config or not config.YOUTUBE_API_KEY:
        raise FetchError(
            "YouTube API key not configured. "
            "Please set YOUTUBE_API_KEY in your .env file. "
            "Get a free API key from: https://console.cloud.google.com/apis/credentials"
        )

    try:
        url = f"https://youtube.com/watch?v={video_id}"
        logger.debug(f"Fetching metadata for video: {video_id}")

        # Build YouTube API client
        youtube = build('youtube', 'v3', developerKey=config.YOUTUBE_API_KEY)

        # Request video details
        request = youtube.videos().list(
            part='snippet,contentDetails,statistics',
            id=video_id
        )
        response = request.execute()

        # Check if video exists
        if not response.get('items'):
            raise FetchError(f"Video not found: {video_id}")

        item = response['items'][0]
        snippet = item['snippet']
        content_details = item['contentDetails']
        statistics = item.get('statistics', {})

        # Parse ISO 8601 duration (e.g., "PT15M33S" -> 933 seconds)
        duration_str = content_details['duration']
        duration_seconds = _parse_iso8601_duration(duration_str)

        # Extract metadata
        metadata = {
            'video_id': video_id,
            'url': url,
            'title': snippet['title'],
            'author': snippet['channelTitle'],
            'channel_url': f"https://youtube.com/channel/{snippet['channelId']}",
            'duration_seconds': duration_seconds,
            'published_date': snippet['publishedAt'][:10],  # "2024-03-15T10:30:00Z" -> "2024-03-15"
            'view_count': int(statistics.get('viewCount', 0)),
            'like_count': int(statistics.get('likeCount', 0)),
            'comment_count': int(statistics.get('commentCount', 0)),
            'favorite_count': int(statistics.get('favoriteCount', 0)),
            'description': snippet.get('description', ''),
            'keywords': snippet.get('tags', []),
        }

        logger.debug(f"Successfully fetched metadata for {video_id}: {metadata['title']}")
        return metadata

    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        if e.resp.status == 403:
            raise FetchError(
                f"YouTube API quota exceeded or invalid API key. "
                f"Error: {error_content}"
            ) from e
        elif e.resp.status == 404:
            raise FetchError(f"Video not found: {video_id}") from e
        else:
            raise FetchError(f"YouTube API error for {video_id}: {error_content}") from e
    except Exception as e:
        raise FetchError(f"Unexpected error fetching metadata for {video_id}: {e}") from e


def _parse_iso8601_duration(duration_str: str) -> int:
    """
    Parse ISO 8601 duration string to seconds.

    Args:
        duration_str: ISO 8601 duration (e.g., "PT15M33S", "PT1H2M10S")

    Returns:
        Duration in seconds

    Examples:
        >>> _parse_iso8601_duration("PT15M33S")
        933
        >>> _parse_iso8601_duration("PT1H2M10S")
        3730
    """
    import re

    # Remove PT prefix
    duration_str = duration_str.replace('PT', '')

    # Extract hours, minutes, seconds
    hours = 0
    minutes = 0
    seconds = 0

    hour_match = re.search(r'(\d+)H', duration_str)
    if hour_match:
        hours = int(hour_match.group(1))

    minute_match = re.search(r'(\d+)M', duration_str)
    if minute_match:
        minutes = int(minute_match.group(1))

    second_match = re.search(r'(\d+)S', duration_str)
    if second_match:
        seconds = int(second_match.group(1))

    return hours * 3600 + minutes * 60 + seconds


def download_audio(video_id: str, video_url: str) -> Optional[str]:
    """
    Download audio from YouTube video using yt-dlp.

    Args:
        video_id: YouTube video ID
        video_url: Full YouTube URL

    Returns:
        Path to downloaded audio file, or None if failed

    Example:
        >>> audio_path = download_audio("abc123", "https://youtube.com/watch?v=abc123")
    """
    try:
        logger.info(f"  → Downloading audio for {video_id}...")

        # Create temporary directory for audio file
        temp_dir = tempfile.gettempdir()
        output_template = os.path.join(temp_dir, f"yt_audio_{video_id}.%(ext)s")

        # Build yt-dlp command with browser cookies support
        cmd = [
            "yt-dlp",
            "--cookies-from-browser", "chrome",  # Use Chrome cookies (change to "firefox", "safari", etc. as needed)
            "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "-x", "--audio-format", "mp3",
            "-o", output_template,
            "--no-playlist",
            "--quiet",  # Suppress most output
            "--progress",  # Show download progress
            video_url
        ]

        # Run yt-dlp to download audio
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for download
        )

        if result.returncode != 0:
            logger.error(f"yt-dlp error for {video_id}: {result.stderr}")
            return None

        # Find the downloaded file
        audio_file = os.path.join(temp_dir, f"yt_audio_{video_id}.mp3")
        if os.path.exists(audio_file):
            logger.info(f"  ✓ Audio downloaded ({os.path.getsize(audio_file) / 1024 / 1024:.1f} MB)")
            return audio_file
        else:
            logger.error(f"Audio file not found after download: {audio_file}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"Download timeout for {video_id} (>5 minutes)")
        return None
    except Exception as e:
        logger.error(f"Error downloading audio for {video_id}: {e}")
        return None


def transcribe_audio(audio_file: str, video_id: str, model: Any = None) -> Optional[Tuple[List[Dict[str, Any]], str]]:
    """
    Transcribe audio file using Whisper.

    Args:
        audio_file: Path to audio file
        video_id: YouTube video ID (for logging)
        model: Whisper model instance (if None, loads 'small' model)

    Returns:
        Tuple of (segments, detected_language) or None if failed
        - segments: List of transcript segments with text, start, and duration
        - detected_language: ISO 639-1 language code (e.g., 'en', 'hi', 'es')

    Example:
        >>> result = transcribe_audio("/tmp/audio.mp3", "abc123")
        >>> if result:
        ...     segments, language = result
        ...     print(f"Detected language: {language}")
    """
    try:
        logger.info("  → Transcribing audio with Whisper (this may take 1-2 minutes)...")

        # Load Whisper model if not provided
        if model is None:
            logger.debug("Loading Whisper 'small' model...")
            model = whisper.load_model("small")

        # Transcribe with Whisper
        result = model.transcribe(audio_file, verbose=False)

        if not result or 'segments' not in result:
            logger.warning(f"No segments returned from Whisper for {video_id}")
            return None

        # Extract detected language (Whisper auto-detects)
        detected_language = result.get('language', 'en')

        # Convert Whisper segments to our format
        segments = []
        for seg in result['segments']:
            # Calculate duration from start and end times
            duration = seg['end'] - seg['start']
            segments.append({
                'text': seg['text'].strip(),
                'start': seg['start'],  # seconds (float)
                'duration': duration  # seconds (float)
            })

        logger.info(f"  ✓ Transcription complete ({len(segments)} segments)")
        logger.info(f"  ✓ Detected language: {detected_language}")

        return (segments, detected_language)

    except Exception as e:
        logger.error(f"Error transcribing audio for {video_id}: {e}")
        return None


def fetch_transcript(video_id: str, language: str = "en") -> Optional[Tuple[List[Dict[str, Any]], str]]:
    """
    Fetch video transcript using Whisper + yt-dlp.

    This function:
    1. Downloads audio from YouTube using yt-dlp
    2. Transcribes audio using Whisper (small model)
    3. Returns transcript segments and detected language
    4. Cleans up temporary audio file

    Args:
        video_id: YouTube video ID
        language: Language code (default: 'en') - NOT USED, Whisper auto-detects language

    Returns:
        Tuple of (segments, detected_language) or None if unavailable
        - segments: List of transcript segments with text, start, and duration
        - detected_language: ISO 639-1 language code detected by Whisper

    Raises:
        FetchError: If transcript fetch fails unexpectedly

    Example:
        >>> result = fetch_transcript("abc123")
        >>> if result:
        ...     segments, language = result
        ...     print(f"Language: {language}")
        ...     print(segments[0]['text'])
    """
    audio_file = None
    try:
        # Construct YouTube URL
        video_url = f"https://youtube.com/watch?v={video_id}"

        # Step 1: Download audio
        audio_file = download_audio(video_id, video_url)
        if not audio_file:
            logger.warning(f"Could not download audio for {video_id}")
            return None

        # Step 2: Transcribe audio (returns segments and detected language)
        # Note: Load model once per batch for efficiency (handled by caller)
        result = transcribe_audio(audio_file, video_id)

        if not result:
            return None

        segments, detected_language = result
        return (segments, detected_language)

    except Exception as e:
        logger.error(f"Unexpected error fetching transcript for {video_id}: {e}")
        return None
    finally:
        # Always clean up audio file
        if audio_file and os.path.exists(audio_file):
            try:
                os.remove(audio_file)
                logger.debug(f"Cleaned up audio file: {audio_file}")
            except Exception as e:
                logger.warning(f"Could not remove audio file {audio_file}: {e}")


def crawl_video(
    url: str,
    max_retries: Optional[int] = None,
    language: str = "en",
    show_progress: bool = True
) -> Optional[YouTubeVideo]:
    """
    Crawl a single YouTube video: fetch metadata + transcript and validate.

    This process includes:
    1. Extract video ID from URL
    2. Fetch metadata from YouTube Data API (~2-5 seconds)
    3. Download audio using yt-dlp (~15-60 seconds depending on video length)
    4. Transcribe audio using Whisper (~1-3 minutes depending on video length)
    5. Validate and structure the data

    Args:
        url: YouTube video URL
        max_retries: Maximum retry attempts (default: from config)
        language: Transcript language (default: 'en')
        show_progress: Show progress messages (default: True)

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

    if show_progress:
        logger.info(f"\n{'='*70}")
        logger.info(f"Crawling video: {url}")
        logger.info(f"{'='*70}")

    for attempt in range(1, max_retries + 1):
        start_time = time.time()
        try:
            # Extract video ID
            video_id = extract_video_id(url)

            # Step 1: Fetch metadata
            if show_progress:
                logger.info("[1/3] Fetching video metadata...")
            metadata_start = time.time()
            metadata = fetch_video_metadata(video_id)
            metadata_time = time.time() - metadata_start

            if show_progress:
                logger.info(f"  ✓ Metadata fetched in {metadata_time:.1f}s")
                logger.info(f"  → Title: {metadata['title']}")
                logger.info(f"  → Duration: {metadata['duration_seconds']}s ({metadata['duration_seconds']//60} min)")

            # Step 2 & 3: Fetch transcript (download + transcribe)
            if show_progress:
                logger.info("\n[2/3] Downloading audio and transcribing...")
                logger.info("  ⏱  Estimated time: 2-4 minutes")
            transcript_start = time.time()
            transcript_result = fetch_transcript(video_id, language=language)
            transcript_time = time.time() - transcript_start

            if not transcript_result:
                logger.warning(f"No transcript available for {url}, skipping")
                return None

            # Unpack transcript segments and detected language
            transcript_data, detected_language = transcript_result

            if show_progress:
                logger.info(f"  ✓ Transcription complete in {transcript_time:.1f}s ({transcript_time//60:.0f} min {transcript_time%60:.0f}s)")

            # Step 4: Validate and create transcript segments
            if show_progress:
                logger.info("\n[3/3] Validating and structuring data...")
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
                description=metadata['description'],
                language=detected_language,  # Use Whisper's detected language
                transcript=transcript_segments,
                metadata=VideoMetadata(
                    view_count=metadata['view_count'],
                    favorite_count=metadata.get('favorite_count'),
                    like_count=metadata.get('like_count'),
                    comment_count=metadata.get('comment_count'),
                    tags=metadata.get('keywords', []),
                    transcript_type="whisper"  # Whisper transcription
                ),
                provenance=Provenance(
                    can_redistribute=False,
                    attribution_required=True,
                    tos_version="youtube_tos_2024"
                ),
                fetched_at=datetime.now(timezone.utc),
                fetched_by="crawler_v1_whisper"
            )

            total_time = time.time() - start_time
            if show_progress:
                logger.info("  ✓ Data validated successfully")
                logger.info(f"\n{'='*70}")
                logger.info(f"✅ Successfully crawled: {video.title}")
                logger.info(f"   Total time: {total_time:.1f}s ({total_time//60:.0f} min {total_time%60:.0f}s)")
                logger.info(f"   Transcript segments: {len(transcript_segments)}")
                logger.info(f"{'='*70}\n")

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
    Crawl multiple YouTube videos with detailed progress tracking.

    Process per video (~2-5 minutes each):
    1. Fetch metadata (~5 seconds)
    2. Download audio (~30-60 seconds)
    3. Transcribe with Whisper (~1-3 minutes)

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

    # Estimate total time (average 3 minutes per video)
    estimated_minutes = len(urls) * 3
    logger.info(f"\n{'='*80}")
    logger.info("STARTING BATCH CRAWL")
    logger.info(f"{'='*80}")
    logger.info(f"Total videos: {len(urls)}")
    logger.info(f"Estimated time: ~{estimated_minutes} minutes ({estimated_minutes//60}h {estimated_minutes%60}m)")
    logger.info(f"Rate limit: {rate_limit}s between videos")
    logger.info(f"Max retries: {max_retries}")
    logger.info(f"{'='*80}\n")

    successful_videos: List[YouTubeVideo] = []
    failed_urls: List[str] = []
    skipped_urls: List[str] = []
    batch_start_time = time.time()

    # Progress bar with custom format
    with tqdm(total=len(urls), desc="Processing videos", unit="video", ncols=100) as pbar:
        for i, url in enumerate(urls):
            video_start_time = time.time()

            # Calculate ETA
            if i > 0:
                avg_time_per_video = (time.time() - batch_start_time) / i
                remaining_videos = len(urls) - i
                eta_seconds = avg_time_per_video * remaining_videos
                eta_minutes = int(eta_seconds // 60)
                eta_secs = int(eta_seconds % 60)
                eta_str = f"ETA: {eta_minutes}m {eta_secs}s"
            else:
                eta_str = "Calculating ETA..."

            # Update progress bar description
            pbar.set_description(
                f"Video {i+1}/{len(urls)} | ✓ {len(successful_videos)} | "
                f"✗ {len(failed_urls)} | ⊘ {len(skipped_urls)} | {eta_str}"
            )

            # Crawl video (with detailed progress inside)
            video = crawl_video(url, max_retries=max_retries, language=language, show_progress=False)

            video_time = time.time() - video_start_time

            if video:
                successful_videos.append(video)
                logger.info(
                    f"✅ [{i+1}/{len(urls)}] SUCCESS: {video.title[:50]}... "
                    f"({video_time//60:.0f}m {video_time%60:.0f}s)"
                )
            else:
                # Check if failed or skipped
                try:
                    # Just mark as failed - don't retry transcript fetch
                    failed_urls.append(url)
                    logger.error(f"❌ [{i+1}/{len(urls)}] FAILED: {url}")
                except Exception:
                    failed_urls.append(url)
                    logger.error(f"❌ [{i+1}/{len(urls)}] FAILED: {url}")

            # Update progress
            pbar.update(1)

            # Rate limiting (don't sleep after last video)
            if i < len(urls) - 1:
                time.sleep(rate_limit)

    # Final summary
    total_time = time.time() - batch_start_time
    logger.info(f"\n{'='*80}")
    logger.info("BATCH CRAWL COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Total time: {total_time//60:.0f}m {total_time%60:.0f}s")
    logger.info(f"✅ Successful: {len(successful_videos)}/{len(urls)} videos")
    logger.info(f"❌ Failed: {len(failed_urls)}/{len(urls)} videos")
    logger.info(f"⊘ Skipped: {len(skipped_urls)}/{len(urls)} videos")
    logger.info(f"Average time per video: {total_time/len(urls):.1f}s")
    logger.info(f"{'='*80}\n")

    if successful_videos:
        logger.info("Successfully crawled videos:")
        for v in successful_videos:
            logger.info(f"  - {v.title} ({len(v.transcript)} segments)")

    if failed_urls:
        logger.warning(f"\nFailed URLs ({len(failed_urls)}):")
        for url in failed_urls:
            logger.warning(f"  - {url}")

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
        print("✓ Successfully crawled video:")
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
    print("\nResults:")
    print(f"  Successful: {len(successful)}")
    print(f"  Failed: {len(failed)}")

    if successful:
        print("\nSuccessfully crawled videos:")
        for v in successful:
            print(f"  - {v.title} ({v.duration_seconds}s, {len(v.transcript)} segments)")

    if failed:
        print("\nFailed URLs:")
        for url in failed:
            print(f"  - {url}")

    print("\n" + "=" * 70)
    print("Example complete!")
    print("=" * 70)
