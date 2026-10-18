import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.master import Master
    from app.models.service import Service


class AppointmentStatus(enum.StrEnum):
    CREATED = "created"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Appointment(CreatedAtMixin, Base):
    """Запись клиента к мастеру на услугу: центральная таблица, она ссылается на остальные."""

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ends_after_starts"),
        # Чаще всего нужны записи конкретного мастера на конкретный день. Составной индекс
        # (мастер, начало) отвечает на такой запрос без просмотра всей таблицы.
        Index("ix_appointments_master_id_starts_at", "master_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # RESTRICT: БД не позволит удалить мастера, клиента или услугу, у которых есть записи.
    # История важнее удобства удаления; для скрытия есть is_active.
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="RESTRICT"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"))

    # Время всегда с часовым поясом (см. type_annotation_map в base.py), храним в UTC.
    starts_at: Mapped[datetime]
    # ends_at считаем при создании записи: starts_at + длительность услуги. Если услугу потом
    # сделают длиннее, уже созданные записи не должны «поехать».
    ends_at: Mapped[datetime]

    # По той же причине храним цену на момент записи, а не берём её из услуги.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # native_enum=False: храним статус обычной строкой (VARCHAR), а не типом ENUM Postgres.
    # Нативный ENUM неудобно менять: добавление статуса требует отдельной команды ALTER TYPE,
    # а Alembic такие изменения сам не замечает.
    # values_callable: в БД пишем "no_show", а не "NO_SHOW" (имя члена Python-перечисления).
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=AppointmentStatus.CREATED,
        server_default=AppointmentStatus.CREATED.value,
    )

    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="appointments")
    master: Mapped["Master"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments")
