"""认证 HTTP 接口。"""

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    bearer_scheme,
    get_current_user,
    invalid_access_token,
)
from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SendCodeRequest,
    UserOut,
)
from app.services.auth_service import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
    send_registration_code,
)


router = APIRouter()


@router.post("/send-code")
async def send_code(
    data: SendCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """发送注册验证码。"""

    await send_registration_code(
        db,
        redis,
        email=str(data.email),
        client_ip=client_ip(request),
    )

    # 路由只组装 HTTP 响应，不包含验证码业务逻辑。
    return {
        "code": status.HTTP_200_OK,
        "message": "验证码已发送",
    }


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """验证邮箱验证码并创建用户。"""

    user = await register_user(
        db,
        redis,
        username=data.username,
        email=str(data.email),
        password=data.password,
        code=data.code,
        client_ip=client_ip(request),
    )

    return {
        "code": status.HTTP_201_CREATED,
        "message": "注册成功",
        "data": {
            # UserOut 确保 password_hash 等敏感字段不会进入响应。
            "user": UserOut.model_validate(user).model_dump(
                mode="json"
            ),
        },
    }


@router.post("/login")
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """使用邮箱和密码登录。"""

    auth_data = await login_user(
        db,
        redis,
        email=str(data.email),
        password=data.password,
        client_ip=client_ip(request),
    )

    return {
        "code": status.HTTP_200_OK,
        "message": "登录成功",
        "data": auth_data.model_dump(mode="json"),
    }


@router.post("/refresh")
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """原子轮换 Access 和 Refresh Token。"""
    tokens = await refresh_tokens(
        db,
        redis,
        refresh_token=data.refresh_token,
    )

    return {
        "code": status.HTTP_200_OK,
        "message": "Token 已刷新",
        "data": tokens.model_dump(mode="json"),
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    """撤销当前登录会话。"""

    # 正常情况下 get_current_user 已经验证过凭据，这里做最终防御检查。
    if credentials is None or not credentials.credentials:
        raise invalid_access_token()

    await logout_user(
        redis,
        user_id=current_user.id,
        access_token=credentials.credentials,
    )

    return {
        "code": status.HTTP_200_OK,
        "message": "登出成功",
    }


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """返回当前登录用户的公开资料。"""

    return {
        "code": status.HTTP_200_OK,
        "data": UserOut.model_validate(current_user).model_dump(
            mode="json"
        ),
    }
