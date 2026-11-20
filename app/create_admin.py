"""CLI-утилита создания администратора (первый запуск / деплой).

Приложение не имеет публичного эндпоинта регистрации админа — иначе любой мог бы создать
себе админскую учётную запись. Вместо этого администратор создаётся адресно: на сервере
или локально, запуском этой команды.

Использование:
    python -m app.create_admin --name "Администратор" --phone "+79990000000" --password "..."

Пароль можно не передавать флагом (тогда он не попадёт в историю shell): команда
запросит его интерактивно через getpass. Хеш сохраняется в БД (bcrypt), открытый
пароль никуда не пишется.

Требует переменные окружения POSTGRES_* (см. .env.example) — как и само приложение.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import ClientORM


def _parse_args() -> argparse.Namespace:
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Создать или повысить администратора салона")
    parser.add_argument("--name", required=True, help="Имя администратора")
    parser.add_argument("--phone", required=True, help="Телефон для входа (уникальный)")
    parser.add_argument("--password", default=None, help="Пароль (если не задан — спросим)")
    return parser.parse_args()


async def _create_or_promote(name: str, phone: str, password: str) -> None:
    """Создаёт нового админа по телефону либо повышает существующего клиента до админа.

    Если клиент с таким телефоном уже есть — обновляем его имя, пароль и флаг is_admin;
    если нет — создаём новую запись. Возвращает сообщение о результате для вывода.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        result = await session.execute(select(ClientORM).where(ClientORM.phone == phone))
        client = result.scalars().first()

        if client is None:
            client = ClientORM(name=name, phone=phone)
            session.add(client)
            action = "создан"
        else:
            action = "обновлён"

        client.name = name
        client.password_hash = hash_password(password)
        client.is_admin = True
        await session.commit()
        await session.refresh(client)
        print(f"✅ Администратор {action}: id={client.id}, phone={client.phone}")

    await engine.dispose()


def main() -> None:
    """Точка входа: читает аргументы, запрашивает пароль при необходимости и запускает."""
    args = _parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Пароль администратора: ")
        if not password:
            print("Пароль не может быть пустым.", file=sys.stderr)
            sys.exit(2)

    try:
        asyncio.run(_create_or_promote(args.name, args.phone, password))
    except Exception as exc:  # noqa: BLE001 — понятное сообщение об ошибке настройки
        print(f"❌ Не удалось создать администратора: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
