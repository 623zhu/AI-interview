"""ScoreReport model."""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScoreReport(Base):
    __tablename__ = "score_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    question_evaluations: Mapped[list] = mapped_column(JSON, nullable=False)
    strengths: Mapped[list | None] = mapped_column(JSON, default=None)
    weaknesses: Mapped[list | None] = mapped_column(JSON, default=None)
    improvements: Mapped[list | None] = mapped_column(JSON, default=None)
    full_report: Mapped[str] = mapped_column(Text(length=16777215), nullable=False)  # MEDIUMTEXT markdown
    full_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    # Relationships
    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="report")
    user: Mapped["User"] = relationship("User", back_populates="score_reports")
