#!/usr/bin/env python3
"""
Stage 2 Integration Tests

Tests the complete Stage 2 pipeline end-to-end:
1. Load video data from S3
2. Video classification (short/long)
3. Translation (if non-English)
4. LLM extraction with GPT-4o-mini
5. Pydantic validation
6. S3 upload
7. Metadata tracker updates

Usage:
    python tests/test_stage2.py [--limit N]

Examples:
    # Test with 2 videos
    python tests/test_stage2.py --limit 2

    # Test with 1 video
    python tests/test_stage2.py --limit 1
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import click

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.s3 import S3Storage
from src.utils.metadata_tracker import MetadataTracker
from src.processors.stage2_extractor import (
    process_short_video,
    classify_video_length,
    calculate_word_count,
    estimate_tokens_from_transcript,
    should_chunk_transcript
)
from src.utils.config import config
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Test Utilities
# =============================================================================

def print_section(title: str):
    """Print a section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")


def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"{'─'*70}\n")


def load_video_from_s3(s3_storage: S3Storage, s3_path: str) -> Optional[Dict[str, Any]]:
    """
    Load video data from S3 JSONL file.

    Args:
        s3_storage: S3Storage instance
        s3_path: S3 path (e.g., "s3://bucket/path/to/file.jsonl")

    Returns:
        Video data dict, or None if loading failed
    """
    try:
        # Parse S3 path
        if not s3_path.startswith("s3://"):
            logger.error(f"Invalid S3 path format: {s3_path}")
            return None

        # Remove s3:// prefix and bucket name
        path_parts = s3_path.replace("s3://", "").split("/", 1)
        if len(path_parts) != 2:
            logger.error(f"Invalid S3 path format: {s3_path}")
            return None

        bucket_name = path_parts[0]
        s3_key = path_parts[1]

        # Download from S3
        logger.info(f"Downloading from S3: {s3_key}")
        response = s3_storage.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')

        # Parse JSONL (may contain multiple videos, we want the first line)
        lines = content.strip().split('\n')
        if not lines:
            logger.error(f"Empty file: {s3_path}")
            return None

        # Parse first line as JSON
        video_data = json.loads(lines[0])

        logger.info(f"Loaded video: {video_data.get('source_id', 'unknown')}")
        return video_data

    except Exception as e:
        logger.error(f"Failed to load video from {s3_path}: {e}")
        return None


# =============================================================================
# Test Functions
# =============================================================================

def test_video_classification(video_data: Dict[str, Any]) -> Dict[str, Any]:
    """Test video classification functions."""
    print_subsection("Test 1: Video Classification")

    duration = video_data.get('duration_seconds', 0)
    transcript = video_data.get('transcript', [])
    language = video_data.get('language', 'en')

    # Classify video length
    video_class = classify_video_length(duration)
    print(f"✓ Video duration: {duration:.1f}s ({duration/60:.1f} min)")
    print(f"✓ Video classification: {video_class}")

    # Calculate word count
    word_count = calculate_word_count(transcript)
    print(f"✓ Word count: {word_count:,} words")

    # Estimate tokens
    estimated_tokens = estimate_tokens_from_transcript(transcript, language)
    print(f"✓ Estimated tokens: {estimated_tokens:,} tokens")

    # Check if chunking needed
    needs_chunking = should_chunk_transcript(transcript, language, max_tokens=6000)
    print(f"✓ Needs chunking: {needs_chunking}")

    return {
        'duration_seconds': duration,
        'duration_minutes': duration / 60,
        'video_class': video_class,
        'word_count': word_count,
        'estimated_tokens': estimated_tokens,
        'needs_chunking': needs_chunking
    }


