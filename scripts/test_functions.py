#!/usr/bin/env python3
import sys
from pathlib import Path
import json

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.youtube import fetch_video_metadata

if __name__ == "__main__":
    # Example: Test with a video ID
    video_id = "5PtysfqW1GM"  # Thailand travel guide video

    print(f"Testing fetch_video_metadata with video_id: {video_id}")
    metadata = fetch_video_metadata(video_id)

    if metadata:
        # print("\n✅ Success!")
        print(f"Metadata: {json.dumps(metadata, indent=4)}")
        # print(f"Channel: {metadata.get('author')}")
        # print(f"Duration: {metadata.get('duration_seconds')}s")
        # print(f"Views: {metadata.get('view_count')}")
    else:
        print("❌ Failed to fetch metadata")