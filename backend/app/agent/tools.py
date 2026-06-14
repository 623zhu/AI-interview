"""Interview Agent tools — profile-building paradigm.

Tools:
  evaluate_answer  — 点评 + 更新画像
  retrieve_questions — 检索题目池（多道候选）
  update_profile   — 调整画像
  end_interview    — 结束面试
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage

from app.core.llm import get_llm
from app.agent.rag import search_questions
from app.agent.prompts import REACT_SYSTEM_PROMPT
from app.models.interview_session import InterviewMessage, InterviewSession
from app.models.question import Question
from app.models.question_link import InterviewQuestionLink

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Candidate Profile
# ═══════════════════════════════════════════════════════════════


class CandidateProfile:
    """Mutable profile built during an interview."""

    def __init__(self):
        self.skills: dict[str, dict] = {}
        self.impression: str = ""
        self.current_target: str = ""

    def update_skill(
        self,
        skill_path: str,
        confidence: float | None = None,
        depth: float | None = None,
        comment: str = "",
        gaps: str = "",
    ):
        entry = self.skills.get(skill_path, {
            "confidence": 0.0, "depth": 0.0,
            "comments": [], "gaps": [], "asked": 0,
        })
        if confidence is not None:
            entry["confidence"] = max(0, min(1, confidence))
        if depth is not None:
            entry["depth"] = max(0, min(1, depth))
        if comment:
            entry["comments"].append(comment)
        if gaps:
            entry["gaps"].append(gaps)
        entry["asked"] += 1
        self.skills[skill_path] = entry
        self.current_target = skill_path

    def to_text(self) -> str:
        if not self.skills:
            return "（画像为空）"
        lines = ["| 技能节点 | 置信度 | 深度 | 已问 | 最近点评 |",
                  "|----------|--------|------|------|----------|"]
        for path, s in self.skills.items():
            name = path.split("/")[-1]
            last_comment = (s["comments"][-1][:60] if s["comments"] else "—")
            lines.append(
                f"| {name} | {s['confidence']:.1f} | {s['depth']:.1f} | {s['asked']} | {last_comment} |"
            )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Runtime context
# ═══════════════════════════════════════════════════════════════


class ReactContext:
    def __init__(self, db: AsyncSession, session: InterviewSession, user_msg_id: str = ""):
        self.db = db
        self.session = session
        self.user_msg_id = user_msg_id
        self.profile = CandidateProfile()
        self.search_results: list[dict] = []
        self.selected_question: dict | None = None
        self.evaluation: dict | None = None
        self.is_ended: bool = False
        self.report_id: str | None = None


# ═══════════════════════════════════════════════════════════════
# Agent factory
# ═══════════════════════════════════════════════════════════════


def make_interview_agent(ctx: ReactContext, system_prompt: str):
    """Create a langgraph ReAct agent."""

    # ── evaluate_answer ─────────────────────────────────────

    @tool
    async def evaluate_answer(
        skill_path: str,
        comment: str,
        confidence: float,
        depth: float,
        gaps: str,
        expected_points: str = "",
        reference_answer: str = "",
    ) -> str:
        """点评本轮回答并更新画像。
        点评时必须对照 expected_points（核心考察点）和 reference_answer（参考答案）。
        看候选人答到了哪些点、漏了哪些点。
        Args:
            skill_path: 技能节点路径
            comment: 1-2句点评，必须对照核心点和参考答案，具体指出覆盖了哪些、遗漏了哪些
            confidence: 置信度 0-1（渐进：第1题≤0.4，第2题≤0.7，第3题≤0.9）
            depth: 深度 0-1
            gaps: 知识盲区
            expected_points: 本题的核心考察点（来自检索结果）
            reference_answer: 本题的参考答案（来自检索结果）
        """
        ctx.evaluation = {
            "skill_path": skill_path, "comment": comment,
            "confidence": confidence, "depth": depth, "gaps": gaps,
        }
        ctx.profile.update_skill(
            skill_path=skill_path, confidence=confidence, depth=depth,
            comment=comment, gaps=gaps,
        )
        if ctx.user_msg_id:
            msg = await ctx.db.get(InterviewMessage, ctx.user_msg_id)
            if msg:
                msg.extra_data = {
                    "skill_path": skill_path, "comment": comment,
                    "confidence": confidence, "depth": depth, "gaps": gaps,
                }
                await ctx.db.flush()
        asked = ctx.profile.skills.get(skill_path, {}).get("asked", 0)
        return f"已点评: {skill_path} confidence={confidence:.1f} depth={depth:.1f} (第{asked}题)"

    # ── retrieve_questions ──────────────────────────────────

    @tool
    async def retrieve_questions(
        query: str, difficulty: str = "medium"
    ) -> str:
        """用你想问的问题去题库检索。返回 3-5 道候选，从中选最合适的。

        根据候选人刚才的回答，你想追问什么？把这个想法写成自然语言查询。
        Args:
            query: 用自然语言描述你想问的方向（如"RAG检索的具体实现流程"），不要传技能路径
            difficulty: 期望难度
        """
        print(f"\n{'='*60}")
        print(f"[retrieve_questions] query={query} difficulty={difficulty}")
        try:
            results = await search_questions(
                query=query,
                difficulty=difficulty if difficulty in ("easy", "medium", "hard") else None,
                k=5,
                rerank=True,
                over_fetch=30,
            )
        except Exception:
            print(f"[retrieve_questions] SEARCH FAILED")
            return f"检索失败: {query}，请换一个 query 重试。"

        used = await ctx.db.execute(
            select(InterviewQuestionLink.question_id).where(
                InterviewQuestionLink.interview_id == ctx.session.id
            )
        )
        used_ids = {r[0] for r in used}

        # Batch-load questions in one query
        mids = []
        for r in results:
            mid = r.metadata.get("mysql_id", "") if isinstance(r.metadata, dict) else ""
            if mid and mid not in used_ids:
                mids.append(mid)

        questions_map: dict[str, Question] = {}
        if mids:
            q_result = await ctx.db.execute(
                select(Question).where(Question.id.in_(mids))
            )
            for q in q_result.scalars().all():
                questions_map[q.id] = q

        ctx.search_results.clear()
        for r in results:
            mid = r.metadata.get("mysql_id", "") if isinstance(r.metadata, dict) else ""
            if mid and mid in used_ids:
                continue
            q = questions_map.get(mid)
            qc = q.content if q else ""
            ep = q.expected_points or "" if q else ""
            ra = q.reference_answer or "" if q else ""
            ctx.search_results.append({
                "id": mid,
                "content": qc or (r.metadata.get("content", "") if isinstance(r.metadata, dict) else ""),
                "difficulty": r.metadata.get("difficulty", "medium") if isinstance(r.metadata, dict) else "medium",
                "expected_points": ep,
                "reference_answer": ra,
            })

        print(f"[retrieve_questions] Found {len(ctx.search_results)} results (after filtering used):")
        if not ctx.search_results:
            print(f"[retrieve_questions] EMPTY — asking agent to retry with another query")
            return f"题库中无 '{query}' 相关题目（或都已用过）。请换一个问法重试。"

        lines = [f"候选题目池（{len(ctx.search_results)} 道），请选一道："]
        for i, item in enumerate(ctx.search_results):
            lines.append(f"[{i}] ({item['difficulty']}) 题目: {item['content']}")
            print(f"  [{i}] ({item['difficulty']}) {item['content'][:100]}")
            if item.get("expected_points"):
                lines.append(f"    核心点: {item['expected_points']}")
            if item.get("reference_answer"):
                lines.append(f"    参考答案: {item['reference_answer']}")
        print(f"{'='*60}\n")
        return "\n".join(lines)

    # ── update_profile ──────────────────────────────────────

    @tool
    async def update_profile(
        skill_path: str,
        confidence: float,
        depth: float,
        impression: str = "",
    ) -> str:
        """直接调整画像置信度/深度（不附带点评）。
        Args:
            skill_path: 技能节点路径
            confidence: 新置信度 0-1
            depth: 新深度 0-1
            impression: 对该技能的整体印象
        """
        ctx.profile.update_skill(
            skill_path=skill_path, confidence=confidence, depth=depth, comment=impression,
        )
        if impression:
            ctx.profile.impression = impression
        return f"画像更新: {skill_path} confidence={confidence:.1f} depth={depth:.1f}"

    # ── end_interview ───────────────────────────────────────

    @tool
    async def end_interview(summary: str) -> str:
        """结束面试。画像覆盖度达标时调用。
        Args:
            summary: 候选人能力简要总结
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ctx.session.status = "completed"
        ctx.session.completed_at = now
        if ctx.session.started_at:
            s = ctx.session.started_at
            if s.tzinfo is None:
                s = s.replace(tzinfo=timezone.utc)
            ctx.session.duration_seconds = int((now - s).total_seconds())
        await ctx.db.flush()
        ctx.is_ended = True
        ctx.profile.impression = summary
        try:
            from app.agent.score_agent import generate_report as _gen
            report = await _gen(ctx.db, ctx.session.id)
            await ctx.db.commit()
            ctx.report_id = report.id
            return f"面试结束，报告已生成"
        except Exception:
            await ctx.db.commit()
            return "面试结束"

    # ── Build agent ──────────────────────────────────────────

    return create_react_agent(
        model=get_llm(temperature=0.3),
        tools=[evaluate_answer, retrieve_questions, update_profile, end_interview],
        state_modifier=SystemMessage(content=system_prompt),
    )


# ═══════════════════════════════════════════════════════════════
# Prompt builder
# ═══════════════════════════════════════════════════════════════

def build_react_prompt(
    *,
    job_title: str,
    job_category: str,
    resume_summary: str,
    total_q: int,
    answered_count: int,
    asked_topics: str,
    recent_history: str,
    latest_answer: str,
    skill_tree_text: str = "",
    profile_text: str = "",
) -> str:
    return REACT_SYSTEM_PROMPT.format(
        job_title=job_title,
        job_category=job_category,
        resume_summary=resume_summary,
        total_q=total_q,
        answered_count=answered_count,
        asked_topics=asked_topics or "（暂无）",
        recent_history=recent_history or "（面试刚开始）",
        latest_answer=latest_answer or "（面试刚开始，请开场并邀请自我介绍）",
        skill_tree=skill_tree_text or "（无技能树）",
        profile=profile_text or "（画像为空）",
    )
