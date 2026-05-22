# nodes/load_candidate.py

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.state import InterviewState
from models.candidate import Candidate
from models.session import InterviewSession
from models.qa import QuestionAnswer

logger = logging.getLogger(__name__)


async def load_candidate_node(state: InterviewState) -> InterviewState:
    """
    Loads candidate + session from DB into graph state.
    Only runs on the FIRST call (answer_text is None).

    Fixed: question_index is set to (answered_count + 1)
    which is always correct regardless of session state.
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]

    logger.info(f"load_candidate_node | session={session_id}")

    try:
        # Load session
        session_result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.session_id == session_id
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            return {**state, "error": f"Session not found: {session_id}"}

        # Load candidate
        candidate_result = await db.execute(
            select(Candidate).where(Candidate.id == session.candidate_id)
        )
        candidate = candidate_result.scalar_one_or_none()

        if not candidate:
            return {
                **state,
                "error": f"Candidate not found: {session.candidate_id}",
            }

        # Count already-answered questions from DB
        qa_result = await db.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.session_id == session_id)
            .order_by(QuestionAnswer.question_index)
        )
        qa_list            = qa_result.scalars().all()
        previous_questions = [qa.question_text for qa in qa_list]

        # Next index = how many answered + 1
        next_index = len(previous_questions) + 1

        logger.info(
            f"Candidate loaded | "
            f"name={candidate.name} | "
            f"role={candidate.role} | "
            f"answered={len(previous_questions)} | "
            f"next_index={next_index}"
        )

        return {
            **state,
            "candidate_id":            candidate.id,
            "candidate_name":          candidate.name,
            "candidate_role":          candidate.role,
            "candidate_skills":        candidate.skills,
            "candidate_experience":    candidate.experience,
            "candidate_qualification": candidate.qualification,
            "total_questions":         session.total_questions,
            "question_index":          next_index,
            "previous_questions":      previous_questions,
            "error":                   None,
        }

    except Exception as e:
        logger.error(f"load_candidate_node error: {e}")
        return {**state, "error": str(e)}