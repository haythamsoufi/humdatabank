"""
Extended unit tests for app/utils/request_utils.py

Covers: _JsonFormProxy, get_request_data, get_request_field,
        get_request_list, is_static_asset_request, _is_json_body,
        get_json_or_form, parse_ids_from_request,
        mobile_app_webview_embed_active, mark_mobile_app_webview_embed_request,
        persist_mobile_app_embed_cookie, clear_mobile_app_embed_cookie
"""
import base64
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestJsonFormProxy:
    """Tests for the _JsonFormProxy class."""

    def test_get_existing_key(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"key": "value"})
        assert proxy.get("key") == "value"

    def test_get_missing_key_returns_default(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({})
        assert proxy.get("missing", "default_val") == "default_val"

    def test_get_missing_key_no_default_returns_none(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({})
        assert proxy.get("missing") is None

    def test_get_with_type_coercion_success(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"count": "42"})
        assert proxy.get("count", type=int) == 42

    def test_get_with_type_coercion_failure_returns_default(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"count": "not_a_num"})
        assert proxy.get("count", default=0, type=int) == 0

    def test_get_with_none_value_and_type(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"x": None})
        # val is None so type coercion is skipped, returns None
        assert proxy.get("x", type=int) is None

    def test_getlist_list_value(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"items": [1, 2, 3]})
        assert proxy.getlist("items") == [1, 2, 3]

    def test_getlist_scalar_value_wrapped_in_list(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"item": "value"})
        assert proxy.getlist("item") == ["value"]

    def test_getlist_none_value_returns_empty_list(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"item": None})
        assert proxy.getlist("item") == []

    def test_getlist_missing_key_returns_empty_list(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({})
        assert proxy.getlist("missing") == []

    def test_contains_existing_key(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"key": "value"})
        assert "key" in proxy

    def test_contains_missing_key(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"key": "value"})
        assert "other" not in proxy

    def test_getitem_existing_key(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"key": "value"})
        assert proxy["key"] == "value"

    def test_keys_returns_all_keys(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy({"a": 1, "b": 2})
        assert set(proxy.keys()) == {"a", "b"}

    def test_to_dict(self):
        from app.utils.request_utils import _JsonFormProxy
        data = {"a": 1, "b": 2}
        proxy = _JsonFormProxy(data)
        assert proxy.to_dict() == data

    def test_none_data_normalised_to_empty_dict(self):
        from app.utils.request_utils import _JsonFormProxy
        proxy = _JsonFormProxy(None)
        assert proxy.get("key") is None
        assert proxy.to_dict() == {}


@pytest.mark.unit
class TestGetRequestData:
    def test_json_body_returns_proxy(self, app):
        from app.utils.request_utils import get_request_data, _JsonFormProxy
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data=json.dumps({"key": "value"}),
        ):
            result = get_request_data()
            assert isinstance(result, _JsonFormProxy)
            assert result.get("key") == "value"

    def test_form_body_returns_request_form(self, app):
        from app.utils.request_utils import get_request_data
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={"key": "value"},
        ):
            result = get_request_data()
            assert result.get("key") == "value"

    def test_json_body_with_payload_b64_unwrapped(self, app):
        from app.utils.request_utils import get_request_data
        inner = {"nested_key": "nested_value"}
        encoded = base64.b64encode(json.dumps(inner).encode()).decode()
        body = json.dumps({"payload": encoded})
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data=body,
        ):
            result = get_request_data()
            assert result.get("nested_key") == "nested_value"

    def test_json_body_with_invalid_b64_falls_back_to_raw(self, app):
        from app.utils.request_utils import get_request_data, _JsonFormProxy
        body = json.dumps({"payload": "!!!not-valid-base64!!!"})
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data=body,
        ):
            result = get_request_data()
            # Malformed base64 logs a warning and falls back to the raw dict
            assert isinstance(result, _JsonFormProxy)
            assert "payload" in result

    def test_json_body_with_payload_b64_key(self, app):
        from app.utils.request_utils import get_request_data
        inner = {"alt_key": "alt_value"}
        encoded = base64.b64encode(json.dumps(inner).encode()).decode()
        body = json.dumps({"payload_b64": encoded})
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data=body,
        ):
            result = get_request_data()
            assert result.get("alt_key") == "alt_value"


