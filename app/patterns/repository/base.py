from pydantic import BaseModel
from sqlalchemy import insert

from app.patterns.mapper.base import MapperBase


class BaseRepository:
    model = None
    mapper = MapperBase

    def __init__(self, session):
        self.session = session

    async def create(self, data: BaseModel):
        stmt = insert(self.model).values(**data.model_dump()).returning(self.model)
        data = await self.session.execute(stmt)
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(data.scalars().one())
