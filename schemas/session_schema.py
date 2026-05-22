# schemas/session_schema.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Response schema — returned after session creation
# ---------------------------------------------------------------------------
class SessionResponse(BaseModel):
    session_id: str
    candidate_id: int
    status: str
    total_questions: int
    started_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Full session detail — returned on GET /session/{session_id}
# ---------------------------------------------------------------------------
class SessionDetail(BaseModel):
    session_id: str
    candidate_id: int
    candidate_name: Optional[str] = None
    status: str
    current_question: int
    total_questions: int
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Session status update — used internally when updating session state
# ---------------------------------------------------------------------------
class SessionUpdate(BaseModel):
    status: Optional[str] = None
    current_question: Optional[int] = None
    completed_at: Optional[datetime] = None