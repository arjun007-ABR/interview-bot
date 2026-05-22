# nodes/generate_report.py
#
# Node 5 — Generates the final interview report and saves it to DB.
# ---------------------------------------------------------------------------

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agent.state import InterviewState
from services.llm_service import LLMService
from services.evaluation_service import EvaluationService
from models.report import Report
from models.session import InterviewSession

logger = logging.getLogger(__name__)
llm_service        = LLMService()
evaluation_service = EvaluationService()


async def generate_report_node(state: InterviewState) -> InterviewState:
    """
    Generates the final interview report:
        1. Fetches all saved Q&A records from DB
        2. Calls LLM to generate overall assessment
        3. Saves the report to the reports table
        4. Populates state["report"]

    Reads  : session_id, candidate_name, candidate_role, db
    Writes : report, is_complete
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]
    candidate_name   = state.get("candidate_name", "Unknown")
    candidate_role   = state.get("candidate_role", "Unknown")

    logger.info(f"generate_report_node | session={session_id}")

    try:
        # -- Step 1: Fetch all Q&A records
        qa_pairs = await evaluation_service.get_all_qa_for_session(
            db=db,
            session_id=session_id,
        )

        if not qa_pairs:
            raise ValueError(
                f"No Q&A records found for session: {session_id}"
            )

        logger.info(
            f"Generating report | session={session_id} | "
            f"qa_pairs={len(qa_pairs)}"
        )

        # -- Step 2: LLM report generation
        report_data = await llm_service.generate_report(
            candidate_name=candidate_name,
            role=candidate_role,
            qa_pairs=qa_pairs,
        )

        overall_score       = report_data["overall_score"]
        hire_recommendation = report_data["hire_recommendation"]
        strengths           = report_data["strengths"]
        weaknesses          = report_data["weaknesses"]

        # -- Step 3: Check if report already exists (avoid duplicates)
        existing_result = await db.execute(
            select(Report).where(Report.session_id == session_id)
        )
        existing_report = existing_result.scalar_one_or_none()

        if existing_report:
            # Update existing report
            existing_report.overall_score       = overall_score
            existing_report.hire_recommendation = hire_recommendation
            existing_report.strengths           = strengths
            existing_report.weaknesses          = weaknesses
            existing_report.generated_at        = datetime.utcnow()
            await db.commit()
            await db.refresh(existing_report)
            logger.info(
                f"Report updated | session={session_id} | "
                f"score={overall_score}"
            )
        else:
            # Insert new report
            new_report = Report(
                session_id          = session_id,
                overall_score       = overall_score,
                hire_recommendation = hire_recommendation,
                strengths           = strengths,
                weaknesses          = weaknesses,
                generated_at        = datetime.utcnow(),
            )
            db.add(new_report)
            await db.commit()
            await db.refresh(new_report)
            logger.info(
                f"Report saved | session={session_id} | "
                f"score={overall_score} | "
                f"recommendation={hire_recommendation}"
            )

        # -- Step 4: Build report dict for state
        report = {
            "session_id":          session_id,
            "overall_score":       overall_score,
            "hire_recommendation": hire_recommendation,
            "strengths":           strengths,
            "weaknesses":          weaknesses,
            "generated_at":        datetime.utcnow().isoformat(),
            "questions_answers":   qa_pairs,
        }

        return {
            **state,
            "report":      report,
            "is_complete": True,
            "error":       None,
        }

    except Exception as e:
        logger.error(f"generate_report_node error: {e}")
        return {**state, "error": str(e)}