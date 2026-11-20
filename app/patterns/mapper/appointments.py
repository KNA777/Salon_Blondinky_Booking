from app.models import AppointmentORM
from app.patterns.mapper.base import MapperBase
from app.schemas.appointment import AppointmentOut


class AppointmentMapper(MapperBase[AppointmentOut]):
    schema = AppointmentOut
    model = AppointmentORM
