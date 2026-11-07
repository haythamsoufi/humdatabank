"""Every plugin route either carries an auth decorator or is listed here on purpose.

A new route without a recognised guard fails this test until a reviewer adds it to
``INTENTIONALLY_UNGUARDED`` with a reason, so public exposure is always a conscious call.
"""
import ast
import re
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parents[3] / "plugins"

_ROUTE_DECORATOR = re.compile(r"\.(route|get|post|put|patch|delete)\(")
_GUARD = re.compile(
    r"(login_required|permission_required|system_manager_required|require_api_key|"
    r"api_view|plugin_admin_route_wrapper|plugin_route_wrapper|admin_required)"
)

INTENTIONALLY_UNGUARDED = {
    # Public by design (rate-limited): legacy FDRS-compatible CSV export.
    ("fdrs/public_compat_routes.py", "fdrs_public_compat_csv_export"),
    ("fdrs/public_compat_routes.py", "fdrs_public_compat_csv_export_ns"),
    # Static assets of the plugin (also gated on plugin activation by the manager).
    ("ifrc/decisions/routes.py", "static_file"),
    ("ifrc/routes.py", "static_file"),
    ("upr/routes.py", "static_file"),
    # Guarded in the body by ``_page_guard()`` (redirects/denies per Decision Maker access).
    ("ifrc/decisions/routes.py", "page_catalogue"),
    ("ifrc/decisions/routes.py", "page_workspace"),
    ("ifrc/decisions/routes.py", "page_country"),
    ("ifrc/decisions/routes.py", "page_region"),
    ("ifrc/decisions/routes.py", "page_evidence"),
    # Public embeds / public data for the website (rate-limited, read-only).
    ("ifrc/routes.py", "ppp_dashboard"),
    ("ifrc/routes.py", "ppp_detail_redirect"),
    ("ifrc/routes.py", "ppp_data"),
    ("upr/routes.py", "support_flow_embed"),
    ("upr/routes.py", "support_funding_embed"),
    ("upr/routes.py", "support_coverage_embed"),
    ("upr/routes.py", "support_overview_embed"),
    ("upr/routes.py", "support_flow_data"),
    ("upr/routes.py", "support_flow_tile"),
    ("upr/documents_gallery.py", "upr_documents_gallery"),
    ("upr/upr_data_routes.py", "get_ns_key_data"),
    # Answers an empty object for anonymous users, link only for permitted users.
    ("nsd_report_forms/routes_pm.py", "links"),
}


def _unguarded_routes():
    found = set()
    for path in PLUGINS_DIR.rglob("*.py"):
        rel = path.relative_to(PLUGINS_DIR).as_posix()
        if "/tests/" in f"/{rel}" or path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            if not any(_ROUTE_DECORATOR.search(d) for d in decorators):
                continue
            guards = [d for d in decorators if not _ROUTE_DECORATOR.search(d)]
            if not any(_GUARD.search(d) for d in guards):
                found.add((rel, node.name))
    return found


@pytest.mark.unit
def test_plugin_routes_without_a_guard_are_all_acknowledged():
    unacknowledged = sorted(_unguarded_routes() - INTENTIONALLY_UNGUARDED)
    assert not unacknowledged, (
        "Plugin routes without an auth decorator. Guard them or add them to "
        f"INTENTIONALLY_UNGUARDED with a reason: {unacknowledged}"
    )


@pytest.mark.unit
def test_allowlist_has_no_stale_entries():
    stale = sorted(INTENTIONALLY_UNGUARDED - _unguarded_routes())
    assert not stale, f"Remove entries that are now guarded or deleted: {stale}"
