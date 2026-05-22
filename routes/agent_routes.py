# routes/agent_routes.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.interview_schema import AgentRequest, AgentResponse
from agent.graph import run_interview_graph

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/respond", response_model=AgentResponse)
async def agent_respond(
    payload: AgentRequest,
    db     : AsyncSession = Depends(get_db),
):
    """
    Core interview loop endpoint.

    Validates that:
    - session_id is always present
    - answer_text + question_index are BOTH provided together
      on subsequent calls (not one without the other)
    """
    try:
        # -- Validate: subsequent call must have BOTH answer + index
        if payload.answer_text is not None and payload.question_index is None:
            raise HTTPException(
                status_code=422,
                detail="question_index is required when answer_text is provided.",
            )

        if payload.question_index is not None and payload.answer_text is None:
            # question_index provided but no answer — treat as first call
            # (handles edge case where frontend sends index=null incorrectly)
            logger.warning(
                f"question_index={payload.question_index} provided "
                f"without answer_text — treating as first call | "
                f"session={payload.session_id}"
            )

        logger.info(
            f"Agent respond | "
            f"session_id={payload.session_id} | "
            f"question_index={payload.question_index} | "
            f"has_answer={payload.answer_text is not None} | "
            f"answer_preview='{str(payload.answer_text)[:40] if payload.answer_text else None}'"
        )

        result = await run_interview_graph(
            session_id    = payload.session_id,
            answer_text   = payload.answer_text,
            question_index= payload.question_index,
            db            = db,
        )

        return AgentResponse(
            question_text  = result.get("question_text"),
            question_index = result.get("question_index"),
            is_complete    = result.get("is_complete", False),
            report         = result.get("report"),
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            f"Agent respond error | session_id={payload.session_id}"
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )