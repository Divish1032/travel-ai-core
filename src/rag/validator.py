#!/usr/bin/env python3
"""
RAG Itinerary Validator - Quality Assurance and Hallucination Prevention

Validates generated itineraries across multiple dimensions to ensure accuracy,
feasibility, and practical usability. Critical safety net for production deployment.

Validation Checks:
1. No hallucinations (entities exist in source data)
2. Logistics feasibility (distances, timing, activity durations)
3. Budget compliance (within user constraints)
4. Geographic sensibility (efficient routing, no ping-ponging)
5. Data quality & confidence (sufficient evidence)
6. Constraint compliance (must-include, must-avoid)

Features:
- Comprehensive multi-dimensional validation
- Automatic issue fixing where possible
- Quality scoring
- Improvement suggestions

Author: TravelAI Team
Date: 2025-12-20
"""

import re
import math
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter, defaultdict

from src.utils.logging import get_logger
from src.utils.schemas import (
    GeneratedItinerary,
    ItineraryDay,
    TimeSlot,
    RAGContext,
    UserIntent,
    ValidationReport,
    ValidationIssue,
    ValidationSeverity,
    ValidationType
)

logger = get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Thresholds
MAX_DAILY_DISTANCE_KM = 20.0        # >20km walking = unrealistic
MAX_ACTIVITY_DURATION_HOURS = 8.0  # Single activity >8 hours = unrealistic
MIN_ACCEPTABLE_CONFIDENCE = 0.6     # Below 0.6 = low quality data
MAX_ACTIVITIES_PER_DAY = 4          # More than 4 = rushed

# Severity penalties for scoring
SEVERITY_PENALTIES = {
    ValidationSeverity.ERROR: 0.15,
    ValidationSeverity.WARNING: 0.05,
    ValidationSeverity.INFO: 0.01
}


# =============================================================================
# Helper Functions
# =============================================================================

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    R = 6371  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def parse_duration_to_hours(duration_str: str) -> float:
    """
    Parse duration string to hours.

    Args:
        duration_str: Duration like "2-3 hours", "1 hour", "30 minutes"

    Returns:
        Average duration in hours
    """
    if not duration_str:
        return 2.0  # Default 2 hours

    # Extract numbers
    numbers = re.findall(r'\d+', duration_str)

    if not numbers:
        return 2.0

    # Check if minutes
    if 'minute' in duration_str.lower() or 'min' in duration_str.lower():
        if len(numbers) >= 2:
            avg_minutes = (float(numbers[0]) + float(numbers[1])) / 2
        else:
            avg_minutes = float(numbers[0])
        return avg_minutes / 60.0

    # Hours
    if len(numbers) >= 2:
        return (float(numbers[0]) + float(numbers[1])) / 2
    else:
        return float(numbers[0])


def parse_cost_string(cost_str: str) -> Dict[str, float]:
    """
    Parse cost string to min/max values.

    Args:
        cost_str: Cost like "$10-15", "$20", "Varies"

    Returns:
        Dictionary with 'min' and 'max' keys
    """
    if not cost_str or cost_str.lower() == 'varies':
        return {'min': 0.0, 'max': 0.0}

    # Remove currency symbols
    cost_str = cost_str.replace("$", "").replace(" ", "").replace(",", "")

    # Try to find range
    if "-" in cost_str:
        parts = cost_str.split("-")
        try:
            return {
                'min': float(parts[0]),
                'max': float(parts[1])
            }
        except (ValueError, IndexError):
            pass

    # Single value
    try:
        value = float(cost_str)
        return {'min': value, 'max': value}
    except ValueError:
        return {'min': 0.0, 'max': 0.0}


# =============================================================================
# ItineraryValidator Class
# =============================================================================

