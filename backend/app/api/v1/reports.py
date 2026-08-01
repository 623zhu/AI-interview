"""Report endpoints: list, detail, and generation commands."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport
from app.schemas.report import ReportOut
from app.services.report_service import (
    REPORT_COMPLETED,
    REPORT_FAILED,
    REPORT_PENDING,
    generate_report_background,
    generate_report_for_session as run_report_generation,
    mark_report_pending,
)
from app.services.interview_session_service import get_owned_interview_session

router = APIRouter()


async def _get_owned_report(
    db: AsyncSession,
    report_id: str,
    user_id: str,
) -> ScoreReport:
    result = await db.execute(
        select(ScoreReport).where(
            ScoreReport.id == report_id,
            ScoreReport.user_id == user_id,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return report


def _completed_report_data(report: ScoreReport) -> dict:
    return {
        **ReportOut.model_validate(report).model_dump(),
        "status": REPORT_COMPLETED,
        "error": None,
    }


@router.get("")
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List score reports for current user, newest first."""
    count_result = await db.execute(
        select(func.count(ScoreReport.id)).where(ScoreReport.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ScoreReport)
        .where(ScoreReport.user_id == current_user.id)
        .options(selectinload(ScoreReport.session).selectinload(InterviewSession.job))
        .order_by(ScoreReport.generated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    reports = result.scalars().all()

    items = []
    for r in reports:
        job_title = None
        if r.session and r.session.job:
            job_title = r.session.job.title
        items.append(
            {
                "id": r.id,
                "session_id": r.session_id,
                "job_title": job_title,
                "round_count": len(r.question_evaluations)
                if r.question_evaluations
                else 0,
                "generated_at": r.generated_at.isoformat() if r.generated_at else "",
            }
        )

    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/by-session/{session_id}")
async def get_report_by_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get report for a specific interview session without side effects."""
    session = await get_owned_interview_session(db, session_id, current_user.id)

    result = await db.execute(
        select(ScoreReport).where(
            ScoreReport.session_id == session_id, ScoreReport.user_id == current_user.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        status = session.report_status or REPORT_PENDING
        code = 202 if session.status == "completed" and status != REPORT_FAILED else 404
        return {
            "code": code,
            "data": {
                "session_id": session.id,
                "status": status,
                "error": session.report_error,
            },
        }

    return {
        "code": 200,
        "data": _completed_report_data(report),
    }


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get report detail by report ID."""
    report = await _get_owned_report(db, report_id, current_user.id)
    return {"code": 200, "data": ReportOut.model_validate(report).model_dump()}


@router.post("/generate/{session_id}")
async def generate_report_for_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Schedule report generation for a completed interview."""
    session = await get_owned_interview_session(db, session_id, current_user.id)
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="面试尚未结束，无法生成报告")

    existing = await db.execute(
        select(ScoreReport).where(ScoreReport.session_id == session_id)
    )
    report = existing.scalar_one_or_none()
    if report:
        return {
            "code": 200,
            "message": "报告已存在",
            "data": _completed_report_data(report),
        }

    await mark_report_pending(db, session)
    background_tasks.add_task(generate_report_background, session_id)
    return {
        "code": 202,
        "message": "报告生成已提交",
        "data": {"session_id": session_id, "status": REPORT_PENDING, "error": None},
    }


@router.post("/{report_id}/regenerate")
async def regenerate_report(
    report_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Schedule regeneration for an existing report."""
    report = await _get_owned_report(db, report_id, current_user.id)
    session_id = report.session_id
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    await mark_report_pending(db, session)
    background_tasks.add_task(generate_report_background, session_id, replace=True)
    return {
        "code": 202,
        "message": "报告重新生成已提交",
        "data": {"session_id": session_id, "status": REPORT_PENDING, "error": None},
    }


@router.post("/generate/{session_id}/sync")
async def generate_report_for_session_sync(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate report synchronously for tests and maintenance scripts."""
    session = await get_owned_interview_session(db, session_id, current_user.id)
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="面试尚未结束，无法生成报告")

    try:
        report = await run_report_generation(db, session_id, replace=True)
        await db.commit()
    except Exception as exc:
        await db.commit()
        raise HTTPException(status_code=500, detail=f"报告生成失败: {str(exc)}")

    return {
        "code": 201,
        "message": "报告已生成",
        "data": _completed_report_data(report),
    }
