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

                from app.services.user_analytics_service import cleanup_inactive_sessions

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

                from app.services.rbac_seed_service import seed_rbac_permissions_and_roles

                stats = seed_rbac_permissions_and_roles()
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


def audit_admin_route_guards(app):
    """
    Lightweight static check that /admin routes have RBAC guard decorators.
    """
    try:
        mode_raw = os.environ.get("RBAC_ADMIN_ROUTE_GUARD_MODE", "").strip().lower()
        mode = mode_raw or ("warn" if app.debug else "warn")
        if mode in {"off", "disabled", "0", "false", "no"}:
            return

        problems = []
        for rule in app.url_map.iter_rules():
            try:
                path = str(rule.rule or "")
                if not path.startswith("/admin"):
                    continue
                endpoint = str(rule.endpoint or "")
                view = app.view_functions.get(endpoint)
                if view is None:
                    continue
                if bool(getattr(view, "_rbac_guard_audit_exempt", False)):
                    continue

                protected = bool(
                    getattr(view, "_rbac_admin_required", False)
                    or getattr(view, "_rbac_system_manager_required", False)
                    or (getattr(view, "_rbac_permissions_required", None) not in (None, [], ()))
                    or (getattr(view, "_rbac_permissions_any_required", None) not in (None, [], ()))
                )
                if not protected:
                    problems.append((path, endpoint))
            except Exception as e:
                app.logger.debug("RBAC audit: skip rule %s: %s", getattr(rule, 'rule', ''), e)
                continue

        if not problems:
            return

        details = "; ".join([f"{p} -> {e}" for p, e in problems[:50]])
        msg = (
            f"RBAC: detected {len(problems)} /admin route(s) without an RBAC guard decorator. "
            f"These routes may be unintentionally exposed. Examples: {details}"
        )
        if mode in {"error", "strict", "raise"}:
            raise RuntimeError(msg)
        app.logger.warning(msg)
    except Exception as e:
        try:
            app.logger.debug("RBAC admin-route audit skipped/failed: %s", e)
        except Exception:
            pass


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
