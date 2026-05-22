# models/session.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class InterviewSession(Base):
    """
    Tracks a single interview session for a candidate.
    Holds current progress — which question we're on and overall status.
    """

    __tablename__ = "sessions"

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
        String(36),           # UUID string e.g. "550e8400-e29b-41d4-..."
        unique=True,
        nullable=False,
        index=True,
        comment="UUID that uniquely identifies this session",
    )
    candidate_id = Column(
        Integer,
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        comment="FK → candidates.id",
    )
    status = Column(
        String(20),
        nullable=False,
        default="active",
        comment="active | completed | aborted",
    )
    current_question = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Index of the question currently being asked (0-based)",
    )
    total_questions = Column(
        Integer,
        nullable=False,
        default=5,
        comment="Total number of questions planned for this session",
    )
    started_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Timestamp when the session started",
    )
    completed_at = Column(
        DateTime,
        nullable=True,
        comment="Timestamp when the session was completed or aborted",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    candidate = relationship(
        "Candidate",
        back_populates="sessions",
        lazy="select",
    )
    questions_answers = relationship(
        "QuestionAnswer",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="QuestionAnswer.question_index",
        lazy="select",
    )
    report = relationship(
        "Report",
        back_populates="session",
        uselist=False,           # one-to-one
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<InterviewSession session_id={self.session_id!r} "
            f"status={self.status!r} "
            f"question={self.current_question}/{self.total_questions}>"
        )

    def is_complete(self) -> bool:
        return self.current_question >= self.total_questions

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "current_question": self.current_question,
            "total_questions": self.total_questions,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }