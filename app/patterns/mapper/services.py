from app.models import ServiceORM
from app.patterns.mapper.base import MapperBase
from app.schemas.service import ServiceOut


class ServiceMapper(MapperBase):
    schema = ServiceOut
    model = ServiceORM
