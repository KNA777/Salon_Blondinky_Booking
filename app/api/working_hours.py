from fastapi import APIRouter

from app.api.deps import DBDep
from app.schemas.working_hour import WorkingHourCreate, WorkingHourUpdate

router = APIRouter(tags=["Working Hours"])


@router.get("/masters/{master_id}/working-hours")
async def get_working_hours(db: DBDep, master_id: int):
    return await db.working_hours.get_by_master(master_id)


@router.post("/masters/{master_id}/working-hours")
async def add_working_hour(db: DBDep, master_id: int, data: WorkingHourCreate):
    return await db.working_hours.create_for_master(master_id, data)


@router.patch("/masters/{master_id}/working-hours/{working_hour_id}")
async def change_working_hour(
    db: DBDep,
    master_id: int,
    working_hour_id: int,
    data: WorkingHourUpdate,
):
    return await db.working_hours.change_object(
        data,
        id=working_hour_id,
        master_id=master_id,
        exclude_unset=True,
    )


@router.delete("/masters/{master_id}/working-hours/{working_hour_id}")
async def remove_working_hour(db: DBDep, master_id: int, working_hour_id: int):
    await db.working_hours.delete(id=working_hour_id, master_id=master_id)
    return {"status": "OK"}
