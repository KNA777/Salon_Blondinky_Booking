"""Тесты валидации initData из Telegram Mini App (HMAC-SHA256).

Покрываем чистую логику app/core/telegram_auth.py: корректную подпись принимаем,
подделанные/битые данные отклоняем. Для генерации валидных initData используем
build_init_data_for_test (тот же алгоритм, что и в проде, но на стороне теста).
"""

import json
import time

import pytest

from app.core.telegram_auth import (
    TelegramInitDataError,
    build_init_data_for_test,
    extract_user_id,
    validate_init_data,
)

BOT_TOKEN = "123456:ABC-DEF_test-token"


def _fields(user_id: int = 42, auth_date_ts: int | None = None) -> dict[str, str]:
    """Собирает поля initData, похожие на то, что присылает Telegram."""
    user = json.dumps(
        {
            "id": user_id,
            "first_name": "Иван",
            "last_name": "Петров",
            "username": "ivan",
        }
    )
    fields = {
        "auth_date": str(auth_date_ts if auth_date_ts is not None else int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohAOIu1Y",
        "user": user,
    }
    return fields


# --- подпись (валидные данные принимаем) ---------------------------------------


def test_valid_init_data_passes():
    init_data = build_init_data_for_test(BOT_TOKEN, _fields())
    parsed = validate_init_data(init_data, BOT_TOKEN)
    assert parsed["auth_date"].isdigit()
    assert "user" in parsed


def test_returns_fields_excluding_hash():
    init_data = build_init_data_for_test(BOT_TOKEN, _fields(user_id=7))
    parsed = validate_init_data(init_data, BOT_TOKEN)
    # hash не должен попадать в результат — он валидационный, а не бизнес-данные.
    assert "hash" not in parsed


def test_extract_user_id_returns_int():
    parsed_fields = {"user": json.dumps({"id": 123, "first_name": "Анна"})}
    assert extract_user_id(parsed_fields) == 123


# --- подделка / некорректные данные отклоняем ----------------------------------


def test_tampered_init_data_rejected():
    # Берём валидную подпись, но меняем user (id 42 -> 999). Подпись перестаёт сходиться.
    fields = _fields(user_id=42)
    init_data = build_init_data_for_test(BOT_TOKEN, fields)
    # Подменить id внутри подписанной строки, не трогая hash.
    tampered = init_data.replace('"id": 42', '"id": 999')
    with pytest.raises(TelegramInitDataError):
        validate_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_rejected():
    # Данные, подписанные другим токеном (другим ботом), не должны проходить.
    init_data = build_init_data_for_test("other-token", _fields())
    with pytest.raises(TelegramInitDataError):
        validate_init_data(init_data, BOT_TOKEN)


def test_missing_hash_rejected():
    # initData без поля hash невалиден.
    with pytest.raises(TelegramInitDataError):
        validate_init_data("auth_date=123&user=%7B%7D", BOT_TOKEN)


def test_empty_init_data_rejected():
    with pytest.raises(TelegramInitDataError):
        validate_init_data("", BOT_TOKEN)


def test_no_bot_token_rejected():
    # Без токена бота подпись проверить невозможно — это всегда ошибка.
    init_data = build_init_data_for_test(BOT_TOKEN, _fields())
    with pytest.raises(TelegramInitDataError):
        validate_init_data(init_data, None)


# --- свежесть (auth_date) ------------------------------------------------------


def test_stale_init_data_rejected_with_max_age():
    old = int(time.time()) - 3600  # час назад
    init_data = build_init_data_for_test(BOT_TOKEN, _fields(auth_date_ts=old))
    with pytest.raises(TelegramInitDataError):
        validate_init_data(init_data, BOT_TOKEN, max_age_seconds=60)


def test_fresh_init_data_accepted_with_max_age():
    now = int(time.time())
    init_data = build_init_data_for_test(BOT_TOKEN, _fields(auth_date_ts=now))
    # В пределах окна — ок.
    validate_init_data(init_data, BOT_TOKEN, max_age_seconds=60)


def test_max_age_zero_skips_freshness_check():
    # По умолчанию (max_age_seconds=0) проверка срока отключена — старый auth_date проходит.
    old = int(time.time()) - 3600
    init_data = build_init_data_for_test(BOT_TOKEN, _fields(auth_date_ts=old))
    validate_init_data(init_data, BOT_TOKEN, max_age_seconds=0)


# --- extract_user_id: некорректные данные --------------------------------------


def test_extract_user_id_missing_user():
    assert extract_user_id({}) is None


def test_extract_user_id_bad_json():
    assert extract_user_id({"user": "not-json"}) is None


def test_extract_user_id_non_int():
    assert extract_user_id({"user": json.dumps({"id": "abc"})}) is None
