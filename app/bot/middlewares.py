"""Middleware, открывающий сессию БД на время обработки одного апдейта.

Бот — отдельный процесс от FastAPI, поэтому у него своя сессия БД (без общего lifespan).
На каждый апдейт открывается свой DBManager, который закрывается после обработки, даже
если хендлер упал. Хендлеры получают `db: DBManager` как именованный аргумент.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.storage import BookingStorage
from app.core.db_context_manager import DBManager


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with DBManager(self.session_factory) as db_manager:
            data["db"] = db_manager
            return await handler(event, data)


class StorageMiddleware(BaseMiddleware):
    """Подставляет активное хранилище FSM-состояний в `data["storage"]`.

    В polling хранилище — in-memory, в webhook — Redis (одинаковый интерфейс),
    поэтому хендлеры не знают, какая реализация используется.
    """

    def __init__(self, storage: BookingStorage) -> None:
        self.storage = storage

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["storage"] = self.storage
        return await handler(event, data)
