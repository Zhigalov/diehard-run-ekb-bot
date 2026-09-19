from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.captcha import CAPTCHA_PREFIX, create_captcha, verify_captcha
from bot.config import Config
from bot.messages import (
    CAPTCHA_TEXT,
    CAPTCHA_WRONG_TEXT,
    JOIN_APPROVED_TEXT,
    JOIN_REQUEST_MISSING_TEXT,
    RULES_TEXT,
    WELCOME_TEXT,
)

dispatcher = Dispatcher()
ACCEPT_RULES_PREFIX = "accept_rules"
WELCOME_IMAGE_PATH = Path(__file__).with_name("assets") / "welcome.jpg"


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


def captcha_keyboard(chat_id: int, user_id: int, secret: str) -> tuple[str, InlineKeyboardMarkup]:
    question, buttons = create_captcha(chat_id, user_id, secret)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=callback_data)]
            for label, callback_data in buttons
        ]
    )
    return question, keyboard


async def send_welcome(bot: Bot, chat_id: int) -> None:
    await bot.send_photo(chat_id=chat_id, photo=FSInputFile(WELCOME_IMAGE_PATH))
    await bot.send_message(chat_id=chat_id, text=WELCOME_TEXT, parse_mode="HTML")


@dispatcher.message(CommandStart())
async def welcome(message: Message) -> None:
    await send_welcome(message.bot, message.chat.id)


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
    await send_welcome(join_request.bot, join_request.user_chat_id)
    await join_request.bot.send_message(
        chat_id=join_request.user_chat_id,
        text=RULES_TEXT,
        parse_mode="HTML",
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

    config = Config.from_env(require_webhook_secret=True)
    question, keyboard = captcha_keyboard(
        chat_id,
        callback.from_user.id,
        config.webhook_secret or "",
    )
    if callback.message:
        await callback.message.edit_text(
            f"{CAPTCHA_TEXT}\n\n{question}",
            reply_markup=keyboard,
        )
    await callback.answer()


@dispatcher.callback_query(F.data.startswith(f"{CAPTCHA_PREFIX}:"))
async def check_captcha(callback: CallbackQuery) -> None:
    config = Config.from_env(require_webhook_secret=True)
    answer = verify_captcha(callback.data or "", config.webhook_secret or "")
    if answer is None:
        await callback.answer("Некорректная или устаревшая кнопка", show_alert=True)
        return

    if callback.from_user.id != answer.user_id:
        await callback.answer("Эта кнопка предназначена другому пользователю", show_alert=True)
        return

    if not answer.is_correct:
        await callback.answer(CAPTCHA_WRONG_TEXT, show_alert=True)
        return

    try:
        await callback.bot.approve_chat_join_request(
            chat_id=answer.chat_id,
            user_id=callback.from_user.id,
        )
    except TelegramBadRequest:
        await callback.answer(JOIN_REQUEST_MISSING_TEXT, show_alert=True)
        return

    if callback.message:
        await callback.message.edit_text(JOIN_APPROVED_TEXT)
    await callback.answer()
