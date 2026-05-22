# services/stt_service.py
#
# Speech-to-Text using Sarvam AI API.
# Replaces OpenAI Whisper with Sarvam's cloud STT endpoint.
# API: https://api.sarvam.ai/speech-to-text
# ---------------------------------------------------------------------------

import asyncio
import logging
import os
import aiohttp
import aiofiles

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


class STTService:
    """
    Wraps Sarvam AI Speech-to-Text API.
    Sends audio files to Sarvam's cloud endpoint and returns transcripts.

    Supported formats : wav, mp3, webm, ogg, m4a, flac
    Max file size     : 50 MB (enforced by audio_routes.py)
    Language          : Configurable via SARVAM_LANGUAGE env var
    """

    def __init__(self):
        self.api_key = os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "SARVAM_API_KEY is not set. "
                "Add it to your .env file.\n"
                "Get your key at: https://dashboard.sarvam.ai"
            )

        self.stt_url  = SARVAM_STT_URL
        self.language = os.getenv("SARVAM_LANGUAGE", "en-IN")
        self.model    = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")

        logger.info(
            f"STTService initialized | "
            f"provider=Sarvam AI | "
            f"model={self.model} | "
            f"language={self.language}"
        )

    # ------------------------------------------------------------------
    # Primary transcription method
    # ------------------------------------------------------------------
    async def transcribe(self, file_path: str) -> str:
        """
        Transcribes the audio file at `file_path` using Sarvam AI STT.

        Reads the file asynchronously and POSTs it as multipart/form-data
        to the Sarvam API. Returns the transcribed text string.

        Args:
            file_path : Absolute or relative path to the audio file.

        Returns:
            Transcribed text string.

        Raises:
            FileNotFoundError : If the audio file does not exist.
            RuntimeError      : If the API call fails or returns an error.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Audio file not found: {file_path}"
            )

        file_size = os.path.getsize(file_path)
        logger.info(
            f"Sending to Sarvam STT | "
            f"file={file_path} | "
            f"size={file_size} bytes"
        )

        try:
            transcript = await self._call_sarvam_api(file_path)
        except Exception as e:
            logger.error(f"Sarvam STT failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

        logger.info(
            f"Sarvam STT complete | "
            f"chars={len(transcript)} | "
            f"preview={transcript[:80]}..."
        )
        return transcript

    # ------------------------------------------------------------------
    # Internal API call
    # ------------------------------------------------------------------
    async def _call_sarvam_api(self, file_path: str) -> str:
        """
        Sends the audio file to Sarvam STT API and parses the response.

        Sarvam API expects:
          - POST multipart/form-data
          - Field: file       → audio binary
          - Field: model      → model name e.g. "saarika:v2"
          - Field: language_code → e.g. "en-IN"
          - Header: api-subscription-key → your API key

        Returns:
            Transcribed text string.
        """
        filename     = os.path.basename(file_path)
        content_type = self._get_content_type(filename)

        headers = {
            "api-subscription-key": self.api_key,
        }

        # Read file asynchronously
        async with aiofiles.open(file_path, "rb") as f:
            audio_bytes = await f.read()

        # Build multipart form
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                name        = "file",
                value       = audio_bytes,
                filename    = filename,
                content_type= content_type,
            )
            form.add_field("model",         self.model)
            form.add_field("language_code", self.language)
            form.add_field("with_timestamps", "false")
            form.add_field("with_disfluencies", "false")

            async with session.post(
                self.stt_url,
                headers = headers,
                data    = form,
                timeout = aiohttp.ClientTimeout(total=120),  # 2 min timeout
            ) as response:

                # -- Handle non-200 responses
                if response.status != 200:
                    error_body = await response.text()
                    logger.error(
                        f"Sarvam STT API error | "
                        f"status={response.status} | "
                        f"body={error_body[:300]}"
                    )
                    raise RuntimeError(
                        f"Sarvam STT API returned {response.status}: "
                        f"{error_body[:200]}"
                    )

                # -- Parse JSON response
                data = await response.json()

        return self._parse_transcript(data)

    # ------------------------------------------------------------------
    # Response parser
    # ------------------------------------------------------------------
    def _parse_transcript(self, data: dict) -> str:
        """
        Parses Sarvam STT API JSON response.

        Sarvam response shape:
        {
            "transcript": "transcribed text here",
            "language_code": "en-IN",
            "request_id": "..."
        }

        Falls back gracefully if shape is unexpected.
        """
        # Primary field
        if "transcript" in data:
            return (data["transcript"] or "").strip()

        # Some versions return inside results array
        if "results" in data and isinstance(data["results"], list):
            texts = [
                r.get("transcript", "")
                for r in data["results"]
                if r.get("transcript")
            ]
            return " ".join(texts).strip()

        # Last resort — log full response and return empty
        logger.warning(
            f"Unexpected Sarvam STT response shape: "
            f"{str(data)[:300]}"
        )
        return ""

    # ------------------------------------------------------------------
    # Extended transcription with metadata
    # ------------------------------------------------------------------
    async def transcribe_with_metadata(self, file_path: str) -> dict:
        """
        Transcribes audio and returns text + language + request metadata.

        Useful for debugging or when you need language detection info.

        Args:
            file_path : Path to audio file.

        Returns:
            dict with keys: text, language_code, request_id
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Audio file not found: {file_path}"
            )

        filename     = os.path.basename(file_path)
        content_type = self._get_content_type(filename)

        headers = {
            "api-subscription-key": self.api_key,
        }

        async with aiofiles.open(file_path, "rb") as f:
            audio_bytes = await f.read()

        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field(
                name        = "file",
                value       = audio_bytes,
                filename    = filename,
                content_type= content_type,
            )
            form.add_field("model",            self.model)
            form.add_field("language_code",    self.language)
            form.add_field("with_timestamps",  "true")
            form.add_field("with_disfluencies","false")

            async with session.post(
                self.stt_url,
                headers = headers,
                data    = form,
                timeout = aiohttp.ClientTimeout(total=120),
            ) as response:

                if response.status != 200:
                    error_body = await response.text()
                    raise RuntimeError(
                        f"Sarvam STT API returned {response.status}: "
                        f"{error_body[:200]}"
                    )

                data = await response.json()

        return {
            "text":          self._parse_transcript(data),
            "language_code": data.get("language_code", self.language),
            "request_id":    data.get("request_id", ""),
            "raw":           data,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_content_type(filename: str) -> str:
        """
        Returns the correct MIME type for the audio file
        based on its extension.
        """
        ext_map = {
            ".wav":  "audio/wav",
            ".mp3":  "audio/mpeg",
            ".webm": "audio/webm",
            ".ogg":  "audio/ogg",
            ".m4a":  "audio/mp4",
            ".flac": "audio/flac",
            ".mp4":  "audio/mp4",
        }
        ext = os.path.splitext(filename)[-1].lower()
        return ext_map.get(ext, "audio/webm")   # default to webm for browser recordings

    def health(self) -> dict:
        """
        Returns STT service health info.
        """
        return {
            "stt_provider": "Sarvam AI",
            "stt_url":      self.stt_url,
            "model":        self.model,
            "language":     self.language,
            "api_key_set":  bool(self.api_key),
        }