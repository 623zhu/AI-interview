"""Deterministic policy helpers for the interview workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.agent.interview_contracts import (
    InterviewAction,
    InterviewerDecision,
    QuestionCandidate,
)

VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def utc_now() -> datetime:
    """Return the timezone-aware UTC clock value used by workflow states."""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Serialize a datetime in UTC so checkpoints use one timestamp format."""
    return value.astimezone(timezone.utc).isoformat()


def parse_datetime(value: str | None) -> datetime | None:
    """Parse checkpoint timestamps, treating legacy naive values as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_interview_config(config: dict[str, Any] | None) -> dict[str, int]:
    """Apply defaults and safety bounds before configuration enters the graph."""
    raw = config or {}
    return {
        "max_turns": min(max(int(raw.get("max_turns", 12)), 3), 30),
        "max_duration_minutes": min(
            max(int(raw.get("max_duration_minutes", 45)), 5), 180
        ),
        "max_follow_ups_per_skill": min(
            max(int(raw.get("max_follow_ups_per_skill", 1)), 0), 2
        ),
    }


def deadline_for(started_at: datetime, config: dict[str, int]) -> datetime:
    """Derive the hard interview deadline from normalized configuration."""
    return started_at + timedelta(minutes=config["max_duration_minutes"])


def build_skill_catalog(job_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the configured skill tree, falling back to job requirements."""
    catalog: list[dict[str, Any]] = []
    tree = job_snapshot.get("skill_tree") or {}
    domains = tree.get("domains") or []

    for domain in domains:
        domain_name = str(domain.get("name") or "").strip()
        if not domain_name:
            continue
        skills = domain.get("skills") or []
        domain_weight = float(domain.get("weight") or 0)
        skill_weight = domain_weight / max(len(skills), 1)
        for skill in skills:
            _append_skill_node(
                catalog,
                skill,
                parent_path=domain_name,
                weight=skill_weight,
                depth=1,
            )

    if catalog:
        return catalog

    skills = (job_snapshot.get("requirements") or {}).get("skills") or []
    weight = 1 / max(len(skills), 1)
    for skill in skills:
        name = str(skill or "").strip()
        if name:
            catalog.append({
                "path": name,
                "name": name,
                "weight": weight,
                "difficulty": _job_level_to_difficulty(job_snapshot.get("level")),
                "depth": 1,
                "parent_path": "",
            })
    return catalog


def _append_skill_node(
    catalog: list[dict[str, Any]],
    node: dict[str, Any],
    *,
    parent_path: str,
    weight: float,
    depth: int,
) -> None:
    name = str(node.get("name") or "").strip()
    if not name:
        return
    path = f"{parent_path}/{name}" if parent_path else name
    difficulty = str(node.get("level") or "medium").lower()
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"
    catalog.append({
        "path": path,
        "name": name,
        "weight": weight,
        "difficulty": difficulty,
        "depth": depth,
        "parent_path": parent_path,
    })
    children = node.get("children") or []
    child_weight = weight / max(len(children), 1)
    for child in children:
        _append_skill_node(
            catalog,
            child,
            parent_path=path,
            weight=child_weight,
            depth=depth + 1,
        )


def _job_level_to_difficulty(level: Any) -> str:
    normalized = str(level or "mid").lower()
    if normalized in {"senior", "lead"}:
        return "hard"
    if normalized in {"junior", "intern"}:
        return "easy"
    return "medium"


