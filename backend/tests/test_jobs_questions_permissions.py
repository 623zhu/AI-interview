import pytest
from fastapi import HTTPException

from app.api.v1.jobs import delete_job
from app.api.v1.questions import get_question, list_questions
from app.models.interview_session import InterviewSession
from app.models.question import Question
from app.models.user import User
from tests.test_interviews import _seed_user_resume_job


@pytest.mark.asyncio
async def test_delete_referenced_job_disables_instead_of_hard_delete(db_session):
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

    response = await delete_job(job.id, db=db_session)

    assert response["code"] == 200
    assert response["data"]["is_active"] is False
    assert response["data"]["referenced_interviews"] == 1
    refreshed = await db_session.get(type(job), job.id)
    assert refreshed is not None
    assert refreshed.is_active is False


@pytest.mark.asyncio
async def test_question_list_is_admin_only(db_session):
    user = User(username="alice", email="alice@example.com", password_hash="hash")
    admin = User(username="admin", email="admin@example.com", password_hash="hash", is_admin=True)
    question = Question(
        category="backend",
        difficulty="medium",
        skill_nodes=["Redis"],
        content="Redis 击穿怎么处理？",
        expected_points="互斥锁、逻辑过期",
        reference_answer="参考答案不应给普通用户",
        source="admin",
        is_active=True,
    )
    db_session.add_all([user, admin, question])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await list_questions(current_user=user, db=db_session)
    assert exc.value.status_code == 403

    response = await list_questions(current_user=admin, db=db_session)
    item = response["data"]["items"][0]
    assert item["content"] == question.content
    assert item["expected_points"] == question.expected_points
    assert "reference_answer" not in item
    assert "evaluation_criteria" not in item


@pytest.mark.asyncio
async def test_question_detail_is_admin_only(db_session):
    user = User(username="alice", email="alice@example.com", password_hash="hash")
    admin = User(username="admin", email="admin@example.com", password_hash="hash", is_admin=True)
    question = Question(
        category="backend",
        difficulty="medium",
        content="Redis 击穿怎么处理？",
        expected_points="互斥锁、逻辑过期",
        reference_answer="参考答案",
        source="admin",
        is_active=True,
    )
    db_session.add_all([user, admin, question])
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await get_question(question.id, current_user=user, db=db_session)
    assert exc.value.status_code == 403

    response = await get_question(question.id, current_user=admin, db=db_session)
    assert response["data"]["reference_answer"] == "参考答案"
