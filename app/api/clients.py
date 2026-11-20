from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentAdminDep, CurrentClientDep, DBDep
from app.schemas.client import ClientCreate, ClientOut, ClientUpdate

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("")
async def add_client(db: DBDep, data: ClientCreate) -> ClientOut:
    """Создать клиента. Если передан telegram_id и такой клиент уже есть — вернуть его.

    Upsert нужен боту: повторный /start не должен плодить дубли, а должен найти
    существующего клиента по telegram_id (см. ClientRepository.upsert_by_telegram_id).
    """
    if data.telegram_id is not None:
        return await db.clients.upsert_by_telegram_id(data)
    return await db.clients.create(data)


@router.get("")
async def get_clients_bulk(
    db: DBDep, _admin: CurrentAdminDep, telegram_id: int | None = Query(default=None)
) -> list[ClientOut]:
    """Список клиентов (только админ — это персональные данные).

    Если задан telegram_id — вернуть одного клиента или пустой список.
    Эндпоинт закрыт для не-админов: он возвращает имена и телефоны всех клиентов.
    """
    if telegram_id is not None:
        client = await db.clients.get_by_telegram_id(telegram_id)
        return [client] if client is not None else []
    return await db.clients.get_data_bulk()


@router.get("/{client_id}")
async def get_client_by_id(
    db: DBDep, client_id: int, current_client: CurrentClientDep
) -> ClientOut:
    """Получить клиента по id (только владелец или админ).

    Клиент видит свою карточку; чужую — только админ. Иначе 403 (не выдаём чужую
    персональную информацию).
    """
    if not current_client.is_admin and current_client.id != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для просмотра этого клиента",
        )
    return await db.clients.get_one_by_id(id=client_id)


@router.patch("/{client_id}")
async def client_partial_change(
    db: DBDep,
    client_id: int,
    data: ClientUpdate,
    current_client: CurrentClientDep,
) -> ClientOut:
    """Изменить клиента (только владелец или админ).

    Клиент правит свою карточку (имя/телефон), чужую — только админ. Иначе 403.
    """
    if not current_client.is_admin and current_client.id != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения этого клиента",
        )
    return await db.clients.change_object(data, id=client_id, exclude_unset=True)
