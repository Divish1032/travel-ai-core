# RAG Error Handling Guide

Comprehensive error handling for the Stage 5 RAG pipeline with graceful degradation.

## Overview

The error handling system provides:
- **Custom exceptions** for different failure modes
- **Automatic retry logic** for transient failures
- **Graceful degradation** when full pipeline fails
- **User-friendly messages** instead of technical errors
- **Actionable suggestions** for users

---

## Quick Start

```python
from src.rag.error_handling import RAGErrorHandler, InsufficientDataError

# Initialize handler
handler = RAGErrorHandler()

try:
    # Try to generate itinerary
    result = pipeline.generate(query)

except InsufficientDataError as e:
    # Handle gracefully
    response = handler.handle_insufficient_data(intent, candidates)

    # Show user-friendly message
    print(response.user_message)

    # Show suggestions
    for suggestion in response.suggestions:
        print(f"  💡 {suggestion}")
```

---

## Exception Hierarchy

```python
RAGException (base)
├── InsufficientDataError    # Not enough entities
├── ValidationError           # Itinerary quality issues
├── BudgetExceededError       # Budget constraints
├── LLMError                  # API failures
├── ProfileMismatchError      # No data for profile
└── DurationError             # Duration impossible
```

---

## Error Handlers

### 1. Insufficient Data

Handles cases where not enough traveler data exists:

```python
from src.rag.error_handling import RAGErrorHandler

handler = RAGErrorHandler()

# Only 2 entities found (need 5+)
response = handler.handle_insufficient_data(
    intent=user_intent,
    candidates=retrieved_entities,
    min_required=5
)

if response.status == 'error':
    print(response.user_message)
    # "We don't have enough traveler experiences for Obscure Village yet.
    #  We found only 2 relevant places, but need at least 5 for a quality
    #  5-day itinerary."

    for suggestion in response.suggestions:
        print(f"  • {suggestion}")
    # • Try a shorter trip (4 days)
    # • Broaden your interests
    # • Try nearby destinations: Bangkok, Chiang Mai, Phuket
```

**Automatic suggestions include:**
- Shorter duration
- Broader interests
- Different budget tier
- Alternative destinations

---

### 2. Validation Failure

Handles invalid itineraries with partial results:

```python
response = handler.handle_validation_failure(
    itinerary=generated_itinerary,
    report=validation_report,
    intent=user_intent
)

if response.status == 'partial':
    # Still show itinerary with warnings
    display_itinerary(response.partial_result)

    print(f"⚠️  {response.user_message}")
    # "The generated itinerary has some quality issues.
    #  We're showing you the best version we could create..."

    # Show what went wrong
    print(f"Validation score: {response.details['validation_score']:.2f}")
    print(f"Issues found: {response.details['total_issues']}")
```

**Returns:**
- Partial itinerary (best effort)
- Validation score
- List of issues
- Actionable suggestions

---

### 3. LLM Failure with Retry

Handles API failures with automatic retry:

```python
handler = RAGErrorHandler()

try:
    result = llm_client.generate(prompt)

except Exception as e:
    response = handler.handle_llm_failure(
        phase='generation',
        error=e,
        retry_context='itinerary_gen'
    )

    if response.status == 'retry':
        # Retry automatically (with backoff)
        print(f"Retrying in {response.details['retry_delay']}s...")

    elif response.status == 'error':
        # Final failure
        print(response.user_message)
        # "Our AI service is temporarily unavailable.
        #  Please try again in a few moments."
```

**Features:**
- Exponential backoff (2s, 4s, 8s)
- Max 3 retries
- Rate limit detection
- User-friendly messages

---

### 4. Budget Exceeded

Handles impossible budget constraints:

```python
response = handler.handle_budget_exceeded(
    intent=user_intent,
    estimated_budget=100.0  # Minimum needed
)

print(response.user_message)
# "Your budget of $50/day is too tight for Phuket.
#  Based on traveler data, the minimum recommended budget is $100/day."

for suggestion in response.suggestions:
    print(f"  • {suggestion}")
# • Increase your budget to $100/day
# • Try a more budget-friendly destination
# • Reduce trip duration to save costs
```

---

## Integration with Pipeline

### Update pipeline.py:

```python
from src.rag.error_handling import (
    RAGErrorHandler,
    InsufficientDataError,
    ValidationError,
    LLMError
)

class RAGPipeline:
    def __init__(self):
        # ... existing code
        self.error_handler = RAGErrorHandler()

    def generate(self, query: str, **kwargs):
        try:
            # Phase 1: Parse
            intent = self.intent_parser.parse_query(query)

            # Phase 2: Retrieve
            candidates = self.retriever.retrieve_for_itinerary(intent)

            # Check if sufficient data
            if len(candidates) < 5:
                response = self.error_handler.handle_insufficient_data(
                    intent, candidates
                )
                raise InsufficientDataError(
                    response.user_message,
                    details=response.details
                )

            # Phase 5: Generate
            try:
                itinerary = self.generator.generate_itinerary(context, intent)
            except Exception as e:
                response = self.error_handler.handle_llm_failure(
                    'generation', e
                )
                if response.status == 'retry':
                    # Retry automatically
                    itinerary = self.generator.generate_itinerary(context, intent)
                else:
                    raise LLMError(response.user_message)

            # Phase 6: Validate
            report = self.validator.validate_itinerary(itinerary, context)

            if not report.is_valid:
                response = self.error_handler.handle_validation_failure(
                    itinerary, report, intent
                )

                # Return partial result with warnings
                return {
                    'itinerary': response.partial_result,
                    'status': 'partial',
                    'warnings': response.suggestions,
                    'validation_score': report.overall_score
                }

            return result

        except InsufficientDataError as e:
            # Try graceful degradation
            return self._generate_with_degradation(query, intent, e)

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'user_message': 'Unable to generate itinerary. Please try again.'
            }
```

