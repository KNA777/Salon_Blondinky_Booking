"""Тесты защиты от двойной записи (задача 9).

Чистая логика пересечения интервалов и определения конфликта — без БД.
Race-тест на сам exclusion constraint требует реального Postgres и покрывается
интеграционными тестами (задача 23); здесь проверяем алгоритм, на котором построена
проверка на уровне приложения.
"""

from datetime import UTC, datetime

from app.services.booking_conflict import has_conflict, overlaps

UTC = UTC


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, 20, hour, minute, tzinfo=UTC)


def test_overlaps_fully_inside():
    assert overlaps(_dt(10), _dt(11), _dt(10, 30), _dt(10, 45))


def test_overlaps_partial_left():
    # новый [9:30, 10:30] пересекается с занятым [10:00, 11:00]
    assert overlaps(_dt(9, 30), _dt(10, 30), _dt(10), _dt(11))


def test_overlaps_partial_right():
    assert overlaps(_dt(10, 30), _dt(11, 30), _dt(10), _dt(11))


def test_overlaps_disjoint():
    assert not overlaps(_dt(9), _dt(9, 45), _dt(10), _dt(11))


def test_overlaps_adjacent_not_overlapping():
    # полуинтервалы: конец одного == начало другого -> НЕ пересекаются
    assert not overlaps(_dt(9), _dt(10), _dt(10), _dt(11))


def test_has_conflict_true():
    existing = [(_dt(10), _dt(11))]
    assert has_conflict(existing, _dt(10, 30), _dt(11, 15))


def test_has_conflict_false():
    existing = [(_dt(10), _dt(11))]
    assert not has_conflict(existing, _dt(11), _dt(12))


def test_has_conflict_empty():
    assert not has_conflict([], _dt(10), _dt(11))


def test_has_conflict_multiple_intervals():
    existing = [(_dt(9), _dt(10)), (_dt(12), _dt(13))]
    # 10:00-12:00 свободен
    assert not has_conflict(existing, _dt(10), _dt(12))
    # 9:30-10:30 задевает первый
    assert has_conflict(existing, _dt(9, 30), _dt(10, 30))
