from sqlalchemy import Column, ForeignKey, Table

from app.models.base import Base

# Связующая таблица «мастер умеет услугу». Дополнительных полей у неё нет, поэтому это
# просто Table, а не отдельный класс-модель. Если позже понадобятся поля (например,
# индивидуальная цена мастера), её нужно будет превратить в полноценную модель.
#
# Составной первичный ключ (master_id + service_id) сам запрещает дубли: нельзя
# назначить мастеру одну и ту же услугу дважды.
#
# ondelete="CASCADE": если мастера или услугу всё же удалили, связи с ними удаляются вместе
# с ними. Историю записей это не затрагивает: там внешние ключи с RESTRICT.
master_services = Table(
    "master_services",
    Base.metadata,
    Column("master_id", ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)
