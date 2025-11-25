"""
LLM Client for Stage 2 Entity Extraction

Provides interface to OpenAI API for extracting structured travel information.
Uses gpt-4o-mini model with JSON mode for cost-effective extraction.

Key Features:
- JSON mode for structured output
- Automatic retry with exponential backoff (3 attempts)
- Token usage tracking
- Error handling and validation
- Cost estimation

Usage:
    from src.utils.llm_client import extract_with_gpt4o_mini

    result = extract_with_gpt4o_mini(
        prompt="Extract travel entities from: ...",
        max_retries=3
    )

    if result['success']:
        data = result['data']  # Parsed JSON
        tokens = result['tokens_used']
        cost = result['cost_usd']
"""

import json
import time
from typing import Dict, Any, Optional
from openai import OpenAI, APIError, RateLimitError, APIConnectionError

from src.utils.config import config
from src.utils.logging import get_logger


logger = get_logger(__name__)


# =============================================================================
# Cost Constants (as of 2024)
# =============================================================================

# GPT-4o-mini pricing (per 1M tokens)
GPT4O_MINI_INPUT_COST_PER_1M = 0.15  # $0.15 per 1M input tokens
GPT4O_MINI_OUTPUT_COST_PER_1M = 0.60  # $0.60 per 1M output tokens


# =============================================================================
# LLM Client Functions
# =============================================================================

