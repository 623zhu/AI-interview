"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


#数据库连接的总管
engine = create_async_engine(
    settings.DATABASE_URL,      # 用配置里的异步连接串,如 mysql+asyncmy://...
    echo=settings.DEBUG,        # DEBUG 时打印所有 SQL 语句
    pool_pre_ping=True,         # 用连接前先 ping 一下,确认没断
    pool_size=10,               # 连接池常驻 10 个连接
    max_overflow=20,            # 高峰时最多再临时加 20 个
)

async_session_factory = async_sessionmaker(
    bind=engine,                  # 绑定到上面的引擎
    class_=AsyncSession,          # 生产的是异步会话
    expire_on_commit=False,       # commit 后对象不失效
)



class Base(DeclarativeBase):
    """ 所有数据模型的基类 所有数据模型的基类"""


async def get_db() -> AsyncIterator[AsyncSession]:
    """Provide one transactional session for a request."""

    async with async_session_factory() as session:   # 开一个 session
        try:
            yield session                              # 交给接口使用
            await session.commit()                     # 接口正常结束 → 提交
        except Exception:
            await session.rollback()                   # 出错了 → 回滚
            raise                                      # 把异常继续抛出

async def close_database() -> None:
    """Release all pooled database connections."""
    await engine.dispose()
