"""Интеграционные тесты входа через Telegram Mini App (задача 15).

Проверяем POST /auth/telegram на реальной БД: валидный initData создаёт клиента по
telegram_id (upsert) и ставит httpOnly cookie с access-токеном; подделанный initData
отклоняется 401. Фикстуры client/clean_db из conftest.py; при недоступном Postgres — skip.
"""

import json
import time

from app.core.telegram_auth import build_init_data_for_test

# Токен бота, которым будут подписываться initData в тестах. Соответствует settings.bot_token,
# который мы задаём через monkeypatch (get_settings кешируется, но validate проверяет токен,
# переданный аргументом; эндпоинт берёт его из settings.bot_token).
BOT_TOKEN = "123456:ABC-DEF_test-token"


def _init_data(user_id: int, first_name: str = "Иван") -> str:
    user = json.dumps(
        {"id": user_id, "first_name": first_name, "last_name": "Петров", "username": "ivan"}
    )
    return build_init_data_for_test(
        BOT_TOKEN,
        {"auth_date": str(int(time.time())), "query_id": "AAHdF6IQ", "user": user},
    )


async def test_telegram_login_creates_client_and_sets_cookie(client, clean_db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bot_token", BOT_TOKEN)

    resp = await client.post("/auth/telegram", json={"init_data": _init_data(42)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["client_id"] > 0

    # httpOnly cookie с access-токеном выставлена.
    assert "set-cookie" in resp.headers
    cookie = resp.headers["set-cookie"]
    assert "access_token=" in cookie
    assert "HttpOnly" in cookie

    # Повторный вход с тем же telegram_id не плодит дубль — тот же client_id.
    resp2 = await client.post("/auth/telegram", json={"init_data": _init_data(42)})
    assert resp2.status_code == 200
    assert resp2.json()["client_id"] == body["client_id"]


async def test_telegram_login_tampered_init_data_rejected(client, clean_db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bot_token", BOT_TOKEN)

    # Подменяем id внутри подписанной строки — подпись перестаёт сходиться.
    tampered = _init_data(42).replace('"id": 42', '"id": 999')
    resp = await client.post("/auth/telegram", json={"init_data": tampered})
    assert resp.status_code == 401


async def test_telegram_login_rejects_missing_user(client, clean_db, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bot_token", BOT_TOKEN)

    # Подписанный initData без поля user (валидная подпись, но нет user.id).
    init_data = build_init_data_for_test(
        BOT_TOKEN, {"auth_date": str(int(time.time())), "query_id": "AAHdF6IQ"}
    )
    resp = await client.post("/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 401
