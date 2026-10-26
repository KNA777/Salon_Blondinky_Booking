"""Проверка, что модели описаны корректно. База данных для этих тестов не нужна."""

from sqlalchemy.orm import configure_mappers

from app.models import BaseORM


def test_all_tables_registered():
    # Если новую модель забыли импортировать в app/models/__init__.py, она не попадёт
    # в metadata, и этот тест упадёт.
    assert set(BaseORM.metadata.tables) == {
        "masters",
        "services",
        "master_services",
        "clients",
        "working_hours",
        "appointments",
    }


def test_relationships_are_consistent():
    # configure_mappers связывает relationship между собой. Опечатка в имени класса или в
    # back_populates проявится здесь как ошибка, а не в середине работы приложения.
    configure_mappers()
