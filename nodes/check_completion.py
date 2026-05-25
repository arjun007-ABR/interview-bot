# nodes/check_completion.py
#
# Node 4 — Checks whether all questions have been answered.
# ---------------------------------------------------------------------------

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from agent.state import InterviewState
from models.session import InterviewSession
from models.qa import QuestionAnswer

logger = logging.getLogger(__name__)


async def check_completion_node(state: InterviewState) -> InterviewState:
    """
    Determines whether the interview is complete by comparing
    the number of saved Q&A records against total_questions.

    Also updates session status to 'completed' if done.

    Reads  : session_id, question_index, total_questions, db
    Writes : is_complete, total_questions (if loaded from DB)
    """
    db: AsyncSession = state["db"]
    session_id       = state["session_id"]

    logger.info(f"check_completion_node | session={session_id}")

    try:
        # -- Load session for total_questions + current status
        session_result = await db.execute(
            select(InterviewSession).where(
                InterviewSession.session_id == session_id
            )
        )
        session = session_result.scalar_one_or_none()

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        total_questions = session.total_questions

        # -- Count how many Q&A records have been saved
        count_result = await db.execute(
    select(func.count(QuestionAnswer.id)).where(
        QuestionAnswer.session_id == session_id,
        QuestionAnswer.feedback != "",
    )
)
        answered_count = count_result.scalar() or 0

        is_complete = answered_count >= total_questions

        logger.info(
            f"Completion check | session={session_id} | "
            f"answered={answered_count} / total={total_questions} | "
            f"is_complete={is_complete}"
        )

        # -- If complete, update session status + completed_at
        if is_complete and session.status != "completed":
            from datetime import datetime
            from sqlalchemy import update

            await db.execute(
                update(InterviewSession)
                .where(InterviewSession.session_id == session_id)
                .values(
                    status="completed",
                    completed_at=datetime.utcnow(),
                )
            )
            await db.commit()
            logger.info(
                f"Session marked completed | session={session_id}"
            )

        return {
            **state,
            "is_complete":    is_complete,
            "total_questions": total_questions,
            "error":           None,
        }

    except Exception as e:
        logger.error(f"check_completion_node error: {e}")
        return {**state, "error": str(e)}