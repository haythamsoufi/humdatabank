from app.utils.activity_form_data_redaction import redact_activity_form_data


def test_drops_password_and_csrf():
    fd = redact_activity_form_data(
        [
            ("name", "Alice"),
            ("password", "secret"),
            ("csrf_token", "abc"),
            ("api_key", "k"),
        ]
    )
    assert fd == {"name": "Alice"}


def test_truncates_long_strings():
    long = "x" * 200
    fd = redact_activity_form_data([("note", long)], max_value_len=50)
    assert len(fd["note"]) == 53
    assert fd["note"].endswith("...")
