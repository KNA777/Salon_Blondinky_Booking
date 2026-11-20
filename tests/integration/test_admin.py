"""Интеграционные тесты админки (задачи 14/16): JWT для администратора.

Проверяем:
- вход администратора (/auth/admin/login) и отказ не-админу;
- защиту админ-эндпоинтов (403 без прав, 401 без токена);
- админский просмотр записей на день (/appointments/admin/day);
- подтверждение записи админом (/appointments/{id}/confirm).

Фикстуры определены в tests/conftest.py; при недоступном Postgres тесты пропускаются.
"""


async def test_admin_login_returns_token(client, clean_db, admin_headers):
    """Админ (is_admin=True) логинится и получает JWT в httpOnly cookie."""
    # admin_headers уже создал админа с паролем admin-pass / телефоном +79990000000.
    resp = await client.post(
        "/auth/admin/login",
        json={"phone": "+79990000000", "password": "admin-pass"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Токен уходит в cookie, а не в тело; в теле остаётся только client_id.
    assert "access_token" not in body
    assert body["client_id"]
    set_cookie = resp.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "HttpOnly" in set_cookie


async def test_non_admin_cannot_login_as_admin(client, clean_db, client_headers):
    """Не-админ получает 403 при попытке админского входа."""
    resp = await client.post(
        "/auth/admin/login",
        json={"phone": "+79990000001", "password": "client-pass"},
    )
    assert resp.status_code == 403


async def test_admin_login_wrong_password_returns_401(client, clean_db, admin_headers):
    resp = await client.post(
        "/auth/admin/login",
        json={"phone": "+79990000000", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_cookie_auth_flow(client, clean_db, admin_headers):
    """Полный cookie-флоу: логин ставит куку -> защищённый эндпоинт авторизует по куке.

    httpx.AsyncClient сам сохраняет куки из Set-Cookie и подставляет их в последующие
    запросы, поэтому после логина POST /services должен пройти без явного Authorization.
    """
    login = await client.post(
        "/auth/admin/login",
        json={"phone": "+79990000000", "password": "admin-pass"},
    )
    assert login.status_code == 200

    # Защищённый эндпоинт — без заголовков, только за счёт cookie.
    created = await client.post(
        "/services",
        json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
    )
    assert created.status_code == 200
    assert created.json()["name"] == "Маникюр"


async def test_logout_clears_cookie(client, clean_db, admin_headers):
    """POST /auth/logout удаляет access_token из cookie (max-age=0)."""
    login = await client.post(
        "/auth/admin/login",
        json={"phone": "+79990000000", "password": "admin-pass"},
    )
    assert login.status_code == 200

    logout = await client.post("/auth/logout")
    assert logout.status_code == 204
    set_cookie = logout.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "max-age=0" in set_cookie.lower() or "Max-Age=0" in set_cookie


async def test_admin_day_listing_requires_admin(client, clean_db, admin_headers, client_headers):
    """Создаём запись на день, затем смотрим /appointments/admin/day под админом и не-админом."""
    from datetime import UTC, datetime, timedelta

    # Подготовим услугу и мастера от имени админа.
    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()

    # Запись на 2026-11-25 10:00-11:00 Москва = 07:00-08:00 UTC.
    start = datetime(2026, 11, 25, 7, 0, tzinfo=UTC)
    end = start + timedelta(minutes=60)
    await client.post(
        "/appointments",
        json={
            "client_id": c1["id"],
            "master_id": master["id"],
            "service_id": service["id"],
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "price": "1500.00",
        },
        headers=admin_headers,
    )

    # Не-админ -> 403.
    denied = await client.get(
        "/appointments/admin/day", params={"day": "2026-11-25"}, headers=client_headers
    )
    assert denied.status_code == 403

    # Админ -> 200 и видит запись.
    day_list = await client.get(
        "/appointments/admin/day", params={"day": "2026-11-25"}, headers=admin_headers
    )
    assert day_list.status_code == 200
    appointments = day_list.json()
    assert len(appointments) == 1
    assert appointments[0]["client_id"] == c1["id"]


async def test_admin_confirm_appointment(client, clean_db, admin_headers, client_headers):
    """Админ подтверждает запись created -> confirmed; не-админ не может."""
    from datetime import UTC, datetime, timedelta

    service = (
        await client.post(
            "/services",
            json={"name": "Маникюр", "duration_minutes": 60, "price": "1500.00"},
            headers=admin_headers,
        )
    ).json()
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()
    c1 = (await client.post("/clients", json={"name": "Иван"})).json()

    start = datetime(2026, 11, 25, 7, 0, tzinfo=UTC)
    end = start + timedelta(minutes=60)
    appt = (
        await client.post(
            "/appointments",
            json={
                "client_id": c1["id"],
                "master_id": master["id"],
                "service_id": service["id"],
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "price": "1500.00",
            },
            headers=admin_headers,
        )
    ).json()

    # Не-админ не может подтвердить -> 403.
    denied = await client.post(f"/appointments/{appt['id']}/confirm", headers=client_headers)
    assert denied.status_code == 403

    # Админ подтверждает -> confirmed.
    confirmed = await client.post(f"/appointments/{appt['id']}/confirm", headers=admin_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"


async def test_masters_creation_requires_admin(client, clean_db, client_headers):
    """POST /masters без админских прав -> 403."""
    resp = await client.post("/masters", json={"name": "Анна"}, headers=client_headers)
    assert resp.status_code == 403


async def test_working_hours_creation_requires_admin(
    client, clean_db, admin_headers, client_headers
):
    """POST /masters/{id}/working-hours без админских прав -> 403."""
    master = (await client.post("/masters", json={"name": "Мария"}, headers=admin_headers)).json()

    denied = await client.post(
        f"/masters/{master['id']}/working-hours",
        json={"weekday": 2, "start_time": "10:00", "end_time": "12:00"},
        headers=client_headers,
    )
    assert denied.status_code == 403
