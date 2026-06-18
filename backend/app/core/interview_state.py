"""Interview session state rules."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


STATUS_CREATED = "created"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

ACTION_START = "start"
ACTION_CHAT = "chat"
ACTION_SKIP = "skip"
ACTION_END = "end"
ACTION_DELETE = "delete"


@dataclass(frozen=True)
class ActionRule:
    allowed_statuses: frozenset[str]
    next_status: str | None = None


ACTION_RULES = {
    ACTION_START: ActionRule(frozenset({STATUS_CREATED}), STATUS_IN_PROGRESS),
    ACTION_CHAT: ActionRule(frozenset({STATUS_IN_PROGRESS})),
    ACTION_SKIP: ActionRule(frozenset({STATUS_IN_PROGRESS})),
    ACTION_END: ActionRule(frozenset({STATUS_IN_PROGRESS}), STATUS_COMPLETED),
    ACTION_DELETE: ActionRule(
        frozenset({STATUS_CREATED, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_CANCELLED})
    ),
}


def can_perform(status: str, action: str) -> bool:
    rule = ACTION_RULES[action]
    return status in rule.allowed_statuses


def assert_can_perform(status: str, action: str) -> None:
    if can_perform(status, action):
        return

    raise HTTPException(
        status_code=400,
        detail={
            "code": "invalid_interview_state",
            "message": "当前面试状态不允许执行该操作",
            "status": status,
            "action": action,
            "allowed_statuses": sorted(ACTION_RULES[action].allowed_statuses),
        },
    )


def next_status_for(action: str) -> str | None:
    return ACTION_RULES[action].next_status
