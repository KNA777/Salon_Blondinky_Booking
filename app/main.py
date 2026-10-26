from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import main_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import NotFoundError


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

    yield

    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title="Salon Booking", lifespan=lifespan)


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Превращает «объект не найден» в HTTP 404, а не в 500."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


app.include_router(health_router)
app.include_router(main_router)
