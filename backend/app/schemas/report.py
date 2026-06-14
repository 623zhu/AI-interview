"""Report schemas."""
from datetime import datetime
from pydantic import BaseModel, field_serializer


class ReportOut(BaseModel):
    id: str
    session_id: str
    user_id: str
    overall_score: int
    dimension_scores: dict = {}
    question_evaluations: list = []
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    improvements: list | None = None
    full_report: str = ""
    generated_at: datetime | None = None
    created_at: datetime | None = None

    @field_serializer('generated_at', 'created_at')
    def serialize_dt(self, dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    id: str
    session_id: str
    job_title: str | None = None
    round_count: int = 0
    generated_at: str

    model_config = {"from_attributes": True}
