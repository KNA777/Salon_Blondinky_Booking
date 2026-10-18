from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

# Эти импорты нужны только для подсказок типов. Если импортировать модели друг в друга
# по-настоящему, получится циклический импорт (Master -> Appointment -> Master).
if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.service import Service
    from app.models.working_hour import WorkingHour


class Master(CreatedAtMixin, Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(32))  # `| None` = колонка nullable

    # Идентификаторы Telegram уже не помещаются в обычный 32-битный int, нужен BigInteger.
    # unique: один Telegram-аккаунт не может принадлежать двум мастерам.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)

    # Мастера не удаляем, а скрываем: на него ссылается история записей.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    # secondary="master_services": связь «многие ко многим» идёт через эту таблицу.
    services: Mapped[list["Service"]] = relationship(
        secondary="master_services", back_populates="masters"
    )
    working_hours: Mapped[list["WorkingHour"]] = relationship(back_populates="master")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="master")
