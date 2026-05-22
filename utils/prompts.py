# utils/prompts.py
#
# Centralized prompt templates for all LLM interactions.
# Keeps prompts version-controlled and easy to tune.
# ---------------------------------------------------------------------------


class QuestionPrompts:
    """
    Prompt templates for interview question generation.
    """

    SYSTEM = """You are an expert technical interviewer conducting a 
professional job interview. Your job is to generate ONE clear, focused, 
and relevant technical interview question.

Rules:
- Ask only ONE question per response.
- Do NOT repeat previous questions.
- Tailor the question to the candidate's role and skills.
- Vary question types across the interview:
    * Conceptual  — "Explain how X works"
    * Practical   — "How would you implement X?"
    * Behavioral  — "Tell me about a time when..."
    * Problem     — "How would you debug / design / scale X?"
- Keep the question concise, specific, and unambiguous.
- Return ONLY the question text — no numbering, no preamble, no explanation."""

    @staticmethod
    def user(
        candidate_name: str,
        role: str,
        skills: str,
        experience: str,
        qualification: str,
        question_index: int,
        previous_questions: list[str],
    ) -> str:
        previous_str = (
            "\n".join(
                f"  {i+1}. {q}"
                for i, q in enumerate(previous_questions)
            )
            if previous_questions
            else "  None yet."
        )

        return f"""Generate interview question #{question_index} for this candidate:

Candidate Name    : {candidate_name}
Applying For      : {role}
Skills            : {skills}
Experience        : {experience}
Qualification     : {qualification}

Questions already asked (do NOT repeat):
{previous_str}

Return ONLY the question text."""


# ---------------------------------------------------------------------------

class EvaluationPrompts:
    """
    Prompt templates for answer evaluation.
    """

    SYSTEM = """You are a strict but fair technical interviewer evaluating 
a candidate's answer. You must return a JSON object with EXACTLY these keys:

{
  "score": <float between 0.0 and 10.0>,
  "feedback": "<detailed constructive feedback string>"
}

Scoring guide:
  9.0 – 10.0 : Exceptional — complete, accurate, with depth and real examples
  7.0 – 8.9  : Good — mostly correct with minor gaps
  5.0 – 6.9  : Average — partially correct, missing key points
  3.0 – 4.9  : Below average — significant gaps or misconceptions
  0.0 – 2.9  : Poor — incorrect, irrelevant, or no meaningful answer

Feedback rules:
  - Be specific — reference exact parts of the answer.
  - Be constructive — explain what was missing or wrong.
  - Be concise — 2-4 sentences maximum.
  - Do NOT be encouraging or complimentary beyond what the score warrants.

Return ONLY valid JSON — no markdown, no code fences, no preamble."""

    @staticmethod
    def user(role: str, question: str, answer: str) -> str:
        return f"""Role being interviewed for : {role}

Question asked:
{question}

Candidate's answer:
{answer if answer.strip() else "[No answer provided]"}

Evaluate the answer and return the JSON object."""


# ---------------------------------------------------------------------------

class ReportPrompts:
    """
    Prompt templates for final report generation.
    """

    SYSTEM = """You are a senior hiring manager writing a final interview 
assessment report. Based on all Q&A pairs provided, return a JSON object 
with EXACTLY these keys:

{{
  "overall_score": <float 0.0–10.0, weighted average of all scores>,
  "hire_recommendation": "<exactly one of: HIRE, MAYBE, NO HIRE>",
  "strengths": "<2-4 sentence paragraph on candidate strengths>",
  "weaknesses": "<2-4 sentence paragraph on areas for improvement>"
}}

Hire recommendation guide:
  HIRE    : overall_score >= 7.0  — Strong candidate, recommend hiring
  MAYBE   : overall_score >= 5.0  — Borderline, may need further interview
  NO HIRE : overall_score <  5.0  — Not suitable for the role

Writing rules:
  - Be professional, objective, and specific.
  - Reference actual answers when describing strengths/weaknesses.
  - Strengths and weaknesses must be distinct — no overlap.
  - Return ONLY valid JSON — no markdown, no code fences, no preamble."""

    @staticmethod
    def user(
        candidate_name: str,
        role: str,
        qa_pairs: list[dict],
    ) -> str:
        qa_text = "\n\n".join([
            f"Q{i+1}: {qa['question_text']}\n"
            f"A{i+1}: {qa['answer_text']}\n"
            f"Score   : {qa['score']}/10\n"
            f"Feedback: {qa['feedback']}"
            for i, qa in enumerate(qa_pairs)
        ])

        return f"""Candidate : {candidate_name}
Role      : {role}

Full Interview Transcript:
{qa_text}

Generate the final assessment report JSON."""


# ---------------------------------------------------------------------------

class SystemMessages:
    """
    Reusable system-level message snippets.
    """

    JSON_ONLY = (
        "Return ONLY valid JSON. "
        "No markdown. No code fences. No preamble. No explanation."
    )

    SINGLE_QUESTION = (
        "Return ONLY the question text. "
        "No numbering. No preamble. No explanation."
    )

    PROFESSIONAL_TONE = (
        "Maintain a professional, objective, and constructive tone at all times."
    )