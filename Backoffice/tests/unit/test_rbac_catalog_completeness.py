"""
RBAC permission catalog completeness guard.

RBAC review finding: nothing verified that every permission code referenced
by a route decorator (`@permission_required`, `@permission_required_any`,
`@admin_permission_required[_any]`, `@mobile_auth_required(permission=...)`)
or by a baseline/plugin role's `permission_codes` list actually exists in the
seed catalog (`_permission_catalog()` in rbac_seed_service.py, plus whatever
plugins contribute via `get_seed_permissions()`).

Why this matters: `seed_rbac_permissions_and_roles()` upserts `RbacPermission`
rows *only* for codes present in that catalog, and every non-System-Manager
role can only ever be granted permissions that exist in that catalog (see
`_baseline_roles()` -- `system_manager`'s `permission_codes` is literally
`[code for code, _, _ in permission_catalog]`, not "every code anyone
references"). A typo'd or renamed code in a decorator, or in a role's
`permission_codes` list, is invisible at review time and at `flask rbac seed`
time (it just never creates/links that code -- see `desired_perm_ids` in
`seed_rbac_permissions_and_roles()`, which silently drops any code not found
in `perms_by_code`). The practical effect: a route guarded by a permission
that no *non-System-Manager* role can ever hold (System Manager bypasses the
permission lookup entirely via `AuthorizationService.has_rbac_permission()`'s
superuser shortcut, so it alone would still get in), or a role that looks
like it grants N permissions in code but is actually missing one after every
seed run.

This test walks every registered view function (core admin routes, mobile
API routes, and plugin blueprint routes alike) for the RBAC metadata each of
those decorators attaches, plus every baseline/plugin role definition, and
asserts every referenced permission code is present in the combined core +
plugin seed catalog. It also guards the catalog/role data itself against
duplicate codes, which the seeder's list-based (not dict-based) catalog
would otherwise let shadow each other silently.
"""

from __future__ import annotations

from app.services.organization.rbac_seed_service import (
    _baseline_roles,
    _extension_baseline_roles,
    _extension_permission_catalog,
    _permission_catalog,
)

# Attributes set by app/routes/admin/shared.py's permission_required /
# permission_required_any (directly, or via the admin_permission_required[_any]
# combo decorators) on the decorated view function.
_DECORATOR_LIST_ATTRS = ("_rbac_permissions_required", "_rbac_permissions_any_required")

# Attribute set by app/utils/mobile_auth.py's mobile_auth_required(permission=...,
# permissions=(...)) on the decorated view function.
_MOBILE_LIST_ATTRS = ("_ep_permissions",)


def _decorator_referenced_permission_codes(flask_app) -> dict[str, set[str]]:
    """
    Return {permission_code: {endpoint, ...}} for every RBAC permission code
    referenced by a route decorator's metadata, across every registered view
    function -- core admin HTML routes, mobile API routes, and plugin routes
    alike (they all share the same `app.view_functions` registry).
    """
    codes: dict[str, set[str]] = {}

    def _record(code, endpoint):
        if isinstance(code, str) and code.strip() and "." in code:
            codes.setdefault(code.strip(), set()).add(endpoint)

    for endpoint, view in flask_app.view_functions.items():
        for attr in _DECORATOR_LIST_ATTRS + _MOBILE_LIST_ATTRS:
            for code in getattr(view, attr, None) or ():
                _record(code, endpoint)

    return codes


def _full_catalog(app):
    with app.app_context():
        core_permissions = _permission_catalog()
        extension_permissions = _extension_permission_catalog()
        baseline_roles = _baseline_roles(core_permissions + extension_permissions)
        extension_roles = _extension_baseline_roles()
    return core_permissions, extension_permissions, baseline_roles, extension_roles


