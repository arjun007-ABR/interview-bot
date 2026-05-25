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
    Evaluates the candidate's answer against the question and role,
    now also passing the Bloom's taxonomy level so the LLM scorer
    can calibrate its rubric appropriately.

    Scoring rubric intent per level:
        remember   — did they recall the fact/definition correctly?
        understand — did they explain the concept clearly?
        apply      — did they apply the concept correctly to the scenario?
        analyze    — did they identify the right trade-offs / break it down well?
        evaluate   — did they give a well-reasoned, justified recommendation?
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]
    question_index   = state.get("question_index")
    answer_text      = state.get("answer_text", "") or ""
    role             = state.get("candidate_role", "")
    blooms_level     = state.get("blooms_level") or "remember"

    logger.info(
        f"evaluate_answer_node | "
        f"session={session_id} | "
        f"question_index={question_index} | "
        f"blooms_level={blooms_level} | "
        f"answer_preview='{answer_text[:60]}'"
    )

    try:
        # ------------------------------------------------------------------
        # Get question_text from state first; fall back to DB
        # ------------------------------------------------------------------
        question_text = (state.get("current_question") or "").strip()

        if not question_text:
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
                # Already evaluated — skip re-evaluation
                logger.warning(
                    f"Q&A already in DB for index={question_index} | "
                    f"session={session_id} — skipping re-evaluation"
                )
                return {
                    **state,
                    "score":          existing_qa.score,
                    "feedback":       existing_qa.feedback,
                    "question_index": question_index + 1,
                    "error":          None,
                }

            raise ValueError(
                f"Question text not found in state or DB | "
                f"session={session_id} | index={question_index}"
            )

        # ------------------------------------------------------------------
        # Evaluate + save — pass blooms_level for rubric calibration
        # ------------------------------------------------------------------
        result = await evaluation_service.evaluate_and_save(
            db             = db,
            session_id     = session_id,
            question_index = question_index,
            question_text  = question_text,
            answer_text    = answer_text,
            role           = role,
            # New parameter — EvaluationService.evaluate_and_save must
            # accept this and include it in the scoring prompt
            blooms_level   = blooms_level,
        )

        next_index = question_index + 1

        logger.info(
            f"evaluate_answer_node complete | "
            f"session={session_id} | "
            f"blooms={blooms_level} | "
            f"score={result['score']} | "
            f"next_index={next_index}"
        )

        return {
            **state,
            "score":          result["score"],
            "feedback":       result["feedback"],
            "question_index": next_index,
            "error":          None,
        }

    except Exception as e:
        logger.error(f"evaluate_answer_node error: {e}")
        return {**state, "error": str(e)}