# schemas/candidate_schema.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Request schema — used when registering a new candidate
# ---------------------------------------------------------------------------
class CandidateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name of the candidate")
    qualification: str = Field(..., min_length=2, max_length=200, description="Educational qualification")
    experience: str = Field(..., description="Years or description of experience")
    skills: str = Field(..., description="Comma-separated list of skills")
    role: str = Field(..., description="Role the candidate is applying for")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "qualification": "B.Tech in Computer Science",
                "experience": "3 years",
                "skills": "Python, FastAPI, PostgreSQL, Docker",
                "role": "Backend Engineer",
            }
        }


# ---------------------------------------------------------------------------
# Response schema — returned after candidate is created
# ---------------------------------------------------------------------------
class CandidateResponse(BaseModel):
    id: int
    name: str
    qualification: str
    experience: str
    skills: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Minimal candidate info — used inside other response schemas
# ---------------------------------------------------------------------------
class CandidateSummary(BaseModel):
    id: int
    name: str
    role: str

    class Config:
        from_attributes = True