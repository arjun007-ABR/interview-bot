# agent/state.py
#
# Defines the shared state object that flows through
# every node in the LangGraph interview workflow.
# ---------------------------------------------------------------------------

from typing import Any, Optional
from typing_extensions import TypedDict


class InterviewState(TypedDict):
    """
    Shared state passed between all LangGraph nodes.
    Every node reads from and writes to this dict.

    Fields
    ------
    session_id          : Active interview session UUID
    candidate_id        : DB id of the candidate
    candidate_name      : Full name
    candidate_role      : Role being interviewed for
    candidate_skills    : Comma-separated skills string
    candidate_experience: Experience string
    candidate_qualification: Qualification string

    question_index      : Current 1-based question index
    total_questions     : Total questions planned for session
    current_question    : Question text just generated
    previous_questions  : List of all previously asked question texts
    answer_text         : Candidate's answer for current question

    score               : LLM score for current answer (0–10)
    feedback            : LLM feedback for current answer

    is_complete         : True when all questions are answered
    report              : Final report dict (populated at end)

    error               : Error message if any node fails
    db                  : AsyncSession — injected at graph entry point
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

    # -- Evaluation
    score:                    Optional[float]
    feedback:                 Optional[str]

    # -- Completion
    is_complete:              Optional[bool]
    report:                   Optional[dict]

    # -- Internal
    error:                    Optional[str]
    db:                       Any           # AsyncSession (not typed to avoid import)