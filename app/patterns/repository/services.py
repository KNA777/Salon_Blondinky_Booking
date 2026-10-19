from app.models import Service
from app.patterns.mapper.services import ServiceMapper
from app.patterns.repository.base import BaseRepository


class ServiceRepository(BaseRepository):

    model = Service
    mapper = ServiceMapper


