# services/tts_service.py
#
# Text-to-Speech using Coqui TTS (local model).
# Falls back to pyttsx3 if Coqui is unavailable.
# Converts question text to a .wav audio file.
# ---------------------------------------------------------------------------

import asyncio
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTS Backend Loader
# Tries Coqui TTS first, falls back to pyttsx3
# ---------------------------------------------------------------------------

class TTSBackend:
    """
    Detects and loads the best available TTS backend.

    Priority:
        1. Coqui TTS  (high quality, local neural TTS)
        2. pyttsx3    (lightweight, offline fallback)
    """

    def __init__(self):
        self.backend_name: str           = ""
        self.coqui_tts                   = None
        self.pyttsx3_engine              = None
        self._load_backend()

    def _load_backend(self) -> None:
        """
        Attempts to load Coqui TTS first.
        Falls back to pyttsx3 if Coqui is not installed or fails.
        """
        # -- Try Coqui TTS
        try:
            from TTS.api import TTS  # type: ignore

            model_name = os.getenv(
                "TTS_MODEL",
                "tts_models/en/ljspeech/tacotron2-DDC",
            )
            use_cuda = os.getenv("TTS_USE_CUDA", "false").lower() == "true"

            logger.info(f"Loading Coqui TTS model: {model_name} ...")

            tts = TTS(model_name=model_name, progress_bar=False)

            if use_cuda:
                try:
                    tts = tts.to("cuda")
                    logger.info("Coqui TTS running on CUDA (GPU).")
                except Exception:
                    logger.warning("CUDA not available — using CPU.")

            self.coqui_tts    = tts
            self.backend_name = "coqui"
            logger.info(
                f"Coqui TTS backend loaded | model={model_name}"
            )
            return

        except ImportError:
            logger.warning(
                "Coqui TTS not installed (TTS package missing). "
                "Falling back to pyttsx3."
            )
        except Exception as e:
            logger.warning(
                f"Coqui TTS failed to load: {e}. "
                "Falling back to pyttsx3."
            )

        # -- Fallback: pyttsx3
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()

            # Configure voice properties
            rate  = int(os.getenv("TTS_RATE", "150"))    # words per minute
            volume= float(os.getenv("TTS_VOLUME", "1.0"))# 0.0 – 1.0

            engine.setProperty("rate",   rate)
            engine.setProperty("volume", volume)

            # Try to set a preferred voice
            voices = engine.getProperty("voices")
            preferred_voice_index = int(os.getenv("TTS_VOICE_INDEX", "0"))
            if voices and preferred_voice_index < len(voices):
                engine.setProperty(
                    "voice",
                    voices[preferred_voice_index].id,
                )

            self.pyttsx3_engine = engine
            self.backend_name   = "pyttsx3"
            logger.info("pyttsx3 TTS backend loaded (fallback mode).")
            return

        except ImportError:
            logger.error(
                "Neither Coqui TTS nor pyttsx3 is installed. "
                "Install at least one: `uv add TTS` or `uv add pyttsx3`."
            )
        except Exception as e:
            logger.error(f"pyttsx3 failed to load: {e}")

        # -- No backend available
        self.backend_name = "none"
        logger.error(
            "No TTS backend available. "
            "Text-to-audio endpoint will not work."
        )

    def is_available(self) -> bool:
        return self.backend_name != "none"

    def synthesize_sync(self, text: str, output_path: str) -> None:
        """
        Blocking synthesis call — runs inside ThreadPoolExecutor.
        Dispatches to the loaded backend.
        """
        if self.backend_name == "coqui":
            self._synthesize_coqui(text, output_path)
        elif self.backend_name == "pyttsx3":
            self._synthesize_pyttsx3(text, output_path)
        else:
            raise RuntimeError(
                "No TTS backend is available. "
                "Install Coqui TTS or pyttsx3."
            )

    def _synthesize_coqui(self, text: str, output_path: str) -> None:
        """
        Synthesizes text using Coqui TTS and saves to output_path.
        """
        self.coqui_tts.tts_to_file(
            text      = text,
            file_path = output_path,
        )

    def _synthesize_pyttsx3(self, text: str, output_path: str) -> None:
        """
        Synthesizes text using pyttsx3 and saves to output_path.
        pyttsx3 saves as .wav natively.
        """
        engine = self.pyttsx3_engine

        # pyttsx3 requires save_to_file then runAndWait
        engine.save_to_file(text, output_path)
        engine.runAndWait()


