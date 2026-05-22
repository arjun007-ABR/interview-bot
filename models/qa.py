# models/qa.py

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


class QuestionAnswer(Base):
    """
    Stores every question asked and the candidate's evaluated answer.

    IMPORTANT: Each row is inserted IMMEDIATELY after LLM evaluation —
    never deferred to end of session. This ensures no data loss if the
    session is interrupted.
    """

    __tablename__ = "questions_answers"

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
        index=True,
        comment="FK → sessions.session_id",
    )
    question_index = Column(
        Integer,
        nullable=False,
        comment="1-based index of the question in this session",
    )
    question_text = Column(
        Text,
        nullable=False,
        comment="The full question that was asked",
    )
    answer_text = Column(
        Text,
        nullable=False,
        comment="The candidate's transcribed answer",
    )
    score = Column(
        Float,
        nullable=False,
        comment="LLM-assigned score between 0.0 and 10.0",
    )
    feedback = Column(
        Text,
        nullable=False,
        comment="LLM-generated feedback on the answer",
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="Timestamp of immediate save after evaluation",
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    session = relationship(
        "InterviewSession",
        back_populates="questions_answers",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<QuestionAnswer session={self.session_id!r} "
            f"q_index={self.question_index} score={self.score}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "question_index": self.question_index,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "score": self.score,
            "feedback": self.feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }