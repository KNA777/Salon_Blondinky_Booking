from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.api.deps import DBDep
from app.core.config import get_settings
from app.schemas.slot import FreeSlotsOut
from app.services.slots import get_free_slots

router = APIRouter(prefix="/masters", tags=["Slots"])


@router.get("/{master_id}/free-slots", response_model=FreeSlotsOut)
async def free_slots(
    db: DBDep,
    master_id: int,
    service_id: int,
    datetime: date,
    step_minutes: int = Query(default=30, ge=1, le=1440),
) -> FreeSlotsOut:
    """Свободные слоты мастера на услугу на конкретную дату.

    step_minutes — шаг, с которым генерируются начала слотов (по умолчанию 30 минут).
    """
    salon_tz = ZoneInfo(get_settings().salon_timezone)
    return await get_free_slots(db, master_id, service_id, datetime, step_minutes, salon_tz)
