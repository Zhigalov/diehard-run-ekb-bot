from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.messages import (
    JOIN_REQUEST_MISSING_TEXT,
    RULES_ACCEPTED_TEXT,
    RULES_TEXT,
    WELCOME_TEXT,
)

dispatcher = Dispatcher()
ACCEPT_RULES_PREFIX = "accept_rules"


def accept_rules_callback_data(chat_id: int, user_id: int) -> str:
    return f"{ACCEPT_RULES_PREFIX}:{chat_id}:{user_id}"


def parse_accept_rules_callback_data(data: str) -> tuple[int, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != ACCEPT_RULES_PREFIX:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


@dispatcher.message(CommandStart())
async def welcome(message: Message) -> None:
    await message.answer(WELCOME_TEXT)


@dispatcher.chat_join_request()
async def show_rules(join_request: ChatJoinRequest) -> None:
    callback_data = accept_rules_callback_data(
        chat_id=join_request.chat.id,
        user_id=join_request.from_user.id,
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Правила прочитал(а), принимаю",
                    callback_data=callback_data,
                )
            ]
        ]
    )
    await join_request.bot.send_message(
        chat_id=join_request.user_chat_id,
        text=WELCOME_TEXT,
    )
    await join_request.bot.send_message(
        chat_id=join_request.user_chat_id,
        text=RULES_TEXT,
        reply_markup=keyboard,
    )


@dispatcher.callback_query(F.data.startswith(f"{ACCEPT_RULES_PREFIX}:"))
async def accept_rules(callback: CallbackQuery) -> None:
    parsed = parse_accept_rules_callback_data(callback.data or "")
    if parsed is None:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return

    chat_id, expected_user_id = parsed
    if callback.from_user.id != expected_user_id:
        await callback.answer("Эта кнопка предназначена другому пользователю", show_alert=True)
        return

    try:
        await callback.bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=callback.from_user.id,
        )
    except TelegramBadRequest:
        await callback.answer(JOIN_REQUEST_MISSING_TEXT, show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text(RULES_ACCEPTED_TEXT)
    await callback.answer()
