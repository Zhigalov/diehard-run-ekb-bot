import pytest

from bot.config import Config


def test_config_reads_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")

    assert Config.from_env().bot_token == "test-token"


def test_config_rejects_missing_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        Config.from_env()
