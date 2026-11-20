"""Хранилище состояния и накопленных данных записи для каждого пользователя.

Есть две реализации одного интерфейса — все методы асинхронные, чтобы Redis-версия
(которая делает сетевые вызовы) и in-memory версия были взаимозаменяемы:

1. InMemoryBookingStorage — словарь в памяти. Подходит для одного процесса бота
   (long polling). Состояние живёт, пока процесс работает.

2. RedisBookingStorage — то же самое, но поверх Redis. Нужен для webhook-режима:
   FastAPI может обслуживать запросы несколькими воркерами, и состояние пользователя
   должно быть доступно из любого воркера, а также переживать перезапуск.
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from redis.asyncio import Redis

from app.bot.states import BookingState


@dataclass
class BookingContext:
    """Накопленные данные записи: заполняются по мере прохождения цепочки."""

    state: BookingState = BookingState.START
    client_id: int | None = None
    service_id: int | None = None
    master_id: int | None = None
    day: str | None = None  # ISO-дата (YYYY-MM-DD)


class BookingStorage(Protocol):
    """Общий интерфейс хранилищ состояния диалога (все методы — асинхронные)."""

    async def get_state(self, user_id: int) -> BookingState: ...

    async def set_state(self, user_id: int, state: BookingState) -> None: ...

    async def get_context(self, user_id: int) -> BookingContext: ...

    async def save(self, user_id: int, **fields: Any) -> None: ...

    async def reset(self, user_id: int) -> None: ...


class InMemoryBookingStorage:
    """In-memory хранилище: словарь user_id -> BookingContext.

    Методы объявлены async для единообразия с Redis-версией, но внутри обращаются к
    обычному словарю без ожиданий реального I/O.
    """

    def __init__(self) -> None:
        self._data: dict[int, BookingContext] = {}

    async def get_state(self, user_id: int) -> BookingState:
        ctx = self._data.get(user_id)
        return ctx.state if ctx is not None else BookingState.START

    async def set_state(self, user_id: int, state: BookingState) -> None:
        self._ensure(user_id).state = state

    async def get_context(self, user_id: int) -> BookingContext:
        return self._ensure(user_id)

    async def save(self, user_id: int, **fields: Any) -> None:
        """Обновить одно или несколько полей контекста записи."""
        ctx = self._ensure(user_id)
        for name, value in fields.items():
            setattr(ctx, name, value)

    async def reset(self, user_id: int) -> None:
        """Сбросить диалог: state -> START и все накопленные данные очищаются."""
        self._data[user_id] = BookingContext(state=BookingState.START)

    def _ensure(self, user_id: int) -> BookingContext:
        """Вернуть контекст пользователя, создав его при отсутствии."""
        if user_id not in self._data:
            self._data[user_id] = BookingContext()
        return self._data[user_id]


class RedisBookingStorage:
    """Хранилище состояния диалога в Redis (для webhook с несколькими воркерами).

    Каждый пользователь — один ключ вида `booking:{user_id}`, значение — контекст
    BookingContext, сериализованный в JSON.
    """

    def __init__(self, redis: Redis, key_prefix: str = "booking") -> None:
        self._redis = redis
        self._prefix = key_prefix

    def _key(self, user_id: int) -> str:
        """Redis-ключ для хранения контекста пользователя."""
        return f"{self._prefix}:{user_id}"

    async def get_state(self, user_id: int) -> BookingState:
        ctx = await self.get_context(user_id)
        return ctx.state

    async def set_state(self, user_id: int, state: BookingState) -> None:
        ctx = await self.get_context(user_id)
        ctx.state = state
        await self._write(user_id, ctx)

    async def get_context(self, user_id: int) -> BookingContext:
        raw = await self._redis.get(self._key(user_id))
        if raw is None:
            return BookingContext()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return self._deserialize(text)

    async def save(self, user_id: int, **fields: Any) -> None:
        """Обновить одно или несколько полей контекста записи и сохранить в Redis."""
        ctx = await self.get_context(user_id)
        for name, value in fields.items():
            setattr(ctx, name, value)
        await self._write(user_id, ctx)

    async def reset(self, user_id: int) -> None:
        """Сбросить диалог до начального состояния и сохранить в Redis."""
        await self._redis.set(self._key(user_id), self._serialize(BookingContext()))

    async def _write(self, user_id: int, ctx: BookingContext) -> None:
        """Сериализовать контекст и записать его в Redis."""
        await self._redis.set(self._key(user_id), self._serialize(ctx))

    @staticmethod
    def _serialize(ctx: BookingContext) -> str:
        """Сериализовать контекст записи в JSON-строку."""
        return json.dumps(
            {
                "state": ctx.state.value,
                "client_id": ctx.client_id,
                "service_id": ctx.service_id,
                "master_id": ctx.master_id,
                "day": ctx.day,
            }
        )

    @staticmethod
    def _deserialize(raw: str) -> BookingContext:
        """Восстановить BookingContext из JSON-строки."""
        data: dict = json.loads(raw)
        return BookingContext(
            state=BookingState(data.get("state", BookingState.START.value)),
            client_id=data.get("client_id"),
            service_id=data.get("service_id"),
            master_id=data.get("master_id"),
            day=data.get("day"),
        )


# Единый экземпляр на процесс бота (long polling). В webhook-версии используется
# RedisBookingStorage, создаваемый в lifespan FastAPI.
storage: BookingStorage = InMemoryBookingStorage()
