#!/usr/bin/env python3
"""
Stage 5 Readiness Check

Verifies all dependencies and prerequisites for Stage 5 RAG pipeline.
Checks:
- ChromaDB accessibility
- Vector collections populated
- LLM API keys configured
- Embedding model available

Usage:
    python check_stage5_ready.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment
load_dotenv()


def check_ready():
    """Run all readiness checks."""
    checks = []
    warnings = []

    print("=" * 70)
    print("STAGE 5 READINESS CHECK")
    print("=" * 70)
    print()

    # Check 1: ChromaDB Connection
    print("1. Checking ChromaDB connection...")
    try:
        from src.vectordb import ChromaDBClient

        client = ChromaDBClient.initialize_from_env()
        checks.append(("✅", "ChromaDB accessible"))

        # Check collections
        if hasattr(client, 'entities_collection'):
            entity_count = client.entities_collection.count()
            checks.append(("✅", f"Entities collection: {entity_count:,} vectors"))

            if entity_count < 100:
                warnings.append(
                    f"⚠️  Low entity count ({entity_count}). "
                    "Consider running more Stage 2-4 processing."
                )
        else:
            checks.append(("⚠️ ", "Entities collection not found"))

        if hasattr(client, 'profile_consensus_collection'):
            profile_count = client.profile_consensus_collection.count()
            checks.append(("✅", f"Profile consensus: {profile_count} vectors"))

            if profile_count < 50:
                warnings.append(
                    f"⚠️  Low profile count ({profile_count}). "
                    "Quality may be limited for some destinations."
                )
        else:
            checks.append(("⚠️ ", "Profile consensus collection not found"))

        if hasattr(client, 'experiences_collection'):
            exp_count = client.experiences_collection.count()
            checks.append(("✅", f"Experiences collection: {exp_count} vectors"))
        else:
            checks.append(("⚠️ ", "Experiences collection not found"))

    except Exception as e:
        checks.append(("❌", f"ChromaDB error: {str(e)[:50]}..."))
        print(f"   Error details: {e}")

    print()

    # Check 2: LLM API Keys
    print("2. Checking LLM API keys...")
    llm_keys_found = []

    if os.getenv('DEEPSEEK_API_KEY'):
        checks.append(("✅", "DeepSeek API key configured"))
        llm_keys_found.append('deepseek')

    if os.getenv('OPENAI_API_KEY'):
        checks.append(("✅", "OpenAI API key configured"))
        llm_keys_found.append('openai')

    if os.getenv('GEMINI_API_KEY'):
        checks.append(("✅", "Gemini API key configured"))
        llm_keys_found.append('gemini')

    if not llm_keys_found:
        checks.append(("❌", "No LLM API key found"))
        checks.append(("", "Add DEEPSEEK_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY to .env"))
    else:
        checks.append(("✅", f"Available providers: {', '.join(llm_keys_found)}"))

    print()

    # Check 3: Embedding Model
    print("3. Checking embedding model...")
    try:
        from src.utils.embedding_client import EmbeddingClient

        client = EmbeddingClient()
        checks.append(("✅", f"Embedding model: {client.MODEL}"))

        # Test embedding
        test_embedding = client.embed_text("test")
        checks.append(("✅", f"Embedding dimension: {len(test_embedding)}"))

    except Exception as e:
        checks.append(("❌", f"Embedding client error: {str(e)[:50]}..."))
        print(f"   Error details: {e}")

    print()

    # Check 4: Required Python packages
    print("4. Checking Python packages...")
    required_packages = [
        ('click', 'Click'),
        ('chromadb', 'ChromaDB'),
        ('sentence_transformers', 'Sentence Transformers'),
        ('pydantic', 'Pydantic')
    ]

    for module_name, display_name in required_packages:
        try:
            __import__(module_name)
            checks.append(("✅", f"{display_name} installed"))
        except ImportError:
            checks.append(("❌", f"{display_name} not installed"))
            checks.append(("", f"Install with: pip install {module_name}"))

    print()

    # Check 5: RAG Components
    print("5. Checking RAG components...")
    components = [
        ('src.rag.intent_parser', 'IntentParser'),
        ('src.rag.retriever', 'RAGRetriever'),
        ('src.rag.reranker', 'LLMReranker'),
        ('src.rag.context_builder', 'ContextBuilder'),
        ('src.rag.itinerary_generator', 'ItineraryGenerator'),
        ('src.rag.validator', 'ItineraryValidator'),
        ('src.rag.narrative_generator', 'NarrativeGenerator'),
        ('src.rag.formatter', 'ItineraryFormatter'),
        ('src.rag.pipeline', 'RAGPipeline')
    ]

    for module_name, class_name in components:
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            checks.append(("✅", f"{class_name} available"))
        except Exception as e:
            checks.append(("❌", f"{class_name} error: {str(e)[:40]}..."))

    # Print results
    print()
    print("=" * 70)
    print("CHECK RESULTS")
    print("=" * 70)

    for status, message in checks:
        if status:
            print(f"{status} {message}")
        else:
            print(f"   {message}")

    # Print warnings
    if warnings:
        print()
        print("=" * 70)
        print("WARNINGS")
        print("=" * 70)
        for warning in warnings:
            print(warning)

    # Summary
    print()
    print("=" * 70)

    failed_checks = sum(1 for status, _ in checks if status == "❌")
    warning_checks = sum(1 for status, _ in checks if status == "⚠️ ")

    if failed_checks == 0 and warning_checks == 0:
        print("✅ STAGE 5 IS READY!")
        print("=" * 70)
        print()
        print("You can now:")
        print("  • Run quick test: python quick_test.py")
        print("  • Generate itineraries: ./crawl.sh generate-itinerary -q 'YOUR QUERY'")
        print("  • Run full tests: ./crawl.sh test-stage5")
        print()
        return True

    elif failed_checks > 0:
        print("❌ STAGE 5 NOT READY")
        print("=" * 70)
        print(f"\nFound {failed_checks} error(s) and {warning_checks} warning(s).")
        print("Please fix the errors above before using Stage 5.")
        print()
        return False

    else:  # Only warnings
        print("⚠️  STAGE 5 READY WITH WARNINGS")
        print("=" * 70)
        print(f"\nFound {warning_checks} warning(s).")
        print("Stage 5 will work but quality may be limited.")
        print("Consider addressing warnings for better results.")
        print()
        return True


if __name__ == "__main__":
    ready = check_ready()
    sys.exit(0 if ready else 1)