# ---------------------------------------------------------------------------
# Singleton backend instance
# Loaded once at module import time — shared across all requests
# ---------------------------------------------------------------------------
_tts_backend: Optional[TTSBackend] = None


def get_tts_backend() -> TTSBackend:
    global _tts_backend
    if _tts_backend is None:
        _tts_backend = TTSBackend()
    return _tts_backend


# ---------------------------------------------------------------------------
# TTSService — async wrapper used by routes and nodes
# ---------------------------------------------------------------------------

class TTSService:
    """
    Async TTS service that wraps TTSBackend.

    All synthesis calls run in a ThreadPoolExecutor so the
    FastAPI event loop is never blocked.

    Usage:
        tts = TTSService()
        path = await tts.synthesize(text="Hello!", output_path="audio/q1.wav")
    """

    def __init__(self):
        self.backend = get_tts_backend()
        logger.info(
            f"TTSService initialized | backend={self.backend.backend_name}"
        )

    # ------------------------------------------------------------------
    # Primary method — synthesize text to file
    # ------------------------------------------------------------------
    async def synthesize(
        self,
        text: str,
        output_path: str,
    ) -> str:
        """
        Converts text to speech and saves it as a .wav file.

        The synthesis runs in a thread pool to avoid blocking
        the FastAPI async event loop.

        Args:
            text        : Text to convert to speech
            output_path : Full path where the .wav will be saved

        Returns:
            output_path — path of the saved audio file.

        Raises:
            ValueError  : If text is empty.
            RuntimeError: If no TTS backend is available or synthesis fails.
        """
        # -- Validate input
        text = text.strip()
        if not text:
            raise ValueError("Cannot synthesize empty text.")

        if not self.backend.is_available():
            raise RuntimeError(
                "No TTS backend is available. "
                "Install Coqui TTS (`uv add TTS`) or pyttsx3 (`uv add pyttsx3`)."
            )

        # -- Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        logger.info(
            f"TTSService.synthesize | backend={self.backend.backend_name} | "
            f"chars={len(text)} | output={output_path}"
        )

        # -- Run blocking TTS in thread pool
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,                          # default ThreadPoolExecutor
                self.backend.synthesize_sync,
                text,
                output_path,
            )
        except Exception as e:
            logger.error(
                f"TTS synthesis failed | backend={self.backend.backend_name} "
                f"| error={e}"
            )
            raise RuntimeError(f"TTS synthesis failed: {e}") from e

        # -- Verify output file was created
        if not os.path.exists(output_path):
            raise RuntimeError(
                f"TTS completed but output file not found: {output_path}"
            )

        file_size = os.path.getsize(output_path)
        logger.info(
            f"TTS complete | backend={self.backend.backend_name} | "
            f"file={output_path} | size={file_size} bytes"
        )

        return output_path

    # ------------------------------------------------------------------
    # Synthesize to bytes (for streaming or in-memory use)
    # ------------------------------------------------------------------
    async def synthesize_to_bytes(self, text: str) -> bytes:
        """
        Synthesizes text and returns raw audio bytes.
        Useful for streaming audio responses.

        Args:
            text : Text to synthesize

        Returns:
            Raw .wav audio bytes.
        """
        text = text.strip()
        if not text:
            raise ValueError("Cannot synthesize empty text.")

        # Write to a temp file then read back
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
            dir="audio",
        ) as tmp:
            tmp_path = tmp.name

        try:
            await self.synthesize(text=text, output_path=tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
                logger.debug(f"Temp TTS file cleaned up: {tmp_path}")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def health(self) -> dict:
        """
        Returns TTS backend health status.
        Called by /health endpoint or monitoring.
        """
        return {
            "tts_available": self.backend.is_available(),
            "tts_backend":   self.backend.backend_name,
            "model": os.getenv(
                "TTS_MODEL",
                "tts_models/en/ljspeech/tacotron2-DDC"
                if self.backend.backend_name == "coqui"
                else "pyttsx3-default",
            ),
        }

    # ------------------------------------------------------------------
    # List available Coqui models (dev utility)
    # ------------------------------------------------------------------
    @staticmethod
    def list_coqui_models() -> list[str]:
        """
        Lists all available Coqui TTS models.
        Useful during development to choose the right model.

        Returns:
            List of model name strings, or empty list if Coqui not installed.
        """
        try:
            from TTS.api import TTS  # type: ignore
            return TTS().list_models()
        except Exception as e:
            logger.warning(f"Could not list Coqui models: {e}")
            return []