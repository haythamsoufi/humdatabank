import logging

from app.utils.api_errors import (
    GENERIC_BAD_REQUEST_MESSAGE,
    GENERIC_NOT_FOUND_MESSAGE,
    ClientInputError,
    client_error_message,
)


def test_client_input_error_message_is_passed_through():
    assert client_error_message(ClientInputError("query is required")) == "query is required"


def test_plain_value_error_gets_generic_message_and_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="app.utils.api_errors"):
        msg = client_error_message(ValueError("/etc/passwd: bad"), context="x")
    assert msg == GENERIC_BAD_REQUEST_MESSAGE
    assert "/etc/passwd" not in msg
    assert any("/etc/passwd" in r.getMessage() for r in caplog.records)


def test_custom_fallback():
    assert client_error_message(KeyError("k"), GENERIC_NOT_FOUND_MESSAGE) == GENERIC_NOT_FOUND_MESSAGE


def test_client_input_error_is_still_a_value_error():
    assert issubclass(ClientInputError, ValueError)
