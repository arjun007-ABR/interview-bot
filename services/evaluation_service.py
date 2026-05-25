# services/evaluation_service.py
#
# Orchestrates answer evaluation + immediate database save.
# This is the critical service that ensures every Q&A is
# persisted to DB right after evaluation — never deferred.
# ---------------------------------------------------------------------------

import json
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
        1. Call LLM to evaluate answer using Bloom's-calibrated rubric
        2. INSERT / UPDATE questions_answers immediately
        3. COMMIT transaction immediately
        4. Update session current_question counter
        5. Return evaluation result
    """

    def __init__(self):
        self.llm = LLMService()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_blooms_rubric(blooms_level: str) -> str:
        """
        Returns a self-contained scoring rubric paragraph for the given
        Bloom's taxonomy level.  The rubric is injected into the LLM
        evaluation prompt so the model scores against the correct
        cognitive expectation.
        """
        rubric_map = {
            "remember": (
                "Award full marks for accurate recall of facts, terms, or "
                "definitions relevant to the question. Deduct marks for "
                "factual errors, omissions of key details, or answers that "
                "confuse related concepts."
            ),
            "understand": (
                "Reward clear, accurate explanation in the candidate's own "
                "words that demonstrates genuine comprehension. Deduct for "
                "vague, circular, or copy-paste definitions that show no "
                "evidence the candidate understands the underlying idea."
            ),
            "apply": (
                "Reward correct and relevant application of knowledge to the "
                "specific scenario presented. Deduct for generic answers that "
                "ignore the scenario context, or for applying the wrong "
                "concept to the situation."
            ),
            "analyze": (
                "Reward structured reasoning, clear identification of "
                "trade-offs, and meaningful comparison of approaches or "
                "components. Deduct for surface-level, one-sided, or "
                "unsupported assertions that lack analytical depth."
            ),
            "evaluate": (
                "Reward well-justified recommendations that acknowledge "
                "limitations, weigh alternatives, and demonstrate critical "
                "judgment. Deduct for unsupported opinions, missing rationale, "
                "or answers that simply state a preference without reasoning."
            ),
        }

        level_display = blooms_level.capitalize()
        criteria = rubric_map.get(
            blooms_level,
            rubric_map["remember"],   # safe fallback
        )

        return (
            f"BLOOM'S TAXONOMY SCORING RUBRIC — Active level: "
            f"{level_display}\n"
            f"{criteria}\n"
            f"Score strictly against the '{level_display}' rubric. "
            f"Do not reward lower-order thinking when a higher level was "
            f"required, and do not penalise a candidate for not performing "
            f"beyond the level that was asked."
        )

    @staticmethod
    def _build_evaluation_prompt(
        role: str,
        question_text: str,
        answer_text: str,
        blooms_level: str,
        blooms_rubric: str,
    ) -> str:
        """
        Assembles the full evaluation prompt that is sent to the LLM.
        Keeps prompt construction in one place so it is easy to audit
        and update independently of the save logic.
        """
        return f"""You are an expert technical interviewer evaluating a candidate's response.

Role being interviewed for: {role}
Bloom's Taxonomy level of this question: {blooms_level.capitalize()}

{blooms_rubric}

Question asked:
{question_text}

Candidate's answer:
{answer_text}

Evaluate the answer strictly against the Bloom's level rubric above.
Return your evaluation as valid JSON with exactly these two keys:
{{
  "score": <integer 0–10>,
  "feedback": "<one concise paragraph — state what was strong, what was \
missing or incorrect, and what a complete answer would include at the \
'{blooms_level}' level>"
}}

