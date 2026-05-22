# services/evaluation_service.py
#
# Orchestrates answer evaluation + immediate database save.
# This is the critical service that ensures every Q&A is
# persisted to DB right after evaluation — never deferred.
# ---------------------------------------------------------------------------

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models.qa import QuestionAnswer
from models.session import InterviewSession
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class EvaluationService:
    """
    Handles the evaluate → save pipeline.

    MANDATORY ORDER:
        1. Call LLM to evaluate answer
        2. INSERT into questions_answers immediately
        3. COMMIT transaction immediately
        4. Update session current_question counter
        5. Return evaluation result
    """

    def __init__(self):
        self.llm = LLMService()

    async def evaluate_and_save(
        self,
        db: AsyncSession,
        session_id: str,
        question_index: int,
        question_text: str,
        answer_text: str,
        role: str,
    ) -> dict:
        """
        Evaluates the candidate's answer using the LLM and
        IMMEDIATELY saves the result to the database.

        Args:
            db            : Active async DB session
            session_id    : Current interview session ID
            question_index: 1-based index of this question
            question_text : The question that was asked
            answer_text   : The candidate's transcribed answer
            role          : Role being interviewed for (for context)

        Returns:
            dict with keys: score, feedback
        """

        # ------------------------------------------------------------------
        # Step 1 — LLM evaluation
        # ------------------------------------------------------------------
        logger.info(
            f"Evaluating answer | session={session_id} | "
            f"question_index={question_index}"
        )

        evaluation = await self.llm.evaluate_answer(
            role=role,
            question=question_text,
            answer=answer_text,
        )

        score    = evaluation["score"]
        feedback = evaluation["feedback"]

        # ------------------------------------------------------------------
        # Step 2 — IMMEDIATE INSERT into questions_answers
        # ------------------------------------------------------------------
        logger.info(
            f"Saving Q&A to DB immediately | session={session_id} | "
            f"q_index={question_index} | score={score}"
        )

        qa_record = QuestionAnswer(
            session_id=session_id,
            question_index=question_index,
            question_text=question_text,
            answer_text=answer_text,
            score=score,
            feedback=feedback,
            created_at=datetime.utcnow(),
        )
        db.add(qa_record)

        # ------------------------------------------------------------------
        # Step 3 — IMMEDIATE COMMIT — do not defer
        # ------------------------------------------------------------------
        await db.commit()
        await db.refresh(qa_record)

        logger.info(
            f"Q&A saved successfully | id={qa_record.id} | "
            f"session={session_id} | score={score}"
        )

        # ------------------------------------------------------------------
        # Step 4 — Update session's current_question counter
        # ------------------------------------------------------------------
        await db.execute(
            update(InterviewSession)
            .where(InterviewSession.session_id == session_id)
            .values(current_question=question_index)
        )
        await db.commit()

        logger.info(
            f"Session updated | session={session_id} | "
            f"current_question={question_index}"
        )

        return {
            "score":    score,
            "feedback": feedback,
            "qa_id":    qa_record.id,
        }

    async def get_all_qa_for_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> list[dict]:
        """
        Fetches all saved Q&A pairs for a session, ordered by question index.
        Used during report generation.
        """
        result = await db.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.session_id == session_id)
            .order_by(QuestionAnswer.question_index)
        )
        qa_list = result.scalars().all()

        return [
            {
                "question_index": qa.question_index,
                "question_text":  qa.question_text,
                "answer_text":    qa.answer_text,
                "score":          qa.score,
                "feedback":       qa.feedback,
            }
            for qa in qa_list
        ]

    async def calculate_average_score(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> float:
        """
        Calculates the average score from all saved Q&A pairs.
        Returns 0.0 if no records found.
        """
        qa_list = await self.get_all_qa_for_session(db, session_id)

        if not qa_list:
            return 0.0

        total = sum(qa["score"] for qa in qa_list)
        average = round(total / len(qa_list), 2)

        logger.info(
            f"Average score calculated | session={session_id} | "
            f"average={average} | total_questions={len(qa_list)}"
        )
        return average