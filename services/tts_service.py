# services/tts_service.py
#
# Robust Text-to-Speech Service
# --------------------------------------------
# Features:
#   - Coqui TTS support (high quality)
#   - Safe pyttsx3 fallback
#   - Thread-safe synthesis
#   - Fixes second-question audio issue
#   - Prevents pyttsx3 engine deadlocks
#   - Creates fresh pyttsx3 engine per request
#   - Waits for output file creation
# --------------------------------------------

import asyncio
import logging
import os
import tempfile
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTS Backend Loader
# ---------------------------------------------------------------------------

class TTSBackend:
    """
    Detects and loads the best available TTS backend.

    Priority:
        1. Coqui TTS
        2. pyttsx3
    """

    def __init__(self):
        self.backend_name: str = ""
        self.coqui_tts = None

        # Thread safety lock
        self.pyttsx3_lock = threading.Lock()

        self._load_backend()

    # -------------------------------------------------------------------
    # Backend loader
    # -------------------------------------------------------------------

    def _load_backend(self) -> None:

        # ---------------------------------------------------------------
        # Try Coqui TTS
        # ---------------------------------------------------------------
        try:
            from TTS.api import TTS  # type: ignore

            model_name = os.getenv(
                "TTS_MODEL",
                "tts_models/en/ljspeech/tacotron2-DDC",
            )

            use_cuda = (
                os.getenv("TTS_USE_CUDA", "false").lower() == "true"
            )

            logger.info(
                f"Loading Coqui TTS model: {model_name}"
            )

            tts = TTS(
                model_name=model_name,
                progress_bar=False,
            )

            if use_cuda:
                try:
                    tts = tts.to("cuda")
                    logger.info("Coqui TTS using CUDA")
                except Exception:
                    logger.warning(
                        "CUDA unavailable, using CPU"
                    )

            self.coqui_tts = tts
            self.backend_name = "coqui"

            logger.info(
                f"Coqui TTS backend loaded | model={model_name}"
            )

            return

        except ImportError:
            logger.warning(
                "Coqui TTS not installed. "
                "Falling back to pyttsx3."
            )

        except Exception as e:
            logger.warning(
                f"Coqui TTS failed: {e}. "
                "Falling back to pyttsx3."
            )

        # ---------------------------------------------------------------
        # Test pyttsx3 availability
        # ---------------------------------------------------------------
        try:
            import pyttsx3  # type: ignore

            test_engine = pyttsx3.init()
            test_engine.stop()

            self.backend_name = "pyttsx3"

            logger.info(
                "pyttsx3 TTS backend loaded (fallback mode)"
            )

            return

        except ImportError:
            logger.error("pyttsx3 not installed.")

        except Exception as e:
            logger.error(f"pyttsx3 init failed: {e}")

        # ---------------------------------------------------------------
        # No backend available
        # ---------------------------------------------------------------
        self.backend_name = "none"

        logger.error(
            "No TTS backend available."
        )

    # -------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------

    def is_available(self) -> bool:
        return self.backend_name != "none"

    # -------------------------------------------------------------------
    # Main synthesis dispatcher
    # -------------------------------------------------------------------

    def synthesize_sync(
        self,
        text: str,
        output_path: str,
    ) -> None:

        if self.backend_name == "coqui":
            self._synthesize_coqui(
                text,
                output_path,
            )

        elif self.backend_name == "pyttsx3":
            self._synthesize_pyttsx3(
                text,
                output_path,
            )

        else:
            raise RuntimeError(
                "No TTS backend available."
            )

    # -------------------------------------------------------------------
    # Coqui synthesis
    # -------------------------------------------------------------------

    def _synthesize_coqui(
        self,
        text: str,
        output_path: str,
    ) -> None:

        self.coqui_tts.tts_to_file(
            text=text,
            file_path=output_path,
        )

    # -------------------------------------------------------------------
    # pyttsx3 synthesis
    # -------------------------------------------------------------------

    def _synthesize_pyttsx3(
        self,
        text: str,
        output_path: str,
    ) -> None:
        """
        Production-safe pyttsx3 synthesis.

        Creates a NEW engine for every request.
        Prevents Windows COM deadlocks.
        """

        import pyttsx3

        with self.pyttsx3_lock:

            engine = None

            try:

                # -------------------------------------------------------
                # Create fresh engine every request
                # -------------------------------------------------------

                engine = pyttsx3.init()

                rate = int(
                    os.getenv("TTS_RATE", "150")
                )

                volume = float(
                    os.getenv("TTS_VOLUME", "1.0")
                )

                engine.setProperty(
                    "rate",
                    rate,
                )

                engine.setProperty(
                    "volume",
                    volume,
                )

                voices = engine.getProperty(
                    "voices"
                )

                preferred_voice_index = int(
                    os.getenv(
                        "TTS_VOICE_INDEX",
                        "0",
                    )
                )

                if (
                    voices
                    and preferred_voice_index < len(voices)
                ):
                    engine.setProperty(
                        "voice",
                        voices[
                            preferred_voice_index
                        ].id,
                    )

                # -------------------------------------------------------
                # Remove old file
                # -------------------------------------------------------

                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass

                logger.info(
                    f"pyttsx3 synth start | "
                    f"output={output_path}"
                )

                # -------------------------------------------------------
                # Generate WAV
                # -------------------------------------------------------

                engine.save_to_file(
                    text,
                    output_path,
                )

                engine.runAndWait()

                # -------------------------------------------------------
                # Wait for file flush (Windows fix)
                # -------------------------------------------------------

                timeout = 15
                start = time.time()

                while True:

                    if (
                        os.path.exists(output_path)
                        and os.path.getsize(output_path) > 1024
                    ):
                        break

                    if (
                        time.time() - start
                        > timeout
                    ):
                        raise RuntimeError(
                            "Timed out waiting for WAV file"
                        )

                    time.sleep(0.1)

                logger.info(
                    f"pyttsx3 synth complete | "
                    f"size={os.path.getsize(output_path)}"
                )

            except Exception as e:

                logger.error(
                    f"pyttsx3 synthesis failed: {e}"
                )

                raise

            finally:

                # -------------------------------------------------------
                # FULL engine cleanup
                # -------------------------------------------------------

                try:
                    if engine:
                        engine.stop()
                except Exception:
                    pass

                try:
                    del engine
                except Exception:
                    pass

    # -------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------

    def shutdown(self):
        """
        No persistent pyttsx3 engine now.
        Kept only for compatibility.
        """
        pass


