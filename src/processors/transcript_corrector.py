#!/usr/bin/env python3
"""
Transcript Corrector Module - Thai Place Name Corrections & LLM Proofreading

This module provides three layers of transcript correction:
1. Dictionary-based phonetic corrections (fast, free)
2. Fuzzy matching for similar names (fast, free)
3. LLM proofreading for complex corrections (accurate, ~$0.001/transcript)

Usage:
    from src.processors.transcript_corrector import TranscriptCorrector

    corrector = TranscriptCorrector()
    corrected_segments = corrector.correct_transcript(segments, video_title="Thailand Travel")

Features:
    - 200+ Thai place name corrections
    - Phonetic pattern matching (Calsock → Khao Sok)
    - Context-aware LLM proofreading
    - Preserves original text for audit trail
    - Minimal latency for dictionary corrections
"""

import re
import os
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher
from datetime import datetime, timezone

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Thai Place Name Dictionary - Phonetic Corrections
# =============================================================================

# Common Whisper transcription errors for Thai place names
# Format: "wrong_spelling": "correct_spelling"
THAI_PLACE_CORRECTIONS: Dict[str, str] = {
    # National Parks & Nature
    "calsock": "khao sok",
    "cal sock": "khao sok",
    "cow sock": "khao sok",
    "kao sok": "khao sok",
    "kow sok": "khao sok",
    "cal sawk": "khao sok",
    "khao yai": "khao yai",  # correct but common variants
    "cow yai": "khao yai",
    "kao yai": "khao yai",
    "erawan": "erawan",
    "air a wan": "erawan",
    "airy one": "erawan",

    # Bangkok
    "cow san": "khao san",
    "kao san": "khao san",
    "cow sarn": "khao san",
    "cal san": "khao san",
    "chatuchak": "chatuchak",
    "jatujak": "chatuchak",
    "ja tu jak": "chatuchak",
    "chat u chak": "chatuchak",
    "lumpini": "lumpini",
    "lum pini": "lumpini",
    "lumphini": "lumpini",
    "siam": "siam",
    "see am": "siam",
    "sy am": "siam",
    "sukhumvit": "sukhumvit",
    "suk hum vit": "sukhumvit",
    "su kum wit": "sukhumvit",
    "silom": "silom",
    "see lom": "silom",
    "si lom": "silom",
    "pratunam": "pratunam",
    "pra tu nam": "pratunam",
    "victory monument": "victory monument",
    "asiatique": "asiatique",
    "asia teak": "asiatique",
    "asia teek": "asiatique",

    # Temples (Wat)
    "wat pho": "wat pho",
    "wat po": "wat pho",
    "wat poe": "wat pho",
    "what pho": "wat pho",
    "wat arun": "wat arun",
    "what are run": "wat arun",
    "wat ah run": "wat arun",
    "wat a roon": "wat arun",
    "grand palace": "grand palace",
    "wat phra kaew": "wat phra kaew",
    "wat pra keo": "wat phra kaew",
    "emerald buddha": "emerald buddha temple",

    # Phuket
    "pooket": "phuket",
    "poo ket": "phuket",
    "fu ket": "phuket",
    "foo ket": "phuket",
    "pu ket": "phuket",
    "patong": "patong",
    "pa tong": "patong",
    "paton": "patong",
    "kata": "kata",
    "karon": "karon",
    "car on": "karon",
    "ka ron": "karon",
    "rawai": "rawai",
    "ra why": "rawai",
    "nai harn": "nai harn",
    "ny harn": "nai harn",
    "big buddha phuket": "big buddha phuket",
    "phang nga": "phang nga",
    "pang na": "phang nga",
    "pang nga": "phang nga",
    "fang na": "phang nga",
    "james bond island": "james bond island",

    # Chiang Mai
    "chiang mai": "chiang mai",
    "chang mai": "chiang mai",
    "cheng mai": "chiang mai",
    "chieng mai": "chiang mai",
    "chiang my": "chiang mai",
    "chang my": "chiang mai",
    "doi suthep": "doi suthep",
    "doy su tep": "doi suthep",
    "doi su thep": "doi suthep",
    "sunday market": "sunday walking street",
    "night bazaar": "night bazaar",
    "nimman": "nimmanhaemin",
    "nimman haemin": "nimmanhaemin",
    "nim man": "nimmanhaemin",
    "old city": "old city",
    "tha phae": "tha phae",
    "ta pay": "tha phae",
    "ta pae": "tha phae",
    "elephant sanctuary": "elephant sanctuary",
    "elephant nature park": "elephant nature park",
    "sticky waterfalls": "bua tong sticky waterfalls",
    "bua tong": "bua tong sticky waterfalls",
    "pai": "pai",
    "pie": "pai",
    "pye": "pai",

    # Chiang Rai
    "chiang rai": "chiang rai",
    "chang rai": "chiang rai",
    "chieng rai": "chiang rai",
    "white temple": "wat rong khun",
    "wat rong khun": "wat rong khun",
    "blue temple": "wat rong suea ten",
    "wat rong suea ten": "wat rong suea ten",
    "black house": "baan dam museum",
    "baan dam": "baan dam museum",

    # Krabi & Islands
    "krabi": "krabi",
    "krabee": "krabi",
    "crabby": "krabi",
    "cra bee": "krabi",
    "railay": "railay beach",
    "rai lay": "railay beach",
    "raily": "railay beach",
    "rai lei": "railay beach",
    "ao nang": "ao nang",
    "ow nang": "ao nang",
    "a o nang": "ao nang",
    "phi phi": "phi phi islands",
    "pee pee": "phi phi islands",
    "fee fee": "phi phi islands",
    "maya bay": "maya bay",
    "my a bay": "maya bay",
    "koh lanta": "koh lanta",
    "ko lanta": "koh lanta",
    "call anta": "koh lanta",

    # Koh Samui & Gulf Islands
    "koh samui": "koh samui",
    "ko samui": "koh samui",
    "co samui": "koh samui",
    "ko sa moo ee": "koh samui",
    "koh phangan": "koh phangan",
    "ko phangan": "koh phangan",
    "ko pan gan": "koh phangan",
    "koh pangan": "koh phangan",
    "full moon party": "full moon party",
    "haad rin": "haad rin",
    "had rin": "haad rin",
    "koh tao": "koh tao",
    "ko tao": "koh tao",
    "co tao": "koh tao",
    "koh chang": "koh chang",
    "ko chang": "koh chang",
    "co chang": "koh chang",

    # Pattaya & East
    "pattaya": "pattaya",
    "pa ta ya": "pattaya",
    "pat ta ya": "pattaya",
    "pataya": "pattaya",
    "walking street pattaya": "walking street pattaya",

    # Ayutthaya & Central
    "ayutthaya": "ayutthaya",
    "a you ta ya": "ayutthaya",
    "ayuthaya": "ayutthaya",
    "a yut ta ya": "ayutthaya",
    "hua hin": "hua hin",
    "who a hin": "hua hin",
    "wa hin": "hua hin",
    "kanchanaburi": "kanchanaburi",
    "kanchan a buri": "kanchanaburi",
    "kan cha na bu ree": "kanchanaburi",
    "bridge on the river kwai": "bridge over the river kwai",
    "river kwai": "river kwai",
    "death railway": "death railway",

    # Isaan (Northeast)
    "isaan": "isan",
    "ee san": "isan",
    "i saan": "isan",
    "nakhon ratchasima": "nakhon ratchasima",
    "korat": "korat",
    "khon kaen": "khon kaen",
    "con ken": "khon kaen",
    "udon thani": "udon thani",
    "ubon": "ubon ratchathani",

    # Food & Common Terms
    "pad thai": "pad thai",
    "pat thai": "pad thai",
    "pad tie": "pad thai",
    "tom yum": "tom yum",
    "tom yam": "tom yum",
    "tom yang": "tom yum",
    "som tam": "som tam",
    "som tum": "som tam",
    "papaya salad": "som tam",
    "khao soi": "khao soi",
    "cow soy": "khao soi",
    "kao soy": "khao soi",
    "massaman": "massaman",
    "muss a man": "massaman",
    "green curry": "green curry",
    "mango sticky rice": "mango sticky rice",

    # Transport & Common
    "tuk tuk": "tuk tuk",
    "took took": "tuk tuk",
    "tuk-tuk": "tuk tuk",
    "songthaew": "songthaew",
    "song tao": "songthaew",
    "song taew": "songthaew",
    "baht": "baht",
    "bot": "baht",
    "bat": "baht",
    "bht": "baht",
    "sawadee": "sawasdee",
    "sawatdee": "sawasdee",
    "sa wat dee": "sawasdee",
    "kop khun": "khob khun",
    "kob kun": "khob khun",

    # Common Misspellings
    "tie land": "thailand",
    "thai land": "thailand",
    "ty land": "thailand",
    "bangkok": "bangkok",
    "bang cock": "bangkok",
    "bang kok": "bangkok",
}

