import asyncio
import base64
import hmac
import json
import time
from typing import Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Update

from bot.config import Config
from bot.handlers import dispatcher

def _log(message: str, **fields: Any) -> None:
    print(json.dumps({"level": "INFO", "message": message, **fields}), flush=True)


async def _log_api_request(make_request: Any, bot: Bot, method: Any) -> Any:
    started = time.monotonic()
    name = method.__api_method__
    _log("telegram_request_started", method=name)
    try:
        result = await make_request(bot, method)
    except Exception as error:
        _log("telegram_request_failed", method=name, error_type=type(error).__name__,
             elapsed=round(time.monotonic() - started, 3))
        raise
    _log("telegram_request_completed", method=name,
         elapsed=round(time.monotonic() - started, 3))
    return result


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


def _get_bot(token: str, api_base_url: str | None = None) -> Bot:
    options: dict[str, Any] = {"timeout": 8}
    if api_base_url:
        options["api"] = TelegramAPIServer.from_base(api_base_url)
    session = AiohttpSession(**options)
    session.middleware(_log_api_request)
    return Bot(token=token, session=session)


async def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    _log("webhook_started", request_id=getattr(context, "request_id", None))
    config = Config.from_env(require_webhook_secret=True)
    received_secret = _header(event, "X-Telegram-Bot-Api-Secret-Token")
    if received_secret is None or not hmac.compare_digest(
        received_secret,
        config.webhook_secret or "",
    ):
        return {"statusCode": 401, "body": "Unauthorized"}

    telegram_bot = _get_bot(config.bot_token, config.telegram_api_base_url)
    try:
        update = Update.model_validate(_decode_body(event), context={"bot": telegram_bot})
        async with asyncio.timeout(25):
            await dispatcher.feed_update(telegram_bot, update)
    except Exception as error:
        # Do not log exception text: HTTP errors may contain the bot token or user data.
        _log("webhook_failed", error_type=type(error).__name__)
        return {"statusCode": 503, "body": "Temporary processing failure"}
    finally:
        await telegram_bot.session.close()
    _log("webhook_completed")
    return {"statusCode": 200, "body": "OK"}
