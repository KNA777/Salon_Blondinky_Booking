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
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: AppointmentStatusEnum | None = None


class AppointmentOut(AppointmentBase):
    id: int
    status: AppointmentStatusEnum

    model_config = ConfigDict(from_attributes=True)
