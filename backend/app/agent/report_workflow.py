"""Report graph built from independent per-turn evaluations."""

from __future__ import annotations

import inspect
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agent.interview_contracts import ReportGraphState, ReportNarrative
from app.agent.interview_policy import build_skill_catalog
from app.agent.prompts import REPORT_NARRATIVE_PROMPT
from app.core.database import async_session_factory
from app.core.llm import get_llm
from app.models.interview_session import InterviewSession
from app.models.score_report import ScoreReport

EvaluationCollector = Callable[
    [dict[str, Any], ReportGraphState],
    dict[str, Any] | None | Awaitable[dict[str, Any] | None],
]
NarrativeWriter = Callable[
    [ReportGraphState], ReportNarrative | Awaitable[ReportNarrative]
]
ReportPersister = Callable[
    [ReportGraphState], str | Awaitable[str]
]


def report_thread_id(session_id: str) -> str:
    """Return the checkpoint namespace for one session's report graph."""
    return f"report:{session_id}"


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def aggregate_evaluations(
    evaluations: list[dict[str, Any]], job_snapshot: dict[str, Any]
) -> dict[str, Any]:
    """确定性聚合分数：先算每项技能平均，再按岗位技能权重汇总。

    不能直接按每一轮加权，否则某个技能被多次追问会无意中放大其权重。
    该函数不调用 LLM，确保相同评价输入始终得到相同分数。
    """
    scored = [
        item for item in evaluations
        if item.get("scored") and isinstance(item.get("answer_score"), (int, float))
    ]
    catalog = build_skill_catalog(job_snapshot)
    weights = {item["path"]: float(item.get("weight") or 0) for item in catalog}

    # 第一步：把同一技能下的多轮评价归为一组。
    by_skill: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in scored:
        by_skill[str(item.get("skill_path") or "其他")].append(item)

    # 第二步：计算技能平均分，并取岗位技能树中配置的权重。
    skill_weights = {
        skill: max(weights.get(skill, 0), 0.01) for skill in by_skill
    }
    raw_skill_scores = {
        skill: sum(float(item["answer_score"]) for item in items) / len(items)
        for skill, items in by_skill.items()
    }
    skill_scores = {
        skill: round(value) for skill, value in raw_skill_scores.items()
    }
    total_weight = sum(skill_weights.values())
    overall = (
        round(
            sum(raw_skill_scores[skill] * skill_weights[skill] for skill in by_skill)
            / total_weight
        )
        if total_weight
        else 0
    )
    # 第三步：正确性、完整性等维度也遵循相同的两层聚合规则。
    dimensions: dict[str, int | None] = {}
    for key in ("correctness", "completeness", "depth", "communication"):
        skill_dimension_scores = {}
        for skill, items in by_skill.items():
            available = [
                float(item[key])
                for item in items
                if isinstance(item.get(key), (int, float))
            ]
            if available:
                skill_dimension_scores[skill] = sum(available) / len(available)
        denominator = sum(skill_weights[skill] for skill in skill_dimension_scores)
        dimensions[key] = (
            round(
                sum(
                    value * skill_weights[skill]
                    for skill, value in skill_dimension_scores.items()
                )
                / denominator
            )
            if denominator
            else None
        )

    return {
        "overall_score": overall,
        "dimension_scores": dimensions,
        "skill_scores": skill_scores,
        "scored_turn_count": len(scored),
        "total_turn_count": len(evaluations),
        "formula": "weighted mean of per-skill averages using job skill weights",
    }


def fallback_narrative(state: ReportGraphState) -> ReportNarrative:
    """Build a deterministic narrative when the report LLM is unavailable."""
    evaluations = state.get("evaluations") or []
    scored = [item for item in evaluations if item.get("scored")]
    ordered = sorted(scored, key=lambda item: item.get("answer_score") or 0, reverse=True)
    strengths = [
        f"{item.get('skill_path') or '相关能力'}：{item.get('comment') or '回答表现较完整'}"
        for item in ordered[:2]
        if (item.get("answer_score") or 0) >= 70
    ]
    weaknesses = [
        f"{item.get('skill_path') or '相关能力'}：{item.get('comment') or '回答仍有缺口'}"
        for item in reversed(ordered[-2:])
        if (item.get("answer_score") or 100) < 70
    ]
    improvements = []
    for item in ordered:
        missed = item.get("missed_points") or []
        if missed:
            improvements.append(f"补充掌握：{'、'.join(str(point) for point in missed[:3])}")
        if len(improvements) >= 3:
            break
    overall = (state.get("aggregate") or {}).get("overall_score", 0)
    return ReportNarrative(
        summary=f"本次共完成 {len(evaluations)} 轮问答，计分轮次 {len(scored)}，综合得分 {overall}。",
        strengths=strengths,
        weaknesses=weaknesses,
        improvements=improvements,
    )


