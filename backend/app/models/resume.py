"""Resume model."""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf / docx
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text(length=16777215), default=None)  # MEDIUMTEXT
    parsed_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/completed/failed
    parse_error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="resumes")
    job_matches: Mapped[list["ResumeJobMatch"]] = relationship("ResumeJobMatch", back_populates="resume", cascade="all, delete-orphan")
    interview_sessions: Mapped[list["InterviewSession"]] = relationship("InterviewSession", back_populates="resume")
