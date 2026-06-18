"""Report generation orchestration.

The report content itself is compiled in ``app.agent.report``. This module owns
status transitions and background task entry points so read APIs stay side-effect
free.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.report import generate_report
from app.core.database import async_session_factory
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


async def generate_report_for_session(db: AsyncSession, session_id: str, *, replace: bool = False) -> ScoreReport:
    """Generate a report and maintain session report status."""
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    if session.status != "completed":
        raise ValueError("Interview must be completed before generating a report.")

    session.report_status = REPORT_GENERATING
    session.report_error = None
    await db.flush()

    existing_result = await db.execute(
        select(ScoreReport).where(ScoreReport.session_id == session_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing and not replace:
        session.report_status = REPORT_COMPLETED
        await db.flush()
        return existing
    if existing:
        await db.delete(existing)
        await db.flush()

    try:
        report = await generate_report(db, session_id)
        session.report_status = REPORT_COMPLETED
        session.report_error = None
        await db.flush()
        return report
    except Exception as exc:
        session.report_status = REPORT_FAILED
        session.report_error = str(exc)[:500]
        await db.flush()
        raise


async def generate_report_background(session_id: str, *, replace: bool = False) -> None:
    """Background task entry point using an independent DB session."""
    async with async_session_factory() as db:
        try:
            await generate_report_for_session(db, session_id, replace=replace)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Background report generation failed session=%s", session_id)
