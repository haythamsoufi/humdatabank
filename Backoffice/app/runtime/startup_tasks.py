"""Deferred startup tasks and RBAC route guard audit."""

import os
import threading
import time as _time

from app.extensions import db


def deferred_startup_cleanup(app):
    """Defer session cleanup to avoid blocking startup."""

    def cleanup_task():
        try:
            with app.app_context():
                with db.engine.connect() as conn:
                    conn.execute(db.text('SELECT 1'))

                from app.services.platform.user_analytics_service import cleanup_inactive_sessions

                cleanup_count = cleanup_inactive_sessions()
                if cleanup_count > 0:
                    app.logger.info(
                        "Startup cleanup: ended %s stale sessions from previous runs",
                        cleanup_count,
                    )
        except Exception as e:
            app.logger.warning(
                "Skipping startup session cleanup - database not ready: %s", str(e)
            )

    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    app.logger.debug("Startup session cleanup deferred to background thread")


def deferred_rbac_seed(app, selected_config_name, is_reloader):
    """Defer RBAC seeding to avoid blocking startup."""
    auto_seed_env = os.environ.get("AUTO_SEED_RBAC_ON_STARTUP")
    if auto_seed_env is not None and str(auto_seed_env).strip() != "":
        auto_seed = str(auto_seed_env).strip().lower() == "true"
    else:
        # Default to always seeding (idempotent, deferred to a background thread) so
        # RBAC role/permission definitions can't silently drift out of sync with the
        # code in any environment -- including local dev, where nobody automatically
        # runs `flask rbac seed` after pulling changes that add/rename roles. A stale
        # dev DB missing newer roles (e.g. assignment_* roles) previously surfaced as
        # confusing, incomplete-looking role checkboxes in the user management UI.
        auto_seed = True

    if not auto_seed:
        return

    if app.config.get("TESTING", False):
        return

    if os.environ.get("RUNNING_MIGRATION"):
        return

    # NOTE: `flask rbac seed` used to race this background thread for the advisory
    # lock. That's now solved at the lock layer (rbac_seed_service uses a bounded
    # blocking wait for CLI/entrypoint-triggered seeding instead of a non-blocking
    # try), not by disabling this thread -- `FLASK_RUN_FROM_CLI` is set by Flask for
    # *every* `flask` subcommand, including plain `flask run`, so bailing out here
    # on that env var previously also disabled local-dev auto-seed entirely.

    if app.debug and not is_reloader:
        return

    def seed_task():
        try:
            with app.app_context():
                last_err = None
                for attempt in range(1, 6):
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(db.text("SELECT 1"))
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < 6:
                            _time.sleep(min(2**attempt, 15))
                if last_err is not None:
                    raise last_err

                from app.services.organization.rbac_seed_service import (
                    RbacSeedLockMode,
                    seed_rbac_permissions_and_roles,
                )

                # TRY (non-blocking): a background boot-time thread must never block
                # worker startup waiting on another process's lock. Losing the race to
                # a sibling worker seeding the same catalog is harmless.
                stats = seed_rbac_permissions_and_roles(lock_mode=RbacSeedLockMode.TRY)
                if stats.get("skipped_due_to_lock"):
                    app.logger.info("RBAC auto-seed skipped (another worker is seeding).")
                else:
                    app.logger.info(
                        "RBAC auto-seed complete "
                        "(permissions: +%s/%s updated, "
                        "roles: +%s/%s updated, "
                        "links: +%s / -%s)",
                        stats.get('created_permissions', 0),
                        stats.get('updated_permissions', 0),
                        stats.get('created_roles', 0),
                        stats.get('updated_roles', 0),
                        stats.get('created_role_permission_links', 0),
                        stats.get('deleted_role_permission_links', 0),
                    )
        except Exception as e:
            app.logger.warning("Skipping RBAC auto-seed - database not ready: %s", str(e))

    seed_thread = threading.Thread(target=seed_task, daemon=True)
    seed_thread.start()
    app.logger.info("RBAC auto-seed deferred to background thread")


_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _view_guard_metadata(view):
    permissions = list(getattr(view, "_rbac_permissions_required", None) or [])
    permissions_any = list(getattr(view, "_rbac_permissions_any_required", None) or [])
    return {
        "admin_required": bool(getattr(view, "_rbac_admin_required", False)),
        "system_manager": bool(getattr(view, "_rbac_system_manager_required", False)),
        "permissions": permissions,
        "permissions_any": permissions_any,
        "exempt": bool(getattr(view, "_rbac_guard_audit_exempt", False)),
    }