# ---------------------------------------------------------------------------
# Singleton Backend
# ---------------------------------------------------------------------------

_tts_backend: Optional[TTSBackend] = None


def get_tts_backend() -> TTSBackend:

    global _tts_backend

    if _tts_backend is None:
        _tts_backend = TTSBackend()

    return _tts_backend


# ---------------------------------------------------------------------------
# TTS Service
# ---------------------------------------------------------------------------

class TTSService:

    def __init__(self):

        self.backend = get_tts_backend()

        logger.info(
            f"TTSService initialized | "
            f"backend={self.backend.backend_name}"
        )

    # -------------------------------------------------------------------
    # Synthesize to file
    # -------------------------------------------------------------------

    async def synthesize(
        self,
        text: str,
        output_path: str,
    ) -> str:

        text = text.strip()

        if not text:
            raise ValueError(
                "Cannot synthesize empty text."
            )

        if not self.backend.is_available():
            raise RuntimeError(
                "No TTS backend available."
            )

        output_dir = os.path.dirname(
            output_path
        )

        if output_dir:
            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        logger.info(
            f"TTSService.synthesize | "
            f"backend={self.backend.backend_name} | "
            f"chars={len(text)} | "
            f"output={output_path}"
        )

        loop = asyncio.get_running_loop()

        try:

            await loop.run_in_executor(
                None,
                self.backend.synthesize_sync,
                text,
                output_path,
            )

        except Exception as e:

            logger.error(
                f"TTS synthesis failed | "
                f"backend={self.backend.backend_name} | "
                f"error={e}"
            )

            raise RuntimeError(
                f"TTS synthesis failed: {e}"
            ) from e

        # ---------------------------------------------------------------
        # Validate generated file
        # ---------------------------------------------------------------

        if not os.path.exists(output_path):
            raise RuntimeError(
                f"TTS output missing: {output_path}"
            )

        file_size = os.path.getsize(
            output_path
        )

        if file_size <= 1024:
            raise RuntimeError(
                "Generated audio file is invalid or empty."
            )

        logger.info(
            f"TTS complete | "
            f"backend={self.backend.backend_name} | "
            f"file={output_path} | "
            f"size={file_size} bytes"
        )

        return output_path

    # -------------------------------------------------------------------
    # Synthesize to bytes
    # -------------------------------------------------------------------

    async def synthesize_to_bytes(
        self,
        text: str,
    ) -> bytes:

        text = text.strip()

        if not text:
            raise ValueError(
                "Cannot synthesize empty text."
            )

        os.makedirs(
            "audio",
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
            dir="audio",
        ) as tmp:

            tmp_path = tmp.name

        try:

            await self.synthesize(
                text=text,
                output_path=tmp_path,
            )

            with open(
                tmp_path,
                "rb",
            ) as f:

                return f.read()

        finally:

            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # -------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------

    def health(self) -> dict:

        return {
            "tts_available": self.backend.is_available(),
            "tts_backend": self.backend.backend_name,
            "model": os.getenv(
                "TTS_MODEL",
                (
                    "tts_models/en/ljspeech/tacotron2-DDC"
                    if self.backend.backend_name == "coqui"
                    else "pyttsx3-default"
                ),
            ),
        }

    # -------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------

    @staticmethod
    def list_coqui_models() -> list[str]:

        try:
            from TTS.api import TTS  # type: ignore

            return TTS().list_models()

        except Exception as e:

            logger.warning(
                f"Could not list Coqui models: {e}"
            )

            return []