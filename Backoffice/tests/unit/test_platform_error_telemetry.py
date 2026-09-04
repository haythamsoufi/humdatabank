"""Ajax-save WAF 403 security-event telemetry (no Flask).

If a returning visitor hits 403 again, the platform-error event must record
the page ASSET_VERSION, the loaded ajax-save.js ?v=, and whether wrap-candidate
fields were sent as raw text (stale JS) or b64: (current JS).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
TELEMETRY_PY = BACKOFFICE / "app" / "utils" / "platform_error_telemetry.py"


def _load():
    spec = importlib.util.spec_from_file_location("platform_error_telemetry", TELEMETRY_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestSanitizeAjaxSaveTelemetry:
    def test_version_and_wrap_details_kept(self):
        tel = _load()
        out = tel.sanitize_ajax_save_telemetry({
            "asset_version": "deploy-waf-fix",
            "ajax_save_script_version": "deploy-waf-fix.abc123def456",
            "ajax_save_script_delivery": "disk_cache",
            "ajax_save_script_transfer_size": 0,
            "request_field_count": 40,
            "request_approx_bytes": 8200,
            "request_b64_field_count": 0,
            "request_unwrapped_field_count": 12,
            "request_longest_field_bytes": 1800,
            "request_longest_field_name": "field_value[1414]",
            "request_unwrapped_field_names": ["field_value[1414]", "field_other_text[11]"],
            "response_server": "Microsoft-Azure-Application-Gateway/v2",
        })
        assert out["asset_version"] == "deploy-waf-fix"
        assert out["ajax_save_script_version"] == "deploy-waf-fix.abc123def456"
        assert out["ajax_save_script_delivery"] == "disk_cache"
        assert out["ajax_save_script_transfer_size"] == 0
        assert out["request_b64_field_count"] == 0
        assert out["request_unwrapped_field_count"] == 12
        assert out["request_longest_field_name"] == "field_value[1414]"
        assert out["request_unwrapped_field_names"] == [
            "field_value[1414]",
            "field_other_text[11]",
        ]
        assert out["response_server"] == "Microsoft-Azure-Application-Gateway/v2"

    def test_invalid_values_dropped(self):
        tel = _load()
        out = tel.sanitize_ajax_save_telemetry({
            "asset_version": "bad version\nwith\tcontrol",
            "ajax_save_script_delivery": "totally-made-up",
            "request_unwrapped_field_names": "not-a-list",
            "request_longest_field_name": "field_value[1]; DROP TABLE",
            "request_field_count": "nope",
            "request_approx_bytes": -500,
        })
        assert out["asset_version"] == "badversionwithcontrol"
        assert "ajax_save_script_delivery" not in out
        assert "request_unwrapped_field_names" not in out
        assert out["request_longest_field_name"] == "field_value[1]DROPTABLE"
        assert "request_field_count" not in out
        assert "request_approx_bytes" not in out

    def test_non_dict_returns_empty(self):
        tel = _load()
        assert tel.sanitize_ajax_save_telemetry(None) == {}
        assert tel.sanitize_ajax_save_telemetry("x") == {}


class TestDescriptionExtras:
    def test_includes_version_and_wrap_counts_for_stale_js(self):
        tel = _load()
        extras = tel.format_platform_error_description_extras({
            "request_field_count": 87,
            "request_approx_bytes": 45000,
            "asset_version": "deploy-waf-fix",
            "ajax_save_script_version": "deploy-waf-fix.abc123def456",
            "request_b64_field_count": 0,
            "request_unwrapped_field_count": 12,
        })
        joined = "; ".join(extras)
        assert "87 fields" in joined
        assert "43.9KB" in joined or "44.0KB" in joined
        assert "asset v=deploy-waf-fix" in joined
        assert "ajax-save.js v=deploy-waf-fix.abc123def456" in joined
        assert "0 b64-wrapped" in joined
        assert "12 unwrapped wrap-candidates" in joined

    def test_empty_when_no_telemetry(self):
        tel = _load()
        assert tel.format_platform_error_description_extras({}) == []
        assert tel.format_platform_error_description_extras(None) == []


class TestSanitizerHelpers:
    def test_version_token_strips_spaces_and_controls(self):
        tel = _load()
        assert tel.sanitize_version_token("deploy-waf-fix.abc123") == "deploy-waf-fix.abc123"
        assert tel.sanitize_version_token("bad version\nwith\tcontrol") == "badversionwithcontrol"
        assert tel.sanitize_version_token("") is None

    def test_field_name_keeps_brackets_drops_punctuation(self):
        tel = _load()
        assert tel.sanitize_form_field_name("field_value[1414]") == "field_value[1414]"
        assert tel.sanitize_form_field_name("field_value[1]; DROP TABLE") == "field_value[1]DROPTABLE"

    def test_script_delivery_allow_list(self):
        tel = _load()
        assert tel.sanitize_script_delivery("disk_cache") == "disk_cache"
        assert tel.sanitize_script_delivery("network") == "network"
        assert tel.sanitize_script_delivery("memory") is None

    def test_field_name_list_caps_and_drops_junk(self):
        tel = _load()
        assert tel.sanitize_field_name_list("nope") is None
        assert tel.sanitize_field_name_list(["field_value[1]", "", None, "ok_field"]) == [
            "field_value[1]",
            "ok_field",
        ]
        long_list = [f"field_value[{i}]" for i in range(20)]
        assert len(tel.sanitize_field_name_list(long_list)) == 15
