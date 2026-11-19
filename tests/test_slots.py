"""Тесты расчёта свободных слотов. База данных не нужна — тестируем чистую логику."""

from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.slots import generate_slots

MOSCOW = ZoneInfo("Europe/Moscow")


def _wh(start: str, end: str) -> SimpleNamespace:
    return SimpleNamespace(start_time=time.fromisoformat(start), end_time=time.fromisoformat(end))


def _appt(start_iso: str, end_iso: str) -> SimpleNamespace:
    return SimpleNamespace(
        starts_at=datetime.fromisoformat(start_iso),
        ends_at=datetime.fromisoformat(end_iso),
    )


def _local(slots) -> list[str]:
    return [s.starts_at.astimezone(MOSCOW).strftime("%H:%M") for s in slots]


def test_empty_when_no_working_hours():
    assert generate_slots([], [], date(2026, 10, 29), 60, 30, MOSCOW) == []


def test_full_day_without_appointments():
    slots = generate_slots([_wh("10:00", "13:00")], [], date(2026, 10, 29), 60, 60, MOSCOW)
    assert _local(slots) == ["10:00", "11:00", "12:00"]


def test_appointment_blocks_slot():
    # 11:00–12:00 по Москве занято (08:00–09:00 UTC).
    busy = [_appt("2026-10-29T08:00:00+00:00", "2026-10-29T09:00:00+00:00")]
    slots = generate_slots([_wh("10:00", "14:00")], busy, date(2026, 10, 29), 60, 60, MOSCOW)
    assert _local(slots) == ["10:00", "12:00", "13:00"]


def test_slot_must_fit_inside_interval():
    # Услуга 90 минут, шаг 30: последний подходящий старт — 10:30 (10:30 + 90 = 12:00).
    slots = generate_slots([_wh("10:00", "12:00")], [], date(2026, 10, 29), 90, 30, MOSCOW)
    assert _local(slots) == ["10:00", "10:30"]


def test_two_intervals_with_break():
    hours = [_wh("10:00", "11:00"), _wh("12:00", "13:00")]
    slots = generate_slots(hours, [], date(2026, 10, 29), 60, 30, MOSCOW)
    assert _local(slots) == ["10:00", "12:00"]


def test_partial_overlap_blocks():
    # Занято 10:30–11:30. Слоты 10:00, 10:30 и 11:00 пересекаются с занятым интервалом.
    busy = [_appt("2026-10-29T07:30:00+00:00", "2026-10-29T08:30:00+00:00")]
    slots = generate_slots([_wh("10:00", "13:00")], busy, date(2026, 10, 29), 60, 30, MOSCOW)
    assert _local(slots) == ["11:30", "12:00"]
