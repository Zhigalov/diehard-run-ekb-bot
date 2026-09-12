from aiogram import Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.messages import WELCOME_TEXT

dispatcher = Dispatcher()


@dispatcher.message(CommandStart())
async def welcome(message: Message) -> None:
    await message.answer(WELCOME_TEXT)
