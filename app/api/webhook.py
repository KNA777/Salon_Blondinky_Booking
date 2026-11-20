"""Webhook-эндпоинт Telegram-бота.

Вместо long polling бот может принимать апдейты через webhook: Telegram POST-запросом
присылает обновления на этот эндпоинт, а мы передаём их Dispatcher'у aiogram.

Безопасность: запросы подписываются секретом в заголовке X-Telegram-Bot-Api-Secret-Token.
Без валидного секрета отвечаем 403 — это защищает от поддельных запросов к боту.
"""

import hmac

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["Webhook"])

# Имя заголовка, которым Telegram подписывает webhook-запросы (см. setWebhook secret_token).
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

# Префикс Redis-ключей дедупликации update_id. Ключ живёт 24 часа — за это время Telegram
# гарантированно перестаёт повторять конкретный апдейт (он хранит неподтверждённые апдейты
# ограниченное время и повторит не позднее этого окна).
UPDATE_ID_KEY_PREFIX = "webhook:update_id"
UPDATE_ID_TTL_SECONDS = 24 * 60 * 60


class WebhookResponse(BaseModel):
    ok: bool = True


def _secret_matches(provided: str | None, expected: str | None) -> bool:
    """Сравнивает секрет, пришедший в заголовке, с ожидаемым (constant-time).

    Секрет — это криптографическая строка, которой Telegram подписывает webhook-запросы,
    поэтому сравниваем её через hmac.compare_digest: сравнение выполняется за одинаковое
    время независимо от того, где именно строки расходятся. Обычное `==` давало бы
    утечку через timing-атаку (злоумышленник мог бы подбирать секрет посимвольно).
    Если ожидаемый секрет не настроен, любой входящий считается неверным.
    """
    if expected is None or provided is None:
        return False
    return hmac.compare_digest(provided, expected)


def _extract_update_id(update: dict) -> int | None:
    """Достаёт update_id из тела апдейта Telegram (если оно похоже на Update)."""
    return update.get("update_id") if isinstance(update, dict) else None


async def _is_duplicate(redis, update_id: int | None) -> bool:
    """True, если этот update_id уже обработан (повторный вебхук от Telegram).

    Используем атомарный SET ... NX EX в Redis: он возвращает False, если ключ уже
    существует, и True, если ключ записан впервые. Тем самым даже параллельные/повторные
    вебхуки с одинаковым update_id обработаются ровно один раз, а повторный вернёт True
    (нужно пропустить). Без Redis (нет клиента) дедупликация отключается — это лучше,
    чем потеря апдейта: корректность важнее идемпотентности в dev-режиме.
    """
    if update_id is None or redis is None:
        return False
    key = f"{UPDATE_ID_KEY_PREFIX}:{update_id}"
    # SETNX + TTL: ключ ставится только если его ещё нет; TTL ограничивает рост памяти.
    fresh = await redis.set(key, "1", nx=True, ex=UPDATE_ID_TTL_SECONDS)
    return fresh is False


@router.post("/webhook/bot", response_model=WebhookResponse)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias=SECRET_HEADER),
) -> WebhookResponse:
    """Принимает апдейт от Telegram и передаёт его Dispatcher'у бота.

    Dispatcher и Bot создаются в lifespan (см. main.py) и лежат в app.state.
    Если webhook не настроен (нет токена/секрета) — 503, если секрет неверен — 403.
    Повторная доставка одного update_id (Telegram повторяет запрос при недоставке ответа)
    дедуплицируется через Redis: повторный апдейт отвечает ok, но не обрабатывается.
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

    # Идемпотентность: повторный вебхук с уже обработанным update_id не должен запускать
    # хендлер повторно (иначе возможно, например, двойное создание записи).
    redis = getattr(request.app.state, "redis", None)
    if await _is_duplicate(redis, _extract_update_id(update)):
        return WebhookResponse()

    await dispatcher.feed_webhook_update(bot, update)

    return WebhookResponse()
