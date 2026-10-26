from app.models import WorkingHourORM
from app.patterns.mapper.base import MapperBase
from app.schemas.working_hour import WorkingHourOut


class WorkingHourMapper(MapperBase):
    schema = WorkingHourOut
    model = WorkingHourORM
