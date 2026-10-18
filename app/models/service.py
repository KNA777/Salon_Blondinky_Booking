from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Numeric, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.master import Master


class Service(Base):
    __tablename__ = "services"
    # CHECK-ограничения: БД сама не даст сохранить услугу с нулевой длительностью
    # или отрицательной ценой, даже если ошибка проскочит мимо кода приложения.
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int]  # длительность задана на уровне услуги
    # Деньги храним в Numeric (точное десятичное число), а не во float:
    # у float бывают ошибки округления вроде 0.1 + 0.2 = 0.30000000000000004.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    masters: Mapped[list["Master"]] = relationship(
        secondary="master_services", back_populates="services"
    )
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="service")
