from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload

from app.models import MasterORM, master_services
from app.patterns.mapper.masters import MasterMapper
from app.patterns.repository.base import BaseRepository
from app.schemas.master import MasterAdd, MasterCreate, MasterService


class MasterRepository(BaseRepository):
    model = MasterORM
    mapper = MasterMapper

    async def create_master_with_services(self, data: MasterCreate):
        stmt = (
            insert(self.model)
            .values(**MasterAdd(**data.model_dump()).model_dump())
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        master_id = result.scalar_one()
        if data.service_ids:
            data_services = [
                MasterService(master_id=master_id, service_id=s_id) for s_id in data.service_ids
            ]
            await self.add_data_bulk(data_services, table=master_services)
        await self.session.commit()

        query = (
            select(self.model).options(selectinload(self.model.services)).filter_by(id=master_id)
        )
        result = await self.session.execute(query)
        data = result.scalars().one()
        return self.mapper.from_alchemy_to_schema(data)

    async def get_all_active_masters_bulk(self, include_inactive: bool):
        query = select(self.model).options(selectinload(self.model.services))
        if not include_inactive:
            query = query.where(self.model.is_active)
        data = await self.session.execute(query)
        return [self.mapper.from_alchemy_to_schema(el) for el in data.scalars().all()]
