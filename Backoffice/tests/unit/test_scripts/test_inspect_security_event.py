"""Unit tests for scripts/ops/inspect_security_event.py helpers (no live DB)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit]

SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "ops" / "inspect_security_event.py"
)


@pytest.fixture(scope="module")
def inspect_mod():
    spec = importlib.util.spec_from_file_location("inspect_security_event", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExtractAssignmentIds:
    def test_canonical_and_legacy_paths(self, inspect_mod):
        ids = inspect_mod.extract_assignment_ids(
            "https://databank.ifrc.org/assignment/4410",
            "https://databank.ifrc.org/forms/assignment/1641?page=0",
        )
        assert ids == [4410, 1641]

    def test_dedupes_and_skips_empty(self, inspect_mod):
        ids = inspect_mod.extract_assignment_ids(
            None,
            "",
            "/assignment/12#section",
            "see /assignment/12 again",
        )
        assert ids == [12]

    def test_no_match(self, inspect_mod):
        assert inspect_mod.extract_assignment_ids("https://databank.ifrc.org/") == []


class TestFormatting:
    def test_format_anonymous_user(self, inspect_mod):
        assert inspect_mod.format_user(None) == "anonymous"

    def test_format_named_user(self, inspect_mod):
        label = inspect_mod.format_user(
            {"id": 56, "email": "catalin.ilies@ifrc.org", "name": "Catalin Ilies"}
        )
        assert label == "Catalin Ilies <catalin.ilies@ifrc.org> (id=56)"

    def test_enum_value(self, inspect_mod):
        assert inspect_mod.enum_value(SimpleNamespace(value="pending")) == "pending"
        assert inspect_mod.enum_value(None) is None

    def test_context_excerpt_keeps_summary_not_full_metrics(self, inspect_mod):
        excerpt = inspect_mod.context_excerpt(
            {
                "url": "https://databank.ifrc.org/",
                "likely_causes": ["upstream_gateway_timeout"],
                "diagnostics_summary": "HTTP 502",
                "worker_metrics": {
                    "worker_pid": 32571,
                    "in_flight_count": 0,
                    "stale_in_flight_count": 0,
                    "traffic_last_60s": 2,
                    "traffic_last_5m": 26,
                    "redis_cross_worker": False,
                    "db_pool": {"size": 10, "checked_out": 1, "overflow": -8},
                    "in_flight_requests": [{"path": "/slow"}],
                },
            }
        )
        assert excerpt["url"] == "https://databank.ifrc.org/"
        assert excerpt["worker_pid"] == 32571
        assert excerpt["db_pool"] == "1/10 checked out (overflow -8)"
        assert "in_flight_requests" not in excerpt


class TestParseArgs:
    def test_event_id(self, inspect_mod):
        args = inspect_mod.parse_args(["894"])
        assert args.event_id == 894
        assert args.list is False

    def test_list_filters(self, inspect_mod):
        args = inspect_mod.parse_args(
            ["--list", "--unresolved", "--severity", "high", "--type", "platform_502_bad_gateway"]
        )
        assert args.list is True
        assert args.unresolved is True
        assert args.severity == "high"
        assert args.event_type == "platform_502_bad_gateway"

    def test_requires_id_or_list(self, inspect_mod):
        with pytest.raises(SystemExit):
            inspect_mod.parse_args([])

    def test_rejects_id_and_list(self, inspect_mod):
        with pytest.raises(SystemExit):
            inspect_mod.parse_args(["894", "--list"])
