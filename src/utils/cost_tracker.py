"""
Cost Tracker for Stage 3 Processing

Centralized cost tracking for:
- LLM API calls (Gemini Flash, OpenAI, DeepSeek)
- Geocoding API calls (Google Maps vs Nominatim)

Usage:
    from src.utils.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.track_llm_call(input_tokens=1000, output_tokens=500, model='gemini-2.5-flash-lite')
    tracker.track_geocoding(provider='google', count=10)

    report = tracker.get_cost_report()
    print(f"Total cost: ${report['grand_total']:.6f}")
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Cost Rates
# =============================================================================

# LLM API Costs (per 1M tokens)
LLM_COSTS = {
    # Gemini
    'gemini-2.5-flash-lite': {
        'input': 0.0,  # Free tier
        'output': 0.0,  # Free tier
        'free_tier': True,
        'free_limits': '15 req/min, 1M tokens/min, 1500 req/day'
    },
    'gemini-1.5-flash': {
        'input': 0.075,
        'output': 0.30
    },
    'gemini-1.5-pro': {
        'input': 1.25,
        'output': 5.0
    },

    # OpenAI
    'gpt-4o': {
        'input': 2.50,
        'output': 10.0
    },
    'gpt-4o-mini': {
        'input': 0.150,
        'output': 0.600
    },
    'gpt-3.5-turbo': {
        'input': 0.50,
        'output': 1.50
    },

    # DeepSeek
    'deepseek-chat': {
        'input': 0.14,
        'output': 0.28
    }
}

# Geocoding API Costs
GEOCODING_COSTS = {
    'nominatim': 0.0,  # Free (OpenStreetMap)
    'google': 0.005    # $5 per 1000 requests = $0.005 per request
}


# =============================================================================
# Cost Tracker Class
# =============================================================================

class CostTracker:
    """
    Centralized cost tracker for Stage 3 processing.

    Tracks:
    - LLM API calls (tokens + costs)
    - Geocoding API calls (requests + costs)
    - Running totals

    Example:
        >>> tracker = CostTracker()
        >>> tracker.track_llm_call(1000, 500, 'gemini-2.5-flash-lite')
        >>> tracker.track_geocoding('google', 10)
        >>> report = tracker.get_cost_report()
        >>> print(f"Total: ${report['grand_total']:.6f}")
    """

    def __init__(self):
        """Initialize cost tracker."""
        self.llm_calls = {}  # model -> {calls, input_tokens, output_tokens, cost}
        self.geocoding_calls = {}  # provider -> {requests, cost}
        self.start_time = datetime.now(timezone.utc)

    def track_llm_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """
        Track an LLM API call.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name (e.g., 'gemini-2.5-flash-lite')

        Returns:
            Cost of this call in USD

        Example:
            >>> cost = tracker.track_llm_call(1000, 500, 'gemini-2.5-flash-lite')
            >>> print(f"This call cost: ${cost:.6f}")
        """
        # Get cost rates
        if model not in LLM_COSTS:
            logger.warning(f"Unknown model '{model}', assuming free tier")
            cost_rates = {'input': 0.0, 'output': 0.0}
        else:
            cost_rates = LLM_COSTS[model]

        # Calculate cost
        input_cost = (input_tokens / 1_000_000) * cost_rates.get('input', 0.0)
        output_cost = (output_tokens / 1_000_000) * cost_rates.get('output', 0.0)
        total_cost = input_cost + output_cost

        # Update tracking
        if model not in self.llm_calls:
            self.llm_calls[model] = {
                'calls': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'cost': 0.0
            }

        self.llm_calls[model]['calls'] += 1
        self.llm_calls[model]['input_tokens'] += input_tokens
        self.llm_calls[model]['output_tokens'] += output_tokens
        self.llm_calls[model]['total_tokens'] += input_tokens + output_tokens
        self.llm_calls[model]['cost'] += total_cost

        logger.debug(
            f"LLM call tracked: {model} "
            f"({input_tokens} + {output_tokens} tokens, ${total_cost:.6f})"
        )

        return total_cost

    def track_geocoding(self, provider: str, count: int = 1) -> float:
        """
        Track geocoding API calls.

        Args:
            provider: 'nominatim' (free) or 'google' (paid)
            count: Number of requests (default: 1)

        Returns:
            Cost of these requests in USD

        Example:
            >>> cost = tracker.track_geocoding('google', 10)
            >>> print(f"10 Google requests cost: ${cost:.6f}")
        """
        # Get cost rate
        cost_per_request = GEOCODING_COSTS.get(provider, 0.0)
        total_cost = cost_per_request * count

        # Update tracking
        if provider not in self.geocoding_calls:
            self.geocoding_calls[provider] = {
                'requests': 0,
                'cost': 0.0
            }

        self.geocoding_calls[provider]['requests'] += count
        self.geocoding_calls[provider]['cost'] += total_cost

        logger.debug(
            f"Geocoding tracked: {provider} "
            f"({count} requests, ${total_cost:.6f})"
        )

        return total_cost

    def get_cost_report(self) -> Dict[str, Any]:
        """
        Get comprehensive cost report.

        Returns:
            Dict with cost breakdown:
            {
                'llm_costs': {
                    'by_model': {
                        'gemini-2.5-flash-lite': {
                            'calls': 100,
                            'tokens': 50000,
                            'cost': 0.0
                        }
                    },
                    'total_calls': 100,
                    'total_tokens': 50000,
                    'total_cost': 0.0
                },
                'geocoding_costs': {
                    'by_provider': {
                        'nominatim': {'requests': 90, 'cost': 0.0},
                        'google': {'requests': 10, 'cost': 0.05}
                    },
                    'total_requests': 100,
                    'total_cost': 0.05
                },
                'grand_total': 0.05,
                'duration_seconds': 120.5,
                'generated_at': '2025-12-09T...'
            }

        Example:
            >>> report = tracker.get_cost_report()
            >>> print(json.dumps(report, indent=2))
        """
        # Calculate LLM totals
        llm_total_calls = sum(stats['calls'] for stats in self.llm_calls.values())
        llm_total_tokens = sum(stats['total_tokens'] for stats in self.llm_calls.values())
        llm_total_cost = sum(stats['cost'] for stats in self.llm_calls.values())

        # Calculate geocoding totals
        geocoding_total_requests = sum(stats['requests'] for stats in self.geocoding_calls.values())
        geocoding_total_cost = sum(stats['cost'] for stats in self.geocoding_calls.values())

        # Grand total
        grand_total = llm_total_cost + geocoding_total_cost

        # Duration
        duration_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

        return {
            'llm_costs': {
                'by_model': self.llm_calls,
                'total_calls': llm_total_calls,
                'total_tokens': llm_total_tokens,
                'total_cost': llm_total_cost
            },
            'geocoding_costs': {
                'by_provider': self.geocoding_calls,
                'total_requests': geocoding_total_requests,
                'total_cost': geocoding_total_cost
            },
            'grand_total': grand_total,
            'duration_seconds': duration_seconds,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }

    def print_cost_report(self) -> None:
        """
        Print formatted cost report to console.

        Example:
            >>> tracker.print_cost_report()
            ================================================================================
            COST REPORT - Stage 3 Processing
            ================================================================================
            ...
        """
        report = self.get_cost_report()

        print("\n" + "=" * 80)
        print("COST REPORT - Stage 3 Processing")
        print("=" * 80)

        # LLM Costs
        print("\n💬 LLM API COSTS:")
        if report['llm_costs']['by_model']:
            for model, stats in report['llm_costs']['by_model'].items():
                is_free = LLM_COSTS.get(model, {}).get('free_tier', False)
                free_tag = " (FREE TIER)" if is_free else ""
                print(f"   {model}{free_tag}:")
                print(f"      Calls: {stats['calls']}")
                print(f"      Tokens: {stats['total_tokens']:,} ({stats['input_tokens']:,} in + {stats['output_tokens']:,} out)")
                print(f"      Cost: ${stats['cost']:.6f}")
            print(f"\n   TOTAL LLM:")
            print(f"      Calls: {report['llm_costs']['total_calls']}")
            print(f"      Tokens: {report['llm_costs']['total_tokens']:,}")
            print(f"      Cost: ${report['llm_costs']['total_cost']:.6f}")
        else:
            print("   No LLM calls tracked")

        # Geocoding Costs
        print("\n🌍 GEOCODING COSTS:")
        if report['geocoding_costs']['by_provider']:
            for provider, stats in report['geocoding_costs']['by_provider'].items():
                is_free = provider == 'nominatim'
                free_tag = " (FREE)" if is_free else " (PAID)"
                print(f"   {provider.title()}{free_tag}:")
                print(f"      Requests: {stats['requests']}")
                print(f"      Cost: ${stats['cost']:.6f}")
            print(f"\n   TOTAL GEOCODING:")
            print(f"      Requests: {report['geocoding_costs']['total_requests']}")
            print(f"      Cost: ${report['geocoding_costs']['total_cost']:.6f}")
        else:
            print("   No geocoding calls tracked")

        # Grand Total
        print("\n" + "=" * 80)
        print(f"💰 GRAND TOTAL: ${report['grand_total']:.6f}")
        print(f"⏱️  Duration: {report['duration_seconds']:.1f} seconds")
        print("=" * 80 + "\n")

    def save_cost_report(self, output_path: str) -> bool:
        """
        Save cost report to JSON file.

        Args:
            output_path: Path to save report (e.g., 'data/cost_report.json')

        Returns:
            True if saved successfully, False otherwise

        Example:
            >>> tracker.save_cost_report('data/cost_report.json')
            True
        """
        try:
            report = self.get_cost_report()

            # Ensure directory exists
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Save report
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.info(f"Cost report saved to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save cost report: {e}")
            return False

    def check_budget_warning(self, budget_usd: float) -> bool:
        """
        Check if costs are approaching or exceeding budget.

        Args:
            budget_usd: Budget threshold in USD

        Returns:
            True if budget exceeded, False otherwise

        Example:
            >>> if tracker.check_budget_warning(1.0):
            ...     print("WARNING: Budget exceeded!")
        """
        report = self.get_cost_report()
        total_cost = report['grand_total']

        if total_cost >= budget_usd:
            logger.warning(f"⚠️  BUDGET EXCEEDED: ${total_cost:.6f} >= ${budget_usd:.6f}")
            return True
        elif total_cost >= budget_usd * 0.8:
            logger.warning(f"⚠️  APPROACHING BUDGET: ${total_cost:.6f} / ${budget_usd:.6f} (80%+)")
            return False
        else:
            return False


# =============================================================================
# Global Tracker Instance
# =============================================================================

_global_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """
    Get global cost tracker instance.

    Returns:
        Global CostTracker instance

    Example:
        >>> tracker = get_cost_tracker()
        >>> tracker.track_llm_call(1000, 500, 'gemini-2.5-flash-lite')
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker


