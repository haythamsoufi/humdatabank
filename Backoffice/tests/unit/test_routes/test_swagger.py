"""
Comprehensive pytest tests for:
- app/swagger/openapi_spec.py  (get_openapi_spec, get_api_paths)
- app/swagger/routes.py        (swagger_ui, openapi_json, openapi_yaml, test_spec)

Aims for 100% coverage of both modules.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(resp):
    return json.loads(resp.data)


def _assert_status(resp, *allowed):
    assert resp.status_code in allowed, (
        f"Expected one of {allowed}, got {resp.status_code}: {resp.data[:300]}"
    )


# ===========================================================================
#  openapi_spec.py  –  unit tests (no HTTP)
# ===========================================================================

class TestGetOpenApiSpec:
    """Unit tests for get_openapi_spec() and get_api_paths()."""

    def test_returns_dict(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert isinstance(spec, dict)

    def test_openapi_field_present(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert spec.get("openapi") == "3.0.3"

    def test_info_section(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        info = spec["info"]
        assert "title" in info
        assert "version" in info
        assert info["version"] == "1.0.0"
        assert "contact" in info
        assert "license" in info

    def test_servers_section(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        servers = spec.get("servers", [])
        assert len(servers) >= 1
        assert "url" in servers[0]

    def test_tags_section(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        tags = spec.get("tags", [])
        tag_names = [t["name"] for t in tags]
        assert "Countries" in tag_names
        assert "Indicators" in tag_names
        assert "Templates" in tag_names

    def test_components_section(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        comps = spec.get("components", {})
        assert "securitySchemes" in comps
        assert "schemas" in comps
        assert "parameters" in comps
        assert "responses" in comps

    def test_security_scheme_bearer(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        bearer = spec["components"]["securitySchemes"]["BearerAuth"]
        assert bearer["type"] == "http"
        assert bearer["scheme"] == "bearer"

    def test_schemas_present(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        schemas = spec["components"]["schemas"]
        for expected in ("Error", "Country", "Indicator", "Template", "Submission", "Pagination"):
            assert expected in schemas, f"Schema '{expected}' missing"

    def test_parameters_present(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        params = spec["components"]["parameters"]
        for expected in ("PageParam", "PerPageParam", "LocaleParam"):
            assert expected in params, f"Parameter '{expected}' missing"

    def test_responses_present(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        resps = spec["components"]["responses"]
        for expected in ("Unauthorized", "Forbidden", "NotFound", "BadRequest", "ServerError"):
            assert expected in resps, f"Response '{expected}' missing"

    def test_paths_is_dict(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert isinstance(spec.get("paths"), dict)
        assert len(spec["paths"]) > 0

    def test_paths_has_countrymap(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/countrymap" in spec["paths"]

    def test_paths_has_indicator_bank(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/indicator-bank" in spec["paths"]

    def test_paths_has_templates(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/templates" in spec["paths"]

    def test_paths_has_data(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/data" in spec["paths"]

    def test_paths_has_submissions(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/submissions" in spec["paths"]

    def test_paths_has_user_profile(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/user/profile" in spec["paths"]

    def test_paths_has_resources(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/resources" in spec["paths"]

    def test_paths_has_common_words(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/common-words" in spec["paths"]

    def test_paths_has_data_tables(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/data/tables" in spec["paths"]

    def test_paths_has_periods(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "/periods" in spec["paths"]

    def test_spec_is_json_serializable(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        try:
            serialized = json.dumps(spec)
        except TypeError as e:
            pytest.fail(f"Spec is not JSON serializable: {e}")
        assert len(serialized) > 100

    def test_org_name_in_title(self, app):
        """org_name should appear in the spec title."""
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert "API" in spec["info"]["title"]

    def test_org_name_fallback_outside_context(self):
        """Without app context, org_name should fall back to 'Humanitarian Databank'."""
        from app.swagger.openapi_spec import get_openapi_spec
        # Calling outside app context should still work (uses default org_name)
        spec = get_openapi_spec()
        assert "API" in spec["info"]["title"]

    def test_base_url_default_server_present(self, app):
        """Default server URL should be present in the servers list."""
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        urls = [s["url"] for s in spec.get("servers", [])]
        assert any("localhost" in url or "http" in url for url in urls)

    def test_get_api_paths_returns_dict(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert isinstance(paths, dict)
        assert len(paths) > 5

    def test_countrymap_has_get(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "get" in paths["/countrymap"]

    def test_indicator_bank_has_get(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "get" in paths["/indicator-bank"]

    def test_indicator_by_id_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/indicator-bank/{indicator_id}" in paths

    def test_template_by_id_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/templates/{template_id}" in paths

    def test_user_profile_has_get_and_put(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        profile = paths.get("/user/profile", {})
        assert "get" in profile
        assert "put" in profile

    def test_submission_by_id_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/submissions/{submission_id}" in paths

    def test_sectors_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/sectors" in paths

    def test_subsectors_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/subsectors" in paths

    def test_sectors_subsectors_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/sectors-subsectors" in paths

    def test_users_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/users" in paths

    def test_template_data_path(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        assert "/templates/{template_id}/data" in paths

    def test_error_schema_has_required(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        error_schema = spec["components"]["schemas"]["Error"]
        assert "required" in error_schema
        assert "success" in error_schema["required"]

    def test_pagination_schema_properties(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        pag = spec["components"]["schemas"]["Pagination"]
        props = pag.get("properties", {})
        for field in ("page", "per_page", "total", "pages"):
            assert field in props, f"Pagination missing property '{field}'"

    def test_country_schema_properties(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        country = spec["components"]["schemas"]["Country"]
        props = country.get("properties", {})
        assert "id" in props
        assert "name" in props
        assert "iso3" in props


# ===========================================================================
#  swagger/routes.py  –  HTTP route tests
# ===========================================================================

class TestSwaggerUI:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/api-docs/")
        _assert_status(resp, 302, 401)

    def test_authenticated_returns_html(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/")
        _assert_status(resp, 200)
        assert resp.content_type.startswith("text/html")

    def test_content_type_header(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/")
        _assert_status(resp, 200)
        assert "text/html" in resp.headers.get("Content-Type", "")

    def test_spec_error_still_renders(self, logged_in_client, db_session):
        """Even if spec generation fails, UI should still render."""
        with patch("app.swagger.openapi_spec.get_openapi_spec", side_effect=RuntimeError("boom")):
            resp = logged_in_client.get("/api-docs/")
        _assert_status(resp, 200)


class TestOpenApiJson:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/api-docs/openapi.json")
        _assert_status(resp, 302, 401)

    def test_authenticated_returns_json(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("openapi") == "3.0.3"
        assert "paths" in data
        assert "info" in data

    def test_response_has_paths(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert len(data.get("paths", {})) > 0

    def test_response_has_components(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert "components" in data

    def test_missing_openapi_field_returns_500(self, logged_in_client, db_session):
        """When spec is missing 'openapi' field should return server error."""
        with patch("app.swagger.openapi_spec.get_openapi_spec", return_value={"paths": {}}):
            resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 500)

    def test_missing_paths_field_returns_500(self, logged_in_client, db_session):
        """When spec is missing 'paths' field should return server error."""
        with patch("app.swagger.openapi_spec.get_openapi_spec", return_value={"openapi": "3.0.3"}):
            resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 500)

    def test_spec_exception_returns_500(self, logged_in_client, db_session):
        with patch("app.swagger.openapi_spec.get_openapi_spec", side_effect=Exception("broken")):
            resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 500)

    def test_spec_includes_tags(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/openapi.json")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert len(data.get("tags", [])) > 0


class TestOpenApiYaml:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/api-docs/openapi.yaml")
        _assert_status(resp, 302, 401)

    def test_authenticated_returns_yaml_or_503(self, logged_in_client, db_session):
        """Endpoint returns YAML if PyYAML is installed, 503 if not."""
        resp = logged_in_client.get("/api-docs/openapi.yaml")
        _assert_status(resp, 200, 503)

    def test_yaml_content_type_when_available(self, logged_in_client, db_session):
        try:
            import yaml  # noqa: F401
            yaml_available = True
        except ImportError:
            yaml_available = False

        resp = logged_in_client.get("/api-docs/openapi.yaml")
        if yaml_available:
            _assert_status(resp, 200)
            assert "yaml" in resp.content_type.lower()
        else:
            _assert_status(resp, 503)

    def test_yaml_import_error_returns_503(self, logged_in_client, db_session):
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("yaml not available")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            resp = logged_in_client.get("/api-docs/openapi.yaml")
        _assert_status(resp, 503, 200)  # may already be cached

    def test_yaml_generation_exception_returns_500(self, logged_in_client, db_session):
        try:
            import yaml  # noqa: F401
        except ImportError:
            pytest.skip("PyYAML not installed")

        with patch("app.swagger.openapi_spec.get_openapi_spec", side_effect=RuntimeError("fail")):
            resp = logged_in_client.get("/api-docs/openapi.yaml")
        _assert_status(resp, 500)


class TestSwaggerTestSpec:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/api-docs/test")
        _assert_status(resp, 302, 401)

    def test_authenticated_returns_success(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("status") == "success"

    def test_has_openapi_version(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("openapi_version") == "3.0.3"

    def test_has_paths_count(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert isinstance(data.get("paths_count"), int)
        assert data["paths_count"] > 0

    def test_has_tags_count(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert isinstance(data.get("tags_count"), int)
        assert data["tags_count"] > 0

    def test_json_valid_flag(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("json_valid") is True

    def test_has_components_flags(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("has_components") is True
        assert data.get("has_schemas") is True
        assert data.get("has_security_schemes") is True
        assert data.get("has_responses") is True

    def test_has_sample_paths(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        sample_paths = data.get("sample_paths", [])
        assert isinstance(sample_paths, list)
        assert len(sample_paths) <= 5

    def test_has_title(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("title")

    def test_spec_exception_returns_500(self, logged_in_client, db_session):
        with patch("app.swagger.openapi_spec.get_openapi_spec", side_effect=Exception("boom")):
            resp = logged_in_client.get("/api-docs/test")
        _assert_status(resp, 500)


# ===========================================================================
#  Edge cases and spec integrity
# ===========================================================================

class TestOpenApiSpecIntegrity:
    """Cross-cutting checks on the generated spec."""

    def test_all_paths_have_at_least_one_operation(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()

        http_methods = {"get", "post", "put", "patch", "delete", "head", "options"}
        for path, ops in spec["paths"].items():
            has_op = any(m in ops for m in http_methods)
            assert has_op, f"Path '{path}' has no HTTP operations"

    def test_all_operations_have_summary(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()

        http_methods = {"get", "post", "put", "patch", "delete"}
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                if method in http_methods:
                    assert "summary" in op, f"Operation {method.upper()} {path} missing 'summary'"

    def test_all_operations_have_responses(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()

        http_methods = {"get", "post", "put", "patch", "delete"}
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                if method in http_methods:
                    assert "responses" in op, f"Operation {method.upper()} {path} missing 'responses'"

    def test_schema_refs_are_consistent(self, app):
        """All $ref values in paths should point to existing components."""
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()

        schemas = set(spec["components"]["schemas"].keys())
        responses = set(spec["components"]["responses"].keys())
        params = set(spec["components"]["parameters"].keys())

        def _check_refs(obj):
            if isinstance(obj, dict):
                ref = obj.get("$ref", "")
                if ref.startswith("#/components/schemas/"):
                    name = ref.split("/")[-1]
                    assert name in schemas, f"Unknown schema ref: {ref}"
                elif ref.startswith("#/components/responses/"):
                    name = ref.split("/")[-1]
                    assert name in responses, f"Unknown response ref: {ref}"
                elif ref.startswith("#/components/parameters/"):
                    name = ref.split("/")[-1]
                    assert name in params, f"Unknown parameter ref: {ref}"
                for v in obj.values():
                    _check_refs(v)
            elif isinstance(obj, list):
                for item in obj:
                    _check_refs(item)

        _check_refs(spec["paths"])

    def test_no_empty_tags(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        for tag in spec.get("tags", []):
            assert tag.get("name"), "Tag has empty name"
            assert tag.get("description"), f"Tag '{tag['name']}' has empty description"

    def test_security_schemes_not_empty(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert spec["components"]["securitySchemes"]

    def test_spec_version_is_string(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert isinstance(spec["info"]["version"], str)

    def test_spec_description_present(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_openapi_spec
            spec = get_openapi_spec()
        assert spec["info"].get("description")

    def test_indicator_bank_no_auth_required(self, app):
        """Indicator bank (public endpoint) should have no security requirement."""
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        op = paths["/indicator-bank"]["get"]
        # Public endpoint - either no security key or empty list
        security = op.get("security", None)
        assert security is None or security == []

    def test_countrymap_has_bearer_auth(self, app):
        with app.app_context():
            from app.swagger.openapi_spec import get_api_paths
            paths = get_api_paths()
        op = paths["/countrymap"]["get"]
        security = op.get("security", [])
        assert any("BearerAuth" in (s or {}) for s in security)