# Phonetic patterns that indicate Thai place names (regex)
THAI_PHONETIC_PATTERNS = [
    (r"\bcal\s*sock\b", "khao sok"),
    (r"\bcow\s*sock\b", "khao sok"),
    (r"\bka[ow]\s*s[oa][ck]k?\b", "khao sok"),
    (r"\bcal\s*san\b", "khao san"),
    (r"\bcow\s*san\b", "khao san"),
    (r"\bka[ow]\s*san\b", "khao san"),
    (r"\bp[uo]+\s*ket\b", "phuket"),
    (r"\bf[uo]+\s*ket\b", "phuket"),
    (r"\bch[aie]+ng?\s*m[aiy]+\b", "chiang mai"),
    (r"\bch[aie]+ng?\s*r[aiy]+\b", "chiang rai"),
    (r"\bp[ea]+\s*t[ao]+ng\b", "patong"),
    (r"\br[aiy]+\s*l[aey]+\b", "railay"),
    (r"\ba[oy]+\s*nang\b", "ao nang"),
    (r"\bp[h]?[ie]+\s*p[h]?[ie]+\b", "phi phi"),
    (r"\bk[o]h?\s*sam[ou]+[ie]?\b", "koh samui"),
    (r"\bk[o]h?\s*p[h]?a?ngan\b", "koh phangan"),
    (r"\bk[o]h?\s*tao\b", "koh tao"),
    (r"\bk[o]h?\s*lanta\b", "koh lanta"),
    (r"\bk[o]h?\s*chang\b", "koh chang"),
    (r"\bp[h]?ang?\s*n?ga\b", "phang nga"),
    (r"\ba\s*?yut+h?a\s*?ya\b", "ayutthaya"),
    (r"\berr?[ai]\s*w[ao]n\b", "erawan"),
]