def reset_cost_tracker() -> None:
    """
    Reset global cost tracker.

    Example:
        >>> reset_cost_tracker()  # Start fresh tracking
    """
    global _global_tracker
    _global_tracker = CostTracker()
    logger.info("Cost tracker reset")


# =============================================================================
# Convenience Functions
# =============================================================================

def track_llm_call(input_tokens: int, output_tokens: int, model: str) -> float:
    """
    Track LLM call using global tracker.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name

    Returns:
        Cost in USD

    Example:
        >>> from src.utils.cost_tracker import track_llm_call
        >>> cost = track_llm_call(1000, 500, 'gemini-2.5-flash-lite')
    """
    return get_cost_tracker().track_llm_call(input_tokens, output_tokens, model)


def track_geocoding(provider: str, count: int = 1) -> float:
    """
    Track geocoding call using global tracker.

    Args:
        provider: 'nominatim' or 'google'
        count: Number of requests

    Returns:
        Cost in USD

    Example:
        >>> from src.utils.cost_tracker import track_geocoding
        >>> cost = track_geocoding('google', 10)
    """
    return get_cost_tracker().track_geocoding(provider, count)


def get_cost_report() -> Dict[str, Any]:
    """
    Get cost report from global tracker.

    Returns:
        Cost report dict

    Example:
        >>> from src.utils.cost_tracker import get_cost_report
        >>> report = get_cost_report()
        >>> print(f"Total: ${report['grand_total']:.6f}")
    """
    return get_cost_tracker().get_cost_report()


def print_cost_report() -> None:
    """
    Print cost report from global tracker.

    Example:
        >>> from src.utils.cost_tracker import print_cost_report
        >>> print_cost_report()
    """
    get_cost_tracker().print_cost_report()


# =============================================================================
# Test Function
# =============================================================================

if __name__ == '__main__':
    """Test cost tracker with sample calls."""
    print("Testing Cost Tracker...")

    tracker = CostTracker()

    # Test LLM calls
    print("\n1. Tracking LLM calls...")
    tracker.track_llm_call(1000, 500, 'gemini-2.5-flash-lite')
    tracker.track_llm_call(2000, 1000, 'gemini-1.5-flash')
    tracker.track_llm_call(5000, 3000, 'gpt-4o-mini')

    # Test geocoding
    print("\n2. Tracking geocoding...")
    tracker.track_geocoding('nominatim', 90)
    tracker.track_geocoding('google', 10)

    # Print report
    print("\n3. Cost Report:")
    tracker.print_cost_report()

    # Save report
    print("\n4. Saving report...")
    tracker.save_cost_report('data/test_cost_report.json')

    # Budget check
    print("\n5. Budget check...")
    tracker.check_budget_warning(0.10)

    print("\n✅ Test complete!")