async def default_narrative_writer(state: ReportGraphState) -> ReportNarrative:
    """Generate prose from evaluations without exposing raw interview state."""
    allowed_fields = {
        "turn_id",
        "skill_path",
        "scored",
        "answer_score",
        "correctness",
        "completeness",
        "depth",
        "communication",
        "covered_points",
        "missed_points",
        "evidence",
        "comment",
        "score_confidence",
    }
    payload = {
        "aggregate": state.get("aggregate") or {},
        "evaluations": [
            {key: value for key, value in item.items() if key in allowed_fields}
            for item in (state.get("evaluations") or [])
        ],
    }
    structured = get_llm(temperature=0.2).with_structured_output(
        ReportNarrative,
        method="json_mode",
    )
    result = await structured.ainvoke([
        SystemMessage(content=REPORT_NARRATIVE_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ])
    return ReportNarrative.model_validate(result)


def render_report_markdown(state: ReportGraphState) -> str:
    """Render the persisted human-readable report from structured graph state."""
    aggregate = state.get("aggregate") or {}
    narrative = ReportNarrative.model_validate(state.get("narrative") or {})
    lines = [
        "# 面试评估报告",
        "",
        f"**综合得分：{aggregate.get('overall_score', 0)} / 100**",
        "",
        narrative.summary,
        "",
        "## 维度得分",
        "",
    ]
    for name, score in (aggregate.get("dimension_scores") or {}).items():
        lines.append(f"- {name}: {score if score is not None else '未评分'}")
    for title, items in (
        ("优势", narrative.strengths),
        ("待提升", narrative.weaknesses),
        ("改进建议", narrative.improvements),
    ):
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {item}" for item in items)

    lines.extend(["", "## 逐题评价", ""])
    turns = {turn.get("turn_id"): turn for turn in state.get("turns") or []}
    for index, evaluation in enumerate(state.get("evaluations") or [], 1):
        turn = turns.get(evaluation.get("turn_id"), {})
        question = (turn.get("question") or {}).get("content", "")
        lines.extend([
            f"### 第 {index} 轮",
            "",
            f"**问：** {question}",
            "",
            f"**答：** {str(turn.get('answer') or '')[:1000]}",
            "",
            f"**评价：** {evaluation.get('comment') or '无'}",
            "",
        ])
    return "\n".join(lines)


async def default_report_persister(state: ReportGraphState) -> str:
    """Upsert one report per session and synchronize the session report status."""
    session_id = str(state["session_id"])
    aggregate = state.get("aggregate") or {}
    narrative = ReportNarrative.model_validate(state.get("narrative") or {})
    async with async_session_factory() as db:
        session = await db.get(InterviewSession, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        result = await db.execute(
            select(ScoreReport).where(ScoreReport.session_id == session_id)
        )
        report = result.scalar_one_or_none()
        values = {
            "overall_score": int(aggregate.get("overall_score") or 0),
            "dimension_scores": aggregate.get("dimension_scores") or {},
            "question_evaluations": state.get("evaluations") or [],
            "strengths": narrative.strengths,
            "weaknesses": narrative.weaknesses,
            "improvements": narrative.improvements,
            "full_report": render_report_markdown(state),
            "full_data": {
                "aggregate": aggregate,
                "narrative": narrative.model_dump(mode="json"),
                "turns": state.get("turns") or [],
            },
            "generated_at": datetime.now(timezone.utc),
        }
        if report is None:
            report = ScoreReport(
                session_id=session_id,
                user_id=str(state["user_id"]),
                **values,
            )
            db.add(report)
        else:
            for key, value in values.items():
                setattr(report, key, value)
        session.status = "completed"
        session.report_status = "completed"
        session.report_error = None
        await db.flush()
        report_id = report.id
        await db.commit()
        return report_id


def build_report_graph(
    checkpointer: Any,
    *,
    evaluation_collector: EvaluationCollector,
    narrative_writer: NarrativeWriter | None = None,
    persister: ReportPersister | None = None,
):
    """Compile collection, aggregation, narration, and persistence into one graph."""
    write_narrative = narrative_writer or default_narrative_writer
    persist = persister or default_report_persister

    async def collect(state: ReportGraphState) -> dict[str, Any]:
        evaluations: list[dict[str, Any]] = []
        for turn in state.get("turns") or []:
            if turn.get("status") != "answered":
                continue
            evaluation = await _resolve(evaluation_collector(turn, state))
            question = turn.get("question") or {}
            if evaluation:
                evaluation_data = dict(evaluation)
            else:
                evaluation_data = {
                    "turn_id": str(turn.get("turn_id") or "unknown"),
                    "skill_path": str(question.get("skill_path") or ""),
                    "scored": False,
                    "answer_score": None,
                    "correctness": None,
                    "completeness": None,
                    "depth": None,
                    "communication": None,
                    "covered_points": [],
                    "missed_points": [],
                    "evidence": [],
                    "comment": "本轮评价模型调用失败，未计入技术总分。",
                    "score_confidence": 0.0,
                    "evaluation_status": "unavailable",
                }
            evaluations.append({
                **evaluation_data,
                "turn_number": turn.get("turn_number"),
                "question": question.get("content", ""),
                "answer": turn.get("answer", ""),
                "action": question.get("action"),
                "question_origin": question.get("origin"),
            })
        return {"evaluations": evaluations, "status": "generating", "error": None}

    def route_collection(state: ReportGraphState) -> str:
        return "stop" if state.get("status") == "failed" else "aggregate"

    async def aggregate(state: ReportGraphState) -> dict[str, Any]:
        return {
            "aggregate": aggregate_evaluations(
                state.get("evaluations") or [], state.get("job_snapshot") or {}
            )
        }

    async def narrate(state: ReportGraphState) -> dict[str, Any]:
        try:
            narrative = await _resolve(write_narrative(state))
            parsed = ReportNarrative.model_validate(narrative)
        except Exception:
            parsed = fallback_narrative(state)
        return {"narrative": parsed.model_dump(mode="json")}

    async def save(state: ReportGraphState) -> dict[str, Any]:
        try:
            report_id = await _resolve(persist(state))
            return {
                "report_id": str(report_id),
                "status": "completed",
                "error": None,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }

    graph = StateGraph(ReportGraphState)
    graph.add_node("collect_evaluations", collect)
    graph.add_node("aggregate_scores", aggregate)
    graph.add_node("write_narrative", narrate)
    graph.add_node("persist_report", save)
    graph.add_edge(START, "collect_evaluations")
    graph.add_conditional_edges(
        "collect_evaluations",
        route_collection,
        {"stop": END, "aggregate": "aggregate_scores"},
    )
    graph.add_edge("aggregate_scores", "write_narrative")
    graph.add_edge("write_narrative", "persist_report")
    graph.add_edge("persist_report", END)
    return graph.compile(checkpointer=checkpointer)
