from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, PermissionError, SlotConflictError
from app.models import AppointmentORM, AppointmentStatusEnum
from app.patterns.mapper.appointments import AppointmentMapper
from app.patterns.repository.base import BaseRepository
from app.schemas.appointment import AppointmentCreate, AppointmentOut
from app.services.booking_conflict import BLOCKING_STATUSES, overlaps
from app.services.status_machine import validate_transition


class AppointmentRepository(BaseRepository[AppointmentOut]):
    model = AppointmentORM
    mapper = AppointmentMapper

    async def get_bulk_by_client(self, client_id: int) -> list[AppointmentOut]:
        """Все записи клиента (для личного кабинета / истории)."""
        result = await self.session.execute(select(self.model).filter_by(client_id=client_id))
        return [self.mapper.from_alchemy_to_schema(el) for el in result.scalars().all()]

    async def get_bulk_by_master(self, master_id: int) -> list[AppointmentOut]:
        """Все записи мастера (для просмотра расписания админом)."""
        result = await self.session.execute(select(self.model).filter_by(master_id=master_id))
        return [self.mapper.from_alchemy_to_schema(el) for el in result.scalars().all()]

    async def get_by_day(self, day_start: datetime, day_end: datetime) -> list[AppointmentOut]:
        """Все записи, пересекающиеся с интервалом [day_start, day_end).

        Используется для админского просмотра расписания на день. day_start/day_end —
        aware datetime в UTC (границы дня в часовом поясе салона). Возвращает записи,
        отсортированные по началу.
        """
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.starts_at < day_end,
                self.model.ends_at > day_start,
            )
            .order_by(self.model.starts_at)
        )
        return [self.mapper.from_alchemy_to_schema(el) for el in result.scalars().all()]

    async def get_due_reminders(
        self,
        marker: Any,
        now: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> list[AppointmentORM]:
        """Записи, которым пора отправить напоминание (задача 13).

        Отбираем записи в блокирующих статусах (created/confirmed), чьё starts_at попадает
        в окно [window_start, window_end], и у которых ещё не проставлен соответствующий
        marker (reminded_24h_at / reminded_2h_at). Наличие маркера и есть идемпотентность:
        повторный запуск планировщика не вернёт уже отправленные записи.

        marker — колонка модели (self.model.reminded_24h_at и т.п.); его же передаём в
        mark_reminder_sent() для отметки после успешной отправки.
        """
        result = await self.session.execute(
            select(self.model)
            .options(
                selectinload(self.model.client),
                selectinload(self.model.master),
                selectinload(self.model.service),
            )
            .where(
                self.model.status.in_(BLOCKING_STATUSES),
                marker.is_(None),
                self.model.starts_at >= window_start,
                self.model.starts_at < window_end,
            )
            .order_by(self.model.starts_at)
        )
        return list(result.scalars().all())

    async def mark_reminder_sent(self, appointment_id: int, marker: Any, sent_at: datetime) -> None:
        """Проставляет момент отправки напоминания, чтобы не слать его повторно.

        marker — колонка reminded_24h_at / reminded_2h_at. Обновляем только если она ещё
        NULL, чтобы конкурентный запуск не перезаписал отметку (UPDATE ... WHERE is NULL).
        """
        await self.session.execute(
            update(self.model)
            .where(self.model.id == appointment_id, marker.is_(None))
            .values({marker: sent_at})
        )
        await self.session.commit()

    async def _conflicting_appointments(
        self, master_id: int, starts_at: datetime, ends_at: datetime
    ) -> list[AppointmentORM]:
        """Записи того же мастера в блокирующих статусах, пересекающиеся с интервалом.

        Выборка происходит по мастеру и статусам; точное пересечение проверяем в Python
        через overlaps(). Этого достаточно для быстрой проверки до вставки.
        """
        result = await self.session.execute(
            select(self.model).where(
                self.model.master_id == master_id,
                self.model.status.in_(BLOCKING_STATUSES),
                self.model.starts_at < ends_at,
                self.model.ends_at > starts_at,
            )
        )
        return list(result.scalars().all())

    async def create_with_conflict_check(self, data: AppointmentCreate) -> AppointmentOut:
        """Создать запись, проверив, что слот свободен (защита от двойной записи).

        Проверяем пересечение с уже существующими записями мастера. Если слот занят,
        кидаем SlotConflictError (HTTP 409) до вставки. Саму вставку защищает также
        exclusion constraint в БД (миграция a1b2c3d4e5f6) на случай гонки.
        """
        existing = await self._conflicting_appointments(
            data.master_id, data.starts_at, data.ends_at
        )
        if any(overlaps(data.starts_at, data.ends_at, a.starts_at, a.ends_at) for a in existing):
            raise SlotConflictError()
        return await self.create(data)

    async def transition_status(
        self, appointment_id: int, next_status: AppointmentStatusEnum
    ) -> AppointmentOut:
        """Перевести запись в новый статус, проверив допустимость перехода.

        Сначала валидируем граф (status_machine), и только потом обновляем запись.
        Если переход запрещён, кидаем InvalidTransitionError до записи в БД.
        """
        result = await self.session.execute(select(self.model).filter_by(id=appointment_id))
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

    async def cancel(
        self, appointment_id: int, client_id: int, is_admin: bool = False
    ) -> AppointmentOut:
        """Отменить запись. Клиент отменяет ТОЛЬКО свою запись, админ — любую.

        Проверка владения: не-админ может отменить запись, только если её client_id
        совпадает с запрашивающим. Иначе — PermissionError (HTTP 403).
        """
        appointment = await self._get_appointment_or_404(appointment_id)
        self._ensure_owner(appointment, client_id, is_admin)
        return await self.transition_status(appointment_id, AppointmentStatusEnum.CANCELLED)

    async def reschedule(
        self,
        appointment_id: int,
        starts_at: datetime,
        ends_at: datetime,
        client_id: int,
        is_admin: bool = False,
    ) -> AppointmentOut:
        """Перенести запись на новое время. Клиент — только свою, админ — любую.

        Проверяем владение, затем что новое время не конфликтует с другими записями того же
        мастера (защита от двойной записи), и меняем starts_at/ends_at.
        """
        appointment = await self._get_appointment_or_404(appointment_id)
        self._ensure_owner(appointment, client_id, is_admin)

        conflicts = await self._conflicting_appointments(appointment.master_id, starts_at, ends_at)
        # Исключаем саму переносимую запись из проверки.
        others = [a for a in conflicts if a.id != appointment_id and a.status in BLOCKING_STATUSES]
        if any(overlaps(starts_at, ends_at, a.starts_at, a.ends_at) for a in others):
            raise SlotConflictError()

        stmt = (
            update(self.model)
            .filter_by(id=appointment_id)
            .values(starts_at=starts_at, ends_at=ends_at)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        updated = result.scalars().one()
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(updated)

    async def _get_appointment_or_404(self, appointment_id: int) -> AppointmentORM:
        """Загрузить запись по id или кинуть NotFoundError (404)."""
        result = await self.session.execute(select(self.model).filter_by(id=appointment_id))
        appointment = result.scalars().first()
        if appointment is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        return appointment

    @staticmethod
    def _ensure_owner(appointment: AppointmentORM, client_id: int, is_admin: bool) -> None:
        """Админ проходит всегда; клиент — только если запись его."""
        if is_admin:
            return
        if appointment.client_id != client_id:
            raise PermissionError(f"Запись {appointment.id} принадлежит другому клиенту")
