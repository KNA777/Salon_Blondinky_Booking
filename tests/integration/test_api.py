"""Интеграционные тесты REST API на реальной БД (задача 23).

Полный сквозной цикл: услуги -> мастера -> рабочие часы -> слоты -> клиенты -> записи,
включая проверку владения, машину состояний и защиту от двойной записи на уровне API.

Фикстуры client/clean_db определены в tests/conftest.py и подменяют get_session так,
чтобы эндпоинты работали с тестовой базой. При недоступном Postgres тесты пропускаются.
"""

from datetime import UTC, date, datetime, timedelta


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _slot(day: date, wall_hour: int, duration_min: int = 60) -> tuple[str, str]:
    """Возвращает (starts_at, ends_at) как ISO-строки в UTC для записи в указанный день.

    Салон в Europe/Moscow (UTC+3 без перехода), поэтому «настенные» часы переводятся
    вычитанием 3 часов. Используется только для создания записей в БД в тестах.
    """
    start = datetime(day.year, day.month, day.day, wall_hour, 0, tzinfo=UTC) - timedelta(hours=3)
    return _iso(start), _iso(start + timedelta(minutes=duration_min))


# --- услуги --------------------------------------------------------------------


async def test_services_crud_roundtrip(client, clean_db, admin_headers):
    created = await client.post(
        "/services",
        json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
        headers=admin_headers,
    )
    assert created.status_code == 200
    service = created.json()
    assert service["name"] == "Маникюр"
    assert service["is_active"] is True

    listed = (await client.get("/services")).json()
    assert any(s["id"] == service["id"] for s in listed)

    fetched = await client.get(f"/services/{service['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Маникюр"

    updated = await client.patch(
        f"/services/{service['id']}", json={"price": "1800.00"}, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json()["price"] == "1800.00"

    deactivated = await client.post(f"/services/{service['id']}", headers=admin_headers)
    assert deactivated.status_code == 200
    # По умолчанию неактивные не возвращаются.
    assert all(s["id"] != service["id"] for s in (await client.get("/services")).json())
    # С include_inactive — возвращаются.
    assert any(
        s["id"] == service["id"]
        for s in (await client.get("/services", params={"include_inactive": True})).json()
    )


async def test_service_creation_requires_admin(client, clean_db, client_headers):
    """Не-админ не может создать услугу -> 403."""
    resp = await client.post(
        "/services",
        json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
        headers=client_headers,
    )
    assert resp.status_code == 403


async def test_service_404(client, clean_db):
    assert (await client.get("/services/99999")).status_code == 404


# --- мастера -------------------------------------------------------------------


async def test_masters_crud_and_slots(client, clean_db, admin_headers):
    service = (
        await client.post(
            "/services",
            json={"name": "Стрижка", "duration_minutes": 60, "price": "1000.00"},
            headers=admin_headers,
        )
    ).json()

    master_resp = await client.post(
        "/masters",
        json={"name": "Анна", "phone": "+7", "service_ids": [service["id"]]},
        headers=admin_headers,
    )
    assert master_resp.status_code == 200
    master = master_resp.json()
    assert master["name"] == "Анна"
    assert [s["id"] for s in master["services"]] == [service["id"]]

    # Рабочие часы: среда (weekday=2), 10:00–12:00.
    wh = await client.post(
        f"/masters/{master['id']}/working-hours",
        json={"weekday": 2, "start_time": "10:00", "end_time": "12:00"},
        headers=admin_headers,
    )
    assert wh.status_code == 200

    listed_wh = (await client.get(f"/masters/{master['id']}/working-hours")).json()
    assert len(listed_wh) == 1
    assert listed_wh[0]["start_time"] == "10:00"

    # Свободные слоты на конкретную среду (2026-11-25 — среда).
    day = "2026-11-25"
    slots = await client.get(
        f"/masters/{master['id']}/free-slots",
        params={"service_id": service["id"], "datetime": day, "step_minutes": 60},
    )
    assert slots.status_code == 200
    body = slots.json()
    assert body["timezone"] == "Europe/Moscow"
    starts = [s["starts_at"] for s in body["slots"]]
    # Слоты отдаются в «настенном» времени салона (Europe/Moscow, UTC+3 без перехода):
    # 10:00 и 11:00 локально.
    assert "2026-11-25T10:00:00+03:00" in starts
    assert "2026-11-25T11:00:00+03:00" in starts


async def test_master_404(client, clean_db):
    assert (await client.get("/masters/99999")).status_code == 404


# --- клиенты и записи ----------------------------------------------------------


async def test_clients_and_appointments_full_flow(client, clean_db, admin_headers):
    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()

    # Клиент через upsert по telegram_id.
    c1 = (
        await client.post("/clients", json={"name": "Иван", "phone": "+7", "telegram_id": 111})
    ).json()
    # Повторный upsert с тем же telegram_id возвращает того же клиента (без дубля).
    c1_again = (await client.post("/clients", json={"name": "Иван", "telegram_id": 111})).json()
    assert c1["id"] == c1_again["id"]
    # Среди клиентов есть наш (плюс админ из фикстуры admin_headers).
    clients = (await client.get("/clients")).json()
    assert any(c["id"] == c1["id"] for c in clients)

    # Создание записи.
    starts_at, ends_at = _slot(date(2026, 11, 25), 10)
    appt = await client.post(
        "/appointments",
        json={
            "client_id": c1["id"],
            "master_id": master["id"],
            "service_id": service["id"],
            "starts_at": starts_at,
            "ends_at": ends_at,
            "price": "1500.00",
        },
    )
    assert appt.status_code == 200
    appointment = appt.json()
    assert appointment["status"] == "created"

    # Список записей клиента.
    by_client = (await client.get("/appointments", params={"client_id": c1["id"]})).json()
    assert len(by_client) == 1
    assert by_client[0]["id"] == appointment["id"]

    # Смена статуса через машину: created -> confirmed.
    confirmed = await client.post(
        f"/appointments/{appointment['id']}/status", json={"status": "confirmed"}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


async def test_appointment_double_booking_rejected_at_api(client, clean_db, admin_headers):
    """Два запроса на один и тот же слот: второй должен получить 409 (SlotConflictError)."""
    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()
    c2 = (await client.post("/clients", json={"name": "Пётр"})).json()

    starts_at, ends_at = _slot(date(2026, 11, 25), 10)
    payload1 = {
        "client_id": c1["id"],
        "master_id": master["id"],
        "service_id": service["id"],
        "starts_at": starts_at,
        "ends_at": ends_at,
        "price": "1500.00",
    }
    payload2 = dict(payload1, client_id=c2["id"])

    first = await client.post("/appointments", json=payload1)
    second = await client.post("/appointments", json=payload2)

    assert first.status_code == 200
    assert second.status_code == 409


async def test_forbidden_status_transition_returns_409(client, clean_db, admin_headers):
    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()

    starts_at, ends_at = _slot(date(2026, 11, 25), 10)
    appt = (
        await client.post(
            "/appointments",
            json={
                "client_id": c1["id"],
                "master_id": master["id"],
                "service_id": service["id"],
                "starts_at": starts_at,
                "ends_at": ends_at,
                "price": "1500.00",
            },
        )
    ).json()

    # completed -> created запрещён.
    await client.post(f"/appointments/{appt['id']}/status", json={"status": "completed"})
    resp = await client.post(f"/appointments/{appt['id']}/status", json={"status": "created"})
    assert resp.status_code == 409


async def test_reschedule_and_cancel(client, clean_db, admin_headers):
    from app.api.deps import get_current_client
    from app.main import app

    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()

    starts_at, ends_at = _slot(date(2026, 11, 25), 10)
    appt = (
        await client.post(
            "/appointments",
            json={
                "client_id": c1["id"],
                "master_id": master["id"],
                "service_id": service["id"],
                "starts_at": starts_at,
                "ends_at": ends_at,
                "price": "1500.00",
            },
        )
    ).json()

    # Подменяем текущего клиента (владелец записи) для /cancel и /reschedule.
    app.dependency_overrides[get_current_client] = lambda: type(
        "CurrentClient", (), {"id": c1["id"], "is_admin": False}
    )()

    # Перенос на 11:00 (свободный слот).
    new_start, new_end = _slot(date(2026, 11, 25), 11)
    rescheduled = await client.post(
        f"/appointments/{appt['id']}/reschedule",
        json={"starts_at": new_start, "ends_at": new_end},
    )
    assert rescheduled.status_code == 200

    cancelled = await client.post(f"/appointments/{appt['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


async def test_non_owner_cannot_cancel(client, clean_db, admin_headers):
    from app.api.deps import get_current_client
    from app.main import app

    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()
    c2 = (await client.post("/clients", json={"name": "Пётр"})).json()

    starts_at, ends_at = _slot(date(2026, 11, 25), 10)
    appt = (
        await client.post(
            "/appointments",
            json={
                "client_id": c1["id"],
                "master_id": master["id"],
                "service_id": service["id"],
                "starts_at": starts_at,
                "ends_at": ends_at,
                "price": "1500.00",
            },
        )
    ).json()

    # Запись принадлежит c1, но подменяем текущего клиента на c2 -> 403.
    app.dependency_overrides[get_current_client] = lambda: type(
        "CurrentClient", (), {"id": c2["id"], "is_admin": False}
    )()
    resp = await client.post(f"/appointments/{appt['id']}/cancel")
    assert resp.status_code == 403
