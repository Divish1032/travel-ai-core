"""
Test suite for content ID system (src/utils/content_id.py).

Tests universal content ID generation and parsing for YouTube, Reddit,
blogs, and websites.

Run with:
    pytest tests/test_content_id.py -v
    pytest tests/test_content_id.py::test_extract_youtube_id -v
"""
import pytest

from src.utils.content_id import (
    extract_youtube_id,
    extract_reddit_id,
    generate_url_hash,
    generate_content_id,
    parse_content_id,
    is_valid_content_id
)


################################################################################
# Test: extract_youtube_id
################################################################################

def test_extract_youtube_id_standard_url():
    """Test extraction from standard YouTube URL."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"
    assert len(video_id) == 11


def test_extract_youtube_id_short_url():
    """Test extraction from short youtu.be URL."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"


def test_extract_youtube_id_embed_url():
    """Test extraction from embed URL."""
    url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"


def test_extract_youtube_id_mobile_url():
    """Test extraction from mobile URL."""
    url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"


def test_extract_youtube_id_with_parameters():
    """Test extraction from URL with query parameters."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s&list=PLxxx"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"


def test_extract_youtube_id_without_www():
    """Test extraction from URL without www."""
    url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = extract_youtube_id(url)
    assert video_id == "dQw4w9WgXcQ"


def test_extract_youtube_id_invalid_url():
    """Test that invalid URL raises ValueError."""
    with pytest.raises(ValueError, match="Could not extract YouTube video ID"):
        extract_youtube_id("https://vimeo.com/123456")


def test_extract_youtube_id_empty_url():
    """Test that empty URL raises ValueError."""
    with pytest.raises(ValueError, match="Invalid URL"):
        extract_youtube_id("")


def test_extract_youtube_id_non_string():
    """Test that non-string input raises ValueError."""
    with pytest.raises(ValueError, match="Invalid URL"):
        extract_youtube_id(None)


def test_extract_youtube_id_malformed_url():
    """Test that malformed URL raises ValueError."""
    with pytest.raises(ValueError, match="Could not extract YouTube video ID"):
        extract_youtube_id("https://youtube.com/not_a_video")


################################################################################
# Test: extract_reddit_id
################################################################################

def test_extract_reddit_id_standard_url():
    """Test extraction from standard Reddit post URL."""
    url = "https://www.reddit.com/r/travel/comments/abc123/my_post_title"
    post_id = extract_reddit_id(url)
    assert post_id == "t3_abc123"
    assert post_id.startswith("t3_")


def test_extract_reddit_id_without_www():
    """Test extraction from URL without www."""
    url = "https://reddit.com/r/travel/comments/xyz789/post"
    post_id = extract_reddit_id(url)
    assert post_id == "t3_xyz789"


def test_extract_reddit_id_old_reddit():
    """Test extraction from old.reddit.com URL."""
    url = "https://old.reddit.com/r/travel/comments/def456/title"
    post_id = extract_reddit_id(url)
    assert post_id == "t3_def456"


def test_extract_reddit_id_trailing_slash():
    """Test extraction from URL with trailing slash."""
    url = "https://reddit.com/r/travel/comments/ghi789/"
    post_id = extract_reddit_id(url)
    assert post_id == "t3_ghi789"


def test_extract_reddit_id_case_insensitive():
    """Test that extraction is case-insensitive."""
    url = "https://REDDIT.COM/r/travel/comments/jkl012/post"
    post_id = extract_reddit_id(url)
    assert post_id == "t3_jkl012"


def test_extract_reddit_id_invalid_url():
    """Test that invalid URL raises ValueError."""
    with pytest.raises(ValueError, match="Could not extract Reddit post ID"):
        extract_reddit_id("https://twitter.com/post/123")


def test_extract_reddit_id_empty_url():
    """Test that empty URL raises ValueError."""
    with pytest.raises(ValueError, match="Invalid URL"):
        extract_reddit_id("")


def test_extract_reddit_id_non_reddit_domain():
    """Test that non-Reddit domain raises ValueError."""
    with pytest.raises(ValueError, match="Could not extract Reddit post ID"):
        extract_reddit_id("https://youtube.com/watch?v=123")


################################################################################
# Test: generate_url_hash
################################################################################

def test_generate_url_hash_basic():
    """Test basic URL hash generation."""
    url = "https://example.com/blog/post"
    hash_value = generate_url_hash(url)
    assert isinstance(hash_value, str)
    assert len(hash_value) == 8
    assert hash_value.isalnum()


def test_generate_url_hash_deterministic():
    """Test that same URL always produces same hash."""
    url = "https://example.com/blog/post"
    hash1 = generate_url_hash(url)
    hash2 = generate_url_hash(url)
    assert hash1 == hash2


def test_generate_url_hash_ignores_trailing_slash():
    """Test that trailing slash doesn't affect hash."""
    url1 = "https://example.com/blog/post"
    url2 = "https://example.com/blog/post/"
    hash1 = generate_url_hash(url1)
    hash2 = generate_url_hash(url2)
    assert hash1 == hash2


