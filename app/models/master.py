from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseORM, CreatedAtMixin

# Эти импорты нужны только для подсказок типов. Если импортировать модели друг в друга
# по-настоящему, получится циклический импорт (Master -> Appointment -> Master).
if TYPE_CHECKING:
    from app.models.appointment import AppointmentORM
    from app.models.service import ServiceORM
    from app.models.working_hour import WorkingHourORM


class MasterORM(CreatedAtMixin, BaseORM):
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
    services: Mapped[list["ServiceORM"]] = relationship(
        secondary="master_services", back_populates="masters"
    )
    working_hours: Mapped[list["WorkingHourORM"]] = relationship(back_populates="master")
    appointments: Mapped[list["AppointmentORM"]] = relationship(back_populates="master")
