import base64
import json
from unittest.mock import AsyncMock, Mock

import pytest

import index


def test_decode_body_from_json_string() -> None:
    assert index._decode_body({"body": '{"update_id": 1}'}) == {"update_id": 1}


def test_decode_base64_body() -> None:
    encoded = base64.b64encode(json.dumps({"update_id": 2}).encode()).decode()

    assert index._decode_body({"body": encoded, "isBase64Encoded": True}) == {"update_id": 2}


@pytest.mark.asyncio
async def test_handler_rejects_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "correct-secret")

    response = await index.handler(
        {
            "headers": {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
            "body": "{}",
        },
        None,
    )

    assert response == {"statusCode": 401, "body": "Unauthorized"}


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_handler_closes_session_and_retries_failures(monkeypatch, fails) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "correct-secret")
    bot = Mock()
    bot.session.close = AsyncMock()
    monkeypatch.setattr(index, "_get_bot", lambda *args: bot)
    feed = AsyncMock(side_effect=TimeoutError() if fails else None)
    monkeypatch.setattr(index.dispatcher, "feed_update", feed)
    response = await index.handler({
        "headers": {"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
        "body": '{"update_id": 1}',
    }, None)
    assert response["statusCode"] == (503 if fails else 200)
    bot.session.close.assert_awaited_once()
