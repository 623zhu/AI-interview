"""认证业务服务：编排验证码、用户数据和安全组件。"""
"""认证业务服务：编排验证码、用户数据和安全组件。"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from jose import JWTError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import (
    RateLimit,
    check_rate_limit,
    ensure_not_locked,
    increment_with_ttl,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import (
    UserConflicts,
    create_user,
    email_exists,
    find_user_conflicts,
    get_user_by_email,
    get_user_by_id,
)
from app.schemas.auth import AuthData, TokenPair, UserOut
from app.services.token_service import (
    block_access_token,
    revoke_user_refresh_tokens,
    rotate_refresh_token,
    store_refresh_token,
)
from app.services.verification_service import (
    consume_registration_code,
    issue_registration_code,
)
REGISTER_IP_LIMIT = RateLimit(
    limit=20,
    window_seconds=3600,
    message="注册请求过于频繁",
)
LOGIN_IP_LIMIT = RateLimit(
    limit=30,
    window_seconds=300,
    message="登录请求过于频繁",
)
LOGIN_EMAIL_LIMIT = RateLimit(
    limit=10,
    window_seconds=300,
    message="该邮箱登录请求过于频繁",
)

LOGIN_FAILURE_WINDOW = 900
LOGIN_LOCK_SECONDS = 900
LOGIN_FAILURE_LIMIT = 5


def _auth_state_unavailable() -> HTTPException:
    """Redis 等认证状态依赖不可用。"""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "auth_state_unavailable",
            "message": "认证状态服务暂时不可用",
        },
    )


def _auth_data_unavailable() -> HTTPException:
    """MySQL 用户数据依赖不可用。"""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "auth_data_unavailable",
            "message": "用户数据服务暂时不可用",
        },
    )


def _registration_conflict(
    conflicts: UserConflicts,
) -> HTTPException:
    """将数据库唯一约束冲突转换为稳定的业务错误。"""

    if conflicts.username:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "username_already_exists",
                "message": "用户名已存在",
            },
        )

    if conflicts.email:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "email_already_registered",
                "message": "该邮箱已注册",
            },
        )

    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "registration_conflict",
            "message": "注册信息发生冲突",
        },
    )


async def send_registration_code(
    db: AsyncSession,
    redis: Redis,
    *,
    email: str,
    client_ip: str,
) -> None:
    """检查邮箱状态并发送注册验证码。"""

    normalized_email = email.strip().lower()

    try:
        registered = await email_exists(
            db,
            normalized_email,
        )
    except SQLAlchemyError as exc:
        raise _auth_data_unavailable() from exc

    try:
        await issue_registration_code(
            redis,
            email=normalized_email,
            client_ip=client_ip,
            email_registered=registered,
        )
    except RedisError as exc:
        # Redis 不可用时不能绕过限流、冷却或验证码状态。
        raise _auth_state_unavailable() from exc


async def register_user(
    db: AsyncSession,
    redis: Redis,
    *,
    username: str,
    email: str,
    password: str,
    code: str,
    client_ip: str,
) -> User:
    """验证注册码并创建用户，但不自动登录。"""

    normalized_email = email.strip().lower()

    try:
        await check_rate_limit(
            redis,
            f"aiiv2:auth:rl:register:ip:{client_ip}",
            REGISTER_IP_LIMIT,
        )
    except RedisError as exc:
        raise _auth_state_unavailable() from exc

    try:
        conflicts = await find_user_conflicts(
            db,
            username=username,
            email=normalized_email,
        )
    except SQLAlchemyError as exc:
        raise _auth_data_unavailable() from exc

    if conflicts.any:
        raise _registration_conflict(conflicts)

    try:
        # 验证码先被原子消费，确保同一个验证码不能创建两个用户。
        await consume_registration_code(
            redis,
            email=normalized_email,
            code=code,
        )
    except RedisError as exc:
        raise _auth_state_unavailable() from exc

    password_hash = await hash_password(password)

    try:
        user = await create_user(
            db,
            username=username,
            email=normalized_email,
            password_hash=password_hash,
            # MySQL DATETIME 不保存时区，统一写入无时区的 UTC 时间。
            email_verified_at=datetime.now(
                timezone.utc
            ).replace(tzinfo=None),
        )
    except IntegrityError as exc:
        # 预检查和 INSERT 之间仍可能出现并发注册，唯一约束才是最终保障。
        await db.rollback()

        try:
            conflicts = await find_user_conflicts(
                db,
                username=username,
                email=normalized_email,
            )
        except SQLAlchemyError as query_exc:
            raise _auth_data_unavailable() from query_exc

        raise _registration_conflict(conflicts) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _auth_data_unavailable() from exc

    # 提交事务由 get_db() 统一完成，Service 不提前 commit。
    return user

def _invalid_credentials() -> HTTPException:
    """统一登录失败响应，避免暴露邮箱是否存在。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_credentials",
            "message": "邮箱或密码错误",
        },
    )


