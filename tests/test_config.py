import pytest

from bot.config import Config


def test_config_reads_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")

    assert Config.from_env().bot_token == "test-token"


def test_config_reads_telegram_api_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "https://relay.example.com/")

    assert Config.from_env().telegram_api_base_url == "https://relay.example.com/"


def test_config_rejects_missing_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        Config.from_env()


def test_config_requires_webhook_secret_for_cloud_function(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        Config.from_env(require_webhook_secret=True)
