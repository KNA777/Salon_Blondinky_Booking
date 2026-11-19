"""Обработчики сообщений и inline-кнопок бота.

Тонкая прослойка между aiogram и логикой FSM (fsm.py): хендлер принимает сообщение и
callback, извлекает данные, вызывает логику и отвечает пользователю. Вся «умная» логика
(что показывать, как валидировать) живёт в fsm.py и testлируется отдельно.
"""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot import fsm
from app.bot.states import BookingState
from app.bot.storage import BookingStorage
from app.core.db_context_manager import DBManager
from app.schemas.client import ClientCreate

router = Router(name="booking")


# --- Текстовые команды ---------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, db: DBManager, storage: BookingStorage) -> None:
    """Начало: регистрируем/находим клиента по telegram_id и предлагаем выбрать услугу."""
    user_id = message.from_user.id
    client = await db.clients.upsert_by_telegram_id(
        ClientCreate(name=message.from_user.full_name or "Клиент", telegram_id=user_id)
    )

    await storage.reset(user_id)
    await storage.set_state(user_id, BookingState.CHOOSE_SERVICE)
    await storage.save(user_id, client_id=client.id)

    keyboard = await fsm.services_keyboard(db)
    await message.answer("Запишемся к мастеру? Выберите услугу 👇", reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Я помогу записаться к мастеру.\n\n"
        "/start — начать запись\n"
        "/cancel — отменить и начать заново\n"
        "/help — эта справка"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, storage: BookingStorage) -> None:
    await storage.reset(message.from_user.id)
    await message.answer("Запись отменена. Напишите /start, чтобы начать заново.")


# --- Inline-кнопки (callback_query) ---------------------------------------------


def _telegram_id_from_query(query: CallbackQuery) -> int:
    return query.from_user.id


@router.callback_query(F.data == "cancel")
async def cb_cancel(query: CallbackQuery, storage: BookingStorage) -> None:
    await storage.reset(_telegram_id_from_query(query))
    await query.message.edit_text("Запись отменена. Напишите /start, чтобы начать заново.")
    await query.answer()


@router.callback_query(F.data.startswith("service:"))
async def cb_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    service_id = int(query.data.split(":", 1)[1])
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    await storage.save(user_id, service_id=service_id)

    keyboard = await fsm.masters_keyboard(db, service_id)
    await query.message.edit_text("Теперь выберите мастера 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("master:"))
async def cb_master(query: CallbackQuery, storage: BookingStorage) -> None:
    master_id = int(query.data.split(":", 1)[1])
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    await storage.save(user_id, master_id=master_id)

    keyboard = fsm.day_keyboard()
    await query.message.edit_text("Выберите дату 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("day:"))
async def cb_day(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    day_text = query.data.split(":", 1)[1]
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SLOT)
    await storage.save(user_id, day=day_text)

    ctx = await storage.get_context(user_id)
    day = date.fromisoformat(day_text)
    keyboard = await fsm.slots_keyboard(db, ctx.master_id, ctx.service_id, day)
    await query.message.edit_text("Свободное время 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("slot:"))
async def cb_slot(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    ctx = await storage.get_context(user_id)
    starts_at = datetime.fromisoformat(query.data.split(":", 1)[1])

    await fsm.create_appointment(
        db, ctx.client_id, ctx.master_id, ctx.service_id, starts_at
    )

    master = await db.masters.get_one_with_services(ctx.master_id)
    service = await db.services.get_one_by_id(id=ctx.service_id)
    client = await db.clients.get_one_by_id(id=ctx.client_id)

    text = await fsm.confirm_text(client.name, master.name, service.name, starts_at)

    await storage.set_state(user_id, BookingState.DONE)
    await query.message.edit_text(text)
    await query.answer()


@router.callback_query(F.data == "back_to_service")
async def cb_back_to_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SERVICE)
    keyboard = await fsm.services_keyboard(db)
    await query.message.edit_text("Выберите услугу 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data == "back_to_master")
async def cb_back_to_master(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    ctx = await storage.get_context(user_id)
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    keyboard = await fsm.masters_keyboard(db, ctx.service_id)
    await query.message.edit_text("Выберите мастера 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data == "back_to_date")
async def cb_back_to_date(query: CallbackQuery, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    keyboard = fsm.day_keyboard()
    await query.message.edit_text("Выберите дату 👇", reply_markup=keyboard)
    await query.answer()

