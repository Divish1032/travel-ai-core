#!/usr/bin/env python3
"""
Travel AI - Itinerary Generation CLI

User-facing command to generate personalized travel itineraries.
Simple, intuitive interface for testing and using the RAG system.

Usage:
    python cli/generate_itinerary.py -q "5 days Bangkok solo budget party"
    python cli/generate_itinerary.py -q "romantic Phuket 3 days" -o html -s trip.html
    python cli/generate_itinerary.py -q "Bangkok trip" -i  # Interactive mode

Author: TravelAI Team
Date: 2025-12-20
"""

import sys
import json
from pathlib import Path
from collections import Counter

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import click
from dotenv import load_dotenv

# Load environment
load_dotenv()

from src.rag.intent_parser import IntentParser
from src.rag.retriever import RAGRetriever
from src.rag.reranker import LLMReranker
from src.rag.context_builder import ContextBuilder
from src.rag.itinerary_generator import ItineraryGenerator
from src.rag.validator import ItineraryValidator
from src.rag.narrative_generator import NarrativeGenerator
from src.rag.formatter import ItineraryFormatter
from src.vectordb import ChromaDBClient
from src.utils.embedding_client import EmbeddingClient
from src.utils.schemas import UserIntent
from src.utils.logging import get_logger

logger = get_logger(__name__)


def clarify_intent_interactive(intent: UserIntent) -> UserIntent:
    """
    Ask follow-up questions to refine intent.

    Args:
        intent: Initial parsed intent

    Returns:
        Refined intent with user input
    """
    click.echo("\n📋 Let me clarify a few details...\n")

    # If no budget specified
    if not intent.budget_per_day:
        budget = click.prompt(
            "What's your daily budget in USD? (e.g., 50 for ~$50/day)",
            type=int,
            default=50
        )
        intent.budget_per_day = {"min": budget * 0.8, "max": budget * 1.2}

    # If vague interests
    if not intent.interests or len(intent.interests) < 2:
        interests = click.prompt(
            "What are you most interested in? (comma-separated)",
            default="food,nightlife,culture"
        )
        intent.interests = [i.strip() for i in interests.split(',')]

    # Pace preference
    if not hasattr(intent, 'pace') or not intent.pace:
        pace = click.prompt(
            "What pace do you prefer?",
            type=click.Choice(['relaxed', 'balanced', 'packed']),
            default='balanced'
        )
        from src.utils.schemas import Pace
        intent.pace = Pace(pace)

    # Confirm
    click.echo("\n" + "=" * 60)
    click.echo("📋 YOUR TRIP SUMMARY:")
    click.echo("=" * 60)
    click.echo(f"   Destination: {intent.destination}")
    click.echo(f"   Duration: {intent.duration_days} days")
    click.echo(f"   Traveler: {intent.traveler_profile.traveler_type} ({intent.traveler_profile.budget_tier})")
    if intent.budget_per_day:
        click.echo(f"   Budget: ${intent.budget_per_day['min']:.0f}-${intent.budget_per_day['max']:.0f}/day")
    click.echo(f"   Interests: {', '.join(intent.interests)}")
    click.echo(f"   Pace: {intent.pace.value}")
    click.echo("=" * 60)

    if not click.confirm("\nLooks good?", default=True):
        click.echo("Aborted.")
        raise click.Abort()

    return intent


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Travel AI - Generate personalized travel itineraries."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option('--query', '-q', required=True, help='Travel query (e.g., "5 days Bangkok solo budget")')
@click.option('--output', '-o', default='markdown', type=click.Choice(['json', 'markdown', 'html', 'text']),
              help='Output format')
