"""Public schema exports."""

from pydantic import BaseModel

from app.schemas.auth import (
    AuthData,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SendCodeRequest,
    TokenPair,
    UserOut,
)


class ApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict | list | None = None


class PaginatedResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


__all__ = [
    "AuthData",
    "LoginRequest",
    "RefreshRequest",
    "RegisterRequest",
    "SendCodeRequest",
    "TokenPair",
    "UserOut",
    "ApiResponse",
    "PaginatedResponse",
]
