from app.models import ClientORM
from app.patterns.mapper.base import MapperBase
from app.schemas.client import ClientOut


class ClientMapper(MapperBase[ClientOut]):
    """Маппер клиентов: ORM <-> ClientOut."""

    schema = ClientOut
    model = ClientORM