@click.option('--save', '-s', help='Save output to file')
@click.option('--interactive', '-i', is_flag=True, help='Interactive mode with follow-up questions')
@click.option('--validate-only', is_flag=True, help='Only validate, don\'t generate narrative')
@click.option('--skip-narrative', is_flag=True, help='Skip narrative generation (faster)')
@click.option('--debug', is_flag=True, help='Show debug information')
def generate(query, output, save, interactive, validate_only, skip_narrative, debug):
    """Generate personalized travel itinerary from natural language query."""

    click.echo("\n" + "=" * 70)
    click.echo("🌍 TRAVEL AI - ITINERARY GENERATOR")
    click.echo("=" * 70)
    click.echo()

    total_cost = 0.0

    try:
        # Phase 1: Parse intent
        click.echo("Phase 1/7: Parsing your query... 🔍")
        parser = IntentParser()
        intent = parser.parse_query(query)
        total_cost += parser.total_cost

        if debug:
            click.echo(f"  ✓ Destination: {intent.destination}")
            click.echo(f"  ✓ Duration: {intent.duration_days} days")
            click.echo(f"  ✓ Profile: {intent.traveler_profile.traveler_type}, {intent.traveler_profile.budget_tier}")
            click.echo(f"  ✓ Confidence: {intent.confidence:.2f}")
            click.echo(f"  ✓ Cost: ${parser.total_cost:.6f}")

        # Interactive clarification
        if interactive:
            intent = clarify_intent_interactive(intent)

        click.echo("✅ Intent parsed\n")

        # Phase 2: Initialize clients
        click.echo("Phase 2/7: Connecting to database... 🔗")
        chromadb = ChromaDBClient.initialize_from_env()
        embedding_client = EmbeddingClient()

        click.echo("✅ Connected\n")

        # Phase 3: Retrieve
        click.echo("Phase 3/7: Finding relevant places... 🔎")
        retriever = RAGRetriever(chromadb, embedding_client)
        candidates = retriever.retrieve_for_itinerary(intent, top_k=20)

        if debug:
            click.echo(f"  ✓ Retrieved: {len(candidates)} entities")
            type_counts = Counter([c.entity_type for c in candidates])
            click.echo(f"  ✓ Types: {dict(type_counts)}")
            if candidates:
                click.echo(f"  ✓ Avg rating: {sum(c.profile_rating for c in candidates) / len(candidates):.2f}/5.0")

        if len(candidates) < 5:
            click.echo("\n⚠️  Warning: Limited data for this destination/profile")
            click.echo(f"   Found only {len(candidates)} relevant places")
            click.echo("   Continuing with available data...\n")

        click.echo("✅ Retrieval complete\n")

        # Phase 4: Re-rank
        click.echo("Phase 4/7: Personalizing recommendations... ⭐")
        reranker = LLMReranker()
        reranked = reranker.rerank_candidates(candidates, intent, top_k=min(12, len(candidates)))
        total_cost += reranker.total_cost

        if debug:
            click.echo(f"  ✓ Re-ranked to top {len(reranked)} entities")
            click.echo(f"  ✓ Cost: ${reranker.total_cost:.6f}")

        click.echo("✅ Personalization complete\n")

        # Phase 5: Build context
        click.echo("Phase 5/7: Building context... 📚")
        builder = ContextBuilder()
        context = builder.build_rag_context(reranked, intent)

        if debug:
            estimated_tokens = context.estimate_tokens() if hasattr(context, 'estimate_tokens') else 2000
            click.echo(f"  ✓ Context tokens: ~{estimated_tokens}")
            click.echo(f"  ✓ Priority entities: {len(context.priority_entities)}")
            click.echo(f"  ✓ Supporting entities: {len(context.supporting_entities)}")

        click.echo("✅ Context ready\n")

        # Phase 6: Generate itinerary
        click.echo("Phase 6/7: Creating your itinerary... ✨")
        generator = ItineraryGenerator()
        itinerary = generator.generate_itinerary(context, intent)
        total_cost += generator.total_cost

        if debug:
            click.echo(f"  ✓ Generated {len(itinerary.days)} days")
            click.echo(f"  ✓ Total entities: {len(itinerary.entity_ids)}")
            click.echo(f"  ✓ Confidence: {itinerary.overall_confidence:.2f}")
            click.echo(f"  ✓ Cost: ${generator.total_cost:.6f}")

        click.echo("✅ Itinerary generated\n")

        # Phase 7: Validate
        click.echo("Phase 7/7: Validating quality... ✔️")
        validator = ItineraryValidator()
        report = validator.validate_itinerary(itinerary, context, intent)

        if debug:
            click.echo(f"  ✓ Validation score: {report.overall_score:.2f}/1.0")
            click.echo(f"  ✓ Issues found: {len(report.issues)}")

        # Show validation results
        if not report.is_valid:
            click.echo(f"\n⚠️  Validation Warnings ({len(report.issues)} issues):")
            for issue in report.issues[:3]:  # Show top 3
                click.echo(f"   - {issue.description}")
            if len(report.issues) > 3:
                click.echo(f"   ... and {len(report.issues) - 3} more")
            click.echo()
        else:
            click.echo("✅ Validation passed\n")

        if validate_only:
            click.echo("\n" + "=" * 70)
            click.echo("📊 VALIDATION SUMMARY")
            click.echo("=" * 70)
            click.echo(f"Valid: {'✅ Yes' if report.is_valid else '❌ No'}")
            click.echo(f"Score: {report.overall_score:.2f}/1.0")
            click.echo(f"Issues: {len(report.issues)}")
            click.echo(f"Errors: {len([i for i in report.issues if i.severity.value == 'error'])}")
            click.echo(f"Warnings: {len([i for i in report.issues if i.severity.value == 'warning'])}")
            click.echo("=" * 70)
            return

        # Optional: Generate narrative
        narrative = None
        if not skip_narrative:
            click.echo("\nGenerating narrative... 📝")
            narrative_gen = NarrativeGenerator()
            narrative = narrative_gen.generate_narrative(itinerary, intent)
            total_cost += narrative_gen.total_cost

            if debug:
                click.echo(f"  ✓ Title: {narrative.title}")
                click.echo(f"  ✓ Word count: {narrative.word_count}")
                click.echo(f"  ✓ Tone: {narrative.tone}")
                click.echo(f"  ✓ Cost: ${narrative_gen.total_cost:.6f}")

            click.echo("✅ Narrative complete\n")

        # Format output
        click.echo("Formatting output...\n")
        formatter = ItineraryFormatter()

        if output == 'json':
            formatted = formatter.format_json(itinerary, narrative) if narrative else itinerary.model_dump(mode='json')
            output_text = json.dumps(formatted, indent=2, default=str)
        elif output == 'markdown':
            output_text = formatter.format_markdown(itinerary, narrative) if narrative else formatter.format_text_summary(itinerary)
        elif output == 'html':
            output_text = formatter.format_html(itinerary, narrative) if narrative else "<html><body><pre>" + formatter.format_text_summary(itinerary) + "</pre></body></html>"
        else:  # text
            output_text = formatter.format_text_summary(itinerary)

        # Save or print
        if save:
            save_path = Path(save)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w') as f:
                f.write(output_text)
            click.echo(f"✅ Saved to: {save_path}\n")
        else:
            click.echo("=" * 70)
            click.echo(output_text)
            click.echo("=" * 70 + "\n")

        # Summary
        click.echo("=" * 70)
        click.echo("📊 GENERATION SUMMARY")
        click.echo("=" * 70)
        click.echo(f"Destination: {itinerary.destination}")
        click.echo(f"Duration: {itinerary.duration_days} days")
        click.echo(f"Budget: {itinerary.total_budget_estimate}")
        click.echo(f"Confidence: {itinerary.overall_confidence:.2f}/1.0")
        click.echo(f"Sources: {itinerary.sources_used} traveler experiences")
        click.echo(f"Video sources: {len(itinerary.source_video_ids)}")
        click.echo(f"Total cost: ${total_cost:.6f}")

        if not report.is_valid:
            click.echo(f"⚠️  Validation: {len(report.issues)} warnings (score: {report.overall_score:.2f})")
        else:
            click.echo(f"✅ Validation: Passed (score: {report.overall_score:.2f})")

        click.echo("=" * 70)

    except Exception as e:
        click.echo(f"\n❌ Error: {str(e)}", err=True)
        if debug:
            import traceback
            traceback.print_exc()
        raise click.Abort()


