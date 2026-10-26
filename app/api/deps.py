from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_context_manager import DBManager


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Одна сессия БД на один HTTP-запрос.

    `async with` гарантирует, что сессия закроется, даже если в обработчике случилась ошибка.
    Фабрика сессий создаётся один раз при старте приложения (см. lifespan в main.py).
    """
    async with DBManager(request.app.state.session_factory) as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


# Annotated-алиасы: в обработчиках пишем `session: SessionDep` вместо длинного Depends(...).
# Заодно в тестах эти зависимости легко подменить (см. tests/test_health.py).
DBDep = Annotated[DBManager, Depends(get_session)]

RedisDep = Annotated[Redis, Depends(get_redis)]
