#!/usr/bin/env python3
"""
Entity Extraction Pipeline Debugger

Debug tool for testing the 3-stage entity extraction pipeline:
- Stage 1: YouTube video crawling
- Stage 2: Entity extraction
- Stage 3: Deduplication

Usage:
    python scripts/debug_entity_extraction.py --url "https://youtube.com/watch?v=abc123"
    python scripts/debug_entity_extraction.py --url "https://youtube.com/watch?v=abc123" --output-dir debug_reports/
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import Counter

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.youtube import crawl_video, extract_video_id
from src.processors.stage2_extractor import (
    process_short_video,
    process_long_video,
    classify_video_length,
    calculate_word_count
)
from src.processors.deduplication import group_exact_matches, find_fuzzy_candidates
from src.utils.logging import get_logger
from src.utils.content_id import generate_content_id

logger = get_logger(__name__)


class EntityExtractionDebugger:
    """Debug and analyze entity extraction pipeline"""

    def __init__(self, output_dir: str = "debug_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.report_data = {
            "run_metadata": {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
            },
            "stages": {}
        }

    def run_stage1(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        Run Stage 1: YouTube Crawling

        Returns:
            Video data with metadata and transcript
        """
        logger.info("=" * 80)
        logger.info("STAGE 1: YOUTUBE VIDEO CRAWLING")
        logger.info("=" * 80)

        stage_start = time.time()

        try:
            video_id = extract_video_id(video_url)
            logger.info(f"Video ID: {video_id}")
            logger.info(f"Fetching video metadata and transcript...")

            video_obj = crawl_video(video_url)

            if not video_obj:
                logger.error("Failed to crawl video")
                self.report_data["stages"]["stage1"] = {
                    "status": "failed",
                    "error": "Video crawling failed"
                }
                return None

            # Convert Pydantic object to dict
            video_data = video_obj.model_dump() if hasattr(video_obj, 'model_dump') else video_obj.dict()

            # Analyze transcript quality
            transcript = video_data.get('transcript', [])
            transcript_text = " ".join([seg.get('text', '') for seg in transcript])
            word_count = len(transcript_text.split())

            # Calculate metrics
            duration = video_data.get('duration_seconds', 0)
            words_per_minute = (word_count / duration) * 60 if duration > 0 else 0

            stage_time = time.time() - stage_start

            # Store results
            self.report_data["stages"]["stage1"] = {
                "status": "success",
                "execution_time_seconds": round(stage_time, 2),
                "video_metadata": {
                    "video_id": video_id,
                    "title": video_data.get('title', ''),
                    "channel": video_data.get('channel_name', ''),
                    "duration_seconds": duration,
                    "duration_formatted": f"{duration // 60}m {duration % 60}s",
                    "view_count": video_data.get('view_count', 0),
                    "publish_date": video_data.get('publish_date', ''),
                    "language": video_data.get('language', 'unknown')
                },
                "transcript_quality": {
                    "segment_count": len(transcript),
                    "word_count": word_count,
                    "words_per_minute": round(words_per_minute, 1),
                    "transcript_length_chars": len(transcript_text),
                    "quality_assessment": self._assess_transcript_quality(
                        words_per_minute, len(transcript)
                    )
                },
                "sample_transcript": transcript_text[:500] + "..." if len(transcript_text) > 500 else transcript_text
            }

            logger.info(f"✅ Stage 1 Complete ({stage_time:.1f}s)")
            logger.info(f"   Title: {video_data.get('title', '')}")
            logger.info(f"   Duration: {duration // 60}m {duration % 60}s")
            logger.info(f"   Transcript: {len(transcript)} segments, {word_count} words")
            logger.info(f"   Quality: {self.report_data['stages']['stage1']['transcript_quality']['quality_assessment']}")

            return video_data

        except Exception as e:
            logger.error(f"Stage 1 failed: {e}", exc_info=True)
            self.report_data["stages"]["stage1"] = {
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": time.time() - stage_start
            }
            return None

    def run_stage2(self, video_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run Stage 2: Entity Extraction

        Returns:
            Extracted entities and traveler profile
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("STAGE 2: ENTITY EXTRACTION")
        logger.info("=" * 80)

        stage_start = time.time()

        try:
            logger.info("Sending transcript to LLM for entity extraction...")

            # Classify video length
            duration = video_data.get('duration_seconds', 0)
            video_length = classify_video_length(duration)

            logger.info(f"Video classified as: {video_length} ({duration // 60}m {duration % 60}s)")

            # Process based on video length
            if video_length == "short":
                result_obj = process_short_video(video_data)
            else:
                result_obj = process_long_video(video_data)

            if not result_obj:
                logger.error("Entity extraction failed")
                self.report_data["stages"]["stage2"] = {
                    "status": "failed",
                    "error": "Entity extraction returned no results"
                }
                return None

            # Convert Pydantic object to dict
            result = result_obj.model_dump() if hasattr(result_obj, 'model_dump') else result_obj.dict()

            # Analyze entities
            entities = result.get('entities', [])
            traveler_profile = result.get('traveler_profile', {})

            # Count by type
            entity_types = Counter([e.get('entity_type', 'unknown') for e in entities])

            # Calculate quality metrics
            avg_quality = sum([e.get('quality_score', 0) for e in entities]) / len(entities) if entities else 0
            entities_with_location = sum([1 for e in entities if e.get('location')])
            entities_with_price = sum([1 for e in entities if e.get('price_info')])

            stage_time = time.time() - stage_start

            # Store results
            self.report_data["stages"]["stage2"] = {
                "status": "success",
                "execution_time_seconds": round(stage_time, 2),
                "entity_statistics": {
                    "total_entities": len(entities),
                    "entities_by_type": dict(entity_types),
                    "average_quality_score": round(avg_quality, 2),
                    "entities_with_location": entities_with_location,
                    "entities_with_price": entities_with_price,
                    "location_coverage": round((entities_with_location / len(entities)) * 100, 1) if entities else 0,
                    "price_coverage": round((entities_with_price / len(entities)) * 100, 1) if entities else 0
                },
                "traveler_profile": {
                    "demographics": traveler_profile.get('demographics', {}),
                    "travel_style": traveler_profile.get('travel_style', []),
                    "budget_tier": traveler_profile.get('budget_tier', 'unknown'),
                    "trip_duration_days": traveler_profile.get('trip_duration_days'),
                    "confidence_score": traveler_profile.get('confidence_score', 0)
                },
                "sample_entities": entities[:5],  # First 5 entities
                "llm_metrics": {
                    "tokens_used": result.get('tokens_used', 0),
                    "cost_usd": result.get('cost', 0),
                    "model": result.get('model', 'unknown')
                }
            }

            logger.info(f"✅ Stage 2 Complete ({stage_time:.1f}s)")
            logger.info(f"   Entities Extracted: {len(entities)}")
            logger.info(f"   Entity Types: {dict(entity_types)}")
            logger.info(f"   Average Quality: {avg_quality:.2f}/5.0")
            logger.info(f"   Location Coverage: {self.report_data['stages']['stage2']['entity_statistics']['location_coverage']}%")
            logger.info(f"   LLM Cost: ${result.get('cost', 0):.4f}")

            return result

        except Exception as e:
            logger.error(f"Stage 2 failed: {e}", exc_info=True)
            self.report_data["stages"]["stage2"] = {
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": time.time() - stage_start
            }
            return None

    def run_stage3(self, entities: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Run Stage 3: Deduplication

        Returns:
            Deduplicated entities and statistics
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("STAGE 3: ENTITY DEDUPLICATION")
        logger.info("=" * 80)

        stage_start = time.time()

        try:
            # Convert entities to format expected by deduplication
            formatted_entities = []
            for i, entity in enumerate(entities):
                formatted_entities.append({
                    'entity_id': f"entity_{i}",
                    'normalized_name': entity.get('name', '').strip().lower(),
                    'normalized_location': entity.get('location', '').strip().lower() if entity.get('location') else '',
                    'entity': entity
                })

            logger.info(f"Running exact matching (Tier 1)...")
            exact_groups = group_exact_matches(formatted_entities)

            logger.info(f"Running fuzzy matching (Tier 2)...")
            fuzzy_pairs = find_fuzzy_candidates(formatted_entities, threshold=0.80)

            # Calculate statistics
            exact_duplicates = sum([len(group) - 1 for group in exact_groups.values() if len(group) > 1])
            fuzzy_duplicates = len(fuzzy_pairs)

            # Unique entities after deduplication
            unique_entities = len(entities) - exact_duplicates - fuzzy_duplicates
            dedup_rate = (exact_duplicates + fuzzy_duplicates) / len(entities) * 100 if entities else 0

            stage_time = time.time() - stage_start

            # Store results
            self.report_data["stages"]["stage3"] = {
                "status": "success",
                "execution_time_seconds": round(stage_time, 2),
                "deduplication_statistics": {
                    "input_entities": len(entities),
                    "exact_duplicates_found": exact_duplicates,
                    "fuzzy_duplicates_found": fuzzy_duplicates,
                    "total_duplicates": exact_duplicates + fuzzy_duplicates,
                    "unique_entities": unique_entities,
                    "deduplication_rate_percent": round(dedup_rate, 1)
                },
                "exact_match_groups": {
                    "group_count": len([g for g in exact_groups.values() if len(g) > 1]),
                    "sample_groups": [
                        {
                            "group_id": gid,
                            "entity_count": len(group),
                            "normalized_name": group[0]['normalized_name'] if group else None
                        }
                        for gid, group in list(exact_groups.items())[:3] if len(group) > 1
                    ]
                },
                "fuzzy_match_pairs": {
                    "pair_count": len(fuzzy_pairs),
                    "sample_pairs": [
                        {
                            "entity1": pair[0]['entity'].get('name'),
                            "entity2": pair[1]['entity'].get('name'),
                            "similarity": pair[2]
                        }
                        for pair in fuzzy_pairs[:5]
                    ]
                }
            }

            logger.info(f"✅ Stage 3 Complete ({stage_time:.1f}s)")
            logger.info(f"   Input Entities: {len(entities)}")
            logger.info(f"   Exact Duplicates: {exact_duplicates}")
            logger.info(f"   Fuzzy Duplicates: {fuzzy_duplicates}")
            logger.info(f"   Unique Entities: {unique_entities}")
            logger.info(f"   Deduplication Rate: {dedup_rate:.1f}%")

            return {
                "exact_groups": exact_groups,
                "fuzzy_pairs": fuzzy_pairs,
                "unique_count": unique_entities
            }

        except Exception as e:
            logger.error(f"Stage 3 failed: {e}", exc_info=True)
            self.report_data["stages"]["stage3"] = {
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": time.time() - stage_start
            }
            return None

    def _assess_transcript_quality(self, words_per_minute: float, segment_count: int) -> str:
        """Assess transcript quality based on metrics"""
        if words_per_minute < 50:
            return "Poor (too slow)"
        elif words_per_minute > 200:
            return "Poor (too fast)"
        elif segment_count < 10:
            return "Poor (too short)"
        elif 100 <= words_per_minute <= 180 and segment_count >= 50:
            return "Excellent"
        elif 80 <= words_per_minute <= 200:
            return "Good"
        else:
            return "Fair"

    def generate_report(self, video_url: str) -> str:
        """Generate HTML report"""
        logger.info("")
        logger.info("=" * 80)
        logger.info("GENERATING DEBUG REPORT")
        logger.info("=" * 80)

        # Generate filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_id = extract_video_id(video_url) if video_url else "unknown"

        json_path = self.output_dir / f"debug_{video_id}_{timestamp}.json"
        html_path = self.output_dir / f"debug_{video_id}_{timestamp}.html"

        # Save JSON
        with open(json_path, 'w') as f:
            json.dump(self.report_data, f, indent=2)

        # Generate HTML
        html_content = self._generate_html_report()
        with open(html_path, 'w') as f:
            f.write(html_content)

        logger.info(f"✅ Reports generated:")
        logger.info(f"   JSON: {json_path}")
        logger.info(f"   HTML: {html_path}")

        return str(html_path)

    def _generate_html_report(self) -> str:
        """Generate HTML report content"""
        # Calculate summary
        total_time = sum([
            self.report_data['stages'].get(f'stage{i}', {}).get('execution_time_seconds', 0)
            for i in range(1, 4)
        ])

        stages_passed = sum([
            1 for stage_data in self.report_data['stages'].values()
            if stage_data.get('status') == 'success'
        ])

        # Get data safely
        stage1 = self.report_data['stages'].get('stage1', {})
        stage2 = self.report_data['stages'].get('stage2', {})
        stage3 = self.report_data['stages'].get('stage3', {})

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Entity Extraction Debug Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}

        h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}

        .subtitle {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}

        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .summary-card {{
            background: #1e293b;
            padding: 25px;
            border-radius: 12px;
            border-left: 4px solid #667eea;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}

        .summary-card h3 {{
            font-size: 0.9rem;
            text-transform: uppercase;
            color: #94a3b8;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }}

        .summary-card .value {{
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }}

        .stage {{
            background: #1e293b;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}

        .stage-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 2px solid #334155;
        }}

        .stage-title {{
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            gap: 15px;
        }}

        .badge {{
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .badge.success {{
            background: #10b981;
            color: white;
        }}

        .badge.failed {{
            background: #ef4444;
            color: white;
        }}

        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }}

        .metric {{
            background: #0f172a;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #334155;
        }}

        .metric-label {{
            font-size: 0.85rem;
            color: #94a3b8;
            margin-bottom: 8px;
        }}

        .metric-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #667eea;
        }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: #0f172a;
            border-radius: 8px;
            overflow: hidden;
        }}

        .data-table th {{
            background: #334155;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }}

        .data-table td {{
            padding: 15px;
            border-top: 1px solid #334155;
        }}

        .data-table tr:hover {{
            background: #1e293b;
        }}

        .code-block {{
            background: #0f172a;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #334155;
            overflow-x: auto;
            margin-top: 15px;
        }}

        .code-block pre {{
            margin: 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.5;
        }}

        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #334155;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 10px;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            padding: 30px;
            color: #64748b;
            font-size: 0.9rem;
        }}

        .entity-card {{
            background: #0f172a;
            padding: 15px;
            border-radius: 8px;
            border-left: 3px solid #667eea;
            margin-bottom: 10px;
        }}

        .entity-card h4 {{
            margin-bottom: 8px;
            color: #667eea;
        }}

        .entity-card p {{
            font-size: 0.9rem;
            color: #94a3b8;
            margin: 4px 0;
        }}

        .chart-container {{
            background: #0f172a;
            padding: 25px;
            border-radius: 8px;
            border: 1px solid #334155;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 Entity Extraction Debug Report</h1>
            <div class="subtitle">Pipeline Performance Analysis</div>
            <div class="subtitle" style="margin-top: 10px; font-size: 0.9rem;">
                Generated: {self.report_data['run_metadata']['timestamp']}
            </div>
        </header>

        <div class="summary">
            <div class="summary-card">
                <h3>Total Time</h3>
                <div class="value">{total_time:.1f}s</div>
            </div>
            <div class="summary-card">
                <h3>Stages Passed</h3>
                <div class="value">{stages_passed}/3</div>
            </div>
            <div class="summary-card">
                <h3>Entities Extracted</h3>
                <div class="value">{stage2.get('entity_statistics', {}).get('total_entities', 0)}</div>
            </div>
            <div class="summary-card">
                <h3>Unique After Dedup</h3>
                <div class="value">{stage3.get('deduplication_statistics', {}).get('unique_entities', 0)}</div>
            </div>
        </div>

        <!-- Stage 1: YouTube Crawling -->
        <div class="stage">
            <div class="stage-header">
                <div class="stage-title">
                    📹 Stage 1: YouTube Crawling
                </div>
                <span class="badge {stage1.get('status', 'failed')}">{stage1.get('status', 'failed')}</span>
            </div>

            {self._render_stage1_content(stage1)}
        </div>

        <!-- Stage 2: Entity Extraction -->
        <div class="stage">
            <div class="stage-header">
                <div class="stage-title">
                    🎯 Stage 2: Entity Extraction
                </div>
                <span class="badge {stage2.get('status', 'failed')}">{stage2.get('status', 'failed')}</span>
            </div>

            {self._render_stage2_content(stage2)}
        </div>

        <!-- Stage 3: Deduplication -->
        <div class="stage">
            <div class="stage-header">
                <div class="stage-title">
                    🔄 Stage 3: Deduplication
                </div>
                <span class="badge {stage3.get('status', 'failed')}">{stage3.get('status', 'failed')}</span>
            </div>

            {self._render_stage3_content(stage3)}
        </div>

        <footer>
            <p>TravelAI Entity Extraction Pipeline Debugger v1.0</p>
            <p style="margin-top: 10px;">For issues and improvements, check the improvement plan</p>
        </footer>
    </div>
</body>
</html>
"""
        return html

    def _render_stage1_content(self, stage1: Dict) -> str:
        """Render Stage 1 content"""
        if stage1.get('status') != 'success':
            return f"<div class='code-block'><pre>Error: {stage1.get('error', 'Unknown error')}</pre></div>"

        metadata = stage1.get('video_metadata', {})
        quality = stage1.get('transcript_quality', {})

        return f"""
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label">Execution Time</div>
                    <div class="metric-value">{stage1.get('execution_time_seconds', 0)}s</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Duration</div>
                    <div class="metric-value">{metadata.get('duration_formatted', 'N/A')}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Word Count</div>
                    <div class="metric-value">{quality.get('word_count', 0):,}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Quality</div>
                    <div class="metric-value" style="font-size: 1.2rem;">{quality.get('quality_assessment', 'N/A')}</div>
                </div>
            </div>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Video Details</h3>
            <table class="data-table">
                <tr>
                    <td style="font-weight: 600; width: 200px;">Video ID</td>
                    <td>{metadata.get('video_id', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Title</td>
                    <td>{metadata.get('title', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Channel</td>
                    <td>{metadata.get('channel', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Views</td>
                    <td>{metadata.get('view_count', 0):,}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Language</td>
                    <td>{metadata.get('language', 'N/A')}</td>
                </tr>
            </table>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Transcript Sample</h3>
            <div class="code-block">
                <pre>{stage1.get('sample_transcript', 'No transcript available')}</pre>
            </div>
        """

    def _render_stage2_content(self, stage2: Dict) -> str:
        """Render Stage 2 content"""
        if stage2.get('status') != 'success':
            return f"<div class='code-block'><pre>Error: {stage2.get('error', 'Unknown error')}</pre></div>"

        stats = stage2.get('entity_statistics', {})
        profile = stage2.get('traveler_profile', {})
        llm = stage2.get('llm_metrics', {})

        entity_types_html = "".join([
            f"<tr><td>{etype}</td><td style='font-weight: 600; color: #667eea;'>{count}</td></tr>"
            for etype, count in stats.get('entities_by_type', {}).items()
        ])

        sample_entities = stage2.get('sample_entities', [])
        entities_html = "".join([
            f"""<div class="entity-card">
                <h4>{entity.get('name', 'Unknown')}</h4>
                <p><strong>Type:</strong> {entity.get('entity_type', 'N/A')}</p>
                <p><strong>Location:</strong> {entity.get('location', 'N/A')}</p>
                <p><strong>Quality Score:</strong> {entity.get('quality_score', 0)}/5.0</p>
            </div>"""
            for entity in sample_entities
        ])

        return f"""
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label">Execution Time</div>
                    <div class="metric-value">{stage2.get('execution_time_seconds', 0)}s</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total Entities</div>
                    <div class="metric-value">{stats.get('total_entities', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Avg Quality</div>
                    <div class="metric-value">{stats.get('average_quality_score', 0)}/5</div>
                </div>
                <div class="metric">
                    <div class="metric-label">LLM Cost</div>
                    <div class="metric-value">${llm.get('cost_usd', 0):.4f}</div>
                </div>
            </div>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Entity Distribution</h3>
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Entity Type</th>
                        <th>Count</th>
                    </tr>
                </thead>
                <tbody>
                    {entity_types_html}
                </tbody>
            </table>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Coverage Metrics</h3>
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label">Location Coverage</div>
                    <div class="metric-value">{stats.get('location_coverage', 0)}%</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {stats.get('location_coverage', 0)}%"></div>
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Price Coverage</div>
                    <div class="metric-value">{stats.get('price_coverage', 0)}%</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {stats.get('price_coverage', 0)}%"></div>
                    </div>
                </div>
            </div>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Sample Entities</h3>
            {entities_html if entities_html else '<p style="color: #94a3b8;">No entities to display</p>'}

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Traveler Profile</h3>
            <div class="code-block">
                <pre>{json.dumps(profile, indent=2)}</pre>
            </div>
        """

    def _render_stage3_content(self, stage3: Dict) -> str:
        """Render Stage 3 content"""
        if stage3.get('status') != 'success':
            return f"<div class='code-block'><pre>Error: {stage3.get('error', 'Unknown error')}</pre></div>"

        stats = stage3.get('deduplication_statistics', {})

        return f"""
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label">Execution Time</div>
                    <div class="metric-value">{stage3.get('execution_time_seconds', 0)}s</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Input Entities</div>
                    <div class="metric-value">{stats.get('input_entities', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Duplicates Found</div>
                    <div class="metric-value">{stats.get('total_duplicates', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Unique Entities</div>
                    <div class="metric-value">{stats.get('unique_entities', 0)}</div>
                </div>
            </div>

            <h3 style="margin-top: 25px; margin-bottom: 15px;">Deduplication Breakdown</h3>
            <table class="data-table">
                <tr>
                    <td style="font-weight: 600; width: 300px;">Exact Match Duplicates</td>
                    <td style="color: #667eea; font-weight: 600;">{stats.get('exact_duplicates_found', 0)}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Fuzzy Match Duplicates</td>
                    <td style="color: #667eea; font-weight: 600;">{stats.get('fuzzy_duplicates_found', 0)}</td>
                </tr>
                <tr>
                    <td style="font-weight: 600;">Deduplication Rate</td>
                    <td style="color: #667eea; font-weight: 600;">{stats.get('deduplication_rate_percent', 0)}%</td>
                </tr>
            </table>

            <div class="progress-bar" style="margin-top: 20px;">
                <div class="progress-fill" style="width: {stats.get('deduplication_rate_percent', 0)}%"></div>
            </div>
        """


def main():
    parser = argparse.ArgumentParser(description="Debug entity extraction pipeline with single video")
    parser.add_argument("--url", required=True, help="YouTube video URL")
    parser.add_argument("--output-dir", default="debug_reports", help="Output directory for reports")

    args = parser.parse_args()

    # Initialize debugger
    debugger = EntityExtractionDebugger(output_dir=args.output_dir)

    print("\n" + "=" * 80)
    print("ENTITY EXTRACTION PIPELINE DEBUGGER")
    print("=" * 80)
    print(f"Video URL: {args.url}")
    print(f"Output Directory: {args.output_dir}")
    print("=" * 80 + "\n")

    # Run Stage 1
    video_data = debugger.run_stage1(args.url)
    if not video_data:
        print("\n❌ Stage 1 failed. Cannot continue.")
        debugger.generate_report(args.url)
        return 1

    # Run Stage 2
    extraction_result = debugger.run_stage2(video_data)
    if not extraction_result:
        print("\n❌ Stage 2 failed. Skipping Stage 3.")
        debugger.generate_report(args.url)
        return 1

    # Run Stage 3
    entities = extraction_result.get('entities', [])
    if entities:
        dedup_result = debugger.run_stage3(entities)
    else:
        print("\n⚠️  No entities to deduplicate. Skipping Stage 3.")

    # Generate report
    report_path = debugger.generate_report(args.url)

    print("\n" + "=" * 80)
    print("✅ PIPELINE DEBUG COMPLETE")
    print("=" * 80)
    print(f"\n📊 Open the report in your browser:")
    print(f"   file://{report_path}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
