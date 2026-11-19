"""Расчёт свободных слотов мастера на конкретную дату.

Идея:
1. У мастера есть недельная сетка рабочих часов (WorkingHourORM) — «настенное» время салона.
2. Услуга задаёт длительность слота.
3. Записи (AppointmentORM) занимают интервалы [starts_at, ends_at) в UTC.
4. Слот свободен, если целиком помещается в рабочий интервал и не пересекается ни с одной
   записью, которая реально занимает время мастера.

Перевод «настенного» времени в UTC выполняется через salon_timezone (zoneinfo). Это важно:
в дни перехода на летнее/зимнее время «10:00» — это разный момент в UTC, и zoneinfo
считает его правильно.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db_context_manager import DBManager
from app.core.exceptions import NotFoundError
from app.models import (
    AppointmentORM,
    MasterORM,
    ServiceORM,
    WorkingHourORM,
    master_services,
)
from app.schemas.slot import FreeSlot, FreeSlotsOut
from app.services.booking_conflict import BLOCKING_STATUSES

# Только эти статусы (см. BLOCKING_STATUSES в booking_conflict) занимают время мастера.
# CANCELLED, COMPLETED и NO_SHOW не мешают появлению новых записей.


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Пересечение двух интервалов (полуинтервалов [start, end))."""
    return a_start < b_end and a_end > b_start


def generate_slots(
    working_hours: Sequence[WorkingHourORM],
    appointments: Sequence[AppointmentORM],
    day: date,
    duration_minutes: int,
    step_minutes: int,
    salon_tz: ZoneInfo,
) -> list[FreeSlot]:
    """Чистая геометрия слотов: без обращений к базе, удобно тестировать.

    working_hours — строки расписания на нужный день (start_time/end_time — Time).
    appointments — уже отфильтрованные занятые интервалы (starts_at/ends_at — aware UTC).
    Возвращает свободные слоты в UTC; в локальное время переводится через astimezone(salon_tz).
    """
    if duration_minutes <= 0 or step_minutes <= 0:
        return []

    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=step_minutes)
    busy = [(a.starts_at, a.ends_at) for a in appointments]

    free: list[FreeSlot] = []
    for wh in working_hours:
        interval_start = datetime.combine(day, wh.start_time, tzinfo=salon_tz).astimezone(UTC)
        interval_end = datetime.combine(day, wh.end_time, tzinfo=salon_tz).astimezone(UTC)

        slot_start = interval_start
        while slot_start + duration <= interval_end:
            slot_end = slot_start + duration
            if not any(_overlaps(slot_start, slot_end, bs, be) for bs, be in busy):
                free.append(FreeSlot(starts_at=slot_start, ends_at=slot_end))
            slot_start += step

    return free


def _empty_result(master_id: int, service_id: int, day: date, salon_tz: ZoneInfo) -> FreeSlotsOut:
    return FreeSlotsOut(
        master_id=master_id,
        service_id=service_id,
        date=day,
        timezone=salon_tz.key,
        slots=[],
    )


async def get_free_slots(
    db: DBManager,
    master_id: int,
    service_id: int,
    day: date,
    step_minutes: int,
    salon_tz: ZoneInfo,
) -> FreeSlotsOut:
    """Читает данные и собирает ответ о свободных слотах.

    Пустой список слотов возвращается, если мастер или услуга неактивны, мастер не оказывает
    эту услугу либо в этот день у него нет рабочих часов. Отсутствие самого мастера или
    услуги — ошибка 404 (NotFoundError).
    """
    master = await db.session.get(MasterORM, master_id)
    if master is None:
        raise NotFoundError("masters not found")

    service = await db.session.get(ServiceORM, service_id)
    if service is None:
        raise NotFoundError("services not found")

    if not master.is_active or not service.is_active:
        return _empty_result(master_id, service_id, day, salon_tz)

    link = await db.session.execute(
        select(master_services).where(
            master_services.c.master_id == master_id,
            master_services.c.service_id == service_id,
        )
    )
    if link.first() is None:
        return _empty_result(master_id, service_id, day, salon_tz)

    working_hours = (
        (
            await db.session.execute(
                select(WorkingHourORM)
                .where(
                    WorkingHourORM.master_id == master_id,
                    WorkingHourORM.weekday == day.weekday(),
                )
                .order_by(WorkingHourORM.start_time)
            )
        )
        .scalars()
        .all()
    )

    if not working_hours:
        return _empty_result(master_id, service_id, day, salon_tz)

    # Окно всего дня в UTC: выбираем записи, пересекающиеся с этим днём.
    day_start = datetime.combine(day, time.min, tzinfo=salon_tz).astimezone(UTC)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=salon_tz).astimezone(UTC)

    appointments = (
        (
            await db.session.execute(
                select(AppointmentORM).where(
                    AppointmentORM.master_id == master_id,
                    AppointmentORM.status.in_(BLOCKING_STATUSES),
                    AppointmentORM.starts_at < day_end,
                    AppointmentORM.ends_at > day_start,
                )
            )
        )
        .scalars()
        .all()
    )

    slots = generate_slots(
        working_hours, appointments, day, service.duration_minutes, step_minutes, salon_tz
    )

    return FreeSlotsOut(
        master_id=master_id,
        service_id=service_id,
        date=day,
        timezone=salon_tz.key,
        slots=[
            FreeSlot(
                starts_at=s.starts_at.astimezone(salon_tz),
                ends_at=s.ends_at.astimezone(salon_tz),
            )
            for s in slots
        ],
    )
