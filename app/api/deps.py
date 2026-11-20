from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db_context_manager import DBManager
from app.core.security import decode_token
from app.schemas.client import ClientOut


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Одна сессия БД на один HTTP-запрос.

    `async with` гарантирует, что сессия закроется, даже если в обработчике случилась ошибка.
    Фабрика сессий создаётся один раз при старте приложения (см. lifespan в main.py).
    """
    async with DBManager(request.app.state.session_factory) as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_client(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ClientOut:
    """Извлекает текущего клиента из access-токена.

    Токен берётся приоритетно из httpOnly cookie (имя из настроек cookie_name), которую
    браузер сам подставляет в каждый запрос. Фолбэк — заголовок `Authorization: Bearer
    <token>`: это нужно для API-клиентов и тестов, которые не работают с cookie.
    Проверяется подпись и срок жизни, затем по client_id загружается клиент из БД.
    При отсутствии/невалидном токене или несуществующем клиенте — HTTP 401.
    """
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)

    # Фолбэк на Bearer-заголовок, если cookie нет (API-клиенты, тесты).
    if not token and authorization is not None and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_id = decode_token(token)
    if client_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_factory = request.app.state.session_factory
    async with DBManager(session_factory) as db:
        client = await db.clients.get_one_by_id(id=client_id)

    return client


async def get_current_admin(
    current_client: Annotated[ClientOut, Depends(get_current_client)],
) -> ClientOut:
    """Требует, чтобы текущий клиент был администратором (is_admin=True).

    Строится поверх get_current_client: сначала восстанавливаем клиента по JWT, затем
    проверяем флаг. Не-админу отвечаем HTTP 403. Используется для админ-эндпоинтов
    (задачи 14, 16).
    """
    if not current_client.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return current_client


# Annotated-алиасы: в обработчиках пишем `session: SessionDep` вместо длинного Depends(...).
# Заодно в тестах эти зависимости легко подменить (см. tests/test_health.py).
DBDep = Annotated[DBManager, Depends(get_session)]

RedisDep = Annotated[Redis, Depends(get_redis)]

CurrentClientDep = Annotated[ClientOut, Depends(get_current_client)]

CurrentAdminDep = Annotated[ClientOut, Depends(get_current_admin)]
