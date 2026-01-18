#!/usr/bin/env python3
"""
Quick Test - Stage 5 RAG Pipeline

Fast sanity check to verify Stage 5 is working.
Generates a simple itinerary and prints results.

Usage:
    ./crawl.sh quick-test
    # Or directly
    python cli/quick_test.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment
load_dotenv()

from src.rag.pipeline import RAGPipeline


def main():
    print("=" * 70)
    print("QUICK TEST - STAGE 5 RAG PIPELINE")
    print("=" * 70)

    # Test query
    test_query = "Plan 3 days in Bangkok for solo budget traveler who loves parties"

    print(f"\nTest Query: {test_query}\n")
    print("Initializing pipeline...")

    try:
        # Initialize pipeline
        pipeline = RAGPipeline()

        print("Generating itinerary (this may take 30-60 seconds)...\n")

        # Generate with text output (fastest)
        result = pipeline.generate(
            query=test_query,
            output_format='text',
            skip_narrative=True  # Skip narrative for faster test
        )

        # Print result
        print("\n" + "=" * 70)
        print("GENERATED ITINERARY")
        print("=" * 70)
        print(result['formatted_output'])

        # Print metadata
        print("\n" + "=" * 70)
        print("METADATA")
        print("=" * 70)
        metadata = result['metadata']
        print(f"Destination:        {result['itinerary'].destination}")
        print(f"Duration:           {result['itinerary'].duration_days} days")
        print(f"Processing time:    {metadata['processing_time']:.1f}s")
        print(f"Total cost:         ${metadata['total_cost']:.4f}")
        print(f"Validation score:   {metadata['validation_score']:.2f}/1.0")
        print(f"Validation passed:  {'✅ Yes' if metadata['validation_passed'] else '⚠️  No'}")
        print(f"Entities retrieved: {metadata['entities_retrieved']}")
        print(f"Phases completed:   {metadata['phases_completed']}/7")

        print("\n" + "=" * 70)
        print("✅ QUICK TEST PASSED")
        print("=" * 70)
        print("\nStage 5 RAG pipeline is working correctly!")
        print("Try a full generation with:")
        print('  ./crawl.sh generate-itinerary -q "5 days Bangkok solo budget party"')

        return 0

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ QUICK TEST FAILED")
        print("=" * 70)
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("1. Check ChromaDB is accessible: python cli/check_stage5_ready.py")
        print("2. Verify LLM API keys in .env file")
        print("3. Ensure Stage 4 vector database is populated")

        import traceback
        traceback.print_exc()

        return 1


if __name__ == "__main__":
    sys.exit(main())
