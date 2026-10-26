class NotFoundError(Exception):
    """Объект не найден в базе. Обработчик в main.py отвечает на него HTTP 404."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)
