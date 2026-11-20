"""Скрипт наполнения БД демо-данными: мастера, услуги, связи и расписание.

Запуск (из корня проекта, виртуальное окружение активировано):

    python scripts/seed_data.py          # добавить данные
    python scripts/seed_data.py --drop   # сначала очистить демо-таблицы, затем добавить

Скрипт переиспользует настройки и модели приложения, поэтому работает с тем же
Postgres/Redis, что и сам бот и FastAPI. Значения берутся из .env (через get_settings).

Что делает:
  * создаёт 5 мастеров;
  * создаёт 10 услуг;
  * назначает каждому мастеру свой набор услуг (связь многие-ко-многим master_services);
  * создаёт недельное расписание (working_hours) для каждого мастера.

Скрипт идемпотентен: повторный запуск не плодит дубликаты — он либо очищает таблицы
(--drop), либо пропускает уже существующие (сверка по имени мастера / названию услуги).
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

# Корень проекта должен быть в sys.path, чтобы импорт `from app.*` работал при любом
# способе запуска: и `python scripts/seed_data.py` (из корня), и `python seed_data.py`
# (из папки scripts). Та же страховка, что и в app/bot/__main__.py.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import app.models  # noqa: E402  (регистрирует все таблицы в BaseORM.metadata)
from app.core.config import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    MasterORM,
    ServiceORM,
    WorkingHourORM,
    master_services,
)

# ---------------------------------------------------------------------------
# Демо-данные
# ---------------------------------------------------------------------------

# Каждая услуга: название, длительность в минутах, цена.
SERVICES = [
    ("Женская стрижка", 60, Decimal("1500.00")),
    ("Мужская стрижка", 45, Decimal("1200.00")),
    ("Стрижка + укладка", 90, Decimal("2500.00")),
    ("Окрашивание", 120, Decimal("4500.00")),
    ("Мелирование", 150, Decimal("5500.00")),
    ("Тонирование", 90, Decimal("3000.00")),
    ("Укладка", 45, Decimal("1300.00")),
    ("Маникюр", 60, Decimal("1800.00")),
    ("Педикюр", 75, Decimal("2200.00")),
    ("Наращивание ресниц", 120, Decimal("3500.00")),
]

# Каждый мастер: имя, телефон и список названий услуг, которые он выполняет.
# Названия услуг должны совпадать с теми, что в SERVICES (связь строится по имени).
MASTERS = [
    {
        "name": "Анна",
        "phone": "+7 (900) 111-22-33",
        "services": [
            "Женская стрижка",
            "Стрижка + укладка",
            "Укладка",
            "Окрашивание",
        ],
    },
    {
        "name": "Мария",
        "phone": "+7 (900) 222-33-44",
        "services": [
            "Окрашивание",
            "Мелирование",
            "Тонирование",
            "Женская стрижка",
        ],
    },
    {
        "name": "Сергей",
        "phone": "+7 (900) 333-44-55",
        "services": [
            "Мужская стрижка",
            "Стрижка + укладка",
        ],
    },
    {
        "name": "Ольга",
        "phone": "+7 (900) 444-55-66",
        "services": [
            "Маникюр",
            "Педикюр",
        ],
    },
    {
        "name": "Екатерина",
        "phone": "+7 (900) 555-66-77",
        "services": [
            "Наращивание ресниц",
            "Укладка",
            "Женская стрижка",
        ],
    },
]

# Расписание. weekday: 0 = понедельник ... 6 = воскресенье.
# Так можно задать каждому мастеру свои часы и выходные (просто не указываем день).
# Формат: (weekday, "HH:MM", "HH:MM"). Обеденный перерыв — два интервала в один день.
WORKING_HOURS = {
    "Анна": [
        (0, "10:00", "14:00"),
        (0, "15:00", "19:00"),
        (1, "10:00", "19:00"),
        (2, "10:00", "19:00"),
        (3, "10:00", "19:00"),
        (4, "10:00", "18:00"),
        (5, "11:00", "17:00"),
    ],
    "Мария": [
        (1, "11:00", "20:00"),
        (2, "11:00", "20:00"),
        (3, "11:00", "20:00"),
        (4, "11:00", "20:00"),
        (5, "10:00", "16:00"),
    ],
    "Сергей": [
        (0, "09:00", "18:00"),
        (1, "09:00", "18:00"),
        (2, "09:00", "18:00"),
        (3, "09:00", "18:00"),
        (4, "09:00", "18:00"),
        (5, "09:00", "15:00"),
    ],
    "Ольга": [
        (0, "10:00", "19:00"),
        (2, "10:00", "19:00"),
        (3, "10:00", "19:00"),
        (4, "10:00", "19:00"),
        (6, "10:00", "16:00"),
    ],
    "Екатерина": [
        (1, "10:00", "18:00"),
        (2, "10:00", "18:00"),
        (3, "10:00", "18:00"),
        (4, "10:00", "18:00"),
        (5, "10:00", "14:00"),
    ],
}

# Таблицы для TRUNCATE. master_services — связующая Table (не модель), CASCADE всё
# равно подчистит ссылки; достаточно перечислить родительские таблицы.
_DROP_ORDER = [MasterORM, ServiceORM, WorkingHourORM]


def _parse_time(value: str):
    """Переводит "HH:MM" в datetime.time без лишнего импорта в теле данных."""
    from datetime import time

    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


async def _reset_tables(session) -> None:
    """Очищает демо-таблицы, чтобы --drop-запуск стартовал с чистого листа."""
    # TRUNCATE ... CASCADE чистит и зависимые записи (master_services, RESTART IDENTITY обнуляет id).
    tables = ", ".join(t.__tablename__ for t in _DROP_ORDER)
    await session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    await session.commit()


async def seed(drop_existing: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        if drop_existing:
            await _reset_tables(session)

        # 1) Услуги.
        services_by_name: dict[str, ServiceORM] = {}
        for name, duration, price in SERVICES:
            existing = await session.execute(
                select(ServiceORM).where(ServiceORM.name == name, ServiceORM.is_active.is_(True))
            )
            service = existing.scalars().first()
            if service is None:
                service = ServiceORM(name=name, duration_minutes=duration, price=price)
                session.add(service)
                await session.flush()  # получить id сразу
            services_by_name[name] = service
        await session.commit()

        # 2) Мастера + связи с услугами.
        masters_by_name: dict[str, MasterORM] = {}
        for item in MASTERS:
            name = item["name"]
            existing = await session.execute(
                select(MasterORM).where(MasterORM.name == name, MasterORM.is_active.is_(True))
            )
            master = existing.scalars().first()
            if master is None:
                master = MasterORM(name=name, phone=item["phone"])
                session.add(master)
                await session.flush()
            masters_by_name[name] = master

            # Связь многие-ко-многим. Уже существующие пары не дублируем: id уже
            # связанных услуг берём явным запросом, не трогая relationship (в async
            # lazy-load даёт MissingGreenlet).
            linked_rows = await session.execute(
                select(master_services.c.service_id).where(master_services.c.master_id == master.id)
            )
            linked = set(linked_rows.scalars().all())
            for service_name in item["services"]:
                service = services_by_name[service_name]
                if service.id not in linked:
                    await session.execute(
                        master_services.insert().values(
                            master_id=master.id, service_id=service.id
                        )
                    )
                    linked.add(service.id)
        await session.commit()

        # 3) Расписание.
        for master_name, intervals in WORKING_HOURS.items():
            master = masters_by_name[master_name]
            # Не плодим дубли: сверяем по (weekday, start_time), как и UniqueConstraint.
            existing = await session.execute(
                select(WorkingHourORM).where(WorkingHourORM.master_id == master.id)
            )
            have = {(wh.weekday, wh.start_time) for wh in existing.scalars()}
            for weekday, start, end in intervals:
                start_t = _parse_time(start)
                if (weekday, start_t) in have:
                    continue
                session.add(
                    WorkingHourORM(
                        master_id=master.id,
                        weekday=weekday,
                        start_time=start_t,
                        end_time=_parse_time(end),
                    )
                )
        await session.commit()

        # Финальный отчёт: перечитываем мастеров вместе с услугами, чтобы не
        # полагаться на lazy-loading (в async-сессии это даёт MissingGreenlet).
        report = await session.execute(
            select(MasterORM).options(selectinload(MasterORM.services)).order_by(MasterORM.id)
        )
        masters = report.scalars().all()
        print(f"Готово. Услуг: {len(services_by_name)}, мастеров: {len(masters)}.")
        for m in masters:
            print(f"  - {m.name}: {', '.join(s.name for s in m.services)}")

    await engine.dispose()


def main() -> None:
    drop_existing = "--drop" in sys.argv
    asyncio.run(seed(drop_existing))


if __name__ == "__main__":
    main()
