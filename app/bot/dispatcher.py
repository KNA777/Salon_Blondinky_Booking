"""Сборка Bot + Dispatcher, общая для polling (`__main__.py`) и webhook (FastAPI).

И polling, и webhook используют один и тот же набор роутеров и middleware — разница только
в способе доставки апдейтов. Здесь делается эта общая часть, чтобы не дублировать
конфигурацию Dispatcher в двух местах.
"""

from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.handlers import router
from app.bot.middlewares import DbSessionMiddleware, StorageMiddleware
from app.bot.storage import BookingStorage


def build_dispatcher(
    bot: Bot,
    session_factory: async_sessionmaker,
    storage: BookingStorage,
) -> Dispatcher:
    """Собирает Dispatcher: роутеры + middleware (БД и FSM-хранилище)."""
    dp = Dispatcher()
    dp.include_router(router)
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.update.middleware(StorageMiddleware(storage))
    return dp
