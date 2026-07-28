"""Tests for app/routes/forms/__init__.py – covers the get_frontend_url_global template global.

The module-level import side-effects (register_*_routes calls) are exercised
implicitly by importing the package inside an app context; we only need explicit
unit tests for the four uncovered lines in get_frontend_url_global.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_global(app):
    """Call get_frontend_url_global() inside an app context and return the result."""
    with app.app_context():
        from app.routes.forms import bp
        # The function is registered as an app_template_global; retrieve it.
        fn = bp.app_template_globals.get("get_frontend_url_global")
        assert fn is not None, "get_frontend_url_global template global not found on blueprint"
        return fn()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetFrontendUrlGlobal:
    """Cover all branches of get_frontend_url_global()."""

    def test_returns_url_when_service_returns_value(self, app):
        """Happy path: service returns a non-None URL string."""
        with app.app_context():
            with patch(
                "app.routes.forms.get_frontend_url_global.__wrapped__"
                if False else "app.services.platform.app_settings_service.get_frontend_url",
                return_value="https://example.com",
                create=True,
            ):
                from app.routes.forms import bp

                fn = bp.app_template_globals.get("get_frontend_url_global")
                assert fn is not None

                with patch(
                    "app.routes.forms.__init__" if False else "app.services.platform.app_settings_service",
                    create=True,
                ):
                    # Patch get_frontend_url inside the closure's import
                    with patch(
                        "app.services.platform.app_settings_service.get_frontend_url",
                        return_value="https://frontend.example.com",
                    ):
                        result = fn()
                assert result == "https://frontend.example.com"

    def test_returns_hash_when_service_returns_none(self, app):
        """When get_frontend_url() returns None, the function should return '#'."""
        with app.app_context():
            from app.routes.forms import bp

            fn = bp.app_template_globals.get("get_frontend_url_global")
            assert fn is not None

            with patch(
                "app.services.platform.app_settings_service.get_frontend_url",
                return_value=None,
            ):
                result = fn()
        assert result == "#"

    def test_returns_hash_when_service_raises_exception(self, app):
        """When get_frontend_url() raises, the except branch should return '#'."""
        with app.app_context():
            from app.routes.forms import bp

            fn = bp.app_template_globals.get("get_frontend_url_global")
            assert fn is not None

            with patch(
                "app.services.platform.app_settings_service.get_frontend_url",
                side_effect=RuntimeError("service unavailable"),
            ):
                result = fn()
        assert result == "#"

    def test_returns_hash_when_import_fails(self, app):
        """When the import inside the function raises ImportError, return '#'."""
        import builtins
        original_import = builtins.__import__

        def _broken_import(name, *args, **kwargs):
            if "app_settings_service" in name:
                raise ImportError("mocked import failure")
            return original_import(name, *args, **kwargs)

        with app.app_context():
            from app.routes.forms import bp

            fn = bp.app_template_globals.get("get_frontend_url_global")
            assert fn is not None

            with patch("builtins.__import__", side_effect=_broken_import):
                result = fn()
        assert result == "#"

    def test_blueprint_is_registered_with_correct_prefix(self, app):
        """The forms blueprint should be registered under /forms."""
        from app.routes.forms import bp
        assert bp.url_prefix == "/forms"

    def test_package_re_exports_helper_functions(self, app):
        """Key helpers are re-exported from the forms package."""
        with app.app_context():
            import app.routes.forms as forms_pkg
            assert hasattr(forms_pkg, "calculate_section_completion_status")
            assert hasattr(forms_pkg, "debug_numeric_value")
            assert hasattr(forms_pkg, "map_unified_item_to_original")
            assert hasattr(forms_pkg, "process_existing_data_for_template")
            assert hasattr(forms_pkg, "process_numeric_value")

    def test_package_re_exports_entry_functions(self, app):
        """Entry route helpers are re-exported from the forms package."""
        with app.app_context():
            import app.routes.forms as forms_pkg
            assert hasattr(forms_pkg, "handle_assignment_form")
            assert hasattr(forms_pkg, "preview_template")

    def test_package_re_exports_submission_functions(self, app):
        """Submission route helpers are re-exported from the forms package."""
        with app.app_context():
            import app.routes.forms as forms_pkg
            assert hasattr(forms_pkg, "handle_public_submission_form")
