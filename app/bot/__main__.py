"""Точка входа бота: python -m app.bot

Бот запускается отдельно от FastAPI. Он берёт токен из настроек (env-переменная BOT_TOKEN),
создаёт сам объект Bot/Dispatcher и уходит в aiogram.polling.

БД нужна боту для сценария записи (список услуг, мастера, создание записи), поэтому здесь
создаётся свой async engine и sessionmaker; на каждый апдейт middleware открывает сессию.
"""

import asyncio
import sys
from pathlib import Path

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Корень проекта должен быть в sys.path, чтобы импорт `from app.*` работал при любом
# способе запуска: и `python -m app.bot` (из корня), и `python app/bot/__main__.py`
# (когда Python кладёт в sys.path каталог app/bot вместо корня). Без этой страховки
# во втором случае вылетает `ModuleNotFoundError: No module named 'app'`.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.bot.dispatcher import build_dispatcher  # noqa: E402
from app.bot.storage import InMemoryBookingStorage  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def require_token(token: str | None) -> str:
    """Возвращает токен или падает сразу с понятной подсказкой.

    Отдельная функция, чтобы её можно было тестировать без сети и Telegram.
    """
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Получите токен у @BotFather и добавьте в .env: BOT_TOKEN=..."
        )
    return token


async def main() -> None:
    settings = get_settings()
    token = require_token(settings.bot_token)

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(token=token)
    # В polling-режиме состояние диалога хранится в памяти (один процесс).
    dp = build_dispatcher(bot, session_factory, InMemoryBookingStorage())

    # Простое long polling. Пропускать уже накопившиеся апдейты, чтобы после долгого простоя
    # бот не обрабатывал старые сообщения.
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
