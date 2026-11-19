from datetime import date, datetime

from pydantic import BaseModel


class FreeSlot(BaseModel):
    """Один свободный интервал: начало и конец в часовом поясе салона."""

    starts_at: datetime
    ends_at: datetime


class FreeSlotsOut(BaseModel):
    master_id: int
    service_id: int
    date: date
    timezone: str
    slots: list[FreeSlot]
