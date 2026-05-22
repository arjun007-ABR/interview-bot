# schemas/interview_schema.py

from pydantic import BaseModel, Field
from typing import Optional


# ---------------------------------------------------------------------------
# Request schema — sent by frontend on every /agent/respond call
#
# FIRST CALL  → answer_text=None, question_index=None
# NEXT CALLS  → answer_text="...", question_index=<current index>
# ---------------------------------------------------------------------------
class AgentRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID")
    answer_text: Optional[str] = Field(
        None,
        description="Candidate's answer. Null on first call.",
    )
    question_index: Optional[int] = Field(
        None,
        description="Index of the question being answered. Null on first call.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "answer_text": "I have 3 years of experience with FastAPI...",
                "question_index": 1,
            }
        }


# ---------------------------------------------------------------------------
# Response schema — returned by /agent/respond
# ---------------------------------------------------------------------------
class AgentResponse(BaseModel):
    question_text: Optional[str] = Field(
        None,
        description="Next question for the candidate. Null when interview is complete.",
    )
    question_index: Optional[int] = Field(
        None,
        description="Index of the returned question.",
    )
    is_complete: bool = Field(
        False,
        description="True when all questions have been answered.",
    )
    report: Optional[dict] = Field(
        None,
        description="Final report. Populated only when is_complete=True.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question_text": "Can you explain how async/await works in Python?",
                "question_index": 2,
                "is_complete": False,
                "report": None,
            }
        }


# ---------------------------------------------------------------------------
# Schema for a single saved Q&A pair — used internally and in reports
# ---------------------------------------------------------------------------
class QARecord(BaseModel):
    session_id: str
    question_index: int
    question_text: str
    answer_text: str
    score: float
    feedback: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Schema for evaluation result returned by the LLM
# ---------------------------------------------------------------------------
class EvaluationResult(BaseModel):
    score: float = Field(..., ge=0.0, le=10.0, description="Score between 0 and 10")
    feedback: str = Field(..., description="Detailed feedback on the answer")