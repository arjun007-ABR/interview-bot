# routes/session_routes.py

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.candidate import Candidate
from models.session import InterviewSession
from schemas.candidate_schema import CandidateCreate
from schemas.session_schema import SessionResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /session/create
# ---------------------------------------------------------------------------
@router.post("/create", response_model=SessionResponse)
async def create_session(
    payload: CandidateCreate,
    db     : AsyncSession = Depends(get_db),
):
    try:
        # -- Create candidate
        candidate = Candidate(
            name          = payload.name,
            qualification = payload.qualification,
            experience    = payload.experience,
            skills        = payload.skills,
            role          = payload.role,
        )
        db.add(candidate)

        # Issue 4 — Use flush() to get candidate.id WITHOUT committing.
        # get_db() will commit at request end — single commit point.
        await db.flush()

        # -- Create session
        session = InterviewSession(
            session_id      = str(uuid.uuid4()),
            candidate_id    = candidate.id,
            status          = "active",
            current_question= 0,
            total_questions = 5,
            started_at      = datetime.utcnow(),
        )
        db.add(session)

        # Issue 4 — flush() again to get session data; NO db.commit() here.
        await db.flush()
        await db.refresh(session)

        logger.info(
            f"Session created | session_id={session.session_id} "
            f"candidate={payload.name}"
        )

        return SessionResponse(
            session_id      = session.session_id,
            candidate_id    = candidate.id,
            status          = session.status,
            total_questions = session.total_questions,
            started_at      = session.started_at,
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception("Error creating session")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /session/{session_id}
# ---------------------------------------------------------------------------
@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db        : AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.session_id == session_id
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        candidate_result = await db.execute(
            select(Candidate).where(Candidate.id == session.candidate_id)
        )
        candidate = candidate_result.scalar_one_or_none()

        return {
            "session_id"      : session.session_id,
            "candidate_id"    : session.candidate_id,
            "candidate_name"  : candidate.name if candidate else None,
            "status"          : session.status,
            "current_question": session.current_question,
            "total_questions" : session.total_questions,
            "started_at"      : session.started_at,
            "completed_at"    : session.completed_at,
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(f"Error fetching session | session_id={session_id}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )