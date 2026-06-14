"""Authentication schemas."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class SendCodeRequest(BaseModel):
    email: EmailStr


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel): 
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    user: UserOut
    tokens: TokenResponse
