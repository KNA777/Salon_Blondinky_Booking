"""Webhook-эндпоинт Telegram-бота.

Вместо long polling бот может принимать апдейты через webhook: Telegram POST-запросом
присылает обновления на этот эндпоинт, а мы передаём их Dispatcher'у aiogram.

Безопасность: запросы подписываются секретом в заголовке X-Telegram-Bot-Api-Secret-Token.
Без валидного секрета отвечаем 403 — это защищает от поддельных запросов к боту.
"""

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["Webhook"])

# Имя заголовка, которым Telegram подписывает webhook-запросы (см. setWebhook secret_token).
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class WebhookResponse(BaseModel):
    ok: bool = True


def _secret_matches(provided: str | None, expected: str | None) -> bool:
    """Сравнивает секрет, пришедший в заголовке, с ожидаемым.

    Простое == допустимо: секрет не пароль пользователя, а случайная строка для подписи
    запросов Telegram. Сравниваем безопасно (обе строки в str) и требуем совпадения.
    """
    if expected is None:
        return False
    return provided == expected


@router.post("/webhook/bot", response_model=WebhookResponse)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias=SECRET_HEADER),
) -> WebhookResponse:
    """Принимает апдейт от Telegram и передаёт его Dispatcher'у бота.

    Dispatcher и Bot создаются в lifespan (см. main.py) и лежат в app.state.
    Если webhook не настроен (нет токена/секрета) — 503, если секрет неверен — 403.
    """
    settings = get_settings()

    if not _secret_matches(x_telegram_bot_api_secret_token, settings.webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret",
        )

    bot = getattr(request.app.state, "bot", None)
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if bot is None or dispatcher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot is not configured for webhook",
        )

    # Тело запроса — это Update в формате Telegram Bot API. Передаём его Dispatcher'у,
    # который разберёт его и запустит нужный хендлер.
    update = await request.json()
    await dispatcher.feed_webhook_update(bot, update)

    return WebhookResponse()
