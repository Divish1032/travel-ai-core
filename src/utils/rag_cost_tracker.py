#!/usr/bin/env python3
"""
RAG Cost Tracker - Monitor and Report Stage 5 LLM Costs

Tracks costs across all RAG phases to monitor spending, optimize usage,
and prevent budget overruns.

Features:
- Phase-by-phase cost breakdown
- Token usage tracking
- Budget alerts and limits
- Cost reports and analytics
- Historical cost logging

Author: TravelAI Team
Date: 2025-12-20
"""

import os
import json
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from collections import defaultdict

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class BudgetExceededError(Exception):
    """Raised when cost exceeds budget limit"""
    pass


# =============================================================================
# RAG Cost Tracker
# =============================================================================

class RAGCostTracker:
    """
    Track costs across all RAG phases.

    Monitors LLM API costs for each phase of the RAG pipeline:
    - Intent parsing
    - Re-ranking
    - Itinerary generation
    - Narrative generation

    Example:
        >>> tracker = RAGCostTracker()
        >>> tracker.track_phase('intent_parsing', cost=0.001, input_tokens=500, output_tokens=200)
        >>> tracker.print_summary()
    """

    def __init__(self, budget_limit: Optional[float] = None):
        """
        Initialize cost tracker.

        Args:
            budget_limit: Optional budget limit in USD (alerts when approaching)
        """
        self.costs = {
            'intent_parsing': [],
            'retrieval': [],
            're_ranking': [],
            'context_building': [],
            'generation': [],
            'validation': [],
            'narrative': [],
            'total': 0.0
        }

        self.token_usage = {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0
        }

        self.phase_tokens = defaultdict(lambda: {'input': 0, 'output': 0})
        self.budget_limit = budget_limit
        self.start_time = datetime.now()
        self.queries_processed = 0

        logger.debug("RAGCostTracker initialized")
        if budget_limit:
            logger.info(f"Budget limit set: ${budget_limit:.4f}")

    def track_phase(
        self,
        phase: str,
        cost: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record cost for a phase.

        Args:
            phase: Phase name (e.g., 'intent_parsing', 're_ranking', 'generation')
            cost: Cost in USD
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            metadata: Optional metadata (model, provider, etc.)
        """
        # Validate phase
        if phase not in self.costs:
            logger.warning(f"Unknown phase '{phase}', adding to tracker")
            self.costs[phase] = []

        # Record cost
        self.costs[phase].append({
            'cost': cost,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        })

        self.costs['total'] += cost

        # Update token counts
        self.token_usage['input_tokens'] += input_tokens
        self.token_usage['output_tokens'] += output_tokens
        self.token_usage['total_tokens'] += (input_tokens + output_tokens)

        # Track by phase
        self.phase_tokens[phase]['input'] += input_tokens
        self.phase_tokens[phase]['output'] += output_tokens

        # Check budget
        if self.budget_limit:
            self._check_budget()

        logger.debug(
            f"Tracked {phase}: ${cost:.6f} "
            f"({input_tokens} in, {output_tokens} out)"
        )

    def track_query_complete(self):
        """Mark one query as complete (for averaging)."""
        self.queries_processed += 1

    def _check_budget(self):
        """Check if approaching or exceeding budget limit."""
        if not self.budget_limit:
            return

        current = self.costs['total']
        limit = self.budget_limit

        # 80% warning
        if current > limit * 0.8 and current <= limit:
            warnings.warn(
                f"⚠️  Approaching budget limit: ${current:.4f} / ${limit:.4f} "
                f"({current/limit*100:.1f}%)",
                UserWarning
            )

        # 100% error
        if current > limit:
            raise BudgetExceededError(
                f"Budget limit exceeded: ${current:.4f} > ${limit:.4f}"
            )

    def get_report(self) -> Dict[str, Any]:
        """
        Generate detailed cost report.

        Returns:
            Dict with cost breakdown, token usage, and analytics
        """
        # Calculate breakdown by phase
        breakdown = {}
        for phase, entries in self.costs.items():
            if phase == 'total' or not entries:
                continue

            total_cost = sum(e['cost'] for e in entries)
            total_input = sum(e['input_tokens'] for e in entries)
            total_output = sum(e['output_tokens'] for e in entries)

            breakdown[phase] = {
                'total_cost': total_cost,
                'count': len(entries),
                'avg_cost': total_cost / len(entries) if entries else 0,
                'input_tokens': total_input,
                'output_tokens': total_output,
                'total_tokens': total_input + total_output,
                'percentage': (total_cost / self.costs['total'] * 100) if self.costs['total'] > 0 else 0
            }

        # Calculate cost efficiency metrics
        total_tokens = self.token_usage['total_tokens']
        cost_per_1k_input = (
            (self.costs['total'] / (self.token_usage['input_tokens'] / 1000))
            if self.token_usage['input_tokens'] > 0 else 0
        )
        cost_per_1k_output = (
            (self.costs['total'] / (self.token_usage['output_tokens'] / 1000))
            if self.token_usage['output_tokens'] > 0 else 0
        )

        # Time metrics
        elapsed = (datetime.now() - self.start_time).total_seconds()

        return {
            'summary': {
                'total_cost': self.costs['total'],
                'queries_processed': self.queries_processed,
                'cost_per_query': self.costs['total'] / self.queries_processed if self.queries_processed > 0 else 0,
                'elapsed_time': elapsed,
                'cost_per_second': self.costs['total'] / elapsed if elapsed > 0 else 0
            },
            'breakdown_by_phase': breakdown,
            'token_usage': {
                'total': self.token_usage['total_tokens'],
                'input': self.token_usage['input_tokens'],
                'output': self.token_usage['output_tokens'],
                'input_percentage': (
                    self.token_usage['input_tokens'] / total_tokens * 100
                    if total_tokens > 0 else 0
                ),
                'output_percentage': (
                    self.token_usage['output_tokens'] / total_tokens * 100
                    if total_tokens > 0 else 0
                )
            },
            'cost_efficiency': {
                'cost_per_1k_input_tokens': cost_per_1k_input,
                'cost_per_1k_output_tokens': cost_per_1k_output,
                'cost_per_1k_total_tokens': (
                    self.costs['total'] / (total_tokens / 1000)
                    if total_tokens > 0 else 0
                )
            },
            'budget': {
                'limit': self.budget_limit,
                'used': self.costs['total'],
                'remaining': self.budget_limit - self.costs['total'] if self.budget_limit else None,
                'percentage_used': (
                    self.costs['total'] / self.budget_limit * 100
                    if self.budget_limit else None
                )
            } if self.budget_limit else None,
            'timestamp': datetime.now().isoformat(),
            'start_time': self.start_time.isoformat()
        }

    def print_summary(self, verbose: bool = False):
        """
        Print human-readable cost summary.

        Args:
            verbose: Show detailed breakdown (default: False)
        """
        report = self.get_report()

        print("\n" + "=" * 70)
        print("💰 RAG COST SUMMARY")
        print("=" * 70)

        # Summary stats
        summary = report['summary']
        print(f"Queries processed:    {summary['queries_processed']}")
        print(f"Total cost:          ${summary['total_cost']:.6f}")
        print(f"Cost per query:      ${summary['cost_per_query']:.6f}")
        print(f"Elapsed time:        {summary['elapsed_time']:.1f}s")

        # Budget info
        if report.get('budget'):
            budget = report['budget']
            print(f"\nBudget:              ${budget['limit']:.6f}")
            print(f"Used:                ${budget['used']:.6f} ({budget['percentage_used']:.1f}%)")
            print(f"Remaining:           ${budget['remaining']:.6f}")

        # Phase breakdown
        print("\n" + "-" * 70)
        print("BREAKDOWN BY PHASE:")
        print("-" * 70)
        print(f"{'Phase':<20} {'Cost':>12} {'Calls':>8} {'%':>8} {'Tokens':>12}")
        print("-" * 70)

        breakdown = report['breakdown_by_phase']
        for phase in sorted(breakdown.keys(), key=lambda x: breakdown[x]['total_cost'], reverse=True):
            data = breakdown[phase]
            print(
                f"{phase:<20} "
                f"${data['total_cost']:>11.6f} "
                f"{data['count']:>8} "
                f"{data['percentage']:>7.1f}% "
                f"{data['total_tokens']:>12,}"
            )

        # Token usage
        print("\n" + "-" * 70)
        print("TOKEN USAGE:")
        print("-" * 70)
        tokens = report['token_usage']
        print(f"Input tokens:        {tokens['input']:>12,} ({tokens['input_percentage']:.1f}%)")
        print(f"Output tokens:       {tokens['output']:>12,} ({tokens['output_percentage']:.1f}%)")
        print(f"Total tokens:        {tokens['total']:>12,}")

        # Cost efficiency
        print("\n" + "-" * 70)
        print("COST EFFICIENCY:")
        print("-" * 70)
        efficiency = report['cost_efficiency']
        print(f"Per 1K input tokens:  ${efficiency['cost_per_1k_input_tokens']:.6f}")
        print(f"Per 1K output tokens: ${efficiency['cost_per_1k_output_tokens']:.6f}")
        print(f"Per 1K total tokens:  ${efficiency['cost_per_1k_total_tokens']:.6f}")

        print("=" * 70 + "\n")

        # Verbose: show individual calls
        if verbose:
            print("\n" + "=" * 70)
            print("DETAILED CALL LOG:")
            print("=" * 70)
            for phase, entries in self.costs.items():
                if phase == 'total' or not entries:
                    continue

                print(f"\n{phase.upper()}:")
                for i, entry in enumerate(entries, 1):
                    print(
                        f"  {i}. ${entry['cost']:.6f} - "
                        f"{entry['input_tokens']} in, {entry['output_tokens']} out - "
                        f"{entry['timestamp']}"
                    )
            print("=" * 70 + "\n")

    def save_report(
        self,
        filepath: Optional[str] = None,
        format: str = 'json'
    ):
        """
        Save cost report to file.

        Args:
            filepath: Output file path (default: stage5-costs/YYYY-MM-DD_HH-MM-SS.json)
            format: Output format ('json' or 'txt')
        """
        # Generate default filepath
        if filepath is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filepath = f"stage5-costs/{timestamp}.{format}"

        # Create directory
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Get report
        report = self.get_report()

        # Save
        if format == 'json':
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Cost report saved to: {filepath}")

        elif format == 'txt':
            # Redirect print to file
            import io
            import contextlib

            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                self.print_summary(verbose=True)

            with open(filepath, 'w') as file:
                file.write(f.getvalue())

            logger.info(f"Cost report saved to: {filepath}")

        else:
            raise ValueError(f"Unsupported format: {format}")

        return filepath

    def reset(self):
        """Reset all cost tracking."""
        self.__init__(budget_limit=self.budget_limit)
        logger.info("Cost tracker reset")

    def get_phase_cost(self, phase: str) -> float:
        """Get total cost for a specific phase."""
        if phase not in self.costs or not self.costs[phase]:
            return 0.0
        return sum(e['cost'] for e in self.costs[phase])

    def get_most_expensive_phase(self) -> tuple[str, float]:
        """
        Get the most expensive phase.

        Returns:
            Tuple of (phase_name, cost)
        """
        phase_costs = {
            phase: sum(e['cost'] for e in entries)
            for phase, entries in self.costs.items()
            if phase != 'total' and entries
        }

        if not phase_costs:
            return ('none', 0.0)

        max_phase = max(phase_costs.items(), key=lambda x: x[1])
        return max_phase


# =============================================================================
# Global Tracker Instance (Optional)
# =============================================================================

# Singleton instance for easy access
_global_tracker = None


def get_global_tracker(budget_limit: Optional[float] = None) -> RAGCostTracker:
    """
    Get or create global cost tracker instance.

    Args:
        budget_limit: Budget limit for new tracker

    Returns:
        Global RAGCostTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = RAGCostTracker(budget_limit=budget_limit)
    return _global_tracker


def reset_global_tracker():
    """Reset global tracker."""
    global _global_tracker
    _global_tracker = None


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("RAG Cost Tracker Test")
    print("=" * 70)

    # Create tracker with budget
    tracker = RAGCostTracker(budget_limit=0.10)  # $0.10 limit

    # Simulate some API calls
    print("\nSimulating RAG pipeline calls...\n")

    # Intent parsing
    tracker.track_phase('intent_parsing', cost=0.0001, input_tokens=100, output_tokens=50)

    # Re-ranking
    tracker.track_phase('re_ranking', cost=0.0015, input_tokens=1500, output_tokens=200)

    # Generation (main cost)
    tracker.track_phase('generation', cost=0.0080, input_tokens=3000, output_tokens=1500)

    # Narrative
    tracker.track_phase('narrative', cost=0.0025, input_tokens=1200, output_tokens=800)

    tracker.track_query_complete()

    # Print summary
    tracker.print_summary()

    # Save report
    filepath = tracker.save_report(format='json')
    print(f"Report saved to: {filepath}")

    # Get most expensive phase
    phase, cost = tracker.get_most_expensive_phase()
    print(f"\nMost expensive phase: {phase} (${cost:.6f})")

    print("\n" + "=" * 70)