@cli.command()
@click.argument('query')
@click.option('--debug', is_flag=True, help='Show detailed parsing info')
def parse(query, debug):
    """Test intent parsing without generating itinerary."""
    click.echo("🔍 Parsing query...\n")

    try:
        parser = IntentParser()
        intent = parser.parse_query(query)

        # Pretty print
        click.echo("=" * 70)
        click.echo("PARSED INTENT")
        click.echo("=" * 70)
        click.echo(f"Query: {intent.query_text}")
        click.echo(f"\nDestination: {intent.destination}")
        click.echo(f"Duration: {intent.duration_days} days")
        click.echo("\nTraveler Profile:")
        click.echo(f"  Type: {intent.traveler_profile.traveler_type}")
        click.echo(f"  Budget: {intent.traveler_profile.budget_tier}")
        click.echo(f"  Travel style: {', '.join(intent.traveler_profile.travel_style) if intent.traveler_profile.travel_style else 'N/A'}")
        click.echo(f"\nInterests: {', '.join(intent.interests) if intent.interests else 'N/A'}")
        click.echo(f"Pace: {intent.pace.value if intent.pace else 'N/A'}")
        click.echo(f"Flexibility: {intent.flexibility.value if intent.flexibility else 'N/A'}")

        if intent.budget_per_day:
            click.echo(f"\nBudget: ${intent.budget_per_day['min']:.0f}-${intent.budget_per_day['max']:.0f}/day")

        if intent.must_include:
            click.echo(f"\nMust include: {', '.join(intent.must_include)}")

        if intent.must_avoid:
            click.echo(f"Must avoid: {', '.join(intent.must_avoid)}")

        click.echo(f"\nConfidence: {intent.confidence:.2f}")
        click.echo(f"Parsing cost: ${parser.total_cost:.6f}")
        click.echo("=" * 70)

        if debug:
            click.echo("\nFull JSON:")
            click.echo(json.dumps(intent.model_dump(mode='json'), indent=2, default=str))

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        if debug:
            import traceback
            traceback.print_exc()
        raise click.Abort()


@cli.command()
@click.argument('itinerary_file')
def validate_file(itinerary_file):
    """Validate an existing itinerary JSON file."""
    click.echo(f"📋 Validating: {itinerary_file}\n")

    try:
        # Load file
        with open(itinerary_file) as f:
            data = json.load(f)

        # Reconstruct itinerary
        from src.utils.schemas import GeneratedItinerary
        itinerary = GeneratedItinerary(**data)

        # Validate structure
        click.echo("✅ JSON structure valid")
        click.echo(f"   Destination: {itinerary.destination}")
        click.echo(f"   Days: {len(itinerary.days)}")
        click.echo(f"   Entities: {len(itinerary.entity_ids)}")

        # Basic checks
        issues = []

        # Check days match duration
        if len(itinerary.days) != itinerary.duration_days:
            issues.append(f"Day count mismatch: {len(itinerary.days)} != {itinerary.duration_days}")

        # Check each day has activities
        for day in itinerary.days:
            slots = [day.morning, day.afternoon, day.evening, day.night]
            if not any(slots):
                issues.append(f"Day {day.day_number} has no activities")

        # Check confidence
        if itinerary.overall_confidence < 0.5:
            issues.append(f"Low confidence: {itinerary.overall_confidence:.2f}")

        if issues:
            click.echo(f"\n⚠️  Issues found ({len(issues)}):")
            for issue in issues:
                click.echo(f"   - {issue}")
        else:
            click.echo("\n✅ No structural issues found")

    except FileNotFoundError:
        click.echo(f"❌ File not found: {itinerary_file}", err=True)
        raise click.Abort()
    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"❌ Validation error: {str(e)}", err=True)
        raise click.Abort()


@cli.command()
def examples():
    """Show example queries."""
    examples = [
        ("Basic trip", "Plan 5 days in Bangkok for solo budget traveler who loves parties"),
        ("Romantic getaway", "Romantic weekend in Phuket for couple, beach resorts"),
        ("Family trip", "Family trip to Chiang Mai, kid-friendly, mid-range, 4 days"),
        ("Backpacking", "Backpacking Thailand 2 weeks, budget hostels and nightlife"),
        ("Food focused", "Best food places in Bangkok for 3 days, foodie solo traveler"),
        ("Luxury trip", "7-day luxury honeymoon in Koh Samui, resort and spa"),
        ("Adventure", "Adventure trip to Krabi, rock climbing and beaches, 5 days"),
        ("Cultural", "Cultural tour of Thailand, temples and history, 10 days"),
        ("Quick trip", "Weekend getaway to Ayutthaya from Bangkok"),
        ("Group travel", "Group trip to Pattaya, nightlife and beach, budget, 3 days")
    ]

    click.echo("\n" + "=" * 70)
    click.echo("📚 EXAMPLE QUERIES")
    click.echo("=" * 70)
    click.echo("\nTry these queries with the generate command:\n")

    for i, (category, example) in enumerate(examples, 1):
        click.echo(f"{i:2d}. [{category}]")
        click.echo(f"    {example}\n")

    click.echo("=" * 70)
    click.echo("\nUsage:")
    click.echo('  python cli/generate_itinerary.py generate -q "YOUR QUERY HERE"')
    click.echo('  python cli/generate_itinerary.py generate -q "5 days Bangkok" -i  # Interactive')
    click.echo('  python cli/generate_itinerary.py generate -q "Phuket 3 days" -o html -s trip.html')
    click.echo("=" * 70 + "\n")


if __name__ == '__main__':
    cli()
