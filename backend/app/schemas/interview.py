"""Interview schemas."""
from datetime import datetime
from pydantic import BaseModel, Field


class InterviewCreateRequest(BaseModel):
    resume_id: str
    job_title: str = Field(..., min_length=1, max_length=100, description="期望面试岗位")
    config: dict | None = Field(
        default=None,
        description="面试配置: question_count, difficulty_distribution, max_duration_minutes, enable_follow_up"
    )


class InterviewSessionOut(BaseModel):
    id: str
    user_id: str
    resume_id: str
    job_id: str
    status: str
    config: dict | None = None
    total_questions: int
    current_question: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewMessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    message_type: str | None = None
    question_id: str | None = None
    scores: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewDetailOut(InterviewSessionOut):
    resume: dict | None = None
    job: dict | None = None
    messages: list[InterviewMessageOut] = []


class StartInterviewResponse(BaseModel):
    id: str
    status: str
    started_at: datetime
    first_question: dict


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class SkipResponse(BaseModel):
    skipped_question_id: str
    next_question: dict | None = None


class EndInterviewResponse(BaseModel):
    session_id: str
    status: str
    completed_at: datetime
    duration_seconds: int
    questions_answered: int
    questions_skipped: int
    report_id: str | None = None


class InterviewListItem(BaseModel):
    id: str
    status: str
    job_title: str | None = None
    total_questions: int
    score: int | None = None
    duration_seconds: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
