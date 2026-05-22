# utils/helpers.py
#
# General-purpose utility functions used across the application.
# ---------------------------------------------------------------------------

import logging
import os
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ID & File Utilities
# ---------------------------------------------------------------------------

def generate_uuid() -> str:
    """
    Generates a new UUID4 string.

    Returns:
        UUID string e.g. "550e8400-e29b-41d4-a716-446655440000"
    """
    return str(uuid.uuid4())


def generate_audio_filename(extension: str = "wav") -> str:
    """
    Generates a unique filename for a TTS audio file.

    Args:
        extension : File extension without dot (default: "wav")

    Returns:
        Filename string e.g. "audio_550e8400.wav"
    """
    ext = extension.lstrip(".")
    return f"audio_{uuid.uuid4().hex[:8]}.{ext}"


def generate_upload_filename(original_filename: str) -> str:
    """
    Generates a unique filename for an uploaded audio file,
    preserving the original extension.

    Args:
        original_filename : Original filename from upload

    Returns:
        Unique filename string.
    """
    ext = os.path.splitext(original_filename)[-1] or ".webm"
    return f"upload_{uuid.uuid4().hex}{ext}"


def get_audio_url(filename: str, base_url: Optional[str] = None) -> str:
    """
    Builds the public URL for a generated audio file.

    Args:
        filename : Audio filename (e.g. "audio_abc123.wav")
        base_url : Optional base URL prefix (reads BACKEND_URL from env)

    Returns:
        Full URL string e.g. "http://localhost:8000/audio/audio_abc123.wav"
    """
    base = base_url or os.getenv("BACKEND_URL", "http://localhost:8000")
    return f"{base}/audio/{filename}"


# ---------------------------------------------------------------------------
# Session Utilities
# ---------------------------------------------------------------------------

def calculate_average_score(scores: list[float]) -> float:
    """
    Calculates the average of a list of scores.

    Args:
        scores : List of float scores

    Returns:
        Rounded average float, or 0.0 if list is empty.
    """
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 2)


def determine_hire_recommendation(overall_score: float) -> str:
    """
    Determines hire recommendation based on overall score.

    Args:
        overall_score : Float between 0.0 and 10.0

    Returns:
        "HIRE" | "MAYBE" | "NO HIRE"
    """
    if overall_score >= 7.0:
        return "HIRE"
    elif overall_score >= 5.0:
        return "MAYBE"
    else:
        return "NO HIRE"


def format_duration(started_at: datetime, completed_at: datetime) -> str:
    """
    Formats the duration between two datetimes into a human-readable string.

    Args:
        started_at   : Session start datetime
        completed_at : Session end datetime

    Returns:
        String e.g. "12 minutes 34 seconds"
    """
    delta = completed_at - started_at
    total_seconds = int(delta.total_seconds())
    minutes, seconds = divmod(abs(total_seconds), 60)
    hours, minutes   = divmod(minutes, 60)

    if hours > 0:
        return f"{hours} hour{'s' if hours != 1 else ''} " \
               f"{minutes} minute{'s' if minutes != 1 else ''}"
    elif minutes > 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''} " \
               f"{seconds} second{'s' if seconds != 1 else ''}"
    else:
        return f"{seconds} second{'s' if seconds != 1 else ''}"


# ---------------------------------------------------------------------------
# Validation Utilities
# ---------------------------------------------------------------------------

def is_valid_uuid(value: str) -> bool:
    """
    Checks whether a string is a valid UUID4.

    Args:
        value : String to check

    Returns:
        True if valid UUID, False otherwise.
    """
    try:
        uuid.UUID(str(value), version=4)
        return True
    except ValueError:
        return False


def is_non_empty(value: Optional[str]) -> bool:
    """
    Returns True if value is a non-None, non-empty string.

    Args:
        value : String to check

    Returns:
        bool
    """
    return bool(value and value.strip())


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamps a float value between min_val and max_val.

    Args:
        value   : Input value
        min_val : Minimum allowed value
        max_val : Maximum allowed value

    Returns:
        Clamped float.
    """
    return max(min_val, min(max_val, value))


# ---------------------------------------------------------------------------
# Logging Utilities
# ---------------------------------------------------------------------------

def log_interview_event(
    session_id: str,
    event: str,
    extra: Optional[dict] = None,
) -> None:
    """
    Logs a structured interview event for traceability.

    Args:
        session_id : Active session ID
        event      : Event name e.g. "question_generated"
        extra      : Optional dict of additional fields
    """
    log_data = {
        "session_id": session_id,
        "event":      event,
        "timestamp":  datetime.utcnow().isoformat(),
    }
    if extra:
        log_data.update(extra)

    logger.info(f"[INTERVIEW EVENT] {log_data}")


def mask_api_key(key: Optional[str]) -> str:
    """
    Masks an API key for safe logging.
    Shows first 4 and last 4 characters only.

    Args:
        key : API key string

    Returns:
        Masked string e.g. "gsk_****...****xYz1"
    """
    if not key or len(key) < 10:
        return "****"
    return f"{key[:4]}****...****{key[-4:]}"


# ---------------------------------------------------------------------------
# Environment Utilities
# ---------------------------------------------------------------------------

def get_env_or_raise(key: str) -> str:
    """
    Gets an environment variable or raises RuntimeError if not set.

    Args:
        key : Environment variable name

    Returns:
        Value string.

    Raises:
        RuntimeError if variable is not set.
    """
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file."
        )
    return value


def get_env_int(key: str, default: int) -> int:
    """
    Gets an environment variable as an integer.

    Args:
        key     : Environment variable name
        default : Default value if not set or invalid

    Returns:
        Integer value.
    """
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid integer value for env var '{key}', "
            f"using default={default}"
        )
        return default


def get_env_float(key: str, default: float) -> float:
    """
    Gets an environment variable as a float.

    Args:
        key     : Environment variable name
        default : Default value if not set or invalid

    Returns:
        Float value.
    """
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid float value for env var '{key}', "
            f"using default={default}"
        )
        return default