class ItineraryValidator:
    """
    Validate generated itineraries for accuracy and feasibility.

    Performs comprehensive validation across multiple dimensions:
    - Hallucination detection
    - Logistics validation
    - Budget compliance
    - Geographic sensibility
    - Data quality checks
    - Constraint compliance

    Example:
        >>> validator = ItineraryValidator()
        >>> report = validator.validate_itinerary(itinerary, context)
        >>> report.is_valid
        True
        >>> report.overall_score
        0.92
    """

    def __init__(self):
        """Initialize validator."""
        logger.info("ItineraryValidator initialized")

    def validate_itinerary(
        self,
        itinerary: GeneratedItinerary,
        rag_context: RAGContext,
        user_intent: Optional[UserIntent] = None
    ) -> ValidationReport:
        """
        Comprehensive validation of generated itinerary.

        Args:
            itinerary: Generated itinerary to validate
            rag_context: RAG context used for generation
            user_intent: Optional user intent for constraint checking

        Returns:
            Complete validation report
        """
        logger.info("=" * 80)
        logger.info("🔍 VALIDATING ITINERARY")
        logger.info("=" * 80)
        logger.info(f"Destination: {itinerary.destination}")
        logger.info(f"Duration: {itinerary.duration_days} days")

        all_issues = []

        # CHECK 1: No Hallucinations
        logger.info("\n✓ Check 1: Hallucination detection...")
        no_hallucinations, h_issues = self.validate_no_hallucinations(itinerary, rag_context)
        all_issues.extend(h_issues)
        logger.info(f"   Found {len(h_issues)} hallucination issues")

        # CHECK 2: Logistics Feasibility
        logger.info("\n✓ Check 2: Logistics feasibility...")
        l_issues = self.validate_logistics(itinerary)
        all_issues.extend(l_issues)
        logger.info(f"   Found {len(l_issues)} logistics issues")

        # CHECK 3: Budget Compliance
        if user_intent and user_intent.budget_per_day:
            logger.info("\n✓ Check 3: Budget compliance...")
            b_issues = self.validate_budget(itinerary, user_intent)
            all_issues.extend(b_issues)
            logger.info(f"   Found {len(b_issues)} budget issues")
        else:
            b_issues = []
            logger.info("\n✓ Check 3: Budget compliance (skipped - no budget set)")

        # CHECK 4: Geographic Sensibility
        logger.info("\n✓ Check 4: Geographic sensibility...")
        g_issues = self.validate_geography(itinerary)
        all_issues.extend(g_issues)
        logger.info(f"   Found {len(g_issues)} geography issues")

        # CHECK 5: Data Quality & Confidence
        logger.info("\n✓ Check 5: Data quality & confidence...")
        c_issues = self.validate_confidence(itinerary)
        all_issues.extend(c_issues)
        logger.info(f"   Found {len(c_issues)} confidence issues")

        # CHECK 6: Constraint Compliance
        if user_intent:
            logger.info("\n✓ Check 6: Constraint compliance...")
            cons_issues = self.validate_constraints(itinerary, user_intent)
            all_issues.extend(cons_issues)
            logger.info(f"   Found {len(cons_issues)} constraint issues")
        else:
            cons_issues = []
            logger.info("\n✓ Check 6: Constraint compliance (skipped - no intent)")

        # Compile report
        error_count = len([i for i in all_issues if i.severity == ValidationSeverity.ERROR])
        warning_count = len([i for i in all_issues if i.severity == ValidationSeverity.WARNING])

        report = ValidationReport(
            is_valid=error_count == 0,
            overall_score=self.calculate_validation_score(all_issues),
            issues=sorted(all_issues, key=lambda x: self._severity_order(x.severity)),
            no_hallucinations=no_hallucinations,
            logistics_feasible=len([i for i in l_issues if i.severity == ValidationSeverity.ERROR]) == 0,
            budget_compliant=len([i for i in b_issues if i.severity == ValidationSeverity.ERROR]) == 0,
            timing_realistic=len([i for i in l_issues if i.type == ValidationType.TIMING and i.severity == ValidationSeverity.ERROR]) == 0,
            improvement_suggestions=self.suggest_improvements(itinerary, all_issues)
        )

        # Determine if regeneration needed
        report.regeneration_needed = error_count > 2 or not report.is_valid

        logger.info("\n" + "=" * 80)
        logger.info("✅ VALIDATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Valid: {report.is_valid}")
        logger.info(f"Score: {report.overall_score:.2f}")
        logger.info(f"Issues: {error_count} errors, {warning_count} warnings")
        logger.info(f"Regeneration needed: {report.regeneration_needed}")

        return report

    def validate_no_hallucinations(
        self,
        itinerary: GeneratedItinerary,
        rag_context: RAGContext
    ) -> Tuple[bool, List[ValidationIssue]]:
        """
        Validate that all entities exist in source data.

        Args:
            itinerary: Generated itinerary
            rag_context: RAG context with source entities

        Returns:
            Tuple of (no_hallucinations_bool, list_of_issues)
        """
        issues = []

        # Build set of valid entity IDs
        valid_entity_ids = set()
        for entity in rag_context.priority_entities + rag_context.supporting_entities + rag_context.background_entities:
            if isinstance(entity, dict):
                valid_entity_ids.add(entity.get('entity_id', ''))

        # Check every time slot
        for day in itinerary.days:
            for slot in day.get_time_slots():
                if slot.entity_id not in valid_entity_ids:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        type=ValidationType.HALLUCINATION,
                        description=f"Entity '{slot.entity_name}' (ID: {slot.entity_id}) not in source data",
                        affected_day=day.day_number,
                        affected_entity=slot.entity_id,
                        suggested_fix="Remove or replace with valid entity from source data"
                    ))

        return len(issues) == 0, issues

    def validate_logistics(self, itinerary: GeneratedItinerary) -> List[ValidationIssue]:
        """
        Validate logistics feasibility (distances, timing, durations).

        Args:
            itinerary: Generated itinerary

        Returns:
            List of validation issues
        """
        issues = []

        for day in itinerary.days:
            # Check 1: Total distance per day
            if day.total_distance_km > MAX_DAILY_DISTANCE_KM:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    type=ValidationType.LOGISTICS,
                    description=f"Day {day.day_number}: {day.total_distance_km:.1f}km total - too much travel",
                    affected_day=day.day_number,
                    suggested_fix="Group geographically close activities or reduce number of stops"
                ))

            # Check 2: Activity durations
            for slot in day.get_time_slots():
                if slot.estimated_duration:
                    hours = parse_duration_to_hours(slot.estimated_duration)
                    if hours > MAX_ACTIVITY_DURATION_HOURS:
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            type=ValidationType.TIMING,
                            description=f"Activity '{slot.entity_name}' duration ({hours:.1f}h) seems too long",
                            affected_day=day.day_number,
                            affected_entity=slot.entity_id,
                            suggested_fix="Split into multiple time slots or reduce duration"
                        ))

            # Check 3: Number of activities per day
            activity_count = len(day.get_time_slots())
            if activity_count > MAX_ACTIVITIES_PER_DAY:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    type=ValidationType.FEASIBILITY,
                    description=f"Day {day.day_number}: {activity_count} activities may be too rushed",
                    affected_day=day.day_number,
                    suggested_fix="Reduce to 3-4 activities per day for better pacing"
                ))

        return issues

    def validate_budget(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent
    ) -> List[ValidationIssue]:
        """
        Validate budget compliance.

        Args:
            itinerary: Generated itinerary
            user_intent: User intent with budget constraints

        Returns:
            List of validation issues
        """
        issues = []

        if not user_intent.budget_per_day:
            return issues

        budget_max = user_intent.budget_per_day.get('max', float('inf'))

        for day in itinerary.days:
            daily_cost = self.calculate_daily_cost(day)

            # Error if exceeds budget
            if daily_cost['max'] > budget_max:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    type=ValidationType.BUDGET,
                    description=f"Day {day.day_number}: ${daily_cost['max']:.0f} exceeds budget ${budget_max:.0f}",
                    affected_day=day.day_number,
                    suggested_fix="Replace expensive activities with budget alternatives"
                ))

            # Warning if cutting it close (>90% of budget)
            elif daily_cost['min'] > budget_max * 0.9:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    type=ValidationType.BUDGET,
                    description=f"Day {day.day_number}: Minimal budget wiggle room (${daily_cost['min']:.0f} of ${budget_max:.0f})",
                    affected_day=day.day_number,
                    suggested_fix="Consider leaving buffer for unexpected costs"
                ))

        return issues

    def validate_geography(self, itinerary: GeneratedItinerary) -> List[ValidationIssue]:
        """
        Validate geographic sensibility (efficient routing, no ping-ponging).

        Args:
            itinerary: Generated itinerary

        Returns:
            List of validation issues
        """
        issues = []

        if len(itinerary.days) < 3:
            return issues  # Need at least 3 days to detect ping-ponging

        # Check for ping-ponging between areas
        for i in range(1, len(itinerary.days) - 1):
            prev_day = itinerary.days[i - 1]
            curr_day = itinerary.days[i]
            next_day = itinerary.days[i + 1]

            prev_cluster = self._get_geographic_cluster(prev_day)
            curr_cluster = self._get_geographic_cluster(curr_day)
            next_cluster = self._get_geographic_cluster(next_day)

            # Pattern: Area A → Area B → Area A (inefficient)
            if prev_cluster and next_cluster and prev_cluster == next_cluster and curr_cluster != prev_cluster:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    type=ValidationType.LOGISTICS,
                    description=f"Days {i}-{i+2}: Inefficient routing (visiting {curr_cluster} between {prev_cluster} visits)",
                    suggested_fix=f"Regroup activities - visit {prev_cluster} on consecutive days"
                ))

        return issues

    def validate_confidence(self, itinerary: GeneratedItinerary) -> List[ValidationIssue]:
        """
        Validate data quality and confidence levels.

        Args:
            itinerary: Generated itinerary

        Returns:
            List of validation issues
        """
        issues = []

        # Overall confidence check
        if itinerary.overall_confidence < MIN_ACCEPTABLE_CONFIDENCE:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                type=ValidationType.DATA_QUALITY,
                description=f"Low overall confidence ({itinerary.overall_confidence:.2f}) - limited traveler data",
                suggested_fix="Add disclaimer about limited data coverage"
            ))

        # Per-day confidence
        for day in itinerary.days:
            if day.confidence_score < 0.5:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    type=ValidationType.DATA_QUALITY,
                    description=f"Day {day.day_number}: Low confidence ({day.confidence_score:.2f})",
                    affected_day=day.day_number,
                    suggested_fix="Fewer traveler experiences available for these places"
                ))

        return issues

    def validate_constraints(
        self,
        itinerary: GeneratedItinerary,
        user_intent: UserIntent
    ) -> List[ValidationIssue]:
        """
        Validate constraint compliance (must-include, must-avoid).

        Args:
            itinerary: Generated itinerary
            user_intent: User intent with constraints

        Returns:
            List of validation issues
        """
        issues = []

        # Check must_include
        for must_include in user_intent.must_include:
            if not self._any_entity_matches(itinerary, must_include):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    type=ValidationType.FEASIBILITY,
                    description=f"Required place '{must_include}' not included in itinerary",
                    suggested_fix=f"Add {must_include} to the itinerary"
                ))

        # Check must_avoid
        for must_avoid in user_intent.must_avoid:
            if self._any_entity_matches(itinerary, must_avoid):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    type=ValidationType.FEASIBILITY,
                    description=f"Forbidden place '{must_avoid}' is included in itinerary",
                    suggested_fix=f"Remove {must_avoid} from the itinerary"
                ))

        return issues

    def calculate_daily_cost(self, day: ItineraryDay) -> Dict[str, float]:
        """
        Calculate total cost for a day.

        Args:
            day: Itinerary day

        Returns:
            Dictionary with 'min' and 'max' costs
        """
        min_total = 0.0
        max_total = 0.0

        for slot in day.get_time_slots():
            if slot.estimated_cost:
                cost = parse_cost_string(slot.estimated_cost)
                min_total += cost['min']
                max_total += cost['max']

        return {'min': min_total, 'max': max_total}

    def calculate_validation_score(self, issues: List[ValidationIssue]) -> float:
        """
        Calculate numerical quality score from issues.

        Args:
            issues: List of validation issues

        Returns:
            Score from 0.0 to 1.0 (higher is better)
        """
        score = 1.0

        for issue in issues:
            penalty = SEVERITY_PENALTIES.get(issue.severity, 0.01)
            score -= penalty

        return max(0.0, score)

    def suggest_improvements(
        self,
        itinerary: GeneratedItinerary,
        issues: List[ValidationIssue]
    ) -> List[str]:
        """
        Suggest improvements even for valid itineraries.

        Args:
            itinerary: Generated itinerary
            issues: Validation issues found

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Diversity check
        all_types = [
            slot.entity_type
            for day in itinerary.days
            for slot in day.get_time_slots()
        ]

        if all_types:
            type_counts = Counter(all_types)

            # Too many of one type
            for entity_type, count in type_counts.most_common(1):
                if count / len(all_types) > 0.4:
                    suggestions.append(
                        f"Consider more variety - {count}/{len(all_types)} activities are {entity_type}s"
                    )

        # Pace check
        if itinerary.days:
            avg_activities = sum(len(day.get_time_slots()) for day in itinerary.days) / len(itinerary.days)
            if avg_activities > 3.5:
                suggestions.append(
                    f"Pace may be rushed - averaging {avg_activities:.1f} activities per day"
                )

        # Free time check
        has_free_time = any(
            len(day.get_time_slots()) < 4
            for day in itinerary.days
        )

        if not has_free_time and len(itinerary.days) > 2:
            suggestions.append("Consider adding free time for rest and spontaneous exploration")

        # Budget buffer
        if not any(issue.type == ValidationType.BUDGET for issue in issues):
            suggestions.append("Leave 10-20% budget buffer for unexpected costs and opportunities")

        return suggestions[:5]  # Max 5 suggestions

    def _severity_order(self, severity: ValidationSeverity) -> int:
        """Get sort order for severity."""
        order = {
            ValidationSeverity.ERROR: 0,
            ValidationSeverity.WARNING: 1,
            ValidationSeverity.INFO: 2
        }
        return order.get(severity, 3)

    def _get_geographic_cluster(self, day: ItineraryDay) -> Optional[str]:
        """
        Identify which geographic area/cluster a day focuses on.

        Args:
            day: Itinerary day

        Returns:
            Cluster name or None
        """
        # Extract areas from entity names (simplified)
        # In production, would use actual geographic coordinates
        areas = []
        for slot in day.get_time_slots():
            # Simple heuristic: extract first word as potential area
            if ' ' in slot.entity_name:
                potential_area = slot.entity_name.split()[0]
                areas.append(potential_area)

        if not areas:
            return None

        # Return most common area
        area_counts = Counter(areas)
        return area_counts.most_common(1)[0][0] if area_counts else None

    def _any_entity_matches(self, itinerary: GeneratedItinerary, search_term: str) -> bool:
        """
        Check if any entity matches search term (fuzzy).

        Args:
            itinerary: Itinerary to search
            search_term: Term to search for

        Returns:
            True if match found
        """
        search_lower = search_term.lower()

        for day in itinerary.days:
            for slot in day.get_time_slots():
                if search_lower in slot.entity_name.lower():
                    return True

        return False


# =============================================================================
# Testing Function
# =============================================================================

def test_validator():
    """Test validator with sample itineraries."""
    from src.utils.schemas import (
        UserIntent,
        TravelerProfileInput,
        Pace,
        example_stage5_generated_itinerary
    )

    logger.info("=" * 80)
    logger.info("🧪 TESTING ITINERARY VALIDATOR")
    logger.info("=" * 80)

    # Create sample itinerary
    itinerary = example_stage5_generated_itinerary()

    # Create sample context
    rag_context = RAGContext(
        user_intent_summary="1-day budget solo trip to Bangkok",
        profile_description="Budget solo traveler",
        priority_entities=[
            {
                'entity_id': 'attraction_bangkok_001',
                'name': 'Grand Palace',
                'type': 'attraction'
            }
        ]
    )

    # Create sample intent
    intent = UserIntent(
        destination="Bangkok",
        duration_days=1,
        traveler_profile=TravelerProfileInput(
            traveler_type="solo",
            budget_tier="budget"
        ),
        budget_per_day={'min': 30, 'max': 50},
        query_text="Test query"
    )

    # Initialize validator
    validator = ItineraryValidator()

    # Run validation
    report = validator.validate_itinerary(itinerary, rag_context, intent)

    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("📋 VALIDATION REPORT")
    logger.info("=" * 80)
    logger.info(f"Valid: {report.is_valid}")
    logger.info(f"Overall score: {report.overall_score:.2f}")
    logger.info(f"\nChecks:")
    logger.info(f"   No hallucinations: {report.no_hallucinations}")
    logger.info(f"   Logistics feasible: {report.logistics_feasible}")
    logger.info(f"   Budget compliant: {report.budget_compliant}")
    logger.info(f"   Timing realistic: {report.timing_realistic}")

    logger.info(f"\nIssues found: {len(report.issues)}")
    for issue in report.get_errors()[:3]:
        logger.info(f"   ERROR: {issue.description}")
    for issue in report.get_warnings()[:3]:
        logger.info(f"   WARNING: {issue.description}")

    logger.info(f"\nImprovement suggestions:")
    for suggestion in report.improvement_suggestions[:3]:
        logger.info(f"   - {suggestion}")

    logger.info(f"\nRegeneration needed: {report.regeneration_needed}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ VALIDATOR TESTING COMPLETE")
    logger.info("=" * 80)

    return report


if __name__ == "__main__":
    test_validator()
