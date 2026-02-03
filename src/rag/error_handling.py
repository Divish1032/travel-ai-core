#!/usr/bin/env python3
"""
RAG Error Handling - Graceful Degradation and User-Friendly Messages

Handles edge cases in the RAG pipeline with graceful degradation:
- Insufficient data for destination
- Validation failures
- LLM API failures
- Budget constraints
- Profile mismatches

Features:
- Custom exception hierarchy
- Automatic retry logic
- Graceful degradation strategies
- User-friendly error messages
- Alternative suggestions

Author: TravelAI Team
Date: 2025-12-20
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from src.utils.logging import get_logger
from src.utils.schemas import (
    UserIntent,
    GeneratedItinerary,
    ValidationReport,
    RetrievalCandidate
)

logger = get_logger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class RAGException(Exception):
    """Base exception for RAG pipeline errors."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InsufficientDataError(RAGException):
    """Raised when not enough entities for destination/profile."""
    pass


class ValidationError(RAGException):
    """Raised when generated itinerary failed validation."""
    pass


class BudgetExceededError(RAGException):
    """Raised when itinerary exceeds user's budget constraints."""
    pass


class LLMError(RAGException):
    """Raised when LLM generation fails."""
    pass


class ProfileMismatchError(RAGException):
    """Raised when no data for traveler profile in destination."""
    pass


class DurationError(RAGException):
    """Raised when duration is impossible for destination."""
    pass


# =============================================================================
# Error Response Dataclass
# =============================================================================

@dataclass
class ErrorResponse:
    """Structured error response."""
    status: str  # 'error', 'partial', 'degraded'
    error_type: str
    message: str
    user_message: str
    suggestions: List[str]
    partial_result: Optional[Any] = None
    details: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'status': self.status,
            'error_type': self.error_type,
            'message': self.message,
            'user_message': self.user_message,
            'suggestions': self.suggestions,
            'partial_result': self.partial_result,
            'details': self.details or {}
        }


# =============================================================================
# User-Friendly Error Messages
# =============================================================================

ERROR_MESSAGES = {
    'insufficient_data': (
        "We don't have enough traveler experiences for {destination} yet. "
        "We found only {count} relevant places, but need at least {min_count} "
        "for a quality {duration}-day itinerary."
    ),
    'budget_impossible': (
        "Your budget of ${budget:.0f}/day is too tight for {destination}. "
        "Based on traveler data, the minimum recommended budget is ${min_budget:.0f}/day. "
        "Consider increasing your budget or choosing a more budget-friendly destination."
    ),
    'no_match_profile': (
        "We don't have enough data for {profile} travelers in {destination}. "
        "Try adjusting your traveler type or interests."
    ),
    'duration_too_long': (
        "A {duration}-day trip to {destination} is too long based on available attractions. "
        "We recommend {max_duration} days for a complete experience without repetition."
    ),
    'duration_too_short': (
        "A {duration}-day trip to {destination} is too short to experience the highlights. "
        "We recommend at least {min_duration} days."
    ),
    'llm_failure': (
        "Our AI service is temporarily unavailable. Please try again in a few moments. "
        "If the problem persists, contact support."
    ),
    'validation_failed': (
        "The generated itinerary has some quality issues. "
        "We're showing you the best version we could create, but please review carefully."
    ),
    'unknown_destination': (
        "We don't have data for '{destination}'. "
        "Did you mean one of these: {alternatives}?"
    ),
    'api_rate_limit': (
        "We're experiencing high demand. Please wait {wait_time} seconds and try again."
    )
}


def get_user_message(error_type: str, **kwargs) -> str:
    """
    Get user-friendly error message.

    Args:
        error_type: Type of error
        **kwargs: Template variables

    Returns:
        Formatted user-friendly message
    """
    template = ERROR_MESSAGES.get(error_type, "An error occurred: {error}")
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing template variable: {e}")
        return "An error occurred. Please try again."


# =============================================================================
# Error Handlers
# =============================================================================