@pytest.mark.unit
class TestGetRequestField:
    def test_reads_from_proxy(self):
        from app.utils.request_utils import get_request_field, _JsonFormProxy
        proxy = _JsonFormProxy({"name": "Alice"})
        assert get_request_field(proxy, "name") == "Alice"

    def test_default_when_key_missing(self):
        from app.utils.request_utils import get_request_field, _JsonFormProxy
        proxy = _JsonFormProxy({})
        assert get_request_field(proxy, "name", default="Bob") == "Bob"

    def test_coerce_to_int(self):
        from app.utils.request_utils import get_request_field, _JsonFormProxy
        proxy = _JsonFormProxy({"count": "5"})
        assert get_request_field(proxy, "count", coerce=int) == 5

    def test_coerce_failure_returns_default(self):
        from app.utils.request_utils import get_request_field, _JsonFormProxy
        proxy = _JsonFormProxy({"count": "abc"})
        assert get_request_field(proxy, "count", default=0, coerce=int) == 0

    def test_none_data_falls_back_to_request_form(self, app):
        from app.utils.request_utils import get_request_field
        with app.test_request_context(
            "/test",
            method="POST",
            data={"name": "Charlie"},
        ):
            assert get_request_field(None, "name") == "Charlie"

    def test_none_val_skips_coerce(self):
        from app.utils.request_utils import get_request_field, _JsonFormProxy
        proxy = _JsonFormProxy({})
        # key not present -> val is None -> coerce not applied
        result = get_request_field(proxy, "missing", coerce=int)
        assert result is None


@pytest.mark.unit
class TestGetRequestList:
    def test_proxy_getlist(self):
        from app.utils.request_utils import get_request_list, _JsonFormProxy
        proxy = _JsonFormProxy({"items": [1, 2, 3]})
        assert get_request_list(proxy, "items") == [1, 2, 3]

    def test_none_data_uses_request_form(self, app):
        from app.utils.request_utils import get_request_list
        with app.test_request_context(
            "/test",
            method="POST",
            data={"items": "hello"},
        ):
            result = get_request_list(None, "items")
            assert isinstance(result, list)

    def test_plain_dict_falls_back_to_get_then_list(self):
        from app.utils.request_utils import get_request_list
        # dict has no getlist; falls back to src.get()
        data = {"items": [1, 2]}
        assert get_request_list(data, "items") == [1, 2]

    def test_plain_dict_scalar_wrapped(self):
        from app.utils.request_utils import get_request_list
        data = {"item": "val"}
        result = get_request_list(data, "item")
        assert result == ["val"]

    def test_missing_key_returns_empty_list(self):
        from app.utils.request_utils import get_request_list, _JsonFormProxy
        proxy = _JsonFormProxy({})
        assert get_request_list(proxy, "missing") == []


@pytest.mark.unit
class TestGetRequestInt:
    def test_scalar_value(self):
        from app.utils.request_utils import get_request_int, _JsonFormProxy

        proxy = _JsonFormProxy({"section_id": "435"})
        assert get_request_int(proxy, "section_id") == 435

    def test_duplicate_values_use_last_non_empty(self):
        from app.utils.request_utils import get_request_int, _JsonFormProxy

        proxy = _JsonFormProxy({"section_id": ["435", "500"]})
        assert get_request_int(proxy, "section_id") == 500

    def test_invalid_value_returns_default(self):
        from app.utils.request_utils import get_request_int, _JsonFormProxy

        proxy = _JsonFormProxy({"section_id": "not-a-number"})
        assert get_request_int(proxy, "section_id", default=12) == 12


