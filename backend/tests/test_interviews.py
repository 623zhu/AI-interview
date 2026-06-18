import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.interviews import create_interview
from app.api.v1.interviews import get_interview_messages
from app.api.v1.interviews import start_interview
from app.models.interview_session import InterviewSession
from app.models.interview_session import InterviewMessage
from app.models.job_position import JobPosition
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import InterviewCreateRequest


async def _seed_user_resume_job(
    db_session,
    *,
    job_active=True,
    username="alice",
    email="alice@example.com",
):
    user = User(
        username=username,
        email=email,
        password_hash="hash",
    )
    resume = Resume(
        user=user,
        original_filename="resume.pdf",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        file_size=100,
        parse_status="completed",
    )
    job = JobPosition(
        title="后端工程师",
        category="backend",
        level="mid",
        requirements={},
        is_active=job_active,
    )
    db_session.add_all([user, resume, job])
    await db_session.flush()
    return user, resume, job


@pytest.mark.asyncio
async def test_create_interview_uses_existing_active_job(db_session):
    user, resume, job = await _seed_user_resume_job(db_session)

    response = await create_interview(
        InterviewCreateRequest(resume_id=resume.id, job_id=job.id),
        current_user=user,
        db=db_session,
    )

    assert response["code"] == 201
    data = response["data"]
    assert data["resume_id"] == resume.id
    assert data["job_id"] == job.id
    assert data["config"] == {"max_turns": 12, "max_duration_minutes": 45}
    assert data["questions"] if "questions" in data else True

    result = await db_session.execute(select(InterviewSession))
    sessions = result.scalars().all()
    assert len(sessions) == 1
    assert sessions[0].questions == []
    assert sessions[0].total_questions == 0


@pytest.mark.asyncio
async def test_create_interview_rejects_inactive_job(db_session):
    user, resume, job = await _seed_user_resume_job(db_session, job_active=False)

    with pytest.raises(HTTPException) as exc:
        await create_interview(
            InterviewCreateRequest(resume_id=resume.id, job_id=job.id),
            current_user=user,
            db=db_session,
        )

    assert exc.value.status_code == 404


def test_create_interview_schema_requires_job_id_not_job_title():
    with pytest.raises(ValidationError):
        InterviewCreateRequest(resume_id="resume-1", job_title="后端工程师")


@pytest.mark.asyncio
async def test_get_interview_messages_hides_system_messages(db_session):
    user, resume, job = await _seed_user_resume_job(db_session)
    session = InterviewSession(
        user=user,
        resume=resume,
        job=job,
        status="in_progress",
        config={"max_turns": 12},
        questions=[],
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add_all([
        InterviewMessage(
            session_id=session.id,
            role="system",
            content="面试已开始",
            message_type="system",
        ),
        InterviewMessage(
            session_id=session.id,
            role="ai",
            content="请先做一个自我介绍。",
            message_type="question",
        ),
        InterviewMessage(
            session_id=session.id,
            role="user",
            content="好的。",
            message_type="answer",
        ),
    ])
    await db_session.flush()

    response = await get_interview_messages(
        session.id,
        current_user=user,
        db=db_session,
    )

    assert [m["role"] for m in response["data"]] == ["ai", "user"]
    assert all(m["content"] != "面试已开始" for m in response["data"])


@pytest.mark.asyncio
async def test_start_interview_uses_fixed_intro_question(db_session, fake_redis):
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

    response = await start_interview(
        session.id,
        current_user=user,
        db=db_session,
        redis=fake_redis,
    )

    first_question = response["data"]["first_question"]
    assert first_question["content"] == "你好！欢迎参加模拟面试。请先做一个简短的自我介绍吧。"
    assert first_question["turn_number"] == 1

    messages = await db_session.execute(
        select(InterviewMessage).where(
            InterviewMessage.session_id == session.id,
            InterviewMessage.role == "ai",
        )
    )
    stored = messages.scalar_one()
    assert stored.content == first_question["content"]
