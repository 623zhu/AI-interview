"""Independent per-turn evaluation graph.

Nothing produced here is consumed by the live interviewer graph.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.agent.interview_contracts import EvaluationGraphState, TurnEvaluation
from app.agent.prompts import TURN_EVALUATION_PROMPT
from app.core.database import async_session_factory
from app.core.llm import get_llm
from app.models.question import Question

RubricLoader = Callable[[str | None], dict[str, Any] | Awaitable[dict[str, Any]]]
TurnEvaluator = Callable[
    [EvaluationGraphState], TurnEvaluation | Awaitable[TurnEvaluation]
]


def evaluation_thread_id(session_id: str, turn_id: str) -> str:
    """Isolate each turn evaluation from the live interview checkpoint."""
    return f"eval:{session_id}:{turn_id}"


async def default_rubric_loader(question_id: str | None) -> dict[str, Any]:
    """从 MySQL 读取题库题的评分依据；生成式追问没有题库依据时返回空。"""
    if not question_id:
        return {}
    async with async_session_factory() as db:
        question = await db.get(Question, question_id)
        if not question:
            return {}
        return {
            "expected_points": question.expected_points,
            "reference_answer": question.reference_answer,
            "evaluation_criteria": question.evaluation_criteria or {},
        }


async def default_turn_evaluator(state: EvaluationGraphState) -> TurnEvaluation:
    """独立评价单轮回答，输出分数、证据和遗漏点，不生成下一题。"""
    turn = state.get("turn") or {}
    question = turn.get("question") or {}
    turn_id = str(turn.get("turn_id") or "")
    skill_path = str(question.get("skill_path") or "")

    is_opening = question.get("id") == "intro" or question.get("category") in {
        "basic",
        "opening",
    }

    payload = {
        "turn": turn,
        "rubric": state.get("rubric") or {},
        "job_requirements": (state.get("job_snapshot") or {}).get("requirements") or {},
    }
    structured = get_llm(temperature=0.1).with_structured_output(
        TurnEvaluation,
        method="json_mode",
    )
    result = await structured.ainvoke([
        SystemMessage(content=TURN_EVALUATION_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ])
    evaluation = TurnEvaluation.model_validate(result)
    evaluation.turn_id = turn_id
    evaluation.skill_path = skill_path
    if is_opening:
        # 开场回答需要模型给出针对性文字反馈，但不能混入技术能力总分。
        evaluation = TurnEvaluation.model_validate({
            **evaluation.model_dump(mode="json"),
            "scored": False,
            "answer_score": None,
            "correctness": None,
            "completeness": None,
            "depth": None,
            "communication": None,
        })
    return evaluation


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def build_evaluation_graph(
    checkpointer: Any,
    *,
    rubric_loader: RubricLoader | None = None,
    evaluator: TurnEvaluator | None = None,
):
    """构建单轮评价图：先加载评分依据，再调用评价模型。

    每个 turn 使用独立 thread_id；该图的任何输出都不会写回 Interview Graph。
    """
    load_rubric = rubric_loader or default_rubric_loader
    evaluate_turn = evaluator or default_turn_evaluator

    async def prepare(state: EvaluationGraphState) -> dict[str, Any]:
        """按当前问题的 source_question_id 准备参考答案和评分点。"""
        turn = state.get("turn") or {}
        question = turn.get("question") or {}
        rubric = await _resolve(load_rubric(question.get("source_question_id")))
        return {"rubric": dict(rubric or {}), "status": "pending", "error": None}

    async def evaluate(state: EvaluationGraphState) -> dict[str, Any]:
        """执行结构化评价，并把异常转为可供报告补跑识别的 failed 状态。"""
        try:
            result = await _resolve(evaluate_turn(state))
            parsed = TurnEvaluation.model_validate(result)
            return {
                "evaluation": parsed.model_dump(mode="json"),
                "status": "completed",
                "error": None,
            }
        except Exception as exc:
            return {
                "evaluation": None,
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }

    graph = StateGraph(EvaluationGraphState)
    graph.add_node("load_rubric", prepare)
    graph.add_node("evaluate_turn", evaluate)
    graph.add_edge(START, "load_rubric")
    graph.add_edge("load_rubric", "evaluate_turn")
    graph.add_edge("evaluate_turn", END)
    return graph.compile(checkpointer=checkpointer)
