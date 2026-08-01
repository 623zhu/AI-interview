"""Typed contracts shared by the interview LangGraph workflows."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator


class InterviewAction(str, Enum):
    CLARIFY = "CLARIFY"
    PROBE = "PROBE"
    BRIDGE = "BRIDGE"
    SWITCH = "SWITCH"
    FINISH = "FINISH"


class QuestionCandidate(BaseModel):
    id: str
    content: str
    skill_path: str
    difficulty: str = "medium"
    category: str = "concept"
    expected_points: str = ""
    evaluation_criteria: dict[str, Any] = Field(default_factory=dict)


class InterviewerDecision(BaseModel):
    action: InterviewAction
    target_skill_path: str = ""
    source_question_id: str | None = None
    anchor: str = ""
    probe_goal: str = ""
    question: str = ""
    reason: str = ""

    @field_validator(
        "target_skill_path",
        "anchor",
        "probe_goal",
        "question",
        "reason",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("question")
    @classmethod
    def limit_question(cls, value: str) -> str:
        return value[:240]


class ComposedInterviewQuestion(BaseModel):
    """Candidate-facing wording for a valid SWITCH decision."""

    anchor: str = ""
    probe_goal: str = ""
    question: str = Field(min_length=1, max_length=240)

    @field_validator("anchor", "probe_goal", "question", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return str(value or "").strip()


class TurnEvaluation(BaseModel):
    # Providers occasionally omit this field; the evaluation graph always
    # overwrites it from the trusted turn state after parsing.
    turn_id: str = ""
    skill_path: str = ""
    scored: bool = True
    answer_score: int | None = Field(default=None, ge=0, le=100)
    correctness: int | None = Field(default=None, ge=0, le=100)
    completeness: int | None = Field(default=None, ge=0, le=100)
    depth: int | None = Field(default=None, ge=0, le=100)
    communication: int | None = Field(default=None, ge=0, le=100)
    covered_points: list[str] = Field(default_factory=list)
    missed_points: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    comment: str = ""
    score_confidence: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_payload(cls, value: Any) -> Any:
        """Accept common single-evaluation wrappers returned by chat models."""
        if not isinstance(value, dict):
            return value

        data = dict(value)
        nested = data.get("evaluation")
        if isinstance(nested, dict):
            data = dict(nested)
        else:
            nested_list = data.get("evaluations")
            if (
                isinstance(nested_list, list)
                and len(nested_list) == 1
                and isinstance(nested_list[0], dict)
            ):
                data = dict(nested_list[0])

        if not data.get("comment"):
            data["comment"] = data.get("rationale") or data.get("notes") or ""
        for field in ("covered_points", "missed_points", "evidence"):
            if isinstance(data.get(field), str):
                data[field] = [data[field]]
        return data

    @model_validator(mode="after")
    def clear_non_scored_dimensions(self) -> "TurnEvaluation":
        if not self.scored:
            self.answer_score = None
            self.correctness = None
            self.completeness = None
            self.depth = None
            self.communication = None
        return self


class ReportNarrative(BaseModel):
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class InterviewGraphState(TypedDict, total=False):
    session_id: str
    user_id: str
    resume_id: str
    job_id: str
    status: Literal["created", "in_progress", "completed"]
    config: dict[str, Any]
    job_snapshot: dict[str, Any]
    resume_summary: str
    started_at: str
    deadline_at: str
    completed_at: str | None
    current_question: dict[str, Any] | None
    turns: list[dict[str, Any]]
    coverage: dict[str, dict[str, Any]]
    used_question_ids: list[str]
    processed_event_ids: list[str]
    pending_evaluation_ids: list[str]
    incoming_event: dict[str, Any] | None
    skill_frontier: list[dict[str, Any]]
    question_pool: list[dict[str, Any]]
    interviewer_decision: dict[str, Any] | None
    hard_stop_reason: str | None
    report_status: str
    background_jobs: list[dict[str, Any]]
    output: dict[str, Any] | None
    error: str | None


class EvaluationGraphState(TypedDict, total=False):
    session_id: str
    turn: dict[str, Any]
    job_snapshot: dict[str, Any]
    resume_summary: str
    rubric: dict[str, Any]
    evaluation: dict[str, Any] | None
    status: Literal["pending", "completed", "failed"]
    error: str | None


class ReportGraphState(TypedDict, total=False):
    session_id: str
    user_id: str
    job_snapshot: dict[str, Any]
    turns: list[dict[str, Any]]
    evaluations: list[dict[str, Any]]
    aggregate: dict[str, Any]
    narrative: dict[str, Any]
    status: Literal["pending", "generating", "completed", "failed"]
    report_id: str | None
    error: str | None
