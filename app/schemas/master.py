from pydantic import BaseModel, ConfigDict

from app.schemas.service import ServiceOut


class MasterBase(BaseModel):
    name: str
    phone: str | None = None


class MasterCreate(MasterBase):
    telegram_id: int | None = None
    service_ids: list[int] = []


class MasterUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: str | None = None


class MasterOut(MasterBase):
    id: int
    is_active: bool
    services: list[ServiceOut] = []

    model_config = ConfigDict(from_attributes=True)
