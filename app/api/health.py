from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DBDep, RedisDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: DBDep, redis: RedisDep, response: Response) -> dict[str, str]:
    """Проверка, что приложение живо и видит Postgres и Redis.

    Если хотя бы один сервис недоступен, отвечаем 503: по коду ответа это понимают
    Docker, балансировщики и мониторинг, им не нужно разбирать тело ответа.
    """
    checks: dict[str, str] = {}

    # Здесь намеренно ловим любое исключение: задача проверки — не упасть,
    # а сообщить, что именно не работает.
    try:
        await session.session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ok" if healthy else "degraded", **checks}
