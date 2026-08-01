"""Report status transitions around the LangGraph report workflow."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.graph_runtime import get_graph_runtime
from app.core.redis import get_redis
from app.core.session_lock import acquire_session_lock, session_lock_lease
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport

logger = logging.getLogger(__name__)

REPORT_PENDING = "pending"
REPORT_GENERATING = "generating"
REPORT_COMPLETED = "completed"
REPORT_FAILED = "failed"


async def mark_report_pending(db: AsyncSession, session: InterviewSession) -> None:
    session.report_status = REPORT_PENDING
    session.report_error = None
    await db.flush()


async def generate_report_for_session(
    db: AsyncSession, session_id: str, *, replace: bool = False
) -> ScoreReport:
    """Run the report graph and return its archived database projection."""
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session.status != "completed":
        raise ValueError("Interview must be completed before generating a report.")

    session.report_status = REPORT_GENERATING
    session.report_error = None
    await db.commit()
    result = await get_graph_runtime().generate_report(session_id)
    await db.rollback()
    session = await db.get(InterviewSession, session_id)

    if result.get("status") != REPORT_COMPLETED:
        error = str(result.get("error") or "Report graph failed")[:500]
        session.report_status = REPORT_FAILED
        session.report_error = error
        await db.flush()
        raise RuntimeError(error)

    report_result = await db.execute(
        select(ScoreReport).where(ScoreReport.session_id == session_id)
    )
    report = report_result.scalar_one_or_none()
    if not report:
        raise RuntimeError("Report graph completed without an archived report")
    session.report_status = REPORT_COMPLETED
    session.report_error = None
    await db.flush()
    return report


async def generate_report_background(session_id: str, *, replace: bool = False) -> None:
    redis = await get_redis()
    token = await acquire_session_lock(redis, session_id)
    if not token:
        logger.info("Report generation already active session=%s", session_id)
        return
    async with session_lock_lease(redis, session_id, token):
        async with async_session_factory() as db:
            try:
                await generate_report_for_session(db, session_id, replace=replace)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                session = await db.get(InterviewSession, session_id)
                if session:
                    session.report_status = REPORT_FAILED
                    session.report_error = str(exc)[:500]
                    await db.commit()
                logger.exception(
                    "Background report generation failed session=%s", session_id
                )


async def recover_pending_reports() -> None:
    """Resume report work that was interrupted by an application restart."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(InterviewSession.id).where(
                InterviewSession.status == "completed",
                InterviewSession.report_status.in_((REPORT_PENDING, REPORT_GENERATING)),
            )
        )
        session_ids = list(result.scalars().all())
    for session_id in session_ids:
        await generate_report_background(session_id)
