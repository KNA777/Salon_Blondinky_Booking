from sqlalchemy import insert, select

from app.models import WorkingHourORM
from app.patterns.mapper.working_hours import WorkingHourMapper
from app.patterns.repository.base import BaseRepository
from app.schemas.working_hour import WorkingHourCreate, WorkingHourOut


class WorkingHourRepository(BaseRepository[WorkingHourOut]):
    model = WorkingHourORM
    mapper = WorkingHourMapper

    async def get_by_master(self, master_id: int) -> list[WorkingHourOut]:
        """Рабочие часы мастера, отсортированные по дню недели и времени начала."""
        query = (
            select(self.model)
            .where(self.model.master_id == master_id)
            .order_by(self.model.weekday, self.model.start_time)
        )
        data = await self.session.execute(query)
        return [self.mapper.from_alchemy_to_schema(el) for el in data.scalars().all()]

    async def create_for_master(self, master_id: int, data: WorkingHourCreate) -> WorkingHourOut:
        """Создать один рабочий интервал для мастера."""
        stmt = (
            insert(self.model)
            .values(master_id=master_id, **data.model_dump())
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        obj = result.scalars().one()
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(obj)
