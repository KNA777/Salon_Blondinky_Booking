from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ServiceBase(BaseModel):
    name: str
    duration_minutes: int
    price: Decimal


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = None
    duration_minutes: int | None = None
    price: Decimal | None = None
    is_active: bool | None = None


class ServiceOut(ServiceBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
