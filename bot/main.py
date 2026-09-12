import asyncio
import logging

from aiogram import Bot

from bot.config import Config
from bot.handlers import dispatcher


async def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    async with Bot(token=config.bot_token) as telegram_bot:
        await dispatcher.start_polling(telegram_bot)


if __name__ == "__main__":
    asyncio.run(main())
