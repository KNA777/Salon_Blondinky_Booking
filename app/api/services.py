from fastapi import APIRouter

from app.api.deps import DBDep
from app.schemas.service import ServiceCreate

router = APIRouter(prefix="/services")




@router.post("")
async def add_service(db: DBDep, data: ServiceCreate):
    data = await db.services.create(data)
    return data
