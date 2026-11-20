"""Пароли и JWT-токены: хеширование паролей и выпуск/проверка access-токенов.

Пароли храним только в виде bcrypt-хеша: `verify_password` сравнивает, нигде не глядя на
открытый пароль. Токены подписываются ключом из настроек (HS256), внутри — subject с
идентификатором клиента. Проверка подписи и срока жизни не даёт подделать токен.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля (в виде строки)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    """Проверяет пароль против хеша. Пустой хеш (нет учётной записи) -> всегда False."""
    if password_hash is None:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Некорректный хеш в БД не должен ронять весь запрос.
        return False


def create_access_token(subject: str | int) -> str:
    """Выпускает access-токен, в subject кладётся id клиента (как строка)."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int | None:
    """Проверяет и декодирует токен, возвращает client_id из subject.

    Возвращает None, если токен недействителен, просрочен или подделан (неверная подпись).
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


def build_auth_cookie(token: str) -> dict[str, str]:
    """Формирует параметры `Set-Cookie` для access-токена.

    Возвращает dict с ключом и значением куки. HttpOnly включён всегда (JS не увидит
    токен — защита от XSS); Secure берётся из настроек (в проде должен быть True, т.к.
    кука должна ходить только по HTTPS); SameSite и Path — тоже из настроек. Max-Age
    ставим равным сроку жизни токена, чтобы браузер сам «забыл» просроченный токен.
    """
    settings = get_settings()
    return {
        "key": settings.cookie_name,
        "value": token,
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "max_age": settings.jwt_expire_minutes * 60,
        "path": settings.cookie_path,
    }


def clear_auth_cookie() -> dict[str, str]:
    """Параметры `Set-Cookie` для удаления access-токена (выход из аккаунта).

    Пустое значение + max_age=0 заставляют браузер удалить куку с тем же именем и путём.
    """
    settings = get_settings()
    return {
        "key": settings.cookie_name,
        "value": "",
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "max_age": 0,
        "path": settings.cookie_path,
    }
