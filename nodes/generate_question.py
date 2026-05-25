# nodes/generate_question.py

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.state import InterviewState, BLOOMS_LEVELS, BLOOMS_DESCRIPTIONS
from models.qa import QuestionAnswer
from services.llm_service import LLMService

logger = logging.getLogger(__name__)
llm_service = LLMService()


def _get_blooms_level(question_index: int, total_questions: int) -> str:
    """
    Maps question_index (1-based) to a Bloom's taxonomy level.

    With 5 questions the mapping is 1:1 — one level per question,
    in ascending cognitive order:
        Q1 → remember
        Q2 → understand
        Q3 → apply
        Q4 → analyze
        Q5 → evaluate

    With fewer or more questions the levels are distributed evenly
    so the interview always progresses from lower- to higher-order
    thinking regardless of session length.

    Args:
        question_index   : 1-based index of the question being generated.
        total_questions  : Total questions configured for this session.

    Returns:
        A Bloom's level string from BLOOMS_LEVELS.
    """
    if total_questions <= 0:
        return BLOOMS_LEVELS[0]

    # Clamp index to valid range
    idx = max(1, min(question_index, total_questions))

    # Map evenly across all five levels
    # e.g. 5 questions → positions 0,1,2,3,4 → levels[0..4]
    # e.g. 3 questions → positions 0,2,4     → remember, apply, evaluate
    level_count = len(BLOOMS_LEVELS)
    position = round((idx - 1) / max(total_questions - 1, 1) * (level_count - 1))
    position = max(0, min(position, level_count - 1))

    return BLOOMS_LEVELS[position]


def _build_blooms_prompt(level: str) -> str:
    """
    Returns a focused instruction paragraph to append to the LLM prompt
    so the model targets the correct cognitive level.
    """
    description = BLOOMS_DESCRIPTIONS[level]
    level_display = level.capitalize()

    return (
        f"COGNITIVE LEVEL REQUIREMENT — Bloom's Taxonomy: {level_display}\n"
        f"{description}\n"
        f"The question must clearly operate at the '{level_display}' level. "
        f"Do not ask a simpler recall question when a higher level is requested, "
        f"and do not ask an open-ended evaluation question when a lower level is requested."
    )


async def generate_question_node(state: InterviewState) -> InterviewState:
    """
    Generates the next interview question at the correct Bloom's taxonomy
    cognitive level and persists it to DB.

    Bloom's progression (default 5-question session):
        Q1 — Remember   : recall facts / definitions
        Q2 — Understand : explain concepts
        Q3 — Apply      : solve a realistic scenario
        Q4 — Analyze    : compare, break down, find trade-offs
        Q5 — Evaluate   : justify, critique, recommend with reasoning
    """

    db: AsyncSession = state["db"]
    session_id = state["session_id"]
    question_index = state.get("question_index", 1)
    total_questions = state.get("total_questions") or len(BLOOMS_LEVELS)
    
    # ------------------------------------------------------------------
    # Determine Bloom's level for this question
    # ------------------------------------------------------------------
    blooms_level = _get_blooms_level(question_index, total_questions)
    blooms_history: list[str] = list(state.get("blooms_history") or [])

    logger.info(
        f"generate_question_node | "
        f"session={session_id} | "
        f"question_index={question_index} | "
        f"blooms_level={blooms_level}"
    )

    try:

        # ------------------------------------------------------------------
        # Load previous questions from DB
        # ------------------------------------------------------------------
        qa_result = await db.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.session_id == session_id)
            .order_by(QuestionAnswer.question_index)
        )

        qa_records = qa_result.scalars().all()

        previous_questions = [
            qa.question_text for qa in qa_records
        ]

        logger.info(
            f"Previous questions loaded from DB | "
            f"session={session_id} | "
            f"count={len(previous_questions)}"
        )

        # ------------------------------------------------------------------
        # Build the Bloom's-aware instruction to inject into the prompt
        # ------------------------------------------------------------------
        blooms_instruction = _build_blooms_prompt(blooms_level)

        # ------------------------------------------------------------------
        # Generate next question — pass blooms_instruction as extra context
        # ------------------------------------------------------------------
        question = await llm_service.generate_question(
            candidate_name=state.get("candidate_name", ""),
            role=state.get("candidate_role", ""),
            skills=state.get("candidate_skills", ""),
            experience=state.get("candidate_experience", ""),
            qualification=state.get("candidate_qualification", ""),
            question_index=question_index,
            previous_questions=previous_questions,
            # New parameter — your LLMService.generate_question must
            # accept and append this to its system/user prompt
            blooms_instruction=blooms_instruction,
        )

        logger.info(
            f"Question generated | "
            f"session={session_id} | "
            f"index={question_index} | "
            f"blooms={blooms_level} | "
            f"q='{question[:80]}...'"
        )

        # ------------------------------------------------------------------
        # Persist generated question (prevent duplicate insert)
        # ------------------------------------------------------------------
        existing_result = await db.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.session_id == session_id,
                QuestionAnswer.question_index == question_index,
            )
        )

        existing_qa = existing_result.scalars().first()

        if not existing_qa:
            qa = QuestionAnswer(
                session_id=session_id,
                question_index=question_index,
                question_text=question,
                answer_text="",
                score=0,
                feedback="",
            )
            db.add(qa)
            await db.commit()

            logger.info(
                f"Question persisted to DB | "
                f"session={session_id} | "
                f"q_index={question_index} | "
                f"blooms={blooms_level}"
            )

        # ------------------------------------------------------------------
        # Update Bloom's history
        # ------------------------------------------------------------------
        blooms_history.append(blooms_level)

        # ------------------------------------------------------------------
        # Return updated state
        # ------------------------------------------------------------------
        return {
            **state,
            "current_question":  question,
            "question_index":    question_index,
            "previous_questions": previous_questions,
            "blooms_level":      blooms_level,
            "blooms_history":    blooms_history,
            "error":             None,
        }

    except Exception as e:
        logger.error(f"generate_question_node error: {e}")
        return {
            **state,
            "error": str(e),
        }