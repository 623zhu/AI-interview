import pytest
from sqlalchemy import select

from app.api.v1.reports import get_report_by_session, generate_report_for_session_sync
from app.models.interview_session import InterviewMessage, InterviewSession
from app.models.score_report import ScoreReport
from tests.test_interviews import _seed_user_resume_job


@pytest.mark.asyncio
async def test_get_report_by_session_has_no_generation_side_effect(db_session):
    user, resume, job = await _seed_user_resume_job(db_session)
    session = InterviewSession(
        user=user,
        resume=resume,
        job=job,
        status="in_progress",
        config={"max_turns": 12, "max_duration_minutes": 45},
    )
    db_session.add(session)
    await db_session.flush()

    response = await get_report_by_session(session.id, current_user=user, db=db_session)

    assert response["code"] == 404
    assert response["data"]["status"] == "pending"
    refreshed = await db_session.get(InterviewSession, session.id)
    assert refreshed.status == "in_progress"
    report_count = await db_session.execute(select(ScoreReport))
    assert report_count.scalars().all() == []


@pytest.mark.asyncio
async def test_generate_report_sync_explicitly_creates_report(db_session):
    user, resume, job = await _seed_user_resume_job(db_session)
    session = InterviewSession(
        user=user,
        resume=resume,
        job=job,
        status="completed",
        config={"max_turns": 12, "max_duration_minutes": 45},
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add_all([
        InterviewMessage(
            session_id=session.id,
            role="ai",
            content="请介绍一下你做过的缓存设计。",
            message_type="question",
        ),
        InterviewMessage(
            session_id=session.id,
            role="user",
            content="我使用 Redis 做热点数据缓存，并设置过期时间。",
            message_type="answer",
            extra_data={
                "comment": "能说明 Redis 缓存和过期策略，但还缺少击穿保护。",
                "confidence": 0.6,
                "depth": 0.5,
            },
        ),
    ])
    await db_session.flush()

    response = await generate_report_for_session_sync(session.id, current_user=user, db=db_session)

    assert response["code"] == 201
    assert response["data"]["status"] == "completed"
    assert response["data"]["overall_score"] == 56
    assert response["data"]["dimension_scores"]["score_formula"]
    assert response["data"]["question_evaluations"][0]["comment"]
    refreshed = await db_session.get(InterviewSession, session.id)
    assert refreshed.report_status == "completed"
