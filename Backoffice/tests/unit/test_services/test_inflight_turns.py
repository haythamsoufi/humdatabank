"""In-process chat turn registry: a second submit joins, it does not start another run."""

from app.services.ai.chat.inflight_turns import begin_turn, finish_turn, get_running_turn


def test_second_begin_joins_the_running_turn():
    user_id = 900001
    client_message_id = "join-me"
    try:
        first, created = begin_turn(
            user_id=user_id,
            client_message_id=client_message_id,
            conversation_id="conv-1",
            request_id="req-1",
        )
        assert created is True
        second, created_again = begin_turn(
            user_id=user_id,
            client_message_id=client_message_id,
            conversation_id="conv-1",
            request_id="req-2",
        )
        assert created_again is False
        assert second.request_id == "req-1"
        assert get_running_turn(user_id=user_id, client_message_id=client_message_id) is first
    finally:
        finish_turn(user_id=user_id, client_message_id=client_message_id, status="cancelled")


def test_finished_turn_can_be_replaced():
    user_id = 900002
    client_message_id = "replace-me"
    try:
        begin_turn(
            user_id=user_id,
            client_message_id=client_message_id,
            conversation_id="conv-2",
            request_id="req-a",
        )
        finish_turn(user_id=user_id, client_message_id=client_message_id, status="completed")
        assert get_running_turn(user_id=user_id, client_message_id=client_message_id) is None
        replacement, created = begin_turn(
            user_id=user_id,
            client_message_id=client_message_id,
            conversation_id="conv-2",
            request_id="req-b",
        )
        assert created is True
        assert replacement.request_id == "req-b"
    finally:
        finish_turn(user_id=user_id, client_message_id=client_message_id, status="cancelled")
