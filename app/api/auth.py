"""Эндпоинты аутентификации: регистрация клиента и вход (получение JWT).

Регистрация создаёт клиента с bcrypt-хешем пароля. Вход сверяет пароль и выдаёт
access-токен. Токен кладётся в httpOnly cookie (Set-Cookie), которую браузер сам
подставляет в каждый запрос; зависимость get_current_client в deps.py читает её и
восстанавливает текущего клиента.
"""

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DBDep
from app.core.security import (
    build_auth_cookie,
    clear_auth_cookie,
    create_access_token,
    verify_password,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.client import ClientCreate

router = APIRouter(prefix="/auth", tags=["Auth"])


def _set_auth_cookie(response: Response, token: str) -> None:
    """Кладёт access-токен в httpOnly cookie через заголовок Set-Cookie."""
    response.set_cookie(**build_auth_cookie(token))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(db: DBDep, data: RegisterRequest, response: Response) -> TokenResponse:
    """Создать клиента с учётной записью и сразу выдать access-токен в cookie.

    Паттерн «зарегистрировался — сразу вошёл»: сервер выдаёт токен сразу, поэтому
    клиенту не нужно повторно логиниться. Токен уходит в httpOnly cookie, а не в тело.
    """
    client = await db.clients.create_with_password(
        ClientCreate(name=data.name, phone=data.phone, telegram_id=None),
        data.password,
    )
    token = create_access_token(client.id)
    _set_auth_cookie(response, token)
    return TokenResponse(client_id=client.id)


@router.post("/login", response_model=TokenResponse)
async def login(db: DBDep, data: LoginRequest, response: Response) -> TokenResponse:
    """Выдать access-токен по паролю в httpOnly cookie. Клиент ищется по телефону."""
    client = await db.clients.get_by_phone(data.phone)
    if client is None or not verify_password(data.password, client.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный телефон или пароль",
        )
    token = create_access_token(client.id)
    _set_auth_cookie(response, token)
    return TokenResponse(client_id=client.id)


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(db: DBDep, data: LoginRequest, response: Response) -> TokenResponse:
    """Вход администратора: как обычный вход, но требует is_admin=True.

    Не-админ (или неверный пароль) получает 401/403. Возвращаемый токен тот же по структуре,
    что и у клиента — разница в флаге is_admin в записи, которую восстанавливает
    get_current_admin (deps.py). Токен кладётся в httpOnly cookie.
    """
    client = await db.clients.get_by_phone(data.phone)
    if client is None or not verify_password(data.password, client.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный телефон или пароль",
        )
    if not client.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    token = create_access_token(client.id)
    _set_auth_cookie(response, token)
    return TokenResponse(client_id=client.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Удаляет access-токен из cookie (выход из аккаунта)."""
    response.set_cookie(**clear_auth_cookie())
