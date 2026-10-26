from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Имена ограничений и индексов задаём по единому правилу. Без этого Postgres придумывает
# имена сам, и Alembic потом не может надёжно изменить или удалить ограничение по имени.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseORM(DeclarativeBase):
    """Общий родитель всех моделей. Именно в Base.metadata хранится описание всех таблиц:
    по нему Alembic строит миграции."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Любое поле Mapped[datetime] автоматически становится timestamptz, то есть временем
    # с часовым поясом. Так нельзя случайно создать «наивное» время без пояса.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class CreatedAtMixin:
    """Добавляет моделям поле created_at. Время проставляет сама БД (server_default),
    поэтому оно корректно, даже если запись создана не из нашего кода."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
