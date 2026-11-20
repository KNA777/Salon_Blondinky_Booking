import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import main_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.exceptions import (
    InvalidTransitionError,
    NotFoundError,
    PermissionError,
    SlotConflictError,
)
from app.core.logging import (
    bind_trace_id,
    configure_logging,
    get_logger,
    new_trace_id,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Код до `yield` выполняется при старте приложения, после `yield` — при остановке."""
    settings = get_settings()
    configure_logging(settings)
    logger.info("🚀 Запуск приложения: инициализация ресурсов...")

    # --- База данных ---
    logger.info("Подключение к базе данных: %s", settings.database_url)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("✅ Пул соединений с БД создан.")

    # --- Redis ---
    logger.info("Подключение к Redis: %s:%s", settings.redis_host, settings.redis_port)
    app.state.redis = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
    )
    logger.info("✅ Клиент Redis создан.")

    # --- Бот и Dispatcher ---
    app.state.bot = None
    app.state.dispatcher = None

    if settings.use_webhook:
        logger.info("Режим webhook включён. Настройка бота и вебхука...")
        try:
            await _setup_webhook(app, settings)
            logger.info("✅ Бот и Dispatcher успешно инициализированы.")
            logger.info("🌐 Webhook URL: %s", settings.webhook_url)
        except Exception as e:
            logger.exception("❌ Ошибка при настройке webhook: %s", e)
            raise  # Пробрасываем ошибку, чтобы приложение не запустилось в нерабочем состоянии
    else:
        logger.info("Режим webhook отключён (use_webhook=False). Бот не будет запущен в FastAPI.")

    # --- Напоминания о записи ---
    # Background-таск рассылки напоминаний (задача 13). Нужен экземпляр бота, поэтому
    # запускаем только в webhook-режиме (в polling-режиме свой таск в app/bot/__main__.py).
    app.state.reminder_stop = None
    app.state.reminder_task = None
    if app.state.bot is not None:
        from app.services.reminders import reminder_loop

        app.state.reminder_stop = asyncio.Event()
        app.state.reminder_task = asyncio.create_task(
            reminder_loop(app.state.session_factory, app.state.bot, app.state.reminder_stop)
        )
        logger.info("✅ Планировщик напоминаний запущен.")

    logger.info("🎉 Приложение готово к работе.")
    yield

    # --- Остановка ---
    logger.info("🛑 Остановка приложения: освобождение ресурсов...")

    # Останавливаем планировщик напоминаний (если он был запущен).
    if app.state.reminder_task is not None:
        app.state.reminder_stop.set()
        app.state.reminder_task.cancel()
        try:
            await app.state.reminder_task
        except asyncio.CancelledError:
            pass
        logger.info("✅ Планировщик напоминаний остановлен.")

    if app.state.bot is not None:
        logger.info("Закрытие сессии бота...")
        await app.state.bot.session.close()
        logger.info("✅ Сессия бота закрыта.")

    logger.info("Закрытие клиента Redis...")
    await app.state.redis.aclose()
    logger.info("✅ Клиент Redis закрыт.")

    logger.info("Освобождение пула соединений с БД...")
    await engine.dispose()
    logger.info("✅ Пул соединений с БД освобождён.")

    logger.info("👋 Приложение остановлено.")


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


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Помечает каждый запрос уникальным trace_id и кладёт его в контекст structlog.

    trace_id связывает все логи одного запроса (и вложенные вызовы) в единый след,
    по которому его легко найти и в Sentry, и в JSON-логах. Значение также пробрасывается
    обратно в заголовке X-Trace-Id, чтобы клиент мог сообщить его в баг-репорте.
    """
    trace_id = new_trace_id()
    bind_trace_id(trace_id)
    request.state.trace_id = trace_id

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Необработанное исключение при обработке запроса", trace_id=trace_id)
        raise

    response.headers["X-Trace-Id"] = trace_id
    return response


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
async def slot_conflict_exception_handler(request: Request, exc: SlotConflictError) -> JSONResponse:
    """Занятый слот (двойная запись) -> HTTP 409 Conflict."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
async def permission_exception_handler(request: Request, exc: PermissionError) -> JSONResponse:
    """Попытка управлять чужой записью без прав -> HTTP 403 Forbidden."""
    return JSONResponse(status_code=403, content={"detail": str(exc)})


app.include_router(health_router)
app.include_router(main_router)

# --- Mini App (задача 17) ---
# Статический фронтенд Telegram Mini App: выбор услуги -> мастера -> даты -> слота.
# Отдаётся как обычная страница; аутентификация идёт через /auth/telegram (валидация initData),
# а данные — через существующие REST-эндпоинты (services/masters/free-slots/appointments).
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/mini-app", include_in_schema=False)
async def mini_app() -> FileResponse:
    """Отдаёт HTML-страницу Mini App (фронтенд записи клиента)."""
    return FileResponse(_STATIC_DIR / "mini-app.html")


@app.get("/admin", include_in_schema=False)
async def admin_panel() -> FileResponse:
    """Отдаёт HTML-страницу админ-панели (задача 14).

    Сама страница статичная: вся работа идёт через существующие REST-эндпоинты
    (вход — /auth/admin/login с httpOnly cookie, данные — /appointments, /masters,
    /services). Доступ к данным защищён на уровне API (зависимость get_current_admin).
    """
    return FileResponse(_STATIC_DIR / "admin.html")
