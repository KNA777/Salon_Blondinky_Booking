"""Все модели импортируются здесь.

Это не просто удобство. Таблица попадает в Base.metadata только в момент, когда Python
выполнил файл с её моделью. Если какую-то модель нигде не импортировать, Alembic её не
увидит и автогенерация миграции «забудет» создать таблицу. Поэтому любой код, которому нужны
все таблицы (Alembic, тесты), делает `import app.models`.
"""

from app.models.appointment import AppointmentORM, AppointmentStatusEnum
from app.models.base import BaseORM
from app.models.client import ClientORM
from app.models.master import MasterORM
from app.models.master_service import master_services
from app.models.service import ServiceORM
from app.models.working_hour import WorkingHourORM

__all__ = [
    "AppointmentORM",
    "AppointmentStatusEnum",
    "BaseORM",
    "ClientORM",
    "MasterORM",
    "ServiceORM",
    "WorkingHourORM",
    "master_services",
]
