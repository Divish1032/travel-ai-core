"""
Universal Content ID System for Travel AI

Provides a consistent ID format across multiple content sources (YouTube, Reddit,
blogs, websites) to enable unified content tracking and deduplication.

Content ID Format:
    - YouTube: youtube_{video_id}
    - Reddit: reddit_t3_{post_id}
    - Blog: blog_{url_hash}
    - Website: web_{url_hash}

Usage:
    from src.utils.content_id import generate_content_id, parse_content_id

    # YouTube video
    youtube_id = generate_content_id(
        source="youtube",
        source_url="https://youtube.com/watch?v=abc123"
    )
    # Returns: "youtube_abc123"

    # Reddit post
    reddit_id = generate_content_id(
        source="reddit",
        source_url="https://reddit.com/r/travel/comments/xyz789/my_post"
    )
    # Returns: "reddit_t3_xyz789"

    # Blog post
    blog_id = generate_content_id(
        source="blog",
        source_url="https://travelblog.com/best-beaches"
    )
    # Returns: "blog_a1b2c3d4"

    # Parse content ID
    info = parse_content_id("youtube_abc123")
    # Returns: {"source": "youtube", "id": "abc123"}
"""
import hashlib
import re
from typing import Optional, Dict
from urllib.parse import urlparse, parse_qs, urlencode