def extract_with_gpt4o_mini(
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.1,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Extract structured data using GPT-4o-mini with JSON mode.

    Args:
        prompt: Full prompt text (should instruct to return JSON)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2.0)
        temperature: LLM temperature (0.0-1.0, default: 0.1 for consistency)
        max_tokens: Maximum output tokens (default: 4000)

    Returns:
        Dict with extraction results:
        {
            "success": True,
            "data": {...},  # Parsed JSON response
            "tokens_used": {
                "input": 1500,
                "output": 800,
                "total": 2300
            },
            "cost_usd": 0.000735,  # Estimated cost
            "model": "gpt-4o-mini",
            "error": None
        }

        On failure:
        {
            "success": False,
            "data": None,
            "tokens_used": {"input": 0, "output": 0, "total": 0},
            "cost_usd": 0.0,
            "model": "gpt-4o-mini",
            "error": "Error message"
        }

    Raises:
        ValueError: If OPENAI_API_KEY is not configured

    Example:
        >>> prompt = "Extract travel info from: I visited Phuket..."
        >>> result = extract_with_gpt4o_mini(prompt)
        >>> if result['success']:
        ...     print(f"Extracted data: {result['data']}")
        ...     print(f"Cost: ${result['cost_usd']:.4f}")
    """
    # Validate API key
    if not config.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY not configured. "
            "Add it to your .env file to use Stage 2 extraction."
        )

    # Initialize result structure
    result = {
        "success": False,
        "data": None,
        "tokens_used": {
            "input": 0,
            "output": 0,
            "total": 0
        },
        "cost_usd": 0.0,
        "model": "gpt-4o-mini",
        "error": None
    }

    # Initialize OpenAI client
    try:
        client = OpenAI(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        result['error'] = f"Failed to initialize OpenAI client: {e}"
        return result

    # Retry logic
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                f"Calling GPT-4o-mini (attempt {attempt}/{max_retries}), "
                f"prompt length: {len(prompt)} chars"
            )

            # Call OpenAI API with JSON mode
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},  # Force JSON output
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Extract response data
            content = response.choices[0].message.content

            if not content:
                logger.warning("Received empty response from GPT-4o-mini")
                result['error'] = "Empty response from API"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                return result

            # Parse JSON response
            try:
                data = json.loads(content)
                result['data'] = data
                result['success'] = True
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response content: {content[:500]}...")
                result['error'] = f"Invalid JSON response: {e}"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result

            # Extract token usage
            usage = response.usage
            result['tokens_used'] = {
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
                "total": usage.total_tokens
            }

            # Calculate cost
            input_cost = (usage.prompt_tokens / 1_000_000) * GPT4O_MINI_INPUT_COST_PER_1M
            output_cost = (usage.completion_tokens / 1_000_000) * GPT4O_MINI_OUTPUT_COST_PER_1M
            result['cost_usd'] = input_cost + output_cost

            logger.info(
                f"GPT-4o-mini extraction successful: "
                f"{usage.total_tokens} tokens, "
                f"${result['cost_usd']:.4f}"
            )

            return result

        except RateLimitError as e:
            logger.warning(
                f"Rate limit hit (attempt {attempt}/{max_retries}): {e}"
            )
            result['error'] = f"Rate limit: {e}"
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                logger.error(f"Rate limit exceeded after {max_retries} attempts")
                return result

        except APIConnectionError as e:
            logger.warning(
                f"API connection error (attempt {attempt}/{max_retries}): {e}"
            )
            result['error'] = f"Connection error: {e}"
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                logger.error(f"Connection failed after {max_retries} attempts")
                return result

        except APIError as e:
            logger.error(f"OpenAI API error (attempt {attempt}/{max_retries}): {e}")
            result['error'] = f"API error: {e}"
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                return result

        except Exception as e:
            logger.error(f"Unexpected error during extraction: {e}", exc_info=True)
            result['error'] = f"Unexpected error: {e}"
            return result

    # Should not reach here, but just in case
    return result


def estimate_extraction_cost(
    input_tokens: int,
    estimated_output_tokens: int = 2000
) -> float:
    """
    Estimate cost for entity extraction before making API call.

    Args:
        input_tokens: Number of input tokens (prompt + transcript)
        estimated_output_tokens: Expected output tokens (default: 2000)

    Returns:
        Estimated cost in USD

    Example:
        >>> # Estimate cost for 3000 input tokens
        >>> cost = estimate_extraction_cost(3000)
        >>> print(f"Estimated cost: ${cost:.4f}")
        Estimated cost: $0.0017
    """
    input_cost = (input_tokens / 1_000_000) * GPT4O_MINI_INPUT_COST_PER_1M
    output_cost = (estimated_output_tokens / 1_000_000) * GPT4O_MINI_OUTPUT_COST_PER_1M
    total_cost = input_cost + output_cost
    return total_cost


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("LLM Client Test")
    print("=" * 70)

    # Test prompt (simple JSON extraction)
    test_prompt = """
    Extract travel information and return as JSON with this structure:
    {
        "destination": "city name",
        "activities": ["activity1", "activity2"],
        "budget": "budget level",
        "sentiment": "positive/negative/neutral"
    }

    Text: "I visited Phuket Thailand for 5 days. Did island hopping and beach activities.
    Spent around 15000 baht total. It was amazing and very affordable!"
    """

    print("\nTest 1: Simple extraction")
    print(f"Prompt length: {len(test_prompt)} chars")

    # Estimate cost first
    estimated_tokens = len(test_prompt.split()) * 1.33  # Rough estimate
    estimated_cost = estimate_extraction_cost(int(estimated_tokens))
    print(f"Estimated cost: ${estimated_cost:.4f}")

    try:
        result = extract_with_gpt4o_mini(test_prompt)

        print(f"\nResult:")
        print(f"  Success: {result['success']}")
        if result['success']:
            print(f"  Data: {json.dumps(result['data'], indent=2)}")
            print(f"  Tokens: {result['tokens_used']['total']}")
            print(f"  Cost: ${result['cost_usd']:.4f}")
        else:
            print(f"  Error: {result['error']}")

    except ValueError as e:
        print(f"\n⚠ Configuration Error: {e}")
        print("\nTo use this client:")
        print("1. Get API key from: https://platform.openai.com/api-keys")
        print("2. Add to .env file: OPENAI_API_KEY=your_key_here")

    print("\n" + "=" * 70)
