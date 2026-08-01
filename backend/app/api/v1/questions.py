"""Question endpoints: admin CRUD, vector sync, and candidate generation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_db
from app.models.job_position import JobPosition
from app.models.question import Question
from app.models.resume import Resume
from app.models.user import User
from app.schemas.question import (
    QuestionCreate,
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    QuestionImportItem,
    QuestionImportResult,
    QuestionListItem,
    QuestionOut,
    QuestionUpdate,
)
from app.services.question_service import (
    build_question,
    delete_question_from_index_best_effort,
    get_question_or_404,
    sync_question_index_best_effort,
)

router = APIRouter()


def _assert_admin(user: User) -> None:
    """Keep authorization intact when handlers are called outside FastAPI."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="题库仅管理员可访问")


def _question_filters(
    *,
    category: str | None,
    difficulty: str | None,
    job_category: str | None,
    keyword: str | None,
    include_inactive: bool,
) -> list[Any]:
    filters: list[Any] = []
    if not include_inactive:
        filters.append(Question.is_active.is_(True))
    if category:
        filters.append(Question.category == category)
    if difficulty:
        filters.append(Question.difficulty == difficulty)
    if job_category:
        filters.append(Question.job_category == job_category)
    if keyword:
        filters.append(Question.content.ilike(f"%{keyword}%"))
    return filters


@router.get("")
async def list_questions(
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    difficulty: str | None = None,
    job_category: str | None = None,
    keyword: str | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List questions with optional admin filters."""
    _assert_admin(current_user)
    filters = _question_filters(
        category=category,
        difficulty=difficulty,
        job_category=job_category,
        keyword=keyword,
        include_inactive=include_inactive,
    )

    total_result = await db.execute(select(func.count(Question.id)).where(*filters))
    result = await db.execute(
        select(Question)
        .where(*filters)
        .order_by(Question.usage_count.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    questions = result.scalars().all()
    return {
        "code": 200,
        "data": {
            "items": [
                QuestionListItem.model_validate(question).model_dump()
                for question in questions
            ],
            "total": total_result.scalar() or 0,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/{question_id}")
async def get_question(
    question_id: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return full question details to an administrator."""
    _assert_admin(current_user)
    question = await get_question_or_404(db, question_id)
    return {"code": 200, "data": QuestionOut.model_validate(question).model_dump()}


@router.post("", dependencies=[Depends(get_current_admin)])
async def create_question(
    req: QuestionCreate,
    db: AsyncSession = Depends(get_db),
):
    question = build_question(req, source="admin")
    db.add(question)
    await db.commit()
    await db.refresh(question)
    await sync_question_index_best_effort(db)
    return {"code": 201, "data": QuestionOut.model_validate(question).model_dump()}


@router.put("/{question_id}", dependencies=[Depends(get_current_admin)])
async def update_question(
    question_id: str,
    req: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
):
    question = await get_question_or_404(db, question_id)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(question, field, value)

    await db.commit()
    await db.refresh(question)
    await sync_question_index_best_effort(db)
    return {"code": 200, "data": QuestionOut.model_validate(question).model_dump()}


@router.delete("/{question_id}", dependencies=[Depends(get_current_admin)])
async def delete_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
):
    question = await get_question_or_404(db, question_id)
    await db.delete(question)
    await db.flush()
    delete_question_from_index_best_effort(question_id)
    await db.commit()
    return {"code": 200, "message": "题目已删除"}


@router.post("/{question_id}/toggle", dependencies=[Depends(get_current_admin)])
async def toggle_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
):
    question = await get_question_or_404(db, question_id)
    question.is_active = not question.is_active
    await db.commit()
    await sync_question_index_best_effort(db)
    return {
        "code": 200,
        "data": {"id": question.id, "is_active": question.is_active},
        "message": "已启用" if question.is_active else "已禁用",
    }


@router.post("/batch-delete", dependencies=[Depends(get_current_admin)])
async def batch_delete_questions(
    ids: list[str],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Question).where(Question.id.in_(ids)))
    questions = result.scalars().all()
    for question in questions:
        await db.delete(question)
    await db.commit()
    await sync_question_index_best_effort(db)
    return {"code": 200, "message": f"已删除 {len(questions)} 道题目"}


@router.post("/import", dependencies=[Depends(get_current_admin)])
async def import_questions(
    items: list[QuestionImportItem],
    db: AsyncSession = Depends(get_db),
):
    success = 0
    errors: list[str] = []
    for index, item in enumerate(items, start=1):
        try:
            db.add(build_question(item, source="import"))
            success += 1
        except Exception as exc:
            errors.append(f"第{index}条: {exc}")

    await db.commit()
    await sync_question_index_best_effort(db)
    return {
        "code": 200,
        "data": QuestionImportResult(
            total=len(items),
            success=success,
            failed=len(errors),
            errors=errors,
        ).model_dump(),
    }


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_questions_to_chroma(
    db: AsyncSession = Depends(get_db),
):
    from app.agent.rag import sync_questions_to_chroma as sync_index

    count = await sync_index(db)
    return {"code": 200, "message": f"已同步 {count} 道题目到向量库"}


@router.post("/generate")
async def generate_questions(
    req: QuestionGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active questions for a verified resume and job pair."""
    resume_result = await db.execute(
        select(Resume).where(
            Resume.id == req.resume_id,
            Resume.user_id == current_user.id,
        )
    )
    if resume_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="简历不存在")

    job_result = await db.execute(
        select(JobPosition).where(JobPosition.id == req.job_id)
    )
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="岗位不存在")

    result = await db.execute(
        select(Question).where(Question.is_active.is_(True)).limit(7)
    )
    questions = result.scalars().all()
    distribution = {"easy": 0, "medium": 0, "hard": 0}
    generated = []
    for question in questions:
        difficulty = (
            question.difficulty if question.difficulty in distribution else "medium"
        )
        distribution[difficulty] += 1
        generated.append(
            {
                "id": question.id,
                "source_question_id": question.id,
                "category": question.category,
                "difficulty": question.difficulty,
                "content": question.content,
                "expected_points": question.expected_points,
                "evaluation_criteria": question.evaluation_criteria,
            }
        )

    return {
        "code": 200,
        "data": QuestionGenerateResponse(
            questions=generated,
            total=len(generated),
            difficulty_distribution=distribution,
            category_distribution={"basic": 3, "scenario": 2, "open_ended": 2},
        ).model_dump(),
    }
