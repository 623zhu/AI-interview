"""Interview APIs backed by the explicit LangGraph command workflow."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.interview_policy import normalize_interview_config, parse_datetime
from app.agent.interview_workflow import (
    conversation_messages,
    public_interview_question,
    public_interview_state,
)
from app.api.deps import get_current_user
from app.core.database import async_session_factory, get_db
from app.core.graph_runtime import get_graph_runtime
from app.core.interview_state import (
    ACTION_DELETE,
    ACTION_END,
    ACTION_SKIP,
    ACTION_START,
    assert_can_perform,
)
from app.core.redis import get_redis
from app.core.session_lock import (
    acquire_session_lock,
    release_session_lock,
    session_lock_lease,
)
from app.models.interview_session import InterviewMessage, InterviewSession
from app.models.job_position import JobPosition
from app.models.resume import Resume
from app.models.user import User
from app.schemas.interview import (
    ChatRequest,
    InterviewCreateRequest,
    InterviewSessionOut,
)
from app.services.report_service import generate_report_background
from app.services.interview_archive_service import (
    archive_terminal_interview,
    interview_duration_seconds,
    load_effective_interview_states,
    load_preferred_interview_state,
)
from app.services.interview_session_service import (
    build_interview_initial_state,
    get_owned_interview_session,
)

logger = logging.getLogger(__name__)
router = APIRouter()
SSE_HEARTBEAT_SECONDS = 15


def _session_busy_error() -> HTTPException:
    return HTTPException(
        status_code=409, detail="当前面试正在处理上一项操作，请稍后再试。"
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return (
        "data: "
        + json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
        + "\n\n"
    )


async def _evaluate_turn_background(session_id: str, turn_id: str) -> None:
    try:
        await get_graph_runtime().evaluate_turn(session_id, turn_id)
    except Exception:
        logger.exception(
            "Background turn evaluation failed session=%s turn=%s", session_id, turn_id
        )


def _schedule_new_work(
    background_tasks: BackgroundTasks,
    *,
    session_id: str,
    before_turn_count: int,
    state: dict[str, Any],
) -> None:
    """把本次新增轮次登记为响应结束后的后台任务。

    逐题评价不会阻塞下一题；如果主图已经结束，再追加报告生成任务。
    Report Graph 会补跑缺失评价，因此后台评价失败也不会丢失最终报告输入。
    """
    turns = state.get("turns") or []
    for turn in turns[before_turn_count:]:
        if turn.get("status") == "answered":
            background_tasks.add_task(
                _evaluate_turn_background, session_id, str(turn["turn_id"])
            )
    if state.get("status") == "completed":
        background_tasks.add_task(generate_report_background, session_id)


@router.get("")
async def list_interviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
):
    offset = (page - 1) * page_size
    count_result = await db.execute(
        select(func.count(InterviewSession.id)).where(
            InterviewSession.user_id == current_user.id
        )
    )
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == current_user.id)
        .options(
            selectinload(InterviewSession.job),
            selectinload(InterviewSession.archive),
        )
        .order_by(InterviewSession.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    runtime = get_graph_runtime()
    sessions = list(result.scalars().all())
    states = await load_effective_interview_states(runtime, sessions)
    items = []
    for session in sessions:
        state = states[session.id]
        public = public_interview_state(state) if state else {}
        items.append(
            {
                "id": session.id,
                "status": public.get("status", session.status),
                "job_title": session.job.title if session.job else None,
                "answered_count": public.get("answered_count", 0),
                "max_turns": public.get(
                    "max_turns", (session.config or {}).get("max_turns")
                ),
                "duration_seconds": (
                    interview_duration_seconds(state)
                    if state
                    else session.duration_seconds
                ),
                "created_at": session.created_at.isoformat()
                if session.created_at
                else None,
            }
        )
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": count_result.scalar() or 0,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("", status_code=201)
async def create_interview(
    req: InterviewCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume_result = await db.execute(
        select(Resume).where(
            Resume.id == req.resume_id, Resume.user_id == current_user.id
        )
    )
    if not resume_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="简历不存在")
    job_result = await db.execute(
        select(JobPosition).where(
            JobPosition.id == req.job_id, JobPosition.is_active.is_(True)
        )
    )
    if not job_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="岗位不存在或未启用")

    config = normalize_interview_config(req.config)
    session = InterviewSession(
        user_id=current_user.id,
        resume_id=req.resume_id,
        job_id=req.job_id,
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
        "data": InterviewSessionOut.model_validate(session).model_dump(),
    }


@router.post("/{session_id}/start")
async def start_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    session = await get_owned_interview_session(
        db, session_id, current_user.id, load_context=True
    )
    runtime = get_graph_runtime()
    existing = await runtime.get_interview_state(session.id)
    if existing:
        if existing.get("status") == "completed":
            await archive_terminal_interview(db, session, existing)
            await db.commit()
            raise HTTPException(status_code=400, detail="面试已结束")
        if session.status != "in_progress":
            session.status = "in_progress"
            started_at = parse_datetime(existing.get("started_at"))
            if started_at:
                session.started_at = started_at.replace(tzinfo=None)
            await db.commit()
        public = public_interview_state(existing)
        return {
            "code": 200,
            "message": "面试继续",
            "data": {**public, "resume": True},
        }

    if session.status != "in_progress":
        assert_can_perform(session.status, ACTION_START)
    token = await acquire_session_lock(redis, session.id)
    if not token:
        raise _session_busy_error()
    resumed_legacy = session.status == "in_progress"
    async with session_lock_lease(redis, session.id, token):
        initial = await build_interview_initial_state(
            db,
            session,
            current_user.id,
            resume_legacy=resumed_legacy,
        )
        await runtime.start_interview(initial)
        state = await runtime.get_interview_state(session.id)
        session.status = "in_progress"
        session.started_at = parse_datetime(state.get("started_at")).replace(
            tzinfo=None
        )
        await db.commit()

    public = public_interview_state(state)
    first_question = {
        **public_interview_question(state["current_question"]),
        "answered_count": public["answered_count"],
    }
    return {
        "code": 200,
        "message": "面试已开始",
        "data": {
            **public,
            "first_question": first_question,
            "resume": resumed_legacy,
        },
    }


@router.post("/{session_id}/chat/stream")
async def chat_stream(
    session_id: str,
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """接收一条候选人回答，恢复主图，并通过 SSE 返回下一题。

    该接口只等待实时面试主图，不等待逐题评价。会话锁覆盖整个 SSE
    生成过程，保证同一场面试不会同时处理两条回答。
    """
    session = await get_owned_interview_session(db, session_id, current_user.id)
    # 锁在返回 StreamingResponse 前获取，在 stream() 退出时释放并持续续租。
    token = await acquire_session_lock(redis, session.id)
    if not token:
        raise _session_busy_error()
    runtime = get_graph_runtime()
    try:
        # 保存回答前的状态快照，用于校验会话状态并判断本轮新增了哪些 turn。
        current = await runtime.get_interview_state(session.id)
        if not current or current.get("status") != "in_progress":
            raise HTTPException(status_code=400, detail="面试未在进行中")
    except Exception:
        await release_session_lock(redis, session.id, token)
        raise

    async def stream():
        """SSE 异步生成器：先发状态事件，图完成后再发下一题或结束事件。"""
        async with session_lock_lease(redis, session.id, token):
            try:
                yield _sse("status", {"status": "thinking"})
                before = len(current.get("turns") or [])
                # 图运行可能包含一次 LLM/RAG 调用；放入 Task 后可以在等待期间发送心跳。
                operation = asyncio.create_task(
                    runtime.resume_interview(
                        session.id,
                        {
                            "type": "answer",
                            "message": req.message,
                            "event_id": req.event_id,
                            "expected_question_id": req.expected_question_id,
                        },
                    )
                )
                try:
                    while not operation.done():
                        done, _ = await asyncio.wait(
                            {operation}, timeout=SSE_HEARTBEAT_SECONDS
                        )
                        if not done:
                            yield _sse("heartbeat", {"status": "thinking"})
                    await operation
                finally:
                    if not operation.done():
                        operation.cancel()
                        try:
                            await operation
                        except asyncio.CancelledError:
                            pass
                state = await runtime.get_interview_state(session.id)
                if state.get("status") == "completed":
                    async with async_session_factory() as archive_db:
                        archive_session = await archive_db.get(
                            InterviewSession, session.id
                        )
                        if not archive_session:
                            raise ValueError(
                                f"Interview directory {session.id} not found"
                            )
                        await archive_terminal_interview(
                            archive_db, archive_session, state
                        )
                        await archive_db.commit()
                # 此处只登记任务；FastAPI 会在 SSE 响应结束后执行逐题评价/报告。
                _schedule_new_work(
                    background_tasks,
                    session_id=session.id,
                    before_turn_count=before,
                    state=state,
                )
                public = public_interview_state(state)
                if state.get("status") == "completed":
                    yield _sse("done", public)
                else:
                    # 主图已经在新的 interrupt 处暂停，current_question 就是下一题。
                    question = {
                        **public_interview_question(state.get("current_question")),
                        "answered_count": public["answered_count"],
                    }
                    yield _sse("question", question)
            except Exception as exc:
                logger.exception("Interview turn failed session=%s", session.id)
                yield _sse("error", {"message": str(exc)[:300] or "生成下一题失败"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/skip")
async def skip_question(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    session = await get_owned_interview_session(db, session_id, current_user.id)
    if session.status != "in_progress":
        assert_can_perform(session.status, ACTION_SKIP)
    token = await acquire_session_lock(redis, session.id)
    if not token:
        raise _session_busy_error()
    async with session_lock_lease(redis, session.id, token):
        runtime = get_graph_runtime()
        current = await runtime.get_interview_state(session.id)
        if not current:
            raise HTTPException(status_code=400, detail="请先恢复面试会话")
        status = (current or {}).get("status", session.status)
        assert_can_perform(status, ACTION_SKIP)
        before = len(current.get("turns") or [])
        skipped_id = (current.get("current_question") or {}).get("id")
        await runtime.resume_interview(session.id, {"type": "skip"})
        state = await runtime.get_interview_state(session.id)
        await archive_terminal_interview(db, session, state)
        await db.commit()
        _schedule_new_work(
            background_tasks,
            session_id=session.id,
            before_turn_count=before,
            state=state,
        )
    public = public_interview_state(state)
    next_question = state.get("current_question")
    if next_question:
        next_question = {
            **public_interview_question(next_question),
            "answered_count": public["answered_count"],
        }
    return {
        "code": 200,
        "message": "已跳过当前题目",
        "data": {
            "skipped_question_id": skipped_id,
            "next_question": next_question,
            **public,
        },
    }


@router.post("/{session_id}/end")
async def end_interview(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    session = await get_owned_interview_session(db, session_id, current_user.id)
    if session.status != "in_progress":
        assert_can_perform(session.status, ACTION_END)
    token = await acquire_session_lock(redis, session.id)
    if not token:
        raise _session_busy_error()
    async with session_lock_lease(redis, session.id, token):
        runtime = get_graph_runtime()
        current = await runtime.get_interview_state(session.id)
        if not current:
            raise HTTPException(status_code=400, detail="请先恢复面试会话")
        status = (current or {}).get("status", session.status)
        assert_can_perform(status, ACTION_END)
        await runtime.resume_interview(session.id, {"type": "end"})
        state = await runtime.get_interview_state(session.id)
        await archive_terminal_interview(db, session, state)
        await db.commit()
        background_tasks.add_task(generate_report_background, session.id)
    public = public_interview_state(state)
    return {
        "code": 200,
        "message": "面试已结束，报告正在生成",
        "data": {
            "session_id": session.id,
            **public,
            "duration_seconds": interview_duration_seconds(state),
            "questions_answered": public["answered_count"],
            "report_id": None,
        },
    }


@router.get("/{session_id}/messages")
async def get_interview_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_owned_interview_session(db, session_id, current_user.id)
    try:
        runtime = get_graph_runtime()
    except RuntimeError:
        runtime = None
    state = await load_preferred_interview_state(
        db,
        runtime,
        session,
        allow_runtime_unavailable=True,
    )
    if state:
        return {"code": 200, "data": conversation_messages(state)}

    # Read-only compatibility for sessions created before graph checkpoints.
    result = await db.execute(
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == session_id,
            InterviewMessage.role.in_(("ai", "user")),
        )
        .order_by(InterviewMessage.created_at)
    )
    return {
        "code": 200,
        "data": [
            {
                "role": item.role,
                "content": item.content,
                "message_type": item.message_type,
            }
            for item in result.scalars().all()
        ],
    }


@router.get("/{session_id}")
async def get_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await get_owned_interview_session(db, session_id, current_user.id)
    state = await load_preferred_interview_state(db, get_graph_runtime(), session)
    if not state:
        return {
            "code": 200,
            "data": {
                "id": session.id,
                "status": session.status,
                "current_question": None,
                "answered_count": 0,
                "max_turns": (session.config or {}).get("max_turns"),
                "duration_seconds": session.duration_seconds,
                "report_status": session.report_status,
            },
        }
    return {
        "code": 200,
        "data": {
            **public_interview_state(state),
            "duration_seconds": interview_duration_seconds(state),
        },
    }


@router.delete("/{session_id}")
async def delete_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    session = await get_owned_interview_session(db, session_id, current_user.id)
    token = await acquire_session_lock(redis, session.id)
    if not token:
        raise _session_busy_error()
    async with session_lock_lease(redis, session.id, token):
        runtime = get_graph_runtime()
        state = await runtime.get_interview_state(session.id)
        assert_can_perform((state or {}).get("status", session.status), ACTION_DELETE)
        await runtime.delete_session(session.id)
        await db.delete(session)
        await db.flush()
    return {"code": 200, "message": "面试记录已删除"}
