import asyncio
from os import environ

from aiogram import Bot

from bot.config import Config


async def main() -> None:
    config = Config.from_env(require_webhook_secret=True)
    webhook_url = environ.get("WEBHOOK_URL", "").strip()
    if not webhook_url.startswith("https://"):
        raise RuntimeError("WEBHOOK_URL must be a valid HTTPS URL")

    async with Bot(config.bot_token) as telegram_bot:
        await telegram_bot.set_webhook(
            url=webhook_url,
            secret_token=config.webhook_secret,
            allowed_updates=["message"],
            drop_pending_updates=True,
        )
        info = await telegram_bot.get_webhook_info()
        print(f"Webhook configured: {info.url}")


if __name__ == "__main__":
    asyncio.run(main())
