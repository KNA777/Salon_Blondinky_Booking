from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.api.deps import CurrentAdminDep, CurrentClientDep, DBDep
from app.core.config import get_settings
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.post("")
async def add_appointment(db: DBDep, data: AppointmentCreate):
    """Создать запись. Статус по умолчанию created (см. server_default в модели).

    Перед вставкой проверяем, что слот свободен (защита от двойной записи); занятый
    слот вернёт HTTP 409.
    """
    return await db.appointments.create_with_conflict_check(data)


@router.get("")
async def get_appointments_bulk(
    db: DBDep, client_id: int | None = None, master_id: int | None = None
):
    """Список записей. Можно фильтровать по клиенту или мастеру."""
    if client_id is not None:
        return await db.appointments.get_bulk_by_client(client_id)
    if master_id is not None:
        return await db.appointments.get_bulk_by_master(master_id)
    return await db.appointments.get_data_bulk()


@router.get("/{appointment_id}")
async def get_appointment_by_id(db: DBDep, appointment_id: int):
    return await db.appointments.get_one_by_id(id=appointment_id)


@router.get("/admin/day")
async def get_appointments_by_day(
    db: DBDep,
    day: Annotated[date, Query(description="Дата в часовом поясе салона (YYYY-MM-DD)")],
    _admin: CurrentAdminDep,
):
    """Админский просмотр расписания на конкретный день (задача 14).

    Возвращает все записи, пересекающиеся с этим днём (в часовом поясе салона),
    независимо от клиента и мастера. Требует прав администратора.
    """
    salon_tz = ZoneInfo(get_settings().salon_timezone)
    day_start = datetime.combine(day, time.min, tzinfo=salon_tz)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=salon_tz)
    return await db.appointments.get_by_day(day_start, day_end)


@router.patch("/{appointment_id}")
async def appointment_partial_change(db: DBDep, appointment_id: int, data: AppointmentUpdate):
    """Изменить время/статус записи. Статус здесь меняется через машину переходов."""
    return await db.appointments.change_object(data, id=appointment_id, exclude_unset=True)


@router.post("/{appointment_id}/status")
async def change_appointment_status(db: DBDep, appointment_id: int, data: AppointmentStatusUpdate):
    """Перевести запись в новый статус с проверкой допустимости перехода (машина).

    Запрещённый переход (например, completed -> created) вернёт HTTP 409.
    """
    return await db.appointments.transition_status(appointment_id, data.status)


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(db: DBDep, appointment_id: int, current_client: CurrentClientDep):
    """Клиент отменяет свою запись: статус -> cancelled (через машину переходов).

    Не-админ может отменить только свою запись (иначе 403); админ — любую.
    """
    return await db.appointments.cancel(appointment_id, current_client.id, current_client.is_admin)


@router.post("/{appointment_id}/confirm")
async def confirm_appointment(db: DBDep, appointment_id: int, _admin: CurrentAdminDep):
    """Админ подтверждает запись: created -> confirmed (задача 14).

    Смена статуса идёт через машину переходов; недопустимый переход вернёт 409.
    """
    from app.models import AppointmentStatusEnum

    return await db.appointments.transition_status(appointment_id, AppointmentStatusEnum.CONFIRMED)


@router.post("/{appointment_id}/reschedule")
async def reschedule_appointment(
    db: DBDep,
    appointment_id: int,
    data: AppointmentReschedule,
    current_client: CurrentClientDep,
):
    """Перенос записи на другой слот (проверка конфликта со слотами и владения).

    Не-админ переносит только свою запись (иначе 403); админ — любую.
    """
    return await db.appointments.reschedule(
        appointment_id,
        data.starts_at,
        data.ends_at,
        current_client.id,
        current_client.is_admin,
    )
