"""Обработчики сообщений бота.

Пока это каркас: бот отвечает на /start и /help и повторяет всё остальное текстом.
Логика записи клиента (выбор услуги → мастера → даты → слота) будет добавлена следующими
шагами, поверх этого каркаса.
"""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="base")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Здравствуйте! Я бот салона. Здесь можно будет записаться к мастеру.\n"
        "Отправьте /help, чтобы узнать, что я умею."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Пока я умею немного: отвечаю на /start и /help, а остальные сообщения повторяю.\n"
        "Запись к мастеру появится в следующих обновлениях."
    )


@router.message(F.text)
async def echo(message: Message) -> None:
    # Эхо нужно только чтобы проверить, что бот получает сообщения. Уберём, когда появится
    # настоящий сценарий записи.
    await message.answer(f"Вы написали: {message.text}")
