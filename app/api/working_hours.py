from fastapi import APIRouter

from app.api.deps import CurrentAdminDep, DBDep
from app.schemas.working_hour import WorkingHourCreate, WorkingHourOut, WorkingHourUpdate

router = APIRouter(tags=["Working Hours"])


@router.get("/masters/{master_id}/working-hours")
async def get_working_hours(db: DBDep, master_id: int) -> list[WorkingHourOut]:
    """Вернуть рабочие часы мастера по его id."""
    return await db.working_hours.get_by_master(master_id)


@router.post("/masters/{master_id}/working-hours")
async def add_working_hour(
    db: DBDep, master_id: int, data: WorkingHourCreate, _admin: CurrentAdminDep
) -> WorkingHourOut:
    """Добавить рабочие часы мастеру (только админ)."""
    return await db.working_hours.create_for_master(master_id, data)


@router.patch("/masters/{master_id}/working-hours/{working_hour_id}")
async def change_working_hour(
    db: DBDep,
    master_id: int,
    working_hour_id: int,
    data: WorkingHourUpdate,
    _admin: CurrentAdminDep,
) -> WorkingHourOut:
    """Изменить рабочие часы (только админ)."""
    return await db.working_hours.change_object(
        data,
        id=working_hour_id,
        master_id=master_id,
        exclude_unset=True,
    )


@router.delete("/masters/{master_id}/working-hours/{working_hour_id}")
async def remove_working_hour(
    db: DBDep,
    master_id: int,
    working_hour_id: int,
    _admin: CurrentAdminDep,
) -> dict[str, str]:
    """Удалить рабочие часы (только админ)."""
    await db.working_hours.delete(id=working_hour_id, master_id=master_id)
    return {"status": "OK"}
