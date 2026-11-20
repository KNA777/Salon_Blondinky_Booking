"""Тесты часовых поясов (задача 11): единое хранение в UTC, отображение в TZ салона.

Проверяем, что перевод «настенного» времени салона в UTC и обратно корректен, в том
числе в дни перехода на летнее/зимнее время. Для этого используем зону с реальным
переходом (Europe/Berlin): Moscow с 2014 г. на постоянном UTC+3 и перехода не даёт.

Ключевая идея (см. app/services/slots.py): расписание мастера хранится как «настенное»
время (Time без пояса), в UTC переводится только при расчёте конкретных слотов через
zoneinfo. Значит «10:00» в день весеннего и осеннего перехода — это разный момент UTC,
и generate_slots обязана это учитывать.
"""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.slots import generate_slots

BERLIN = ZoneInfo("Europe/Berlin")
MOSCOW = ZoneInfo("Europe/Moscow")
UTC_ZONE = ZoneInfo("UTC")


def _wh(start: str, end: str) -> SimpleNamespace:
    return SimpleNamespace(start_time=time.fromisoformat(start), end_time=time.fromisoformat(end))


def _local(slots, tz: ZoneInfo) -> list[str]:
    """Локальное (настенное) время начала слота в заданной зоне."""
    return [s.starts_at.astimezone(tz).strftime("%H:%M") for s in slots]


def test_moscow_has_no_dst_transition():
    """Фоновый факт: Europe/Moscow на постоянном UTC+3, поэтому слоты одной даты
    в январе и июле в UTC совпадают по смещению."""
    jan = generate_slots([_wh("10:00", "11:00")], [], date(2026, 1, 15), 60, 60, MOSCOW)
    jul = generate_slots([_wh("10:00", "11:00")], [], date(2026, 7, 15), 60, 60, MOSCOW)
    assert jan[0].starts_at.astimezone(UTC).hour == 7
    assert jul[0].starts_at.astimezone(UTC).hour == 7


def test_spring_forward_wall_clock_is_different_utc_instant():
    """Весенний переход (Europe/Berlin, 29.03.2026): «10:00» до и после перехода —
    разные моменты UTC. generate_slots должен отдать корректный момент для каждого дня."""
    before = generate_slots([_wh("10:00", "11:00")], [], date(2026, 3, 28), 60, 60, BERLIN)
    after = generate_slots([_wh("10:00", "11:00")], [], date(2026, 3, 29), 60, 60, BERLIN)

    # Настенное время в обоих случаях одно и то же...
    assert _local(before, BERLIN) == ["10:00"]
    assert _local(after, BERLIN) == ["10:00"]
    # ...но момент UTC отличается ровно на час (UTC+1 -> UTC+2).
    assert before[0].starts_at.astimezone(UTC).hour == 9  # до перехода: +1
    assert after[0].starts_at.astimezone(UTC).hour == 8  # после: +2


def test_fall_back_wall_clock_returns_to_previous_offset():
    """Осенний переход (Europe/Berlin, 25.10.2026): «10:00» снова сдвигается на час
    в UTC (UTC+2 -> UTC+1)."""
    before = generate_slots([_wh("10:00", "11:00")], [], date(2026, 10, 24), 60, 60, BERLIN)
    after = generate_slots([_wh("10:00", "11:00")], [], date(2026, 10, 25), 60, 60, BERLIN)

    assert before[0].starts_at.astimezone(UTC).hour == 8  # до перехода: +2
    assert after[0].starts_at.astimezone(UTC).hour == 9  # после: +1


def test_slot_duration_is_constant_across_dst():
    """Слот длится ровно 60 минут реального времени и на следующий день после перехода:
    разница start-end не «плывёт» из-за изменения смещения."""
    slots = generate_slots([_wh("10:00", "13:00")], [], date(2026, 3, 29), 60, 60, BERLIN)
    for s in slots:
        assert (s.ends_at - s.starts_at).total_seconds() == 3600


def test_appointment_in_utc_blocks_correct_wall_slot_across_dst():
    """Занятый интервал хранится в UTC; в день перехода он должен блокировать именно те
    настенные слоты, с которыми пересекается по реальному времени."""
    # 10:00-11:00 Berlin в день перехода (29.03) = 08:00-09:00 UTC.
    busy = [
        SimpleNamespace(
            starts_at=datetime.fromisoformat("2026-03-29T08:00:00+00:00"),
            ends_at=datetime.fromisoformat("2026-03-29T09:00:00+00:00"),
        )
    ]
    slots = generate_slots([_wh("09:00", "12:00")], busy, date(2026, 3, 29), 60, 60, BERLIN)
    # 09:00 блокируется интервалом? 09:00 Berlin = 07:00 UTC, до занятого 08:00 — свободен.
    # 10:00 Berlin = 08:00 UTC — занят. 11:00 Berlin = 09:00 UTC — свободен.
    assert _local(slots, BERLIN) == ["09:00", "11:00"]


def test_utc_storage_is_timezone_aware():
    """Слоты отдаются как aware datetime (с tzinfo), а не наивные — иначе astimezone
    упадёт либо даст неверный момент."""
    slots = generate_slots([_wh("10:00", "11:00")], [], date(2026, 7, 15), 60, 60, MOSCOW)
    assert all(s.starts_at.tzinfo is not None for s in slots)
    assert all(s.ends_at.tzinfo is not None for s in slots)