class RAGErrorHandler:
    """
    Centralized error handling for RAG pipeline.

    Provides graceful degradation, retry logic, and user-friendly responses.
    """

    def __init__(self):
        self.retry_count = {}
        self.max_retries = 3
        self.base_retry_delay = 2.0

    def handle_insufficient_data(
        self,
        intent: UserIntent,
        candidates: List[RetrievalCandidate],
        min_required: int = 5
    ) -> ErrorResponse:
        """
        Handle case where not enough data available.

        Args:
            intent: User intent
            candidates: Retrieved candidates
            min_required: Minimum required entities

        Returns:
            ErrorResponse with suggestions
        """
        count = len(candidates)

        logger.warning(
            f"Insufficient data for {intent.destination}: "
            f"{count} entities found (need {min_required})"
        )

        # Generate suggestions
        suggestions = []

        # Suggestion 1: Shorter duration
        if intent.duration_days > 2:
            suggestions.append(
                f"Try a shorter trip ({intent.duration_days - 1} days)"
            )

        # Suggestion 2: Broader interests
        if len(intent.interests) > 2:
            suggestions.append("Broaden your interests (remove specific requirements)")

        # Suggestion 3: Different budget tier
        if intent.traveler_profile.budget_tier == 'budget':
            suggestions.append("Try 'mid-range' budget tier (more data available)")

        # Suggestion 4: Alternative destinations
        alternatives = self._find_alternative_destinations(intent)
        if alternatives:
            suggestions.append(f"Try nearby destinations: {', '.join(alternatives[:3])}")

        user_message = get_user_message(
            'insufficient_data',
            destination=intent.destination,
            count=count,
            min_count=min_required,
            duration=intent.duration_days
        )

        return ErrorResponse(
            status='error',
            error_type='insufficient_data',
            message=f"Only {count} entities found for {intent.destination}",
            user_message=user_message,
            suggestions=suggestions,
            details={
                'destination': intent.destination,
                'entities_found': count,
                'min_required': min_required,
                'alternatives': alternatives
            }
        )

    def handle_validation_failure(
        self,
        itinerary: GeneratedItinerary,
        report: ValidationReport,
        intent: UserIntent
    ) -> ErrorResponse:
        """
        Handle invalid itinerary with partial results.

        Args:
            itinerary: Generated itinerary (may be invalid)
            report: Validation report
            intent: User intent

        Returns:
            ErrorResponse with partial itinerary
        """
        critical_issues = [
            issue for issue in report.issues
            if issue.severity == 'error'
        ]

        logger.warning(
            f"Validation failed: {len(critical_issues)} critical issues, "
            f"score: {report.overall_score:.2f}"
        )

        # Generate suggestions based on issues
        suggestions = []

        # Check for common issues
        hallucination_count = sum(
            1 for i in critical_issues
            if 'hallucination' in i.issue_type.lower()
        )

        if hallucination_count > 5:
            suggestions.append(
                "Try a different destination with more data available"
            )

        budget_issues = sum(
            1 for i in critical_issues
            if 'budget' in i.issue_type.lower()
        )

        if budget_issues > 0:
            suggestions.append(
                f"Increase your budget (current: ${intent.budget_per_day.get('max', 0):.0f}/day)"
            )

        if report.overall_score < 0.5:
            suggestions.append(
                "This destination may not match your requirements well"
            )

        user_message = get_user_message('validation_failed')

        return ErrorResponse(
            status='partial',
            error_type='validation_failed',
            message=f"Validation failed with {len(critical_issues)} critical issues",
            user_message=user_message,
            suggestions=suggestions,
            partial_result=itinerary,
            details={
                'validation_score': report.overall_score,
                'critical_issues': len(critical_issues),
                'total_issues': len(report.issues),
                'top_issues': [i.description for i in critical_issues[:3]]
            }
        )

    def handle_llm_failure(
        self,
        phase: str,
        error: Exception,
        retry_context: Optional[str] = None
    ) -> ErrorResponse:
        """
        Handle LLM API failures with retry logic.

        Args:
            phase: Pipeline phase that failed
            error: Exception raised
            retry_context: Optional context for retry tracking

        Returns:
            ErrorResponse with retry action or final failure
        """
        context_key = retry_context or phase
        retry_count = self.retry_count.get(context_key, 0)

        logger.error(
            f"LLM failure in {phase} (attempt {retry_count + 1}/{self.max_retries}): {error}"
        )

        # Check if should retry
        if retry_count < self.max_retries - 1:
            # Retry with exponential backoff
            delay = self.base_retry_delay * (2 ** retry_count)
            self.retry_count[context_key] = retry_count + 1

            logger.info(f"Retrying after {delay}s...")
            time.sleep(delay)

            return ErrorResponse(
                status='retry',
                error_type='llm_failure',
                message=f"Retrying {phase} after {delay}s",
                user_message="Processing... please wait",
                suggestions=[],
                details={
                    'retry_count': retry_count + 1,
                    'max_retries': self.max_retries,
                    'retry_delay': delay
                }
            )
        else:
            # Final failure
            self.retry_count[context_key] = 0  # Reset for next time

            # Check if rate limit error
            if 'rate limit' in str(error).lower() or '429' in str(error):
                user_message = get_user_message(
                    'api_rate_limit',
                    wait_time=60
                )
                suggestions = ["Wait 1 minute and try again"]
            else:
                user_message = get_user_message('llm_failure')
                suggestions = [
                    "Try again in a few moments",
                    "Contact support if the problem persists"
                ]

            return ErrorResponse(
                status='error',
                error_type='llm_failure',
                message=f"LLM failed in {phase} after {self.max_retries} attempts",
                user_message=user_message,
                suggestions=suggestions,
                details={
                    'phase': phase,
                    'error': str(error),
                    'retries': self.max_retries
                }
            )

    def handle_budget_exceeded(
        self,
        intent: UserIntent,
        estimated_budget: float
    ) -> ErrorResponse:
        """
        Handle case where itinerary exceeds budget.

        Args:
            intent: User intent with budget constraints
            estimated_budget: Estimated minimum budget

        Returns:
            ErrorResponse with budget suggestions
        """
        user_budget = intent.budget_per_day.get('max', 0)

        logger.warning(
            f"Budget exceeded: user ${user_budget:.0f}/day, "
            f"estimated ${estimated_budget:.0f}/day"
        )

        suggestions = [
            f"Increase your budget to ${estimated_budget:.0f}/day",
            "Try a more budget-friendly destination",
            "Reduce trip duration to save costs",
            "Focus on free/cheap activities"
        ]

        user_message = get_user_message(
            'budget_impossible',
            budget=user_budget,
            destination=intent.destination,
            min_budget=estimated_budget
        )

        return ErrorResponse(
            status='error',
            error_type='budget_exceeded',
            message=f"Budget ${user_budget:.0f}/day too low (need ${estimated_budget:.0f}/day)",
            user_message=user_message,
            suggestions=suggestions,
            details={
                'user_budget': user_budget,
                'min_budget': estimated_budget,
                'budget_gap': estimated_budget - user_budget
            }
        )

    def _find_alternative_destinations(
        self,
        intent: UserIntent,
        max_alternatives: int = 5
    ) -> List[str]:
        """
        Find alternative destinations with more data.

        Args:
            intent: User intent
            max_alternatives: Maximum alternatives to return

        Returns:
            List of alternative destination names
        """
        # Common alternatives by region
        ALTERNATIVES = {
            'Bangkok': ['Chiang Mai', 'Phuket', 'Pattaya', 'Ayutthaya', 'Krabi'],
            'Phuket': ['Krabi', 'Koh Samui', 'Bangkok', 'Chiang Mai'],
            'Chiang Mai': ['Bangkok', 'Pai', 'Chiang Rai', 'Sukhothai'],
            'Koh Samui': ['Phuket', 'Krabi', 'Koh Phangan', 'Koh Tao'],
            'Krabi': ['Phuket', 'Koh Samui', 'Koh Lanta', 'Railay'],
            'Pattaya': ['Bangkok', 'Koh Samet', 'Rayong', 'Hua Hin']
        }

        alternatives = ALTERNATIVES.get(intent.destination, [])
        return alternatives[:max_alternatives]


