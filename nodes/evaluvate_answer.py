# nodes/evaluate_answer.py

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agent.state import InterviewState
from services.evaluation_service import EvaluationService
from models.qa import QuestionAnswer

logger = logging.getLogger(__name__)
evaluation_service = EvaluationService()


async def evaluate_answer_node(state: InterviewState) -> InterviewState:
    """
    BUG FIX — Bug 3:
    Original code tried to load question_text from the DB first.
    But at evaluation time, the question has NOT been saved to DB yet —
    it only exists in state["current_question"] (put there by
    generate_question_node in the previous turn).

    Correct priority:
      1. Read question_text from state["current_question"]  ← primary source
      2. Fall back to DB only if state is empty (edge case)

    Also fixed: question_index was being incremented here AND in
    load_candidate_node causing double increment.
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]
    question_index   = state.get("question_index")
    answer_text      = state.get("answer_text", "")
    role             = state.get("candidate_role", "")

    # Normalize answer — None becomes empty string for evaluation
    if answer_text is None:
        answer_text = ""

    logger.info(
        f"evaluate_answer_node | "
        f"session={session_id} | "
        f"question_index={question_index} | "
        f"answer_preview='{answer_text[:60]}'"
    )

    try:
        # ------------------------------------------------------------------
        # BUG FIX — Bug 3:
        # Get question_text from STATE first — it's always there from
        # the previous generate_question_node call.
        # Only fall back to DB if state doesn't have it.
        # ------------------------------------------------------------------
        question_text = state.get("current_question", "").strip()

        if not question_text:
            # Fallback: try loading from DB (edge case: session resumed)
            logger.warning(
                f"current_question not in state — falling back to DB | "
                f"session={session_id} | index={question_index}"
            )
            qa_result = await db.execute(
                select(QuestionAnswer).where(
                    QuestionAnswer.session_id     == session_id,
                    QuestionAnswer.question_index == question_index,
                )
            )
            existing_qa = qa_result.scalar_one_or_none()

            if existing_qa:
                # Already evaluated — skip re-evaluation to avoid duplicates
                logger.warning(
                    f"Q&A already exists in DB for index={question_index} | "
                    f"session={session_id} — skipping re-evaluation"
                )
                next_index = question_index + 1
                return {
                    **state,
                    "score":          existing_qa.score,
                    "feedback":       existing_qa.feedback,
                    "question_index": next_index,
                    "error":          None,
                }

            # Truly missing — cannot evaluate
            raise ValueError(
                f"Question text not found in state or DB | "
                f"session={session_id} | index={question_index}"
            )

        # ------------------------------------------------------------------
        # Evaluate + SAVE IMMEDIATELY via EvaluationService
        # ------------------------------------------------------------------
        result = await evaluation_service.evaluate_and_save(
            db             = db,
            session_id     = session_id,
            question_index = question_index,
            question_text  = question_text,
            answer_text    = answer_text,
            role           = role,
        )

        # Increment index for next question
        next_index = question_index + 1

        logger.info(
            f"evaluate_answer_node complete | "
            f"session={session_id} | "
            f"score={result['score']} | "
            f"next_index={next_index}"
        )

        return {
            **state,
            "score":          result["score"],
            "feedback":       result["feedback"],
            "question_index": next_index,       # ← incremented here only
            "error":          None,
        }

    except Exception as e:
        logger.error(f"evaluate_answer_node error: {e}")
        return {**state, "error": str(e)}