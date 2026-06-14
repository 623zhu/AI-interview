"""Question model."""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # concept/principle/practice/optimization/design
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False, default="medium", index=True)  # easy/medium/hard
    job_category: Mapped[str | None] = mapped_column(String(50), default=None, index=True)
    job_level: Mapped[str | None] = mapped_column(String(20), default=None)
    skill_nodes: Mapped[list | None] = mapped_column(JSON, default=None)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    expected_points: Mapped[str | None] = mapped_column(Text, default=None)
    reference_answer: Mapped[str | None] = mapped_column(Text, default=None)
    evaluation_criteria: Mapped[dict | None] = mapped_column(JSON, default=None)
    chroma_doc_id: Mapped[str | None] = mapped_column(String(100), default=None, index=True)
    source: Mapped[str] = mapped_column(String(20), default="seed")  # seed/ai_generated/user
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float(5, 2), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
