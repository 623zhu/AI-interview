"""Interview endpoints: create, start, chat (SSE), skip, end."""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.core.database import get_db
from app.core.redis import get_redis
from app.api.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.models.job_position import JobPosition
from app.models.question import Question
from app.models.interview_session import InterviewSession, InterviewMessage
from app.agent.rag import search_questions
from app.schemas.interview import (
    InterviewCreateRequest, InterviewSessionOut,
    ChatRequest, StartInterviewResponse,
)
from app.agent.interview_agent import InterviewManager
from app.agent.score_agent import generate_report as generate_score_report
from app.utils.resume_utils import build_resume_context

router = APIRouter()
logger = logging.getLogger(__name__)


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

    items = []
    for s in sessions:
        print(f"[DEBUG] list interview {s.id[:8]}: status={s.status}")
        items.append({
            "id": s.id,
            "status": s.status,
            "job_title": s.job.title if s.job else None,
            "total_questions": s.total_questions,
            "current_question": s.current_question,
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

    # Find or create job by title
    result = await db.execute(
        select(JobPosition).where(JobPosition.title == req.job_title)
    )
    job = result.scalar_one_or_none()
    if not job:
        # Create a job on-the-fly with the user's desired title
        job = JobPosition(
            title=req.job_title,
            category="general",
            level="mid",
            requirements={},
            is_active=True,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)

    # Build config
    config = req.config or {
        "question_count": 2,
        "difficulty_distribution": {"easy": 1, "medium": 4, "hard": 2},
        "max_duration_minutes": 45,
        "enable_follow_up": True,
    }

    session = InterviewSession(
        user_id=current_user.id,
        resume_id=req.resume_id,
        job_id=job.id,
        status="created",
        config=config,
        questions=[],
        total_questions=config.get("question_count", 7),
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # Pre-select questions from Chroma vector DB for this interview
    total_q = session.total_questions
    try:
        # Build search query from job + resume context (including project experience)
        resume_summary = ""
        if resume.parsed_data:
            rd = resume.parsed_data
            parts = []
            skills = rd.get("skills", [])
            if skills:
                parts.append("技能: " + ", ".join(skills[:8]))
            # Include work experience for better question matching
            work_exp = rd.get("work_experience") or rd.get("experience") or []
            if isinstance(work_exp, list):
                for exp in work_exp[:2]:
                    if isinstance(exp, dict):
                        exp_text = f"{exp.get('company','')} {exp.get('title','')} {exp.get('description','')[:150]}"
                        parts.append(exp_text)
            # Include personal projects
            projects = rd.get("projects", [])
            if isinstance(projects, list):
                for proj in projects[:2]:
                    if isinstance(proj, dict):
                        proj_text = f"{proj.get('name','')} {proj.get('description','')[:100]}"
                        parts.append(proj_text)
            resume_summary = " | ".join(parts)

        search_text = f"{job.title} {job.category} {resume_summary}"
        rag_results = await search_questions(query=search_text, category=None, k=total_q + 3)

        if rag_results:
            questions = []
            for i, r in enumerate(rag_results[:total_q + 3]):
                mysql_id = r.metadata.get("mysql_id", "") if isinstance(r.metadata, dict) else ""
                question_obj = None
                if mysql_id:
                    q_result = await db.execute(select(Question).where(Question.id == mysql_id))
                    question_obj = q_result.scalar_one_or_none()

                questions.append({
                    "question_number": i + 1,
                    "id": mysql_id,
                    "content": question_obj.content if question_obj else "",
                    "category": question_obj.category if question_obj else r.metadata.get("category", "") if isinstance(r.metadata, dict) else "",
                    "difficulty": question_obj.difficulty if question_obj else r.metadata.get("difficulty", "medium") if isinstance(r.metadata, dict) else "medium",
                })

            session.questions = questions
            await db.flush()
            await db.refresh(session)
            logger.info("Pre-selected %d questions from Chroma for interview %s", len(questions), session.id)
        else:
            logger.warning("Chroma returned no results for interview %s, questions will be generated by LLM", session.id)
    except Exception as e:
        logger.warning("Failed to pre-select questions from Chroma for interview %s: %s", session.id, e)
        # session.questions stays as [] — fallback handled in interview agent

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
    if session.status == "in_progress":
        return {
            "code": 200,
            "message": "面试继续",
            "data": {
                "id": session.id,
                "status": "in_progress",
                "resume": True,
            }
        }

    now = datetime.now(timezone.utc)
    session.status = "in_progress"
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

    # Generate first question via ReAct Agent (opening turn)
    manager = InterviewManager(db, redis)
    first_question_text = "你好！欢迎参加模拟面试。请先做一个简短的自我介绍吧。"

    async for sse in manager.process_turn(session):
        # Extract question content from SSE event
        if '"event": "question"' in sse:
            try:
                event_data = json.loads(sse.removeprefix("data: "))
                first_question_text = event_data["data"]["content"]
            except Exception:
                pass

    await db.commit()

    first_question = {
        "id": "intro",
        "content": first_question_text,
        "category": "basic",
        "question_number": 1,
        "total_questions": session.total_questions,
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

    print(f"[DEBUG] chat_stream: current_question={session.current_question} total={session.total_questions}")

    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="面试未在进行中")

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
        event_stream,
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

    session.current_question += 1
    next_q = session.current_question  # current_question 已自增，下一题直接用它

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

    return {
        "code": 200,
        "message": "已跳过当前题目",
        "data": {
            "skipped_question_id": f"q{next_q - 1}",
            "next_question": {
                "id": f"q{next_q}",
                "content": next_question_text,
                "question_number": next_q,
                "total_questions": session.total_questions,
            }
        }
    }


@router.post("/{session_id}/end")
async def end_interview(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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

    now = datetime.now(timezone.utc)
    session.status = "completed"
    session.completed_at = now
    if session.started_at:
        # Convert naive started_at to aware if needed
        started = session.started_at
        if started.tzinfo is None:
            from datetime import timezone as tz
            started = started.replace(tzinfo=tz.utc)
        session.duration_seconds = int((now - started).total_seconds())
    await db.flush()

    # Generate report
    report_id = None
    try:
        report = await generate_score_report(db, session.id)
        await db.commit()
        report_id = report.id
    except Exception:
        await db.rollback()
        # Save session as completed even if report fails
        session = await db.get(InterviewSession, session_id)
        if session:
            session.status = "completed"
            session.completed_at = now
            if session.started_at:
                session.duration_seconds = int((now - session.started_at).total_seconds())
            await db.commit()

    return {
        "code": 200,
        "message": "面试已结束" + ("，报告已生成" if report_id else "，报告生成失败请稍后重试"),
        "data": {
            "session_id": session.id,
            "status": "completed",
            "completed_at": now.isoformat(),
            "duration_seconds": session.duration_seconds,
            "questions_answered": session.current_question,
            "questions_skipped": session.total_questions - session.current_question,
            "report_id": report_id,
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
        .where(InterviewMessage.session_id == session_id)
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

    await db.delete(session)
    await db.flush()

    return {"code": 200, "message": "面试记录已删除"}
