import hashlib
import hmac
import secrets
from dataclasses import dataclass

CAPTCHA_PREFIX = "captcha"
SIGNATURE_LENGTH = 12


@dataclass(frozen=True, slots=True)
class CaptchaQuestion:
    text: str
    options: tuple[str, ...]
    correct_option: int


@dataclass(frozen=True, slots=True)
class CaptchaAnswer:
    chat_id: int
    user_id: int
    is_correct: bool


QUESTIONS = (
    CaptchaQuestion(
        text="Какую дистанцию мы бежим на Лонге?",
        options=("5 км", "10 км", "20 км"),
        correct_option=2,
    ),
    CaptchaQuestion(
        text="Во сколько стартует Лонг на Плотинке?",
        options=("07:00", "08:30", "10:00"),
        correct_option=1,
    ),
    CaptchaQuestion(
        text="Сколько человек может бежать в одном ряду?",
        options=("Не больше трёх", "Не больше пяти", "Сколько угодно"),
        correct_option=0,
    ),
)


def _signature(payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:SIGNATURE_LENGTH]


def create_captcha(
    chat_id: int,
    user_id: int,
    secret: str,
    *,
    question_id: int | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    selected_question_id = (
        secrets.randbelow(len(QUESTIONS)) if question_id is None else question_id
    )
    question = QUESTIONS[selected_question_id]
    option_ids = list(range(len(question.options)))
    secrets.SystemRandom().shuffle(option_ids)

    buttons = []
    for option_id in option_ids:
        payload = f"{CAPTCHA_PREFIX}:{selected_question_id}:{chat_id}:{user_id}:{option_id}"
        callback_data = f"{payload}:{_signature(payload, secret)}"
        buttons.append((question.options[option_id], callback_data))

    return question.text, buttons


def verify_captcha(data: str, secret: str) -> CaptchaAnswer | None:
    parts = data.split(":")
    if len(parts) != 6 or parts[0] != CAPTCHA_PREFIX:
        return None

    payload = ":".join(parts[:-1])
    if not hmac.compare_digest(parts[-1], _signature(payload, secret)):
        return None

    try:
        question_id = int(parts[1])
        chat_id = int(parts[2])
        user_id = int(parts[3])
        option_id = int(parts[4])
        question = QUESTIONS[question_id]
    except (IndexError, ValueError):
        return None

    if option_id < 0 or option_id >= len(question.options):
        return None

    return CaptchaAnswer(
        chat_id=chat_id,
        user_id=user_id,
        is_correct=option_id == question.correct_option,
    )
