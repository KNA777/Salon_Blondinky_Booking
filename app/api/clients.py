from fastapi import APIRouter, Query

from app.api.deps import DBDep
from app.schemas.client import ClientCreate, ClientUpdate

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("")
async def add_client(db: DBDep, data: ClientCreate):
    """Создать клиента. Если передан telegram_id и такой клиент уже есть — вернуть его.

    Upsert нужен боту: повторный /start не должен плодить дубли, а должен найти
    существующего клиента по telegram_id (см. ClientRepository.upsert_by_telegram_id).
    """
    if data.telegram_id is not None:
        return await db.clients.upsert_by_telegram_id(data)
    return await db.clients.create(data)


@router.get("")
async def get_clients_bulk(db: DBDep, telegram_id: int | None = Query(default=None)):
    """Список клиентов. Если задан telegram_id — вернуть одного клиента или 404."""
    if telegram_id is not None:
        client = await db.clients.get_by_telegram_id(telegram_id)
        return [client] if client is not None else []
    return await db.clients.get_data_bulk()


@router.get("/{client_id}")
async def get_client_by_id(db: DBDep, client_id: int):
    return await db.clients.get_one_by_id(id=client_id)


@router.patch("/{client_id}")
async def client_partial_change(db: DBDep, client_id: int, data: ClientUpdate):
    return await db.clients.change_object(data, id=client_id, exclude_unset=True)
