import asyncio
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

REMINDER_TEXT = (
    "🏃 Планы на воскресенье? Не забудь зарегистрироваться на лонг!\n\n"
    "Перейди на diehard.run/trainings, выбери нужную тренировку и нажми "
    "«Принять участие».\n\n"
    "До встречи на старте!\n\n"
    "Отключить напоминания: /unsubscribe"
)
SUBSCRIPTION_NOTE = (
    "\n\n🔔 Напомню о регистрации в пятницу в 14:00. Отключить: /unsubscribe"
)
MOSCOW = ZoneInfo("Europe/Moscow")


async def send_reminder(bot, chat_id):
    await bot.send_message(
        chat_id=chat_id, text=REMINDER_TEXT,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏃 Зарегистрироваться", url="https://diehard.run/trainings"),
        ]]),
    )


def delivery_slot(now: datetime):
    local = now.astimezone(MOSCOW)
    # Start at 12:00; the rest of the hour is reserved for batches and retries.
    if local.weekday() != 4 or local.hour != 12:
        return None
    start = local.replace(minute=0, second=0, microsecond=0)
    return start.date().isoformat(), int(start.timestamp())


async def deliver_batch(bot, store, now=None, budget=45):
    slot = delivery_slot(now or datetime.now(MOSCOW))
    stats = {"sent": 0, "disabled": 0, "retry": 0, "skipped": 0}
    if slot is None:
        return stats
    week, cutoff = slot
    deadline = time.monotonic() + budget
    owner = uuid.uuid4().hex
    while time.monotonic() < deadline:
        ids = await asyncio.to_thread(store.due, week, cutoff, int(time.time()))
        if not ids:
            break
        for chat_id in ids:
            if time.monotonic() >= deadline:
                return stats
            claimed = await asyncio.to_thread(store.claim, chat_id, week, cutoff,
                                              int(time.time()), owner)
            if not claimed:
                stats["skipped"] += 1
                continue
            try:
                await send_reminder(bot, chat_id)
            except TelegramForbiddenError:
                await asyncio.to_thread(store.unsubscribe, chat_id)
                stats["disabled"] += 1
            except TelegramBadRequest:
                # Do not disable subscriptions for an unknown payload/config error.
                await asyncio.to_thread(store.postpone, chat_id, owner, int(time.time()) + 3600)
                stats["retry"] += 1
            except TelegramRetryAfter as error:
                await asyncio.to_thread(store.postpone, chat_id, owner,
                                        int(time.time()) + error.retry_after + 1)
                stats["retry"] += 1
                return stats  # Respect a bot-wide Telegram rate limit.
            except (TelegramNetworkError, TelegramServerError):
                await asyncio.to_thread(store.postpone, chat_id, owner, int(time.time()) + 120)
                stats["retry"] += 1
            else:
                await asyncio.to_thread(store.finish, chat_id, owner, week)
                stats["sent"] += 1
            await asyncio.sleep(0.05)  # At most 20 sends/s; no paid broadcast.
    return stats


async def handler(event, context):
    # Separate PRIVATE function: cannot be reached through the public webhook.
    from bot.config import Config
    from bot.subscribers import get_store
    from index import _get_bot, _log

    if event == {"healthcheck": True}:
        store = await asyncio.to_thread(get_store)
        await asyncio.to_thread(store.health)
        return {"statusCode": 200, "body": "OK"}
    messages = event.get("messages", [])
    if not messages or any(m.get("event_metadata", {}).get("event_type") !=
                           "yandex.cloud.events.serverless.triggers.TimerMessage"
                           for m in messages):
        raise ValueError("Only timer events are accepted")
    config = Config.from_env()
    bot = _get_bot(config.bot_token, config.telegram_api_base_url)
    try:
        store = await asyncio.to_thread(get_store)
        stats = await deliver_batch(bot, store)
        _log("reminder_batch_completed", **stats)
        return stats
    except Exception as error:
        _log("reminder_batch_failed", error_type=type(error).__name__)
        raise RuntimeError("Reminder batch failed") from None
    finally:
        await bot.session.close()
