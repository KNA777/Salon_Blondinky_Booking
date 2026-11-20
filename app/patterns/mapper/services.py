from app.models import ServiceORM
from app.patterns.mapper.base import MapperBase
from app.schemas.service import ServiceOut


class ServiceMapper(MapperBase[ServiceOut]):
    """Маппер услуг: ORM <-> ServiceOut."""

    schema = ServiceOut
    model = ServiceORM