def _invalid_refresh_token() -> HTTPException:
    """统一 Refresh Token 错误响应。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_refresh_token",
            "message": "刷新令牌无效或已失效",
        },
    )


def _token_pair(user_id: str) -> TokenPair:
    """为同一用户创建 Access 和 Refresh Token。"""

    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        # expires_in 使用秒，不能在接口中硬编码。
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def login_user(
    db: AsyncSession,
    redis: Redis,
    *,
    email: str,
    password: str,
    client_ip: str,
) -> AuthData:
    """验证邮箱密码，并创建登录会话。"""

    normalized_email = email.strip().lower()
    failure_key = f"aiiv2:auth:login_fail:{normalized_email}"
    lock_key = f"aiiv2:auth:login_lock:{normalized_email}"

    try:
        # 登录前同时检查 IP、邮箱频率和密码失败锁定。
        await check_rate_limit(
            redis,
            f"aiiv2:auth:rl:login:ip:{client_ip}",
            LOGIN_IP_LIMIT,
        )
        await check_rate_limit(
            redis,
            f"aiiv2:auth:rl:login:email:{normalized_email}",
            LOGIN_EMAIL_LIMIT,
        )
        await ensure_not_locked(redis, lock_key)
    except RedisError as exc:
        raise _auth_state_unavailable() from exc

    try:
        user = await get_user_by_email(
            db,
            normalized_email,
        )
    except SQLAlchemyError as exc:
        raise _auth_data_unavailable() from exc

    # 用户不存在时 verify_password 也执行虚拟 bcrypt，降低邮箱枚举风险。
    password_valid = await verify_password(
        password,
        user.password_hash if user else None,
    )

    if user is None or not password_valid:
        try:
            failures, _ = await increment_with_ttl(
                redis,
                failure_key,
                LOGIN_FAILURE_WINDOW,
            )

            # 第五次仍返回密码错误；后续请求因锁定返回 429。
            if failures >= LOGIN_FAILURE_LIMIT:
                await redis.setex(
                    lock_key,
                    LOGIN_LOCK_SECONDS,
                    "1",
                )
        except RedisError as exc:
            raise _auth_state_unavailable() from exc

        raise _invalid_credentials()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "user_disabled",
                "message": "账户已被禁用",
            },
        )

    tokens = _token_pair(user.id)

    try:
        # Refresh Token 只有登记到 Redis 后才真正有效。
        await store_refresh_token(
            redis,
            user.id,
            tokens.refresh_token,
        )
        await redis.delete(failure_key, lock_key)
    except RedisError as exc:
        raise _auth_state_unavailable() from exc

    return AuthData(
        user=UserOut.model_validate(user),
        tokens=tokens,
    )


async def refresh_tokens(
    db: AsyncSession,
    redis: Redis,
    *,
    refresh_token: str,
) -> TokenPair:
    """验证并原子轮换 Refresh Token。"""

    try:
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise JWTError("需要 Refresh Token")

        user_id = str(payload.get("sub") or "")
        old_jti = str(payload.get("jti") or "")

        if not user_id or not old_jti:
            raise JWTError("Refresh Token 缺少必要声明")
    except (JWTError, TypeError, ValueError) as exc:
        raise _invalid_refresh_token() from exc

    try:
        user = await get_user_by_id(db, user_id)
    except SQLAlchemyError as exc:
        raise _auth_data_unavailable() from exc

    # 不泄漏用户不存在、禁用或 Token 状态失效的具体原因。
    if user is None or not user.is_active:
        raise _invalid_refresh_token()

    tokens = _token_pair(user.id)

    try:
        rotated = await rotate_refresh_token(
            redis,
            user_id=user.id,
            old_jti=old_jti,
            new_token=tokens.refresh_token,
        )
    except RedisError as exc:
        raise _auth_state_unavailable() from exc
    except JWTError as exc:
        raise _invalid_refresh_token() from exc

    if not rotated:
        raise _invalid_refresh_token()

    return tokens


async def logout_user(
    redis: Redis,
    *,
    user_id: str,
    access_token: str,
) -> None:
    """撤销用户全部 Refresh Token，并拉黑当前 Access Token。"""

    try:
        # 先撤销 Refresh Token；若后续失败，当前 Access 仍可用于重试登出。
        await revoke_user_refresh_tokens(
            redis,
            user_id,
        )
        await block_access_token(
            redis,
            access_token,
        )
    except RedisError as exc:
        # 登出状态写入失败时不能假装成功。
        raise _auth_state_unavailable() from exc
    except JWTError as exc:
        raise _invalid_credentials() from exc

