"""InterviewSession and InterviewMessage models."""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[str] = mapped_column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")  # created/ready/in_progress/completed/cancelled
    config: Mapped[dict | None] = mapped_column(JSON, default=None)
    questions: Mapped[list | None] = mapped_column(JSON, default=None)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    current_question: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="interview_sessions")
    resume: Mapped["Resume"] = relationship("Resume", back_populates="interview_sessions")
    job: Mapped["JobPosition"] = relationship("JobPosition", back_populates="interview_sessions")
    messages: Mapped[list["InterviewMessage"]] = relationship("InterviewMessage", back_populates="session", cascade="all, delete-orphan", order_by="InterviewMessage.created_at")
    report: Mapped["ScoreReport | None"] = relationship("ScoreReport", back_populates="session", uselist=False, cascade="all, delete-orphan")


class InterviewMessage(Base):
    __tablename__ = "interview_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # ai / user / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str | None] = mapped_column(String(30), default=None)  # question/answer/follow_up/evaluation/system
    question_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    scores: Mapped[dict | None] = mapped_column(JSON, default=None)
    extra_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), index=True
    )

    # Relationships
    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="messages")
