from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.appointment import AppointmentStatusEnum


class AppointmentBase(BaseModel):
    client_id: int
    master_id: int
    service_id: int
    # Время вернёт API/бот уже в UTC (aware). Хранится в БД как timestamptz.
    starts_at: datetime
    ends_at: datetime
    price: Decimal


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    """Изменение записи: только время/цена, которые можно менять свободно.

    status намеренно отсутствует: статус меняется ТОЛЬКО через машину переходов
    (эндпоинт POST /appointments/{id}/status), чтобы запрещённые переходы не могли
    проскочить через обычный PATCH.
    """

    starts_at: datetime | None = None
    ends_at: datetime | None = None
    price: Decimal | None = None


class AppointmentStatusUpdate(BaseModel):
    """Смена статуса записи. Отдельная схема, потому что статус меняют только через машину
    переходов (валидация допустимого графа), а не напрямую через AppointmentUpdate."""

    status: AppointmentStatusEnum


class AppointmentReschedule(BaseModel):
    """Перенос записи на другой слот: новое время (конфликт со слотами проверяется)."""

    starts_at: datetime
    ends_at: datetime


class AppointmentOut(AppointmentBase):
    id: int
    status: AppointmentStatusEnum

    model_config = ConfigDict(from_attributes=True)
