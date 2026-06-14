"""Resume schemas."""
from datetime import datetime
from pydantic import BaseModel


class ResumeOut(BaseModel):
    id: str
    user_id: str
    original_filename: str
    file_type: str
    file_size: int
    raw_text: str | None = None
    parsed_data: dict | None = None
    parse_status: str
    parse_error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ResumeListItem(BaseModel):
    """Brief resume info for list display."""
    id: str
    original_filename: str
    file_type: str
    parse_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ResumeUpdate(BaseModel):
    """Manual update of parsed data."""
    parsed_data: dict
