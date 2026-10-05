from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage

from bot import handlers, reminders
from bot.messages import WELCOME_TEXT


@pytest.mark.parametrize("instant,expected", [
    ("2026-10-09T08:59:59+00:00", False),
    ("2026-10-09T09:00:00+00:00", True),
    ("2026-10-09T09:59:59+00:00", True),
    ("2026-10-09T10:00:00+00:00", False),
    ("2026-10-08T09:00:00+00:00", False),
    ("2026-12-25T09:00:00+00:00", True),
])
def test_moscow_schedule(instant, expected):
    slot = reminders.delivery_slot(datetime.fromisoformat(instant))
    assert bool(slot) == expected
    if slot:
        assert datetime.fromtimestamp(slot[1], timezone.utc).hour == 9


class Store:
    def __init__(self):
        self.active = {1, 2}
        self.sent = set()
        self.leased = set()
        self.delayed = set()

    def due(self, *args):
        return sorted(self.active - self.sent - self.leased - self.delayed)

    def claim(self, chat_id, *args):
        if chat_id not in self.due():
            return False
        self.leased.add(chat_id)
        return True

    def finish(self, chat_id, *args):
        self.sent.add(chat_id)
        self.leased.discard(chat_id)

    def unsubscribe(self, chat_id):
        self.active.discard(chat_id)

    def postpone(self, chat_id, *args):
        self.delayed.add(chat_id)
        self.leased.discard(chat_id)


FRIDAY = datetime.fromisoformat("2026-10-09T09:00:00+00:00")


@pytest.mark.asyncio
async def test_repeated_timer_does_not_resend():
    store = Store()
    bot = Mock(send_message=AsyncMock())
    assert (await reminders.deliver_batch(bot, store, FRIDAY))["sent"] == 2
    assert (await reminders.deliver_batch(bot, store, FRIDAY))["sent"] == 0
    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_no_broadcast_outside_friday_window():
    bot = Mock(send_message=AsyncMock())
    await reminders.deliver_batch(bot, Store(), datetime.fromisoformat("2026-10-10T09:00:00+00:00"))
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TelegramForbiddenError, TelegramNetworkError])
async def test_failed_recipient_does_not_block_others(error):
    store = Store()
    bot = Mock(send_message=AsyncMock(side_effect=[
        error(method=SendMessage(chat_id=1, text="test"), message="test"), None,
    ]))
    stats = await reminders.deliver_batch(bot, store, FRIDAY)
    assert stats["sent"] == 1
    assert store.sent == {2}
    if error is TelegramForbiddenError:
        assert 1 not in store.active
    else:
        assert 1 in store.delayed


@pytest.mark.asyncio
async def test_rate_limit_stops_batch():
    store = Store()
    bot = Mock(send_message=AsyncMock(side_effect=TelegramRetryAfter(
        method=SendMessage(chat_id=1, text="test"), message="test", retry_after=100,
    )))
    assert (await reminders.deliver_batch(bot, store, FRIDAY))["retry"] == 1
    assert bot.send_message.await_count == 1
    assert store.delayed == {1}


@pytest.mark.asyncio
async def test_preview_only_replies_to_caller(monkeypatch):
    sender = AsyncMock()
    monkeypatch.setattr(handlers, "send_reminder", sender)
    message = Mock(chat=Mock(id=777))
    await handlers.reminder_test(message)
    sender.assert_awaited_once_with(message.bot, 777)


@pytest.mark.asyncio
@pytest.mark.parametrize("command,expected", [("/subscribe", "subscribe"),
                                             ("/unsubscribe", "unsubscribe")])
async def test_subscription_command(monkeypatch, command, expected):
    store = Mock()
    monkeypatch.setattr(handlers.subscribers, "enabled", lambda: True)
    monkeypatch.setattr(handlers.subscribers, "get_store", lambda: store)
    message = Mock(text=command, chat=Mock(id=777), answer=AsyncMock())
    await handlers.subscription_command(message)
    assert getattr(store, expected).call_args.args[0] == 777
    message.answer.assert_awaited_once()
    if expected == "subscribe":
        text = message.answer.await_args.args[0]
        assert "14:00" in text
        assert "МСК" not in text


@pytest.mark.asyncio
async def test_start_subscribes_private_chat_and_shows_notice(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    store = Mock()
    monkeypatch.setattr(handlers.subscribers, "enabled", lambda: True)
    monkeypatch.setattr(handlers.subscribers, "get_store", lambda: store)
    sender = AsyncMock()
    monkeypatch.setattr(handlers, "send_welcome", sender)
    message = Mock(chat=Mock(id=777, type="private"))
    await handlers.welcome(message)
    store.subscribe.assert_called_once()
    assert sender.await_args.kwargs["subscription_notice"] is True


@pytest.mark.asyncio
async def test_start_does_not_subscribe_group(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    get_store = Mock()
    monkeypatch.setattr(handlers.subscribers, "get_store", get_store)
    monkeypatch.setattr(handlers, "send_welcome", AsyncMock())
    await handlers.welcome(Mock(chat=Mock(id=-1, type="group")))
    get_store.assert_not_called()


def test_caption_with_subscription_notice_fits():
    from html import unescape
    import re

    plain = unescape(re.sub("<[^>]+>", "", WELCOME_TEXT + reminders.SUBSCRIPTION_NOTE))
    assert len(plain.encode("utf-16-le")) // 2 <= 1024


@pytest.mark.asyncio
async def test_preview_link_and_unsubscribe():
    bot = Mock(send_message=AsyncMock())
    await reminders.send_reminder(bot, 777)
    args = bot.send_message.await_args.kwargs
    assert args["chat_id"] == 777
    assert "/unsubscribe" in args["text"]
    assert "появляется по пятницам" not in args["text"]
    assert args["reply_markup"].inline_keyboard[0][0].url == "https://diehard.run/trainings"


def test_subscription_notice_uses_local_time():
    assert "14:00" in reminders.SUBSCRIPTION_NOTE
    assert "МСК" not in reminders.SUBSCRIPTION_NOTE


@pytest.mark.asyncio
async def test_worker_rejects_webhook_payload():
    with pytest.raises(ValueError):
        await reminders.handler({"body": '{"healthcheck":true}'}, None)
