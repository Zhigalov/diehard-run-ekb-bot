from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SendPhoto

from bot.handlers import send_welcome
from bot.messages import WELCOME_TEXT


@pytest.mark.asyncio
async def test_photo_timeout_does_not_block_welcome(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    bot = Mock(id=123)
    bot.send_photo = AsyncMock(side_effect=TelegramNetworkError(
        method=SendPhoto(chat_id=1, photo="test"), message="timeout",
    ))
    bot.send_message = AsyncMock()
    await send_welcome(bot, 1)
    bot.send_message.assert_awaited_once_with(
        chat_id=1, text=WELCOME_TEXT, parse_mode="HTML", reply_markup=None,
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