def test_extraction(video_data: Dict[str, Any], s3_path: str) -> Optional[Dict[str, Any]]:
    """Test LLM extraction pipeline."""
    print_subsection("Test 2: LLM Extraction Pipeline")

    source_id = video_data.get('source_id', 'unknown')
    language = video_data.get('language', 'en')

    print(f"Processing video: {source_id}")
    print(f"Language: {language}")

    # Run extraction
    try:
        stage2_output = process_short_video(
            video_data=video_data,
            raw_file_path=s3_path,
            translate_non_english=True
        )

        if not stage2_output:
            print("❌ Extraction failed (returned None)")
            return None

        print("\n✅ Extraction successful!")
        print(f"   - Entities extracted: {len(stage2_output.entities)}")
        print(f"   - Extraction quality: {stage2_output.extraction_quality}")
        print(f"   - Tokens used: {stage2_output.tokens_used:,}")
        print(f"   - Cost: ${stage2_output.cost_usd:.4f}")
        print(f"   - LLM model: {stage2_output.llm_model}")

        # Print traveler profile
        print("\n📋 Traveler Profile:")
        profile = stage2_output.traveler_profile
        print(f"   - Type: {profile.traveler_type}")
        print(f"   - Age range: {profile.age_range}")
        print(f"   - Budget tier: {profile.budget_tier}")
        print(f"   - Travel style: {', '.join(profile.travel_style) if profile.travel_style else 'None'}")
        print(f"   - Confidence: {profile.confidence_score:.2f}")

        # Print sample entities
        print(f"\n🗺️  Entities Extracted ({len(stage2_output.entities)} total):")
        for i, entity in enumerate(stage2_output.entities[:5], 1):  # Show first 5
            print(f"\n   {i}. {entity.entity_name}")
            print(f"      Type: {entity.entity_type}")
            print(f"      Location: {entity.location or 'N/A'}")
            print(f"      Sentiment: {entity.sentiment}")
            print(f"      Confidence: {entity.confidence_score:.2f}")
            if entity.cost_mentioned:
                print(f"      Cost: {entity.cost_mentioned}")
            # Truncate long experiences
            experience = entity.experience[:100] + "..." if len(entity.experience) > 100 else entity.experience
            print(f"      Experience: {experience}")

        if len(stage2_output.entities) > 5:
            print(f"\n   ... and {len(stage2_output.entities) - 5} more entities")

        return {
            'success': True,
            'output': stage2_output,
            'entities_count': len(stage2_output.entities),
            'extraction_quality': stage2_output.extraction_quality,
            'tokens_used': stage2_output.tokens_used,
            'cost_usd': stage2_output.cost_usd
        }

    except Exception as e:
        print(f"❌ Extraction failed with error: {e}")
        logger.error(f"Extraction error: {e}", exc_info=True)
        return None


def test_s3_upload(s3_storage: S3Storage, stage2_output: Any) -> Optional[str]:
    """Test S3 upload."""
    print_subsection("Test 3: S3 Upload")

    try:
        processing_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        s3_path = s3_storage.save_stage2_output(
            output=stage2_output,
            processing_date=processing_date
        )

        print(f"✅ Uploaded to S3:")
        print(f"   {s3_path}")

        return s3_path

    except Exception as e:
        print(f"❌ S3 upload failed: {e}")
        logger.error(f"S3 upload error: {e}", exc_info=True)
        return None


def test_metadata_tracker(
    tracker: MetadataTracker,
    content_id: str,
    stage2_output: Any,
    s3_path: str
) -> bool:
    """Test metadata tracker updates."""
    print_subsection("Test 4: Metadata Tracker Update")

    try:
        # Start stage
        tracker.start_stage(stage_name="stage_2_extract", content_id=content_id)
        print(f"✓ Started stage_2_extract for {content_id}")

        # Complete stage
        tracker.complete_stage(
            stage_name="stage_2_extract",
            content_id=content_id,
            s3_paths=[s3_path],
            metadata={
                'entities_extracted': len(stage2_output.entities),
                'extraction_quality': stage2_output.extraction_quality,
                'tokens_used': stage2_output.tokens_used,
                'cost_usd': stage2_output.cost_usd,
                'llm_model': stage2_output.llm_model
            }
        )
        print(f"✓ Completed stage_2_extract for {content_id}")

        # Save to S3
        tracker.save_to_s3()
        print(f"✓ Saved metadata to S3")

        # Verify status
        item = tracker.get_item(content_id)
        if item:
            stages = item.get('stages', {})
            stage2 = stages.get('stage_2_extract', {})
            status = stage2.get('status', 'unknown')
            print(f"\n✅ Metadata tracker updated successfully!")
            print(f"   - Content ID: {content_id}")
            print(f"   - Stage 2 status: {status}")
            print(f"   - Pipeline status: {item.get('pipeline_status', 'unknown')}")

            return True
        else:
            print(f"❌ Failed to verify metadata for {content_id}")
            return False

    except Exception as e:
        print(f"❌ Metadata tracker update failed: {e}")
        logger.error(f"Metadata tracker error: {e}", exc_info=True)
        return False


# =============================================================================
# Main Test Runner
# =============================================================================

