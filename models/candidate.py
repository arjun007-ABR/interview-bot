# models/candidate.py

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class Candidate(Base):
    """
    Stores candidate registration details.
    One candidate can have multiple interview sessions.
    """

    __tablename__ = "candidates"

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )
    name = Column(
        String(100),
        nullable=False,
        comment="Full name of the candidate",
    )
    qualification = Column(
        String(200),
        nullable=False,
        comment="Educational qualification",
    )
    experience = Column(
        String(100),
        nullable=False,
        comment="Years or description of work experience",
    )
    skills = Column(
        Text,
        nullable=False,
        comment="Comma-separated list of technical skills",
    )
    role = Column(
        String(150),
        nullable=False,
        comment="Role the candidate is interviewing for",
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Timestamp when candidate was registered",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    sessions = relationship(
        "InterviewSession",
        back_populates="candidate",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<Candidate id={self.id} name={self.name!r} role={self.role!r}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "qualification": self.qualification,
            "experience": self.experience,
            "skills": self.skills,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }