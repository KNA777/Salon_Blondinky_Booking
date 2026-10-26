"""Тесты /health без настоящих Postgres и Redis.

Вместо них подставляем «фейки» через dependency_overrides. Так тест быстрый,
не требует Docker и проверяет именно логику эндпоинта: как он реагирует на сбои.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_redis, get_session
from app.main import app


class FakeSession:
    async def execute(self, *args, **kwargs):
        return None


class BrokenSession:
    async def execute(self, *args, **kwargs):
        raise ConnectionRefusedError


class FakeDBManager:
    # /health обращается к БД через session.session (AsyncSession внутри DBManager),
    # поэтому фейк имитирует DBManager, а не голую сессию.
    session = FakeSession()


class BrokenDBManager:
    session = BrokenSession()


class FakeRedis:
    async def ping(self):
        return True


class BrokenRedis:
    async def ping(self):
        raise ConnectionError


@pytest.fixture
def client():
    # TestClient без `with` не запускает lifespan, поэтому подключение к реальным
    # сервисам не создаётся, а нужные зависимости мы подменяем в самих тестах.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_ok(client):
    app.dependency_overrides[get_session] = lambda: FakeDBManager()
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "redis": "ok"}


def test_health_postgres_down(client):
    app.dependency_overrides[get_session] = lambda: BrokenDBManager()
    app.dependency_overrides[get_redis] = lambda: FakeRedis()

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "error: ConnectionRefusedError"
    assert body["redis"] == "ok"


def test_health_redis_down(client):
    app.dependency_overrides[get_session] = lambda: FakeDBManager()
    app.dependency_overrides[get_redis] = lambda: BrokenRedis()

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["redis"] == "error: ConnectionError"
