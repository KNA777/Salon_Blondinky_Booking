"""Общая инфраструктура для интеграционных тестов на реальной БД (задачи 23/24).

Поднимает отдельную тестовую базу (salon_blondinky_test), прогоняет на ней миграции
Alembic и предоставляет session_factory, движок и TestClient, смотрящие в неё.

Если Postgres недоступен (например, в CI без базы), интеграционные тесты пропускаются
через pytest.skip — юнит-тесты при этом продолжают работать. Чтобы интеграционные
тесты гарантированно шли локально, нужен запущенный Postgres (см. README).
"""

import asyncio
import os
import threading
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_session

# `Settings` требует postgres_* / redis_* без дефолтов (production fail-fast). Юнит-тесты
# auth/bot/webhook вызывают get_settings() только ради JWT- и таймзона-параметров, к БД и
# Redis не подключаясь, а в CI-джобе `pytest-unit` эти переменные не заданы — без заглушек
# Settings() падал бы с ValidationError. Проставляем значения через setdefault на этапе
# импорта conftest (до любых тестов): реальные env из CI/integration-джоба не перетираются.
for _key, _value in {
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
    "POSTGRES_DB": "postgres",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
}.items():
    os.environ.setdefault(_key, _value)


# Имя тестовой базы: отдельная от салона, чтобы тесты не трогали рабочие данные.
TEST_DB_NAME = "salon_blondinky_test"

# Берём параметры подключения из окружения (.env), как и само приложение.
_POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
_POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "postgres")
_POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
_POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")

_ADMIN_URL = (
    f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}"
    f"@{_POSTGRES_HOST}:{_POSTGRES_PORT}/postgres"
)
_TEST_URL = (
    f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}"
    f"@{_POSTGRES_HOST}:{_POSTGRES_PORT}/{TEST_DB_NAME}"
)


async def _postgres_available() -> bool:
    """Проверяем, что к Postgres вообще можно подключиться."""
    try:
        engine = create_async_engine(_ADMIN_URL)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


async def _create_test_db_if_missing() -> None:
    """Создаёт тестовую БД, если её ещё нет (CREATE DATABASE нельзя в транзакции)."""
    engine = create_async_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await engine.dispose()


async def _apply_schema(url: str) -> None:
    """Создаёт схему тестовой БД: таблицы из metadata + exclusion constraint.

    Alembic здесь не запускаем — его env.py сам вызывает asyncio.run(), что ломается внутри
    уже запущенного event loop pytest-asyncio. Вместо этого создаём таблицы через
    BaseORM.metadata.create_all, а затем вручную применяем то, что create_all не умеет:
    расширение btree_gist и exclusion constraint appointments_no_overlap (миграция
    a1b2c3d4e5f6). Именно его проверяет race-тест.
    """
    import app.models  # noqa: F401 — регистрирует все модели в BaseORM.metadata
    from app.models import BaseORM

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(BaseORM.metadata.create_all)
    # create_all создаёт схему public заново только если её нет; для чистоты — сбрасываем выше.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.execute(
            text(
                """
                ALTER TABLE appointments
                ADD CONSTRAINT appointments_no_overlap
                EXCLUDE USING gist (
                    master_id WITH =,
                    tstzrange(starts_at, ends_at) WITH &&
                )
                WHERE (status IN ('created', 'confirmed'))
                """
            )
        )
    await engine.dispose()


def _run(coro):
    """Запускает корутину в отдельном потоке со своим event loop.

    pytest-asyncio в режиме `auto` создаёт уже запущенный event loop для async-тестов,
    поэтому внутри sync-фикстур `asyncio.run()` падает с RuntimeError. Отдельный поток
    решает эту проблему: у него собственный, ещё не запущенный цикл, а наши корутины
    сами не вызывают вложенный asyncio.run (в отличие от alembic env.py).
    """
    result = {}

    def _target():
        result["value"] = asyncio.run(coro)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    return result["value"]


@pytest.fixture(scope="session")
def _integration_db():
    """Подготавливает тестовую БД один раз на всю сессию тестов.

    Возвращает None, если Postgres недоступен (тогда фикстуры ниже пропустят тесты).
    """
    available = _run(_postgres_available())
    if not available:
        return None
    _run(_create_test_db_if_missing())
    # Прогоняем схему начисто: дропаем public и создаём заново из metadata + constraint.
    _run(_drop_all(_TEST_URL))
    _run(_apply_schema(_TEST_URL))
    return _TEST_URL


async def _drop_all(url: str) -> None:
    """Сбрасывает схему public в тестовой БД (чтобы каждый прогон начинался с чистого листа).

    asyncpg не позволяет несколько команд в одном prepared statement, поэтому DROP и CREATE
    выполняем отдельными запросами.
    """
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def db_url(_integration_db):
    if _integration_db is None:
        pytest.skip("Postgres недоступен — интеграционные тесты пропущены")
    return _integration_db


@pytest.fixture
async def session_factory(db_url) -> AsyncIterator[async_sessionmaker]:
    """Фабрика сессий, смотрящая в тестовую БД. У каждой функции — свой движок."""
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(session_factory) -> AsyncIterator:
    """Асинхронный HTTP-клиент к приложению с реальной БД.

    Используем httpx.AsyncClient + ASGITransport (а не синхронный TestClient): он дёргает
    ASGI-приложение прямо внутри event loop теста, поэтому asyncpg-сессии (привязанные к
    этому же loop) работают корректно. TestClient запускает приложение в отдельном потоке
    с другим event loop, из-за чего asyncpg ловит «attached to a different loop».
    """
    import httpx

    from app.main import app

    async def _override_session():
        from app.core.db_context_manager import DBManager

        async with DBManager(session_factory) as db:
            yield db

    app.dependency_overrides[get_session] = _override_session
    # get_current_client / get_current_admin читают request.app.state.session_factory
    # (а не get_session), поэтому указываем тестовую фабрику и там.
    app.state.session_factory = session_factory
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def clean_db(session_factory) -> AsyncIterator[None]:
    """Очищает таблицы перед каждым тестом, чтобы тесты не влияли друг на друга."""
    async with session_factory() as session:
        # Порядок важен из-за внешних ключей с RESTRICT.
        for table in (
            "appointments",
            "master_services",
            "working_hours",
            "clients",
            "services",
            "masters",
        ):
            await session.execute(text(f"TRUNCATE {table} RESTART IDENTITY CASCADE"))
        await session.commit()
    yield


@pytest.fixture
async def admin_headers(session_factory, clean_db) -> dict:
    """Создаёт клиента-админа и возвращает заголовки авторизации с его JWT.

    Используется в интеграционных тестах админ-эндпоинтов (задачи 14/16): эндпоинты
    создания/правки услуг, мастеров и рабочих часов теперь требуют токен администратора.
    """
    from app.core.security import create_access_token, hash_password
    from app.models import ClientORM

    async with session_factory() as session:
        admin = ClientORM(
            name="Админ",
            phone="+79990000000",
            password_hash=hash_password("admin-pass"),
            is_admin=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        token = create_access_token(admin.id)

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client_headers(session_factory, clean_db) -> dict:
    """Создаёт обычного клиента (не админа) и возвращает заголовки с его JWT."""
    from app.core.security import create_access_token, hash_password
    from app.models import ClientORM

    async with session_factory() as session:
        client = ClientORM(
            name="Клиент",
            phone="+79990000001",
            password_hash=hash_password("client-pass"),
            is_admin=False,
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        token = create_access_token(client.id)

    return {"Authorization": f"Bearer {token}"}