def test_generate_url_hash_ignores_query_params():
    """Test that query parameters don't affect hash."""
    url1 = "https://example.com/blog/post"
    url2 = "https://example.com/blog/post?utm_source=google&utm_medium=cpc"
    hash1 = generate_url_hash(url1)
    hash2 = generate_url_hash(url2)
    assert hash1 == hash2


def test_generate_url_hash_ignores_fragment():
    """Test that URL fragment doesn't affect hash."""
    url1 = "https://example.com/blog/post"
    url2 = "https://example.com/blog/post#section"
    hash1 = generate_url_hash(url1)
    hash2 = generate_url_hash(url2)
    assert hash1 == hash2


def test_generate_url_hash_case_insensitive():
    """Test that URL is case-normalized."""
    url1 = "https://EXAMPLE.com/blog/post"
    url2 = "https://example.com/blog/post"
    hash1 = generate_url_hash(url1)
    hash2 = generate_url_hash(url2)
    assert hash1 == hash2


def test_generate_url_hash_different_paths():
    """Test that different paths produce different hashes."""
    url1 = "https://example.com/blog/post1"
    url2 = "https://example.com/blog/post2"
    hash1 = generate_url_hash(url1)
    hash2 = generate_url_hash(url2)
    assert hash1 != hash2


def test_generate_url_hash_invalid_url():
    """Test that invalid URL raises ValueError."""
    with pytest.raises(ValueError, match="URL must have scheme and domain"):
        generate_url_hash("not_a_url")


def test_generate_url_hash_empty_url():
    """Test that empty URL raises ValueError."""
    with pytest.raises(ValueError, match="Invalid URL"):
        generate_url_hash("")


################################################################################
# Test: generate_content_id
################################################################################

def test_generate_content_id_youtube():
    """Test content ID generation for YouTube."""
    url = "https://youtube.com/watch?v=abc123xyz12"
    content_id = generate_content_id("youtube", url)
    assert content_id == "youtube_abc123xyz12"
    assert content_id.startswith("youtube_")


def test_generate_content_id_reddit():
    """Test content ID generation for Reddit."""
    url = "https://reddit.com/r/travel/comments/abc123/post"
    content_id = generate_content_id("reddit", url)
    assert content_id == "reddit_t3_abc123"
    assert content_id.startswith("reddit_")


def test_generate_content_id_blog():
    """Test content ID generation for blog."""
    url = "https://travelblog.com/best-beaches"
    content_id = generate_content_id("blog", url)
    assert content_id.startswith("blog_")
    assert len(content_id.split("_")[1]) == 8


def test_generate_content_id_website():
    """Test content ID generation for website."""
    url = "https://example.com/page"
    content_id = generate_content_id("website", url)
    assert content_id.startswith("web_")
    assert len(content_id.split("_")[1]) == 8


def test_generate_content_id_with_source_id():
    """Test content ID generation with pre-provided source_id."""
    content_id = generate_content_id("youtube", "dummy_url", source_id="provided123")
    assert content_id == "youtube_provided123"


def test_generate_content_id_case_insensitive_source():
    """Test that source is case-insensitive."""
    url = "https://youtube.com/watch?v=abc123xyz12"
    content_id1 = generate_content_id("YouTube", url)
    content_id2 = generate_content_id("youtube", url)
    assert content_id1 == content_id2


def test_generate_content_id_invalid_source():
    """Test that invalid source raises ValueError."""
    with pytest.raises(ValueError, match="Invalid source"):
        generate_content_id("invalid_source", "https://example.com")


def test_generate_content_id_youtube_deterministic():
    """Test that YouTube content ID is deterministic."""
    url = "https://youtube.com/watch?v=test12345"
    id1 = generate_content_id("youtube", url)
    id2 = generate_content_id("youtube", url)
    assert id1 == id2


def test_generate_content_id_blog_deterministic():
    """Test that blog content ID is deterministic."""
    url = "https://blog.example.com/post"
    id1 = generate_content_id("blog", url)
    id2 = generate_content_id("blog", url)
    assert id1 == id2


################################################################################
# Test: parse_content_id
################################################################################

def test_parse_content_id_youtube():
    """Test parsing YouTube content ID."""
    content_id = "youtube_abc123"
    parsed = parse_content_id(content_id)
    assert parsed == {"source": "youtube", "id": "abc123"}


