"""Хранилище состояния и накопленных данных записи для каждого пользователя.

Реализация на словаре в памяти — простая и подходит для одного процесса бота
(long polling). Когда бот переедет на webhook с несколькими воркерами (задача 8),
это хранилище нужно будет заменить на Redis, чтобы состояние переживало перезапуск
и было доступно из любого воркера. Интерфейс (get_state/set_state/save/reset)
оставлен так, чтобы замена реализации не потребовала менять handlers/fsm.
"""

from dataclasses import dataclass

from app.bot.states import BookingState


@dataclass
class BookingContext:
    """Накопленные данные записи: заполняются по мере прохождения цепочки."""

    state: BookingState = BookingState.START
    client_id: int | None = None
    service_id: int | None = None
    master_id: int | None = None
    day: str | None = None  # ISO-дата (YYYY-MM-DD)


class InMemoryBookingStorage:
    """Простое in-memory хранилище: словарь user_id -> BookingContext."""

    def __init__(self) -> None:
        self._data: dict[int, BookingContext] = {}

    def get_state(self, user_id: int) -> BookingState:
        ctx = self._data.get(user_id)
        return ctx.state if ctx is not None else BookingState.START

    def set_state(self, user_id: int, state: BookingState) -> None:
        self._ensure(user_id).state = state

    def get_context(self, user_id: int) -> BookingContext:
        return self._ensure(user_id)

    def save(self, user_id: int, **fields) -> None:
        """Обновить одно или несколько полей контекста записи."""
        ctx = self._ensure(user_id)
        for name, value in fields.items():
            setattr(ctx, name, value)

    def reset(self, user_id: int) -> None:
        """Сбросить диалог: state -> START и все накопленные данные очищаются."""
        self._data[user_id] = BookingContext(state=BookingState.START)

    def _ensure(self, user_id: int) -> BookingContext:
        if user_id not in self._data:
            self._data[user_id] = BookingContext()
        return self._data[user_id]


# Единый экземпляр на процесс бота. В webhook-версии будет создаваться из Redis.
storage = InMemoryBookingStorage()
