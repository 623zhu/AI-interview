"""Authentication endpoints: register, login, refresh, logout, send code."""
import random

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, security_scheme
from fastapi.security import HTTPAuthorizationCredentials
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_token_jti,
)
from app.models.user import User
from app.schemas.auth import (
    SendCodeRequest, RegisterRequest, UserLogin, UserOut,
    TokenResponse, RefreshRequest, AuthResponse,
)
from app.utils.email import send_verification_code

router = APIRouter()


@router.post("/send-code")
async def send_code(
    data: SendCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """Send verification code to email. Cooldown: 60s per email."""
    email = data.email

    # Check cooldown (60s)
    cooldown = await redis.get(f"email_cooldown:{email}")
    if cooldown:
        raise HTTPException(status_code=429, detail="发送过于频繁，请60秒后再试")

    # Generate 6-digit random code
    code = "".join(random.choices("0123456789", k=6))

    # Send email
    try:
        await send_verification_code(email, code)
    except Exception:
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")

    # Store code in Redis with 5min TTL, set cooldown
    await redis.setex(f"email_code:{email}", 300, code)
    await redis.setex(f"email_cooldown:{email}", 60, "1")

    return {"code": 200, "message": "验证码已发送"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Register a new user with email verification code."""
    # Verify email code
    stored_code = await redis.get(f"email_code:{data.email}")
    if not stored_code or stored_code != data.code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # Delete the code so it can't be reused
    await redis.delete(f"email_code:{data.email}")

    # Check username
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")

    # Check email
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="邮箱已被注册")

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return {
        "code": 201,
        "message": "注册成功",
        "data": {
            "user": UserOut.model_validate(user).model_dump()
        }
    }


@router.post("/login")
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Login with email and password."""
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")

    # Create tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Store refresh token in Redis
    jti = get_token_jti(refresh_token)
    if jti:
        await redis.setex(
            f"refresh_token:{jti}",
            7 * 24 * 3600,  # 7 days
            user.id
        )

    return {
        "code": 200,
        "message": "登录成功",
        "data": AuthResponse(
            user=UserOut.model_validate(user),
            tokens=TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=3600,
            ),
        ).model_dump()
    }


@router.post("/refresh")
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Refresh access token using refresh token."""
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="无效的刷新令牌")
    except Exception:
        raise HTTPException(status_code=401, detail="无效的刷新令牌")

    jti = payload.get("jti")
    user_id = payload.get("sub")

    # Check if refresh token is in Redis (not revoked)
    stored = await redis.get(f"refresh_token:{jti}")
    if not stored:
        raise HTTPException(status_code=401, detail="刷新令牌已失效")

    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    # Revoke old refresh token
    await redis.delete(f"refresh_token:{jti}")

    # Create new tokens
    new_access = create_access_token(subject=user.id)
    new_refresh = create_refresh_token(subject=user.id)

    new_jti = get_token_jti(new_refresh)
    if new_jti:
        await redis.setex(f"refresh_token:{new_jti}", 7 * 24 * 3600, user.id)

    return {
        "code": 200,
        "message": "Token刷新成功",
        "data": TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_in=3600,
        ).model_dump()
    }


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    redis: Redis = Depends(get_redis),
):
    """Logout: blacklist current access token JTI and revoke refresh tokens."""
    # Blacklist current access token JTI
    token = credentials.credentials
    jti = get_token_jti(token)
    if jti:
        # Get remaining TTL from the token to set blacklist TTL
        try:
            from datetime import datetime, timezone
            payload = decode_token(token)
            exp = payload.get("exp", 0)
            now = int(datetime.now(timezone.utc).timestamp())
            ttl = max(exp - now, 1) if exp else 3600
            await redis.setex(f"blacklist:{jti}", ttl, "1")
        except Exception:
            await redis.setex(f"blacklist:{jti}", 3600, "1")

    # Revoke all refresh tokens for this user
    try:
        keys = await redis.keys(f"refresh_token:*")
        for key in keys:
            stored_user = await redis.get(key)
            if stored_user == current_user.id:
                await redis.delete(key)
    except Exception:
        pass

    return {"code": 200, "message": "登出成功"}


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """Get current user info."""
    return {
        "code": 200,
        "data": UserOut.model_validate(current_user).model_dump()
    }
