"""Authentication request and response schemas."""

from datetime import datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
)

#:统一邮箱格式——去空格 + 转小写。
def normalize_email(value: EmailStr | str) -> str:
    """在查询和存储前标准化邮箱地址"""

    return str(value).strip().lower()


def validate_password(value: str) -> str:
    """Validate password length according to bcrypt limits."""

    if len(value) < 8:
        raise ValueError("密码至少需要 8 个字符")

    if len(value.encode("utf-8")) > 72:
        raise ValueError("密码的 UTF-8 长度不能超过 72 字节")

    return value


class EmailRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def normalized_email(cls, value: EmailStr) -> str:
        return normalize_email(value)


class SendCodeRequest(EmailRequest):
    """Request a registration verification code."""


class RegisterRequest(EmailRequest):
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    password: str = Field(min_length=8, max_length=128)
    code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        return validate_password(value)


class LoginRequest(EmailRequest):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: str) -> str:
        return validate_password(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return (
            value.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(gt=0)


class AuthData(BaseModel):
    user: UserOut
    tokens: TokenPair
