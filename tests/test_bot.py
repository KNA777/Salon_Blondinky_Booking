"""Тесты каркаса бота: обработчики отвечают, не обращаясь к Telegram.

Проверяем только логику хендлеров: какую команду на какой текст возвращает бот.
Реальный Telegram и polling здесь не участвуют, поэтому тест быстрый и без сети.
"""

import pytest

from app.bot.__main__ import require_token
from app.bot.handlers import cmd_help, cmd_start, echo


class FakeMessage:
    """Минимальная имитация aiogram.types.Message: хендлерам нужны только .answer и .text."""

    def __init__(self, text: str | None = None):
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


@pytest.mark.asyncio
async def test_start_greets():
    msg = FakeMessage()
    await cmd_start(msg)
    assert len(msg.answers) == 1
    assert "Здравствуйте" in msg.answers[0]


@pytest.mark.asyncio
async def test_help_lists_commands():
    msg = FakeMessage()
    await cmd_help(msg)
    assert len(msg.answers) == 1
    assert "/start" in msg.answers[0]


@pytest.mark.asyncio
async def test_echo_repeats_text():
    msg = FakeMessage(text="Привет")
    await echo(msg)
    assert msg.answers == ["Вы написали: Привет"]


def test_require_token_ok():
    assert require_token("123:abc") == "123:abc"


def test_require_token_missing_raises():
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        require_token(None)
