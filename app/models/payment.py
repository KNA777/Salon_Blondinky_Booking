import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseORM, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.appointment import AppointmentORM


class PaymentStatusEnum(enum.StrEnum):
    """Жизненный цикл платежа (каркас — задача 18).

    pending — создан, ждёт оплаты;
    paid — оплачен (подтверждён провайдером);
    failed — оплата не прошла;
    refunded — возврат средств.
    """

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProviderEnum(enum.StrEnum):
    """Поддерживаемые платёжные провайдеры.

    Каркас хранит название провайдера строкой, чтобы легко добавить нового без миграции
    enum-типа БД. Сейчас заявлен Telegram Payments — реальная оплата будет через
    sendInvoice/успешный webhook провайдера, а здесь фиксируется факт и сумма предоплаты.
    """

    TELEGRAM = "telegram_payments"
    YOOKASSA = "yookassa"


class PaymentORM(CreatedAtMixin, BaseORM):
    """Предоплата за запись (задача 18, каркас).

    Одна запись может иметь одну активную предоплату. Сумма по умолчанию берётся из цены
    услуги на момент записи, но хранится отдельно, чтобы провайдер/скидки не влияли на
    аудит. Статус меняется по событиям платёжного провайдера.
    """

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # RESTRICT как и у appointments: историю оплат не удаляем вместе с записью.
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="RESTRICT"))

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Средства идентификации платежа у провайдера (invoice_id Telegram / payment_id ЮKassa).
    # Nullable: создаём запись о намерении оплатить до того, как провайдер выдаст id.
    provider_payment_id: Mapped[str | None] = mapped_column(String(128))

    provider: Mapped[PaymentProviderEnum] = mapped_column(
        Enum(
            PaymentProviderEnum,
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PaymentProviderEnum.TELEGRAM,
    )

    status: Mapped[PaymentStatusEnum] = mapped_column(
        Enum(
            PaymentStatusEnum,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PaymentStatusEnum.PENDING,
        server_default=PaymentStatusEnum.PENDING.value,
    )

    # Webhook провайдера может прийти с опозданием; фиксируем момент смены статуса.
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)

    appointment: Mapped["AppointmentORM"] = relationship(back_populates="payment")
