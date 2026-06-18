import pytest
from fastapi import HTTPException

from app.core.interview_state import (
    ACTION_CHAT,
    ACTION_DELETE,
    ACTION_END,
    ACTION_SKIP,
    ACTION_START,
    STATUS_COMPLETED,
    STATUS_CREATED,
    STATUS_IN_PROGRESS,
    assert_can_perform,
    can_perform,
    next_status_for,
)


def test_interview_state_allows_expected_transitions():
    assert can_perform(STATUS_CREATED, ACTION_START)
    assert next_status_for(ACTION_START) == STATUS_IN_PROGRESS

    assert can_perform(STATUS_IN_PROGRESS, ACTION_CHAT)
    assert can_perform(STATUS_IN_PROGRESS, ACTION_SKIP)
    assert can_perform(STATUS_IN_PROGRESS, ACTION_END)
    assert next_status_for(ACTION_END) == STATUS_COMPLETED

    assert can_perform(STATUS_COMPLETED, ACTION_DELETE)


def test_interview_state_rejects_invalid_actions():
    assert not can_perform(STATUS_CREATED, ACTION_CHAT)
    assert not can_perform(STATUS_CREATED, ACTION_END)
    assert not can_perform(STATUS_COMPLETED, ACTION_START)
    assert not can_perform(STATUS_COMPLETED, ACTION_SKIP)


def test_interview_state_error_payload_is_structured():
    with pytest.raises(HTTPException) as exc:
        assert_can_perform(STATUS_COMPLETED, ACTION_CHAT)

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "invalid_interview_state"
    assert exc.value.detail["status"] == STATUS_COMPLETED
    assert exc.value.detail["action"] == ACTION_CHAT
