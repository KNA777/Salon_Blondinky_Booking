from app.models import MasterORM
from app.patterns.mapper.base import MapperBase
from app.schemas.master import MasterOut


class MasterMapper(MapperBase):
    schema = MasterOut
    model = MasterORM