def test_parse_content_id_reddit():
    """Test parsing Reddit content ID."""
    content_id = "reddit_t3_xyz789"
    parsed = parse_content_id(content_id)
    assert parsed == {"source": "reddit", "id": "t3_xyz789"}


def test_parse_content_id_blog():
    """Test parsing blog content ID."""
    content_id = "blog_a1b2c3d4"
    parsed = parse_content_id(content_id)
    assert parsed == {"source": "blog", "id": "a1b2c3d4"}


def test_parse_content_id_website():
    """Test parsing website content ID."""
    content_id = "web_e5f6g7h8"
    parsed = parse_content_id(content_id)
    assert parsed == {"source": "web", "id": "e5f6g7h8"}


def test_parse_content_id_invalid_format():
    """Test that invalid format raises ValueError."""
    with pytest.raises(ValueError, match="Invalid source in content ID"):
        parse_content_id("invalid_format_here_extra")


def test_parse_content_id_no_underscore():
    """Test that content ID without underscore raises ValueError."""
    with pytest.raises(ValueError, match="Invalid content ID format"):
        parse_content_id("invalidnoundersc")


def test_parse_content_id_empty():
    """Test that empty content ID raises ValueError."""
    with pytest.raises(ValueError, match="Invalid content ID"):
        parse_content_id("")


def test_parse_content_id_empty_identifier():
    """Test that empty identifier raises ValueError."""
    with pytest.raises(ValueError, match="Empty identifier"):
        parse_content_id("youtube_")


def test_parse_content_id_invalid_source():
    """Test that invalid source raises ValueError."""
    with pytest.raises(ValueError, match="Invalid source in content ID"):
        parse_content_id("invalid_abc123")


################################################################################
# Test: is_valid_content_id
################################################################################

def test_is_valid_content_id_youtube():
    """Test validation of valid YouTube content ID."""
    assert is_valid_content_id("youtube_abc123") is True


def test_is_valid_content_id_reddit():
    """Test validation of valid Reddit content ID."""
    assert is_valid_content_id("reddit_t3_xyz789") is True


def test_is_valid_content_id_blog():
    """Test validation of valid blog content ID."""
    assert is_valid_content_id("blog_a1b2c3d4") is True


def test_is_valid_content_id_website():
    """Test validation of valid website content ID."""
    assert is_valid_content_id("web_e5f6g7h8") is True


def test_is_valid_content_id_invalid():
    """Test validation of invalid content ID."""
    assert is_valid_content_id("invalid") is False


def test_is_valid_content_id_empty_identifier():
    """Test validation of content ID with empty identifier."""
    assert is_valid_content_id("youtube_") is False


def test_is_valid_content_id_invalid_source():
    """Test validation of content ID with invalid source."""
    assert is_valid_content_id("invalid_source_abc123") is False


def test_is_valid_content_id_empty():
    """Test validation of empty content ID."""
    assert is_valid_content_id("") is False


################################################################################
# Integration Tests
################################################################################

def test_round_trip_youtube():
    """Test generating and parsing YouTube content ID."""
    url = "https://youtube.com/watch?v=test12345"
    content_id = generate_content_id("youtube", url)
    parsed = parse_content_id(content_id)

    assert parsed["source"] == "youtube"
    assert parsed["id"] == "test12345"
    assert is_valid_content_id(content_id)


def test_round_trip_reddit():
    """Test generating and parsing Reddit content ID."""
    url = "https://reddit.com/r/travel/comments/test123/post"
    content_id = generate_content_id("reddit", url)
    parsed = parse_content_id(content_id)

    assert parsed["source"] == "reddit"
    assert parsed["id"] == "t3_test123"
    assert is_valid_content_id(content_id)


def test_round_trip_blog():
    """Test generating and parsing blog content ID."""
    url = "https://blog.example.com/post"
    content_id = generate_content_id("blog", url)
    parsed = parse_content_id(content_id)

    assert parsed["source"] == "blog"
    assert len(parsed["id"]) == 8
    assert is_valid_content_id(content_id)


def test_multiple_youtube_videos_unique_ids():
    """Test that different YouTube videos get different IDs."""
    url1 = "https://youtube.com/watch?v=video1"
    url2 = "https://youtube.com/watch?v=video2"

    id1 = generate_content_id("youtube", url1)
    id2 = generate_content_id("youtube", url2)

    assert id1 != id2
    assert id1 == "youtube_video1"
    assert id2 == "youtube_video2"


def test_same_blog_url_same_id():
    """Test that same blog URL always gets same ID."""
    url1 = "https://blog.example.com/post?utm=source"
    url2 = "https://blog.example.com/post"

    id1 = generate_content_id("blog", url1)
    id2 = generate_content_id("blog", url2)

    assert id1 == id2  # Query params should be ignored
