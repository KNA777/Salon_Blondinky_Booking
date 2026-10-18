"""Все модели импортируются здесь.

Это не просто удобство. Таблица попадает в Base.metadata только в момент, когда Python
выполнил файл с её моделью. Если какую-то модель нигде не импортировать, Alembic её не
увидит и автогенерация миграции «забудет» создать таблицу. Поэтому любой код, которому нужны
все таблицы (Alembic, тесты), делает `import app.models`.
"""

from app.models.appointment import Appointment, AppointmentStatus
from app.models.base import Base
from app.models.client import Client
from app.models.master import Master
from app.models.master_service import master_services
from app.models.service import Service
from app.models.working_hour import WorkingHour

__all__ = [
    "Appointment",
    "AppointmentStatus",
    "Base",
    "Client",
    "Master",
    "Service",
    "WorkingHour",
    "master_services",
]
