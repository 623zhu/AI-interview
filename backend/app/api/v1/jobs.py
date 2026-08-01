"""Job endpoints: list, detail, recommend, and admin CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user, get_current_admin
from app.models.user import User
from app.models.job_position import JobPosition
from app.models.interview_session import InterviewSession
from app.schemas.job import (
    JobOut, JobListItem,
    JobCreate, JobUpdate,
)

router = APIRouter()


@router.get("")
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List job positions with filters. Admin can include inactive."""
    base_filter = True if not (include_inactive and current_user.is_admin) else None
    query = select(JobPosition)
    count_query = select(func.count(JobPosition.id))
    if base_filter is not None:
        query = query.where(JobPosition.is_active == base_filter)
        count_query = count_query.where(JobPosition.is_active == base_filter)

    if category:
        query = query.where(JobPosition.category == category)
        count_query = count_query.where(JobPosition.category == category)
    if level:
        query = query.where(JobPosition.level == level)
        count_query = count_query.where(JobPosition.level == level)
    if keyword:
        query = query.where(
            (JobPosition.title.ilike(f"%{keyword}%")) |
            (JobPosition.description.ilike(f"%{keyword}%"))
        )
        count_query = count_query.where(
            (JobPosition.title.ilike(f"%{keyword}%")) |
            (JobPosition.description.ilike(f"%{keyword}%"))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(JobPosition.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "code": 200,
        "data": {
            "items": [JobListItem.model_validate(j).model_dump() for j in jobs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get job detail."""
    result = await db.execute(select(JobPosition).where(JobPosition.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    return {"code": 200, "data": JobOut.model_validate(job).model_dump()}


# ── Admin CRUD ──────────────────────────────────────────


@router.post("", dependencies=[Depends(get_current_admin)])
async def create_job(
    req: JobCreate,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Create a new job position."""
    job = JobPosition(
        title=req.title,
        category=req.category,
        level=req.level,
        description=req.description,
        requirements=req.requirements,
        skill_tree=req.skill_tree,
        salary_range=req.salary_range,
        company_type=req.company_type,
        is_active=req.is_active,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)


    return {"code": 201, "data": JobOut.model_validate(job).model_dump()}


@router.put("/{job_id}", dependencies=[Depends(get_current_admin)])
async def update_job(
    job_id: str,
    req: JobUpdate,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Update a job position."""
    result = await db.execute(select(JobPosition).where(JobPosition.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(job, key, value)

    await db.commit()
    await db.refresh(job)


    return {"code": 200, "data": JobOut.model_validate(job).model_dump()}


@router.delete("/{job_id}", dependencies=[Depends(get_current_admin)])
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Delete a job position, disabling it if historical interviews reference it."""
    result = await db.execute(select(JobPosition).where(JobPosition.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    refs = await db.execute(
        select(func.count(InterviewSession.id)).where(InterviewSession.job_id == job.id)
    )
    ref_count = refs.scalar() or 0
    if ref_count > 0:
        job.is_active = False
        await db.flush()
        return {
            "code": 200,
            "message": "岗位已被历史面试引用，已改为禁用",
            "data": {"id": job.id, "is_active": job.is_active, "referenced_interviews": ref_count},
        }

    await db.delete(job)
    await db.flush()
    return {"code": 200, "message": "岗位已删除"}


@router.post("/{job_id}/toggle", dependencies=[Depends(get_current_admin)])
async def toggle_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """[Admin] Toggle job active/inactive."""
    result = await db.execute(select(JobPosition).where(JobPosition.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    job.is_active = not job.is_active
    await db.commit()


    return {
        "code": 200,
        "data": {"id": job.id, "is_active": job.is_active},
        "message": "已启用" if job.is_active else "已禁用",
    }


