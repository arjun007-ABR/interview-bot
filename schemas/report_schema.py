# schemas/report_schema.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ---------------------------------------------------------------------------
# Single Q&A entry inside the report
# ---------------------------------------------------------------------------
class QAEntry(BaseModel):
    question_index: int
    question_text: str
    answer_text: str
    score: float
    feedback: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Full report response — returned by GET /report/{session_id}
# ---------------------------------------------------------------------------
class ReportResponse(BaseModel):
    session_id: str
    overall_score: float = Field(..., description="Average score across all answers")
    hire_recommendation: str = Field(
        ...,
        description="HIRE / MAYBE / NO HIRE recommendation",
    )
    strengths: str = Field(..., description="Key strengths identified")
    weaknesses: str = Field(..., description="Areas that need improvement")
    generated_at: datetime
    questions_answers: List[QAEntry] = Field(
        default_factory=list,
        description="All Q&A pairs with scores and feedback",
    )

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Request schema — used when triggering report generation
# ---------------------------------------------------------------------------
class ReportRequest(BaseModel):
    session_id: str = Field(..., description="Session ID to generate report for")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }


# ---------------------------------------------------------------------------
# Internal schema — structured output expected from LLM during report gen
# ---------------------------------------------------------------------------
class ReportLLMOutput(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=10.0)
    hire_recommendation: str = Field(
        ...,
        description="Must be one of: HIRE, MAYBE, NO HIRE",
    )
    strengths: str
    weaknesses: str