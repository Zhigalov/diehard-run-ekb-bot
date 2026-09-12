from bot.captcha import CAPTCHA_PREFIX, create_captcha, verify_captcha


def test_captcha_has_one_correct_answer_and_fits_callback_limit() -> None:
    question, buttons = create_captcha(
        chat_id=-1001234567890,
        user_id=987654321,
        secret="test-secret",
        question_id=0,
    )

    assert question
    answers = [verify_captcha(data, "test-secret") for _, data in buttons]
    assert sum(answer is not None and answer.is_correct for answer in answers) == 1
    assert all(len(data.encode()) <= 64 for _, data in buttons)


def test_captcha_is_bound_to_signature() -> None:
    _, buttons = create_captcha(
        chat_id=-1001234567890,
        user_id=987654321,
        secret="test-secret",
        question_id=1,
    )
    _, callback_data = buttons[0]

    assert callback_data.startswith(f"{CAPTCHA_PREFIX}:")
    assert verify_captcha(callback_data, "another-secret") is None


def test_captcha_rejects_tampered_answer() -> None:
    _, buttons = create_captcha(
        chat_id=-1001234567890,
        user_id=987654321,
        secret="test-secret",
        question_id=2,
    )
    _, callback_data = buttons[0]
    parts = callback_data.split(":")
    parts[4] = "2" if parts[4] != "2" else "1"

    assert verify_captcha(":".join(parts), "test-secret") is None
