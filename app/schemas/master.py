from pydantic import BaseModel, ConfigDict, Field

from app.schemas.service import ServiceOut


class MasterBase(BaseModel):
    name: str
    phone: str | None = None


class MasterCreate(MasterBase):
    telegram_id: int | None = None
    service_ids: list[int] = Field(default_factory=list)


class MasterAdd(MasterBase):
    telegram_id: int | None = None


class MasterUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class MasterOut(MasterBase):
    id: int
    is_active: bool
    services: list[ServiceOut]

    model_config = ConfigDict(from_attributes=True)


class MasterService(BaseModel):
    master_id: int
    service_id: int
