"""Interview endpoints: create, start, chat (SSE), skip, end."""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.database import get_db
from app.core.interview_state import (
    ACTION_CHAT,
    ACTION_DELETE,
    ACTION_END,
    ACTION_SKIP,
    ACTION_START,
    STATUS_IN_PROGRESS,
    assert_can_perform,
    next_status_for,
)
from app.core.redis import get_redis
from app.core.session_lock import acquire_session_lock, release_session_lock
from app.api.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.models.job_position import JobPosition
from app.models.interview_session import InterviewSession, InterviewMessage
from app.schemas.interview import (
    InterviewCreateRequest, InterviewSessionOut,
    ChatRequest,
)
from app.agent.interview_agent import InterviewManager
from app.services.report_service import generate_report_background, mark_report_pending

router = APIRouter()


def _session_busy_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="当前面试正在处理上一项操作，请稍后再试",
    )


async def _locked_stream(redis: Redis, session_id: str, token: str, event_stream):
    try:
        async for event in event_stream:
            yield event
    finally:
        await release_session_lock(redis, session_id, token)


@router.get("")
async def list_interviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
):
    """List interviews for the current user, newest first."""
    offset = (page - 1) * page_size

    # Count
    count_result = await db.execute(
        select(func.count(InterviewSession.id)).where(InterviewSession.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    # Items
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == current_user.id)
        .options(selectinload(InterviewSession.job), selectinload(InterviewSession.report))
        .order_by(InterviewSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    sessions = result.scalars().all()
    session_ids = [s.id for s in sessions]
    answered_counts = {}
    if session_ids:
        counts = await db.execute(
            select(InterviewMessage.session_id, func.count(InterviewMessage.id))
            .where(
                InterviewMessage.session_id.in_(session_ids),
                InterviewMessage.role == "user",
                InterviewMessage.message_type == "answer",
            )
            .group_by(InterviewMessage.session_id)
        )
        answered_counts = {session_id: count for session_id, count in counts.all()}

    items = []
    for s in sessions:
        items.append({
            "id": s.id,
            "status": s.status,
            "job_title": s.job.title if s.job else None,
            "answered_count": answered_counts.get(s.id, 0),
            "max_turns": (s.config or {}).get("max_turns"),
            "duration_seconds": s.duration_seconds,
            "created_at": s.created_at.isoformat() if s.created_at else None,
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


@router.post("", status_code=201)
async def create_interview(
    req: InterviewCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new interview session."""
    # Verify resume
    result = await db.execute(
        select(Resume).where(Resume.id == req.resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    # Verify selected job. Interviews can only use existing enabled jobs.
    result = await db.execute(
        select(JobPosition).where(JobPosition.id == req.job_id, JobPosition.is_active == True)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在或未启用")

    raw_config = req.config or {}
    config = {
        "max_turns": int(raw_config.get("max_turns", 12)),
        "max_duration_minutes": int(raw_config.get("max_duration_minutes", 45)),
    }

    session = InterviewSession(
        user_id=current_user.id,
        resume_id=req.resume_id,
        job_id=job.id,
        status="created",
        config=config,
        questions=[],
        total_questions=0,
        current_question=0,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    return {
        "code": 201,
        "message": "面试会话已创建",
        "data": InterviewSessionOut.model_validate(session).model_dump()
    }


@router.post("/{session_id}/start")
async def start_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Start an interview session."""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    if session.status == "completed":
        raise HTTPException(status_code=400, detail="面试已结束")

    # If already in progress, return existing state without regenerating
    if session.status == STATUS_IN_PROGRESS:
        return {
            "code": 200,
            "message": "面试继续",
            "data": {
                "id": session.id,
                "status": "in_progress",
                "resume": True,
            }
        }

    assert_can_perform(session.status, ACTION_START)

    lock_token = await acquire_session_lock(redis, session.id)
    if not lock_token:
        raise _session_busy_error()

    now = datetime.now(timezone.utc)
    session.status = next_status_for(ACTION_START)
    session.started_at = now
    await db.flush()

    # Add system message
    sys_msg = InterviewMessage(
        session_id=session.id,
        role="system",
        content="面试已开始",
        message_type="system",
    )
    db.add(sys_msg)
    await db.flush()

    first_question_text = "你好！欢迎参加模拟面试。请先做一个简短的自我介绍吧。"
    session.current_question = 1
    db.add(InterviewMessage(
        session_id=session.id,
        role="ai",
        content=first_question_text,
        message_type="question",
        question_id=None,
    ))

    await db.commit()
    await release_session_lock(redis, session.id, lock_token)

    first_question = {
        "id": "intro",
        "content": first_question_text,
        "category": "basic",
        "turn_number": session.current_question,
        "answered_count": 0,
    }

    return {
        "code": 200,
        "message": "面试已开始",
        "data": {
            "id": session.id,
            "status": "in_progress",
            "started_at": now.isoformat(),
            "first_question": first_question,
        }
    }


@router.post("/{session_id}/chat/stream")
async def chat_stream(
    session_id: str,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """SSE streaming chat endpoint for interview conversation."""
    # Verify session
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="面试未在进行中")

    lock_token = await acquire_session_lock(redis, session.id)
    if not lock_token:
        raise _session_busy_error()

    assert_can_perform(session.status, ACTION_CHAT)

    # Save user message
    user_msg = InterviewMessage(
        session_id=session.id,
        role="user",
        content=req.message,
        message_type="answer",
    )
    db.add(user_msg)
    await db.flush()

    # Delegate to Interview Agent (pass user_msg_id for score persistence)
    manager = InterviewManager(db, redis)
    event_stream = manager.process_turn(session, req.message, user_msg.id)

    return StreamingResponse(
        _locked_stream(redis, session.id, lock_token, event_stream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/{session_id}/skip")
async def skip_question(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Skip the current question."""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    assert_can_perform(session.status, ACTION_SKIP)

    lock_token = await acquire_session_lock(redis, session.id)
    if not lock_token:
        raise _session_busy_error()

    # Generate skip message
    skip_msg = InterviewMessage(
        session_id=session.id,
        role="system",
        content="面试官跳过了当前题目",
        message_type="system",
    )
    db.add(skip_msg)

    # Generate next question through the same InterviewManager path used by normal turns
    manager = InterviewManager(db, redis)
    next_question_text = "请结合你的项目经验，谈谈相关的技术理解。"

    async for sse in manager.process_turn(session):
        if '"event": "question"' in sse:
            try:
                event_data = json.loads(sse.removeprefix("data: "))
                next_question_text = event_data["data"]["content"]
            except Exception:
                pass

    await db.commit()
    await release_session_lock(redis, session.id, lock_token)
    next_q = session.current_question

    return {
        "code": 200,
        "message": "已跳过当前题目",
        "data": {
            "skipped_question_id": f"q{max(next_q - 1, 0)}",
            "next_question": {
                "id": f"q{next_q}",
                "content": next_question_text,
                "turn_number": next_q,
                "answered_count": max(next_q - 1, 0),
            }
        }
    }


@router.post("/{session_id}/end")
async def end_interview(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """End the interview."""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    assert_can_perform(session.status, ACTION_END)

    lock_token = await acquire_session_lock(redis, session.id)
    if not lock_token:
        raise _session_busy_error()

    now = datetime.now(timezone.utc)
    session.status = next_status_for(ACTION_END)
    session.completed_at = now
    if session.started_at:
        # Convert naive started_at to aware if needed
        started = session.started_at
        if started.tzinfo is None:
            from datetime import timezone as tz
            started = started.replace(tzinfo=tz.utc)
        session.duration_seconds = int((now - started).total_seconds())
    await db.flush()

    await mark_report_pending(db, session)
    background_tasks.add_task(generate_report_background, session.id)
    await release_session_lock(redis, session.id, lock_token)

    return {
        "code": 200,
        "message": "面试已结束，报告正在生成",
        "data": {
            "session_id": session.id,
            "status": "completed",
            "completed_at": now.isoformat(),
            "duration_seconds": session.duration_seconds,
            "questions_answered": session.current_question,
            "questions_skipped": 0,
            "report_status": session.report_status,
            "report_id": None,
        }
    }


@router.get("/{session_id}/messages")
async def get_interview_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages for an interview session."""
    result = await db.execute(
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == session_id,
            InterviewMessage.role.in_(("ai", "user")),
        )
        .order_by(InterviewMessage.created_at)
    )
    messages = result.scalars().all()
    return {
        "code": 200,
        "data": [
            {"role": m.role, "content": m.content, "message_type": m.message_type}
            for m in messages
        ]
    }


@router.get("/{session_id}")
async def get_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single interview session (for status check)."""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试记录不存在")

    return {
        "code": 200,
        "data": {
            "id": session.id,
            "status": session.status,
            "current_question": session.current_question,
            "answered_count": session.current_question,
            "max_turns": (session.config or {}).get("max_turns"),
            "duration_seconds": session.duration_seconds,
        }
    }


@router.delete("/{session_id}")
async def delete_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Delete an interview session, its messages, and Redis state."""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="面试记录不存在")

    assert_can_perform(session.status, ACTION_DELETE)

    await db.delete(session)
    await db.flush()

    return {"code": 200, "message": "面试记录已删除"}
