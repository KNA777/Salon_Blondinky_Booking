from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import BaseModel
from sqlalchemy import Table, delete, insert, select, update

from app.core.exceptions import NotFoundError
from app.patterns.mapper.base import MapperBase

# Тип схемы Pydantic (DTO наружу). ORM-модель типизируем как Any — см. комментарий в
# app/patterns/mapper/base.py.


class BaseRepository[SchemaT: BaseModel]:
    """Базовый репозиторий поверх SQLAlchemy.

    Конкретные репозитории наследуют его с конкретной схемой (`BaseRepository[ClientOut]`),
    поэтому методы `create`/`get_one_by_id`/`change_object` возвращают именно её, а не
    абстрактный `BaseModel`.
    """

    model: ClassVar[Any]
    mapper: ClassVar[type[MapperBase[SchemaT]]]

    def __init__(self, session):
        self.session = session

    async def create(self, data: BaseModel) -> SchemaT:
        stmt = insert(self.model).values(**data.model_dump()).returning(self.model)
        result = await self.session.execute(stmt)
        data = result.scalars().one()
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(data)

    async def get_data_bulk(self) -> list[SchemaT]:
        query = select(self.model)
        data = await self.session.execute(query)
        return [self.mapper.from_alchemy_to_schema(el) for el in data.scalars().all()]

    async def get_one_by_id(self, **filter_by) -> SchemaT:
        query = select(self.model).filter_by(**filter_by)
        result = await self.session.execute(query)
        data = result.scalars().first()
        if data is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        return self.mapper.from_alchemy_to_schema(data)

    async def is_active_false(self, obj_id) -> None:
        stmt = (
            update(self.model).filter_by(id=obj_id).values(is_active=False).returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        if result.scalars().first() is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        await self.session.commit()

    async def change_object(
        self, data: BaseModel, exclude_unset: bool = False, **filter_by
    ) -> SchemaT:
        stmt = (
            update(self.model)
            .filter_by(**filter_by)
            .values(**data.model_dump(exclude_unset=exclude_unset))
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        obj = result.scalars().first()
        if obj is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(obj)

    async def delete(self, **filter_by) -> None:
        stmt = delete(self.model).filter_by(**filter_by).returning(self.model.id)
        result = await self.session.execute(stmt)
        if result.scalars().first() is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        await self.session.commit()

    async def add_data_bulk(self, data: Sequence[BaseModel], table: Table | None = None) -> None:
        target_table = table if table is not None else self.model
        stmt = insert(target_table).values([item.model_dump() for item in data])
        await self.session.execute(stmt)
