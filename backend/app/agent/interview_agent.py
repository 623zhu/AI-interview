"""Interview Agent — profile-building via langgraph ReAct.

Python is a shell: build context, create agent, invoke, stream SSE.
The agent drives everything: analysis, skill selection, question retrieval,
scoring, and profile updates. Profile persists in Redis across turns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from app.core.config import settings
from app.core.llm import LLMServiceError
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

INTERNAL_NOTE_RE = re.compile(
    r"[（(][^（）()]*("
    r"我选|选择第?\s*\d+\s*题|第\s*\d+\s*题|微调|措辞|候选池|候选题|"
    r"内部|思考|推理|retrieve_questions|Speak|结合他|结合候选人|来问"
    r")[^（）()]*[）)]",
    re.IGNORECASE,
)

MARKDOWN_FORMAT_REPLACEMENTS = (
    (re.compile(r"\*\*(.*?)\*\*"), r"\1"),
    (re.compile(r"__(.*?)__"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE), ""),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
)

META_PATTERNS = (
    "（等待",
    "好的，刚才",
    "等你回答",
    "已经问出去",
    "请回答",
    "我选第",
    "选择第",
    "微调措辞",
    "候选池",
    "内部对话",
    "系统内部",
    "Speak",
    "retrieve_questions",
)

AGENT_ERROR_MESSAGES = {
    "agent_timeout": "本轮面试处理超时，请稍后重试。",
    "agent_iteration_limit": "智能体本轮思考次数过多，已安全停止。请重新发送回答或稍后重试。",
    "agent_turn_failed": "本轮面试处理失败，请稍后重试。",
}

GENERIC_FALLBACK_QUESTION = "请结合你做过的一个项目，讲讲你遇到的主要技术难点，以及你是怎么解决的？"


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

    @staticmethod
    def _agent_config() -> dict:
        return {"recursion_limit": settings.REACT_AGENT_RECURSION_LIMIT}

    async def _invoke_agent(self, agent, payload: dict) -> dict:
        return await asyncio.wait_for(
            agent.ainvoke(payload, config=self._agent_config()),
            timeout=settings.INTERVIEW_AGENT_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _agent_error_payload(exc: BaseException) -> dict:
        if isinstance(exc, LLMServiceError):
            return exc.to_dict()

        if isinstance(exc, TimeoutError):
            code = "agent_timeout"
        elif isinstance(exc, GraphRecursionError):
            code = "agent_iteration_limit"
        else:
            code = "agent_turn_failed"

        return {
            "code": code,
            "message": AGENT_ERROR_MESSAGES[code],
            "retryable": True,
        }

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
                total_q=(session.config or {}).get("max_turns", 12),
                answered_count=session.current_question,
                asked_topics=self._asked_topics(history),
                recent_history=self._format_history(history),
                latest_answer=user_message[:800] if user_message else "",
                skill_tree_text=self._format_skill_tree(job),
                profile_text=profile.to_text(),
            )

            agent = make_interview_agent(ctx, prompt)
            result = await self._invoke_agent(agent, {
                "messages": [HumanMessage(content=user_message or "（开场）")]
            })

            agent_output = self._parse_agent_output(self._extract_speak(result))
            speak = self._clean_candidate_message(agent_output["candidate_message"])
            internal_note = agent_output.get("internal_note", "")
            # If agent produced meta-commentary instead of a real question
            if not agent_output.get("valid") or self._is_meta_message(speak):
                logger.warning("Agent produced meta-commentary, retrying. speak=%s", speak[:100])
                retry_result = await self._invoke_agent(agent, {
                    "messages": result["messages"] + [
                        HumanMessage(content='你刚才的最终输出不合格。请只输出 JSON：{"action":"ask_next","candidate_message":"直接说给候选人的一句问题","internal_note":"内部选题说明"}。candidate_message 不能包含内部说明、候选池、选择第几题、微调措辞。')
                    ]
                })
                agent_output = self._parse_agent_output(self._extract_speak(retry_result))
                speak = self._clean_candidate_message(agent_output["candidate_message"])
                internal_note = agent_output.get("internal_note", "")
            if not agent_output.get("valid") or self._is_meta_message(speak):
                speak = self._fallback_question(ctx.search_results)
                internal_note = "Used fallback question after invalid structured agent output."
            print(f"[Agent Speak] {speak[:200]}")
            if internal_note:
                logger.info(
                    "Agent internal note session=%s note=%s",
                    session.id,
                    internal_note[:300],
                )

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
                "turn_number": session.current_question,
                "answered_count": max(session.current_question - 1, 0),
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

        except (asyncio.TimeoutError, TimeoutError, GraphRecursionError) as exc:
            logger.warning(
                "Agent turn stopped session=%s error=%s",
                session.id,
                type(exc).__name__,
                exc_info=True,
            )
            yield sse_event("error", self._agent_error_payload(exc))
        except Exception as exc:
            logger.exception("Turn failed session=%s", session.id)
            yield sse_event("error", self._agent_error_payload(exc))

    @staticmethod
    def _extract_speak(result: dict) -> str:
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and msg.type == "ai":
                c = msg.content
                if c and len(c.strip()) > 2:
                    return c.strip()
        return ""

    @staticmethod
    def _parse_agent_output(text: str) -> dict:
        raw = (text or "").strip()
        if not raw:
            return {
                "valid": False,
                "action": "ask_next",
                "candidate_message": "",
                "internal_note": "",
            }

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "valid": False,
                "action": "ask_next",
                "candidate_message": "",
                "internal_note": raw[:300],
            }

        if not isinstance(parsed, dict):
            return {
                "valid": False,
                "action": "ask_next",
                "candidate_message": "",
                "internal_note": raw[:300],
            }

        candidate_message = parsed.get("candidate_message") or parsed.get("message") or ""
        internal_note = parsed.get("internal_note") or parsed.get("reasoning") or ""
        action = parsed.get("action") or "ask_next"
        valid = bool(str(candidate_message).strip())
        return {
            "valid": valid,
            "action": str(action),
            "candidate_message": str(candidate_message),
            "internal_note": str(internal_note),
        }

    @staticmethod
    def _clean_candidate_message(text: str) -> str:
        """Keep only the natural question text that is safe to show candidates."""
        cleaned = (text or "").strip()
        if not cleaned:
            return ""

        cleaned = INTERNAL_NOTE_RE.sub("", cleaned)
        for pattern, replacement in MARKDOWN_FORMAT_REPLACEMENTS:
            cleaned = pattern.sub(replacement, cleaned)

        cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _is_meta_message(text: str) -> bool:
        cleaned = (text or "").strip()
        return len(cleaned) < 10 or any(pattern in cleaned for pattern in META_PATTERNS)

    @staticmethod
    def _fallback_question(search_results: list[dict] | None) -> str:
        for item in search_results or []:
            content = InterviewManager._clean_candidate_message(item.get("content", ""))
            if content and not InterviewManager._is_meta_message(content):
                return content
        return GENERIC_FALLBACK_QUESTION

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
        normalized = "".join(InterviewManager._clean_candidate_message(speak).split())
        for item in search_results:
            content = item.get("content", "")
            if not content:
                continue
            candidate = "".join(InterviewManager._clean_candidate_message(content).split())
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
