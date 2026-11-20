"""Схемы аутентификации: регистрация, вход и ответ с токеном.

Пароль приходит только в запросах (plain text по HTTPS в продакшене), в ответах никогда
не возвращается — наружу отдаётся только access-токен и данные клиента.
"""

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """Регистрация клиента: имя, телефон (опционально) и пароль."""

    name: str
    phone: str | None = None
    password: str


class LoginRequest(BaseModel):
    """Вход: клиент идентифицируется по телефону (или telegram_id), пароль сверяется."""

    phone: str
    password: str


class TelegramLoginRequest(BaseModel):
    """Вход через Telegram Mini App: фронтенд передаёт initData, подписанный Telegram.

    Валидация подписи (HMAC по bot_token) происходит на бэкенде; отсюда фронту нужна
    только сырая строка из `window.Telegram.WebApp.initData`. Telegram гарантирует
    подлинность `user.id`, поэтому пароль не нужен — доверяем самой подписи.
    """

    init_data: str


class TokenResponse(BaseModel):
    """Ответ на регистрацию/вход.

    Сам access-токен уходит в httpOnly cookie (через Set-Cookie), а не в теле — так его
    не читает JavaScript (защита от XSS). В теле остаются только безопасные данные,
    которые фронту нужны для UI: id клиента и тип токена.
    """

    token_type: str = "bearer"
    client_id: int
