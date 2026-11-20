from datetime import UTC, datetime

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.models import PaymentORM, PaymentStatusEnum
from app.patterns.mapper.payments import PaymentMapper
from app.patterns.repository.base import BaseRepository
from app.schemas.payment import PaymentCreate, PaymentOut, PaymentUpdate


class PaymentRepository(BaseRepository[PaymentOut]):
    """Репозиторий предоплат (задача 18, каркас).

    Управляет записью о предоплате к appointment. Реальную оплату выполняет провайдер
    (Telegram Payments / ЮKassa); здесь — факт, сумма и статус.
    """

    model = PaymentORM
    mapper = PaymentMapper

    async def get_by_appointment(self, appointment_id: int) -> PaymentOut | None:
        """Активная (последняя) предоплата по записи, если она есть."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.appointment_id == appointment_id)
            .order_by(self.model.id.desc())
        )
        obj = result.scalars().first()
        if obj is None:
            return None
        return self.mapper.from_alchemy_to_schema(obj)

    async def get_by_id(self, payment_id: int) -> PaymentOut:
        """Получить платёж по id или кинуть NotFoundError."""
        return await self.get_one_by_id(id=payment_id)

    async def get_by_appointment_and_id(self, payment_id: int) -> PaymentOut:
        """Получить платёж по id (для бота). Совместимый псевдоним get_by_id."""
        return await self.get_by_id(payment_id)

    async def create_payment(self, data: PaymentCreate) -> PaymentOut:
        """Создать намерение предоплаты в статусе pending.

        Сумму можно не задавать (тогда берём из тела вызова); каркас задаёт её явно в
        эндпоинте по цене услуги записи. Здесь просто фиксируем переданное.
        """
        return await self.create(data)

    async def update_payment_status(self, payment_id: int, data: PaymentUpdate) -> PaymentOut:
        """Обновить статус платежа (по webhook провайдера).

        При переходе в paid проставляем paid_at (текущий UTC), если он не передан явно.
        Идемпотентно по id: повторный webhook с тем же статусом не ломает состояние.
        """
        result = await self.session.execute(select(self.model).filter_by(id=payment_id))
        obj = result.scalars().first()
        if obj is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")

        values: dict[str, object] = {"status": data.status}
        if data.provider_payment_id is not None:
            values["provider_payment_id"] = data.provider_payment_id
        if data.status == PaymentStatusEnum.PAID:
            values["paid_at"] = data.paid_at or datetime.now(UTC)

        payment = await self.change_object_for_id(payment_id, values)
        return payment

    async def change_object_for_id(self, payment_id: int, values: dict[str, object]) -> PaymentOut:
        """Обновить строку платежа по произвольному набору значений и вернуть DTO."""
        from sqlalchemy import update

        stmt = update(self.model).filter_by(id=payment_id).values(**values).returning(self.model)
        result = await self.session.execute(stmt)
        obj = result.scalars().first()
        if obj is None:
            raise NotFoundError(f"{self.model.__tablename__} not found")
        await self.session.commit()
        return self.mapper.from_alchemy_to_schema(obj)
