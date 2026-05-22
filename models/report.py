# models/report.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class Report(Base):
    """
    Stores the final interview report generated after all questions
    have been answered and evaluated.

    One report per session (one-to-one with InterviewSession).
    """

    __tablename__ = "reports"

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
    )
    session_id = Column(
        String(36),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,          # one report per session
        index=True,
        comment="FK → sessions.session_id",
    )
    overall_score = Column(
        Float,
        nullable=False,
        comment="Average score across all Q&A pairs (0.0 – 10.0)",
    )
    hire_recommendation = Column(
        String(20),
        nullable=False,
        comment="HIRE | MAYBE | NO HIRE",
    )
    strengths = Column(
        Text,
        nullable=False,
        comment="Key strengths identified by the LLM",
    )
    weaknesses = Column(
        Text,
        nullable=False,
        comment="Areas that need improvement identified by the LLM",
    )
    generated_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Timestamp when the report was generated",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    session = relationship(
        "InterviewSession",
        back_populates="report",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<Report session={self.session_id!r} "
            f"score={self.overall_score} "
            f"recommendation={self.hire_recommendation!r}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "overall_score": self.overall_score,
            "hire_recommendation": self.hire_recommendation,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "generated_at": (
                self.generated_at.isoformat() if self.generated_at else None
            ),
        }