from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


async def commit_or_rollback(session: AsyncSession, operation: Callable[[], Awaitable[T]]) -> T:
    try:
        result = await operation()
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
