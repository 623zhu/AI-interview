"""User SQLAlchemy model."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.interview_session import InterviewSession
    from app.models.resume import Resume
    from app.models.score_report import ScoreReport


class User(Base):
    """Candidate or administrator account."""
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "username",
            name="uq_users_username",
        ),
        UniqueConstraint(
            "email",
            name="uq_users_email",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    email_verified_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        server_default=func.current_timestamp(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    resumes: Mapped[list["Resume"]] = relationship(
        "Resume", back_populates="user", cascade="all, delete-orphan"
    )
    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        "InterviewSession", back_populates="user", cascade="all, delete-orphan"
    )
    score_reports: Mapped[list["ScoreReport"]] = relationship(
        "ScoreReport", back_populates="user", cascade="all, delete-orphan"
    )
