import base64
import hmac
import json
from typing import Any

from aiogram import Bot
from aiogram.types import Update

from bot.config import Config
from bot.handlers import dispatcher

_telegram_bot: Bot | None = None


def _header(event: dict[str, Any], name: str) -> str | None:
    expected_name = name.casefold()
    for key, value in (event.get("headers") or {}).items():
        if key.casefold() == expected_name:
            return str(value)
    return None


def _decode_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if isinstance(body, dict):
        return body
    if not isinstance(body, str):
        raise ValueError("Webhook request body must be a JSON object")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Webhook request body must be a JSON object")
    return parsed


def _get_bot(token: str) -> Bot:
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = Bot(token=token)
    return _telegram_bot


async def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    config = Config.from_env(require_webhook_secret=True)
    received_secret = _header(event, "X-Telegram-Bot-Api-Secret-Token")
    if received_secret is None or not hmac.compare_digest(
        received_secret,
        config.webhook_secret or "",
    ):
        return {"statusCode": 401, "body": "Unauthorized"}

    telegram_bot = _get_bot(config.bot_token)
    update = Update.model_validate(_decode_body(event), context={"bot": telegram_bot})
    await dispatcher.feed_update(telegram_bot, update)
    return {"statusCode": 200, "body": "OK"}