@pytest.mark.unit
class TestIsStaticAssetRequest:
    def test_static_path(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/static/css/main.css"):
            assert is_static_asset_request() is True

    def test_plugins_static_path(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/plugins/static/plugin.js"):
            assert is_static_asset_request() is True

    def test_favicon(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/favicon.ico"):
            assert is_static_asset_request() is True

    def test_manifest_webmanifest(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/manifest.webmanifest"):
            assert is_static_asset_request() is True

    def test_manifest_prefix_path(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/manifest.json"):
            assert is_static_asset_request() is True

    def test_normal_page_is_not_static(self, app):
        from app.utils.request_utils import is_static_asset_request
        with app.test_request_context("/admin/dashboard"):
            assert is_static_asset_request() is False

    def test_static_endpoint_on_req_object(self):
        from app.utils.request_utils import is_static_asset_request
        mock_req = MagicMock()
        mock_req.path = "/admin/page"
        mock_req.endpoint = "static"
        assert is_static_asset_request(mock_req) is True

    def test_plugin_static_endpoint_on_req_object(self):
        from app.utils.request_utils import is_static_asset_request
        mock_req = MagicMock()
        mock_req.path = "/some/path"
        mock_req.endpoint = "plugin_static.my_plugin"
        assert is_static_asset_request(mock_req) is True

    def test_none_endpoint_on_req_object(self):
        from app.utils.request_utils import is_static_asset_request
        mock_req = MagicMock()
        mock_req.path = "/admin/page"
        mock_req.endpoint = None
        assert is_static_asset_request(mock_req) is False


@pytest.mark.unit
class TestIsJsonBody:
    def test_json_content_type_is_json_body(self, app):
        from app.utils.request_utils import _is_json_body
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data="{}",
        ):
            assert _is_json_body() is True

    def test_form_content_type_is_not_json_body(self, app):
        from app.utils.request_utils import _is_json_body
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data="key=val",
        ):
            assert _is_json_body() is False

    def test_no_content_type_is_not_json_body(self, app):
        from app.utils.request_utils import _is_json_body
        with app.test_request_context("/test", method="GET"):
            assert _is_json_body() is False


@pytest.mark.unit
class TestGetJsonOrForm:
    def test_json_body_returns_dict(self, app):
        from app.utils.request_utils import get_json_or_form
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data=json.dumps({"key": "value"}),
        ):
            result = get_json_or_form()
            assert isinstance(result, dict)
            assert result.get("key") == "value"

    def test_form_body_returns_dict(self, app):
        from app.utils.request_utils import get_json_or_form
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={"key": "value"},
        ):
            result = get_json_or_form()
            assert isinstance(result, dict)
            assert result.get("key") == "value"

    def test_empty_json_body_returns_empty_dict(self, app):
        from app.utils.request_utils import get_json_or_form
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            data="null",
        ):
            result = get_json_or_form()
            assert result == {}


@pytest.mark.unit
class TestParseIdsFromRequest:
    def test_json_list(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            headers={"Accept": "application/json"},
            data=json.dumps({"ids": [1, 2, 3]}),
        ):
            assert parse_ids_from_request() == [1, 2, 3]

    def test_json_list_deduplication(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            headers={"Accept": "application/json"},
            data=json.dumps({"ids": [1, 2, 2, 3]}),
        ):
            assert parse_ids_from_request() == [1, 2, 3]

    def test_json_invalid_values_skipped(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            headers={"Accept": "application/json"},
            data=json.dumps({"ids": [1, "bad", None, 3]}),
        ):
            assert parse_ids_from_request() == [1, 3]

    def test_json_non_list_ids_ignored(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/json",
            headers={"Accept": "application/json"},
            data=json.dumps({"ids": "not_a_list"}),
        ):
            assert parse_ids_from_request() == []

    def test_form_comma_separated(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={"ids": "1,2,3"},
        ):
            assert parse_ids_from_request() == [1, 2, 3]

    def test_form_empty_field(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={},
        ):
            assert parse_ids_from_request() == []

    def test_form_invalid_values_skipped(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={"ids": "1,abc,,3"},
        ):
            result = parse_ids_from_request()
            assert result == [1, 3]

    def test_custom_key(self, app):
        from app.utils.request_utils import parse_ids_from_request
        with app.test_request_context(
            "/test",
            method="POST",
            content_type="application/x-www-form-urlencoded",
            data={"user_ids": "5,10"},
        ):
            assert parse_ids_from_request(key="user_ids") == [5, 10]


