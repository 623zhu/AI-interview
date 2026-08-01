"""Durable terminal snapshot for a completed interview workflow."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.interview_session import InterviewSession


class InterviewArchive(Base):
    __tablename__ = "interview_archives"

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    state_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    session: Mapped["InterviewSession"] = relationship(
        "InterviewSession", back_populates="archive"
    )
