"""Эндпоинты предоплаты (задача 18, каркас).

Каркас: фиксируем намерение оплатить запись и храним её статус. Реальную оплату
выполняет платёжный провайдер (Telegram Payments / ЮKassa): создание инвойса ->
оплата клиентом -> подтверждающий webhook провайдера обновляет статус.

Правила доступа:
- Создать предоплату может владелец записи или админ.
- Просмотреть предоплату — владелец записи или админ.
- Обновить статус (имитация webhook провайдера) — только админ/сервер. В реальном
  деплое этот эндпоинт должен быть закрыт секретом провайдера, а не доступом админа;
  здесь упрощённо для каркаса.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentAdminDep, CurrentClientDep, DBDep
from app.schemas.payment import PaymentCreate, PaymentOut, PaymentUpdate

router = APIRouter(prefix="/payments", tags=["Payments"])


async def _authorize_payment_access(
    db: DBDep, appointment_id: int, current_client: CurrentClientDep
) -> None:
    """Разрешает операции с предоплатой записи её владельцу или админу."""
    if current_client.is_admin:
        return
    try:
        appointment = await db.appointments.get_one_by_id(id=appointment_id)
    except Exception:  # noqa: BLE001 — ниже переводим в 404 с понятным текстом
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена"
        ) from None
    if appointment.client_id != current_client.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для предоплаты этой записи",
        )


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(
    db: DBDep, data: PaymentCreate, current_client: CurrentClientDep
) -> PaymentOut:
    """Создать намерение предоплаты за запись.

    Если сумма не задана (0), берём цену услуги из записи — так бот может предложить
    «оплатить запись целиком» без передачи суммы. Владелец записи или админ.
    """
    await _authorize_payment_access(db, data.appointment_id, current_client)

    if data.amount <= 0:
        appointment = await db.appointments.get_one_by_id(id=data.appointment_id)
        # amount — Decimal; цена записи тоже Decimal. Сумма предоплаты по умолчанию = цена.
        data = PaymentCreate(
            appointment_id=data.appointment_id,
            amount=appointment.price,
            provider=data.provider,
        )

    return await db.payments.create_payment(data)


@router.get("/appointment/{appointment_id}", response_model=PaymentOut | None)
async def get_payment_for_appointment(
    db: DBDep, appointment_id: int, current_client: CurrentClientDep
) -> PaymentOut | None:
    """Получить последнюю предоплату по записи (владелец или админ)."""
    await _authorize_payment_access(db, appointment_id, current_client)
    return await db.payments.get_by_appointment(appointment_id)


@router.patch("/{payment_id}", response_model=PaymentOut)
async def update_payment_status(
    db: DBDep, payment_id: int, data: PaymentUpdate, _admin: CurrentAdminDep
) -> PaymentOut:
    """Обновить статус предоплаты (имитация подтверждения провайдера).

    В каркасе доступно только админу. В боевом деплое замените проверку на валидацию
    секрета/подписи webhook платёжного провайдера (Telegram Payments / ЮKassa).
    """
    return await db.payments.update_payment_status(payment_id, data)
