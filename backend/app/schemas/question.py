"""Question schemas."""
from datetime import datetime
from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: str
    category: str
    difficulty: str
    skill_nodes: list[str] | None = None
    content: str
    expected_points: str | None = None
    reference_answer: str | None = None
    evaluation_criteria: dict | None = None
    source: str
    usage_count: int
    avg_score: float | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionListItem(BaseModel):
    id: str
    category: str
    difficulty: str
    skill_nodes: list[str] | None = None
    content: str
    expected_points: str | None = None
    source: str
    usage_count: int
    avg_score: float | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class QuestionGenerateRequest(BaseModel):
    resume_id: str
    job_id: str
    config: dict | None = Field(
        default=None,
        description="面试配置: question_count, difficulty_distribution, categories"
    )


class GeneratedQuestion(BaseModel):
    id: str | None = None
    source_question_id: str | None = None
    category: str
    difficulty: str
    content: str
    expected_points: str | None = None
    evaluation_criteria: dict | None = None


class QuestionGenerateResponse(BaseModel):
    questions: list[GeneratedQuestion]
    total: int
    difficulty_distribution: dict
    category_distribution: dict


class QuestionCreate(BaseModel):
    """新增题目 — 必填：题目内容、核心点、参考答案"""
    content: str = Field(..., min_length=1, description="题目内容")
    expected_points: str = Field(..., min_length=1, description="核心考察点 / 评分指引")
    reference_answer: str = Field(..., min_length=1, description="参考答案")
    category: str = Field(default="concept", description="分类: concept/principle/practice/optimization/design")
    difficulty: str = Field(default="medium", description="难度: easy/medium/hard")
    skill_nodes: list[str] | None = None
    evaluation_criteria: dict | None = None


class QuestionUpdate(BaseModel):
    category: str | None = None
    difficulty: str | None = None
    skill_nodes: list[str] | None = None
    content: str | None = None
    expected_points: str | None = None
    reference_answer: str | None = None
    evaluation_criteria: dict | None = None
    is_active: bool | None = None


class QuestionImportItem(BaseModel):
    """批量导入题目 — 只需 题目/核心点/参考答案 三个必填字段。"""
    content: str = Field(..., min_length=1, description="题目内容")
    expected_points: str = Field(..., min_length=1, description="核心考察点 / 评分指引")
    reference_answer: str = Field(..., min_length=1, description="参考答案")
    category: str = Field(default="concept", description="分类: concept/principle/practice/optimization/design")
    difficulty: str = Field(default="medium", description="难度: easy/medium/hard")
    skill_nodes: list[str] | None = None
    evaluation_criteria: dict | None = None


class QuestionImportResult(BaseModel):
    total: int
    success: int
    failed: int
    errors: list[str] = []