def initialize_coverage(job_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Create mutable coverage counters from the immutable job skill catalog."""
    return {
        item["path"]: {
            **item,
            "status": "unasked",
            "questions_asked": 0,
            "follow_ups": 0,
            "skips": 0,
            "last_turn_number": None,
        }
        for item in build_skill_catalog(job_snapshot)
    }


def build_skill_frontier(
    coverage: dict[str, dict[str, Any]],
    *,
    current_skill: str = "",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """选出本轮最值得考察且当前合法的技能节点。

    未覆盖技能优先，其次考虑已问题数、岗位权重和树深度；父技能尚未
    覆盖时暂不开放子技能，避免面试无序跳到过细的知识点。
    """
    if not coverage:
        return []

    eligible = []
    for path, entry in coverage.items():
        parent = entry.get("parent_path") or ""
        if entry.get("depth", 1) > 1 and parent:
            parent_state = coverage.get(parent)
            if parent_state and parent_state.get("status") == "unasked":
                continue
        if path == current_skill and entry.get("status") != "unasked":
            continue
        eligible.append(dict(entry))

    status_rank = {"unasked": 0, "asked": 1, "deepened": 2, "closed": 3}
    eligible.sort(
        key=lambda item: (
            status_rank.get(item.get("status", "unasked"), 9),
            item.get("questions_asked", 0),
            -float(item.get("weight", 0)),
            item.get("depth", 1),
            item.get("path", ""),
        )
    )
    return eligible[:limit]


def update_coverage_for_turn(
    coverage: dict[str, dict[str, Any]],
    *,
    skill_path: str,
    action: InterviewAction,
    turn_number: int,
    answered: bool,
) -> dict[str, dict[str, Any]]:
    """候选人处理完当前题后更新覆盖；展示问题本身不代表已经覆盖。"""
    updated = {path: dict(entry) for path, entry in coverage.items()}
    if not skill_path or skill_path not in updated:
        return updated

    entry = updated[skill_path]
    if not answered:
        # 跳过只记录行为，不增加 questions_asked，也不改变技能覆盖状态。
        entry["skips"] = int(entry.get("skips", 0)) + 1
        entry["last_skipped_turn"] = turn_number
        updated[skill_path] = entry
        return updated

    entry["questions_asked"] = int(entry.get("questions_asked", 0)) + 1
    entry["last_turn_number"] = turn_number
    if action in {InterviewAction.CLARIFY, InterviewAction.PROBE}:
        entry["follow_ups"] = int(entry.get("follow_ups", 0)) + 1
        entry["status"] = "deepened"
    elif entry.get("status") == "unasked":
        entry["status"] = "asked"
    updated[skill_path] = entry
    return updated


def hard_stop_reason(state: dict[str, Any], *, now: datetime | None = None) -> str | None:
    """返回硬停止原因；没有达到最大回答数或截止时间时返回 None。"""
    config = normalize_interview_config(state.get("config"))
    answered_count = sum(
        1 for turn in state.get("turns", []) if turn.get("status") == "answered"
    )
    if answered_count >= config["max_turns"]:
        return "max_turns"

    deadline = parse_datetime(state.get("deadline_at"))
    if deadline and (now or utc_now()) >= deadline:
        return "max_duration"
    return None


def coverage_is_sufficient(coverage: dict[str, dict[str, Any]]) -> bool:
    """判断岗位权重最高的关键技能是否都至少得到一次有效回答。"""
    if not coverage:
        return False
    weighted = sorted(
        coverage.values(),
        key=lambda item: float(item.get("weight", 0)),
        reverse=True,
    )
    key_nodes = weighted[: max(1, min(4, len(weighted)))]
    return all(item.get("status") != "unasked" for item in key_nodes)


def validate_interviewer_decision(
    decision: InterviewerDecision,
    *,
    state: dict[str, Any],
) -> tuple[InterviewerDecision | None, str | None]:
    """校验并规范化模型动作，返回（可执行动作，拒绝原因）。

    返回 None 表示模型动作不能执行，调用方应按确定性策略重新路由。
    """
    pool = {
        str(item.get("id")): QuestionCandidate.model_validate(item)
        for item in state.get("question_pool", [])
        if item.get("id")
    }
    coverage = state.get("coverage", {})
    current_question = state.get("current_question") or {}
    current_skill = str(current_question.get("skill_path") or "")

    if decision.action == InterviewAction.FINISH:
        if state.get("hard_stop_reason") or coverage_is_sufficient(coverage):
            return decision, None
        return None, "finish_not_allowed"

    if decision.action == InterviewAction.SWITCH:
        candidate = pool.get(str(decision.source_question_id or ""))
        if not candidate:
            return None, "switch_question_not_in_pool"
        decision.target_skill_path = candidate.skill_path
        if not decision.question:
            decision.question = candidate.content
        return decision, None

    if not decision.question:
        return None, "question_required"

    if decision.action in {InterviewAction.CLARIFY, InterviewAction.PROBE}:
        decision.source_question_id = None
        if not decision.target_skill_path:
            frontier = state.get("skill_frontier") or []
            decision.target_skill_path = current_skill or (
                str(frontier[0].get("path") or "") if frontier else ""
            )
        config = normalize_interview_config(state.get("config"))
        entry = coverage.get(decision.target_skill_path, {})
        follow_ups = int(entry.get("follow_ups", 0))
        if not entry:
            follow_ups = 0
            for turn in reversed(state.get("turns") or []):
                prior_action = (turn.get("question") or {}).get("action")
                if prior_action not in {
                    InterviewAction.CLARIFY.value,
                    InterviewAction.PROBE.value,
                }:
                    break
                follow_ups += 1
        if follow_ups >= config["max_follow_ups_per_skill"]:
            return None, "follow_up_limit_reached"
        if not decision.probe_goal:
            return None, "probe_goal_required"
        return decision, None

    if decision.action == InterviewAction.BRIDGE:
        if decision.target_skill_path not in coverage:
            return None, "bridge_skill_not_in_tree"
        decision.source_question_id = None
        return decision, None

    return None, "unsupported_action"


def policy_redirect_decision(
    state: dict[str, Any], *, reason: str
) -> InterviewerDecision:
    """Turn a rejected model action into a normal deterministic transition."""
    frontier = state.get("skill_frontier") or []
    if frontier:
        target = str(frontier[0].get("path") or "")
        if target:
            return InterviewerDecision(
                action=InterviewAction.SWITCH,
                target_skill_path=target,
                reason=f"policy_redirect:{reason}",
            )

    coverage = state.get("coverage") or {}
    if state.get("hard_stop_reason") or coverage_is_sufficient(coverage):
        return InterviewerDecision(
            action=InterviewAction.FINISH,
            reason=f"policy_redirect:{reason}",
        )

    raise ValueError(f"No legal interview transition after rejected action: {reason}")


def model_failure_fallback_decision(
    state: dict[str, Any],
    *,
    planned: InterviewerDecision | None = None,
    candidate: QuestionCandidate | None = None,
    opening: bool = False,
) -> InterviewerDecision:
    """Last resort used only after an LLM call exhausts its configured retries."""
    if opening:
        job_title = str((state.get("job_snapshot") or {}).get("title") or "目标")
        return InterviewerDecision(
            action=InterviewAction.BRIDGE,
            probe_goal="了解候选人与目标岗位相关的经历和主要贡献",
            question=(
                f"请结合{job_title}岗位，简要介绍你最相关的一段经历和主要贡献。"
            ),
            reason="model_failure_after_retries_using_opening_fallback",
        )
    if candidate is not None:
        base = planned or InterviewerDecision(action=InterviewAction.SWITCH)
        return base.model_copy(update={
            "action": InterviewAction.SWITCH,
            "target_skill_path": candidate.skill_path,
            "source_question_id": candidate.id,
            "question": candidate.content,
            "reason": "model_failure_after_retries_using_source_question",
        })

    frontier = state.get("skill_frontier") or []
    target = str(frontier[0].get("path") or "") if frontier else ""
    target_name = str(frontier[0].get("name") or target) if frontier else ""
    generic_prompts = [
        "请结合一个实际项目，讲讲你遇到的关键技术难点和解决过程？",
        "请选一个你负责较多的模块，说明当时的设计取舍和验证方式？",
        "遇到线上问题时，你通常怎样定位原因并确认修复有效？",
    ]
    question = (
        f"围绕{target_name}，请结合实际经历说明一次关键判断或技术取舍？"
        if target_name
        else generic_prompts[len(state.get("turns") or []) % len(generic_prompts)]
    )
    return InterviewerDecision(
        action=InterviewAction.SWITCH,
        target_skill_path=target,
        probe_goal="了解候选人在实际项目中的技术判断和解决问题过程",
        question=question,
        reason="model_failure_after_retries",
    )
