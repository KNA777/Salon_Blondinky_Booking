from typing import Any

from sqlalchemy import select

from app.core.security import hash_password
from app.models import ClientORM
from app.patterns.mapper.clients import ClientMapper
from app.patterns.repository.base import BaseRepository
from app.schemas.client import ClientCreate, ClientOut


class ClientRepository(BaseRepository[ClientOut]):
    model = ClientORM
    mapper = ClientMapper

    async def get_by_telegram_id(self, telegram_id: int) -> ClientOut | None:
        """Найти клиента по telegram_id или вернуть None (бот проверяет, регистрировать ли)."""
        result = await self.session.execute(
            select(self.model).where(self.model.telegram_id == telegram_id)
        )
        obj = result.scalars().first()
        if obj is None:
            return None
        return self.mapper.from_alchemy_to_schema(obj)

    async def upsert_by_telegram_id(self, data: ClientCreate) -> ClientOut:
        """Создать клиента. Если telegram_id уже есть — вернуть существующего (без дубля).

        unique-ограничение на telegram_id не дало бы вставить дубль, но тогда повторный
        /start упал бы с IntegrityError. Бот должен его переживать спокойно, поэтому
        сначала ищем существующего клиента.
        """
        if data.telegram_id is not None:
            existing = await self.get_by_telegram_id(data.telegram_id)
            if existing is not None:
                return existing
        return await self.create(data)

    async def get_by_phone(self, phone: str) -> ClientORM | None:
        """Найти клиента по телефону (для входа). Возвращает ORM-объект — нужен password_hash."""
        result = await self.session.execute(select(self.model).where(self.model.phone == phone))
        return result.scalars().first()

    async def create_with_password(self, data: ClientCreate, password: str) -> ClientOut:
        """Создать клиента с учётной записью: пароль хешируется и сохраняется в BCrypt."""
        payload = data.model_dump()
        payload["password_hash"] = hash_password(password)
        return await self.create_from_mapping(payload)

    async def create_from_mapping(self, payload: dict[str, Any]) -> ClientOut:
        """Создать клиента из словаря (нужно для полей, которых нет в схеме ClientCreate)."""
        obj = self.model(**payload)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return self.mapper.from_alchemy_to_schema(obj)
