from sqlalchemy import select

from app.models import ServiceORM
from app.patterns.mapper.services import ServiceMapper
from app.patterns.repository.base import BaseRepository


class ServiceRepository(BaseRepository):
    model = ServiceORM
    mapper = ServiceMapper

    async def get_all_active_services_bulk(self, include_inactive: bool):
        query = select(self.model)
        if not include_inactive:
            query = query.where(self.model.is_active)
        data = await self.session.execute(query)
        return [self.mapper.from_alchemy_to_schema(el) for el in data.scalars().all()]
