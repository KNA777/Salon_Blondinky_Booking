from app.models import AppointmentORM
from app.patterns.mapper.appointments import AppointmentMapper
from app.patterns.repository.base import BaseRepository


class AppointmentRepository(BaseRepository):
    model = AppointmentORM
    mapper = AppointmentMapper
