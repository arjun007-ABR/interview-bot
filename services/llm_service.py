# services/llm_service.py
#
# Handles all Groq LLaMA 3 interactions:
#   - Question generation
#   - Answer evaluation
#   - Report generation
# ---------------------------------------------------------------------------

import json
import logging
import os
from typing import Optional

from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMService:
    """
    Wrapper around the Groq AsyncClient.
    All methods are async and return structured Python dicts.
    """

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        self.client = AsyncGroq(api_key=api_key)
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        logger.info(f"LLMService initialized | model={self.model}")

    # ------------------------------------------------------------------
    # Internal helper — raw completion call
    # ------------------------------------------------------------------
    async def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: int = 1024,
    ) -> str:
        """
        Sends a chat completion request to Groq and returns
        the raw text response.
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # Question Generation
    # ------------------------------------------------------------------
    async def generate_question(
        self,
        candidate_name: str,
        role: str,
        skills: str,
        experience: str,
        qualification: str,
        question_index: int,
        previous_questions: list[str],
    ) -> str:
        """
        Generates the next interview question tailored to the candidate.
        Returns a plain question string.
        """
        previous_str = (
            "\n".join(f"{i+1}. {q}" for i, q in enumerate(previous_questions))
            if previous_questions
            else "None yet."
        )

        system_prompt = """You are an expert technical interviewer conducting a 
professional job interview. Your job is to generate ONE clear, focused, 
and relevant technical interview question.

Rules:
- Ask only ONE question per response.
- Do NOT repeat previous questions.
- Tailor the question to the candidate's role and skills.
- Vary question types: conceptual, practical, problem-solving, behavioral.
- Keep the question concise and unambiguous.
- Return ONLY the question — no preamble, no numbering, no explanation."""

        user_prompt = f"""Generate interview question #{question_index} for this candidate:

Candidate Name   : {candidate_name}
Applying For     : {role}
Skills           : {skills}
Experience       : {experience}
Qualification    : {qualification}

Questions already asked (do NOT repeat these):
{previous_str}

Return only the next question."""

        question = await self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=256,
        )
        logger.info(
            f"Question generated | index={question_index} | q={question[:60]}..."
        )
        return question

    # ------------------------------------------------------------------
    # Answer Evaluation
    # ------------------------------------------------------------------
    async def evaluate_answer(
        self,
        role: str,
        question: str,
        answer: str,
    ) -> dict:
        """
        Evaluates a candidate's answer and returns:
        {
            "score": float (0.0 – 10.0),
            "feedback": str
        }
        """
        system_prompt = """You are a strict but fair technical interviewer evaluating 
a candidate's answer. You must return a JSON object with exactly these keys:

{
  "score": <float between 0.0 and 10.0>,
  "feedback": "<detailed constructive feedback string>"
}

Scoring guide:
  9–10 : Exceptional — complete, accurate, with depth and examples
  7–8  : Good — mostly correct with minor gaps
  5–6  : Average — partially correct, missing key points
  3–4  : Below average — significant gaps or misconceptions
  0–2  : Poor — incorrect or no meaningful answer

Rules:
- Be objective and consistent.
- Feedback must be constructive and specific.
- Return ONLY valid JSON — no preamble, no markdown, no explanation."""

        user_prompt = f"""Role being interviewed for: {role}

Question asked:
{question}

Candidate's answer:
{answer}

Evaluate the answer and return JSON."""

        raw = await self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,    # lower temp for consistent scoring
            max_tokens=512,
        )

        result = self._parse_json(raw, fallback={
            "score": 0.0,
            "feedback": "Unable to evaluate answer.",
        })

        # Clamp score to valid range
        result["score"] = max(0.0, min(10.0, float(result.get("score", 0.0))))
        logger.info(
            f"Answer evaluated | score={result['score']} | "
            f"feedback={result['feedback'][:60]}..."
        )
        return result

    # ------------------------------------------------------------------
    # Report Generation
    # ------------------------------------------------------------------
    async def generate_report(
        self,
        candidate_name: str,
        role: str,
        qa_pairs: list[dict],
    ) -> dict:
        """
        Generates a final interview report from all Q&A pairs.
        Returns:
        {
            "overall_score": float,
            "hire_recommendation": str,  # HIRE | MAYBE | NO HIRE
            "strengths": str,
            "weaknesses": str
        }
        """
        qa_text = "\n\n".join([
            f"Q{i+1}: {qa['question_text']}\n"
            f"A{i+1}: {qa['answer_text']}\n"
            f"Score: {qa['score']}/10\n"
            f"Feedback: {qa['feedback']}"
            for i, qa in enumerate(qa_pairs)
        ])

        system_prompt = """You are a senior hiring manager generating a final 
interview assessment report. Based on all Q&A pairs provided, return a JSON object:

{
  "overall_score": <float 0.0–10.0, average of all scores>,
  "hire_recommendation": "<exactly one of: HIRE, MAYBE, NO HIRE>",
  "strengths": "<paragraph describing candidate strengths>",
  "weaknesses": "<paragraph describing areas for improvement>"
}

Hire recommendation guide:
  HIRE    : overall_score >= 7.0
  MAYBE   : overall_score >= 5.0 and < 7.0
  NO HIRE : overall_score < 5.0

Rules:
- Be professional and objective.
- Strengths and weaknesses must reference specific answers.
- Return ONLY valid JSON — no markdown, no preamble."""

        user_prompt = f"""Candidate: {candidate_name}
Role: {role}

Interview Q&A:
{qa_text}

Generate the final report JSON."""

        raw = await self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=1024,
        )

        result = self._parse_json(raw, fallback={
            "overall_score": 0.0,
            "hire_recommendation": "NO HIRE",
            "strengths": "Unable to generate strengths.",
            "weaknesses": "Unable to generate weaknesses.",
        })

        # Validate hire_recommendation
        valid_recommendations = {"HIRE", "MAYBE", "NO HIRE"}
        if result.get("hire_recommendation") not in valid_recommendations:
            score = float(result.get("overall_score", 0.0))
            result["hire_recommendation"] = (
                "HIRE" if score >= 7.0
                else "MAYBE" if score >= 5.0
                else "NO HIRE"
            )

        logger.info(
            f"Report generated | score={result['overall_score']} | "
            f"recommendation={result['hire_recommendation']}"
        )
        return result

    # ------------------------------------------------------------------
    # Internal JSON parser with fallback
    # ------------------------------------------------------------------
    def _parse_json(self, raw: str, fallback: dict) -> dict:
        """
        Safely parses JSON from LLM output.
        Strips markdown code fences if present.
        Returns fallback dict on any parse failure.
        """
        try:
            # Strip markdown fences if model wraps in ```json ... ```
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"JSON parse failed: {e} | raw={raw[:200]}")
            return fallback