"""
LLM Client for Stage 2 Entity Extraction

Provides unified interface to multiple LLM providers (OpenAI, DeepSeek).
Uses JSON mode for structured output with automatic retry logic.

Supported Providers:
- OpenAI (gpt-4o-mini): $0.150/1M input, $0.600/1M output
- DeepSeek (deepseek-chat): $0.14/1M input, $0.28/1M output (5x cheaper)

Key Features:
- Unified extract_with_llm() interface
- JSON mode for structured output
- Automatic retry with exponential backoff (3 attempts)
- Token usage tracking and cost calculation
- Provider fallback logic
- DeepSeek uses OpenAI-compatible API

Usage:
    from src.utils.llm_client import extract_with_llm

    result = extract_with_llm(
        prompt="Extract travel entities from: ...",
        provider="deepseek",  # or "openai"
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

# Try to import Google Generative AI (optional dependency)
try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None


logger = get_logger(__name__)


# =============================================================================
# Cost Constants (per 1M tokens)
# =============================================================================

# OpenAI gpt-4o-mini pricing
OPENAI_INPUT_COST_PER_1M = 0.150  # $0.150 per 1M input tokens
OPENAI_OUTPUT_COST_PER_1M = 0.600  # $0.600 per 1M output tokens

# DeepSeek deepseek-chat pricing
DEEPSEEK_INPUT_COST_PER_1M = 0.14  # $0.14 per 1M input tokens
DEEPSEEK_OUTPUT_COST_PER_1M = 0.28  # $0.28 per 1M output tokens

# Google Gemini pricing
GEMINI_FLASH_INPUT_COST_PER_1M = 0.075  # $0.075 per 1M input tokens
GEMINI_FLASH_OUTPUT_COST_PER_1M = 0.30  # $0.30 per 1M output tokens
GEMINI_PRO_INPUT_COST_PER_1M = 1.25  # $1.25 per 1M input tokens
GEMINI_PRO_OUTPUT_COST_PER_1M = 5.00  # $5.00 per 1M output tokens


# =============================================================================
# Provider-Specific Functions
# =============================================================================

def extract_with_openai(
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.3,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Extract structured data using OpenAI GPT-4o-mini.

    Args:
        prompt: Full prompt text (should instruct to return JSON)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2.0)
        temperature: LLM temperature (0.0-1.0, default: 0.3 for consistency)
        max_tokens: Maximum output tokens (default: 4000)

    Returns:
        Dict with extraction results (see extract_with_llm for schema)

    Raises:
        ValueError: If OPENAI_API_KEY is not configured
    """
    # Validate API key
    if not config.OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY not configured. "
            "Add it to your .env file to use OpenAI extraction."
        )

    # Initialize result structure
    result = {
        "success": False,
        "data": None,
        "tokens_used": {"input": 0, "output": 0, "total": 0},
        "cost_usd": 0.0,
        "model": "gpt-4o-mini",
        "provider": "openai",
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
                f"Calling OpenAI GPT-4o-mini (attempt {attempt}/{max_retries})"
            )

            # Call OpenAI API with JSON mode
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Extract and parse response
            content = response.choices[0].message.content
            if not content:
                logger.warning("Empty response from OpenAI")
                result['error'] = "Empty response"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result

            data = json.loads(content)
            result['data'] = data
            result['success'] = True

            # Extract token usage and calculate cost
            usage = response.usage
            result['tokens_used'] = {
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
                "total": usage.total_tokens
            }

            input_cost = (usage.prompt_tokens / 1_000_000) * OPENAI_INPUT_COST_PER_1M
            output_cost = (usage.completion_tokens / 1_000_000) * OPENAI_OUTPUT_COST_PER_1M
            result['cost_usd'] = input_cost + output_cost

            logger.info(
                f"OpenAI extraction successful: "
                f"{usage.total_tokens} tokens, ${result['cost_usd']:.4f}"
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            result['error'] = f"Invalid JSON: {e}"
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return result

        except (RateLimitError, APIConnectionError, APIError) as e:
            logger.warning(f"OpenAI API error (attempt {attempt}/{max_retries}): {e}")
            result['error'] = str(e)
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return result

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            result['error'] = f"Unexpected error: {e}"
            return result

    return result


def extract_with_deepseek(
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.3,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Extract structured data using DeepSeek API.

    DeepSeek is OpenAI-compatible, so we use the OpenAI SDK with custom base_url.

    Args:
        prompt: Full prompt text (should instruct to return JSON)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2.0)
        temperature: LLM temperature (0.0-1.0, default: 0.3 for consistency)
        max_tokens: Maximum output tokens (default: 4000)

    Returns:
        Dict with extraction results (see extract_with_llm for schema)

    Raises:
        ValueError: If DEEPSEEK_API_KEY is not configured
    """
    # Validate API key
    if not config.DEEPSEEK_API_KEY:
        raise ValueError(
            "DEEPSEEK_API_KEY not configured. "
            "Add it to your .env file to use DeepSeek extraction."
        )

    # Initialize result structure
    model_name = config.DEEPSEEK_MODEL or "deepseek-chat"
    result = {
        "success": False,
        "data": None,
        "tokens_used": {"input": 0, "output": 0, "total": 0},
        "cost_usd": 0.0,
        "model": model_name,
        "provider": "deepseek",
        "error": None
    }

    # Initialize DeepSeek client (OpenAI-compatible)
    try:
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
    except Exception as e:
        logger.error(f"Failed to initialize DeepSeek client: {e}")
        result['error'] = f"Failed to initialize DeepSeek client: {e}"
        return result

    # Retry logic
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                f"Calling DeepSeek {model_name} (attempt {attempt}/{max_retries})"
            )

            # Call DeepSeek API with JSON mode
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Extract and parse response
            content = response.choices[0].message.content
            if not content:
                logger.warning("Empty response from DeepSeek")
                result['error'] = "Empty response"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result
            data = json.loads(content)
            result['data'] = data
            result['success'] = True

            # Extract token usage and calculate cost
            usage = response.usage
            result['tokens_used'] = {
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
                "total": usage.total_tokens
            }

            input_cost = (usage.prompt_tokens / 1_000_000) * DEEPSEEK_INPUT_COST_PER_1M
            output_cost = (usage.completion_tokens / 1_000_000) * DEEPSEEK_OUTPUT_COST_PER_1M
            result['cost_usd'] = input_cost + output_cost

            logger.info(
                f"DeepSeek extraction successful: "
                f"{usage.total_tokens} tokens, ${result['cost_usd']:.4f}"
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            result['error'] = f"Invalid JSON: {e}"
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return result

        except (RateLimitError, APIConnectionError, APIError) as e:
            logger.warning(f"DeepSeek API error (attempt {attempt}/{max_retries}): {e}")
            result['error'] = str(e)
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return result

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            result['error'] = f"Unexpected error: {e}"
            return result

    return result


def extract_with_gemini(
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.3,
    max_tokens: int = 8000
) -> Dict[str, Any]:
    """
    Extract structured data using Google Gemini API.

    Args:
        prompt: Full prompt text (should instruct to return JSON)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2.0)
        temperature: LLM temperature (0.0-2.0, default: 0.3 for consistency)
        max_tokens: Maximum output tokens (default: 8000, increased for long transcripts)

    Returns:
        Dict with extraction results (see extract_with_llm for schema)

    Raises:
        ValueError: If GEMINI_API_KEY is not configured or Gemini SDK not installed
    """
    # Check if Gemini SDK is available
    if not GEMINI_AVAILABLE:
        raise ValueError(
            "Google Generative AI package not installed. "
            "Install with: pip install google-genai"
        )

    # Validate API key
    if not config.GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not configured. "
            "Add it to your .env file to use Gemini extraction."
        )

    # Initialize result structure
    model_name = config.GEMINI_MODEL or "gemini-2.5-flash-lite"

    result = {
        "success": False,
        "data": None,
        "tokens_used": {"input": 0, "output": 0, "total": 0},
        "cost_usd": 0.0,
        "model": model_name,
        "provider": "gemini",
        "error": None
    }

    # Configure Gemini
    try:
        # Create client with API key
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # Configure generation settings for JSON output
        # Increased max_output_tokens from 4000 to 8000 to prevent truncation
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": 8000,  # Increased to handle long transcripts
            "response_mime_type": "application/json",  # Force JSON output
        }

    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        result['error'] = f"Failed to initialize Gemini client: {e}"
        return result

    # Retry logic
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                f"Calling Gemini {model_name} (attempt {attempt}/{max_retries})"
            )

            # Call Gemini API
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=generation_config
            )

            # Extract response text
            if not response.text:
                logger.warning("Empty response from Gemini")
                result['error'] = "Empty response"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result

            # Log response length for debugging
            response_text = response.text
            logger.debug(f"Gemini response length: {len(response_text)} characters")

            # Check if response appears truncated
            if len(response_text) > 7500:
                logger.warning(
                    f"Response is very long ({len(response_text)} chars). "
                    "May be approaching token limit."
                )

            # Parse JSON response
            try:
                data = json.loads(response_text)
                result['data'] = data
                result['success'] = True
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                # Log more context around the error location
                if hasattr(e, 'pos') and e.pos:
                    start = max(0, e.pos - 200)
                    end = min(len(response_text), e.pos + 200)
                    logger.error(f"Error context: ...{response_text[start:end]}...")
                else:
                    # Log first and last parts of response
                    logger.error(f"Response start: {response_text[:500]}")
                    logger.error(f"Response end: {response_text[-500:]}")

                result['error'] = f"Invalid JSON: {e}"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result

            # Extract token usage (if available)
            try:
                if hasattr(response, 'usage_metadata'):
                    usage = response.usage_metadata
                    input_tokens = usage.prompt_token_count
                    output_tokens = usage.candidates_token_count
                    total_tokens = usage.total_token_count
                else:
                    # Estimate tokens if usage not available
                    input_tokens = len(prompt.split()) * 1.3
                    output_tokens = len(response.text.split()) * 1.3
                    total_tokens = input_tokens + output_tokens

                result['tokens_used'] = {
                    "input": int(input_tokens),
                    "output": int(output_tokens),
                    "total": int(total_tokens)
                }

                # Calculate cost based on model
                if "flash" in model_name.lower():
                    input_cost = (input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_COST_PER_1M
                    output_cost = (output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_COST_PER_1M
                elif "pro" in model_name.lower():
                    input_cost = (input_tokens / 1_000_000) * GEMINI_PRO_INPUT_COST_PER_1M
                    output_cost = (output_tokens / 1_000_000) * GEMINI_PRO_OUTPUT_COST_PER_1M
                else:
                    # Default to Flash pricing
                    input_cost = (input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_COST_PER_1M
                    output_cost = (output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_COST_PER_1M

                result['cost_usd'] = input_cost + output_cost

                logger.info(
                    f"Gemini extraction successful: "
                    f"{int(total_tokens)} tokens, ${result['cost_usd']:.4f}"
                )

            except Exception as token_error:
                logger.warning(f"Could not extract token usage: {token_error}")
                # Continue anyway, just without cost tracking

            return result

        except Exception as e:
            error_msg = str(e).lower()

            # Check for rate limiting
            if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                logger.warning(f"Gemini rate limit (attempt {attempt}/{max_retries}): {e}")
                result['error'] = f"Rate limit: {e}"
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return result

            # Other API errors
            logger.error(f"Gemini API error (attempt {attempt}/{max_retries}): {e}")
            result['error'] = str(e)
            if attempt < max_retries:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return result

    return result


# =============================================================================
# Unified Interface
# =============================================================================

def extract_with_llm(
    prompt: str,
    provider: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.3,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Extract structured data using configured LLM provider.

    Unified interface that routes to OpenAI or DeepSeek based on provider setting.
    Includes automatic fallback logic if primary provider fails.

    Args:
        prompt: Full prompt text (should instruct to return JSON)
        provider: LLM provider ("openai" or "deepseek", default: from config)
        max_retries: Maximum retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 2.0)
        temperature: LLM temperature (0.0-1.0, default: 0.3 for consistency)
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
            "cost_usd": 0.000735,
            "model": "deepseek-chat",
            "provider": "deepseek",
            "error": None
        }

        On failure:
        {
            "success": False,
            "data": None,
            "tokens_used": {"input": 0, "output": 0, "total": 0},
            "cost_usd": 0.0,
            "model": "...",
            "provider": "...",
            "error": "Error message"
        }

    Example:
        >>> prompt = "Extract travel info from: I visited Phuket..."
        >>> result = extract_with_llm(prompt, provider="deepseek")
        >>> if result['success']:
        ...     print(f"Cost: ${result['cost_usd']:.4f}")
    """
    # Determine provider (use parameter or fall back to config)
    selected_provider = provider or config.LLM_PROVIDER or "gemini"
    selected_provider = selected_provider.lower()

    logger.info(f"Using LLM provider: {selected_provider}")

    # Route to appropriate provider
    if selected_provider == "openai":
        try:
            return extract_with_openai(
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except ValueError as e:
            # API key not configured, try fallback
            logger.warning(f"OpenAI not available: {e}")
            if config.GEMINI_API_KEY:
                logger.info("Falling back to Gemini")
                return extract_with_gemini(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            elif config.DEEPSEEK_API_KEY:
                logger.info("Falling back to DeepSeek")
                return extract_with_deepseek(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                raise ValueError("No LLM provider configured. Set OPENAI_API_KEY, DEEPSEEK_API_KEY, or GEMINI_API_KEY in .env")

    elif selected_provider == "deepseek":
        try:
            return extract_with_deepseek(
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except ValueError as e:
            # API key not configured, try fallback
            logger.warning(f"DeepSeek not available: {e}")
            if config.GEMINI_API_KEY:
                logger.info("Falling back to Gemini")
                return extract_with_gemini(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            elif config.OPENAI_API_KEY:
                logger.info("Falling back to OpenAI")
                return extract_with_openai(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                raise ValueError("No LLM provider configured. Set OPENAI_API_KEY, DEEPSEEK_API_KEY, or GEMINI_API_KEY in .env")

    elif selected_provider == "gemini":
        try:
            return extract_with_gemini(
                prompt=prompt,
                max_retries=max_retries,
                retry_delay=retry_delay,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except ValueError as e:
            # API key not configured, try fallback
            logger.warning(f"Gemini not available: {e}")
            if config.DEEPSEEK_API_KEY:
                logger.info("Falling back to DeepSeek")
                return extract_with_deepseek(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            elif config.OPENAI_API_KEY:
                logger.info("Falling back to OpenAI")
                return extract_with_openai(
                    prompt=prompt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            else:
                raise ValueError("No LLM provider configured. Set OPENAI_API_KEY, DEEPSEEK_API_KEY, or GEMINI_API_KEY in .env")

    else:
        raise ValueError(
            f"Unknown LLM provider: {selected_provider}. "
            f"Supported providers: openai, deepseek, gemini"
        )


# Backward compatibility alias
def extract_with_gpt4o_mini(
    prompt: str,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    temperature: float = 0.1,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Legacy function for backward compatibility.

    Routes to extract_with_llm() with provider="openai".
    """
    return extract_with_llm(
        prompt=prompt,
        provider="openai",
        max_retries=max_retries,
        retry_delay=retry_delay,
        temperature=temperature,
        max_tokens=max_tokens
    )


# =============================================================================
# LLMClient Class (Simple Wrapper for Object-Oriented Usage)
# =============================================================================

class LLMClient:
    """
    Simple wrapper class for LLM extraction functions.

    Provides object-oriented interface for backwards compatibility.
    """

    def __init__(self, provider: Optional[str] = None):
        """
        Initialize LLM client.

        Args:
            provider: LLM provider ("openai", "deepseek", or "gemini")
        """
        self.provider = provider or config.LLM_PROVIDER or "gemini"

    def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.3,
        max_retries: int = 3
    ) -> str:
        """
        Generate text using LLM.

        Args:
            prompt: Input prompt
            max_tokens: Maximum output tokens
            temperature: LLM temperature
            max_retries: Maximum retry attempts

        Returns:
            Generated text content

        Raises:
            RuntimeError: If extraction fails
        """
        result = extract_with_llm(
            prompt=prompt,
            provider=self.provider,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens=max_tokens
        )

        if not result['success']:
            raise RuntimeError(f"LLM generation failed: {result['error']}")

        # Return JSON as string for compatibility
        return json.dumps(result['data'])


# =============================================================================
# Cost Calculation Utilities
# =============================================================================

def get_extraction_cost(
    provider: str,
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None
) -> Dict[str, float]:
    """
    Calculate extraction cost for given provider and token counts.

    Args:
        provider: LLM provider ("openai", "deepseek", or "gemini")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name (for Gemini: flash vs pro pricing)

    Returns:
        Dict with cost breakdown:
        {
            "input_cost": 0.0003,
            "output_cost": 0.0012,
            "total_cost": 0.0015,
            "provider": "gemini"
        }

    Example:
        >>> cost = get_extraction_cost("gemini", 2000, 500, "gemini-2.5-flash-lite")
        >>> print(f"Total: ${cost['total_cost']:.4f}")
        Total: $0.0003
    """
    provider = provider.lower()

    if provider == "openai":
        input_cost = (input_tokens / 1_000_000) * OPENAI_INPUT_COST_PER_1M
        output_cost = (output_tokens / 1_000_000) * OPENAI_OUTPUT_COST_PER_1M
    elif provider == "deepseek":
        input_cost = (input_tokens / 1_000_000) * DEEPSEEK_INPUT_COST_PER_1M
        output_cost = (output_tokens / 1_000_000) * DEEPSEEK_OUTPUT_COST_PER_1M
    elif provider == "gemini":
        # Determine pricing based on model
        if model and "pro" in model.lower():
            input_cost = (input_tokens / 1_000_000) * GEMINI_PRO_INPUT_COST_PER_1M
            output_cost = (output_tokens / 1_000_000) * GEMINI_PRO_OUTPUT_COST_PER_1M
        else:
            # Default to Flash pricing
            input_cost = (input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_COST_PER_1M
            output_cost = (output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_COST_PER_1M
    else:
        raise ValueError(f"Unknown provider: {provider}")

    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
        "provider": provider
    }


def estimate_extraction_cost(
    input_tokens: int,
    estimated_output_tokens: int = 2000,
    provider: Optional[str] = None
) -> float:
    """
    Estimate cost for entity extraction before making API call.

    Args:
        input_tokens: Number of input tokens (prompt + transcript)
        estimated_output_tokens: Expected output tokens (default: 2000)
        provider: LLM provider (default: from config)

    Returns:
        Estimated cost in USD

    Example:
        >>> cost = estimate_extraction_cost(3000, provider="deepseek")
        >>> print(f"Estimated cost: ${cost:.4f}")
        Estimated cost: $0.0010
    """
    selected_provider = provider or config.LLM_PROVIDER or "deepseek"
    cost_breakdown = get_extraction_cost(
        provider=selected_provider,
        input_tokens=input_tokens,
        output_tokens=estimated_output_tokens
    )
    return cost_breakdown['total_cost']


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("LLM Client Test - Multi-Provider Support")
    print("=" * 70)

    # Test prompt
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

    print("\nTest 1: DeepSeek extraction")
    print(f"Prompt length: {len(test_prompt)} chars")

    # Estimate costs for both providers
    estimated_tokens = len(test_prompt.split()) * 1.33
    deepseek_cost = estimate_extraction_cost(int(estimated_tokens), provider="deepseek")
    openai_cost = estimate_extraction_cost(int(estimated_tokens), provider="openai")

    print("\nEstimated costs:")
    print(f"  DeepSeek: ${deepseek_cost:.4f}")
    print(f"  OpenAI:   ${openai_cost:.4f}")
    print(f"  Savings:  {((openai_cost - deepseek_cost) / openai_cost * 100):.1f}%")

    try:
        # Test with configured provider
        result = extract_with_llm(test_prompt)

        print("\nResult:")
        print(f"  Provider: {result['provider']}")
        print(f"  Model: {result['model']}")
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
        print("1. Get API key from: https://platform.deepseek.com/api_keys (recommended)")
        print("   OR https://platform.openai.com/api-keys")
        print("2. Add to .env file:")
        print("   LLM_PROVIDER=deepseek")
        print("   DEEPSEEK_API_KEY=your_key_here")

    print("\n" + "=" * 70)
