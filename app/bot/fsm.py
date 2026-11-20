"""Логика сценария записи (FSM).

Здесь сосредоточена вся «умная» часть диалога: что показывать на каждом шаге, как
валидировать выбор пользователя и когда переходить к следующему состоянию. Хендлеры
(handlers.py) отвечают только за приём сообщений и вызов этих функций — так логику
удобно тестировать без Telegram.

Чистые функции-помощники (валидация, тексты кнопок) вынесены отдельно, чтобы их можно
было проверять юнит-тестами без БД.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import get_settings
from app.core.db_context_manager import DBManager
from app.schemas.appointment import AppointmentCreate
from app.schemas.master import MasterOut
from app.schemas.service import ServiceOut
from app.services.slots import get_free_slots

# Сколько дней вперёд предлагать на выбор даты.
DAYS_AHEAD = 7
# Шаг сетки слотов в минутах.
SLOT_STEP_MINUTES = 30

RU_DAYS = {
    "Mon": "Пн",
    "Tue": "Вт",
    "Wed": "Ср",
    "Thu": "Чт",
    "Fri": "Пт",
    "Sat": "Сб",
    "Sun": "Вс",
}


def _salon_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().salon_timezone)


def _service_label(service: ServiceOut, number: int) -> str:
    """Текст кнопки услуги: «1. Маникюр — 45 мин, 1500 ₽»."""
    if service.price == service.price.to_integral_value():
        price = f"{service.price:.0f}"
    else:
        price = str(service.price)
    return f"{number}. {service.name} — {service.duration_minutes} мин, {price} ₽"


def _master_label(master: MasterOut, number: int) -> str:
    """Текст кнопки мастера: «1. Имя мастера»."""
    return f"{number}. {master.name}"


def _start_day() -> date:
    """Первый день, на который можно записаться.

    Если сейчас позже 20:00 по времени салона, запись «на сегодня» обычно уже неактуальна,
    поэтому начинаем с завтрашнего дня. Иначе — с сегодняшнего.
    """
    now = datetime.now(_salon_tz())
    today = now.date()
    if now.time() >= time(20, 0):
        return today + timedelta(days=1)
    return today


def available_days() -> list[date]:
    """Список дат, доступных для выбора (от первой до +DAYS_AHEAD)."""
    start = _start_day()
    return [start + timedelta(days=i) for i in range(DAYS_AHEAD)]


def day_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора даты."""
    buttons = []
    for d in available_days():
        # Получаем английское сокращение (например, 'Thu')
        eng_day = d.strftime("%a")
        # Ищем русский перевод, если нет — оставляем как есть
        ru_day = RU_DAYS.get(eng_day, eng_day)

        # Форматируем текст: 19.11 (Чт)
        text = f"{d.strftime('%d.%m')} ({ru_day})"

        buttons.append([InlineKeyboardButton(text=text, callback_data=f"day:{d.isoformat()}")])

    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_master")])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _slot_label(slot_starts: datetime, slot_ends: datetime) -> str:
    return f"{slot_starts.strftime('%H:%M')}–{slot_ends.strftime('%H:%M')}"


async def services_keyboard(db: DBManager) -> InlineKeyboardMarkup:
    """Клавиатура выбора услуги: активные услуги с ценой и длительностью."""
    services = await db.services.get_all_active_services_bulk(include_inactive=False)
    buttons = [
        [InlineKeyboardButton(text=_service_label(s, i), callback_data=f"service:{s.id}")]
        for i, s in enumerate(services, start=1)
    ]
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def masters_keyboard(db: DBManager, service_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора мастера: только те, кто оказывает выбранную услугу и активны."""
    masters = await db.masters.get_all_active_masters_bulk(include_inactive=False)
    filtered = [m for m in masters if any(s.id == service_id for s in m.services)]
    buttons = [
        [InlineKeyboardButton(text=_master_label(m, i), callback_data=f"master:{m.id}")]
        for i, m in enumerate(filtered, start=1)
    ]
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_service")])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def slots_available(
    db: DBManager, master_id: int, service_id: int, day: date
) -> list[tuple[datetime, datetime]]:
    """Свободные слоты (уже в часовом поясе салона) для мастера+услуги+даты.

    Переиспользует get_free_slots() из app.services.slots — ту же логику, что у API.
    """
    result = await get_free_slots(
        db, master_id, service_id, day, step_minutes=SLOT_STEP_MINUTES, salon_tz=_salon_tz()
    )
    return [(s.starts_at, s.ends_at) for s in result.slots]


async def slots_keyboard(
    db: DBManager, master_id: int, service_id: int, day: date
) -> InlineKeyboardMarkup:
    slots = await slots_available(db, master_id, service_id, day)
    buttons = [
        [
            InlineKeyboardButton(
                text=_slot_label(starts, ends),
                callback_data=f"slot:{starts.astimezone(UTC).isoformat()}",
            )
        ]
        for starts, ends in slots
    ]
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_date")])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def create_appointment(
    db: DBManager,
    client_id: int,
    master_id: int,
    service_id: int,
    slot_starts: datetime,
) -> int:
    """Создаёт запись в БД и возвращает её id.

    slot_starts — aware datetime (обычно UTC). Длительность и цену берём из услуги на момент
    записи: ends_at = starts_at + duration, price копируется в запись, чтобы потом не
    «поехать», если услугу изменят (см. комментарий в модели AppointmentORM).
    """
    service = await db.services.get_one_by_id(id=service_id)
    starts_at = slot_starts if slot_starts.tzinfo is not None else slot_starts.replace(tzinfo=UTC)

    data = AppointmentCreate(
        client_id=client_id,
        master_id=master_id,
        service_id=service_id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=service.duration_minutes),
        price=service.price,
    )
    created = await db.appointments.create_with_conflict_check(data)
    return created.id


async def confirm_text(
    client_name: str,
    master_name: str,
    service_name: str,
    slot_starts: datetime,
) -> str:
    """Текст подтверждения записи, показываемый клиенту."""
    local = slot_starts.astimezone(_salon_tz())
    return (
        f"Запись подтверждена ✅\n\n"
        f"{service_name}\n"
        f"Мастер: {master_name}\n"
        f"Дата и время: {local.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Ждём вас, {client_name}!"
    )
