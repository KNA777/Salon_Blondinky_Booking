"""Точка входа бота: python -m app.bot

Бот запускается отдельно от FastAPI. Он берёт токен из настроек (env-переменная BOT_TOKEN),
создаёт сам объект Bot/Dispatcher и уходит в aiogram.polling.

БД боту понадобится на следующих шагах (список услуг, запись клиента). Сейчас он к ней не
обращается, поэтому достаточно Bot + Dispatcher; сессию БД подключим, когда появится логика.
"""

import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.core.config import get_settings


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

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)

    # Простое long polling. Пропускать уже накопившиеся апдейты, чтобы после долгого простоя
    # бот не обрабатывал старые сообщения.
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