@pytest.mark.unit
class TestMobileAppWebviewEmbed:
    def test_header_activates_embed(self, app):
        from app.utils.request_utils import (
            mobile_app_webview_embed_active,
            MOBILE_APP_WEBVIEW_HEADER,
            MOBILE_APP_WEBVIEW_HEADER_VALUE,
        )
        with app.test_request_context(
            "/",
            headers={MOBILE_APP_WEBVIEW_HEADER: MOBILE_APP_WEBVIEW_HEADER_VALUE},
        ):
            assert mobile_app_webview_embed_active() is True

    def test_cookie_activates_embed(self, app):
        from app.utils.request_utils import (
            mobile_app_webview_embed_active,
            MOBILE_APP_EMBED_COOKIE_NAME,
            MOBILE_APP_EMBED_COOKIE_VALUE,
        )
        with app.test_request_context(
            "/",
            headers={"Cookie": f"{MOBILE_APP_EMBED_COOKIE_NAME}={MOBILE_APP_EMBED_COOKIE_VALUE}"},
        ):
            assert mobile_app_webview_embed_active() is True

    def test_no_header_no_cookie_is_not_active(self, app):
        from app.utils.request_utils import mobile_app_webview_embed_active
        with app.test_request_context("/"):
            assert mobile_app_webview_embed_active() is False

    def test_wrong_header_value_is_not_active(self, app):
        from app.utils.request_utils import mobile_app_webview_embed_active, MOBILE_APP_WEBVIEW_HEADER
        with app.test_request_context("/", headers={MOBILE_APP_WEBVIEW_HEADER: "wrong-value"}):
            assert mobile_app_webview_embed_active() is False

    def test_mark_sets_g_flag_when_header_present(self, app):
        from flask import g
        from app.utils.request_utils import (
            mark_mobile_app_webview_embed_request,
            MOBILE_APP_WEBVIEW_HEADER,
            MOBILE_APP_WEBVIEW_HEADER_VALUE,
        )
        with app.test_request_context(
            "/",
            headers={MOBILE_APP_WEBVIEW_HEADER: MOBILE_APP_WEBVIEW_HEADER_VALUE},
        ):
            mark_mobile_app_webview_embed_request()
            assert g._hd_mobile_webview_header is True

    def test_mark_sets_g_flag_false_when_no_header(self, app):
        from flask import g
        from app.utils.request_utils import mark_mobile_app_webview_embed_request
        with app.test_request_context("/"):
            mark_mobile_app_webview_embed_request()
            assert g._hd_mobile_webview_header is False

    def test_persist_cookie_when_flag_set(self, app):
        from flask import g, Response
        from app.utils.request_utils import persist_mobile_app_embed_cookie, MOBILE_APP_EMBED_COOKIE_NAME
        with app.test_request_context("/"):
            g._hd_mobile_webview_header = True
            response = Response()
            result = persist_mobile_app_embed_cookie(response)
            assert MOBILE_APP_EMBED_COOKIE_NAME in result.headers.get("Set-Cookie", "")

    def test_persist_cookie_skipped_when_flag_not_set(self, app):
        from flask import g, Response
        from app.utils.request_utils import persist_mobile_app_embed_cookie, MOBILE_APP_EMBED_COOKIE_NAME
        with app.test_request_context("/"):
            g._hd_mobile_webview_header = False
            response = Response()
            result = persist_mobile_app_embed_cookie(response)
            # Cookie should NOT be set
            assert MOBILE_APP_EMBED_COOKIE_NAME not in result.headers.get("Set-Cookie", "")

    def test_persist_cookie_skipped_when_flag_missing(self, app):
        from flask import Response
        from app.utils.request_utils import persist_mobile_app_embed_cookie, MOBILE_APP_EMBED_COOKIE_NAME
        with app.test_request_context("/"):
            response = Response()
            result = persist_mobile_app_embed_cookie(response)
            assert MOBILE_APP_EMBED_COOKIE_NAME not in result.headers.get("Set-Cookie", "")

    def test_clear_embed_cookie(self, app):
        from flask import Response
        from app.utils.request_utils import clear_mobile_app_embed_cookie
        with app.test_request_context("/"):
            response = Response()
            result = clear_mobile_app_embed_cookie(response)
            assert result is response
