from typing import Any, ClassVar

from pydantic import BaseModel

# Тип схемы Pydantic (DTO наружу). ORM-модель SQLAlchemy типизируем как Any: без
# sqlalchemy mypy-плагина типы колонок (`Mapped[int]` и т.п.) не раскрываются, поэтому
# точное структурное описание модели дало бы ложные ошибки, а не пользу.


class MapperBase[SchemaT: BaseModel]:
    """Базовый маппер между ORM-моделью и Pydantic-схемой.

    Конкретные мапперы задают `schema` (тип схемы) и `model` (класс ORM) как ClassVar.
    Благодаря дженерику `from_alchemy_to_schema` возвращает именно `SchemaT` (например
    `ClientOut`), а не абстрактный `BaseModel`.
    """

    schema: ClassVar[type[SchemaT]]
    model: ClassVar[Any]

    @classmethod
    def from_alchemy_to_schema(cls, data: Any) -> SchemaT:
        return cls.schema.model_validate(data, from_attributes=True)

    @classmethod
    def from_schema_to_alchemy(cls, data: BaseModel) -> Any:
        return cls.model(**data.model_dump())
