# utils/parser.py
#
# Utility functions for safely parsing LLM outputs.
# LLMs sometimes wrap JSON in markdown fences or add preamble —
# these helpers handle all edge cases gracefully.
# ---------------------------------------------------------------------------

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Parsing
# ---------------------------------------------------------------------------

def parse_json_response(
    raw: str,
    fallback: Optional[dict] = None,
) -> dict:
    """
    Safely parses a JSON string returned by an LLM.

    Handles common LLM output quirks:
      - Wrapped in ```json ... ``` markdown fences
      - Wrapped in ``` ... ``` plain fences
      - Leading/trailing whitespace
      - Extra text before or after the JSON object

    Args:
        raw      : Raw string output from LLM
        fallback : Dict to return if parsing fails (default: {})

    Returns:
        Parsed dict, or fallback on failure.
    """
    if fallback is None:
        fallback = {}

    if not raw or not raw.strip():
        logger.warning("parse_json_response: empty input, returning fallback")
        return fallback

    cleaned = raw.strip()

    # -- Strip markdown code fences
    # Handles ```json\n...\n``` and ```\n...\n```
    fence_pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    fence_match = re.match(fence_pattern, cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # -- Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # -- Try extracting JSON object from mixed text
    # Finds the first {...} block in the string
    json_pattern = r"\{.*?\}"
    json_match = re.search(json_pattern, cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(
        f"parse_json_response: all parse attempts failed | "
        f"raw preview={raw[:200]!r}"
    )
    return fallback


def parse_score(raw_score: Any, default: float = 0.0) -> float:
    """
    Safely converts a raw score value to a float clamped between 0 and 10.

    Args:
        raw_score : Value from LLM (could be int, float, str)
        default   : Value to return if conversion fails

    Returns:
        Float between 0.0 and 10.0
    """
    try:
        score = float(raw_score)
        return round(max(0.0, min(10.0, score)), 2)
    except (TypeError, ValueError) as e:
        logger.warning(f"parse_score failed for {raw_score!r}: {e}")
        return default


def parse_hire_recommendation(raw: str) -> str:
    """
    Normalizes hire recommendation string to one of:
        HIRE | MAYBE | NO HIRE

    Handles case variations and whitespace.

    Args:
        raw : Raw recommendation string from LLM

    Returns:
        Normalized recommendation string.
    """
    if not raw:
        return "NO HIRE"

    normalized = raw.strip().upper()

    if normalized in {"HIRE", "YES", "RECOMMENDED", "STRONG HIRE"}:
        return "HIRE"
    elif normalized in {"MAYBE", "POSSIBLY", "BORDERLINE", "CONSIDER"}:
        return "MAYBE"
    else:
        return "NO HIRE"


# ---------------------------------------------------------------------------
# Text Cleaning
# ---------------------------------------------------------------------------

def clean_question_text(raw: str) -> str:
    """
    Cleans up LLM-generated question text.

    Removes:
      - Leading question numbers like "1." or "Q1:"
      - Extra whitespace and newlines
      - Surrounding quotes

    Args:
        raw : Raw question string from LLM

    Returns:
        Cleaned question string.
    """
    if not raw:
        return ""

    cleaned = raw.strip()

    # Remove leading numbering: "1.", "Q1:", "Question 1:"
    cleaned = re.sub(
        r"^(?:question\s*\d+[:.]?\s*|q\d+[:.]?\s*|\d+[.)]\s*)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove surrounding quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or \
       (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1]

    return cleaned.strip()


def clean_feedback_text(raw: str) -> str:
    """
    Cleans up LLM-generated feedback text.

    Args:
        raw : Raw feedback string from LLM

    Returns:
        Cleaned feedback string.
    """
    if not raw:
        return "No feedback provided."

    cleaned = raw.strip()

    # Remove surrounding quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or \
       (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1]

    return cleaned.strip()


def sanitize_text(text: str, max_length: int = 5000) -> str:
    """
    General-purpose text sanitizer.
    Strips leading/trailing whitespace and truncates to max_length.

    Args:
        text       : Input text
        max_length : Maximum allowed length (default 5000)

    Returns:
        Sanitized string.
    """
    if not text:
        return ""
    return text.strip()[:max_length]


# ---------------------------------------------------------------------------
# Response Validators
# ---------------------------------------------------------------------------

def validate_evaluation_response(data: dict) -> dict:
    """
    Validates and normalizes the evaluation JSON returned by the LLM.

    Expected keys: score, feedback
    Fills in defaults for missing or invalid fields.

    Args:
        data : Parsed dict from LLM

    Returns:
        Validated dict with guaranteed keys.
    """
    return {
        "score":    parse_score(data.get("score"), default=0.0),
        "feedback": clean_feedback_text(
            str(data.get("feedback", "No feedback provided."))
        ),
    }


def validate_report_response(data: dict) -> dict:
    """
    Validates and normalizes the report JSON returned by the LLM.

    Expected keys: overall_score, hire_recommendation, strengths, weaknesses
    Fills in defaults for missing or invalid fields.

    Args:
        data : Parsed dict from LLM

    Returns:
        Validated dict with guaranteed keys.
    """
    return {
        "overall_score": parse_score(
            data.get("overall_score"), default=0.0
        ),
        "hire_recommendation": parse_hire_recommendation(
            str(data.get("hire_recommendation", "NO HIRE"))
        ),
        "strengths": sanitize_text(
            str(data.get("strengths", "No strengths identified."))
        ),
        "weaknesses": sanitize_text(
            str(data.get("weaknesses", "No weaknesses identified."))
        ),
    }