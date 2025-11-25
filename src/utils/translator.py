"""
Translation Utilities for TravelAI

Provides free translation services using langdetect and googletrans libraries.
Used to translate non-English transcripts to English for LLM processing.

Libraries:
    - langdetect: Language detection (FREE)
    - googletrans: Google Translate API (unofficial, FREE)

Usage:
    from src.utils.translator import detect_language, translate_transcript

    # Detect language
    lang = detect_language("यह एक हिंदी वाक्य है")
    print(lang)  # 'hi'

    # Translate transcript segments
    transcript = [
        {"text": "नमस्ते", "start": 0.0, "duration": 1.0},
        {"text": "कैसे हैं आप", "start": 1.0, "duration": 1.5}
    ]
    translated = translate_transcript(transcript, source_lang='hi')
    # Returns: [
    #     {"text": "Hello", "start": 0.0, "duration": 1.0, "original_text": "नमस्ते"},
    #     {"text": "How are you", "start": 1.0, "duration": 1.5, "original_text": "कैसे हैं आप"}
    # ]

Note:
    - googletrans is UNOFFICIAL and may be rate-limited
    - Has retry logic (3 attempts) for rate limit handling
    - Returns original text if translation fails
    - FREE but not suitable for production at scale
    - For production, consider: DeepL API, Azure Translator, or Google Cloud Translation API
"""

import time
from typing import List, Dict, Any, Optional
from langdetect import detect, LangDetectException
from googletrans import Translator, LANGUAGES
from src.utils.logging import get_logger


logger = get_logger(__name__)


def detect_language(text: str) -> str:
    """
    Detect language of text using langdetect.

    Args:
        text: Text to detect language for

    Returns:
        ISO 639-1 language code (e.g., 'en', 'hi', 'es')
        Returns 'unknown' if detection fails

    Example:
        >>> detect_language("Hello world")
        'en'
        >>> detect_language("नमस्ते")
        'hi'
        >>> detect_language("Hola mundo")
        'es'
    """
    try:
        if not text or not text.strip():
            logger.warning("Empty text provided for language detection")
            return 'unknown'

        # Clean text (remove excessive whitespace)
        cleaned_text = ' '.join(text.split())

        # Detect language
        lang_code = detect(cleaned_text)
        logger.debug(f"Detected language: {lang_code} for text: {cleaned_text[:50]}...")

        return lang_code

    except LangDetectException as e:
        logger.warning(f"Language detection failed: {e}")
        return 'unknown'
    except Exception as e:
        logger.error(f"Unexpected error in language detection: {e}")
        return 'unknown'


