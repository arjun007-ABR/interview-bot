# routes/audio_routes.py

import logging
import os
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.stt_service import STTService
from services.tts_service import TTSService

logger = logging.getLogger(__name__)
router = APIRouter()

stt_service = STTService()
tts_service = TTSService()

UPLOAD_DIR = "uploads"
AUDIO_DIR  = "audio"

# ---------------------------------------------------------------------------
# Issue 2 — Allowed audio extensions and MIME types
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".webm", ".ogg", ".m4a", ".flac"}
ALLOWED_MIME_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/m4a",
    "audio/flac",
    "application/octet-stream",  # some browsers send this for webm
}

# Max upload size: 50 MB
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def validate_audio_file(file: UploadFile) -> str:
    """
    Validates uploaded audio file extension and MIME type.
    Returns the cleaned extension string.
    Raises HTTPException 400 on invalid file.
    """
    # -- Validate extension
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if not ext:
        ext = ".webm"   # default for browser recordings with no extension

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. "
                   f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # -- Validate MIME type
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type '{content_type}'.",
        )

    return ext


# ---------------------------------------------------------------------------
# POST /audio-to-text
# ---------------------------------------------------------------------------
@router.post("/audio-to-text")
async def audio_to_text(
    file      : UploadFile = File(...),
    session_id: str        = Form(...),
    db        : AsyncSession = Depends(get_db),
):
    try:
        # -- Issue 2: Validate file type before saving
        ext = validate_audio_file(file)

        filename  = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        # -- Issue 3: Chunked streaming write — avoids loading entire
        #             file into memory for large uploads
        total_bytes = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)   # 1 MB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)

                # Enforce max file size
                if total_bytes > MAX_UPLOAD_BYTES:
                    f.close()
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is "
                               f"{MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )

                f.write(chunk)

        logger.info(
            f"Audio uploaded | file={filename} "
            f"size={total_bytes} bytes | session={session_id}"
        )

        # -- Transcribe
        transcript = await stt_service.transcribe(file_path)
        logger.info(f"Transcription complete | session={session_id}")

        return JSONResponse(content={
            "transcript": transcript,
            "session_id": session_id,
            "file":       filename,
        })

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"STT error | session={session_id}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# POST /text-to-audio
# ---------------------------------------------------------------------------
@router.post("/text-to-audio")
async def text_to_audio(
    text      : str = Form(...),
    session_id: str = Form(...),
    db        : AsyncSession = Depends(get_db),
):
    try:
        # Basic input validation
        text = text.strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Text cannot be empty.",
            )
        if len(text) > 5000:
            raise HTTPException(
                status_code=400,
                detail="Text too long. Maximum 5000 characters.",
            )

        filename    = f"{uuid.uuid4()}.wav"
        output_path = os.path.join(AUDIO_DIR, filename)

        logger.info(f"TTS request | session={session_id} | chars={len(text)}")

        await tts_service.synthesize(text=text, output_path=output_path)

        audio_url = f"/audio/{filename}"
        logger.info(f"TTS complete | file={filename}")

        return JSONResponse(content={
            "audio_url":  audio_url,
            "session_id": session_id,
            "filename":   filename,
        })

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"TTS error | session={session_id}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )