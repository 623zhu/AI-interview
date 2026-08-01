"""用户数据访问层。"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass(frozen=True)
class UserConflicts:
    """注册时发生冲突的唯一字段。"""

    username: bool
    email: bool

    @property
    def any(self) -> bool:
        return self.username or self.email


async def get_user_by_id(
    db: AsyncSession,
    user_id: str,
) -> User | None:
    """根据用户 ID 查询用户。"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(
    db: AsyncSession,
    email: str,
) -> User | None:
    """根据规范化邮箱查询用户。"""

    result = await db.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def email_exists(
    db: AsyncSession,
    email: str,
) -> bool:
    """仅判断邮箱是否存在，不加载完整用户对象。"""

    result = await db.execute(
        select(
            exists().where(User.email == email)
        )
    )
    return bool(result.scalar())


async def find_user_conflicts(
    db: AsyncSession,
    *,
    username: str,
    email: str,
) -> UserConflicts:
    """在一次数据库往返中检查用户名和邮箱冲突。"""

    statement = select(
        exists()
        .where(User.username == username)
        .label("username_exists"),
        exists()
        .where(User.email == email)
        .label("email_exists"),
    )

    row = (await db.execute(statement)).one()

    # 使用数据库比较结果，正确遵循 MySQL 当前排序规则。
    return UserConflicts(
        username=bool(row.username_exists),
        email=bool(row.email_exists),
    )


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    password_hash: str,
    email_verified_at: datetime,
) -> User:
    """创建用户并刷新数据库生成的时间字段。"""

    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        email_verified_at=email_verified_at,
    )

    db.add(user)

    # flush 将 INSERT 发送到数据库，但不提交事务。
    # 唯一约束冲突会在这里抛出 IntegrityError，由 Service 层处理。
    await db.flush()
    await db.refresh(user)

    return user
