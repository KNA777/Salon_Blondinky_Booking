"""Состояния диалога записи (FSM).

Каждый пользователь в каждый момент находится ровно в одном состоянии. Состояние определяет,
какое сообщение бот ожидает следующим и как его валидировать. Переходы описаны в fsm.py.

Цепочка: START -> CHOOSE_SERVICE -> CHOOSE_MASTER -> CHOOSE_DATE -> CHOOSE_SLOT ->
CONFIRM -> DONE. Любое состояние может быть прервано /cancel и вернуть в START.
"""

import enum


class BookingState(enum.StrEnum):
    START = "start"
    CHOOSE_SERVICE = "choose_service"
    CHOOSE_MASTER = "choose_master"
    CHOOSE_DATE = "choose_date"
    CHOOSE_SLOT = "choose_slot"
    CONFIRM = "confirm"
    DONE = "done"
