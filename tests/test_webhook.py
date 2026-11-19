"""Тесты webhook-эндпоинта и Redis-хранилища состояния.

Без реальных Telegram/Redis: проверяем валидацию секрета (403), ответ 503 при отсутствии
бота, и сериализацию/десериализацию контекста Redis-хранилища.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.webhook import _secret_matches
from app.bot.states import BookingState
from app.bot.storage import BookingContext, RedisBookingStorage
from app.core.config import get_settings
from app.main import app


@pytest.fixture
def client():
    # Без `with` lifespan не запускается (как в test_health.py), поэтому не пытаемся
    # подключиться к реальным Postgres/Redis. Эндпоинт проверяет секрет до обращения к
    # app.state.bot, так что тесты валидации и 503 работают без lifespan.
    yield TestClient(app)


# --- валидация секрета ---------------------------------------------------------


def test_secret_matches_correct():
    assert _secret_matches("abc123", "abc123")


def test_secret_matches_wrong():
    assert not _secret_matches("wrong", "abc123")


def test_secret_matches_missing_expected():
    # Если секрет не настроен, ни один входящий секрет не проходит.
    assert not _secret_matches("anything", None)


def test_secret_matches_missing_provided():
    assert not _secret_matches(None, "abc123")


# --- webhook HTTP --------------------------------------------------------------
# Секрет читается из настроек (get_settings). Подменяем значение поля напрямую.


@pytest.fixture
def secret_token(monkeypatch):
    # get_settings кэшируется через lru_cache; проще подменить поле у уже созданного объекта.
    settings = get_settings()
    monkeypatch.setattr(settings, "webhook_secret", "test-secret")
    yield "test-secret"


def test_webhook_without_secret_header_returns_403(client, secret_token):
    response = client.post("/webhook/bot", json={"update_id": 1})

    assert response.status_code == 403


def test_webhook_with_wrong_secret_returns_403(client, secret_token):
    response = client.post(
        "/webhook/bot",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
    )

    assert response.status_code == 403


def test_webhook_without_bot_configured_returns_503(client, secret_token):
    # Секрет верный, но app.state.bot не создан (webhook не настроен) -> 503.
    response = client.post(
        "/webhook/bot",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
    )

    assert response.status_code == 503


# --- Redis-хранилище: сериализация (без реального Redis) -----------------------


def test_redis_serialize_roundtrip():
    ctx = BookingContext(
        state=BookingState.CHOOSE_SLOT,
        client_id=1,
        service_id=2,
        master_id=3,
        day="2026-11-20",
    )
    raw = RedisBookingStorage._serialize(ctx)
    restored = RedisBookingStorage._deserialize(raw)

    assert restored.state == BookingState.CHOOSE_SLOT
    assert restored.client_id == 1
    assert restored.service_id == 2
    assert restored.master_id == 3
    assert restored.day == "2026-11-20"


def test_redis_serialize_default_context():
    raw = RedisBookingStorage._serialize(BookingContext())
    restored = RedisBookingStorage._deserialize(raw)

    assert restored.state == BookingState.START
    assert restored.client_id is None
    assert restored.master_id is None


def test_redis_key_format():
    storage = RedisBookingStorage(SimpleNamespace(), key_prefix="booking")
    assert storage._key(42) == "booking:42"