# =============================================================================
# Graceful Degradation Strategies
# =============================================================================

class DegradationStrategy:
    """
    Strategies for graceful degradation when full pipeline fails.
    """

    @staticmethod
    def relax_quality_threshold(min_rating: float = 3.0) -> float:
        """Lower quality threshold to get more results."""
        return max(2.0, min_rating - 1.0)

    @staticmethod
    def reduce_duration(intent: UserIntent, reduction: int = 1) -> UserIntent:
        """Reduce trip duration to need fewer entities."""
        intent.duration_days = max(1, intent.duration_days - reduction)
        return intent

    @staticmethod
    def broaden_interests(intent: UserIntent) -> UserIntent:
        """Remove specific interests to get broader results."""
        if len(intent.interests) > 1:
            intent.interests = intent.interests[:1]  # Keep only first interest
        return intent

    @staticmethod
    def adjust_budget_tier(intent: UserIntent) -> UserIntent:
        """Adjust budget tier to access more data."""
        tier_upgrades = {
            'budget': 'mid-range',
            'mid-range': 'luxury',
            'luxury': 'mid-range'  # Downgrade from luxury
        }

        current_tier = intent.traveler_profile.budget_tier
        new_tier = tier_upgrades.get(current_tier, 'mid-range')
        intent.traveler_profile.budget_tier = new_tier

        return intent


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    from src.utils.schemas import UserIntent, TravelerProfileInput

    print("=" * 70)
    print("RAG Error Handling Test")
    print("=" * 70)

    # Initialize handler
    handler = RAGErrorHandler()

    # Test 1: Insufficient data
    print("\n1. Testing insufficient data error...")
    intent = UserIntent(
        destination="Obscure Village",
        duration_days=5,
        traveler_profile=TravelerProfileInput(
            traveler_type='solo',
            budget_tier='budget'
        ),
        interests=['hiking', 'temples']
    )

    response = handler.handle_insufficient_data(intent, candidates=[], min_required=5)
    print(f"\nStatus: {response.status}")
    print(f"User message: {response.user_message}")
    print("Suggestions:")
    for i, s in enumerate(response.suggestions, 1):
        print(f"  {i}. {s}")

    # Test 2: Budget exceeded
    print("\n2. Testing budget exceeded error...")
    response = handler.handle_budget_exceeded(intent, estimated_budget=100)
    print(f"\nStatus: {response.status}")
    print(f"User message: {response.user_message}")

    # Test 3: LLM failure with retry
    print("\n3. Testing LLM failure with retry...")
    response = handler.handle_llm_failure(
        phase='generation',
        error=Exception("API timeout"),
        retry_context='test_generation'
    )
    print(f"\nStatus: {response.status}")
    print(f"Message: {response.message}")

    print("\n" + "=" * 70)
