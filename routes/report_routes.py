# routes/report_routes.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.report import Report

# Issue 7 — Removed unused import: from models.qa import QuestionAnswer
from models.session import InterviewSession
from schemas.report_schema import ReportResponse
from agent.graph import run_report_graph
from services.evaluation_service import EvaluationService

logger           = logging.getLogger(__name__)
router           = APIRouter()
eval_service     = EvaluationService()


# ---------------------------------------------------------------------------
# POST /report/generate
# ---------------------------------------------------------------------------
@router.post("/generate")
async def generate_report(
    session_id: str,
    db        : AsyncSession = Depends(get_db),
):
    try:
        # -- Verify session exists
        session_result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.session_id == session_id
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            raise HTTPException(
                status_code=404,
                detail="Session not found",
            )

        # -- Generate report via LangGraph
        report_data = await run_report_graph(
            session_id=session_id,
            db=db,
        )

        return {
            "session_id"        : session_id,
            "overall_score"     : report_data.get("overall_score"),
            "hire_recommendation": report_data.get("hire_recommendation"),
            "strengths"         : report_data.get("strengths"),
            "weaknesses"        : report_data.get("weaknesses"),
            "generated_at"      : report_data.get("generated_at"),
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            f"Report generation error | session={session_id}"
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )


# ---------------------------------------------------------------------------
# GET /report/{session_id}
# ---------------------------------------------------------------------------
@router.get("/{session_id}", response_model=ReportResponse)
async def get_report(
    session_id: str,
    db        : AsyncSession = Depends(get_db),
):
    try:
        # -- Fetch report
        report_result = await db.execute(
            select(Report).where(Report.session_id == session_id)
        )
        report = report_result.scalar_one_or_none()

        if not report:
            raise HTTPException(
                status_code=404,
                detail="Report not found. Run POST /report/generate first.",
            )

        # -- Fetch all Q&A pairs using EvaluationService
        qa_list = await eval_service.get_all_qa_for_session(
            db=db,
            session_id=session_id,
        )

        return ReportResponse(
            session_id          = session_id,
            overall_score       = report.overall_score,
            hire_recommendation = report.hire_recommendation,
            strengths           = report.strengths,
            weaknesses          = report.weaknesses,
            generated_at        = report.generated_at,
            questions_answers   = qa_list,
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            f"Error fetching report | session={session_id}"
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )