#!/usr/bin/env python3
"""
RAG Itinerary Formatter - Multi-Format Output Generation

Transforms structured itineraries and narratives into various output formats:
- JSON (for APIs and storage)
- Markdown (for readable documentation)
- HTML (for web display)
- Plain text (for quick summaries)
- GeoJSON (for map visualization)
- Shareable formats (social media, links)

Supports export to PDF and interactive maps.

Author: TravelAI Team
Date: 2025-12-20
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import hashlib
import re

from src.utils.logging import get_logger
from src.utils.schemas import (
    GeneratedItinerary,
    ItineraryDay,
    ItineraryNarrative,
    TimeSlot,
    TimePeriod
)

logger = get_logger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def get_all_slots(day: ItineraryDay) -> List[Optional[TimeSlot]]:
    """
    Get all time slots from a day in order.

    Args:
        day: Itinerary day

    Returns:
        List of time slots (some may be None)
    """
    return [
        day.morning,
        day.afternoon,
        day.evening,
        day.night
    ]


def get_slot_emoji(period: TimePeriod) -> str:
    """
    Get emoji for time period.

    Args:
        period: Time period enum

    Returns:
        Emoji string
    """
    emoji_map = {
        TimePeriod.MORNING: "☀️",
        TimePeriod.AFTERNOON: "🌤️",
        TimePeriod.EVENING: "🌆",
        TimePeriod.NIGHT: "🌙"
    }
    return emoji_map.get(period, "⏰")


def get_day_color(day_number: int) -> str:
    """
    Get color code for day (for maps/charts).

    Args:
        day_number: Day number (1-indexed)

    Returns:
        Hex color code
    """
    colors = [
        "#3498db",  # Blue
        "#e74c3c",  # Red
        "#2ecc71",  # Green
        "#f39c12",  # Orange
        "#9b59b6",  # Purple
        "#1abc9c",  # Turquoise
        "#e67e22",  # Carrot
        "#34495e",  # Dark gray
        "#16a085",  # Green sea
        "#c0392b"   # Pomegranate
    ]
    return colors[(day_number - 1) % len(colors)]


# =============================================================================
# ItineraryFormatter Class
# =============================================================================

class ItineraryFormatter:
    """
    Format itineraries for different output types.

    Supports JSON, Markdown, HTML, text, GeoJSON, and shareable formats.

    Example:
        >>> formatter = ItineraryFormatter()
        >>> json_output = formatter.format_json(itinerary, narrative)
        >>> markdown = formatter.format_markdown(itinerary, narrative)
        >>> html = formatter.format_html(itinerary, narrative)
    """

    def __init__(self):
        """Initialize formatter."""
        logger.info("ItineraryFormatter initialized")

    def format_json(
        self,
        itinerary: GeneratedItinerary,
        narrative: ItineraryNarrative
    ) -> Dict[str, Any]:
        """
        Format as complete JSON export.

        For APIs, storage, and data exchange.

        Args:
            itinerary: Generated itinerary
            narrative: Generated narrative

        Returns:
            Complete JSON dictionary
        """
        return {
            "version": "1.0",
            "generated_at": itinerary.generated_at.isoformat() if itinerary.generated_at else datetime.utcnow().isoformat(),
            "user_intent": itinerary.user_intent.dict() if itinerary.user_intent else {},

            "itinerary": {
                "destination": itinerary.destination,
                "duration_days": itinerary.duration_days,
                "total_budget": itinerary.total_budget_estimate,

                "days": [day.dict() for day in itinerary.days],

                "summary": {
                    "highlights": itinerary.highlights,
                    "general_tips": itinerary.general_tips,
                    "warnings": itinerary.important_warnings,
                    "overall_vibe": itinerary.overall_vibe
                }
            },

            "narrative": {
                "title": narrative.title,
                "introduction": narrative.introduction,
                "day_narratives": narrative.day_narratives,
                "conclusion": narrative.conclusion,
                "tone": narrative.tone,
                "word_count": narrative.word_count
            },

            "metadata": {
                "confidence": itinerary.overall_confidence,
                "sources_used": itinerary.sources_used,
                "cost_to_generate": getattr(itinerary, 'total_cost', 0.0),
                "model_version": getattr(itinerary, 'generation_version', '1.0')
            },

            "provenance": {
                "entity_ids": itinerary.entity_ids,
                "source_video_ids": itinerary.source_video_ids
            }
        }

    def format_markdown(
        self,
        itinerary: GeneratedItinerary,
        narrative: ItineraryNarrative
    ) -> str:
        """
        Format as beautiful markdown.

        For readable documentation and sharing.

        Args:
            itinerary: Generated itinerary
            narrative: Generated narrative

        Returns:
            Markdown string
        """
        lines = []

        # Title
        lines.append(f"# {narrative.title}\n")

        # Introduction
        lines.append(narrative.introduction)
        lines.append("\n---\n")

        # Quick Facts
        lines.append("## Quick Facts\n")
        lines.append(f"- **Destination:** {itinerary.destination}")
        lines.append(f"- **Duration:** {itinerary.duration_days} days")
        lines.append(f"- **Budget:** {itinerary.total_budget_estimate}")

        if itinerary.user_intent:
            profile = itinerary.user_intent.traveler_profile
            lines.append(f"- **Travel Style:** {profile.travel_style}")
            lines.append(f"- **Traveler Type:** {profile.traveler_type}")
            lines.append(f"- **Budget Tier:** {profile.budget_tier}")

        lines.append(f"- **Confidence Score:** {itinerary.overall_confidence}/10")
        lines.append(f"- **Vibe:** {itinerary.overall_vibe}")
        lines.append("\n---\n")

        # Day-by-Day Itinerary
        lines.append("## Day-by-Day Itinerary\n")

        for i, day in enumerate(itinerary.days, 1):
            # Day header
            lines.append(f"### Day {i}: {day.theme}\n")

            # Day narrative (extract from narrative.day_narratives)
            if i <= len(narrative.day_narratives):
                day_narrative = narrative.day_narratives[i - 1]
                # Handle both string and dict
                if isinstance(day_narrative, dict):
                    day_text = day_narrative.get('day_narrative', str(day_narrative))
                else:
                    day_text = str(day_narrative)
                lines.append(f"{day_text}\n")

            lines.append(f"**Budget:** {day.daily_budget_estimate}\n")

            # Time slots
            slots = [
                (TimePeriod.MORNING, day.morning),
                (TimePeriod.AFTERNOON, day.afternoon),
                (TimePeriod.EVENING, day.evening),
                (TimePeriod.NIGHT, day.night)
            ]

            for period, slot in slots:
                if slot:
                    emoji = get_slot_emoji(period)
                    lines.append(f"#### {emoji} {period.value.title()}: {slot.entity_name}\n")
                    lines.append(f"{slot.activity_description}\n")

                    # Tips
                    practical_tips = getattr(slot, 'practical_tips', None)
                    if practical_tips:
                        for tip in practical_tips:
                            lines.append(f"💡 **Tip:** {tip}\n")

                    # Warnings
                    warnings = getattr(slot, 'warnings', None)
                    if warnings:
                        for warning in warnings:
                            lines.append(f"⚠️ **Warning:** {warning}\n")

                    # Traveler quotes
                    traveler_quotes = getattr(slot, 'traveler_quotes', None)
                    if traveler_quotes:
                        for quote in traveler_quotes[:2]:  # Max 2 quotes
                            lines.append(f'💬 **Traveler says:** "{quote}"\n')

                    # Cost
                    if slot.estimated_cost:
                        lines.append(f"💰 **Cost:** {slot.estimated_cost}\n")

                    lines.append("")  # Blank line

            lines.append("---\n")

        # Important Information
        lines.append("## Important Information\n")

        # General Tips
        if itinerary.general_tips:
            lines.append("### General Tips\n")
            for tip in itinerary.general_tips:
                lines.append(f"- {tip}")
            lines.append("")

        # Warnings
        if itinerary.important_warnings:
            lines.append("### Warnings\n")
            for warning in itinerary.important_warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        # Highlights
        if itinerary.highlights:
            lines.append("### Highlights\n")
            for highlight in itinerary.highlights:
                lines.append(f"- ✨ {highlight}")
            lines.append("")

        lines.append("---\n")

        # Conclusion
        lines.append("## About This Itinerary\n")
        lines.append(narrative.conclusion)
        lines.append("")

        # Footer
        lines.append(f"*Generated using {itinerary.sources_used} traveler experiences. Confidence: {itinerary.overall_confidence}/10*")

        return "\n".join(lines)

    def format_html(
        self,
        itinerary: GeneratedItinerary,
        narrative: ItineraryNarrative = None
    ) -> str:
        """
        Format as styled HTML.

        For web display with responsive design.

        Args:
            itinerary: Generated itinerary
            narrative: Generated narrative (optional, can be None if skip_narrative=True)

        Returns:
            HTML string
        """
        # Handle when narrative is not provided
        title = narrative.title if narrative else f"{itinerary.destination} - {itinerary.duration_days} Day Itinerary"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            color: #333;
            background-color: #f8f9fa;
        }}

        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}

        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}

        h3 {{
            color: #2c3e50;
            margin-top: 25px;
        }}

        .introduction {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 20px 0;
        }}

        .quick-facts {{
            background: #ecf0f1;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}

        .quick-facts ul {{
            list-style: none;
            padding: 0;
        }}

        .quick-facts li {{
            padding: 5px 0;
        }}

        .day {{
            background: white;
            border-left: 4px solid #3498db;
            padding: 20px;
            margin: 30px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .day-narrative {{
            margin: 15px 0;
            font-style: italic;
            color: #555;
        }}

        .time-slot {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
        }}

        .time-slot h4 {{
            margin-top: 0;
            color: #2980b9;
        }}

        .tip {{
            background: #e8f5e9;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 3px solid #4caf50;
        }}

        .warning {{
            background: #fff3cd;
            padding: 10px;
            border-radius: 5px;
            margin: 10px 0;
            border-left: 3px solid #ffc107;
        }}

        .quote {{
            font-style: italic;
            border-left: 3px solid #95a5a6;
            padding-left: 15px;
            margin: 10px 0;
            color: #555;
        }}

        .cost {{
            color: #27ae60;
            font-weight: bold;
        }}

        .important-info {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .conclusion {{
            background: #e8f4f8;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3498db;
        }}

        .footer {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #bdc3c7;
        }}

        ul {{
            padding-left: 20px;
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}

            .day, .introduction, .important-info {{
                padding: 15px;
            }}
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>

    <div class="introduction">
        {self._markdown_to_html_paragraphs(narrative.introduction) if narrative else f"<p>Your personalized {itinerary.duration_days}-day itinerary for {itinerary.destination}.</p>"}
    </div>

    <div class="quick-facts">
        <h2>Quick Facts</h2>
        <ul>
            <li><strong>Destination:</strong> {itinerary.destination}</li>
            <li><strong>Duration:</strong> {itinerary.duration_days} days</li>
            <li><strong>Budget:</strong> {itinerary.total_budget_estimate}</li>"""

        if itinerary.user_intent:
            profile = itinerary.user_intent.traveler_profile
            html += f"""
            <li><strong>Travel Style:</strong> {profile.travel_style}</li>
            <li><strong>Traveler Type:</strong> {profile.traveler_type}</li>
            <li><strong>Budget Tier:</strong> {profile.budget_tier}</li>"""

        html += f"""
            <li><strong>Confidence Score:</strong> {itinerary.overall_confidence}/10</li>
            <li><strong>Vibe:</strong> {itinerary.overall_vibe}</li>
        </ul>
    </div>

    <h2>Day-by-Day Itinerary</h2>
"""

        # Days
        for i, day in enumerate(itinerary.days, 1):
            color = get_day_color(i)
            html += f"""
    <div class="day" style="border-left-color: {color};">
        <h3>Day {i}: {day.theme}</h3>

        <div class="day-narrative">
"""

            # Day narrative (only if narrative was generated)
            if narrative and i <= len(narrative.day_narratives):
                day_narrative = narrative.day_narratives[i - 1]
                if isinstance(day_narrative, dict):
                    day_text = day_narrative.get('day_narrative', str(day_narrative))
                else:
                    day_text = str(day_narrative)
                html += f"            {self._markdown_to_html_paragraphs(day_text)}\n"

            html += f"""        </div>

        <p><strong>Budget:</strong> <span class="cost">{day.daily_budget_estimate}</span></p>
"""

            # Time slots
            slots = [
                (TimePeriod.MORNING, day.morning),
                (TimePeriod.AFTERNOON, day.afternoon),
                (TimePeriod.EVENING, day.evening),
                (TimePeriod.NIGHT, day.night)
            ]

            for period, slot in slots:
                if slot:
                    emoji = get_slot_emoji(period)
                    html += f"""
        <div class="time-slot">
            <h4>{emoji} {period.value.title()}: {slot.entity_name}</h4>
            <p>{slot.activity_description}</p>
"""

                    # Tips
                    practical_tips = getattr(slot, 'practical_tips', None)
                    if practical_tips:
                        for tip in practical_tips:
                            html += f"""
            <div class="tip">💡 <strong>Tip:</strong> {tip}</div>"""

                    # Warnings
                    warnings = getattr(slot, 'warnings', None)
                    if warnings:
                        for warning in warnings:
                            html += f"""
            <div class="warning">⚠️ <strong>Warning:</strong> {warning}</div>"""

                    # Quotes
                    traveler_quotes = getattr(slot, 'traveler_quotes', None)
                    if traveler_quotes:
                        for quote in traveler_quotes[:2]:
                            html += f"""
            <div class="quote">💬 "{quote}"</div>"""

                    # Cost
                    if slot.estimated_cost:
                        html += f"""
            <p><strong>Cost:</strong> <span class="cost">{slot.estimated_cost}</span></p>"""

                    # Map link
                    if hasattr(slot, 'map_link') and slot.map_link:
                        html += f"""
            <p>🗺️ <a href="{slot.map_link}" target="_blank">View on map</a></p>"""

                    html += """
        </div>"""

            html += """
    </div>
"""

        # Important Information
        html += """
    <div class="important-info">
        <h2>Important Information</h2>
"""

        if itinerary.general_tips:
            html += """
        <h3>General Tips</h3>
        <ul>
"""
            for tip in itinerary.general_tips:
                html += f"            <li>{tip}</li>\n"
            html += """        </ul>
"""

        if itinerary.important_warnings:
            html += """
        <h3>Warnings</h3>
        <ul>
"""
            for warning in itinerary.important_warnings:
                html += f"            <li>⚠️ {warning}</li>\n"
            html += """        </ul>
"""

        if itinerary.highlights:
            html += """
        <h3>Highlights</h3>
        <ul>
"""
            for highlight in itinerary.highlights:
                html += f"            <li>✨ {highlight}</li>\n"
            html += """        </ul>
"""

        html += """    </div>
"""

        # Conclusion (only if narrative was generated)
        if narrative:
            html += """
    <div class="conclusion">
        <h2>About This Itinerary</h2>
"""
            html += f"        {self._markdown_to_html_paragraphs(narrative.conclusion)}\n"
            html += """    </div>
"""

        html += """
    <div class="footer">
"""
        html += f"        <p>Generated using {itinerary.sources_used} traveler experiences. Confidence: {itinerary.overall_confidence}/10</p>\n"
        html += """    </div>
</body>
</html>"""

        return html

    def format_text_summary(self, itinerary: GeneratedItinerary) -> str:
        """
        Format as quick plain-text summary.

        For quick sharing and previews.

        Args:
            itinerary: Generated itinerary

        Returns:
            Plain text string
        """
        lines = []

        # Header
        lines.append(f"{itinerary.destination.upper()} - {itinerary.duration_days} DAYS")
        lines.append("=" * 50)
        lines.append("")

        # Days
        for i, day in enumerate(itinerary.days, 1):
            lines.append(f"Day {i}: {day.theme}")

            if day.morning:
                lines.append(f"  - Morning: {day.morning.entity_name}")
            if day.afternoon:
                lines.append(f"  - Afternoon: {day.afternoon.entity_name}")
            if day.evening:
                lines.append(f"  - Evening: {day.evening.entity_name}")
            if day.night:
                lines.append(f"  - Night: {day.night.entity_name}")

            lines.append(f"  Budget: {day.daily_budget_estimate}")
            lines.append("")

        # Summary
        lines.append("-" * 50)
        lines.append(f"TOTAL BUDGET: {itinerary.total_budget_estimate}")
        lines.append("")

        if itinerary.highlights:
            lines.append("HIGHLIGHTS:")
            for highlight in itinerary.highlights[:5]:
                lines.append(f"  - {highlight}")

        return "\n".join(lines)

    def format_for_sharing(
        self,
        itinerary: GeneratedItinerary,
        narrative: ItineraryNarrative,
        format: str = "social"
    ) -> str:
        """
        Format for sharing on social media.

        Args:
            itinerary: Generated itinerary
            narrative: Generated narrative
            format: "social" or "link"

        Returns:
            Shareable text
        """
        if format == "social":
            # Social media post
            lines = []
            lines.append(f"Just planned my {itinerary.duration_days}-day {itinerary.destination} trip! 🎉\n")

            # Top highlights with emojis
            emoji_list = ["✨", "🌟", "💫", "⭐", "🎯"]
            for i, highlight in enumerate(itinerary.highlights[:3]):
                emoji = emoji_list[i % len(emoji_list)]
                lines.append(f"{emoji} {highlight}")

            lines.append("")
            lines.append(f"💰 Budget: {itinerary.total_budget_estimate}")
            lines.append(f"🎭 Vibe: {itinerary.overall_vibe}")
            lines.append("")
            lines.append(f"#Travel #{itinerary.destination.replace(' ', '')} #TravelPlanning")

            return "\n".join(lines)

        elif format == "link":
            # Generate shareable link (placeholder - would need actual storage)
            # In production, upload to S3 and return short URL
            itinerary_id = hashlib.md5(
                f"{itinerary.destination}{itinerary.duration_days}".encode()
            ).hexdigest()[:8]
            return f"https://travelai.app/itinerary/{itinerary_id}"

        else:
            raise ValueError(f"Unknown format: {format}")

    def add_map_links(self, itinerary: GeneratedItinerary) -> GeneratedItinerary:
        """
        Add Google Maps links to all entities.

        Args:
            itinerary: Generated itinerary

        Returns:
            Itinerary with map links added
        """
        for day in itinerary.days:
            for slot in get_all_slots(day):
                if slot:
                    coordinates = getattr(slot, 'coordinates', None)
                    if coordinates:
                        lat = coordinates.get('lat')
                        lon = coordinates.get('lon')
                        if lat and lon:
                            slot.map_link = f"https://www.google.com/maps?q={lat},{lon}"

        return itinerary

    def create_interactive_map_data(self, itinerary: GeneratedItinerary) -> Dict[str, Any]:
        """
        Create GeoJSON for interactive map visualization.

        Compatible with Leaflet, Mapbox, Google Maps.

        Args:
            itinerary: Generated itinerary

        Returns:
            GeoJSON FeatureCollection
        """
        features = []

        for day_num, day in enumerate(itinerary.days, 1):
            for slot in get_all_slots(day):
                if slot:
                    coordinates = getattr(slot, 'coordinates', None)
                    if coordinates:
                        lat = coordinates.get('lat')
                        lon = coordinates.get('lon')

                        if lat and lon:
                            feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [lon, lat]  # GeoJSON uses [lon, lat]
                                },
                                "properties": {
                                    "name": slot.entity_name,
                                    "day": day_num,
                                    "day_theme": day.theme,
                                    "time": slot.time_period.value if slot.time_period else "unknown",
                                    "description": slot.activity_description,
                                    "category": slot.entity_type,
                                    "cost": slot.estimated_cost or "N/A",
                                    "marker_color": get_day_color(day_num),
                                    "emoji": get_slot_emoji(slot.time_period) if slot.time_period else "📍"
                                }
                            }
                            features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "destination": itinerary.destination,
                "duration_days": itinerary.duration_days,
                "total_locations": len(features)
            }
        }

    def export_to_pdf(
        self,
        itinerary: GeneratedItinerary,
        narrative: ItineraryNarrative,
        output_path: str
    ) -> bool:
        """
        Export to PDF (optional - requires additional libraries).

        This is a placeholder. In production, would use:
        - weasyprint (HTML to PDF)
        - reportlab (direct PDF generation)
        - pdfkit (wkhtmltopdf wrapper)

        Args:
            itinerary: Generated itinerary
            narrative: Generated narrative
            output_path: Path to save PDF

        Returns:
            True if successful, False otherwise
        """
        logger.warning("PDF export not implemented. Install weasyprint or reportlab.")
        logger.info(f"Would export to: {output_path}")

        # Placeholder implementation
        # In production:
        # html = self.format_html(itinerary, narrative)
        # HTML(string=html).write_pdf(output_path)

        return False

    # Helper methods

    def _markdown_to_html_paragraphs(self, text: str) -> str:
        """
        Convert markdown-style text to HTML paragraphs.

        Args:
            text: Text with newlines

        Returns:
            HTML with <p> tags
        """
        # Split into paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        # Wrap in <p> tags
        html_paragraphs = [f"<p>{p}</p>" for p in paragraphs]

        return "\n".join(html_paragraphs)


# =============================================================================
# Testing Function
# =============================================================================

def test_formatter():
    """Test ItineraryFormatter with sample data."""
    from src.rag.itinerary_generator import test_itinerary_generator

    logger.info("=" * 80)
    logger.info("🧪 TESTING ITINERARY FORMATTER")
    logger.info("=" * 80)

    # Generate test itinerary and narrative
    logger.info("\nGenerating test itinerary...")

    # Import test function from itinerary_generator
    from src.rag.intent_parser import IntentParser
    from src.rag.retriever import RAGRetriever
    from src.rag.reranker import LLMReranker
    from src.rag.context_builder import ContextBuilder
    from src.rag.itinerary_generator import ItineraryGenerator
    from src.rag.narrative_generator import NarrativeGenerator
    from src.vectordb import ChromaDBClient
    from src.utils.embedding_client import EmbeddingClient

    # Initialize
    chromadb = ChromaDBClient.initialize_from_env()
    embedding_client = EmbeddingClient()

    # Parse intent
    parser = IntentParser()
    query = "3 days in Bangkok, solo budget traveler, party and food"
    intent = parser.parse_query(query)

    # Retrieve
    retriever = RAGRetriever(chromadb, embedding_client)
    candidates = retriever.retrieve_for_itinerary(intent, top_k=20)

    # Re-rank
    reranker = LLMReranker(provider="deepseek")
    reranked = reranker.rerank_candidates(candidates, intent, top_k=10)

    # Build context
    builder = ContextBuilder()
    context = builder.build_rag_context(reranked, intent)

    # Generate itinerary
    generator = ItineraryGenerator(provider="gemini")
    itinerary = generator.generate_itinerary(context, intent)

    # Generate narrative
    narrative_gen = NarrativeGenerator(provider="gemini")
    narrative = narrative_gen.generate_narrative(itinerary, intent)

    logger.info("✅ Test data generated\n")

    # Test formatter
    formatter = ItineraryFormatter()

    # Test 1: JSON
    logger.info("📝 Testing JSON format...")
    json_output = formatter.format_json(itinerary, narrative)
    assert 'itinerary' in json_output
    assert 'narrative' in json_output
    assert 'metadata' in json_output
    assert 'provenance' in json_output
    logger.info(f"✅ JSON format OK ({len(json.dumps(json_output))} bytes)")

    # Test 2: Markdown
    logger.info("\n📝 Testing Markdown format...")
    md = formatter.format_markdown(itinerary, narrative)
    assert '# ' in md  # Has headers
    assert len(md) > 500  # Substantial content
    assert '##' in md  # Has subheaders
    logger.info(f"✅ Markdown format OK ({len(md)} characters)")

    # Test 3: HTML
    logger.info("\n📝 Testing HTML format...")
    html = formatter.format_html(itinerary, narrative)
    assert '<html>' in html
    assert '</html>' in html
    assert '<body>' in html
    assert len(html) > 1000
    logger.info(f"✅ HTML format OK ({len(html)} characters)")

    # Test 4: Text summary
    logger.info("\n📝 Testing text summary...")
    text = formatter.format_text_summary(itinerary)
    assert itinerary.destination.upper() in text
    assert 'BUDGET' in text
    logger.info(f"✅ Text summary OK ({len(text)} characters)")

    # Test 5: Social sharing
    logger.info("\n📝 Testing social sharing format...")
    social = formatter.format_for_sharing(itinerary, narrative, format="social")
    assert '🎉' in social or '✨' in social  # Has emojis
    assert itinerary.destination in social
    logger.info(f"✅ Social format OK ({len(social)} characters)")

    # Test 6: Map links
    logger.info("\n📝 Testing map link addition...")
    itinerary_with_links = formatter.add_map_links(itinerary)
    # Check if any slots got map links (if they have coordinates)
    has_links = any(
        hasattr(slot, 'map_link') and slot.map_link
        for day in itinerary_with_links.days
        for slot in get_all_slots(day)
        if slot and slot.coordinates
    )
    logger.info(f"✅ Map links {'added' if has_links else 'processed (no coordinates found)'}")

    # Test 7: GeoJSON
    logger.info("\n📝 Testing GeoJSON map data...")
    map_data = formatter.create_interactive_map_data(itinerary)
    assert map_data['type'] == 'FeatureCollection'
    assert 'features' in map_data
    assert 'metadata' in map_data
    logger.info(f"✅ GeoJSON OK ({len(map_data['features'])} features)")

    # Print samples
    logger.info("\n" + "=" * 80)
    logger.info("📄 SAMPLE OUTPUTS")
    logger.info("=" * 80)

    logger.info("\n--- Text Summary (first 500 chars) ---")
    logger.info(text[:500] + "..." if len(text) > 500 else text)

    logger.info("\n--- Social Sharing ---")
    logger.info(social)

    logger.info("\n--- Map Data Summary ---")
    logger.info(f"Total features: {len(map_data['features'])}")
    logger.info(f"Destination: {map_data['metadata']['destination']}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ ALL FORMATTER TESTS PASSED")
    logger.info("=" * 80)

    return {
        'json': json_output,
        'markdown': md,
        'html': html,
        'text': text,
        'social': social,
        'map_data': map_data
    }


if __name__ == '__main__':
    test_formatter()
