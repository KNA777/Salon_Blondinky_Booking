from fastapi import APIRouter, Query

from app.api.deps import DBDep
from app.schemas.master import MasterCreate, MasterUpdate

router = APIRouter(prefix="/masters", tags=["Masters"])


@router.post("")
async def add_master(db: DBDep, data: MasterCreate):
    return await db.masters.create_master_with_services(data)


@router.get("")
async def get_active_masters_bulk(db: DBDep, include_inactive: bool = Query(default=False)):
    return await db.masters.get_all_active_masters_bulk(include_inactive)


@router.get("/{master_id}")
async def get_master_by_id(db: DBDep, master_id: int):
    return await db.masters.get_one_by_id(id=master_id)


@router.post("/{master_id}")
async def master_is_active_on_false(db: DBDep, master_id: int):
    await db.masters.is_active_false(master_id)
    return {"status": "OK"}


@router.patch("/{master_id}")
async def master_partial_change(db: DBDep, master_id: int, data: MasterUpdate):
    return await db.masters.change_object(data, id=master_id, exclude_unset=True)
