"""Валидация initData из Telegram Mini App (HMAC-SHA256).

Когда пользователь открывает Mini App, Telegram передаёт фронтенду строку `initData`
(через `window.Telegram.WebApp.initData`). Фронтенд отправляет её бэкенду, а бэкенд
обязан убедиться, что данные подписаны самим Telegram, а не подделаны клиентом.

Алгоритм (официальный, из документации Telegram):
1. `initData` — это query-string: `user=...&auth_date=...&hash=...`.
2. Из строки извлекается поле `hash`, а все остальные параметры сортируются по имени
   и склеиваются в `data_check_string = k1=v1\nk2=v2\n...`.
3. `secret_key = HMAC_SHA256(key="WebAppData", message=bot_token)`.
4. `expected_hash = HMAC_SHA256(key=secret_key, message=data_check_string)` (hex).
5. Пришедший `hash` сравнивается с `expected_hash` (через `hmac.compare_digest`,
   чтобы избежать timing-атаки).

Если подпись сходится, данным можно доверять: их составил Telegram, а значит `user.id`
и другие поля достоверны. Иначе — 401/вариант «поддельные данные отклоняются».
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import parse_qsl

# Строка-«соль», фиксированная Telegram для всех Mini App (не зависит от бота).
_WEBAPP_KEY = b"WebAppData"


class TelegramInitDataError(ValueError):
    """initData не прошёл валидацию: нет подписи, неверный формат или истёк срок."""


def _hmac_hex(key: bytes, message: str) -> str:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _compute_secret_key(bot_token: str) -> bytes:
    """Вычисляет секретный ключ HMAC из bot_token (первый шаг официального алгоритма)."""
    return hmac.new(_WEBAPP_KEY, bot_token.encode("utf-8"), hashlib.sha256).digest()


def _build_data_check_string(fields: dict[str, str]) -> str:
    """Склеивает все поля (кроме hash), отсортированные по имени, в data_check_string.

    Формат: `a=1\nb=2\n...` — каждая пара на своей строке, без завершающего переноса.
    """
    return "\n".join(f"{key}={value}" for key, value in sorted(fields.items()) if key != "hash")


def validate_init_data(
    init_data: str, bot_token: str | None, max_age_seconds: int = 0
) -> dict[str, Any]:
    """Проверяет подпись initData и возвращает распарсенные поля.

    Аргументы:
      init_data — сырая строка initData из Telegram.
      bot_token — токен бота (None означает «валидация невозможна» -> ошибка).
      max_age_seconds — максимальный допустимый возраст auth_date в секундах.
        0 отключает проверку срока (по умолчанию). Положительное значение требует,
        чтобы auth_date был не старше указанного окна (защита от replay).

    Возвращает dict со всеми полями (включая user/json, если переданы).
    Кидает TelegramInitDataError при любой проблеме: отсутствие hash, неверная подпись,
    слишком старый auth_date.
    """
    if not bot_token:
        raise TelegramInitDataError("BOT_TOKEN не задан — валидация initData невозможна")

    if not init_data:
        raise TelegramInitDataError("initData отсутствует")

    # parse_qsl сохраняет типы строк; поле-значения приходят как str.
    fields: dict[str, str] = dict(parse_qsl(init_data, keep_blank_values=True))

    provided_hash = fields.pop("hash", None)
    if not provided_hash:
        raise TelegramInitDataError("В initData отсутствует поле hash")

    secret_key = _compute_secret_key(bot_token)
    data_check_string = _build_data_check_string(fields)
    expected_hash = _hmac_hex(secret_key, data_check_string)

    if not hmac.compare_digest(provided_hash, expected_hash):
        raise TelegramInitDataError("Неверная подпись initData")

    # Проверка свежести: auth_date задаётся Telegram как Unix-время.
    if max_age_seconds > 0:
        auth_date_raw = fields.get("auth_date")
        if auth_date_raw is None or not auth_date_raw.isdigit():
            raise TelegramInitDataError("В initData отсутствует корректный auth_date")
        auth_date = int(auth_date_raw)
        if time.time() - auth_date > max_age_seconds:
            raise TelegramInitDataError("initData просрочен (auth_date слишком старый)")

    return fields


def extract_user_id(fields: dict[str, Any]) -> int | None:
    """Достаёт telegram user id из проверенных полей initData.

    Пользователь приходит как JSON-строка в поле `user` (например,
    `user={"id":123,...,"first_name":"..."}`). Возвращаем `id` как int или None,
    если поле отсутствует/некорректно.
    """
    import json

    raw = fields.get("user")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        user = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict):
        return None
    user_id = user.get("id")
    if user_id is None:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def build_init_data_for_test(
    bot_token: str,
    fields: dict[str, str],
) -> str:
    """Собирает подписанную initData из произвольных полей (для тестов).

    Поле `hash` вычисляется по официальному алгоритму и добавляется автоматически.
    Утилита нужна только тестам — в проде initData формирует сам Telegram.

    Формат результата повторяет настоящее initData: query-string с разделителем `&`
    (`user=...&auth_date=...&hash=...`). Порядок полей не важен, но hash всегда последним.
    """
    secret_key = _compute_secret_key(bot_token)
    data_check_string = _build_data_check_string(fields)
    signed_hash = _hmac_hex(secret_key, data_check_string)
    params = "&".join(f"{key}={value}" for key, value in sorted(fields.items()))
    return f"{params}&hash={signed_hash}"
