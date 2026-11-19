from app.models import AppointmentORM
from app.patterns.mapper.base import MapperBase
from app.schemas.appointment import AppointmentOut


class AppointmentMapper(MapperBase):
    schema = AppointmentOut
    model = AppointmentORM
