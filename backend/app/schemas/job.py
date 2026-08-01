"""Job schemas."""
from datetime import datetime
from pydantic import BaseModel, Field


class JobOut(BaseModel):
    id: str
    title: str
    category: str
    level: str
    description: str | None = None
    requirements: dict
    skill_tree: dict | None = None
    salary_range: str | None = None
    company_type: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class JobListItem(BaseModel):
    id: str
    title: str
    category: str
    level: str
    salary_range: str | None = None
    company_type: str
    is_active: bool

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    level: str = Field(default="mid")
    description: str | None = None
    requirements: dict
    skill_tree: dict | None = None
    salary_range: str | None = None
    company_type: str = "互联网"
    is_active: bool = True


class JobUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    level: str | None = None
    description: str | None = None
    requirements: dict | None = None
    skill_tree: dict | None = None
    salary_range: str | None = None
    company_type: str | None = None
    is_active: bool | None = None