# Known Thai place names for validation (correct spellings)
KNOWN_THAI_PLACES = {
    # National Parks
    "khao sok", "khao sok national park", "khao yai", "khao yai national park",
    "erawan", "erawan falls", "erawan national park", "doi inthanon",

    # Bangkok
    "bangkok", "khao san road", "khao san", "chatuchak", "chatuchak market",
    "lumpini park", "lumpini", "siam", "siam paragon", "mbk", "sukhumvit",
    "silom", "pratunam", "asiatique", "victory monument", "wat pho",
    "wat arun", "grand palace", "wat phra kaew", "emerald buddha temple",
    "chinatown bangkok", "yaowarat",

    # Phuket
    "phuket", "patong", "patong beach", "kata", "kata beach", "karon",
    "karon beach", "rawai", "nai harn", "big buddha phuket", "phang nga",
    "phang nga bay", "james bond island", "old phuket town",

    # Chiang Mai
    "chiang mai", "doi suthep", "wat phra that doi suthep", "nimmanhaemin",
    "nimman", "old city", "tha phae gate", "tha phae", "sunday walking street",
    "night bazaar", "elephant nature park", "bua tong sticky waterfalls",
    "pai", "mae hong son",

    # Chiang Rai
    "chiang rai", "wat rong khun", "white temple", "wat rong suea ten",
    "blue temple", "baan dam museum", "black house", "golden triangle",

    # Krabi & Islands
    "krabi", "railay beach", "railay", "ao nang", "phi phi islands",
    "phi phi", "maya bay", "koh lanta", "tiger cave temple", "krabi town",

    # Gulf Islands
    "koh samui", "koh phangan", "koh tao", "koh chang", "haad rin",
    "full moon party", "ang thong national park", "chaweng", "lamai",

    # Pattaya
    "pattaya", "walking street pattaya", "sanctuary of truth",

    # Central Thailand
    "ayutthaya", "ayutthaya historical park", "hua hin", "kanchanaburi",
    "bridge over the river kwai", "river kwai", "death railway",

    # Isan
    "isan", "korat", "nakhon ratchasima", "khon kaen", "udon thani",
    "ubon ratchathani",
}


