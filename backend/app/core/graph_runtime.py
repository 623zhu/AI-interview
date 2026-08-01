"""Lifecycle and orchestration for the three LangGraph workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.redis import AsyncShallowRedisSaver
from langgraph.types import Command

from app.agent.evaluation_workflow import (
    build_evaluation_graph,
    evaluation_thread_id,
)
from app.agent.interview_workflow import build_interview_graph
from app.agent.report_workflow import build_report_graph, report_thread_id
from app.core.config import settings
from app.core.database import async_session_factory
from app.services.interview_archive_service import load_interview_archive

logger = logging.getLogger(__name__)


def interview_thread_id(session_id: str) -> str:
    """Return the checkpoint namespace for one live interview graph."""
    return f"interview:{session_id}"


def graph_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Build the LangGraph invocation config for a checkpoint thread."""
    return {"configurable": {"thread_id": thread_id}}


@dataclass
class GraphRuntime:
    """三张 LangGraph 图的统一入口。

    API 层不直接操作图节点，只通过这里按 session_id 启动、恢复和读取状态。
    三张图共享 checkpointer，但使用不同 thread_id，状态不会互相覆盖。
    """

    checkpointer: Any
    interview_graph: Any
    evaluation_graph: Any
    report_graph: Any

    async def get_interview_state(self, session_id: str) -> dict[str, Any] | None:
        """从 Redis 热 checkpoint 读取一场进行中面试的最新完整状态。"""
        snapshot = await self.interview_graph.aget_state(
            graph_config(interview_thread_id(session_id))
        )
        return dict(snapshot.values) if snapshot and snapshot.values else None

    async def get_durable_interview_state(
        self, session_id: str
    ) -> dict[str, Any] | None:
        """Read the hot checkpoint first, then the terminal MySQL archive."""
        state = await self.get_interview_state(session_id)
        if state:
            return state
        async with async_session_factory() as db:
            return await load_interview_archive(db, session_id)

    async def start_interview(self, initial_state: dict[str, Any]) -> dict[str, Any]:
        """用初始状态启动主图；图运行到第一次候选人输入 interrupt 后暂停。"""
        session_id = str(initial_state["session_id"])
        return await self.interview_graph.ainvoke(
            initial_state,
            graph_config(interview_thread_id(session_id)),
        )

    async def resume_interview(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        """把回答、跳过或结束事件送回主图上一次暂停的位置。"""
        return await self.interview_graph.ainvoke(
            # Command(resume=...) 不会重建面试，而是恢复对应 thread_id 的 interrupt。
            Command(resume=event),
            graph_config(interview_thread_id(session_id)),
        )

    async def evaluate_turn(
        self, session_id: str, turn_id: str
    ) -> dict[str, Any] | None:
        """独立评价一个已回答 turn；已完成的评价直接从 checkpoint 返回。"""
        main_state = await self.get_durable_interview_state(session_id)
        if not main_state:
            raise ValueError(f"Interview state {session_id} not found")
        turn = next(
            (item for item in main_state.get("turns") or [] if item.get("turn_id") == turn_id),
            None,
        )
        if not turn or turn.get("status") != "answered":
            return None

        config = graph_config(evaluation_thread_id(session_id, turn_id))
        existing = await self.evaluation_graph.aget_state(config)
        if existing and existing.values.get("status") == "completed":
            return dict(existing.values.get("evaluation") or {})

        result = await self.evaluation_graph.ainvoke(
            {
                "session_id": session_id,
                "turn": turn,
                "job_snapshot": main_state.get("job_snapshot") or {},
                "resume_summary": main_state.get("resume_summary") or "",
                "rubric": {},
                "evaluation": None,
                "status": "pending",
                "error": None,
            },
            config,
        )
        if result.get("status") != "completed":
            logger.warning(
                "Turn evaluation failed session=%s turn=%s error=%s",
                session_id,
                turn_id,
                result.get("error"),
            )
            return None
        return dict(result.get("evaluation") or {})

    async def generate_report(self, session_id: str) -> dict[str, Any]:
        """Run the report graph only after a durable completed interview exists."""
        main_state = await self.get_durable_interview_state(session_id)
        if not main_state:
            raise ValueError(f"Interview state {session_id} not found")
        if main_state.get("status") != "completed":
            raise ValueError("Interview must be completed before report generation")

        config = graph_config(report_thread_id(session_id))
        result = await self.report_graph.ainvoke(
            {
                "session_id": session_id,
                "user_id": main_state["user_id"],
                "job_snapshot": main_state.get("job_snapshot") or {},
                "turns": main_state.get("turns") or [],
                "evaluations": [],
                "aggregate": {},
                "narrative": {},
                "status": "pending",
                "report_id": None,
                "error": None,
            },
            config,
        )
        await self.interview_graph.aupdate_state(
            graph_config(interview_thread_id(session_id)),
            {"report_status": result.get("status", "failed")},
        )
        return dict(result)

    async def delete_session(self, session_id: str) -> None:
        """Delete interview, evaluation, and report checkpoints for a session."""
        state = await self.get_durable_interview_state(session_id)
        thread_ids = [interview_thread_id(session_id), report_thread_id(session_id)]
        for turn in (state or {}).get("turns") or []:
            turn_id = str(turn.get("turn_id") or "")
            if turn_id:
                thread_ids.append(evaluation_thread_id(session_id, turn_id))
        for thread_id in thread_ids:
            await self.checkpointer.adelete_thread(thread_id)


def create_graph_runtime(
    checkpointer: Any,
    *,
    decision_maker: Any = None,
    question_pool_loader: Any = None,
    switch_question_composer: Any = None,
    opening_question_composer: Any = None,
    rubric_loader: Any = None,
    evaluator: Any = None,
    narrative_writer: Any = None,
    persister: Any = None,
) -> GraphRuntime:
    """Compile all workflows. Dependency overrides keep tests deterministic."""
    interview_graph = build_interview_graph(
        checkpointer,
        decision_maker=decision_maker,
        question_pool_loader=question_pool_loader,
        switch_question_composer=switch_question_composer,
        opening_question_composer=opening_question_composer,
    )
    evaluation_graph = build_evaluation_graph(
        checkpointer,
        rubric_loader=rubric_loader,
        evaluator=evaluator,
    )

    runtime_ref: dict[str, GraphRuntime] = {}

    async def collect_evaluation(
        turn: dict[str, Any], report_state: dict[str, Any]
    ) -> dict[str, Any] | None:
        runtime = runtime_ref["runtime"]
        return await runtime.evaluate_turn(
            str(report_state["session_id"]), str(turn["turn_id"])
        )

    report_graph = build_report_graph(
        checkpointer,
        evaluation_collector=collect_evaluation,
        narrative_writer=narrative_writer,
        persister=persister,
    )
    runtime = GraphRuntime(
        checkpointer=checkpointer,
        interview_graph=interview_graph,
        evaluation_graph=evaluation_graph,
        report_graph=report_graph,
    )
    runtime_ref["runtime"] = runtime
    return runtime


_runtime: GraphRuntime | None = None
_redis_saver_context: Any = None


async def start_graph_runtime() -> GraphRuntime:
    """Create the process-wide runtime and initialize its configured checkpointer."""
    global _runtime, _redis_saver_context
    if _runtime is not None:
        return _runtime

    if settings.LANGGRAPH_CHECKPOINTER_BACKEND == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        _runtime = create_graph_runtime(InMemorySaver())
        logger.warning(
            "LangGraph is using the non-durable in-memory checkpointer"
        )
        return _runtime

    _redis_saver_context = AsyncShallowRedisSaver.from_conn_string(
        settings.REDIS_URL,
        ttl={
            "default_ttl": settings.LANGGRAPH_CHECKPOINT_TTL_MINUTES,
            "refresh_on_read": True,
        },
    )
    saver = await _redis_saver_context.__aenter__()
    try:
        await saver.asetup()
        _runtime = create_graph_runtime(saver)
    except Exception:
        await _redis_saver_context.__aexit__(None, None, None)
        _redis_saver_context = None
        raise
    return _runtime


def get_graph_runtime() -> GraphRuntime:
    """Return the initialized process-wide runtime or fail fast during startup."""
    if _runtime is None:
        raise RuntimeError("LangGraph runtime has not been started")
    return _runtime


async def close_graph_runtime() -> None:
    """Close the checkpointer context and clear process-wide runtime references."""
    global _runtime, _redis_saver_context
    _runtime = None
    if _redis_saver_context is not None:
        await _redis_saver_context.__aexit__(None, None, None)
        _redis_saver_context = None
