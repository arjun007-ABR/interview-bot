# nodes/generate_question.py

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.state import InterviewState
from models.qa import QuestionAnswer
from services.llm_service import LLMService

logger = logging.getLogger(__name__)
llm_service = LLMService()


async def generate_question_node(state: InterviewState) -> InterviewState:
    """
    BUG FIX — Bug 4:
    Original code built previous_questions from state and then
    appended the NEW question to it before returning.
    This caused the question list to grow incorrectly and the
    same question to appear in its own exclusion list.

    Correct approach:
      1. Load ALL previously answered questions from DB
         (source of truth — survives restarts)
      2. Generate new question excluding those
      3. Do NOT append new question to previous_questions in state
         (it will be picked up from DB on the next turn)

    This also fixes the "Question 1 repeated" bug — because
    previous_questions was stale/empty on second call.
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]
    question_index   = state.get("question_index", 1)

    logger.info(
        f"generate_question_node | "
        f"session={session_id} | "
        f"question_index={question_index}"
    )

    try:
        # ------------------------------------------------------------------
        # BUG FIX — Bug 4:
        # Always load previous questions from DB — not from state.
        # State["previous_questions"] can be stale between HTTP requests
        # because LangGraph state does NOT persist across calls.
        # DB is the only reliable source of truth.
        # ------------------------------------------------------------------
        qa_result = await db.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.session_id == session_id)
            .order_by(QuestionAnswer.question_index)
        )
        qa_records         = qa_result.scalars().all()
        previous_questions = [qa.question_text for qa in qa_records]

        logger.info(
            f"Previous questions loaded from DB | "
            f"session={session_id} | "
            f"count={len(previous_questions)}"
        )

        # Generate next question
        question = await llm_service.generate_question(
            candidate_name     = state.get("candidate_name",          ""),
            role               = state.get("candidate_role",           ""),
            skills             = state.get("candidate_skills",         ""),
            experience         = state.get("candidate_experience",     ""),
            qualification      = state.get("candidate_qualification",  ""),
            question_index     = question_index,
            previous_questions = previous_questions,
        )

        logger.info(
            f"Question generated | "
            f"session={session_id} | "
            f"index={question_index} | "
            f"q='{question[:80]}...'"
        )

        # BUG FIX — Bug 4:
        # Do NOT append the new question here.
        # previous_questions in state is only used within a single graph run.
        # The next run will reload from DB (which now contains this answer).
        return {
            **state,
            "current_question":   question,       # ← question text for response
            "question_index":     question_index, # ← unchanged, already correct
            "previous_questions": previous_questions,  # ← from DB, not appended
            "error":              None,
        }

    except Exception as e:
        logger.error(f"generate_question_node error: {e}")
        return {**state, "error": str(e)}