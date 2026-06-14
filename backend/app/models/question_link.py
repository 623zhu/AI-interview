"""Interview-Question link table — tracks which questions have been used in which interviews.

When an interview is deleted (CASCADE), its question links are removed,
freeing those questions to be used again.
"""
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InterviewQuestionLink(Base):
    __tablename__ = "interview_question_links"

    interview_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
