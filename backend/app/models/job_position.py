"""JobPosition and ResumeJobMatch models."""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobPosition(Base):
    __tablename__ = "job_positions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="mid")  # junior/mid/senior/lead
    description: Mapped[str | None] = mapped_column(Text, default=None)
    requirements: Mapped[dict] = mapped_column(JSON, nullable=False)
    skill_tree: Mapped[dict | None] = mapped_column(JSON, default=None)
    salary_range: Mapped[str | None] = mapped_column(String(50), default=None)
    company_type: Mapped[str] = mapped_column(String(50), default="互联网")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    matches: Mapped[list["ResumeJobMatch"]] = relationship("ResumeJobMatch", back_populates="job", cascade="all, delete-orphan")
    interview_sessions: Mapped[list["InterviewSession"]] = relationship("InterviewSession", back_populates="job", passive_deletes=True)


class ResumeJobMatch(Base):
    __tablename__ = "resume_job_matches"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resume_id: Mapped[str] = mapped_column(String(36), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False, index=True)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, default=None)
    matched_skills: Mapped[list | None] = mapped_column(JSON, default=None)
    missing_skills: Mapped[list | None] = mapped_column(JSON, default=None)
    match_reason: Mapped[str | None] = mapped_column(Text, default=None)
    advice: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    # Relationships
    resume: Mapped["Resume"] = relationship("Resume", back_populates="job_matches")
    job: Mapped["JobPosition"] = relationship("JobPosition", back_populates="matches")
