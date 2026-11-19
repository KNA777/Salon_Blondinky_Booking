"""Тесты FSM-сценария бота: логика состояний, хранилище и чистые помощники.

Здесь проверяется всё, что можно проверить без Telegram и без реальной БД:
- переходы состояний в хранилище (get/set/reset);
- расчёт доступных дат (available_days, _start_day);
- тексты кнопок (_service_label, _master_label, _slot_label);
- require_token (входная валидация токена).

Хендлеры, работающие с БД (cmd_start, cb_slot и т.п.), требуют тестовой БД и
покрываются интеграционными тестами (план, задача 23) отдельно.
"""

from datetime import datetime

import pytest

from app.bot.__main__ import require_token
from app.bot.fsm import _master_label, _service_label, _slot_label, available_days
from app.bot.states import BookingState
from app.bot.storage import InMemoryBookingStorage

# --- хранилище состояний -----------------------------------------------------


def test_storage_defaults_to_start():
    s = InMemoryBookingStorage()
    assert s.get_state(123) == BookingState.START


def test_storage_set_and_get_state():
    s = InMemoryBookingStorage()
    s.set_state(123, BookingState.CHOOSE_SERVICE)
    assert s.get_state(123) == BookingState.CHOOSE_SERVICE


def test_storage_save_fields_and_reset():
    s = InMemoryBookingStorage()
    s.save(123, service_id=5, master_id=7)
    assert s.get_context(123).service_id == 5
    assert s.get_context(123).master_id == 7
    s.reset(123)
    assert s.get_state(123) == BookingState.START
    assert s.get_context(123).service_id is None


def test_storage_isolates_users():
    s = InMemoryBookingStorage()
    s.set_state(1, BookingState.CHOOSE_MASTER)
    s.set_state(2, BookingState.CHOOSE_DATE)
    assert s.get_state(1) == BookingState.CHOOSE_MASTER
    assert s.get_state(2) == BookingState.CHOOSE_DATE


# --- чистые помощники fsm ----------------------------------------------------


class _FakeService:
    def __init__(self, name, duration_minutes, price):
        from decimal import Decimal

        self.name = name
        self.duration_minutes = duration_minutes
        self.price = Decimal(price)


def test_service_label_integer_price():
    s = _FakeService("Маникюр", 45, "1500")
    assert _service_label(s, 1) == "1. Маникюр — 45 мин, 1500 ₽"


def test_service_label_fractional_price():
    s = _FakeService("Стрижка", 60, "1499.50")
    assert _service_label(s, 2) == "2. Стрижка — 60 мин, 1499.50 ₽"


def test_master_label():
    class _FakeMaster:
        name = "Анна"

    assert _master_label(_FakeMaster(), 3) == "3. Анна"


def test_slot_label():
    start = datetime(2026, 11, 19, 10, 0)
    end = datetime(2026, 11, 19, 10, 45)
    assert _slot_label(start, end) == "10:00–10:45"


def test_available_days_length():
    days = available_days()
    assert len(days) == 7
    # Возвращается подряд идущие даты.
    assert (days[1] - days[0]).days == 1


# --- require_token ------------------------------------------------------------


def test_require_token_ok():
    assert require_token("123:abc") == "123:abc"


def test_require_token_missing_raises():
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        require_token(None)
