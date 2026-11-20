"""Race-тест exclusion constraint (задача 9/23): гонка на уровне БД.

Проверяем, что даже когда два клиента одновременно занимают один и тот же слот и проверка
на уровне приложения «разошлась» (оба выполнили SELECT и увидели слот свободным), exclusion
constraint `appointments_no_overlap` (миграция a1b2c3d4e5f6) не даёт вставить две
пересекающиеся записи в блокирующих статусах (created/confirmed).

Требует реального Postgres (с расширением btree_gist); без него пропускается через
фикстуру db_url в conftest.py.
"""

import asyncio
import os
from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest


def _aware(day: date, wall_hour: int, minutes: int = 60) -> tuple[datetime, datetime]:
    """Момент в UTC: салон Europe/Moscow (+3), «настенный» час -> UTC вычитанием 3 часов."""
    start = datetime(day.year, day.month, day.day, wall_hour, 0, tzinfo=UTC) - timedelta(hours=3)
    return start, start + timedelta(minutes=minutes)


@pytest.fixture(scope="session")
def pg_dsn():
    """Чистый asyncpg DSN к тестовой БД (postgresql://, не SQLAlchemy-URL)."""
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/salon_blondinky_test"


@pytest.fixture
async def seeded(session_factory):
    """Создаёт услугу, мастера и двух клиентов; возвращает их id."""
    from app.models import ClientORM, MasterORM, ServiceORM

    async with session_factory() as session:
        service = ServiceORM(name="Маникюр", duration_minutes=60, price=1500)
        master = MasterORM(name="Мария")
        session.add_all([service, master])
        await session.flush()
        c1 = ClientORM(name="Иван")
        c2 = ClientORM(name="Пётр")
        session.add_all([c1, c2])
        await session.flush()
        ids = (service.id, master.id, c1.id, c2.id)
        await session.commit()
    return ids


async def test_exclusion_constraint_blocks_concurrent_double_booking(
    db_url, pg_dsn, clean_db, seeded
):
    """Два истинно параллельных INSERT в один слот: ровно один проходит, второй блокируется.

    Открываем два независимых asyncpg-соединения и начинаем на обоих транзакцию ДО вставки.
    Затем оба INSERT идут одновременно через asyncio.gather: один вход в exclusion-индекс
    блокируется на «спекулятивной вставке» другого и после COMMIT первого получает
    ExclusionViolationError (asyncpg.ExclusionViolationError). Ровно одна строка остаётся.
    """
    service_id, master_id, c1, c2 = seeded
    starts, ends = _aware(date(2026, 11, 25), 10)

    conn_a = await asyncpg.connect(pg_dsn)
    conn_b = await asyncpg.connect(pg_dsn)
    try:
        # Обе транзакции открыты заранее — вставки реально конкурентны.
        await conn_a.execute("BEGIN")
        await conn_b.execute("BEGIN")

        insert_sql = (
            "INSERT INTO appointments"
            " (client_id, master_id, service_id, starts_at, ends_at, price, status)"
            " VALUES ($1, $2, $3, $4, $5, 1500.00, 'created')"
        )
        args_a = (c1, master_id, service_id, starts, ends)
        args_b = (c2, master_id, service_id, starts, ends)

        async def insert_commit(conn, args):
            await conn.execute(insert_sql, *args)
            await conn.execute("COMMIT")

        # Один INSERT закоммитится, второй получит ExclusionViolationError.
        results = await asyncio.gather(
            insert_commit(conn_a, args_a),
            insert_commit(conn_b, args_b),
            return_exceptions=True,
        )

        # Проверяем, что ровно один прошёл, а второй был отклонён на уровне БД.
        # При конкурентной вставке второй запрос либо ловит ExclusionViolationError,
        # либо (если сервер раньше обнаружил взаимоблокировку) DeadlockDetectedError —
        # в обоих случаях вторая строка не появляется.
        committed = [r for r in results if r is None]
        blocked = [
            r
            for r in results
            if isinstance(r, (asyncpg.ExclusionViolationError, asyncpg.DeadlockDetectedError))
            or (isinstance(r, asyncpg.PostgresError) and r.sqlstate == "40001")
        ]
        assert len(committed) == 1, f"ожидали ровно один успешный COMMIT, получили {results}"
        assert len(blocked) == 1, f"ожидали ровно одно отклонение на уровне БД, получили {results}"
    finally:
        await conn_a.close()
        await conn_b.close()

    # В базе ровно одна запись.
    verify = await asyncpg.connect(pg_dsn)
    try:
        count = await verify.fetchval("SELECT count(*) FROM appointments")
        assert count == 1
    finally:
        await verify.close()


async def test_exclusion_constraint_allows_cancelled_overlap(db_url, pg_dsn, clean_db, seeded):
    """Запись в статусе cancelled не блокирует слот: exclusion constraint действует
    только на created/confirmed (см. WHERE в миграции)."""
    service_id, master_id, c1, c2 = seeded
    starts, ends = _aware(date(2026, 11, 25), 10)

    conn = await asyncpg.connect(pg_dsn)
    try:
        await conn.execute(
            "INSERT INTO appointments"
            " (client_id, master_id, service_id, starts_at, ends_at, price, status)"
            " VALUES ($1, $2, $3, $4, $5, 1500.00, 'cancelled')",
            c1,
            master_id,
            service_id,
            starts,
            ends,
        )
        # Вторая запись (created) на тот же слот свободно проходит.
        await conn.execute(
            "INSERT INTO appointments"
            " (client_id, master_id, service_id, starts_at, ends_at, price, status)"
            " VALUES ($1, $2, $3, $4, $5, 1500.00, 'created')",
            c2,
            master_id,
            service_id,
            starts,
            ends,
        )
        count = await conn.fetchval("SELECT count(*) FROM appointments")
        assert count == 2
    finally:
        await conn.close()


def test_timezone_utc_storage_helper():
    """Дополнительная проверка помощника _aware: слот хранится в UTC, салон +3."""
    starts, ends = _aware(date(2026, 11, 25), 10)
    assert starts.tzinfo == UTC
    assert starts.hour == 7  # 10:00 Москва = 07:00 UTC
    assert ends.hour == 8
