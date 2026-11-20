"""Интеграционные тесты предоплаты (задача 18, каркас).

Проверяем, что эндпоинты платежей создают/читают/обновляют предоплату к записи,
что доступ к чужой записи закрыт, а обновление статуса доступно только админу.
"""

from datetime import UTC, date, datetime, timedelta


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _slot(day: date, wall_hour: int, duration_min: int = 60) -> tuple[str, str]:
    start = datetime(day.year, day.month, day.day, wall_hour, 0, tzinfo=UTC) - timedelta(hours=3)
    return _iso(start), _iso(start + timedelta(minutes=duration_min))


async def _make_appointment(client, admin_headers) -> dict:
    """Создаёт услугу, мастера, клиента и запись; возвращает JSON записи + id клиента."""
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
            headers=admin_headers,
        )
    ).json()
    return appt, c1["id"]


async def test_payment_create_and_get(client, clean_db, admin_headers):
    appt, _ = await _make_appointment(client, admin_headers)

    # Создаём намерение предоплаты (сумма по умолчанию = цена записи).
    created = await client.post(
        "/payments",
        json={"appointment_id": appt["id"], "amount": "1500.00"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    payment = created.json()
    assert payment["status"] == "pending"
    assert payment["amount"] == "1500.00"

    # Читаем предоплату по записи.
    fetched = await client.get(f"/payments/appointment/{appt['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payment["id"]

    # Обновляем статус (админ) — эмуляция webhook провайдера.
    updated = await client.patch(
        f"/payments/{payment['id']}",
        json={"status": "paid", "provider_payment_id": "invoice-123"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "paid"
    assert updated.json()["provider_payment_id"] == "invoice-123"
    assert updated.json()["paid_at"] is not None


async def test_payment_status_update_requires_admin(
    client, clean_db, admin_headers, client_headers
):
    appt, _ = await _make_appointment(client, admin_headers)
    payment = (
        await client.post(
            "/payments",
            json={"appointment_id": appt["id"], "amount": "1500.00"},
            headers=admin_headers,
        )
    ).json()

    # Не-админ не может обновить статус платежа.
    resp = await client.patch(
        f"/payments/{payment['id']}",
        json={"status": "paid"},
        headers=client_headers,
    )
    assert resp.status_code == 403
