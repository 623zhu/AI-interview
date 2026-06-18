import json

import pytest

from app.agent.tools import (
    ToolValidationError,
    validate_difficulty,
    validate_retrieve_questions_args,
    validate_score,
    validate_skill_update_args,
)


def _error_payload(exc: ToolValidationError) -> dict:
    return json.loads(exc.to_tool_result())


def test_validate_score_accepts_numeric_strings():
    assert validate_score("0.7", "confidence") == 0.7


def test_validate_score_rejects_out_of_range_values():
    with pytest.raises(ToolValidationError) as exc:
        validate_score(1.2, "confidence")

    payload = _error_payload(exc.value)
    assert payload["ok"] is False
    assert payload["code"] == "tool_invalid_score"
    assert payload["details"]["field"] == "confidence"


def test_validate_difficulty_rejects_unknown_value():
    with pytest.raises(ToolValidationError) as exc:
        validate_difficulty("expert")

    assert _error_payload(exc.value)["code"] == "tool_invalid_difficulty"


def test_validate_retrieve_questions_args_requires_query():
    with pytest.raises(ToolValidationError) as exc:
        validate_retrieve_questions_args("   ", "medium")

    assert _error_payload(exc.value)["code"] == "tool_missing_argument"


def test_validate_retrieve_questions_args_normalizes_query_and_difficulty():
    query, difficulty = validate_retrieve_questions_args("  RAG retrieval flow  ", " HARD ")

    assert query == "RAG retrieval flow"
    assert difficulty == "hard"


def test_validate_skill_update_args_requires_skill_path():
    with pytest.raises(ToolValidationError) as exc:
        validate_skill_update_args(skill_path="", confidence=0.5, depth=0.5)

    assert _error_payload(exc.value)["code"] == "tool_missing_argument"


def test_validate_skill_update_args_truncates_long_comment():
    args = validate_skill_update_args(
        skill_path="Backend/API",
        confidence=0.8,
        depth=0.6,
        comment="x" * 2000,
    )

    assert args["skill_path"] == "Backend/API"
    assert args["confidence"] == 0.8
    assert args["depth"] == 0.6
    assert len(args["comment"]) == 1200