Rules:
- score must be an integer between 0 and 10 (inclusive).
- feedback must be a single paragraph, plain text, no bullet points.
- Do not include any text outside the JSON object.
- If the answer is blank or off-topic, score = 0 and explain why in feedback."""

    @staticmethod
    def _parse_llm_response(raw: str) -> tuple[int, str]:
        """
        Parses the LLM JSON response into (score, feedback).
        Strips markdown fences if the model wrapped its output.
        Clamps score to [0, 10] regardless of what the model returned.

        Returns:
            (score: int, feedback: str)
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            data = json.loads(cleaned)

        score    = max(0, min(10, int(data.get("score", 0))))
        feedback = str(data.get("feedback", "")).strip() or "No feedback provided."

        return score, feedback

    # ------------------------------------------------------------------
    # Primary public method
    # ------------------------------------------------------------------

    async def evaluate_and_save(
        self,
        db: AsyncSession,
        session_id: str,
        question_index: int,
        question_text: str,
        answer_text: str,
        role: str,
        blooms_level: str = "remember",
    ) -> dict:
        """
        Evaluates the candidate's answer using a Bloom's-calibrated LLM
        rubric and IMMEDIATELY saves the result to the database.

        Args:
            db             : Active async DB session
            session_id     : Current interview session ID
            question_index : 1-based index of this question
            question_text  : The question that was asked
            answer_text    : The candidate's transcribed answer
            role           : Role being interviewed for (for context)
            blooms_level   : Bloom's taxonomy level of this question —
                             calibrates the scoring rubric sent to the LLM.
                             One of: remember | understand | apply |
                             analyze | evaluate

        Returns:
            dict with keys: score, feedback, qa_id
        """

        # ------------------------------------------------------------------
        # Step 1 — Build Bloom's rubric and evaluation prompt
        # ------------------------------------------------------------------
        blooms_rubric = self._build_blooms_rubric(blooms_level)

        prompt = self._build_evaluation_prompt(
            role          = role,
            question_text = question_text,
            answer_text   = answer_text,
            blooms_level  = blooms_level,
            blooms_rubric = blooms_rubric,
        )

        logger.info(
            f"Evaluating answer | "
            f"session={session_id} | "
            f"q_index={question_index} | "
            f"blooms={blooms_level} | "
            f"answer_len={len(answer_text)}"
        )

        # ------------------------------------------------------------------
        # Step 2 — LLM evaluation
        # ------------------------------------------------------------------
        try:
            raw      = await self.llm.evaluate_answer(prompt=prompt)
            score, feedback = self._parse_llm_response(raw)

            logger.info(
                f"LLM evaluation complete | "
                f"session={session_id} | "
                f"q_index={question_index} | "
                f"blooms={blooms_level} | "
                f"score={score}"
            )

        except Exception as e:
            logger.error(
                f"LLM evaluation failed | "
                f"session={session_id} | "
                f"q_index={question_index} | "
                f"blooms={blooms_level} | "
                f"error={e}"
            )
            score    = 0
            feedback = f"Evaluation failed due to an internal error: {e}"

        # ------------------------------------------------------------------
        # Step 3 — IMMEDIATE upsert into questions_answers
        # ------------------------------------------------------------------
        logger.info(
            f"Saving Q&A to DB | "
            f"session={session_id} | "
            f"q_index={question_index} | "
            f"blooms={blooms_level} | "
            f"score={score}"
        )

        try:
            existing_result = await db.execute(
                select(QuestionAnswer).where(
                    QuestionAnswer.session_id     == session_id,
                    QuestionAnswer.question_index == question_index,
                )
            )
            qa_record = existing_result.scalar_one_or_none()

            if qa_record:
                # Update the placeholder row written by generate_question_node
                qa_record.answer_text = answer_text
                qa_record.score       = score
                qa_record.feedback    = feedback
                qa_record.created_at  = datetime.utcnow()
            else:
                # Safety fallback — placeholder was never written
                qa_record = QuestionAnswer(
                    session_id     = session_id,
                    question_index = question_index,
                    question_text  = question_text,
                    answer_text    = answer_text,
                    score          = score,
                    feedback       = feedback,
                    created_at     = datetime.utcnow(),
                )
                db.add(qa_record)

            await db.commit()
            await db.refresh(qa_record)

            logger.info(
                f"Q&A saved | "
                f"id={qa_record.id} | "
                f"session={session_id} | "
                f"blooms={blooms_level} | "
                f"score={score}"
            )

        except Exception as e:
            logger.error(
                f"DB save failed | "
                f"session={session_id} | "
                f"q_index={question_index} | "
                f"error={e}"
            )
            await db.rollback()
            raise

        # ------------------------------------------------------------------
        # Step 4 — Update session current_question counter
        # ------------------------------------------------------------------
        try:
            await db.execute(
                update(InterviewSession)
                .where(InterviewSession.session_id == session_id)
                .values(current_question=question_index)
            )
            await db.commit()

            logger.info(
                f"Session counter updated | "
                f"session={session_id} | "
                f"current_question={question_index}"
            )

        except Exception as e:
            logger.error(
                f"Session counter update failed | "
                f"session={session_id} | "
                f"error={e}"
            )
            await db.rollback()
            raise

        return {
            "score":    score,
            "feedback": feedback,
            "qa_id":    qa_record.id,
        }

    # ------------------------------------------------------------------
    # Read helpers (unchanged)
    # ------------------------------------------------------------------

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

        total   = sum(qa["score"] for qa in qa_list)
        average = round(total / len(qa_list), 2)

        logger.info(
            f"Average score | "
            f"session={session_id} | "
            f"average={average} | "
            f"total_questions={len(qa_list)}"
        )
        return average