def translate_to_english(
    text: str,
    source_lang: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> Dict[str, Any]:
    """
    Translate text to English using Google Translate (unofficial API).

    Args:
        text: Text to translate
        source_lang: Source language code (auto-detected if None)
        max_retries: Maximum retry attempts for rate limits (default: 3)
        retry_delay: Delay between retries in seconds (default: 2.0)

    Returns:
        Dict with translation result:
            {
                "translated_text": "Hello",
                "original_text": "नमस्ते",
                "source_lang": "hi",
                "success": True,
                "error": None
            }

    Example:
        >>> result = translate_to_english("नमस्ते", source_lang='hi')
        >>> print(result['translated_text'])
        'Hello'
    """
    result = {
        "translated_text": text,  # Default to original if translation fails
        "original_text": text,
        "source_lang": source_lang or 'unknown',
        "success": False,
        "error": None
    }

    try:
        if not text or not text.strip():
            logger.warning("Empty text provided for translation")
            result['error'] = "Empty text"
            return result

        # Clean text
        cleaned_text = ' '.join(text.split())

        # Initialize translator
        translator = Translator()

        # Retry logic for rate limiting
        for attempt in range(1, max_retries + 1):
            try:
                # Translate to English
                translation = translator.translate(
                    cleaned_text,
                    src=source_lang or 'auto',
                    dest='en'
                )

                # Update result
                result['translated_text'] = translation.text
                result['source_lang'] = translation.src
                result['success'] = True
                result['error'] = None

                logger.debug(
                    f"Translated ({translation.src} → en): "
                    f"{cleaned_text[:30]}... → {translation.text[:30]}..."
                )

                return result

            except Exception as e:
                error_msg = str(e).lower()

                # Check if rate limited
                if 'ratelimit' in error_msg or '429' in error_msg:
                    if attempt < max_retries:
                        logger.warning(
                            f"Rate limited (attempt {attempt}/{max_retries}), "
                            f"retrying in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts")
                        result['error'] = f"Rate limited after {max_retries} attempts"
                        return result

                # Other errors
                logger.error(f"Translation error (attempt {attempt}/{max_retries}): {e}")
                result['error'] = str(e)

                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                else:
                    return result

        return result

    except Exception as e:
        logger.error(f"Unexpected error in translate_to_english: {e}")
        result['error'] = str(e)
        return result


def translate_transcript(
    transcript: List[Dict[str, Any]],
    source_lang: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    preserve_original: bool = True
) -> List[Dict[str, Any]]:
    """
    Translate transcript segments to English while preserving timestamps.

    Args:
        transcript: List of transcript segments from Stage 1
            Format: [{"text": "...", "start": 0.0, "duration": 1.0}, ...]
        source_lang: Source language code (auto-detected if None)
        max_retries: Maximum retry attempts for rate limits
        retry_delay: Initial delay between retries in seconds
        preserve_original: If True, adds 'original_text' field to each segment

    Returns:
        List of translated transcript segments with same structure:
            [
                {
                    "text": "Hello",  # Translated text
                    "start": 0.0,
                    "duration": 1.0,
                    "original_text": "नमस्ते"  # Only if preserve_original=True
                },
                ...
            ]

        If translation fails for a segment, returns original text

    Example:
        >>> transcript = [
        ...     {"text": "नमस्ते", "start": 0.0, "duration": 1.0},
        ...     {"text": "कैसे हैं", "start": 1.0, "duration": 1.5}
        ... ]
        >>> translated = translate_transcript(transcript, source_lang='hi')
        >>> print(translated[0]['text'])
        'Hello'
        >>> print(translated[0]['original_text'])
        'नमस्ते'
    """
    if not transcript:
        logger.warning("Empty transcript provided for translation")
        return []

    logger.info(f"Translating {len(transcript)} transcript segments to English...")

    translated_segments = []
    successful_translations = 0
    failed_translations = 0

    for i, segment in enumerate(transcript):
        try:
            # Extract text
            original_text = segment.get('text', '')

            if not original_text or not original_text.strip():
                # Empty segment, keep as is
                translated_segments.append(segment.copy())
                continue

            # Translate text
            translation_result = translate_to_english(
                text=original_text,
                source_lang=source_lang,
                max_retries=max_retries,
                retry_delay=retry_delay
            )

            # Create new segment with translation
            new_segment = {
                'text': translation_result['translated_text'],
                'start': segment.get('start', 0.0),
                'duration': segment.get('duration', 0.0)
            }

            # Preserve original text if requested
            if preserve_original:
                new_segment['original_text'] = original_text

            translated_segments.append(new_segment)

            # Track success/failure
            if translation_result['success']:
                successful_translations += 1
            else:
                failed_translations += 1
                logger.warning(
                    f"Segment {i+1}/{len(transcript)} translation failed: "
                    f"{translation_result.get('error', 'Unknown error')}"
                )

            # Small delay to avoid rate limiting
            if (i + 1) % 10 == 0:  # Every 10 segments
                time.sleep(0.5)
                logger.debug(f"Progress: {i+1}/{len(transcript)} segments translated")

        except Exception as e:
            logger.error(f"Error translating segment {i+1}: {e}")
            # Keep original segment on error
            translated_segments.append(segment.copy())
            failed_translations += 1

    # Summary
    logger.info(
        f"Translation complete: {successful_translations} successful, "
        f"{failed_translations} failed out of {len(transcript)} segments"
    )

    return translated_segments


def get_supported_languages() -> Dict[str, str]:
    """
    Get list of supported languages by googletrans.

    Returns:
        Dict mapping language codes to language names
        Example: {'en': 'english', 'hi': 'hindi', 'es': 'spanish', ...}

    Example:
        >>> languages = get_supported_languages()
        >>> print(languages['hi'])
        'hindi'
    """
    return LANGUAGES


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("Translation Utilities - Test")
    print("=" * 70)

    # Test 1: Language Detection
    print("\n1. Testing language detection...")
    test_texts = [
        ("Hello world", "en"),
        ("नमस्ते", "hi"),
        ("Hola mundo", "es"),
        ("Bonjour le monde", "fr"),
        ("こんにちは世界", "ja")
    ]

    for text, expected in test_texts:
        detected = detect_language(text)
        status = "✓" if detected == expected else "✗"
        print(f"{status} '{text}' → {detected} (expected: {expected})")

    # Test 2: Text Translation
    print("\n2. Testing text translation...")
    hindi_text = "नमस्ते, आप कैसे हैं?"
    result = translate_to_english(hindi_text, source_lang='hi')
    print(f"Original: {result['original_text']}")
    print(f"Translated: {result['translated_text']}")
    print(f"Success: {result['success']}")

    # Test 3: Transcript Translation
    print("\n3. Testing transcript translation...")
    sample_transcript = [
        {"text": "नमस्ते", "start": 0.0, "duration": 1.0},
        {"text": "आप कैसे हैं", "start": 1.0, "duration": 1.5},
        {"text": "मुझे यह जगह पसंद है", "start": 2.5, "duration": 2.0}
    ]

    translated = translate_transcript(sample_transcript, source_lang='hi')
    print(f"Translated {len(translated)} segments:")
    for seg in translated:
        print(f"  [{seg['start']:.1f}s] {seg.get('original_text', '')} → {seg['text']}")

    # Test 4: Supported Languages
    print("\n4. Supported languages sample...")
    languages = get_supported_languages()
    sample_langs = ['en', 'hi', 'es', 'fr', 'de', 'ja', 'ko', 'zh-cn']
    for code in sample_langs:
        name = languages.get(code, 'unknown')
        print(f"  {code}: {name}")

    print("\n" + "=" * 70)
    print("Translation utilities test complete!")
    print("=" * 70)
