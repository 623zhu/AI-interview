"""Question endpoints: list, detail, generate, and admin CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, get_current_admin
from app.models.user import User
from app.models.question import Question
from app.models.resume import Resume
from app.models.job_position import JobPosition
from app.schemas.question import (
    QuestionOut, QuestionListItem,
    QuestionCreate, QuestionUpdate, QuestionImportItem, QuestionImportResult,
    QuestionGenerateRequest, QuestionGenerateResponse,
)

router = APIRouter()


@router.get("")
async def list_questions(
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    difficulty: str | None = None,
    job_category: str | None = None,
    keyword: str | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List questions with filters. Admin can include inactive questions."""
    base_filter = True if not (include_inactive and current_user.is_admin) else None
    query = select(Question)
    count_query = select(func.count(Question.id))
    if base_filter is not None:
        query = query.where(Question.is_active == base_filter)
        count_query = count_query.where(Question.is_active == base_filter)

    if category:
        query = query.where(Question.category == category)
        count_query = count_query.where(Question.category == category)
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
        count_query = count_query.where(Question.difficulty == difficulty)
    if job_category:
        query = query.where(Question.job_category == job_category)
        count_query = count_query.where(Question.job_category == job_category)
    if keyword:
        query = query.where(Question.content.ilike(f"%{keyword}%"))
        count_query = count_query.where(Question.content.ilike(f"%{keyword}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Question.usage_count.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    questions = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "items": [QuestionListItem.model_validate(q).model_dump() for q in questions],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


@router.get("/{question_id}")
async def get_question(
    question_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get question detail."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    return {"code": 200, "data": QuestionOut.model_validate(question).model_dump()}


# ── Admin CRUD ──────────────────────────────────────────


@router.post("", dependencies=[Depends(get_current_admin)])
async def create_question(
    req: QuestionCreate,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Create a new question."""
    question = Question(
        category=req.category,
        difficulty=req.difficulty,
        skill_nodes=req.skill_nodes,
        content=req.content,
        expected_points=req.expected_points,
        reference_answer=req.reference_answer,
        evaluation_criteria=req.evaluation_criteria,
        source="admin",
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    # Auto-sync to Chroma (fire-and-forget, best-effort)
    try:
        from app.agent.rag import sync_questions_to_chroma as _sync
        await _sync(db)
    except Exception:
        pass

    return {"code": 201, "data": QuestionOut.model_validate(question).model_dump()}


@router.put("/{question_id}", dependencies=[Depends(get_current_admin)])
async def update_question(
    question_id: str,
    req: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Update a question."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(question, key, value)

    await db.commit()
    await db.refresh(question)

    # Auto-sync to Chroma
    try:
        from app.agent.rag import sync_questions_to_chroma as _sync
        await _sync(db)
    except Exception:
        pass

    return {"code": 200, "data": QuestionOut.model_validate(question).model_dump()}


@router.delete("/{question_id}", dependencies=[Depends(get_current_admin)])
async def delete_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Hard-delete a question."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    await db.delete(question)
    await db.flush()

    # Also remove from Chroma
    try:
        from app.core.chroma import get_question_collection
        get_question_collection().delete(ids=[question_id])
    except Exception:
        pass

    await db.commit()
    return {"code": 200, "message": "题目已删除"}


@router.post("/{question_id}/toggle", dependencies=[Depends(get_current_admin)])
async def toggle_question(
    question_id: str,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Toggle question active/inactive."""
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    question.is_active = not question.is_active
    await db.commit()

    # Auto-sync to Chroma (toggle affects active status)
    try:
        from app.agent.rag import sync_questions_to_chroma as _sync
        await _sync(db)
    except Exception:
        pass

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
    """[Admin] Batch delete questions by ID list."""
    result = await db.execute(select(Question).where(Question.id.in_(ids)))
    questions = result.scalars().all()
    for q in questions:
        await db.delete(q)
    await db.commit()

    # Auto-sync to Chroma
    try:
        from app.agent.rag import sync_questions_to_chroma as _sync
        await _sync(db)
    except Exception:
        pass

    return {"code": 200, "message": f"已删除 {len(questions)} 道题目"}


@router.post("/import", dependencies=[Depends(get_current_admin)])
async def import_questions(
    items: list[QuestionImportItem],
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Batch import questions from JSON array."""
    success = 0
    failed = 0
    errors: list[str] = []

    for i, item in enumerate(items):
        try:
            question = Question(
                category=item.category,
                difficulty=item.difficulty,
                skill_nodes=item.skill_nodes,
                content=item.content,
                expected_points=item.expected_points,
                reference_answer=item.reference_answer,
                evaluation_criteria=item.evaluation_criteria,
                source="import",
            )
            db.add(question)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"第{i+1}条: {str(e)}")

    await db.commit()

    # Auto-sync imported questions to Chroma
    try:
        from app.agent.rag import sync_questions_to_chroma as _sync
        await _sync(db)
    except Exception:
        pass

    return {
        "code": 200,
        "data": QuestionImportResult(
            total=len(items), success=success, failed=failed, errors=errors,
        ).model_dump(),
    }


@router.post("/sync", dependencies=[Depends(get_current_admin)])
async def sync_questions_to_chroma(
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Sync all active questions to the Chroma vector database."""
    from app.agent.rag import sync_questions_to_chroma as _sync
    count = await _sync(db)
    return {"code": 200, "message": f"已同步 {count} 道题目到向量库"}


# ── AI Generation ───────────────────────────────────────


@router.post("/generate")
async def generate_questions(
    req: QuestionGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI generate interview questions based on resume and job."""
    # Verify resume
    result = await db.execute(
        select(Resume).where(Resume.id == req.resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    # Verify job
    result = await db.execute(select(JobPosition).where(JobPosition.id == req.job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    # Placeholder: return some existing questions
    # In Phase 3, this will call Question Agent with RAG
    result = await db.execute(
        select(Question).where(Question.is_active == True).limit(7)
    )
    questions = result.scalars().all()

    generated = []
    easy = medium = hard = 0
    for q in questions:
        if q.difficulty == "easy":
            easy += 1
        elif q.difficulty == "hard":
            hard += 1
        else:
            medium += 1

        generated.append({
            "id": q.id,
            "source_question_id": q.id,
            "category": q.category,
            "difficulty": q.difficulty,
            "content": q.content,
            "expected_points": q.expected_points,
            "evaluation_criteria": q.evaluation_criteria,
        })

    return {
        "code": 200,
        "data": QuestionGenerateResponse(
            questions=generated,
            total=len(generated),
            difficulty_distribution={"easy": easy, "medium": medium, "hard": hard},
            category_distribution={"basic": 3, "scenario": 2, "open_ended": 2},
        ).model_dump()
    }
