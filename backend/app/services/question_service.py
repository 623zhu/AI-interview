"""Question persistence, vector-index maintenance, and RAG generation."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_position import JobPosition
from app.models.question import Question
from app.models.resume import Resume
from app.schemas.question import QuestionCreate, QuestionImportItem
from app.utils.resume_utils import build_resume_context

logger = logging.getLogger(__name__)

QUESTION_CONTENT_FIELDS = {
    "category",
    "difficulty",
    "skill_nodes",
    "content",
    "expected_points",
    "reference_answer",
    "evaluation_criteria",
}


async def get_question_or_404(db: AsyncSession, question_id: str) -> Question:
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return question


def build_question(
    payload: QuestionCreate | QuestionImportItem,
    *,
    source: Literal["admin", "import"],
) -> Question:
    """Map validated API input to the shared question persistence model."""
    values = payload.model_dump(include=QUESTION_CONTENT_FIELDS)
    return Question(**values, source=source)


async def sync_question_index_best_effort(db: AsyncSession) -> None:
    """Refresh Chroma without rolling back an already-committed MySQL write."""
    try:
        from app.agent.rag import sync_questions_to_chroma

        await sync_questions_to_chroma(db)
    except Exception:
        logger.exception("Question index synchronization failed")


def delete_question_from_index_best_effort(question_id: str) -> None:
    """Remove one vector entry without failing the authoritative MySQL write."""
    try:
        from app.core.chroma import get_question_collection

        get_question_collection().delete(ids=[question_id])
    except Exception:
        logger.exception("Failed to delete question %s from the index", question_id)


async def generate_questions(
    resume: Resume,
    job: JobPosition,
    config: dict | None,
) -> list[dict]:
    """Generate interview questions using semantic retrieval."""
    from app.agent.rag import search_questions

    count = config.get("question_count", 7) if config else 7
    resume_summary = build_resume_context(resume)
    search_text = f"{job.title} {job.category} {resume_summary}"

    results = await search_questions(query=search_text, category=None, k=count)
    return [
        {
            "question_number": index,
            "id": result.metadata.get("mysql_id", result.id),
            "content": result.metadata.get("content", ""),
            "category": result.metadata.get("category", "scenario"),
            "difficulty": result.metadata.get("difficulty", "medium"),
        }
        for index, result in enumerate(results, start=1)
    ]
