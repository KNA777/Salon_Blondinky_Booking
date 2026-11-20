"""Эндпоинты управления записями (appointments).

Правила доступа (важно для защиты персональных данных):
- Создать запись может только авторизованный клиент, и только для себя (client_id в теле
  обязан совпадать с текущим клиентом). Админ может создать запись для любого клиента.
- Читать/менять/отменять/переносить запись может её владелец или админ. Чужую запись
  не-админ не видит и не меняет (403).
- Смена статуса идёт только через машину переходов (app/services/status_machine.py).
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentAdminDep, CurrentClientDep, DBDep
from app.core.config import get_settings
from app.models.appointment import AppointmentStatusEnum
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentReschedule,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)
from app.schemas.client import ClientOut

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _authorize_appointment_access(appointment_client_id: int, current_client: ClientOut) -> None:
    """Разрешает доступ к записи только её владельцу или админу.

    Вызывается перед чтением/изменением записи, чтобы не-админ не мог получить доступ
    к чужой записи по перебору id. Если клиент не владелец и не админ — HTTP 403.
    """
    if not current_client.is_admin and appointment_client_id != current_client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для этой записи",
        )


@router.post("")
async def add_appointment(
    db: DBDep, data: AppointmentCreate, current_client: CurrentClientDep
) -> AppointmentOut:
    """Создать запись. Статус по умолчанию created (см. server_default в модели).

    Клиент может записать только себя: client_id в теле обязан совпадать с текущим
    авторизованным клиентом (иначе 403). Админ может создать запись для любого клиента.
    Перед вставкой проверяем, что слот свободен (защита от двойной записи); занятый
    слот вернёт HTTP 409.
    """
    if not current_client.is_admin and data.client_id != current_client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нельзя создать запись для другого клиента",
        )
    return await db.appointments.create_with_conflict_check(data)


@router.get("")
async def get_appointments_bulk(
    db: DBDep,
    current_client: CurrentClientDep,
    client_id: int | None = None,
    master_id: int | None = None,
) -> list[AppointmentOut]:
    """Список записей.

    - Админ без фильтров видит все записи; может фильтровать по клиенту или мастеру.
    - Клиент всегда видит только свои записи (любые переданные id игнорируются,
      чтобы нельзя было подглядеть чужую историю по client_id).
    """
    if current_client.is_admin:
        if client_id is not None:
            return await db.appointments.get_bulk_by_client(client_id)
        if master_id is not None:
            return await db.appointments.get_bulk_by_master(master_id)
        return await db.appointments.get_data_bulk()
    return await db.appointments.get_bulk_by_client(current_client.id)


@router.get("/admin/day")
async def get_appointments_by_day(
    db: DBDep,
    day: Annotated[date, Query(description="Дата в часовом поясе салона (YYYY-MM-DD)")],
    _admin: CurrentAdminDep,
) -> list[AppointmentOut]:
    """Админский просмотр расписания на конкретный день (задача 14).

    Возвращает все записи, пересекающиеся с этим днём (в часовом поясе салона),
    независимо от клиента и мастера. Требует прав администратора.
    """
    salon_tz = ZoneInfo(get_settings().salon_timezone)
    day_start = datetime.combine(day, time.min, tzinfo=salon_tz)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=salon_tz)
    return await db.appointments.get_by_day(day_start, day_end)


@router.get("/{appointment_id}")
async def get_appointment_by_id(
    db: DBDep, appointment_id: int, current_client: CurrentClientDep
) -> AppointmentOut:
    """Получить запись по id (только владелец или админ)."""
    appointment = await db.appointments.get_one_by_id(id=appointment_id)
    _authorize_appointment_access(appointment.client_id, current_client)
    return appointment


@router.patch("/{appointment_id}")
async def appointment_partial_change(
    db: DBDep,
    appointment_id: int,
    data: AppointmentUpdate,
    current_client: CurrentClientDep,
) -> AppointmentOut:
    """Изменить время/цену записи (только владелец или админ).

    Статус здесь намеренно не меняется: его изменение идёт только через машину переходов
    (POST /appointments/{id}/status). Чужую запись не-админ менять не может (403).
    """
    appointment = await db.appointments.get_one_by_id(id=appointment_id)
    _authorize_appointment_access(appointment.client_id, current_client)
    return await db.appointments.change_object(data, id=appointment_id, exclude_unset=True)


@router.post("/{appointment_id}/status")
async def change_appointment_status(
    db: DBDep,
    appointment_id: int,
    data: AppointmentStatusUpdate,
    _admin: CurrentAdminDep,
) -> AppointmentOut:
    """Перевести запись в новый статус (только админ, через машину переходов).

    Смена статуса — административное действие (подтверждение, отметка no_show,
    завершение), поэтому доступно только админу. Запрещённый переход вернёт HTTP 409.
    """
    return await db.appointments.transition_status(appointment_id, data.status)


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(
    db: DBDep, appointment_id: int, current_client: CurrentClientDep
) -> AppointmentOut:
    """Отменить запись: статус -> cancelled (через машину переходов).

    Не-админ может отменить только свою запись (иначе 403); админ — любую.
    """
    return await db.appointments.cancel(appointment_id, current_client.id, current_client.is_admin)


@router.post("/{appointment_id}/confirm")
async def confirm_appointment(
    db: DBDep, appointment_id: int, _admin: CurrentAdminDep
) -> AppointmentOut:
    """Админ подтверждает запись: created -> confirmed (задача 14).

    Смена статуса идёт через машину переходов; недопустимый переход вернёт 409.
    """
    return await db.appointments.transition_status(appointment_id, AppointmentStatusEnum.CONFIRMED)


@router.post("/{appointment_id}/reschedule")
async def reschedule_appointment(
    db: DBDep,
    appointment_id: int,
    data: AppointmentReschedule,
    current_client: CurrentClientDep,
) -> AppointmentOut:
    """Перенести запись на другой слот (проверка конфликта и владения).

    Не-админ переносит только свою запись (иначе 403); админ — любую.
    """
    return await db.appointments.reschedule(
        appointment_id,
        data.starts_at,
        data.ends_at,
        current_client.id,
        current_client.is_admin,
    )