class TestRbacDecoratorPermissionCodesExistInCatalog:
    def test_every_decorator_permission_code_exists_in_seed_catalog(self, app):
        core_permissions, extension_permissions, _, _ = _full_catalog(app)
        catalog_codes = {code for code, _, _ in core_permissions} | {
            code for code, _, _ in extension_permissions
        }

        with app.app_context():
            referenced = _decorator_referenced_permission_codes(app)

        missing = {
            code: endpoints for code, endpoints in referenced.items() if code not in catalog_codes
        }

        assert not missing, (
            "The following RBAC permission code(s) are referenced by a route "
            "decorator but are missing from the seed catalog "
            "(_permission_catalog() / a plugin's get_seed_permissions()). A "
            "route guarded by a permission that no *non-System-Manager* role "
            "can ever be granted is inaccessible to everyone except System "
            "Manager (who bypasses the permission lookup entirely via "
            "AuthorizationService.has_rbac_permission()'s superuser "
            "shortcut). Add the missing code to the catalog, or fix the "
            "typo/rename in the decorator:\n  "
            + "\n  ".join(
                f"{code!r} -> {', '.join(sorted(endpoints))}"
                for code, endpoints in sorted(missing.items())
            )
        )


class TestRbacBaselineRolePermissionCodesExistInCatalog:
    def test_every_baseline_role_permission_code_exists_in_catalog(self, app):
        core_permissions, extension_permissions, baseline_roles, extension_roles = _full_catalog(app)
        catalog_codes = {code for code, _, _ in core_permissions} | {
            code for code, _, _ in extension_permissions
        }

        missing: dict[str, set[str]] = {}
        for role in baseline_roles + extension_roles:
            role_code = str(role.get("code") or "<unnamed role>")
            for code in role.get("permission_codes") or []:
                if code not in catalog_codes:
                    missing.setdefault(role_code, set()).add(code)

        assert not missing, (
            "The following baseline/plugin role(s) list permission code(s) "
            "not present in the seed catalog. "
            "seed_rbac_permissions_and_roles() silently drops any code it "
            "can't resolve (see `desired_perm_ids` / `perms_by_code`), so "
            "the role ends up with fewer permissions than its "
            "permission_codes list implies -- fix the typo/rename, or add "
            "the missing permission to the catalog:\n  "
            + "\n  ".join(
                f"{role_code!r} -> {sorted(codes)}" for role_code, codes in sorted(missing.items())
            )
        )


class TestRbacCatalogHasNoDuplicateCodes:
    """
    _permission_catalog()/_extension_permission_catalog() are plain Python
    lists of (code, name, description) tuples, not a dict keyed by code -- a
    copy-pasted tuple reusing an existing code doesn't raise anything; it
    silently rides along until seed_rbac_permissions_and_roles()'s
    upsert-by-code loop applies whichever entry happens to be seen last,
    hiding one of the two intended descriptions with no error either time.
    """

    def test_permission_catalog_codes_are_unique(self, app):
        core_permissions, extension_permissions, _, _ = _full_catalog(app)
        all_codes = [code for code, _, _ in core_permissions] + [
            code for code, _, _ in extension_permissions
        ]

        seen: set[str] = set()
        dupes: set[str] = set()
        for code in all_codes:
            if code in seen:
                dupes.add(code)
            seen.add(code)

        assert not dupes, (
            f"Duplicate permission code(s) in the seed catalog: {sorted(dupes)}. "
            "Each entry must have a unique code across core + all plugins."
        )

    def test_baseline_role_codes_are_unique(self, app):
        """
        Core and plugin role codes upsert into the same `rbac_role` table by
        `code` (see `existing_roles` in seed_rbac_permissions_and_roles()). A
        plugin accidentally reusing a core role code (or another plugin's)
        wouldn't fail to seed -- it would silently overwrite that role's
        permission links on every seed run, since permission-linking for
        baseline roles iterates the role-definition list, not the DB rows.
        """
        _, _, baseline_roles, extension_roles = _full_catalog(app)
        all_codes = [
            str(r.get("code")) for r in baseline_roles + extension_roles if r.get("code")
        ]

        seen: set[str] = set()
        dupes: set[str] = set()
        for code in all_codes:
            if code in seen:
                dupes.add(code)
            seen.add(code)

        assert not dupes, (
            f"Duplicate role code(s) across core + plugin baseline roles: {sorted(dupes)}. "
            "A plugin's get_seed_roles() must not reuse a core or another "
            "plugin's role code."
        )
