"""Тесты API клиентов и записей + интеграция с машиной статусов.

Без реальной БД: подменяем DBManager через dependency_overrides (как в test_health.py).
Проверяем, что эндпоинты зарегистрированы и корректно вызывают репозитории,
включая отказ запрещённых переходов статуса (HTTP 409).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_client, get_session
from app.main import app
from app.models.appointment import AppointmentStatusEnum
from app.schemas.appointment import AppointmentOut
from app.schemas.client import ClientOut

# --- фейки репозиториев и сессии ---------------------------------------------


def _fake_appointment(appointment_id: int, status: str = "created") -> AppointmentOut:
    """Собирает валидную AppointmentOut для ответов фейкового репозитория.

    Эндпоинты теперь типизированы как AppointmentOut, поэтому FastAPI валидирует ответ:
    фейк должен возвращать полную схему, а не частичный dict.
    """
    return AppointmentOut(
        id=appointment_id,
        client_id=1,
        master_id=1,
        service_id=1,
        starts_at=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 11, 20, 10, 45, tzinfo=UTC),
        price=Decimal("1500.00"),
        status=status,
    )


class FakeRepo:
    """Записывает вызовы, чтобы тест мог проверить, что эндпоинт вызвал нужный метод."""

    calls: list[tuple]

    def __init__(self) -> None:
        self.calls = []


class FakeClients(FakeRepo):
    async def get_by_telegram_id(self, telegram_id):
        self.calls.append(("get_by_telegram_id", telegram_id))
        return None

    async def get_data_bulk(self):
        self.calls.append(("get_data_bulk",))
        return []

    async def get_one_by_id(self, **kw):
        self.calls.append(("get_one_by_id", kw))
        return ClientOut(id=kw.get("id"), name="Клиент")

    async def upsert_by_telegram_id(self, data):
        self.calls.append(("upsert_by_telegram_id", data.telegram_id))
        return {"id": 1, "telegram_id": data.telegram_id, "name": data.name}


class FakeAppointments(FakeRepo):
    async def create_with_conflict_check(self, data):
        self.calls.append(("create_with_conflict_check", data.client_id))
        return _fake_appointment(1)

    async def get_bulk_by_client(self, client_id):
        self.calls.append(("get_bulk_by_client", client_id))
        return []

    async def get_bulk_by_master(self, master_id):
        self.calls.append(("get_bulk_by_master", master_id))
        return []

    async def get_data_bulk(self):
        self.calls.append(("get_data_bulk",))
        return []

    async def get_one_by_id(self, **kw):
        self.calls.append(("get_one_by_id", kw))
        return _fake_appointment(kw.get("id"))

    async def transition_status(self, appointment_id, status):
        self.calls.append(("transition_status", appointment_id, status))
        return _fake_appointment(appointment_id, status=status.value)

    async def cancel(self, appointment_id, client_id=None, is_admin=False):
        self.calls.append(("cancel", appointment_id, client_id, is_admin))
        return _fake_appointment(appointment_id, status="cancelled")

    async def reschedule(self, appointment_id, starts_at, ends_at, client_id=None, is_admin=False):
        self.calls.append(("reschedule", appointment_id, client_id, is_admin))
        return _fake_appointment(appointment_id, status="confirmed")


class FakeDBManager:
    """Имитирует DBManager: репозитории доступны как атрибуты сразу после создания.

    get_session в deps.py отдаёт DBManager напрямую (yield), поэтому здесь атрибуты
    clients/appointments задаём в __init__, а не в __aenter__.
    """

    def __init__(self, clients=None, appointments=None) -> None:
        self.clients = clients or FakeClients()
        self.appointments = appointments or FakeAppointments()


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _override(db: FakeDBManager):
    app.dependency_overrides[get_session] = lambda: db


def _override_client(client_id=1, is_admin=False):
    """Подменяет текущего клиента (как будто он залогинен с заданными правами)."""
    app.dependency_overrides[get_current_client] = lambda: type(
        "CurrentClient", (), {"id": client_id, "is_admin": is_admin}
    )()


# --- клиенты ------------------------------------------------------------------


def test_get_clients_by_telegram_id(client):
    clients = FakeClients()
    _override(FakeDBManager(clients=clients, appointments=FakeAppointments()))
    _override_client(client_id=1, is_admin=True)  # список клиентов — только админ

    response = client.get("/clients", params={"telegram_id": 12345})

    assert response.status_code == 200
    assert clients.calls == [("get_by_telegram_id", 12345)]


def test_post_client_with_telegram_id_upserts(client):
    clients = FakeClients()
    _override(FakeDBManager(clients=clients, appointments=FakeAppointments()))

    response = client.post("/clients", json={"name": "Анна", "phone": "+7", "telegram_id": 777})

    assert response.status_code == 200
    assert any(call[0] == "upsert_by_telegram_id" for call in clients.calls)


def test_get_client_by_id(client):
    clients = FakeClients()
    _override(FakeDBManager(clients=clients, appointments=FakeAppointments()))
    _override_client(client_id=5, is_admin=False)  # владелец видит свою карточку

    response = client.get("/clients/5")

    assert response.status_code == 200
    assert clients.calls == [("get_one_by_id", {"id": 5})]


# --- записи -------------------------------------------------------------------


def test_post_appointment(client):
    appointments = FakeAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=1, is_admin=False)  # запись для себя (client_id=1)

    payload = {
        "client_id": 1,
        "master_id": 2,
        "service_id": 3,
        "starts_at": "2026-11-20T10:00:00Z",
        "ends_at": "2026-11-20T10:45:00Z",
        "price": "1500.00",
    }
    response = client.post("/appointments", json=payload)

    assert response.status_code == 200
    assert any(call[0] == "create_with_conflict_check" for call in appointments.calls)


def test_get_appointments_by_client(client):
    appointments = FakeAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=9, is_admin=False)  # клиент видит только свои записи

    response = client.get("/appointments", params={"client_id": 9})

    assert response.status_code == 200
    assert appointments.calls == [("get_bulk_by_client", 9)]


def test_change_appointment_status_valid(client):
    appointments = FakeAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=1, is_admin=True)  # смена статуса — только админ

    response = client.post("/appointments/1/status", json={"status": "confirmed"})

    assert response.status_code == 200
    assert ("transition_status", 1, AppointmentStatusEnum.CONFIRMED) in appointments.calls


# --- машина статусов через HTTP ------------------------------------------------
# Здесь проверяем, что запрещённый переход превращается в 409 Conflict.


class _RejectingAppointments(FakeAppointments):
    async def transition_status(self, appointment_id, status):
        from app.core.exceptions import InvalidTransitionError

        self.calls.append(("transition_status", appointment_id, status))
        raise InvalidTransitionError(f"completed -> {status.value}")


def test_forbidden_status_transition_returns_409(client):
    appointments = _RejectingAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=1, is_admin=True)  # смена статуса — только админ

    response = client.post("/appointments/1/status", json={"status": "created"})

    assert response.status_code == 409


# --- отмена и перенос (задача 10) ----------------------------------------------


def test_cancel_appointment(client):
    appointments = FakeAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=7, is_admin=False)

    response = client.post("/appointments/7/cancel")

    assert response.status_code == 200
    assert ("cancel", 7, 7, False) in appointments.calls


def test_reschedule_appointment(client):
    appointments = FakeAppointments()
    _override(FakeDBManager(clients=FakeClients(), appointments=appointments))
    _override_client(client_id=7, is_admin=False)

    payload = {
        "starts_at": "2026-11-21T11:00:00Z",
        "ends_at": "2026-11-21T11:45:00Z",
    }
    response = client.post("/appointments/7/reschedule", json=payload)

    assert response.status_code == 200
    assert any(call[0] == "reschedule" for call in appointments.calls)
