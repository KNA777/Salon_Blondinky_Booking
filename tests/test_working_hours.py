"""Тесты валидации схемы рабочих часов. База данных не нужна."""

import pytest
from pydantic import ValidationError

from app.schemas.working_hour import WorkingHourCreate, WorkingHourUpdate


def test_create_valid():
    wh = WorkingHourCreate(weekday=0, start_time="10:00", end_time="19:00")
    assert wh.weekday == 0


def test_create_end_before_start():
    with pytest.raises(ValidationError):
        WorkingHourCreate(weekday=0, start_time="19:00", end_time="10:00")


def test_create_weekday_out_of_range():
    with pytest.raises(ValidationError):
        WorkingHourCreate(weekday=7, start_time="10:00", end_time="19:00")


def test_update_partial():
    wh = WorkingHourUpdate(start_time="11:00")
    assert wh.start_time is not None
    assert wh.end_time is None
