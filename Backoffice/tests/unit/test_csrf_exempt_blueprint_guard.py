"""
Systemic guard for CSRF-exempt blueprints.

CSRF review finding ("No blueprint-wide test enforces CSRF checks on every
mutating route in exempt blueprints"): api_v2/api/mobile_api/ai_v2/swagger are
wholesale ``csrf.exempt()``'d, and individual mutating views are expected to
enforce protection manually (enforce_csrf_json(), mobile_auth_required,
require_api_key, etc.). The only prior automated check was two hand-picked
endpoint tests in tests/api/test_api_v1_csrf.py — nothing caught a *new*
mutating route shipping in one of these blueprints with no protection at all.

This test walks the live ``app.url_map`` for every unsafe-method (POST/PUT/
PATCH/DELETE) rule registered under a CSRF-exempt blueprint and asserts the
view's own source (decorators + body, found via inspect.getsource() which
follows functools.wraps `__wrapped__` chains) contains at least one known
enforcement marker. A route matching none of the markers must be added to
EXPLICITLY_ALLOWED_UNPROTECTED_ROUTES with a written justification — this is
a deliberate manual step, not a rubber stamp, so a reviewer has to actually
look at (and approve) any newly "exempt" route.

This is a coarse, source-text-based guard (it cannot verify the enforcement
call is reachable on every code path) — it complements, but does not
replace, endpoint-specific CSRF tests.
"""

import inspect

import pytest

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Flask blueprint *names* (not the Python variable names!) that are registered
# with csrf.exempt() in app/__init__.py / app/routes/__init__.py.
CSRF_EXEMPT_BLUEPRINT_NAMES = {
    "api",  # api_bp — app/__init__.py
    "swagger",  # swagger_bp — app/__init__.py
    "indicator_bank_compat",  # app/routes/__init__.py
    "mobile_api",  # mobile_bp (Blueprint name "mobile_api") — app/routes/__init__.py
    "ai_v2",  # ai_bp (Blueprint name "ai_v2") — app/routes/__init__.py
}

ENFORCEMENT_MARKERS = (
    "enforce_csrf_json",
    "enforce_api_or_csrf_protection",
    "mobile_auth_required",
    "require_api_key",
    "_enforce_ai_csrf",
    "csrf.protect",
    "validate_csrf",
)

# (blueprint_name, rule) -> justification. Only add an entry here with a real
# reason a route legitimately needs no CSRF/auth-token check (e.g. it is
# read-only despite the HTTP method, or it is itself the login/token-issuance
# endpoint that a CSRF/auth token cannot yet exist for).
EXPLICITLY_ALLOWED_UNPROTECTED_ROUTES = {}


def _iter_unsafe_exempt_rules(flask_app):
    for rule in flask_app.url_map.iter_rules():
        methods = (rule.methods or set()) & UNSAFE_METHODS
        if not methods:
            continue
        endpoint = rule.endpoint
        blueprint_name = endpoint.rsplit(".", 1)[0] if "." in endpoint else None
        if blueprint_name not in CSRF_EXEMPT_BLUEPRINT_NAMES:
            continue
        yield rule, blueprint_name, methods


def _view_source(flask_app, endpoint):
    view_func = flask_app.view_functions.get(endpoint)
    if view_func is None:
        return ""
    try:
        return inspect.getsource(view_func)
    except (OSError, TypeError):
        return ""


class TestCsrfExemptBlueprintGuard:
    def test_no_unprotected_mutation_routes_in_exempt_blueprints(self, app):
        unprotected = []
        with app.app_context():
            for rule, blueprint_name, methods in _iter_unsafe_exempt_rules(app):
                key = (blueprint_name, rule.rule)
                if key in EXPLICITLY_ALLOWED_UNPROTECTED_ROUTES:
                    continue
                source = _view_source(app, rule.endpoint)
                if not source:
                    unprotected.append(
                        f"{rule.endpoint} {sorted(methods)} {rule.rule} "
                        f"(could not introspect source — verify manually)"
                    )
                    continue
                if not any(marker in source for marker in ENFORCEMENT_MARKERS):
                    unprotected.append(f"{rule.endpoint} {sorted(methods)} {rule.rule}")

        assert not unprotected, (
            "The following mutation routes are registered under CSRF-exempt "
            "blueprints with no detected CSRF/auth enforcement marker "
            f"({', '.join(ENFORCEMENT_MARKERS)}) in their source. Add one of "
            "these calls, or add an explicit EXPLICITLY_ALLOWED_UNPROTECTED_ROUTES "
            "entry in this test file with a written justification:\n  "
            + "\n  ".join(unprotected)
        )

    def test_exempt_blueprint_names_still_match_registration(self, app):
        """
        Guard the guard: if a blueprint is renamed or a new one is exempted,
        CSRF_EXEMPT_BLUEPRINT_NAMES above must be updated too, or this test
        silently stops checking blueprints that actually need it.
        """
        registered_names = {bp_name for bp_name in app.blueprints.keys()}
        missing = CSRF_EXEMPT_BLUEPRINT_NAMES - registered_names
        assert not missing, (
            f"Expected CSRF-exempt blueprint(s) not found in app.blueprints: {missing}. "
            "Blueprint may have been renamed — update CSRF_EXEMPT_BLUEPRINT_NAMES."
        )
