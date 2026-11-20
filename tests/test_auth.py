"""Тесты аутентификации: хеширование паролей и выпуск/проверка JWT.

Чистая логика из app/core/security.py без БД и HTTP. Также покрываем проверку
владения записью (AppointmentRepository._ensure_owner) — она статическая и не требует
сессии, поэтому её можно проверить изолированно.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import PermissionError
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.patterns.repository.appointments import AppointmentRepository

# --- пароли --------------------------------------------------------------------


def test_hash_password_is_not_plaintext():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert hashed.startswith("$2")


def test_verify_password_correct():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)


def test_verify_password_wrong():
    hashed = hash_password("secret123")
    assert not verify_password("wrong", hashed)


def test_verify_password_none_hash():
    # Клиент без учётной записи (password_hash=None) никогда не проходит проверку.
    assert not verify_password("anything", None)


def test_verify_password_malformed_hash():
    # Некорректный хеш в БД не должен ронять проверку.
    assert not verify_password("secret123", "not-a-valid-bcrypt-hash")


# --- JWT -----------------------------------------------------------------------


def test_token_roundtrip():
    token = create_access_token(42)
    assert decode_token(token) == 42


def test_token_accepts_int_and_str_subject():
    # subject нормализуется до int в decode_token.
    assert decode_token(create_access_token("42")) == 42


def test_decode_garbage_token_returns_none():
    assert decode_token("not-a-token") is None


def test_decode_token_with_wrong_key_returns_none(monkeypatch):
    token = create_access_token(42)
    # Подменяем ключ — подпись перестанет сходиться.
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_secret_key", "another-secret")
    assert decode_token(token) is None


# --- владение записью (статическая проверка) ------------------------------------


def _appointment(client_id: int, appointment_id: int = 1):
    return SimpleNamespace(id=appointment_id, client_id=client_id)


def test_owner_can_manage_own_appointment():
    # Не должен бросать исключение.
    AppointmentRepository._ensure_owner(_appointment(7), client_id=7, is_admin=False)


def test_non_owner_cannot_manage_appointment():
    with pytest.raises(PermissionError):
        AppointmentRepository._ensure_owner(_appointment(7), client_id=8, is_admin=False)


def test_admin_can_manage_any_appointment():
    # Админ проходит независимо от того, чья запись.
    AppointmentRepository._ensure_owner(_appointment(7), client_id=999, is_admin=True)
