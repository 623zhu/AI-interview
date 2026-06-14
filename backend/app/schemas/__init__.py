"""Pydantic schemas package."""
from pydantic import BaseModel


class ApiResponse(BaseModel):
    """Standard API response wrapper."""
    code: int = 200
    message: str = "success"
    data: dict | list | None = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    code: int = 200
    message: str = "success"
    data: dict  # {"items": [...], "total": N, "page": N, "page_size": N}
