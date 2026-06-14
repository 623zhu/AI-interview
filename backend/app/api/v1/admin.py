"""Admin-only endpoints: dashboard stats, user management."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_admin
from app.models.user import User
from app.models.question import Question
from app.models.job_position import JobPosition
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport
from app.schemas.auth import UserOut

router = APIRouter()


# ──────────────────────────── Dashboard ────────────────────────────

@router.get("/dashboard")
async def admin_dashboard(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get platform-wide analytics dashboard data."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # ── Summary counts ──
    user_count_result = await db.execute(select(func.count(User.id)))
    total_users = user_count_result.scalar() or 0

    q_count_result = await db.execute(
        select(func.count(Question.id)).where(Question.is_active == True)
    )
    total_questions = q_count_result.scalar() or 0

    intv_count_result = await db.execute(select(func.count(InterviewSession.id)))
    total_interviews = intv_count_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(InterviewSession.id)).where(InterviewSession.status == "completed")
    )
    completed_interviews = completed_result.scalar() or 0

    # Completion rate (completed / total)
    completion_rate = round(completed_interviews / total_interviews * 100, 1) if total_interviews > 0 else 0

    # ── Interview trend (last 30 days) ──
    trend_result = await db.execute(
        select(
            func.date(InterviewSession.created_at).label("date"),
            func.count(InterviewSession.id).label("count"),
        )
        .where(InterviewSession.created_at >= thirty_days_ago)
        .group_by(text("date"))
        .order_by(text("date"))
    )
    interview_trend = [
        {"date": str(row.date), "count": row.count}
        for row in trend_result.fetchall()
    ]

    # ── User growth trend (last 30 days) ──
    user_trend_result = await db.execute(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(User.created_at >= thirty_days_ago)
        .group_by(text("date"))
        .order_by(text("date"))
    )
    user_trend = [
        {"date": str(row.date), "count": row.count}
        for row in user_trend_result.fetchall()
    ]

    # ── Job popularity (top 10 by interview count) ──
    job_pop_result = await db.execute(
        select(
            JobPosition.title,
            JobPosition.category,
            func.count(InterviewSession.id).label("count"),
        )
        .join(InterviewSession, InterviewSession.job_id == JobPosition.id)
        .group_by(JobPosition.id)
        .order_by(text("count DESC"))
        .limit(10)
    )
    job_popularity = [
        {"title": row.title, "category": row.category, "count": row.count}
        for row in job_pop_result.fetchall()
    ]

    # ── Question category distribution ──
    cat_result = await db.execute(
        select(Question.category, func.count(Question.id))
        .where(Question.is_active == True)
        .group_by(Question.category)
    )
    cat_labels = {"basic": "基础题", "scenario": "场景题", "open_ended": "开放题"}
    category_dist = [
        {"category": cat_labels.get(row.category, row.category), "count": row.count}
        for row in cat_result.fetchall()
    ]

    # ── Recent interviews (top 10) ──
    recent_result = await db.execute(
        select(InterviewSession)
        .options(selectinload(InterviewSession.user), selectinload(InterviewSession.job))
        .order_by(InterviewSession.created_at.desc())
        .limit(10)
    )
    recent = recent_result.scalars().all()
    recent_interviews = []
    for s in recent:
        recent_interviews.append({
            "id": s.id,
            "username": s.user.username if s.user else "未知",
            "job_title": s.job.title if s.job else "未知岗位",
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    return {
        "code": 200,
        "data": {
            "summary": {
                "total_users": total_users,
                "total_questions": total_questions,
                "total_interviews": total_interviews,
                "completed_interviews": completed_interviews,
                "completion_rate": completion_rate,
            },
            "interview_trend": interview_trend,
            "user_trend": user_trend,
            "job_popularity": job_popularity,
            "category_distribution": category_dist,
            "recent_interviews": recent_interviews,
        }
    }


# ──────────────────────────── User Management ────────────────────────────

@router.get("/users")
async def list_users(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索用户名或邮箱"),
):
    """List all users with interview stats (admin only)."""
    offset = (page - 1) * page_size

    # Build query
    base_query = select(User)
    if keyword:
        base_query = base_query.where(
            (User.username.ilike(f"%{keyword}%")) | (User.email.ilike(f"%{keyword}%"))
        )

    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Page
    users_result = await db.execute(
        base_query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = users_result.scalars().all()

    items = []
    for u in users:
        # Interview count for this user
        ic_result = await db.execute(
            select(func.count(InterviewSession.id)).where(InterviewSession.user_id == u.id)
        )
        interview_count = ic_result.scalar() or 0

        # Average score
        asc_result = await db.execute(
            select(func.avg(ScoreReport.overall_score)).where(ScoreReport.user_id == u.id)
        )
        user_avg = asc_result.scalar()
        avg = round(float(user_avg), 1) if user_avg is not None else None

        # Last activity
        last_result = await db.execute(
            select(InterviewSession.created_at)
            .where(InterviewSession.user_id == u.id)
            .order_by(InterviewSession.created_at.desc())
            .limit(1)
        )
        last_activity = last_result.scalar()

        items.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "avatar_url": u.avatar_url,
            "interview_count": interview_count,
            "avg_score": avg,
            "last_activity": last_activity.isoformat() if last_activity else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user detail with interview history (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # Stats
    ic_result = await db.execute(
        select(func.count(InterviewSession.id)).where(InterviewSession.user_id == user_id)
    )
    interview_count = ic_result.scalar() or 0

    asc_result = await db.execute(
        select(func.avg(ScoreReport.overall_score)).where(ScoreReport.user_id == user_id)
    )
    user_avg = asc_result.scalar()

    # Recent interviews
    recent_result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == user_id)
        .options(selectinload(InterviewSession.job), selectinload(InterviewSession.report))
        .order_by(InterviewSession.created_at.desc())
        .limit(20)
    )
    sessions = recent_result.scalars().all()

    interviews = []
    for s in sessions:
        interviews.append({
            "id": s.id,
            "status": s.status,
            "job_title": s.job.title if s.job else None,
            "total_questions": s.total_questions,
            "current_question": s.current_question,
            "score": s.report.overall_score if s.report else None,
            "duration_seconds": s.duration_seconds,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    return {
        "code": 200,
        "data": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "avatar_url": user.avatar_url,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "stats": {
                "interview_count": interview_count,
                "avg_score": round(float(user_avg), 1) if user_avg is not None else None,
            },
            "recent_interviews": interviews,
        }
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    is_active: bool | None = None,
):
    """Update user status (admin only). Cannot modify self."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能修改自己的状态")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if is_active is not None:
        user.is_active = is_active

    await db.flush()

    return {
        "code": 200,
        "message": "用户已更新",
        "data": UserOut.model_validate(user).model_dump()
    }
