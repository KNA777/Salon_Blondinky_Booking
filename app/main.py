from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import main_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import InvalidTransitionError, NotFoundError, SlotConflictError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Код до `yield` выполняется при старте приложения, после `yield` — при остановке.

    Тяжёлые объекты (пул соединений с БД, клиент Redis) создаём один раз здесь,
    а не на каждый запрос: соединения дорого открывать, их нужно переиспользовать.
    """
    settings = get_settings()

    # pool_pre_ping: перед выдачей соединения из пула проверяет, что оно живое.
    # Без этого после перезапуска Postgres первый запрос упал бы на «мёртвом» соединении.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    # expire_on_commit=False: после commit объекты остаются доступны.
    # В async-коде обращение к «протухшему» объекту вызвало бы скрытый запрос в БД и ошибку.
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,  # получаем строки (str), а не байты
    )

    # Webhook-режим: если задан webhook_url и токен, поднимаем Dispatcher внутри FastAPI.
    # Состояние FSM при этом хранится в Redis (см. RedisBookingStorage) — оно должно быть
    # доступно из любого воркера, а не только из одного процесса.
    app.state.bot = None
    app.state.dispatcher = None
    if settings.use_webhook:
        await _setup_webhook(app, settings)

    yield

    if app.state.bot is not None:
        await app.state.bot.session.close()
    await app.state.redis.aclose()
    await engine.dispose()


async def _setup_webhook(app: FastAPI, settings) -> None:
    """Собирает Bot + Dispatcher для webhook-режима и кладёт их в app.state."""
    from aiogram import Bot

    from app.bot.dispatcher import build_dispatcher
    from app.bot.storage import RedisBookingStorage

    session_factory = app.state.session_factory
    storage = RedisBookingStorage(app.state.redis)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher(bot, session_factory, storage)

    app.state.bot = bot
    app.state.dispatcher = dispatcher
    app.state.webhook_storage = storage


app = FastAPI(title="Salon Booking", lifespan=lifespan)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Превращает «объект не найден» в HTTP 404, а не в 500."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_exception_handler(
    request: Request, exc: InvalidTransitionError
) -> JSONResponse:
    """Запрещённый переход статуса -> HTTP 409 Conflict."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(SlotConflictError)
async def slot_conflict_exception_handler(
    request: Request, exc: SlotConflictError
) -> JSONResponse:
    """Занятый слот (двойная запись) -> HTTP 409 Conflict."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(health_router)
app.include_router(main_router)
