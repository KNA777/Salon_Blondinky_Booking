"""Обработчики сообщений и inline-кнопок бота.

Тонкая прослойка между aiogram и логикой FSM (fsm.py): хендлер принимает сообщение и
callback, извлекает данные, вызывает логику и отвечает пользователю. Вся «умная» логика
(что показывать, как валидировать) живёт в fsm.py и testлируется отдельно.
"""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

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


async def _safe_edit(
    query: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Безопасно редактирует сообщение, игнорируя «невалидные» ошибки Telegram.

    При повторной доставке одного и того же апдейта (Telegram повторяет запрос, если не
    получил ответ, или пользователь долго не отвечает на inline-кнопку) вызовы ``edit_text``
    и ``answer`` могут упасть с ``TelegramBadRequest``: «message is not modified» (тот же
    текст/кнопки) или «query is too old» (устаревший callback). Это не ошибка сценария, а
    нормальное следствие идемпотентной повторной обработки — поэтому молча игнорируем их,
    а не роняем вебхук с HTTP 500 и не заставляем Telegram повторять апдейт бесконечно.
    """
    try:
        await _message_from_query(query).edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        # Текст/разметка не изменились либо callback устарел — ничего делать не нужно.
        pass


async def _safe_answer(query: CallbackQuery) -> None:
    """Безопасно закрывает всплывающее уведомление (закрывает loading).

    ``answer()`` у устаревшего callback тоже бросает ``TelegramBadRequest`` (query is too
    old); эту ошибку нужно глушить, иначе повторная доставка апдейта упадёт с 500.
    """
    try:
        await query.answer()
    except (TelegramBadRequest, TelegramRetryAfter):
        pass


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
    """Показать справку по командам бота."""
    await message.answer(
        "Я помогу записаться к мастеру.\n\n"
        "/start — начать запись\n"
        "/cancel — отменить и начать заново\n"
        "/help — эта справка"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, storage: BookingStorage) -> None:
    """Отменить запись и сбросить состояние диалога."""
    from_user = message.from_user
    if from_user is None:
        return
    await storage.reset(from_user.id)
    await message.answer("Запись отменена. Напишите /start, чтобы начать заново.")


# --- Inline-кнопки (callback_query) ---------------------------------------------


def _telegram_id_from_query(query: CallbackQuery) -> int:
    """Telegram id пользователя, отправившего callback."""
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
    """Обработать кнопку «Отмена»: сбросить состояние и сообщить пользователю."""
    await storage.reset(_telegram_id_from_query(query))
    await _safe_edit(query, "Запись отменена. Напишите /start, чтобы начать заново.")
    await _safe_answer(query)


@router.callback_query(F.data.startswith("service:"))
async def cb_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    """Сохранить выбранную услугу и предложить выбрать мастера."""
    service_id = int(_callback_payload(query))
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    await storage.save(user_id, service_id=service_id)

    keyboard = await fsm.masters_keyboard(db, service_id)
    await _safe_edit(query, "Теперь выберите мастера 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data.startswith("master:"))
async def cb_master(query: CallbackQuery, storage: BookingStorage) -> None:
    """Сохранить выбранного мастера и предложить выбрать дату."""
    master_id = int(_callback_payload(query))
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    await storage.save(user_id, master_id=master_id)

    keyboard = fsm.day_keyboard()
    await _safe_edit(query, "Выберите дату 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data.startswith("day:"))
async def cb_day(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    """Сохранить выбранную дату и предложить выбрать свободный слот."""
    day_text = _callback_payload(query)
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SLOT)
    await storage.save(user_id, day=day_text)

    ctx = await storage.get_context(user_id)
    if ctx.master_id is None or ctx.service_id is None:
        raise RuntimeError("В контексте записи нет master_id/service_id перед выбором слота")
    day = date.fromisoformat(day_text)
    keyboard = await fsm.slots_keyboard(db, ctx.master_id, ctx.service_id, day)
    await _safe_edit(query, "Свободное время 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data.startswith("slot:"))
async def cb_slot(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    """Создать запись по выбранному слоту и показать подтверждение."""
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
        await _safe_edit(query, text)
        await _safe_answer(query)
        return

    appointment_id = await fsm.create_appointment(
        db, ctx.client_id, ctx.master_id, ctx.service_id, starts_at
    )

    master = await db.masters.get_one_with_services(ctx.master_id)
    service = await db.services.get_one_by_id(id=ctx.service_id)
    client = await db.clients.get_one_by_id(id=ctx.client_id)

    text = await fsm.confirm_text(client.name, master.name, service.name, starts_at)

    # Предоплата (задача 18, каркас): создаём намерение оплатить и показываем кнопку.
    # Реальная оплата — у провайдера; здесь кнопка ведёт на имитацию оплаты.
    payment_id, amount = await fsm.create_prepayment(db, appointment_id)
    text += f"\n\n💳 Предоплата {amount} ₽ — нажмите «Оплатить»."

    await storage.set_state(user_id, BookingState.DONE)
    await _safe_edit(
        query, text, reply_markup=fsm.prepayment_keyboard(payment_id)
    )
    await _safe_answer(query)


@router.callback_query(F.data == "back_to_service")
async def cb_back_to_service(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    """Вернуться на шаг выбора услуги."""
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_SERVICE)
    keyboard = await fsm.services_keyboard(db)
    await _safe_edit(query, "Выберите услугу 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data == "back_to_master")
async def cb_back_to_master(query: CallbackQuery, db: DBManager, storage: BookingStorage) -> None:
    """Вернуться на шаг выбора мастера."""
    user_id = _telegram_id_from_query(query)
    ctx = await storage.get_context(user_id)
    if ctx.service_id is None:
        raise RuntimeError("В контексте записи нет service_id перед выбором мастера")
    await storage.set_state(user_id, BookingState.CHOOSE_MASTER)
    keyboard = await fsm.masters_keyboard(db, ctx.service_id)
    await _safe_edit(query, "Выберите мастера 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data == "back_to_date")
async def cb_back_to_date(query: CallbackQuery, storage: BookingStorage) -> None:
    """Вернуться на шаг выбора даты."""
    user_id = _telegram_id_from_query(query)
    await storage.set_state(user_id, BookingState.CHOOSE_DATE)
    keyboard = fsm.day_keyboard()
    await _safe_edit(query, "Выберите дату 👇", reply_markup=keyboard)
    await _safe_answer(query)


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(query: CallbackQuery, db: DBManager) -> None:
    """Кнопка «Оплатить» (задача 18, каркас).

    Реальная оплата выполняется провайдером (Telegram Payments sendInvoice / ЮKassa).
    В каркасе имитируем начало оплаты: показываем, что платёж создан и ожидает
    подтверждения от провайдера. Статус записи о предоплате остаётся pending до
    вебхука провайдера, который переведёт его в paid.
    """
    payment_id = int(_callback_payload(query))
    await db.payments.get_by_appointment_and_id(payment_id)
    await _safe_edit(
        query,
        "💳 Оплата подключена.\n\n"
        "В каркасе реальный платёжный провайдер ещё не подключён: после интеграции "
        "Telegram Payments / ЮKassa здесь будет инициироваться настоящий инвойс.\n\n"
        "Сумма предоплаты зафиксирована — статус обновится автоматически после оплаты.",
    )
    await _safe_answer(query)


@router.callback_query(F.data == "pay_later")
async def cb_pay_later(query: CallbackQuery) -> None:
    """Кнопка «Позже»: пропустить оплату, запись остаётся."""
    await _safe_edit(query, "Хорошо, оплатить можно позже. До встречи! 💇‍♀️")
    await _safe_answer(query)
