"""Interview Agent — profile-building via langgraph ReAct.

Python is a shell: build context, create agent, invoke, stream SSE.
The agent drives everything: analysis, skill selection, question retrieval,
scoring, and profile updates. Profile persists in Redis across turns.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from langchain_core.messages import HumanMessage

from app.agent.tools import (
    ReactContext,
    CandidateProfile,
    make_interview_agent,
    build_react_prompt,
)
from app.models.question_link import InterviewQuestionLink
from app.utils.resume_utils import build_resume_context
from app.models.interview_session import InterviewSession, InterviewMessage
from app.models.resume import Resume
from app.models.job_position import JobPosition

logger = logging.getLogger(__name__)

PROFILE_TTL = 86400  # 24h


def sse_event(event: str, data: dict) -> str:
    return f"data: {json.dumps({'event': event, 'data': data}, ensure_ascii=False)}\n\n"


class InterviewManager:

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    # ── Profile persistence ────────────────────────────────

    async def _load_profile(self, session_id: str) -> CandidateProfile:
        try:
            raw = await self.redis.get(f"profile:{session_id}")
            if raw:
                data = json.loads(raw)
                p = CandidateProfile()
                p.skills = data.get("skills", {})
                p.impression = data.get("impression", "")
                p.current_target = data.get("current_target", "")
                return p
        except Exception:
            pass
        return CandidateProfile()

    async def _save_profile(self, session_id: str, profile: CandidateProfile):
        try:
            data = {
                "skills": profile.skills,
                "impression": profile.impression,
                "current_target": profile.current_target,
            }
            await self.redis.setex(
                f"profile:{session_id}", PROFILE_TTL,
                json.dumps(data, ensure_ascii=False),
            )
        except Exception:
            logger.warning("Failed to save profile", exc_info=True)

    # ── Skill tree formatting ───────────────────────────────

    @staticmethod
    def _format_skill_tree(job: JobPosition | None) -> str:
        if not job or not job.skill_tree:
            return "（无技能树）"
        st = job.skill_tree
        lines = []
        for d in st.get("domains", []):
            lines.append(f"**{d['name']}** (权重 {d.get('weight', 0)})")
            for s in d.get("skills", []):
                indent = "  ├─"
                lines.append(f"{indent} {s['name']} [{s.get('level', 'medium')}]")
                for c in s.get("children", []):
                    lines.append(f"  │  └─ {c['name']}")
        return "\n".join(lines)

    # ── Main ────────────────────────────────────────────────

    async def process_turn(
        self,
        session: InterviewSession,
        user_message: str = "",
        user_msg_id: str = "",
    ) -> AsyncGenerator[str, None]:
        try:
            resume = await self.db.get(Resume, session.resume_id)
            job = await self.db.get(JobPosition, session.job_id)
            history = await self._get_history(session.id)

            yield sse_event("status", {
                "status": "thinking",
                "message": "分析回答，更新画像...",
            })

            # Load persisted profile
            profile = await self._load_profile(session.id)

            ctx = ReactContext(self.db, session, user_msg_id)
            ctx.profile = profile  # carry forward accumulated profile

            prompt = build_react_prompt(
                job_title=job.title if job else "通用岗位",
                job_category=job.category if job else "general",
                resume_summary=build_resume_context(resume),
                total_q=session.total_questions or 3,
                answered_count=session.current_question,
                asked_topics=self._asked_topics(history),
                recent_history=self._format_history(history),
                latest_answer=user_message[:800] if user_message else "",
                skill_tree_text=self._format_skill_tree(job),
                profile_text=profile.to_text(),
            )

            agent = make_interview_agent(ctx, prompt)
            result = await agent.ainvoke({
                "messages": [HumanMessage(content=user_message or "（开场）")]
            })

            speak = self._extract_speak(result)
            # If agent produced meta-commentary instead of a real question
            bad_patterns = ["（等待", "好的，刚才", "等你回答", "已经问出去", "请回答"]
            is_meta = any(p in speak for p in bad_patterns)
            if not speak or len(speak) < 10 or is_meta:
                logger.warning("Agent produced meta-commentary, retrying. speak=%s", speak[:100])
                retry_result = await agent.ainvoke({
                    "messages": result["messages"] + [
                        HumanMessage(content="你刚才说的是系统内部对话，不是对候选人说的话。请从 retrieve_questions 返回的候选池中选一道题，把题目原文 Speak 出来。不要说你已经问了、不要说你等回答——直接说题目。")
                    ]
                })
                speak = self._extract_speak(retry_result)
            print(f"[Agent Speak] {speak[:200]}")

            # ── Emit ReAct trace: tool calls & observations ──
            for msg in result.get("messages", []):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield sse_event("action", {
                            "tool": tc.get("name", ""),
                            "input": tc.get("args", {}),
                        })
                if hasattr(msg, "type") and msg.type == "tool":
                    yield sse_event("observation", {
                        "tool": getattr(msg, "name", ""),
                        "result": str(msg.content)[:300],
                    })

            # Save profile
            await self._save_profile(session.id, ctx.profile)
            print(f"[Profile] {json.dumps(ctx.profile.skills, ensure_ascii=False)}")

            # Emit score + profile update
            if ctx.evaluation:
                yield sse_event("score", {
                    "question_id": f"q{session.current_question}",
                    "comment": ctx.evaluation.get("comment", ""),
                    "skill_path": ctx.evaluation.get("skill_path", ""),
                    "confidence": ctx.evaluation.get("confidence", 0),
                })
            yield sse_event("profile", {
                "skills": ctx.profile.skills,
                "current_target": ctx.profile.current_target,
            })

            if ctx.is_ended:
                # Stream end message then done
                for char in speak:
                    yield sse_event("token", {"content": char})
                yield sse_event("done", {
                    "session_id": session.id,
                    "completed": True,
                    "message": speak,
                    "questions_answered": session.current_question,
                    "duration_seconds": self._calc_duration(session),
                    "report_id": ctx.report_id,
                })
                return

            # Stream question character by character
            for char in speak:
                yield sse_event("token", {"content": char})
                import asyncio
                await asyncio.sleep(0.025)

            session.current_question += 1
            selected_question_id = self._match_selected_question_id(speak, ctx.search_results)
            yield sse_event("question", {
                "question_id": f"q{session.current_question}",
                "content": speak,
                "question_number": session.current_question,
                "total_questions": session.total_questions,
                "source_question_id": selected_question_id,
            })

            self.db.add(InterviewMessage(
                session_id=session.id,
                role="ai",
                content=speak,
                message_type="question",
                question_id=selected_question_id,
            ))
            if selected_question_id:
                self.db.add(InterviewQuestionLink(
                    interview_id=session.id,
                    question_id=selected_question_id,
                ))
            await self.db.flush()
            await self.db.commit()

        except Exception:
            logger.exception("Turn failed session=%s", session.id)
            yield sse_event("error", {"code": 500, "message": "处理出错"})

    @staticmethod
    def _extract_speak(result: dict) -> str:
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and msg.type == "ai":
                c = msg.content
                if c and len(c.strip()) > 2:
                    return c.strip()
        return ""

    async def _get_history(self, session_id: str) -> list[dict]:
        r = await self.db.execute(
            select(InterviewMessage)
            .where(InterviewMessage.session_id == session_id)
            .order_by(InterviewMessage.created_at.desc())
            .limit(20)
        )
        return [
            {"role": m.role, "content": m.content, "message_type": m.message_type}
            for m in reversed(r.scalars().all())
        ]

    def _asked_topics(self, history: list[dict]) -> str:
        topics = [
            f"- {m['content'][:100]}"
            for m in history
            if m["role"] == "ai" and m.get("message_type") in ("question", "follow_up")
        ]
        return "\n".join(topics[-7:]) or "（暂无）"

    def _format_history(self, history: list[dict]) -> str:
        lines = []
        for m in history[-8:]:
            label = "面试官" if m["role"] == "ai" else "候选人"
            lines.append(f"{label}：{m['content'][:200].replace(chr(10), ' ')}")
        return "\n".join(lines) or "（面试刚开始）"

    @staticmethod
    def _match_selected_question_id(speak: str, search_results: list[dict]) -> str | None:
        normalized = "".join((speak or "").split())
        for item in search_results:
            content = item.get("content", "")
            if not content:
                continue
            candidate = "".join(content.split())
            if normalized == candidate or normalized in candidate or candidate in normalized:
                return item.get("id") or None
        return None

    def _calc_duration(self, session: InterviewSession) -> int:
        if session.started_at:
            end = session.completed_at or datetime.now(timezone.utc)
            s = session.started_at
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            return int((end - s).total_seconds())
        return 0
