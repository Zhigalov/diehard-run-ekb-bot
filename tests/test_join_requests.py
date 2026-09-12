from bot.handlers import accept_rules_callback_data, parse_accept_rules_callback_data


def test_accept_rules_callback_is_bound_to_chat_and_user() -> None:
    data = accept_rules_callback_data(chat_id=-1001234567890, user_id=987654321)

    assert data == "accept_rules:-1001234567890:987654321"
    assert parse_accept_rules_callback_data(data) == (-1001234567890, 987654321)


def test_rejects_invalid_accept_rules_callback() -> None:
    assert parse_accept_rules_callback_data("accept_rules:not-a-chat:42") is None
    assert parse_accept_rules_callback_data("something_else:-1001:42") is None
