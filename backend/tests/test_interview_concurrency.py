from datetime import datetime, timezone

import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.interviews import chat_stream, end_interview
from app.core.session_lock import acquire_session_lock
from app.models.interview_session import InterviewMessage, InterviewSession
from app.schemas.interview import ChatRequest
from tests.test_interviews import _seed_user_resume_job


@pytest.mark.asyncio
async def test_chat_stream_rejects_when_session_lock_is_held(db_session, fake_redis):
    user, resume, job = await _seed_user_resume_job(db_session)
    session = InterviewSession(
        user=user,
        resume=resume,
        job=job,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
        config={"max_turns": 12},
        questions=[],
    )
    db_session.add(session)
    await db_session.flush()
    await acquire_session_lock(fake_redis, session.id)

    with pytest.raises(HTTPException) as exc:
        await chat_stream(
            session.id,
            ChatRequest(message="my answer"),
            current_user=user,
            db=db_session,
            redis=fake_redis,
        )

    assert exc.value.status_code == 409
    messages = await db_session.execute(
        select(InterviewMessage).where(InterviewMessage.session_id == session.id)
    )
    assert messages.scalars().all() == []


@pytest.mark.asyncio
async def test_end_interview_rejects_created_session(db_session, fake_redis):
    user, resume, job = await _seed_user_resume_job(db_session)
    session = InterviewSession(
        user=user,
        resume=resume,
        job=job,
        status="created",
        config={"max_turns": 12},
        questions=[],
    )
    db_session.add(session)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await end_interview(
            session.id,
            background_tasks=BackgroundTasks(),
            current_user=user,
            db=db_session,
            redis=fake_redis,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "invalid_interview_state"
    refreshed = await db_session.get(InterviewSession, session.id)
    assert refreshed.status == "created"