def collect_admin_route_guard_findings(app):
    """
    Static check of guard decorators on /admin routes (and other privileged prefixes).

    Returns a list of ``{"kind", "path", "endpoint", "detail"}`` dicts. Kinds:

    * ``missing_guard`` - no RBAC decorator at all.
    * ``non_admin_permission`` - guarded only by a non-``admin.*`` permission (no admin gate).
    * ``read_permission_on_mutating_route`` - POST/PUT/PATCH/DELETE guarded only by ``*.view``.
    * ``policy_system_manager`` / ``policy_post_only`` / ``policy_required_permission`` -
      violations of ``app.routes.admin.route_policy``.
    * ``get_side_effect_name`` - view named like a side effect that still accepts GET.
    * ``csrf_exempt_mutation`` - CSRF-exempt mutating route not in the reviewed allowlist.
    """
    from app.routes.admin import route_policy as policy

    findings = []
    csrf_exempt_names = set()
    try:
        from app.extensions import csrf

        csrf_exempt_names = set(getattr(csrf, "_exempt_views", set()) or set())
    except Exception:
        csrf_exempt_names = set()

    prefixes = ("/admin",) + tuple(policy.EXTRA_AUDITED_PATH_PREFIXES)
    for rule in app.url_map.iter_rules():
        try:
            path = str(rule.rule or "")
            if not path.startswith(prefixes):
                continue
            endpoint = str(rule.endpoint or "")
            view = app.view_functions.get(endpoint)
            if view is None:
                continue
            meta = _view_guard_metadata(view)
            methods = set(rule.methods or ()) - {"HEAD", "OPTIONS"}
            mutating = bool(methods & _MUTATING_METHODS)

            def _add(kind, detail=""):
                findings.append({"kind": kind, "path": path, "endpoint": endpoint, "detail": detail})

            if endpoint in policy.SYSTEM_MANAGER_ONLY_ENDPOINTS and not meta["system_manager"]:
                _add("policy_system_manager", "endpoint must be System Manager only")
            if endpoint in policy.POST_ONLY_ENDPOINTS and (methods - {"POST"}):
                _add("policy_post_only", f"accepts {sorted(methods - {'POST'})}")
            required_permission = policy.REQUIRED_PERMISSION_BY_ENDPOINT.get(endpoint)
            if required_permission and required_permission not in (
                meta["permissions"] + meta["permissions_any"]
            ):
                _add("policy_required_permission", f"requires {required_permission}")

            if meta["exempt"]:
                continue

            permissions = meta["permissions"] + meta["permissions_any"]
            protected = bool(meta["admin_required"] or meta["system_manager"] or permissions)
            if not protected:
                if path.startswith(policy.LOGIN_ONLY_READ_PATH_PREFIXES) and (
                    not mutating or endpoint in policy.LOGIN_ONLY_POST_ALLOWLIST
                ):
                    continue
                _add("missing_guard")
                continue

            if permissions and not (meta["admin_required"] or meta["system_manager"]):
                non_admin = [
                    p for p in permissions
                    if not p.startswith(policy.ADMIN_PERMISSION_PREFIX)
                    and not p.startswith(policy.NON_ADMIN_PERMISSION_ALLOWLIST_PREFIXES)
                ]
                if non_admin:
                    _add("non_admin_permission", ", ".join(sorted(non_admin)))

            if (
                mutating
                and permissions
                and not meta["system_manager"]
                and endpoint not in policy.READ_ONLY_POST_ALLOWLIST
                and all(p.endswith(".view") for p in permissions)
            ):
                _add("read_permission_on_mutating_route", ", ".join(sorted(permissions)))

            view_name = getattr(view, "__name__", "")
            if (
                methods == {"GET"}
                and view_name.startswith(policy.SIDE_EFFECT_VIEW_PREFIXES)
                and endpoint not in policy.GET_SIDE_EFFECT_NAME_ALLOWLIST
            ):
                _add("get_side_effect_name", view_name)

            if (
                mutating
                and f"{getattr(view, '__module__', '')}.{view_name}" in csrf_exempt_names
                and endpoint not in policy.CSRF_EXEMPT_MUTATION_ALLOWLIST
            ):
                _add("csrf_exempt_mutation")
        except Exception as e:
            app.logger.debug("RBAC audit: skip rule %s: %s", getattr(rule, "rule", ""), e)
    return findings


def audit_admin_route_guards(app):
    """
    Lightweight static check that /admin routes have RBAC guard decorators and follow route_policy.

    ``RBAC_ADMIN_ROUTE_GUARD_MODE=error`` raises instead of logging a warning.
    """
    mode = os.environ.get("RBAC_ADMIN_ROUTE_GUARD_MODE", "").strip().lower() or "warn"
    if mode in {"off", "disabled", "0", "false", "no"}:
        return

    try:
        findings = collect_admin_route_guard_findings(app)
    except Exception as e:
        app.logger.debug("RBAC admin-route audit skipped/failed: %s", e)
        return
    if not findings:
        return

    missing = [f for f in findings if f["kind"] == "missing_guard"]
    other = [f for f in findings if f["kind"] != "missing_guard"]
    messages = []
    if missing:
        details = "; ".join(f"{f['path']} -> {f['endpoint']}" for f in missing[:50])
        messages.append(
            f"RBAC: detected {len(missing)} /admin route(s) without an RBAC guard decorator. "
            f"These routes may be unintentionally exposed. Examples: {details}"
        )
    if other:
        details = "; ".join(f"[{f['kind']}] {f['path']} -> {f['endpoint']} {f['detail']}".strip() for f in other[:50])
        messages.append(f"RBAC: {len(other)} route guard policy finding(s). Examples: {details}")
    msg = " | ".join(messages)
    if mode in {"error", "strict", "raise"}:
        raise RuntimeError(msg)
    app.logger.warning(msg)


def run_startup_tasks(app, selected_config_name, is_reloader):
    """Run deferred cleanup and RBAC seeding after blueprints are registered."""
    try:
        deferred_startup_cleanup(app)
    except Exception as e:
        app.logger.warning("Could not defer startup cleanup: %s", str(e))

    try:
        deferred_rbac_seed(app, selected_config_name, is_reloader)
    except Exception as e:
        app.logger.warning("Could not defer RBAC auto-seed: %s", str(e))
