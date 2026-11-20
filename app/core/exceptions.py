class NotFoundError(Exception):
    """Объект не найден в базе. Обработчик в main.py отвечает на него HTTP 404."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidTransitionError(Exception):
    """Запрещённый переход статуса записи (см. app/services/status_machine.py).

    Обработчик в main.py отвечает на него HTTP 409 Conflict: состояние записи не позволяет
    применить запрошенное изменение.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class SlotConflictError(Exception):
    """Попытка занять слот, который уже занят другой записью (двойная запись).

    Обработчик в main.py отвечает на него HTTP 409 Conflict. Слой приложения проверяет
    конфликт заранее (быстрый отказ без гонки), а exclusion constraint в БД — последний
    рубеж против гонки двух одновременных запросов (см. задачу 9).
    """

    def __init__(self, detail: str = "Слот уже занят") -> None:
        self.detail = detail
        super().__init__(detail)


class PermissionError(Exception):
    """Запись принадлежит другому клиенту, и текущий пользователь не может ей управлять.

    Обработчик в main.py отвечает HTTP 403 Forbidden. Возникает, когда не-админ пытается
    отменить/перенести/изменить чужую запись (проверка владения по client_id).
    """

    def __init__(self, detail: str = "Недостаточно прав для этой операции") -> None:
        self.detail = detail
        super().__init__(detail)
