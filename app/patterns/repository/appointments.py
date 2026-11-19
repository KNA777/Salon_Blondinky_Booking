from sqlalchemy import select, update

from app.core.exceptions import NotFoundError
from app.models import AppointmentORM, AppointmentStatusEnum
from app.patterns.mapper.appointments import AppointmentMapper
from app.patterns.repository.base import BaseRepository
from app.services.status_machine import validate_transition


class AppointmentRepository(BaseRepository):
    model = AppointmentORM
    mapper = AppointmentMapper

    async def get_bulk_by_client(self, client_id: int):
        """Все записи клиента (для личного кабинета / истории)."""
        result = await self.session.execute(
            select(self.model).filter_by(client_id=client_id)
        )
        return [self.mapper.from_alchemy_to_schema(el) for el in result.scalars().all()]

    async def get_bulk_by_master(self, master_id: int):
        """Все записи мастера (для просмотра расписания админом)."""
        result = await self.session.execute(
            select(self.model).filter_by(master_id=master_id)
        )
        return [self.mapper.from_alchemy_to_schema(el) for el in result.scalars().all()]

    async def transition_status(
        self, appointment_id: int, next_status: AppointmentStatusEnum
    ):
        """Перевести запись в новый статус, проверив допустимость перехода.

        Сначала валидируем граф (status_machine), и только потом обновляем запись.
        Если переход запрещён, кидаем InvalidTransitionError до записи в БД.
        """
        result = await self.session.execute(
            select(self.model).filter_by(id=appointment_id)
        )
        appointment = result.scalars().first()
        if appointment is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")

        validate_transition(appointment.status, next_status)

        stmt = (
            update(self.model)
            .filter_by(id=appointment_id)
            .values(status=next_status)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        updated = result.scalars().one()
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(updated)
