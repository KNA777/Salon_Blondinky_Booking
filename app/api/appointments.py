from fastapi import APIRouter

from app.api.deps import DBDep
from app.schemas.appointment import AppointmentCreate, AppointmentStatusUpdate, AppointmentUpdate

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.post("")
async def add_appointment(db: DBDep, data: AppointmentCreate):
    """Создать запись. Статус по умолчанию created (см. server_default в модели)."""
    return await db.appointments.create(data)


@router.get("")
async def get_appointments_bulk(
    db: DBDep, client_id: int | None = None, master_id: int | None = None
):
    """Список записей. Можно фильтровать по клиенту или мастеру."""
    if client_id is not None:
        return await db.appointments.get_bulk_by_client(client_id)
    if master_id is not None:
        return await db.appointments.get_bulk_by_master(master_id)
    return await db.appointments.get_data_bulk()


@router.get("/{appointment_id}")
async def get_appointment_by_id(db: DBDep, appointment_id: int):
    return await db.appointments.get_one_by_id(id=appointment_id)


@router.patch("/{appointment_id}")
async def appointment_partial_change(db: DBDep, appointment_id: int, data: AppointmentUpdate):
    """Изменить время/статус записи. Статус здесь меняется через машину переходов."""
    return await db.appointments.change_object(data, id=appointment_id, exclude_unset=True)


@router.post("/{appointment_id}/status")
async def change_appointment_status(
    db: DBDep, appointment_id: int, data: AppointmentStatusUpdate
):
    """Перевести запись в новый статус с проверкой допустимости перехода (машина).

    Запрещённый переход (например, completed -> created) вернёт HTTP 409.
    """
    return await db.appointments.transition_status(appointment_id, data.status)
