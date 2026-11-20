"""Структурированное логирование (structlog) и отслеживание ошибок (Sentry) — задача 27.

Единая точка настройки логирования для всего приложения (FastAPI + бот). structlog
собирает события в JSON (или красивый текстовый формат для локальной разработки), а
Sentry перехватывает необработанные исключения и записывает их в проект мониторинга.

Ключевые идеи:
- Каждый запрос получает trace_id, по которому события из одного запроса/цепочки вызовов
  связываются в Sentry и логах.
- Sentry опционален: без SENTRY_DSN приложение работает как обычно, логи остаются structlog.
- Одна функция configure_logging() вызывается в lifespan FastAPI и в точке входа бота.
"""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

import structlog

from app.core.config import Settings

# Начальная настройка: до вызова configure_logging() structlog молча падает в пустоту.
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso")],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)


def configure_logging(settings: Settings) -> None:
    """Инициализирует structlog и (опционально) Sentry.

    Должна вызываться один раз на процесс — в lifespan FastAPI (main.py) и в main()
    бота (app/bot/__main__.py). Настройка идемпотентна: повторный вызов перезапишет
    предыдущую конфигурацию, но порт при этом не сломает.

    settings — объект настроек (из get_settings()), из него берём SENTRY_DSN / APP_ENV.
    """
    # --- structlog ---
    # В dev пишем человекочитаемо; в prod — JSON для машинной обработки (логи-коллекторы).
    if settings.app_env == "prod":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
        log_level = logging.INFO
    else:
        renderer = structlog.dev.ConsoleRenderer()
        log_level = logging.INFO

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            # Добавляем имя логгера к каждому событию.
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Используем structlog как стандартный logging: так библиотеки (sqlalchemy, uvicorn,
    # aiogram), которые пишут через logging.*, тоже попадают в один поток событий.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
    structlog.stdlib.recreate_defaults()

    # --- Sentry ---
    if settings.sentry_dsn:
        _init_sentry(settings)


def _init_sentry(settings: Settings) -> None:
    """Включает Sentry, если задан SENTRY_DSN.

    Импорт и инициализация отложены внутрь функции, чтобы модуль логирования не тянул
    sentry-sdk при каждом импорте (а только когда DSN реально задан). Это важно для
    тестов и сред без Sentry — там библиотека не должна падать при импорте.
    """
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        # Для FastAPI привязка к ASGI-запросу даёт подробный контекст (URL, статус).
        enable_tracing=True,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Не шлём в Sentry события уровня ниже WARNING — событий слишком много.
        send_default_pii=False,
    )


def new_trace_id() -> str:
    """Генерирует уникальный trace_id для одного запроса/цепочки вызовов.

    Используется middleware'ом FastAPI, чтобы пометить все логи одного запроса. Формат —
    короткий UUID (8 hex-символов): читаемый, но с достаточной энтропией.
    """
    return uuid.uuid4().hex[:8]


def bind_trace_id(trace_id: str) -> None:
    """Кладёт trace_id в контекст structlog для текущего запроса.

    После этого все созданные логгеры внутри обработчика автоматически подмешают
    trace_id в каждое событие. Вызывается в middleware в начале и сбрасывается в конце.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=trace_id)


def get_logger(name: str) -> Any:
    """Возвращает structlog-логгер с заданным именем модуля.

    Предпочтительный способ получить логгер в коде: `logger = get_logger(__name__)`.
    Возвращаемый объект совместим по интерфейсу с logging.Logger (методы info/warning/
    error/exception и т.д.), поэтому код, написанный под старый logging, работает.
    """
    return structlog.get_logger(name)
