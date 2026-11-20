"""Тесты напоминаний о записи (задача 13).

Проверяем чистую логику: is_due (когда напоминание «созрело») и reminder_text (текст).
Отправка по БД/Telegram покрывается интеграционно (подключение к реальному Redis/Postgres
не требуется для этих юнит-тестов).
"""

from datetime import UTC, datetime, timedelta

from app.services.reminders import is_due, reminder_text

POLL = 60  # шаг планировщика в секундах


def test_is_due_exactly_at_offset():
    # Ровно за 2 часа (offset=120 мин) — напоминание должно отправиться.
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts = now + timedelta(minutes=120)
    assert is_due(starts, now, offset_minutes=120, poll_interval_seconds=POLL)


def test_is_due_just_inside_window_end():
    # За 2 часа минус 30 секунд — всё ещё в окне (между lower и upper).
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts = now + timedelta(minutes=120) - timedelta(seconds=30)
    assert is_due(starts, now, offset_minutes=120, poll_interval_seconds=POLL)


def test_is_due_too_far_into_future():
    # За 3 часа — ещё рано отправлять 2-часовое напоминание.
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts = now + timedelta(minutes=180)
    assert not is_due(starts, now, offset_minutes=120, poll_interval_seconds=POLL)


def test_is_due_already_passed_window():
    # До начала осталось меньше lower (например, 30 секунд при шаге 60с) — уже поздно,
    # окно ушло (запись отправил бы предыдущий тик).
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts = now + timedelta(seconds=30)
    assert not is_due(starts, now, offset_minutes=120, poll_interval_seconds=POLL)


def test_is_due_24h_offset():
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts_24 = now + timedelta(hours=24)
    assert is_due(starts_24, now, offset_minutes=24 * 60, poll_interval_seconds=POLL)


def test_is_due_distinguishes_24h_from_2h():
    # За 2 часа запись «созрела» только для 2-часового напоминания, но не для 24-часового.
    now = datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    starts = now + timedelta(hours=2)
    assert is_due(starts, now, offset_minutes=120, poll_interval_seconds=POLL)
    assert not is_due(starts, now, offset_minutes=24 * 60, poll_interval_seconds=POLL)


def test_reminder_text_content():
    starts = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
    text = reminder_text("Маникюр", "Анна", starts, "24h")
    assert "Маникюр" in text
    assert "Анна" in text
    assert "24 часа" in text
    assert "2026-11-25T14:00" in text


def test_reminder_text_2h_label():
    starts = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
    text = reminder_text("Стрижка", "Мария", starts, "2h")
    assert "2 часа" in text
    assert "Стрижка" in text
