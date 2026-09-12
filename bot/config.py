from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    webhook_secret: str | None = None
    telegram_api_base_url: str | None = None

    @classmethod
    def from_env(cls, *, require_webhook_secret: bool = False) -> "Config":
        token = environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN environment variable is required")

        webhook_secret = environ.get("WEBHOOK_SECRET", "").strip() or None
        if require_webhook_secret and not webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET environment variable is required")

        telegram_api_base_url = environ.get("TELEGRAM_API_BASE_URL", "").strip() or None

        return cls(
            bot_token=token,
            webhook_secret=webhook_secret,
            telegram_api_base_url=telegram_api_base_url,
        )