---

## Graceful Degradation

When full pipeline fails, try relaxing constraints:

```python
from src.rag.error_handling import DegradationStrategy

class RAGPipeline:
    def _generate_with_degradation(self, query, intent, error):
        """Try generating with relaxed constraints."""

        logger.info("Attempting graceful degradation...")

        strategies = [
            # Strategy 1: Reduce duration
            lambda: DegradationStrategy.reduce_duration(intent, reduction=1),

            # Strategy 2: Broaden interests
            lambda: DegradationStrategy.broaden_interests(intent),

            # Strategy 3: Adjust budget tier
            lambda: DegradationStrategy.adjust_budget_tier(intent),

            # Strategy 4: Lower quality threshold
            lambda: self.retriever.set_min_rating(
                DegradationStrategy.relax_quality_threshold()
            )
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                logger.info(f"Trying degradation strategy {i}/{len(strategies)}")

                # Apply strategy
                modified_intent = strategy()

                # Retry generation
                result = self.generate(query, intent=modified_intent)

                # Add degradation notice
                result['degraded'] = True
                result['degradation_applied'] = i
                result['warning'] = (
                    "We adjusted your requirements to find available options. "
                    "Results may not perfectly match your original request."
                )

                return result

            except Exception as e:
                logger.warning(f"Strategy {i} failed: {e}")
                continue

        # All strategies failed
        return {
            'status': 'error',
            'message': 'Unable to generate itinerary even with relaxed constraints',
            'user_message': error.message,
            'suggestions': error.details.get('suggestions', [])
        }
```

---

## CLI Integration

### Show user-friendly errors:

```python
# In cli/generate_itinerary.py

from src.rag.error_handling import (
    RAGException,
    InsufficientDataError,
    ValidationError
)

@click.command()
def generate(query):
    pipeline = RAGPipeline()

    try:
        result = pipeline.generate(query)

        if result.get('status') == 'partial':
            # Show warnings for partial results
            click.secho("\n⚠️  Generated with warnings:", fg='yellow')
            click.echo(result.get('user_message', ''))

            click.echo("\nSuggestions for improvement:")
            for suggestion in result.get('warnings', []):
                click.echo(f"  • {suggestion}")

        # Show itinerary
        click.echo(result['formatted_output'])

    except InsufficientDataError as e:
        click.secho(f"\n❌ Insufficient Data", fg='red', bold=True)
        click.echo(f"\n{e.message}\n")

        if e.details.get('suggestions'):
            click.echo("Try these alternatives:")
            for suggestion in e.details['suggestions']:
                click.secho(f"  💡 {suggestion}", fg='cyan')

        raise click.Abort()

    except ValidationError as e:
        click.secho(f"\n⚠️  Quality Warning", fg='yellow', bold=True)
        click.echo(f"\n{e.message}\n")

        # Offer to continue anyway
        if click.confirm("Show itinerary anyway (with warnings)?"):
            click.echo(e.details.get('partial_itinerary', ''))
        else:
            raise click.Abort()

    except RAGException as e:
        click.secho(f"\n❌ Error: {e.message}", fg='red')
        raise click.Abort()
```

---

## Error Messages Reference

All error messages are user-friendly:

| Error Type | User Message |
|------------|-------------|
| `insufficient_data` | "We don't have enough traveler experiences for {destination} yet..." |
| `budget_impossible` | "Your budget of ${budget}/day is too tight for {destination}..." |
| `no_match_profile` | "We don't have enough data for {profile} travelers in {destination}..." |
| `llm_failure` | "Our AI service is temporarily unavailable. Please try again..." |
| `validation_failed` | "The generated itinerary has some quality issues..." |
| `api_rate_limit` | "We're experiencing high demand. Please wait {wait_time} seconds..." |

---

## Testing

```python
# Test error handling
from src.rag.error_handling import RAGErrorHandler

def test_error_handling():
    handler = RAGErrorHandler()

    # Test 1: Insufficient data
    response = handler.handle_insufficient_data(
        intent=test_intent,
        candidates=[],
        min_required=5
    )
    assert response.status == 'error'
    assert len(response.suggestions) > 0

    # Test 2: LLM retry
    response = handler.handle_llm_failure(
        phase='test',
        error=Exception("timeout")
    )
    assert response.status == 'retry'

    # Test 3: Final LLM failure
    for _ in range(3):
        handler.handle_llm_failure('test', Exception("timeout"))

    response = handler.handle_llm_failure('test', Exception("timeout"))
    assert response.status == 'error'

test_error_handling()
```

---

## Summary

✅ **Custom exceptions** for all failure modes
✅ **Automatic retry** with exponential backoff
✅ **Graceful degradation** with multiple strategies
✅ **User-friendly messages** instead of stack traces
✅ **Actionable suggestions** to help users succeed
✅ **Partial results** when possible (better than nothing)

**Result: Robust, user-friendly RAG pipeline!** 🛡️