def run_tests(limit: int = 2):
    """
    Run Stage 2 integration tests.

    Args:
        limit: Number of videos to test (default: 2)
    """
    print_section("Stage 2 Integration Tests")

    # Validate OpenAI API key
    if not config.OPENAI_API_KEY:
        print("❌ Error: OPENAI_API_KEY not set in environment")
        print("   Please add it to .env file")
        print("   Get your API key from: https://platform.openai.com/api-keys")
        return False

    print(f"✓ OpenAI API key configured")

    # Initialize S3 and metadata tracker
    print(f"✓ Initializing S3 storage...")
    s3_storage = S3Storage(bucket_name=config.S3_BUCKET_NAME)

    print(f"✓ Loading metadata tracker...")
    tracker = MetadataTracker(s3_storage=s3_storage)
    tracker.load_from_s3()

    # Find videos ready for Stage 2
    print(f"✓ Finding videos ready for Stage 2...")
    all_items = tracker.get_all_items()
    ready_videos = []

    for content_id, metadata in all_items.items():
        stages = metadata.get('stages', {})
        stage1 = stages.get('stage_1_crawl', {})
        stage1_status = stage1.get('status', 'not_started')

        if stage1_status == 'complete':
            ready_videos.append((content_id, metadata))

    if not ready_videos:
        print("\n❌ No videos found ready for Stage 2")
        return False

    print(f"✓ Found {len(ready_videos)} videos ready for Stage 2")

    # Limit to specified number
    test_videos = ready_videos[:limit]
    print(f"✓ Testing with {len(test_videos)} video(s)\n")

    # Test each video
    total_cost = 0.0
    total_tokens = 0
    total_entities = 0
    successful_tests = 0

    for i, (content_id, metadata) in enumerate(test_videos, 1):
        print_section(f"Testing Video {i}/{len(test_videos)}: {content_id}")

        # Get Stage 1 S3 path
        stages = metadata.get('stages', {})
        stage1 = stages.get('stage_1_crawl', {})
        s3_paths = stage1.get('s3_paths', [])

        if not s3_paths:
            print(f"❌ No Stage 1 S3 path found for {content_id}")
            continue

        s3_path = s3_paths[0]
        print(f"S3 Path: {s3_path}")

        # Load video data
        video_data = load_video_from_s3(s3_storage, s3_path)
        if not video_data:
            print(f"❌ Failed to load video data")
            continue

        # Test 1: Video classification
        try:
            classification_results = test_video_classification(video_data)

            # Skip long videos
            if classification_results['video_class'] == 'long':
                print(f"\n⏭️  Skipping long video (hierarchical extraction not implemented)")
                continue

        except Exception as e:
            print(f"❌ Classification test failed: {e}")
            logger.error(f"Classification error: {e}", exc_info=True)
            continue

        # Test 2: LLM extraction
        try:
            extraction_results = test_extraction(video_data, s3_path)

            if not extraction_results or not extraction_results.get('success'):
                print(f"❌ Extraction test failed")
                continue

            stage2_output = extraction_results['output']
            total_cost += extraction_results['cost_usd']
            total_tokens += extraction_results['tokens_used']
            total_entities += extraction_results['entities_count']

        except Exception as e:
            print(f"❌ Extraction test failed: {e}")
            logger.error(f"Extraction error: {e}", exc_info=True)
            continue

        # Test 3: S3 upload
        try:
            upload_s3_path = test_s3_upload(s3_storage, stage2_output)

            if not upload_s3_path:
                print(f"❌ S3 upload test failed")
                continue

        except Exception as e:
            print(f"❌ S3 upload test failed: {e}")
            logger.error(f"S3 upload error: {e}", exc_info=True)
            continue

        # Test 4: Metadata tracker
        try:
            tracker_success = test_metadata_tracker(
                tracker, content_id, stage2_output, upload_s3_path
            )

            if not tracker_success:
                print(f"❌ Metadata tracker test failed")
                continue

        except Exception as e:
            print(f"❌ Metadata tracker test failed: {e}")
            logger.error(f"Metadata tracker error: {e}", exc_info=True)
            continue

        # All tests passed for this video
        successful_tests += 1
        print(f"\n✅ All tests passed for {content_id}!")

    # Print final summary
    print_section("Test Summary")

    print(f"Videos tested:          {len(test_videos)}")
    print(f"Successful:             {successful_tests}")
    print(f"Failed:                 {len(test_videos) - successful_tests}")
    print(f"\nTotal entities:         {total_entities}")
    print(f"Total tokens:           {total_tokens:,}")
    print(f"Total cost:             ${total_cost:.4f}")

    if successful_tests > 0:
        print(f"\nAverage per video:")
        print(f"  - Entities:           {total_entities / successful_tests:.1f}")
        print(f"  - Tokens:             {total_tokens / successful_tests:,.0f}")
        print(f"  - Cost:               ${total_cost / successful_tests:.4f}")

    print("\n" + "="*70 + "\n")

    if successful_tests == len(test_videos):
        print("🎉 All tests passed!\n")
        return True
    else:
        print(f"⚠️  {len(test_videos) - successful_tests} test(s) failed. Check logs for details.\n")
        return False


# =============================================================================
# CLI Interface
# =============================================================================

@click.command()
@click.option(
    '--limit',
    type=int,
    default=2,
    help='Number of videos to test (default: 2)'
)
def main(limit: int):
    """
    Run Stage 2 integration tests.

    Tests the complete Stage 2 pipeline with real videos from S3.

    Examples:
        # Test with 2 videos
        python tests/test_stage2.py --limit 2

        # Test with 1 video
        python tests/test_stage2.py --limit 1
    """
    try:
        success = run_tests(limit=limit)
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user.\n")
        sys.exit(130)

    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
