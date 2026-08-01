"""FastAPI 鉴权依赖。"""

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jose import JWTError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.user import User
from app.services.token_service import is_access_token_blocked
from app.repositories.user_repository import get_user_by_id

# auto_error=False 让我们统一返回项目约定的错误结构。
bearer_scheme = HTTPBearer(auto_error=False)

def invalid_access_token() -> HTTPException:
    """构造统一的 Access Token 认证错误。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_access_token",
            "message": "无法验证访问凭据",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    """验证 Access Token，并加载当前启用用户。"""

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise invalid_access_token()

    try:
        payload = decode_token(credentials.credentials)

        # Refresh Token 不能作为 Bearer Token 访问业务接口。
        if payload.get("type") != "access":
            raise JWTError("Bearer Token 必须是 Access Token")

        user_id = str(payload.get("sub") or "")
        jti = str(payload.get("jti") or "")

        if not user_id or not jti:
            raise JWTError("Token 缺少用户 ID 或 JTI")
    except (JWTError, TypeError, ValueError) as exc:
        raise invalid_access_token() from exc

    try:
        # Redis 不可用时必须失败关闭，不能绕过登出黑名单。
        blocked = await is_access_token_blocked(
            redis,
            jti,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_state_unavailable",
                "message": "认证状态服务暂时不可用",
            },
        ) from exc

    if blocked:
        raise invalid_access_token()

    try:
        user = await get_user_by_id(db, user_id)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_data_unavailable",
                "message": "用户数据服务暂时不可用",
            },
        ) from exc

    # 用户不存在与 Token 无效使用相同响应，避免泄漏账号状态。
    if user is None:
        raise invalid_access_token()

    # 禁用状态必须每次从数据库读取，不能只相信 JWT 中的旧状态。
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "user_disabled",
                "message": "账户已被禁用",
            },
        )

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求当前用户具有管理员权限。"""

    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_required",
                "message": "需要管理员权限",
            },
        )

    return current_user
