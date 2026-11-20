from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentProviderEnum, PaymentStatusEnum


class PaymentBase(BaseModel):
    appointment_id: int
    amount: Decimal
    provider: PaymentProviderEnum = PaymentProviderEnum.TELEGRAM


class PaymentCreate(PaymentBase):
    """Создание намерения предоплаты. provider_payment_id и статус задаёт сервер/провайдер."""


class PaymentUpdate(BaseModel):
    """Обновление статуса платежа (по webhook провайдера).

    status обязан быть передан; provider_payment_id и paid_at проставляются при PAID.
    """

    status: PaymentStatusEnum
    provider_payment_id: str | None = None
    paid_at: datetime | None = None


class PaymentOut(PaymentBase):
    id: int
    status: PaymentStatusEnum
    provider_payment_id: str | None = None
    paid_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
