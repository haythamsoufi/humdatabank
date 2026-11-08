"""Access-log query-string redaction (app/logging_config.py SensitiveQueryFilter)."""

from __future__ import annotations

import logging

from app.logging_config import SensitiveQueryFilter


def _record(msg, args):
    return logging.LogRecord("gunicorn.access", logging.INFO, __file__, 1, msg, args, None)


def test_gunicorn_dict_atoms_are_redacted_and_still_format():
    fmt = '%(h)s "%(r)s" %(s)s "%(f)s"'
    atoms = {
        "h": "10.0.0.1",
        "r": "GET /reset?token=abc123&next=/home HTTP/1.1",
        "s": "200",
        "f": "https://example.org/x?api_key=zzz&a=1",
    }
    record = _record(fmt, (atoms,))
    assert SensitiveQueryFilter().filter(record) is True
    line = record.getMessage()
    assert "abc123" not in line and "zzz" not in line
    assert "next=/home" in line and "a=1" in line


def test_werkzeug_tuple_args_are_redacted():
    record = _record('%s - - [%s] "%s" %s -', ("127.0.0.1", "now", "GET /x?password=hunter2 HTTP/1.1", "200"))
    SensitiveQueryFilter().filter(record)
    assert "hunter2" not in record.getMessage()


def test_message_without_args_is_redacted():
    record = _record("GET /x?secret=s3 HTTP/1.1", None)
    SensitiveQueryFilter().filter(record)
    assert "s3" not in record.getMessage()


def test_format_template_with_placeholders_is_never_rewritten():
    record = _record("GET /x?token=%s", ("value",))
    SensitiveQueryFilter().filter(record)
    assert record.msg == "GET /x?token=%s"
    assert record.getMessage() == "GET /x?token=value"
