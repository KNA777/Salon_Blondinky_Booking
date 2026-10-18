from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class Client(CreatedAtMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(32))

    # По telegram_id бот узнаёт, кто ему пишет. Поле необязательное, потому что администратор
    # может завести клиента вручную (например, того, кто позвонил по телефону).
    # В unique-колонке Postgres допускает много NULL, так что таких клиентов может быть много.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)

    appointments: Mapped[list["Appointment"]] = relationship(back_populates="client")
