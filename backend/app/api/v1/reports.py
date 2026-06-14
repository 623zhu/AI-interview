"""Report endpoints: list, detail, generate, regenerate."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport
from app.models.job_position import JobPosition
from app.schemas.report import ReportOut, ReportListItem
from app.agent.report import generate_report

router = APIRouter()


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
        items.append({
            "id": r.id,
            "session_id": r.session_id,
            "job_title": job_title,
            "round_count": len(r.question_evaluations) if r.question_evaluations else 0,
            "generated_at": r.generated_at.isoformat() if r.generated_at else "",
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


@router.get("/by-session/{session_id}")
async def get_report_by_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get report for a specific interview session."""
    result = await db.execute(
        select(ScoreReport).where(
            ScoreReport.session_id == session_id,
            ScoreReport.user_id == current_user.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        # Auto-generate if session is completed but report is missing
        session_result = await db.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="面试会话不存在")

        # Generate report on-the-fly and complete the session
        from app.agent.report import generate_report as _gen
        session.status = "completed"
        report = await _gen(db, session_id)
        await db.commit()

    # Ensure session status is synced
    if report and report.session_id:
        session = await db.get(InterviewSession, report.session_id)
        if session and session.status != "completed":
            session.status = "completed"
            await db.commit()

    return {"code": 200, "data": ReportOut.model_validate(report).model_dump()}


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get report detail by report ID."""
    result = await db.execute(
        select(ScoreReport).where(
            ScoreReport.id == report_id,
            ScoreReport.user_id == current_user.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    return {"code": 200, "data": ReportOut.model_validate(report).model_dump()}


@router.post("/generate/{session_id}")
async def generate_report_for_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or regenerate) a report for a completed interview."""
    # Verify session belongs to user and is completed
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")
    if session.status != "completed":
        raise HTTPException(status_code=400, detail="面试尚未结束，无法生成报告")

    # Delete existing report if any
    existing = await db.execute(
        select(ScoreReport).where(ScoreReport.session_id == session_id)
    )
    old = existing.scalar_one_or_none()
    if old:
        await db.delete(old)
        await db.flush()

    # Generate new report
    try:
        report = await generate_report(db, session_id)
        await db.commit()
        return {
            "code": 201,
            "message": "报告已生成",
            "data": ReportOut.model_validate(report).model_dump()
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"报告生成失败: {str(e)}")


@router.post("/{report_id}/regenerate")
async def regenerate_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate an existing report."""
    result = await db.execute(
        select(ScoreReport).where(
            ScoreReport.id == report_id,
            ScoreReport.user_id == current_user.id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    session_id = report.session_id

    # Delete old and regenerate
    await db.delete(report)
    await db.flush()

    try:
        new_report = await generate_report(db, session_id)
        await db.commit()
        return {
            "code": 201,
            "message": "报告已重新生成",
            "data": ReportOut.model_validate(new_report).model_dump()
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"报告重新生成失败: {str(e)}")
