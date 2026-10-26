from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseORM

if TYPE_CHECKING:
    from app.models.master import MasterORM


class WorkingHourORM(BaseORM):
    """Один рабочий интервал мастера в определённый день недели.

    Расписание — это повторяющаяся недельная сетка. Обеденный перерыв не хранится отдельно:
    если мастер работает 10:00-14:00 и 15:00-19:00, это две строки, а перерыв — промежуток
    между ними.

    Важно: start_time и end_time — «настенное» время салона (Time без часового пояса).
    Расписание «с 10 до 19» означает одно и то же независимо от даты и перехода на летнее
    время. В UTC мы будем переводить его уже при расчёте конкретных слотов.
    """

    __tablename__ = "working_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),  # 0 = понедельник
        CheckConstraint("end_time > start_time", name="end_after_start"),
        # Явное имя: автоматическое учло бы только первую колонку и вводило бы в заблуждение.
        UniqueConstraint(
            "master_id", "weekday", "start_time", name="uq_working_hours_master_weekday_start"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE: расписание принадлежит мастеру и не имеет смысла без него.
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    master: Mapped["MasterORM"] = relationship(back_populates="working_hours")
