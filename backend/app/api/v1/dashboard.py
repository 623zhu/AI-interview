"""Dashboard API - aggregated data for the user's workflow hub."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport

router = APIRouter()


@router.get("")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard overview: latest resume, stats, recent interviews."""
    user_id = current_user.id

    # Latest resume
    result = await db.execute(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc())
        .limit(1)
    )
    resume = result.scalar_one_or_none()

    

    # Stats: separate queries for clarity
    count_result = await db.execute(
        select(func.count(InterviewSession.id)).where(InterviewSession.user_id == user_id)
    )
    interview_count = count_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(ScoreReport.overall_score))
        .join(InterviewSession, ScoreReport.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    )
    avg_score = avg_result.scalar()

    # Recent interviews
    recent_result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == user_id)
        .options(selectinload(InterviewSession.job), selectinload(InterviewSession.report))
        .order_by(InterviewSession.created_at.desc())
        .limit(5)
    )
    recent = recent_result.scalars().all()

    return {
        "code": 200,
        "data": {
            "resume": _resume_dict(resume) if resume else None,
            "stats": {
                "interview_count": interview_count,
                "avg_score": round(float(avg_score), 1) if avg_score is not None else None,
            },
            "recent_interviews": [_interview_dict(s) for s in recent],
        }
    }


def _resume_dict(r: Resume) -> dict:
    return {
        "id": r.id,
        "original_filename": r.original_filename,
        "file_type": r.file_type,
        "file_size": r.file_size,
        "parse_status": r.parse_status,
        "parse_error": r.parse_error,
        "parsed_data": r.parsed_data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _interview_dict(s: InterviewSession) -> dict:
    return {
        "id": s.id,
        "status": s.status,
        "job_title": s.job.title if s.job else None,
        "answered_count": s.current_question,
        "max_turns": (s.config or {}).get("max_turns"),
        "score": s.report.overall_score if s.report else None,
        "duration_seconds": s.duration_seconds,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
