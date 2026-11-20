from app.models import PaymentORM
from app.patterns.mapper.base import MapperBase
from app.schemas.payment import PaymentOut


class PaymentMapper(MapperBase[PaymentOut]):
    """Маппер платежей: ORM <-> PaymentOut."""

    schema = PaymentOut
    model = PaymentORM
