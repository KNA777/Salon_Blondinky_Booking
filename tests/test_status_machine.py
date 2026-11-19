"""Тесты машины переходов статусов записи.

Проверяем чистую логику (app/services/status_machine.py) без БД: какие переходы допустимы,
какие запрещены, и что запрещённый переход кидает InvalidTransitionError.
"""

import pytest

from app.core.exceptions import InvalidTransitionError
from app.models.appointment import AppointmentStatusEnum as S
from app.services.status_machine import is_transition_allowed, validate_transition


def test_created_allows_all_initial_transitions():
    # Из created можно подтвердить, отменить, отметить неявку или сразу завершить.
    for target in (S.CONFIRMED, S.CANCELLED, S.NO_SHOW, S.COMPLETED):
        assert is_transition_allowed(S.CREATED, target)


def test_confirmed_allows_terminal_transitions():
    for target in (S.COMPLETED, S.NO_SHOW, S.CANCELLED):
        assert is_transition_allowed(S.CONFIRMED, target)


def test_confirmed_cannot_go_back_to_created():
    assert not is_transition_allowed(S.CONFIRMED, S.CREATED)


def test_terminal_statuses_have_no_outgoing_transitions():
    for terminal in (S.COMPLETED, S.NO_SHOW, S.CANCELLED):
        for target in S:
            assert not is_transition_allowed(terminal, target)


def test_same_status_is_not_a_transition():
    # Перевод в тот же статус не считается переходом (и не должен создавать работу).
    assert not is_transition_allowed(S.CREATED, S.CREATED)


def test_validate_transition_allows_valid():
    # Не должно бросать исключение.
    validate_transition(S.CREATED, S.CONFIRMED)


def test_validate_transition_rejects_invalid():
    with pytest.raises(InvalidTransitionError, match="completed -> created"):
        validate_transition(S.COMPLETED, S.CREATED)


def test_validate_transition_message_mentions_statuses():
    with pytest.raises(InvalidTransitionError) as exc_info:
        validate_transition(S.CONFIRMED, S.CREATED)
    assert "confirmed" in str(exc_info.value)
    assert "created" in str(exc_info.value)
