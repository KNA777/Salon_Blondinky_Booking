from fastapi import APIRouter, Query

from app.api.deps import CurrentAdminDep, DBDep
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate

router = APIRouter(prefix="/services", tags=["Services"])


@router.post("")
async def add_service(db: DBDep, data: ServiceCreate, _admin: CurrentAdminDep) -> ServiceOut:
    """Создать услугу (только админ)."""
    return await db.services.create(data)


@router.get("")
async def get_active_services_bulk(
    db: DBDep, include_inactive: bool = Query(default=False)
) -> list[ServiceOut]:
    """Вернуть список услуг (активных, либо всех при include_inactive)."""
    return await db.services.get_all_active_services_bulk(include_inactive)


@router.get("/{service_id}")
async def get_service_by_id(db: DBDep, service_id: int) -> ServiceOut:
    """Вернуть одну услугу по её id."""
    return await db.services.get_one_by_id(id=service_id)


@router.post("/{service_id}")
async def service_is_active_on_false(
    db: DBDep, service_id: int, _admin: CurrentAdminDep
) -> dict[str, str]:
    """Деактивировать услугу (только админ)."""
    await db.services.is_active_false(service_id)
    return {"status": "OK"}


@router.patch("/{service_id}")
async def service_partial_change(
    db: DBDep, service_id: int, data: ServiceUpdate, _admin: CurrentAdminDep
) -> ServiceOut:
    """Изменить услугу (только админ)."""
    return await db.services.change_object(data, id=service_id, exclude_unset=True)
