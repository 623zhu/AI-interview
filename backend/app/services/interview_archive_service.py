"""Persistence helpers for completed interview graph snapshots."""

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.interview_policy import parse_datetime
from app.models.interview_archive import InterviewArchive
from app.models.interview_session import InterviewSession


def interview_duration_seconds(state: dict[str, Any]) -> int | None:
    """Calculate elapsed seconds from the graph's timezone-aware timestamps."""
    started_at = parse_datetime(state.get("started_at"))
    if started_at is None:
        return None
    completed_at = parse_datetime(state.get("completed_at"))
    elapsed = (completed_at or datetime.now(timezone.utc)) - started_at
    return max(0, int(elapsed.total_seconds()))


async def upsert_interview_archive(
    db: AsyncSession,
    session_id: str,
    state: dict[str, Any],
) -> InterviewArchive:
    archive = await db.get(InterviewArchive, session_id)
    state_data = dict(state)
    if archive is None:
        archive = InterviewArchive(session_id=session_id, state_data=state_data)
        db.add(archive)
    elif archive.state_data != state_data:
        archive.state_data = state_data
        archive.state_version += 1
    await db.flush()
    return archive


async def load_interview_archive(
    db: AsyncSession, session_id: str
) -> dict[str, Any] | None:
    archive = await db.get(InterviewArchive, session_id)
    return dict(archive.state_data) if archive else None


async def archive_terminal_interview(
    db: AsyncSession,
    session: InterviewSession,
    state: dict[str, Any],
) -> None:
    """Persist a completed graph state and mirror its summary onto the session."""
    if state.get("status") != "completed":
        return

    completed_at = parse_datetime(state.get("completed_at")) or datetime.now(
        timezone.utc
    )
    turns = state.get("turns") or []
    session.status = "completed"
    session.completed_at = completed_at.replace(tzinfo=None)
    session.duration_seconds = interview_duration_seconds(state)
    session.total_questions = len(turns)
    session.current_question = len(turns)
    if session.report_status != "completed":
        session.report_status = "pending"
        session.report_error = None

    await upsert_interview_archive(db, session.id, state)
    await db.flush()


async def load_preferred_interview_state(
    db: AsyncSession,
    runtime: Any | None,
    session: InterviewSession,
    *,
    allow_runtime_unavailable: bool = False,
) -> dict[str, Any] | None:
    """Read terminal archives first and otherwise prefer the live checkpoint."""
    state = (
        await load_interview_archive(db, session.id)
        if session.status == "completed"
        else None
    )
    if state is None and runtime is not None:
        try:
            state = await runtime.get_interview_state(session.id)
        except RuntimeError:
            if not allow_runtime_unavailable:
                raise
    if state is None:
        state = await load_interview_archive(db, session.id)
    return state


async def load_effective_interview_states(
    runtime: Any, sessions: list[Any]
) -> dict[str, dict[str, Any] | None]:
    """Resolve hot states concurrently and completed states from eager archives."""
    active = [session for session in sessions if session.status == "in_progress"]
    hot_states = await asyncio.gather(
        *(runtime.get_interview_state(session.id) for session in active)
    )
    resolved = {
        session.id: state for session, state in zip(active, hot_states, strict=True)
    }
    for session in sessions:
        if session.id not in resolved:
            archive = session.archive
            resolved[session.id] = dict(archive.state_data) if archive else None
    return resolved