# =============================================================================
# Transcript Corrector Class
# =============================================================================

class TranscriptCorrector:
    """
    Multi-layer transcript corrector for Thai place names.

    Provides three correction layers:
    1. Dictionary-based corrections (instant, free)
    2. Fuzzy matching (fast, free)
    3. LLM proofreading (accurate, costs ~$0.001)

    Usage:
        corrector = TranscriptCorrector()
        corrected = corrector.correct_transcript(segments)
    """

    def __init__(
        self,
        use_dictionary: bool = True,
        use_fuzzy: bool = True,
        use_llm: bool = False,
        fuzzy_threshold: float = 0.85,
        llm_model: str = "gemini-2.0-flash"
    ):
        """
        Initialize the transcript corrector.

        Args:
            use_dictionary: Enable dictionary-based corrections (default: True)
            use_fuzzy: Enable fuzzy matching corrections (default: True)
            use_llm: Enable LLM proofreading (default: False - enable for accuracy)
            fuzzy_threshold: Minimum similarity for fuzzy matches (default: 0.85)
            llm_model: Model to use for LLM proofreading
        """
        self.use_dictionary = use_dictionary
        self.use_fuzzy = use_fuzzy
        self.use_llm = use_llm
        self.fuzzy_threshold = fuzzy_threshold
        self.llm_model = llm_model

        # Compile regex patterns for efficiency
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in THAI_PHONETIC_PATTERNS
        ]

        # Statistics tracking
        self.stats = {
            'total_segments': 0,
            'dictionary_corrections': 0,
            'fuzzy_corrections': 0,
            'pattern_corrections': 0,
            'llm_corrections': 0,
            'corrections_made': []
        }

        logger.info(f"TranscriptCorrector initialized: dictionary={use_dictionary}, fuzzy={use_fuzzy}, llm={use_llm}")

    def reset_stats(self):
        """Reset correction statistics."""
        self.stats = {
            'total_segments': 0,
            'dictionary_corrections': 0,
            'fuzzy_corrections': 0,
            'pattern_corrections': 0,
            'llm_corrections': 0,
            'corrections_made': []
        }

    def _dictionary_correct(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Apply dictionary-based corrections.

        Args:
            text: Input text

        Returns:
            Tuple of (corrected_text, list_of_corrections)
        """
        corrections = []
        corrected = text.lower()

        for wrong, correct in THAI_PLACE_CORRECTIONS.items():
            if wrong in corrected:
                # Use word boundary matching for accuracy
                pattern = r'\b' + re.escape(wrong) + r'\b'
                if re.search(pattern, corrected, re.IGNORECASE):
                    corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)
                    corrections.append({
                        'type': 'dictionary',
                        'original': wrong,
                        'corrected': correct
                    })

        # Restore original case where possible
        if corrections:
            # Simple title case for place names
            words = corrected.split()
            result_words = []
            for i, word in enumerate(words):
                # Check if this word is at start of sentence or is a proper noun
                if word in KNOWN_THAI_PLACES or i == 0:
                    result_words.append(word.title())
                else:
                    # Preserve original case from input
                    orig_words = text.split()
                    if i < len(orig_words):
                        if orig_words[i][0].isupper():
                            result_words.append(word.capitalize())
                        else:
                            result_words.append(word)
                    else:
                        result_words.append(word)
            corrected = ' '.join(result_words)
        else:
            corrected = text  # No changes, keep original

        return corrected, corrections

    def _pattern_correct(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Apply regex pattern corrections.

        Args:
            text: Input text

        Returns:
            Tuple of (corrected_text, list_of_corrections)
        """
        corrections = []
        corrected = text

        for pattern, replacement in self._compiled_patterns:
            match = pattern.search(corrected)
            if match:
                original = match.group(0)
                corrected = pattern.sub(replacement.title(), corrected)
                corrections.append({
                    'type': 'pattern',
                    'original': original,
                    'corrected': replacement.title()
                })

        return corrected, corrections

    def _fuzzy_correct(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Apply fuzzy matching corrections for unknown misspellings.

        Args:
            text: Input text

        Returns:
            Tuple of (corrected_text, list_of_corrections)
        """
        corrections = []
        words = text.split()
        corrected_words = []

        for word in words:
            word_lower = word.lower()
            best_match = None
            best_score = 0

            # Check against known Thai places
            for place in KNOWN_THAI_PLACES:
                # Only check single-word places for word matching
                if ' ' not in place:
                    score = SequenceMatcher(None, word_lower, place).ratio()
                    if score > best_score and score >= self.fuzzy_threshold:
                        best_score = score
                        best_match = place

            if best_match and word_lower != best_match:
                # Preserve original case pattern
                if word[0].isupper():
                    corrected_word = best_match.title()
                else:
                    corrected_word = best_match

                corrected_words.append(corrected_word)
                corrections.append({
                    'type': 'fuzzy',
                    'original': word,
                    'corrected': corrected_word,
                    'score': best_score
                })
            else:
                corrected_words.append(word)

        return ' '.join(corrected_words), corrections

    def _llm_proofread(
        self,
        segments: List[Dict[str, Any]],
        video_title: Optional[str] = None,
        video_description: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict]]:
        """
        Use LLM to proofread and correct Thai place names.

        Args:
            segments: List of transcript segments
            video_title: Optional video title for context
            video_description: Optional description for context

        Returns:
            Tuple of (corrected_segments, list_of_corrections)
        """
        try:
            import google.generativeai as genai
            from dotenv import load_dotenv

            load_dotenv()
            api_key = os.getenv('GEMINI_API_KEY')

            if not api_key:
                logger.warning("GEMINI_API_KEY not set, skipping LLM proofreading")
                return segments, []

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.llm_model)

            # Combine segments into text blocks (batch for efficiency)
            full_text = ' '.join(seg.get('text', '') for seg in segments)

            # Build context
            context_parts = []
            if video_title:
                context_parts.append(f"Video Title: {video_title}")
            if video_description:
                context_parts.append(f"Description: {video_description[:500]}")

            context = '\n'.join(context_parts) if context_parts else "Travel video about Thailand"

            prompt = f"""You are a Thailand travel expert. Review this transcript and correct ONLY Thai place name spelling errors.

CONTEXT:
{context}

TRANSCRIPT:
{full_text[:4000]}

COMMON ERRORS TO FIX:
- "Calsock" or "Cal sock" → "Khao Sok"
- "Pooket" or "Foo ket" → "Phuket"
- "Cow san" → "Khao San"
- "Chang mai" → "Chiang Mai"
- Phonetic misspellings of Thai locations

RULES:
1. ONLY fix Thai place name spelling errors
2. Keep all other text exactly as-is
3. Preserve punctuation and formatting
4. If unsure, don't change it

Return the corrected transcript. If no corrections needed, return "NO_CORRECTIONS_NEEDED"."""

            response = model.generate_content(prompt)
            corrected_text = response.text.strip()

            if corrected_text == "NO_CORRECTIONS_NEEDED":
                return segments, []

            # Parse corrections and apply to segments
            corrections = []

            # Simple detection of what changed
            if corrected_text != full_text:
                corrections.append({
                    'type': 'llm',
                    'original_length': len(full_text),
                    'corrected_length': len(corrected_text),
                    'model': self.llm_model
                })

                # Redistribute corrected text back to segments
                # This is a simplified approach - keeps segment timing intact
                corrected_segments = []
                remaining_text = corrected_text

                for seg in segments:
                    orig_len = len(seg.get('text', ''))
                    new_seg = seg.copy()

                    # Take proportional amount of corrected text
                    if remaining_text:
                        # Find natural break point
                        target_len = min(orig_len + 20, len(remaining_text))

                        # Look for sentence/phrase boundary
                        cut_point = target_len
                        for i in range(target_len, max(orig_len - 20, 0), -1):
                            if i < len(remaining_text) and remaining_text[i] in '.!?, ':
                                cut_point = i + 1
                                break

                        new_seg['text'] = remaining_text[:cut_point].strip()
                        new_seg['original_text'] = seg.get('text', '')
                        remaining_text = remaining_text[cut_point:].strip()

                    corrected_segments.append(new_seg)

                return corrected_segments, corrections

            return segments, []

        except ImportError:
            logger.warning("google-generativeai not installed, skipping LLM proofreading")
            return segments, []
        except Exception as e:
            logger.error(f"LLM proofreading failed: {e}")
            return segments, []

    def correct_text(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Correct a single text string using all enabled correction layers.

        Args:
            text: Input text to correct

        Returns:
            Tuple of (corrected_text, list_of_all_corrections)
        """
        all_corrections = []
        corrected = text

        # Layer 1: Dictionary corrections
        if self.use_dictionary:
            corrected, dict_corrections = self._dictionary_correct(corrected)
            all_corrections.extend(dict_corrections)
            self.stats['dictionary_corrections'] += len(dict_corrections)

        # Layer 2: Pattern corrections
        if self.use_dictionary:  # Patterns are part of dictionary layer
            corrected, pattern_corrections = self._pattern_correct(corrected)
            all_corrections.extend(pattern_corrections)
            self.stats['pattern_corrections'] += len(pattern_corrections)

        # Layer 3: Fuzzy matching
        if self.use_fuzzy:
            corrected, fuzzy_corrections = self._fuzzy_correct(corrected)
            all_corrections.extend(fuzzy_corrections)
            self.stats['fuzzy_corrections'] += len(fuzzy_corrections)

        return corrected, all_corrections

    def correct_transcript(
        self,
        segments: List[Dict[str, Any]],
        video_title: Optional[str] = None,
        video_description: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Correct all segments in a transcript.

        Args:
            segments: List of transcript segment dicts with 'text' key
            video_title: Optional video title for LLM context
            video_description: Optional description for LLM context

        Returns:
            List of corrected segments (original_text preserved if changed)
        """
        self.reset_stats()
        self.stats['total_segments'] = len(segments)

        logger.info(f"Correcting transcript with {len(segments)} segments")

        corrected_segments = []

        # Apply dictionary and fuzzy corrections to each segment
        for segment in segments:
            text = segment.get('text', '')
            corrected_text, corrections = self.correct_text(text)

            new_segment = segment.copy()
            if corrected_text != text:
                new_segment['text'] = corrected_text
                new_segment['original_text'] = text
                self.stats['corrections_made'].extend(corrections)

            corrected_segments.append(new_segment)

        # Apply LLM proofreading if enabled (batch for efficiency)
        if self.use_llm:
            corrected_segments, llm_corrections = self._llm_proofread(
                corrected_segments,
                video_title=video_title,
                video_description=video_description
            )
            self.stats['llm_corrections'] += len(llm_corrections)
            self.stats['corrections_made'].extend(llm_corrections)

        # Log summary
        total_corrections = (
            self.stats['dictionary_corrections'] +
            self.stats['pattern_corrections'] +
            self.stats['fuzzy_corrections'] +
            self.stats['llm_corrections']
        )

        if total_corrections > 0:
            logger.info(f"✅ Made {total_corrections} corrections:")
            logger.info(f"   Dictionary: {self.stats['dictionary_corrections']}")
            logger.info(f"   Pattern: {self.stats['pattern_corrections']}")
            logger.info(f"   Fuzzy: {self.stats['fuzzy_corrections']}")
            logger.info(f"   LLM: {self.stats['llm_corrections']}")
        else:
            logger.info("✅ No corrections needed")

        return corrected_segments

    def get_stats(self) -> Dict[str, Any]:
        """Get correction statistics."""
        return self.stats.copy()


# =============================================================================
# Whisper Prompt for Thai Place Names
# =============================================================================

def get_whisper_thailand_prompt() -> str:
    """
    Get a prompt to prime Whisper for Thai place name recognition.

    Use with whisper.transcribe(audio, initial_prompt=get_whisper_thailand_prompt())

    Returns:
        Prompt string with common Thai place names
    """
    return """This is a travel video about Thailand. Common places mentioned include:
Bangkok, Khao San Road, Chatuchak Market, Grand Palace, Wat Pho, Wat Arun, Sukhumvit, Silom, Siam, Asiatique, Lumpini Park.
Phuket, Patong Beach, Kata Beach, Karon Beach, Phang Nga Bay, James Bond Island.
Chiang Mai, Doi Suthep, Nimman, Tha Phae Gate, Night Bazaar, Elephant Nature Park, Pai.
Chiang Rai, White Temple Wat Rong Khun, Blue Temple, Black House.
Krabi, Railay Beach, Ao Nang, Phi Phi Islands, Maya Bay, Koh Lanta.
Koh Samui, Koh Phangan, Full Moon Party, Koh Tao, Koh Chang.
Khao Sok National Park, Khao Yai, Erawan Falls.
Ayutthaya, Kanchanaburi, River Kwai, Hua Hin.
Thai food: Pad Thai, Tom Yum, Khao Soi, Som Tam, Massaman curry, Mango sticky rice.
Thai words: Sawasdee, Khob Khun, Baht, Tuk Tuk, Songthaew."""


# =============================================================================
# Convenience Functions
# =============================================================================

def correct_transcript_simple(
    segments: List[Dict[str, Any]],
    use_llm: bool = False
) -> List[Dict[str, Any]]:
    """
    Simple function to correct a transcript.

    Args:
        segments: List of transcript segments
        use_llm: Whether to use LLM proofreading (costs ~$0.001)

    Returns:
        Corrected segments
    """
    corrector = TranscriptCorrector(
        use_dictionary=True,
        use_fuzzy=True,
        use_llm=use_llm
    )
    return corrector.correct_transcript(segments)


def correct_text_simple(text: str) -> str:
    """
    Simple function to correct a single text string.

    Args:
        text: Input text

    Returns:
        Corrected text
    """
    corrector = TranscriptCorrector(
        use_dictionary=True,
        use_fuzzy=True,
        use_llm=False
    )
    corrected, _ = corrector.correct_text(text)
    return corrected


# =============================================================================
# Test Function
# =============================================================================

def test_transcript_corrector():
    """Test the transcript corrector with sample data."""
    logger.info("=" * 80)
    logger.info("TRANSCRIPT CORRECTOR TEST")
    logger.info("=" * 80)

    # Sample segments with common errors
    test_segments = [
        {"text": "Welcome to Tie land, we're going to Calsock National Park", "start": 0.0, "duration": 4.0},
        {"text": "Next stop is Pooket where we'll visit Patong Beach", "start": 4.0, "duration": 3.5},
        {"text": "In Chang Mai, don't miss Doi Suthep temple", "start": 7.5, "duration": 3.0},
        {"text": "The Cow San Road in Bangkok is amazing for nightlife", "start": 10.5, "duration": 3.5},
        {"text": "We took a day trip to the Fee Fee islands", "start": 14.0, "duration": 3.0},
        {"text": "The Full Moon Party at Ko Pangan was incredible", "start": 17.0, "duration": 3.5},
        {"text": "Try the Pad Tie and Tom Yang soup!", "start": 20.5, "duration": 2.5},
    ]

    # Test with dictionary + fuzzy only
    corrector = TranscriptCorrector(
        use_dictionary=True,
        use_fuzzy=True,
        use_llm=False
    )

    logger.info("\n📝 Original Segments:")
    for seg in test_segments:
        logger.info(f"  {seg['text']}")

    corrected = corrector.correct_transcript(test_segments)

    logger.info("\n✅ Corrected Segments:")
    for seg in corrected:
        text = seg['text']
        original = seg.get('original_text')
        if original:
            logger.info(f"  {text}")
            logger.info(f"    (was: {original})")
        else:
            logger.info(f"  {text}")

    logger.info("\n📊 Statistics:")
    stats = corrector.get_stats()
    logger.info(f"  Total segments: {stats['total_segments']}")
    logger.info(f"  Dictionary corrections: {stats['dictionary_corrections']}")
    logger.info(f"  Pattern corrections: {stats['pattern_corrections']}")
    logger.info(f"  Fuzzy corrections: {stats['fuzzy_corrections']}")

    logger.info("\n" + "=" * 80)
    logger.info("Test complete!")

    return corrected


if __name__ == '__main__':
    from src.utils.logging import setup_logging
    setup_logging(log_level='INFO')
    test_transcript_corrector()
