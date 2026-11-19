"""Машина переходов статусов записи (AppointmentStatusEnum).

Граф переходов задан явно и в одном месте. Это единственный источник правды о том,
какой статус в какой можно переводить. Валидация «закрыта по умолчанию»: переход, которого
нет в TRANSITIONS, считается запрещённым и вызывает InvalidTransitionError.

Граф (замкнутость подразумевается явно):
    created   -> confirmed | cancelled | no_show | completed
    confirmed -> completed | no_show   | cancelled
    completed, no_show, cancelled — конечные (никуда не переводятся).

Зачем вообще машина, а не просто «поменять строку статуса»:
- запрещённый переход (например, completed -> created) ломает бизнес-логику и учёт;
- централизованная проверка избавляет каждый эндпоинт от повторения if-ов;
- граф легко показать заказчику и проверить тестами.
"""

from app.core.exceptions import InvalidTransitionError
from app.models.appointment import AppointmentStatusEnum

# Ключ — текущий статус, значение — множество допустимых следующих статусов.
TRANSITIONS: dict[AppointmentStatusEnum, frozenset[AppointmentStatusEnum]] = {
    AppointmentStatusEnum.CREATED: frozenset(
        {
            AppointmentStatusEnum.CONFIRMED,
            AppointmentStatusEnum.CANCELLED,
            AppointmentStatusEnum.NO_SHOW,
            AppointmentStatusEnum.COMPLETED,
        }
    ),
    AppointmentStatusEnum.CONFIRMED: frozenset(
        {
            AppointmentStatusEnum.COMPLETED,
            AppointmentStatusEnum.NO_SHOW,
            AppointmentStatusEnum.CANCELLED,
        }
    ),
    # Конечные статусы: у них нет ключа в TRANSITIONS, поэтому любой переход из них
    # автоматически считается запрещённым.
}


def is_transition_allowed(
    current: AppointmentStatusEnum, next_status: AppointmentStatusEnum
) -> bool:
    """Можно ли перевести запись из current в next_status."""

    return next_status in TRANSITIONS.get(current, frozenset())


def validate_transition(
    current: AppointmentStatusEnum, next_status: AppointmentStatusEnum
) -> None:
    """Проверяет переход и кидает InvalidTransitionError, если он запрещён.

    Используется при смене статуса записи: сначала валидируем граф, и только потом
    пишем в базу. Так ни один эндпоинт не сможет «проскочить» запрещённый переход.
    """
    if not is_transition_allowed(current, next_status):
        raise InvalidTransitionError(
            f"Недопустимый переход статуса: {current.value} -> {next_status.value}"
        )
