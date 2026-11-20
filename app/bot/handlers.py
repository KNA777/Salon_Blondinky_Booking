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


def _message_from_query(query: CallbackQuery) -> Message:
    """Достаёт редактируемое сообщение из callback.

    В личных чатах query.message — это обычный Message. aiogram помечает его как
    `Message | InaccessibleMessage | None` (для каналов/старых сообщений), но для записи
    клиента нам нужно именно редактируемое сообщение — иначе просто нечего обновлять.
    Поднимаем ошибку, а не молча пропускаем: молчание скрыло бы реальный сбой сценария.
    """
    message = query.message
    if not isinstance(message, Message):
        raise RuntimeError("Callback без редактируемого сообщения (InaccessibleMessage/None)")
    return message


# --- Текстовые команды ---------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, db: DBManager, storage: BookingStorage) -> None:
    """Начало: регистрируем/находим клиента по telegram_id и предлагаем выбрать услугу."""
    from_user = message.from_user
    if from_user is None:
        return
    user_id = from_user.id
    client = await db.clients.upsert_by_telegram_id(
        ClientCreate(name=from_user.full_name or "Клиент", telegram_id=user_id)
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
    from_user = message.from_user
    if from_user is None:
        return
    await storage.reset(from_user.id)
    await message.answer("Запись отменена. Напишите /start, чтобы начать заново.")


# --- Inline-кнопки (callback_query) ---------------------------------------------


def _telegram_id_from_query(query: CallbackQuery) -> int:
    return query.from_user.id


def _callback_payload(query: CallbackQuery) -> str:
    """Возвращает часть callback_data после префикса (например, id услуги/слота).

    query.data — это `str` у всех наших колбэков (мы сами их генерируем в fsm.py). aiogram
    помечает поле как `str | None` на случай game/inline-колбэков без data, поэтому здесь
    явно проверяем и поднимаем ошибку, если данных вдруг нет.
    """
    if query.data is None:
        raise RuntimeError("Callback без data")
    return query.data.split(":", 1)[1]


@router.callback_query(F.data == "cancel")
async def cb_cancel(query: CallbackQuery, storage: BookingStorage) -> None:
    await storage.reset(_telegram_id_from_query(query))
    await _message_from_query(query).edit_text(
        "Запись отменена. Напишите /start, чтобы начать заново."
    )
    await query.answer()


@router.callback_query(F.data.startswith("service:"))
async def cb_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    service_id = int(_callback_payload(query))
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    await storage.save(user_id, service_id=service_id)

    keyboard = await fsm.masters_keyboard(db, service_id)
    await _message_from_query(query).edit_text("Теперь выберите мастера 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("master:"))
async def cb_master(query: CallbackQuery, storage: BookingStorage) -> None:
    master_id = int(_callback_payload(query))
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    await storage.save(user_id, master_id=master_id)

    keyboard = fsm.day_keyboard()
    await _message_from_query(query).edit_text("Выберите дату 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("day:"))
async def cb_day(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    day_text = _callback_payload(query)
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SLOT)
    await storage.save(user_id, day=day_text)

    ctx = await storage.get_context(user_id)
    if ctx.master_id is None or ctx.service_id is None:
        raise RuntimeError("В контексте записи нет master_id/service_id перед выбором слота")
    day = date.fromisoformat(day_text)
    keyboard = await fsm.slots_keyboard(db, ctx.master_id, ctx.service_id, day)
    await _message_from_query(query).edit_text("Свободное время 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data.startswith("slot:"))
async def cb_slot(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    ctx = await storage.get_context(user_id)
    if ctx.client_id is None or ctx.master_id is None or ctx.service_id is None:
        raise RuntimeError("В контексте записи не хватает client_id/master_id/service_id")
    starts_at = datetime.fromisoformat(_callback_payload(query))

    # Идемпотентность повторного нажатия: если запись уже завершена (state == DONE),
    # это повторный клик по кнопке слота (двойное нажатие/повторный апдейт). Не создаём
    # вторую запись, а просто отвечаем тем же текстом подтверждения.
    if ctx.state == BookingState.DONE:
        master = await db.masters.get_one_with_services(ctx.master_id)
        service = await db.services.get_one_by_id(id=ctx.service_id)
        client = await db.clients.get_one_by_id(id=ctx.client_id)
        text = await fsm.confirm_text(client.name, master.name, service.name, starts_at)
        await _message_from_query(query).edit_text(text)
        await query.answer()
        return

    await fsm.create_appointment(db, ctx.client_id, ctx.master_id, ctx.service_id, starts_at)

    master = await db.masters.get_one_with_services(ctx.master_id)
    service = await db.services.get_one_by_id(id=ctx.service_id)
    client = await db.clients.get_one_by_id(id=ctx.client_id)

    text = await fsm.confirm_text(client.name, master.name, service.name, starts_at)

    await storage.set_state(user_id, BookingState.DONE)
    await _message_from_query(query).edit_text(text)
    await query.answer()


@router.callback_query(F.data == "back_to_service")
async def cb_back_to_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SERVICE)
    keyboard = await fsm.services_keyboard(db)
    await _message_from_query(query).edit_text("Выберите услугу 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data == "back_to_master")
async def cb_back_to_master(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    ctx = await storage.get_context(user_id)
    if ctx.service_id is None:
        raise RuntimeError("В контексте записи нет service_id перед выбором мастера")
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    keyboard = await fsm.masters_keyboard(db, ctx.service_id)
    await _message_from_query(query).edit_text("Выберите мастера 👇", reply_markup=keyboard)
    await query.answer()


@router.callback_query(F.data == "back_to_date")
async def cb_back_to_date(query: CallbackQuery, storage: BookingStorage) -> None:
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    keyboard = fsm.day_keyboard()
    await _message_from_query(query).edit_text("Выберите дату 👇", reply_markup=keyboard)
    await query.answer()
