# agent/state.py

from typing import Any, Optional
from typing_extensions import TypedDict


BLOOMS_LEVELS = [
    "remember",       # Q1 — recall facts, definitions
    "understand",     # Q2 — explain concepts in own words
    "apply",          # Q3 — use knowledge in a new situation
    "analyze",        # Q4 — break down, compare, contrast
    "evaluate",       # Q5 — judge, justify, critique
]

BLOOMS_DESCRIPTIONS = {
    "remember":   "Ask the candidate to recall or define a fact, term, or concept relevant to their role.",
    "understand": "Ask the candidate to explain a concept, describe how something works, or summarise an idea in their own words.",
    "apply":      "Present a realistic scenario and ask the candidate to apply their knowledge to solve it.",
    "analyze":    "Ask the candidate to compare approaches, identify trade-offs, or break down a complex problem.",
    "evaluate":   "Ask the candidate to critique a design decision, justify a choice, or recommend the best approach with reasoning.",
}


class InterviewState(TypedDict):
    """
    Shared state passed between all LangGraph nodes.

    Fields
    ------
    session_id            : Active interview session UUID
    candidate_id          : DB id of the candidate
    candidate_name        : Full name
    candidate_role        : Role being interviewed for
    candidate_skills      : Comma-separated skills string
    candidate_experience  : Experience string
    candidate_qualification: Qualification string

    question_index        : Current 1-based question index
    total_questions       : Total questions planned for session
    current_question      : Question text just generated
    previous_questions    : List of all previously asked question texts
    answer_text           : Candidate's answer for current question

    blooms_level          : Bloom's taxonomy level for the current question
                            e.g. "remember", "understand", "apply", ...
    blooms_history        : List of taxonomy levels used so far,
                            in order — mirrors previous_questions indices

    score                 : LLM score for current answer (0–10)
    feedback              : LLM feedback for current answer

    is_complete           : True when all questions are answered
    report                : Final report dict (populated at end)

    error                 : Error message if any node fails
    db                    : AsyncSession — injected at graph entry point
    """

    # -- Session & Candidate
    session_id:               str
    candidate_id:             Optional[int]
    candidate_name:           Optional[str]
    candidate_role:           Optional[str]
    candidate_skills:         Optional[str]
    candidate_experience:     Optional[str]
    candidate_qualification:  Optional[str]

    # -- Interview Progress
    question_index:           Optional[int]
    total_questions:          Optional[int]
    current_question:         Optional[str]
    previous_questions:       Optional[list[str]]
    answer_text:              Optional[str]

    # -- Bloom's Taxonomy
    blooms_level:             Optional[str]   # level for the CURRENT question
    blooms_history:           Optional[list[str]]  # one entry per past question

    # -- Evaluation
    score:                    Optional[float]
    feedback:                 Optional[str]

    # -- Completion
    is_complete:              Optional[bool]
    report:                   Optional[dict]

    # -- Internal
    error:                    Optional[str]
    db:                       Any