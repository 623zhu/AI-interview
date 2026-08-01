"""Explicit LangGraph state machine for the live interview conversation."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agent.interview_contracts import (
    ComposedInterviewQuestion,
    InterviewAction,
    InterviewGraphState,
    InterviewerDecision,
    QuestionCandidate,
)
from app.agent.interview_policy import (
    build_skill_frontier,
    deadline_for,
    hard_stop_reason,
    initialize_coverage,
    iso_utc,
    model_failure_fallback_decision,
    normalize_interview_config,
    policy_redirect_decision,
    update_coverage_for_turn,
    utc_now,
    validate_interviewer_decision,
)
from app.agent.prompts import (
    INTERVIEWER_DECISION_PROMPT,
    OPENING_QUESTION_PROMPT,
    SWITCH_QUESTION_COMPOSER_PROMPT,
)
from app.agent.question_pool import retrieve_question_pool
from app.core.llm import get_llm

DecisionMaker = Callable[
    [InterviewGraphState], InterviewerDecision | Awaitable[InterviewerDecision]
]
QuestionPoolLoader = Callable[
    [list[dict[str, Any]], dict[str, Any], list[str]],
    list[dict[str, Any]] | Awaitable[list[dict[str, Any]]],
]
SwitchQuestionComposer = Callable[
    [InterviewGraphState, InterviewerDecision, QuestionCandidate | None],
    ComposedInterviewQuestion | Awaitable[ComposedInterviewQuestion],
]
OpeningQuestionComposer = Callable[
    [InterviewGraphState],
    ComposedInterviewQuestion | Awaitable[ComposedInterviewQuestion],
]

_INTERNAL_QUESTION_FIELDS = {
    "source_question_content",
    "source_question_difficulty",
    "source_question_category",
}


def make_initial_interview_state(
    *,
    session_id: str,
    user_id: str,
    resume_id: str,
    job_id: str,
    config: dict[str, Any] | None,
    job_snapshot: dict[str, Any],
    resume_summary: str,
    now: datetime | None = None,
) -> InterviewGraphState:
    """Create the complete state required to start a new interview graph."""
    started = now or utc_now()
    normalized_config = normalize_interview_config(config)
    return {
        "session_id": session_id,
        "user_id": user_id,
        "resume_id": resume_id,
        "job_id": job_id,
        "status": "in_progress",
        "config": normalized_config,
        "job_snapshot": job_snapshot,
        "resume_summary": resume_summary,
        "started_at": iso_utc(started),
        "deadline_at": iso_utc(deadline_for(started, normalized_config)),
        "completed_at": None,
        "current_question": None,
        "turns": [],
        "coverage": initialize_coverage(job_snapshot),
        "used_question_ids": [],
        "processed_event_ids": [],
        "pending_evaluation_ids": [],
        "incoming_event": None,
        "skill_frontier": [],
        "question_pool": [],
        "interviewer_decision": None,
        "hard_stop_reason": None,
        "report_status": "pending",
        "background_jobs": [],
        "output": None,
        "error": None,
    }


def public_interview_state(state: dict[str, Any]) -> dict[str, Any]:
    """Project internal graph state into the stable API progress contract."""
    turns = state.get("turns") or []
    answered = sum(1 for turn in turns if turn.get("status") == "answered")
    skipped = sum(1 for turn in turns if turn.get("status") == "skipped")
    question = state.get("current_question") or {}
    return {
        "id": state.get("session_id"),
        "status": state.get("status", "created"),
        "started_at": state.get("started_at"),
        "completed_at": state.get("completed_at"),
        "current_question": question.get("turn_number", len(turns)),
        "current_question_id": question.get("id"),
        "answered_count": answered,
        "questions_skipped": skipped,
        "max_turns": (state.get("config") or {}).get("max_turns"),
        "report_status": state.get("report_status", "pending"),
        "hard_stop_reason": state.get("hard_stop_reason"),
    }


def public_interview_question(question: dict[str, Any] | None) -> dict[str, Any]:
    """Remove source-question snapshots from candidate-facing responses."""
    return {
        key: value
        for key, value in (question or {}).items()
        if key not in _INTERNAL_QUESTION_FIELDS
    }


def conversation_messages(state: dict[str, Any]) -> list[dict[str, str]]:
    """Rebuild the visible transcript while excluding internal graph events."""
    messages: list[dict[str, str]] = []
    for turn in state.get("turns") or []:
        question = turn.get("question") or {}
        content = str(question.get("content") or "")
        if content:
            messages.append({"role": "ai", "content": content, "message_type": "question"})
        if turn.get("status") == "answered":
            messages.append({
                "role": "user",
                "content": str(turn.get("answer") or ""),
                "message_type": "answer",
            })
    current = state.get("current_question") or {}
    if state.get("status") == "in_progress" and current.get("content"):
        messages.append({
            "role": "ai",
            "content": str(current["content"]),
            "message_type": "question",
        })
    return messages


async def default_decision_maker(state: InterviewGraphState) -> InterviewerDecision:
    """让 LLM 根据原始问答和技能前沿选择下一动作。

    payload 故意不包含逐题评价或分数，避免评价结论影响后续面试官。
    Pydantic structured output 保证结果能解析为 InterviewerDecision。
    """
    turns = state.get("turns") or []
    payload = {
        "job": {
            "title": (state.get("job_snapshot") or {}).get("title"),
            "category": (state.get("job_snapshot") or {}).get("category"),
            "level": (state.get("job_snapshot") or {}).get("level"),
            "requirements": (state.get("job_snapshot") or {}).get("requirements"),
        },
        "resume_summary": state.get("resume_summary", ""),
        "recent_raw_turns": turns[-5:],
        "current_question": state.get("current_question"),
        "skill_frontier": state.get("skill_frontier") or [],
        "follow_up_limits": {
            path: item.get("follow_ups", 0)
            for path, item in (state.get("coverage") or {}).items()
        },
        "finish_allowed": bool(state.get("hard_stop_reason")),
    }
    structured = get_llm(temperature=0.35).with_structured_output(
        InterviewerDecision,
        method="json_mode",
    )
    result = await structured.ainvoke([
        SystemMessage(content=INTERVIEWER_DECISION_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ])
    return InterviewerDecision.model_validate(result)


async def default_opening_question_composer(
    state: InterviewGraphState,
) -> ComposedInterviewQuestion:
    """Generate a resume- and job-aware self-introduction question."""
    payload = {
        "job": {
            "title": (state.get("job_snapshot") or {}).get("title"),
            "category": (state.get("job_snapshot") or {}).get("category"),
            "level": (state.get("job_snapshot") or {}).get("level"),
            "description": (state.get("job_snapshot") or {}).get("description"),
            "requirements": (state.get("job_snapshot") or {}).get("requirements"),
        },
        "resume_summary": state.get("resume_summary", ""),
    }
    structured = get_llm(temperature=0.35).with_structured_output(
        ComposedInterviewQuestion,
        method="json_mode",
    )
    result = await structured.ainvoke([
        SystemMessage(content=OPENING_QUESTION_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ])
    return ComposedInterviewQuestion.model_validate(result)


async def default_switch_question_composer(
    state: InterviewGraphState,
    decision: InterviewerDecision,
    candidate: QuestionCandidate | None,
) -> ComposedInterviewQuestion:
    """Adapt a retrieved question or compose a new one for a valid SWITCH."""
    turns = state.get("turns") or []
    payload = {
        "target_skill_path": decision.target_skill_path,
        "job": {
            "title": (state.get("job_snapshot") or {}).get("title"),
            "category": (state.get("job_snapshot") or {}).get("category"),
            "level": (state.get("job_snapshot") or {}).get("level"),
            "requirements": (state.get("job_snapshot") or {}).get("requirements"),
        },
        "resume_summary": state.get("resume_summary", ""),
        "recent_raw_turns": turns[-5:],
        "current_question": state.get("current_question"),
        "source_question": (
            {
                "content": candidate.content,
                "difficulty": candidate.difficulty,
                "category": candidate.category,
                "expected_points": candidate.expected_points,
                "evaluation_criteria": candidate.evaluation_criteria,
            }
            if candidate is not None
            else None
        ),
    }
    structured = get_llm(temperature=0.45).with_structured_output(
        ComposedInterviewQuestion,
        method="json_mode",
    )
    result = await structured.ainvoke([
        SystemMessage(content=SWITCH_QUESTION_COMPOSER_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ])
    return ComposedInterviewQuestion.model_validate(result)


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def build_interview_graph(
    checkpointer: Any,
    *,
    decision_maker: DecisionMaker | None = None,
    question_pool_loader: QuestionPoolLoader | None = None,
    switch_question_composer: SwitchQuestionComposer | None = None,
    opening_question_composer: OpeningQuestionComposer | None = None,
):
    """构建一轮一轮暂停/恢复的实时面试状态图。

    下方内部函数都是图节点：它们接收当前完整 state，只返回需要修改的
    字段（状态增量）。真正的节点执行顺序在函数末尾通过 edge 定义。
    可注入 decision_maker/question_pool_loader/switch_question_composer/
    opening_question_composer，
    以便测试时替换 LLM 和 RAG。
    """
    choose = decision_maker or default_decision_maker
    load_pool = question_pool_loader or retrieve_question_pool
    compose_switch_question = (
        switch_question_composer or default_switch_question_composer
    )
    compose_opening_question = (
        opening_question_composer or default_opening_question_composer
    )

    async def initialize(state: InterviewGraphState) -> dict[str, Any]:
        """校验初始状态，并准备第一次返回给 API 的公开进度。"""
        if state.get("status") != "in_progress":
            raise ValueError("Interview graph requires an in-progress initial state")
        return {"output": public_interview_state(state), "error": None}

    async def compose_opening(state: InterviewGraphState) -> dict[str, Any]:
        """Generate the first question inside the graph; preserve resumed legacy state."""
        if state.get("current_question"):
            return {"output": public_interview_state(state)}

        error: str | None = None
        origin = "generated"
        try:
            composed = ComposedInterviewQuestion.model_validate(
                await _resolve(compose_opening_question(state))
            )
            question_text = composed.question
            probe_goal = composed.probe_goal
        except Exception as exc:
            fallback = model_failure_fallback_decision(state, opening=True)
            question_text = fallback.question
            probe_goal = fallback.probe_goal
            origin = "fallback"
            error = f"model_failure_fallback:opening_question:{type(exc).__name__}"

        question = {
            "id": "intro",
            "content": question_text,
            "category": "opening",
            "origin": origin,
            "action": InterviewAction.BRIDGE.value,
            "skill_path": "",
            "source_question_id": None,
            "probe_goal": probe_goal,
            "anchor": "",
            "turn_number": 1,
            "asked_at": iso_utc(utc_now()),
        }
        next_state = {**state, "current_question": question}
        return {
            "current_question": question,
            "output": public_interview_state(next_state),
            "error": error,
        }

    async def wait_for_candidate(state: InterviewGraphState) -> dict[str, Any]:
        """在当前问题处暂停图；恢复后把候选人事件写入 incoming_event。"""
        event = interrupt({
            "kind": "candidate_input",
            "question": state.get("current_question"),
            "progress": public_interview_state(state),
        })
        if not isinstance(event, dict):
            raise ValueError("Interview resume payload must be an event object")
        return {"incoming_event": event, "error": None}

    def route_event(state: InterviewGraphState) -> str:
        """校验事件幂等性，并决定记录回答、结束还是忽略旧事件。"""
        event = state.get("incoming_event") or {}
        event_type = str(event.get("type") or "")
        event_id = str(event.get("event_id") or "")
        expected_question_id = str(event.get("expected_question_id") or "")
        current_question_id = str((state.get("current_question") or {}).get("id") or "")
        # 浏览器重试可能重复提交同一 event_id，只允许首次事件推进状态。
        if event_id and event_id in (state.get("processed_event_ids") or []):
            return "ignore"
        # 页面若仍在回答旧问题，也不能把内容记到服务端已经切换的新问题上。
        if expected_question_id and expected_question_id != current_question_id:
            return "ignore"
        if event_type == "end":
            return "finish"
        if event_type in {"answer", "skip"}:
            return "record"
        raise ValueError(f"Unsupported interview event: {event_type or 'missing'}")

    async def ignore_event(state: InterviewGraphState) -> dict[str, Any]:
        """忽略重复/过期事件，保持当前问题不变并重新等待候选人。"""
        return {
            "incoming_event": None,
            "background_jobs": [],
            "output": public_interview_state(state),
            "error": "duplicate_or_stale_event",
        }

    async def record_turn(state: InterviewGraphState) -> dict[str, Any]:
        """把当前问题和本次回答固化为一个 turn，并在答后更新覆盖率。

        这里只登记待评价 turn_id，不执行评价；下一题返回后才启动评价任务。
        """
        event = state.get("incoming_event") or {}
        event_type = str(event.get("type"))
        answer = str(event.get("message") or "").strip()
        if event_type == "answer" and not answer:
            raise ValueError("Answer cannot be empty")

        # 复制列表后再追加，避免直接修改 checkpointer 交给节点的旧状态对象。
        turns = list(state.get("turns") or [])
        number = len(turns) + 1
        turn_id = f"{state['session_id']}:{number}"
        turn = {
            "turn_id": turn_id,
            "turn_number": number,
            "question": dict(state.get("current_question") or {}),
            "answer": answer if event_type == "answer" else "",
            "status": "answered" if event_type == "answer" else "skipped",
            "answered_at": iso_utc(utc_now()),
        }
        turns.append(turn)
        pending = list(state.get("pending_evaluation_ids") or [])
        processed = list(state.get("processed_event_ids") or [])
        event_id = str(event.get("event_id") or "")
        if event_id:
            processed.append(event_id)
        jobs: list[dict[str, Any]] = []
        if event_type == "answer":
            pending.append(turn_id)
            jobs.append({"type": "evaluate_turn", "turn_id": turn_id})
        question = turn["question"]
        action = InterviewAction(
            str(question.get("action") or InterviewAction.SWITCH.value)
        )
        # 覆盖率在候选人处理完问题后更新，展示新问题时不会提前记为已覆盖。
        coverage = update_coverage_for_turn(
            state.get("coverage") or {},
            skill_path=str(question.get("skill_path") or ""),
            action=action,
            turn_number=number,
            answered=event_type == "answer",
        )
        return {
            "turns": turns,
            "coverage": coverage,
            "pending_evaluation_ids": pending,
            "processed_event_ids": processed[-100:],
            "background_jobs": jobs,
            "incoming_event": None,
        }

    async def check_limits(state: InterviewGraphState) -> dict[str, Any]:
        """检查最大回答数和截止时间等硬停止条件。"""
        reason = hard_stop_reason(state)
        return {"hard_stop_reason": reason}

    def route_limits(state: InterviewGraphState) -> str:
        return "finish" if state.get("hard_stop_reason") else "continue"

    async def prepare_frontier(state: InterviewGraphState) -> dict[str, Any]:
        """从技能树覆盖状态中计算本轮允许选择的少量目标技能。"""
        current = state.get("current_question") or {}
        frontier = build_skill_frontier(
            state.get("coverage") or {},
            current_skill=str(current.get("skill_path") or ""),
        )
        return {"skill_frontier": frontier, "question_pool": []}

    async def retrieve_pool(state: InterviewGraphState) -> dict[str, Any]:
        """仅为 SWITCH 的目标技能检索题库候选，其他动作不会经过此节点。"""
        decision = InterviewerDecision.model_validate(state.get("interviewer_decision"))
        target = (state.get("coverage") or {}).get(decision.target_skill_path)
        target_frontier = [dict(target)] if target else [{
            "path": decision.target_skill_path,
            "name": decision.target_skill_path.rsplit("/", 1)[-1],
            "difficulty": "medium",
        }]
        pool = await _resolve(load_pool(
            target_frontier,
            state.get("job_snapshot") or {},
            state.get("used_question_ids") or [],
        ))
        return {"question_pool": list(pool or [])}

    async def decide(state: InterviewGraphState) -> dict[str, Any]:
        """Call the retried decision LLM; only terminal model failure uses fallback."""
        try:
            decision = await _resolve(choose(state))
            parsed = InterviewerDecision.model_validate(decision)
            return {
                "interviewer_decision": parsed.model_dump(mode="json"),
                "error": None,
            }
        except Exception as exc:
            fallback = model_failure_fallback_decision(state)
            return {
                "interviewer_decision": fallback.model_dump(mode="json"),
                "error": f"model_failure_fallback:decision:{type(exc).__name__}",
            }

    async def validate_decision(state: InterviewGraphState) -> dict[str, Any]:
        """用确定性规则约束 LLM 动作，防止越过技能边界或追问上限。"""
        proposed = InterviewerDecision.model_validate(state.get("interviewer_decision"))
        if proposed.action == InterviewAction.SWITCH:
            frontier = state.get("skill_frontier") or []
            frontier_paths = {
                str(item.get("path") or "") for item in frontier if item.get("path")
            }
            target = proposed.target_skill_path
            if target not in frontier_paths:
                target = str(frontier[0].get("path") or "") if frontier else ""
            if target:
                proposed.target_skill_path = target
                proposed.source_question_id = None
                proposed.question = ""
                return {
                    "interviewer_decision": proposed.model_dump(mode="json"),
                    "error": state.get("error"),
                }
        validated, reason = validate_interviewer_decision(proposed, state=state)
        if validated is None:
            validated = policy_redirect_decision(state, reason=reason or "invalid_action")
        return {
            "interviewer_decision": validated.model_dump(mode="json"),
            "error": f"decision_policy_redirect:{reason}" if reason else state.get("error"),
        }

    def route_decision(state: InterviewGraphState) -> str:
        """FINISH 去结束，SWITCH 去题库，其余生成式动作直接出题。"""
        decision = state.get("interviewer_decision") or {}
        action = decision.get("action")
        if action == InterviewAction.FINISH.value:
            return "finish"
        if action == InterviewAction.SWITCH.value:
            return "retrieve"
        return "present"

    async def select_switch_question(state: InterviewGraphState) -> dict[str, Any]:
        """Adapt the top retrieved question, or compose one when the pool is empty."""
        planned = InterviewerDecision.model_validate(state.get("interviewer_decision"))
        pool = state.get("question_pool") or []
        candidate = QuestionCandidate.model_validate(pool[0]) if pool else None

        target = (state.get("coverage") or {}).get(planned.target_skill_path)
        generation_state = {
            **state,
            "skill_frontier": [target] if target else state.get("skill_frontier") or [],
        }
        try:
            composed = ComposedInterviewQuestion.model_validate(
                await _resolve(compose_switch_question(state, planned, candidate))
            )
            selected = planned.model_copy(update={
                "source_question_id": candidate.id if candidate else None,
                "anchor": composed.anchor,
                "probe_goal": composed.probe_goal,
                "question": composed.question,
                "reason": (
                    "adapted_knowledge_base_question"
                    if candidate
                    else "generated_switch_question"
                ),
            })
            return {
                "interviewer_decision": selected.model_dump(mode="json"),
                "error": state.get("error"),
            }
        except Exception as exc:
            fallback = model_failure_fallback_decision(
                generation_state,
                planned=planned,
                candidate=candidate,
            )
            phase = "question_adaptation" if candidate else "question_generation"
            return {
                "interviewer_decision": fallback.model_dump(mode="json"),
                "error": f"model_failure_fallback:{phase}:{type(exc).__name__}",
            }

    async def present_question(state: InterviewGraphState) -> dict[str, Any]:
        """把已校验决策转换成统一 current_question，供 API 和下一轮使用。"""
        decision = InterviewerDecision.model_validate(state.get("interviewer_decision"))
        content = decision.question
        source_candidate = next(
            (
                QuestionCandidate.model_validate(item)
                for item in (state.get("question_pool") or [])
                if str(item.get("id") or "") == str(decision.source_question_id or "")
            ),
            None,
        )
        turn_number = len(state.get("turns") or []) + 1
        question = {
            "id": f"q{turn_number}",
            "content": content,
            "category": "follow_up" if decision.action in {
                InterviewAction.CLARIFY,
                InterviewAction.PROBE,
            } else "technical",
            "origin": "knowledge_base" if decision.source_question_id else "generated",
            "action": decision.action.value,
            "skill_path": decision.target_skill_path,
            "source_question_id": decision.source_question_id,
            "source_question_content": (
                source_candidate.content if source_candidate is not None else None
            ),
            "source_question_difficulty": (
                source_candidate.difficulty if source_candidate is not None else None
            ),
            "source_question_category": (
                source_candidate.category if source_candidate is not None else None
            ),
            "probe_goal": decision.probe_goal,
            "anchor": decision.anchor,
            "turn_number": turn_number,
            "asked_at": iso_utc(utc_now()),
        }
        used = list(state.get("used_question_ids") or [])
        if decision.source_question_id and decision.source_question_id not in used:
            used.append(decision.source_question_id)
        # 此时问题还没被回答，所以这里只更新 current_question 和已用题目。
        next_state = {**state, "current_question": question}
        return {
            "current_question": question,
            "used_question_ids": used,
            "output": public_interview_state(next_state),
        }

    async def finalize(state: InterviewGraphState) -> dict[str, Any]:
        """关闭实时面试状态，并登记最终报告生成任务。"""
        completed_at = iso_utc(utc_now())
        reason = state.get("hard_stop_reason")
        event = state.get("incoming_event") or {}
        if not reason and event.get("type") == "end":
            reason = "candidate_ended"
        if not reason:
            reason = "coverage_complete"
        next_state = {
            **state,
            "status": "completed",
            "completed_at": completed_at,
            "current_question": None,
            "hard_stop_reason": reason,
            "report_status": "pending",
        }
        jobs = list(state.get("background_jobs") or [])
        jobs.append({"type": "generate_report", "session_id": state["session_id"]})
        next_state["background_jobs"] = jobs
        return {
            "status": "completed",
            "completed_at": completed_at,
            "current_question": None,
            "hard_stop_reason": reason,
            "report_status": "pending",
            "background_jobs": jobs,
            "incoming_event": None,
            "output": public_interview_state(next_state),
        }

    # 先注册节点，再在下面用边描述执行顺序；条件边根据 route_* 返回值分支。
    graph = StateGraph(InterviewGraphState)
    graph.add_node("initialize", initialize)
    graph.add_node("compose_opening_question", compose_opening)
    graph.add_node("wait_for_candidate", wait_for_candidate)
    graph.add_node("record_turn", record_turn)
    graph.add_node("ignore_event", ignore_event)
    graph.add_node("check_limits", check_limits)
    graph.add_node("prepare_frontier", prepare_frontier)
    graph.add_node("retrieve_question_pool", retrieve_pool)
    graph.add_node("interviewer_decision", decide)
    graph.add_node("validate_decision", validate_decision)
    graph.add_node("select_switch_question", select_switch_question)
    graph.add_node("present_question", present_question)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "compose_opening_question")
    graph.add_edge("compose_opening_question", "wait_for_candidate")
    graph.add_conditional_edges(
        "wait_for_candidate",
        route_event,
        {"record": "record_turn", "finish": "finalize", "ignore": "ignore_event"},
    )
    graph.add_edge("ignore_event", "wait_for_candidate")
    graph.add_edge("record_turn", "check_limits")
    graph.add_conditional_edges(
        "check_limits",
        route_limits,
        {"finish": "finalize", "continue": "prepare_frontier"},
    )
    graph.add_edge("prepare_frontier", "interviewer_decision")
    graph.add_edge("interviewer_decision", "validate_decision")
    graph.add_conditional_edges(
        "validate_decision",
        route_decision,
        {
            "finish": "finalize",
            "retrieve": "retrieve_question_pool",
            "present": "present_question",
        },
    )
    graph.add_edge("retrieve_question_pool", "select_switch_question")
    graph.add_edge("select_switch_question", "present_question")
    graph.add_edge("present_question", "wait_for_candidate")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
