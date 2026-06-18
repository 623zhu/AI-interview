from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set[str]] = {}

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        if key not in self.values and key not in self.ttls and key not in self.sets:
            return -2
        return self.ttls.get(key, -1)

    async def get(self, key: str):
        return self.values.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self.values[key] = str(value)
        self.ttls[key] = seconds
        return True

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values or key in self.ttls or key in self.sets:
                deleted += 1
            self.values.pop(key, None)
            self.ttls.pop(key, None)
            self.sets.pop(key, None)
        return deleted

    async def keys(self, pattern: str):
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [key for key in self.values if key.startswith(prefix)]
        return [key for key in self.values if key == pattern]

    async def sadd(self, key: str, *values: str) -> int:
        members = self.sets.setdefault(key, set())
        before = len(members)
        members.update(str(value) for value in values)
        return len(members) - before

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def srem(self, key: str, *values: str) -> int:
        members = self.sets.get(key)
        if not members:
            return 0

        removed = 0
        for value in values:
            if str(value) in members:
                members.remove(str(value))
                removed += 1
        return removed


@pytest.fixture
def fake_redis():
    return FakeRedis()
