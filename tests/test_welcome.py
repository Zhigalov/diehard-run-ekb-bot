from html.parser import HTMLParser
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramServerError
from aiogram.methods import SendPhoto
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.handlers import send_welcome
from bot.messages import WELCOME_TEXT


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TelegramNetworkError, TelegramBadRequest, TelegramServerError])
async def test_photo_failure_does_not_block_welcome(monkeypatch, error) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    bot = Mock(id=123)
    bot.send_photo = AsyncMock(side_effect=error(
        method=SendPhoto(chat_id=1, photo="test"), message="timeout",
    ))
    bot.send_message = AsyncMock()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Join", url="https://example.com/join"),
    ]])
    await send_welcome(bot, 1, reply_markup=keyboard)
    bot.send_message.assert_awaited_once_with(
        chat_id=1, text=WELCOME_TEXT, parse_mode="HTML", reply_markup=keyboard,
    )


@pytest.mark.asyncio
async def test_photo_uses_url_then_cached_telegram_file(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("WELCOME_PHOTO_URL", "https://example.com/welcome.jpg")
    bot = Mock(id=456)
    bot.send_photo = AsyncMock(return_value=Mock(photo=[Mock(file_id="cached-photo")]))
    bot.send_message = AsyncMock()
    await send_welcome(bot, 1)
    await send_welcome(bot, 1)
    calls = bot.send_photo.await_args_list
    assert calls[0].kwargs["photo"] == "https://example.com/welcome.jpg"
    assert calls[1].kwargs["photo"] == "cached-photo"
    for call in calls:
        assert call.kwargs["caption"] == WELCOME_TEXT
        assert call.kwargs["parse_mode"] == "HTML"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_welcome_photo_contains_join_button(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Join", url="https://example.com/join"),
    ]])
    bot = Mock(id=789)
    bot.send_photo = AsyncMock(return_value=Mock(photo=[]))
    bot.send_message = AsyncMock()
    await send_welcome(bot, 1, reply_markup=keyboard)
    assert bot.send_photo.await_args.kwargs["reply_markup"] == keyboard
    assert bot.send_photo.await_args.kwargs["caption"] == WELCOME_TEXT
    bot.send_message.assert_not_awaited()


def test_welcome_fits_telegram_caption_limit() -> None:
    parts = []

    class TextParser(HTMLParser):
        def handle_data(self, data):
            parts.append(data)

    TextParser().feed(WELCOME_TEXT)
    # Count UTF-16 code units conservatively, including astral emoji.
    assert len("".join(parts).encode("utf-16-le")) // 2 <= 1024
