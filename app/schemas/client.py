from pydantic import BaseModel, ConfigDict


class ClientBase(BaseModel):
    name: str
    phone: str | None = None


class ClientCreate(ClientBase):
    # По telegram_id бот узнаёт, кто ему пишет. Необязательное: админ может завести
    # клиента вручную (того, кто позвонил по телефону), без Telegram.
    telegram_id: int | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    telegram_id: int | None = None


class ClientOut(ClientBase):
    id: int
    telegram_id: int | None = None

    model_config = ConfigDict(from_attributes=True)
