"""Напоминания о записи (задача 13).

За 24 часа и за 2 часа до начала записи клиенту приходит сообщение в Telegram. Задача
состоит из двух частей:

1. **Логика** (pure-функции) — какие записи «созрели» для напоминания и текст сообщения.
   Тестируется без БД и Telegram.

2. **Планировщик** (send_due_reminders) — периодически опрашивает БД, отбирает записи,
   которым пора, шлёт сообщение и помечает отправленным. Вызывается из background-таска
   (lifespan FastAPI или процесс бота).

Идемпотентность обеспечивается маркерами reminded_24h_at / reminded_2h_at в таблице
appointments: отбор идёт по `marker IS NULL`, а отметка — через `UPDATE ... WHERE IS NULL`,
поэтому даже параллельный запуск планировщика не отправит одно напоминание дважды.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.db_context_manager import DBManager
from app.models import AppointmentORM

# Соответствие: метка напоминания -> атрибут-маркер на модели (и колонка в БД).
REMINDERS = (
    ("24h", "reminded_24h_at"),
    ("2h", "reminded_2h_at"),
)


def reminder_text(
    service_name: str, master_name: str, starts_at: datetime, offset_label: str
) -> str:
    """Текст напоминания, отправляемый клиенту."""
    human = "24 часа" if offset_label == "24h" else "2 часа"
    return (
        f"Напоминание о записи ⏰\n\n"
        f"Услуга: {service_name}\n"
        f"Мастер: {master_name}\n"
        f"Время: {starts_at.isoformat(timespec='minutes')}\n\n"
        f"До начала осталось {human}. Ждём вас!"
    )


def is_due(
    starts_at: datetime,
    now: datetime,
    offset_minutes: int,
    poll_interval_seconds: int,
) -> bool:
    """True, если для записи со временем starts_at пора отправлять напоминание.

    Напоминание «за N минут» считается созревшим, когда до начала осталось из интервала
    (N, N - poll_interval] минут. Верхняя граница исключает пересечения между разными
    оффсетами (24h и 2h), нижняя привязана к шагу планировщика, чтобы запись не «проспали».
    """
    delta_seconds = (starts_at - now).total_seconds()
    upper = offset_minutes * 60
    lower = upper - poll_interval_seconds
    return lower < delta_seconds <= upper


async def send_due_reminders(db: DBManager, bot: Any, now: datetime) -> int:
    """Отправляет все «созревшие» напоминания и возвращает их количество.

    db — DBManager (см. app/core/db_context_manager.py); bot — aiogram Bot или любой объект
    с методом send_message(chat_id, text). Ошибка отправки одного сообщения не останавливает
    остальные напоминания.
    """
    settings = get_settings()
    offsets = settings.reminder_offsets_minutes
    poll = settings.reminder_poll_interval_seconds

    sent = 0
    for (label, marker_attr), offset in zip(REMINDERS, offsets, strict=True):
        marker = getattr(AppointmentORM, marker_attr)
        # Широкое окно: все активные записи, начинающиеся от «прямо сейчас» до «осталось
        # offset минут». Точную проверку делает is_due() ниже.
        due = await db.appointments.get_due_reminders(
            marker,
            now,
            window_start=now - timedelta(minutes=5),
            window_end=now + timedelta(minutes=offset + 1),
        )
        for appointment in due:
            starts = appointment.starts_at
            if not is_due(starts, now, offset, poll):
                continue
            client = appointment.client
            service = appointment.service
            master = appointment.master
            if client is None or client.telegram_id is None:
                continue  # клиент без telegram_id (заведён вручную) — отправить некуда
            text = reminder_text(service.name, master.name, starts, label)
            try:
                await bot.send_message(chat_id=client.telegram_id, text=text)
            except Exception:  # noqa: BLE001 — одно неудавшееся сообщение не роняет рассылку
                continue
            await db.appointments.mark_reminder_sent(appointment.id, marker, now)
            sent += 1

    return sent


async def reminder_loop(session_factory: Any, bot: Any, stop_event: asyncio.Event) -> None:
    """Бесконечный цикл рассылки напоминаний.

    Запускается как background-таск (в lifespan FastAPI или в процессе бота). Каждые
    reminder_poll_interval_seconds секунд открывает сессию БД и вызывает send_due_reminders.
    Останавливается по stop_event (asyncio.Event), который процесс выставляет при shutdown.
    """
    from app.core.db_context_manager import DBManager

    settings = get_settings()
    while not stop_event.is_set():
        async with DBManager(session_factory) as db:
            try:
                await send_due_reminders(db, bot, datetime.now())
            except Exception:  # noqa: BLE001 — сбой одного тика не должен гасить планировщик
                pass
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.reminder_poll_interval_seconds
            )
        except TimeoutError:
            continue