def extract_youtube_id(url: str) -> str:
    """
    Extract video ID from various YouTube URL formats.

    Supports formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtube.com/watch?v=VIDEO_ID&t=30s
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID

    Args:
        url: YouTube video URL

    Returns:
        11-character YouTube video ID

    Raises:
        ValueError: If video ID cannot be extracted or URL is invalid

    Examples:
        >>> extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_youtube_id("https://youtu.be/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
        >>> extract_youtube_id("https://youtube.com/embed/dQw4w9WgXcQ")
        'dQw4w9WgXcQ'
    """
    if not url or not isinstance(url, str):
        raise ValueError(f"Invalid URL: {url}")

    # Patterns for different YouTube URL formats
    patterns = [
        # Standard: youtube.com/watch?v=VIDEO_ID
        r'(?:youtube\.com/watch\?v=|youtube\.com/watch\?.*&v=)([a-zA-Z0-9_-]+)',
        # Short: youtu.be/VIDEO_ID
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        # Embed: youtube.com/embed/VIDEO_ID
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        # Mobile: m.youtube.com/watch?v=VIDEO_ID
        r'm\.youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            # YouTube video IDs are typically 11 characters, but allow some flexibility
            if 6 <= len(video_id) <= 15:
                return video_id

    raise ValueError(
        f"Could not extract YouTube video ID from URL: {url}. "
        "Expected format: youtube.com/watch?v=VIDEO_ID or youtu.be/VIDEO_ID"
    )


def extract_reddit_id(url: str) -> str:
    """
    Extract post ID from Reddit URL and format with t3_ prefix.

    Reddit post IDs use the format t3_{post_id} where t3 indicates it's a post
    (as opposed to t1 for comments, t2 for users, etc.)

    Supports formats:
        - https://www.reddit.com/r/travel/comments/POST_ID/title
        - https://reddit.com/r/travel/comments/POST_ID/
        - https://old.reddit.com/r/travel/comments/POST_ID/title

    Args:
        url: Reddit post URL

    Returns:
        Reddit post ID in format "t3_POST_ID"

    Raises:
        ValueError: If post ID cannot be extracted or URL is invalid

    Examples:
        >>> extract_reddit_id("https://reddit.com/r/travel/comments/abc123/my_post")
        't3_abc123'
        >>> extract_reddit_id("https://www.reddit.com/r/travel/comments/xyz789/")
        't3_xyz789'
    """
    if not url or not isinstance(url, str):
        raise ValueError(f"Invalid URL: {url}")

    # Pattern for Reddit post URL
    # Format: /r/SUBREDDIT/comments/POST_ID/...
    pattern = r'reddit\.com/r/[^/]+/comments/([a-z0-9]+)'

    match = re.search(pattern, url, re.IGNORECASE)
    if match:
        post_id = match.group(1)
        # Reddit post IDs are typically 6-7 alphanumeric characters
        if 5 <= len(post_id) <= 10 and post_id.isalnum():
            return f"t3_{post_id}"

    raise ValueError(
        f"Could not extract Reddit post ID from URL: {url}. "
        "Expected format: reddit.com/r/SUBREDDIT/comments/POST_ID/..."
    )


def generate_url_hash(url: str) -> str:
    """
    Generate deterministic 8-character hash from normalized URL.

    Normalization steps:
        1. Convert to lowercase
        2. Parse URL components
        3. Remove query parameters
        4. Remove fragment (#section)
        5. Remove trailing slash
        6. Generate MD5 hash
        7. Return first 8 characters

    This ensures the same URL always produces the same hash, even if it has
    different query parameters or trailing slashes.

    Args:
        url: Website or blog URL

    Returns:
        8-character hexadecimal hash

    Raises:
        ValueError: If URL is invalid or empty

    Examples:
        >>> generate_url_hash("https://example.com/blog/post")
        'a1b2c3d4'
        >>> generate_url_hash("https://example.com/blog/post/")
        'a1b2c3d4'  # Same as above (trailing slash removed)
        >>> generate_url_hash("https://example.com/blog/post?utm=source")
        'a1b2c3d4'  # Same as above (query params removed)
    """
    if not url or not isinstance(url, str):
        raise ValueError(f"Invalid URL: {url}")

    try:
        # Parse URL
        parsed = urlparse(url.lower())

        # Validate URL has scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"URL must have scheme and domain: {url}")

        # Normalize URL components
        scheme = parsed.scheme
        netloc = parsed.netloc
        path = parsed.path.rstrip('/')  # Remove trailing slash

        # Reconstruct normalized URL (without query params or fragment)
        normalized_url = f"{scheme}://{netloc}{path}"

        # Generate MD5 hash
        hash_obj = hashlib.md5(normalized_url.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()

        # Return first 8 characters
        return hash_hex[:8]

    except Exception as e:
        raise ValueError(f"Failed to generate hash for URL {url}: {e}")


def generate_content_id(
    source: str,
    source_url: str,
    source_id: Optional[str] = None
) -> str:
    """
    Generate universal content ID from source and URL.

    Routes to appropriate ID generator based on source type.
    IDs are deterministic - same URL always produces same ID.

    Args:
        source: Content source type ("youtube", "reddit", "blog", "website")
        source_url: Source URL to generate ID from
        source_id: Optional pre-extracted ID (for sources that provide it)

    Returns:
        Content ID in format "{source}_{identifier}"

    Raises:
        ValueError: If source is invalid or URL cannot be processed

    Examples:
        # YouTube video
        >>> generate_content_id("youtube", "https://youtube.com/watch?v=abc123")
        'youtube_abc123'

        # Reddit post
        >>> generate_content_id("reddit", "https://reddit.com/r/travel/comments/xyz789/post")
        'reddit_t3_xyz789'

        # Blog post
        >>> generate_content_id("blog", "https://travelblog.com/best-beaches")
        'blog_a1b2c3d4'

        # Website with pre-provided ID
        >>> generate_content_id("youtube", "https://youtube.com/watch?v=abc123", source_id="abc123")
        'youtube_abc123'
    """
    # Validate source
    valid_sources = {"youtube", "reddit", "blog", "website"}
    source_lower = source.lower()

    if source_lower not in valid_sources:
        raise ValueError(
            f"Invalid source: {source}. "
            f"Must be one of: {', '.join(sorted(valid_sources))}"
        )

    # If source_id provided, use it directly
    if source_id:
        return f"{source_lower}_{source_id}"

    # Generate ID based on source type
    if source_lower == "youtube":
        video_id = extract_youtube_id(source_url)
        return f"youtube_{video_id}"

    elif source_lower == "reddit":
        post_id = extract_reddit_id(source_url)
        return f"reddit_{post_id}"

    elif source_lower == "blog":
        url_hash = generate_url_hash(source_url)
        return f"blog_{url_hash}"

    elif source_lower == "website":
        url_hash = generate_url_hash(source_url)
        return f"web_{url_hash}"

    else:
        # This should never happen due to validation above, but just in case
        raise ValueError(f"Unsupported source: {source}")


def parse_content_id(content_id: str) -> Dict[str, str]:
    """
    Parse content ID into source and identifier components.

    Args:
        content_id: Content ID in format "{source}_{identifier}"

    Returns:
        Dictionary with keys "source" and "id"

    Raises:
        ValueError: If content ID format is invalid

    Examples:
        >>> parse_content_id("youtube_abc123")
        {'source': 'youtube', 'id': 'abc123'}

        >>> parse_content_id("reddit_t3_xyz789")
        {'source': 'reddit', 'id': 't3_xyz789'}

        >>> parse_content_id("blog_a1b2c3d4")
        {'source': 'blog', 'id': 'a1b2c3d4'}
    """
    if not content_id or not isinstance(content_id, str):
        raise ValueError(f"Invalid content ID: {content_id}")

    # Split on first underscore only
    parts = content_id.split('_', 1)

    if len(parts) != 2:
        raise ValueError(
            f"Invalid content ID format: {content_id}. "
            "Expected format: source_identifier"
        )

    source, identifier = parts

    # Validate source
    valid_sources = {"youtube", "reddit", "blog", "web", "website"}
    if source not in valid_sources:
        raise ValueError(
            f"Invalid source in content ID: {source}. "
            f"Must be one of: {', '.join(sorted(valid_sources))}"
        )

    # Validate identifier is not empty
    if not identifier:
        raise ValueError(f"Empty identifier in content ID: {content_id}")

    return {
        "source": source,
        "id": identifier
    }


def is_valid_content_id(content_id: str) -> bool:
    """
    Check if a content ID is valid.

    Args:
        content_id: Content ID to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> is_valid_content_id("youtube_abc123")
        True
        >>> is_valid_content_id("invalid")
        False
        >>> is_valid_content_id("youtube_")
        False
    """
    try:
        parse_content_id(content_id)
        return True
    except ValueError:
        return False


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("CONTENT ID SYSTEM EXAMPLES")
    print("=" * 70)

    # YouTube examples
    print("\n1. YouTube Videos:")
    youtube_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
        "https://youtube.com/embed/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    ]

    for url in youtube_urls:
        content_id = generate_content_id("youtube", url)
        print(f"  URL: {url}")
        print(f"  ID:  {content_id}")
        print()

    # Reddit examples
    print("2. Reddit Posts:")
    reddit_urls = [
        "https://www.reddit.com/r/travel/comments/abc123/best_beaches_in_asia",
        "https://reddit.com/r/travel/comments/xyz789/",
        "https://old.reddit.com/r/travel/comments/def456/europe_trip_guide",
        "https://www.reddit.com/r/solotravel/comments/ghi789/budget_travel_tips",
        "https://reddit.com/r/backpacking/comments/jkl012/gear_recommendations",
    ]

    for url in reddit_urls:
        content_id = generate_content_id("reddit", url)
        print(f"  URL: {url}")
        print(f"  ID:  {content_id}")
        print()

    # Blog examples
    print("3. Blog Posts:")
    blog_urls = [
        "https://travelblog.com/best-beaches-2024",
        "https://wanderlust.com/europe/italy/rome-guide",
        "https://nomadicmatt.com/travel-guides/thailand-travel-tips",
        "https://expertva.com/blog/budget-travel",
        "https://travelfreak.com/asia/vietnam/hanoi",
    ]

    for url in blog_urls:
        content_id = generate_content_id("blog", url)
        print(f"  URL: {url}")
        print(f"  ID:  {content_id}")
        print()

    # Website examples
    print("4. General Websites:")
    website_urls = [
        "https://lonelyplanet.com/japan/tokyo",
        "https://tripadvisor.com/Attraction_Review-g123-d456.html",
        "https://wikivoyage.org/wiki/Bangkok",
        "https://timeanddate.com/weather/thailand/bangkok",
        "https://example.com/travel/destinations/paris?utm_source=google",
    ]

    for url in website_urls:
        content_id = generate_content_id("website", url)
        print(f"  URL: {url}")
        print(f"  ID:  {content_id}")
        print()

    # Parsing examples
    print("5. Parsing Content IDs:")
    content_ids = [
        "youtube_dQw4w9WgXcQ",
        "reddit_t3_abc123",
        "blog_a1b2c3d4",
        "web_e5f6g7h8",
    ]

    for cid in content_ids:
        parsed = parse_content_id(cid)
        print(f"  Content ID: {cid}")
        print(f"  Source:     {parsed['source']}")
        print(f"  ID:         {parsed['id']}")
        print(f"  Valid:      {is_valid_content_id(cid)}")
        print()

    # Validation examples
    print("6. Validation:")
    test_ids = [
        ("youtube_abc123", True),
        ("invalid", False),
        ("youtube_", False),
        ("_abc123", False),
        ("reddit_t3_xyz789", True),
    ]

    for test_id, expected in test_ids:
        valid = is_valid_content_id(test_id)
        status = "✓" if valid == expected else "✗"
        print(f"  {status} {test_id}: {valid}")

    # Deterministic hash test
    print("\n7. Deterministic Hash Test:")
    test_urls = [
        "https://example.com/blog/post",
        "https://example.com/blog/post/",
        "https://EXAMPLE.com/blog/post",
        "https://example.com/blog/post?utm_source=google",
    ]

    hashes = [generate_content_id("blog", url) for url in test_urls]
    all_same = len(set(hashes)) == 1

    print(f"  All URLs produce same hash: {all_same}")
    for url, hash_id in zip(test_urls, hashes):
        print(f"    {url}")
        print(f"    → {hash_id}")

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
