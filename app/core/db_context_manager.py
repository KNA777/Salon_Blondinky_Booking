from app.patterns.repository.masters import MasterRepository
from app.patterns.repository.services import ServiceRepository
from app.patterns.repository.working_hours import WorkingHourRepository


class DBManager:
    def __init__(self, session):
        self.session_factory = session

    async def __aenter__(self):
        self.session = self.session_factory()

        self.services = ServiceRepository(self.session)
        self.masters = MasterRepository(self.session)
        self.working_hours = WorkingHourRepository(self.session)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.rollback()
        await self.session.close()

    async def commit(self):
        await self.session.commit()
