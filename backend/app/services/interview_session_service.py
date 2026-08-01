"""Session lookup and initial-state construction for interview workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.interview_contracts import InterviewAction
from app.agent.interview_policy import update_coverage_for_turn
from app.agent.interview_workflow import make_initial_interview_state
from app.models.interview_session import InterviewMessage, InterviewSession
from app.models.job_position import JobPosition
from app.models.resume import Resume


async def get_owned_interview_session(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    *,
    load_context: bool = False,
) -> InterviewSession:
    """Return a user's interview session or raise the public 404 response."""
    query = select(InterviewSession).where(
        InterviewSession.id == session_id,
        InterviewSession.user_id == user_id,
    )
    if load_context:
        query = query.options(
            selectinload(InterviewSession.job),
            selectinload(InterviewSession.resume),
        )

    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="面试会话不存在")
    return session


def _job_snapshot(job: JobPosition) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "category": job.category,
        "level": job.level,
        "description": job.description or "",
        "requirements": job.requirements or {},
        "skill_tree": job.skill_tree or {},
    }


def _resume_summary(resume: Resume) -> str:
    parsed = resume.parsed_data or {}
    parts = [str(parsed.get("summary") or "").strip()]

    skills = parsed.get("skills") or []
    if skills:
        parts.append("技能：" + "、".join(str(item) for item in skills[:30]))

    for project in (parsed.get("projects") or [])[:5]:
        project_summary = "；".join(
            filter(
                None,
                (
                    str(project.get("name") or ""),
                    str(project.get("role") or ""),
                    str(project.get("description") or "")[:500],
                ),
            )
        )
        if project_summary:
            parts.append("项目：" + project_summary)

    return "\n".join(filter(None, parts))[:4000]


def _new_initial_state(session: InterviewSession, user_id: str) -> dict[str, Any]:
    return make_initial_interview_state(
        session_id=session.id,
        user_id=user_id,
        resume_id=session.resume_id,
        job_id=session.job_id,
        config=session.config,
        job_snapshot=_job_snapshot(session.job),
        resume_summary=_resume_summary(session.resume),
    )


async def _legacy_initial_state(
    db: AsyncSession,
    session: InterviewSession,
    user_id: str,
) -> dict[str, Any]:
    """Convert pre-LangGraph message rows without reintroducing dual writes."""
    started_at = session.started_at or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    state = make_initial_interview_state(
        session_id=session.id,
        user_id=user_id,
        resume_id=session.resume_id,
        job_id=session.job_id,
        config=session.config,
        job_snapshot=_job_snapshot(session.job),
        resume_summary=_resume_summary(session.resume),
        now=started_at,
    )
    result = await db.execute(
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == session.id,
            InterviewMessage.role.in_(("ai", "user")),
        )
        .order_by(InterviewMessage.created_at)
    )

    turns: list[dict[str, Any]] = []
    pending_question: dict[str, Any] | None = None
    for message in result.scalars().all():
        if message.role == "ai":
            pending_question = {
                "id": message.question_id or f"legacy-q{len(turns) + 1}",
                "content": message.content,
                "category": message.message_type or "technical",
                "origin": "legacy",
                "action": InterviewAction.SWITCH.value,
                "skill_path": "",
                "source_question_id": message.question_id,
                "probe_goal": "",
                "anchor": "",
                "turn_number": len(turns) + 1,
                "asked_at": (
                    message.created_at.isoformat() if message.created_at else None
                ),
            }
            continue

        if pending_question is None:
            continue

        extra = message.extra_data or {}
        skill_path = str(extra.get("skill_path") or "")
        pending_question["skill_path"] = skill_path
        turn_number = len(turns) + 1
        turn_id = f"{session.id}:{turn_number}"
        turns.append(
            {
                "turn_id": turn_id,
                "turn_number": turn_number,
                "question": pending_question,
                "answer": message.content,
                "status": "answered",
                "answered_at": (
                    message.created_at.isoformat() if message.created_at else None
                ),
            }
        )
        state["coverage"] = update_coverage_for_turn(
            state["coverage"],
            skill_path=skill_path,
            action=InterviewAction.SWITCH,
            turn_number=turn_number,
            answered=True,
        )
        pending_question = None

    state["turns"] = turns
    state["pending_evaluation_ids"] = [turn["turn_id"] for turn in turns]
    if pending_question is None:
        pending_question = {
            "id": f"legacy-resume-q{len(turns) + 1}",
            "content": "我们继续。请结合一个实际项目，介绍你解决关键技术难点的过程。",
            "category": "technical",
            "origin": "migration",
            "action": InterviewAction.BRIDGE.value,
            "skill_path": "",
            "source_question_id": None,
            "probe_goal": "了解候选人的实际技术判断和问题解决过程",
            "anchor": "",
            "turn_number": len(turns) + 1,
            "asked_at": datetime.now(timezone.utc).isoformat(),
        }
    state["current_question"] = pending_question
    return state


async def build_interview_initial_state(
    db: AsyncSession,
    session: InterviewSession,
    user_id: str,
    *,
    resume_legacy: bool,
) -> dict[str, Any]:
    """Build a graph state for either a new or pre-checkpoint session."""
    if resume_legacy:
        return await _legacy_initial_state(db, session, user_id)
    return _new_initial_state(session, user_id)
