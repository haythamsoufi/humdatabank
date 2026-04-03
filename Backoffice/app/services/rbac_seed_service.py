"""
RBAC seeding service.

Goal:
- Keep RBAC permissions/roles in sync with the application code.
- Be safe to run multiple times (idempotent).
- Be safe under multi-process deployments (uses PostgreSQL advisory lock).

This module is intentionally used by both:
- `flask rbac seed` (CLI command)
- production/staging app startup auto-seeding
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

from app.extensions import db
from app.models import User
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission, RbacUserRole
from app.utils.transactions import atomic


def _permission_catalog() -> List[Tuple[str, str, str]]:
    # Keep this list stable: permission codes are referenced across code and DB
    return [
        # Admin documentation / onboarding
        ("admin.docs.view", "View admin documentation", "Access admin documentation/onboarding pages"),

        # Users / User Management
        ("admin.users.view", "View users", "View users list and details"),
        ("admin.users.create", "Create users", "Create users"),
        ("admin.users.edit", "Edit users", "Edit users"),
        ("admin.users.deactivate", "Deactivate users", "Deactivate/reactivate users"),
        ("admin.users.delete", "Delete users", "Hard delete users"),
        ("admin.users.roles.assign", "Assign roles", "Assign/remove roles for users"),
        ("admin.users.grants.manage", "Manage access grants", "Manage scoped grants for users"),
        ("admin.users.devices.view", "View user devices", "View user devices"),
        ("admin.users.devices.kickout", "Kick out user devices", "End user device sessions"),
        ("admin.users.devices.remove", "Remove user devices", "Remove user devices from registry"),

        # Assignment management (admin screens)
        ("admin.assignments.view", "View assignments (admin)", "View assignments management screens"),
        ("admin.assignments.create", "Create assignments (admin)", "Create assignments"),
        ("admin.assignments.edit", "Edit assignments (admin)", "Edit assignment metadata and due dates"),
        ("admin.assignments.delete", "Delete assignments (admin)", "Delete assignments"),
        ("admin.assignments.entities.manage", "Manage assignment entities", "Add/remove entities and update entity status settings"),
        ("admin.assignments.public_submissions.manage", "Manage public submissions", "Manage public submissions"),

        # Assignment participation (AES-level)
        ("assignment.view", "View assignments", "View assignments (read-only)"),
        ("assignment.enter", "Enter assignment data", "Enter/edit assignment data when editable"),
        ("assignment.submit", "Submit assignment", "Submit assignment"),
        ("assignment.approve", "Approve assignment", "Approve submitted assignments"),
        ("assignment.reopen", "Reopen assignment", "Reopen submitted/approved assignments"),
        ("assignment.documents.upload", "Upload assignment documents", "Upload/replace assignment documents"),
        ("assignment.documents.delete", "Delete assignment documents", "Delete assignment documents"),

        # Templates
        ("admin.templates.view", "View templates", "View templates"),
        ("admin.templates.create", "Create templates", "Create templates"),
        ("admin.templates.edit", "Edit templates", "Edit templates (draft versions)"),
        ("admin.templates.delete", "Delete templates", "Delete templates"),
        ("admin.templates.duplicate", "Duplicate templates", "Duplicate templates"),
        ("admin.templates.publish", "Publish templates", "Publish templates"),
        ("admin.templates.share", "Share templates", "Share template access"),
        ("admin.templates.export_excel", "Export templates (Excel)", "Export template to Excel"),
        ("admin.templates.import_excel", "Import templates (Excel)", "Import template from Excel"),

        # Countries / organization
        ("admin.countries.view", "View countries", "View countries"),
        ("admin.countries.edit", "Edit countries", "Edit countries"),
        ("admin.organization.manage", "Manage organization", "Manage organization structure"),
        ("admin.access_requests.view", "View access requests", "View access requests"),
        ("admin.access_requests.approve", "Approve access requests", "Approve access requests"),
        ("admin.access_requests.reject", "Reject access requests", "Reject access requests"),

        # Indicator bank
        ("admin.indicator_bank.view", "View indicator bank", "View indicator bank"),
        ("admin.indicator_bank.create", "Create indicator entries", "Create indicator bank entries"),
        ("admin.indicator_bank.edit", "Edit indicator entries", "Edit indicator bank entries"),
        ("admin.indicator_bank.archive", "Archive indicator entries", "Archive indicator bank entries"),
        ("admin.indicator_bank.suggestions.review", "Review indicator suggestions", "Review indicator suggestions"),

        # Content
        ("admin.resources.manage", "Manage resources", "Manage resources"),
        ("admin.publications.manage", "Manage publications", "Manage publications"),
        ("admin.documents.manage", "Manage documents", "Manage documents"),
        ("admin.notifications.manage", "Manage notifications", "Manage admin notifications center (view/send)"),
        ("admin.translations.manage", "Manage translations", "Manage translation strings and compilation"),

        # Analytics / Audit / Security
        ("admin.analytics.view", "View analytics", "View analytics"),
        ("admin.audit.view", "View audit trail", "View audit trail"),
        ("admin.security.view", "View security dashboard", "View security dashboard"),
        ("admin.security.respond", "Respond to security events", "Resolve/respond to security events"),
        ("admin.ai.manage", "Manage AI", "Manage AI system (dashboard, documents, traces, processing)"),

        # System / API / plugins
        ("admin.settings.manage", "Manage settings", "Manage system settings"),
        ("admin.api.manage", "Manage API", "Manage API keys and API settings"),
        ("admin.plugins.manage", "Manage plugins", "Manage plugins"),
        # Data Explorer - granular permissions per tab
        ("admin.data_explore.data_table", "Data Explorer: Data Table", "Access the Data Table tab in Data Explorer"),
        ("admin.data_explore.analysis", "Data Explorer: Analysis", "Access the Analysis tab in Data Explorer"),
        ("admin.data_explore.compliance", "Data Explorer: Compliance", "Access the Compliance tab in Data Explorer"),
        # Governance
        ("admin.governance.view", "View governance dashboard", "Access the Governance dashboard (focal point coverage, access control, quality, compliance, metadata)"),
    ]


def _baseline_roles(permission_catalog: List[Tuple[str, str, str]]) -> List[Dict[str, Any]]:
    return [
        {
            "code": "system_manager",
            "name": "System Manager",
            "description": "Full access to all platform capabilities (superuser).",
            "permission_codes": [code for code, _, _ in permission_catalog],
        },
        {
            "code": "admin_core",
            "name": "Admin: Core (Essentials only)",
            "description": "Essential, mostly read-only access across key admin areas.",
            "permission_codes": [
                # Docs
                "admin.docs.view",
                # Users (view)
                "admin.users.view",
                # Templates (view)
                "admin.templates.view",
                # Assignments (admin screens - view)
                "admin.assignments.view",
                # Countries & Organization (view)
                "admin.countries.view",
                # Indicator bank (view)
                "admin.indicator_bank.view",
            ],
        },
        {
            "code": "admin_full",
            "name": "Admin: Full (All admin roles)",
            "description": "Full access to all admin modules (does not grant System Manager powers).",
            "permission_codes": [code for code, _, _ in permission_catalog if code.startswith("admin.")],
        },
        # ----------------------------------------------------------------
        # Granular admin module roles (recommended for most admins)
        # ----------------------------------------------------------------
        {
            "code": "admin_users_viewer",
            "name": "Admin: Users (View)",
            "description": "View users (list and details).",
            "permission_codes": ["admin.users.view"],
        },
        {
            "code": "admin_users_manager",
            "name": "Admin: Users (Manage)",
            "description": "Manage users (create/edit/deactivate/assign roles).",
            "permission_codes": [
                "admin.users.view",
                "admin.users.create",
                "admin.users.edit",
                "admin.users.deactivate",
                "admin.users.delete",
                "admin.users.roles.assign",
                "admin.users.grants.manage",
                "admin.users.devices.view",
                "admin.users.devices.kickout",
                "admin.users.devices.remove",
            ],
        },
        {
            "code": "admin_templates_viewer",
            "name": "Admin: Templates (View)",
            "description": "View templates.",
            "permission_codes": ["admin.templates.view"],
        },
        {
            "code": "admin_templates_manager",
            "name": "Admin: Templates (Manage)",
            "description": "Manage templates (create/edit/publish/share/import/export).",
            "permission_codes": [
                "admin.templates.view",
                "admin.templates.create",
                "admin.templates.edit",
                "admin.templates.delete",
                "admin.templates.duplicate",
                "admin.templates.publish",
                "admin.templates.share",
                "admin.templates.export_excel",
                "admin.templates.import_excel",
            ],
        },
        {
            "code": "admin_assignments_viewer",
            "name": "Admin: Assignments (View)",
            "description": "View assignments management screens (read-only).",
            "permission_codes": ["admin.assignments.view"],
        },
        {
            "code": "admin_assignments_manager",
            "name": "Admin: Assignments (Manage)",
            "description": "Manage assignments (create/edit/entities/public submissions).",
            "permission_codes": [
                "admin.assignments.view",
                "admin.assignments.create",
                "admin.assignments.edit",
                "admin.assignments.delete",
                "admin.assignments.entities.manage",
                "admin.assignments.public_submissions.manage",
            ],
        },
        {
            "code": "admin_countries_viewer",
            "name": "Admin: Countries & Organization (View)",
            "description": "View countries and organization structure.",
            "permission_codes": ["admin.countries.view"],
        },
        {
            "code": "admin_countries_manager",
            "name": "Admin: Countries & Organization (Manage)",
            "description": "Manage countries and organization structure.",
            "permission_codes": [
                "admin.countries.view",
                "admin.countries.edit",
                "admin.organization.manage",
                "admin.access_requests.view",
                "admin.access_requests.approve",
                "admin.access_requests.reject",
            ],
        },
        {
            "code": "admin_indicator_bank_viewer",
            "name": "Admin: Indicator Bank (View)",
            "description": "View indicator bank.",
            "permission_codes": ["admin.indicator_bank.view"],
        },
        {
            "code": "admin_indicator_bank_manager",
            "name": "Admin: Indicator Bank (Manage)",
            "description": "Manage indicator bank (create/edit/archive/review suggestions).",
            "permission_codes": [
                "admin.indicator_bank.view",
                "admin.indicator_bank.create",
                "admin.indicator_bank.edit",
                "admin.indicator_bank.archive",
                "admin.indicator_bank.suggestions.review",
            ],
        },
        {
            "code": "admin_content_manager",
            "name": "Admin: Content (Manage)",
            "description": "Manage resources, publications, and documents.",
            "permission_codes": [
                "admin.resources.manage",
                "admin.publications.manage",
                "admin.documents.manage",
            ],
        },
        {
            "code": "admin_documents_manager",
            "name": "Admin: Documents (Manage)",
            "description": "Manage documents (upload/edit/delete/approve/decline).",
            "permission_codes": ["admin.documents.manage"],
        },
        {
            "code": "admin_settings_manager",
            "name": "Admin: Settings (Manage)",
            "description": "Manage system settings.",
            "permission_codes": ["admin.settings.manage"],
        },
        {
            "code": "admin_api_manager",
            "name": "Admin: API (Manage)",
            "description": "Manage API keys and API settings.",
            "permission_codes": ["admin.api.manage"],
        },
        {
            "code": "admin_plugins_manager",
            "name": "Admin: Plugins (Manage)",
            "description": "Manage plugins.",
            "permission_codes": ["admin.plugins.manage"],
        },
        {
            "code": "admin_data_explorer_data_table",
            "name": "Admin: Data Explorer (Data Table)",
            "description": "Access the Data Table tab in Data Explorer.",
            "permission_codes": ["admin.data_explore.data_table"],
        },
        {
            "code": "admin_data_explorer_analysis",
            "name": "Admin: Data Explorer (Analysis)",
            "description": "Access the Analysis tab in Data Explorer.",
            "permission_codes": ["admin.data_explore.analysis"],
        },
        {
            "code": "admin_data_explorer_compliance",
            "name": "Admin: Data Explorer (Compliance)",
            "description": "Access the Compliance tab in Data Explorer.",
            "permission_codes": ["admin.data_explore.compliance"],
        },
        {
            "code": "admin_notifications_manager",
            "name": "Admin: Notifications (Manage)",
            "description": "Manage admin notifications center (view all notifications and send notifications).",
            "permission_codes": ["admin.notifications.manage"],
        },
        {
            "code": "admin_translations_manager",
            "name": "Admin: Translations (Manage)",
            "description": "Manage translations (edit/add strings, compile, and reload translations).",
            "permission_codes": ["admin.translations.manage"],
        },
        {
            "code": "admin_docs_viewer",
            "name": "Admin: Docs (View)",
            "description": "View admin documentation and onboarding pages.",
            "permission_codes": ["admin.docs.view"],
        },
        {
            "code": "admin_analytics_viewer",
            "name": "Admin: Analytics (View)",
            "description": "View analytics.",
            "permission_codes": ["admin.analytics.view"],
        },
        {
            "code": "admin_audit_viewer",
            "name": "Admin: Audit Trail (View)",
            "description": "View audit trail.",
            "permission_codes": ["admin.audit.view"],
        },
        {
            "code": "admin_security_viewer",
            "name": "Admin: Security (View)",
            "description": "View security dashboard and events.",
            "permission_codes": ["admin.security.view"],
        },
        {
            "code": "admin_security_responder",
            "name": "Admin: Security (Respond)",
            "description": "View and respond to security events (resolve/test-alert).",
            "permission_codes": ["admin.security.view", "admin.security.respond"],
        },
        {
            "code": "admin_ai_manager",
            "name": "Admin: AI (Manage)",
            "description": "Manage AI system (AI dashboard, document library, reasoning traces, processing).",
            "permission_codes": ["admin.ai.manage"],
        },
        {
            "code": "admin_governance_viewer",
            "name": "Admin: Governance (View)",
            "description": "View the Governance dashboard (focal point coverage, access control, quality, compliance, metadata).",
            "permission_codes": ["admin.governance.view"],
        },
        {
            "code": "assignment_viewer",
            "name": "Assignment Viewer",
            "description": "Read-only access to assignments.",
            "permission_codes": ["assignment.view"],
        },
        {
            "code": "assignment_editor_submitter",
            "name": "Assignment Editor & Submitter",
            "description": "Can enter data and submit assignments (no approval powers).",
            "permission_codes": ["assignment.view", "assignment.enter", "assignment.submit", "assignment.documents.upload"],
        },
        {
            "code": "assignment_documents_uploader",
            "name": "Assignment Documents (Upload)",
            "description": "Upload assignment-related supporting documents (no data entry or submission).",
            "permission_codes": ["assignment.view", "assignment.documents.upload"],
        },
        {
            "code": "assignment_approver",
            "name": "Assignment Approver",
            "description": "Can approve and reopen assignments (typically combined with assignment.view).",
            "permission_codes": ["assignment.view", "assignment.approve", "assignment.reopen"],
        },
    ]


def seed_rbac_permissions_and_roles(*, use_advisory_lock: bool = True) -> Dict[str, int]:
    """
    Seed RBAC permissions and baseline roles (idempotent).

    Returns counts:
      - created_permissions
      - updated_permissions
      - created_roles
      - updated_roles
      - created_role_permission_links
      - deleted_role_permission_links
    """
    permission_catalog = _permission_catalog()
    baseline_roles = _baseline_roles(permission_catalog)

    # This lock prevents multiple gunicorn workers (or multi-instance rollouts)
    # from racing on unique constraints during seeding.
    lock_key = 915_037_121  # arbitrary stable integer constant
    lock_acquired = False

    if use_advisory_lock:
        try:
            lock_acquired = bool(
                db.session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": int(lock_key)}).scalar()
            )
            if not lock_acquired:
                return {
                    "skipped_due_to_lock": 1,
                    "created_permissions": 0,
                    "updated_permissions": 0,
                    "created_roles": 0,
                    "updated_roles": 0,
                    "created_role_permission_links": 0,
                    "deleted_role_permission_links": 0,
                }
        except Exception as e:
            logger.debug("Advisory lock acquire failed: %s", e)
            lock_acquired = False

    try:
        # Best-effort created_by attribution (system_manager user if present)
        created_by_user_id: Optional[int] = None
        try:
            sys_mgr = (
                User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .filter(RbacRole.code == "system_manager")
                .first()
            )
            created_by_user_id = int(sys_mgr.id) if sys_mgr else None
        except Exception as e:
            logger.debug("created_by_user_id lookup failed: %s", e)
            created_by_user_id = None

        catalog_codes = [code for code, _, _ in permission_catalog]
        role_codes = [str(r.get("code")) for r in baseline_roles if r.get("code")]

        created_permissions = 0
        updated_permissions = 0
        created_roles = 0
        updated_roles = 0
        created_links = 0
        deleted_links = 0

        with atomic(remove_session=True):
            # 1) Upsert permissions
            existing_perms = {
                str(p.code): p
                for p in RbacPermission.query.filter(RbacPermission.code.in_(catalog_codes)).all()
                if p and p.code
            }
            for code, name, desc in permission_catalog:
                perm = existing_perms.get(code)
                if not perm:
                    perm = RbacPermission(code=code, name=name, description=desc)
                    db.session.add(perm)
                    existing_perms[code] = perm
                    created_permissions += 1
                else:
                    changed = False
                    if perm.name != name:
                        perm.name = name
                        changed = True
                    if perm.description != desc:
                        perm.description = desc
                        changed = True
                    if changed:
                        updated_permissions += 1

            db.session.flush()

            # Refresh perms with IDs
            perms_by_code = {
                str(p.code): p
                for p in RbacPermission.query.filter(RbacPermission.code.in_(catalog_codes)).all()
                if p and p.code
            }
            catalog_perm_ids = [int(p.id) for p in perms_by_code.values() if getattr(p, "id", None) is not None]

            # 2) Upsert roles
            existing_roles = {
                str(r.code): r
                for r in RbacRole.query.filter(RbacRole.code.in_(role_codes)).all()
                if r and r.code
            }
            for role_def in baseline_roles:
                rcode = str(role_def.get("code") or "").strip()
                if not rcode:
                    continue
                rname = str(role_def.get("name") or rcode)
                rdesc = role_def.get("description")
                role = existing_roles.get(rcode)
                if not role:
                    role = RbacRole(
                        code=rcode,
                        name=rname,
                        description=rdesc,
                        created_by_user_id=created_by_user_id,
                    )
                    db.session.add(role)
                    existing_roles[rcode] = role
                    created_roles += 1
                else:
                    changed = False
                    if role.name != rname:
                        role.name = rname
                        changed = True
                    if role.description != rdesc:
                        role.description = rdesc
                        changed = True
                    if changed:
                        updated_roles += 1

            db.session.flush()

            # 3) Ensure role-permission links for baseline roles, and remove stale catalog links
            for role_def in baseline_roles:
                rcode = str(role_def.get("code") or "").strip()
                if not rcode:
                    continue
                role = existing_roles.get(rcode)
                if not role or getattr(role, "id", None) is None:
                    continue

                desired_codes_raw = list(role_def.get("permission_codes") or [])
                # Deduplicate while preserving order
                seen: set[str] = set()
                desired_codes: List[str] = []
                for c in desired_codes_raw:
                    cs = str(c or "").strip()
                    if not cs or cs in seen:
                        continue
                    seen.add(cs)
                    desired_codes.append(cs)

                desired_perm_ids = {
                    int(perms_by_code[c].id)
                    for c in desired_codes
                    if c in perms_by_code and getattr(perms_by_code[c], "id", None) is not None
                }

                if catalog_perm_ids:
                    existing_links = (
                        RbacRolePermission.query.filter(
                            RbacRolePermission.role_id == role.id,
                            RbacRolePermission.permission_id.in_(catalog_perm_ids),
                        ).all()
                    )
                else:
                    existing_links = []

                existing_perm_ids = {int(l.permission_id) for l in existing_links if l and l.permission_id is not None}

                # Add missing
                for pid in desired_perm_ids - existing_perm_ids:
                    db.session.add(RbacRolePermission(role_id=int(role.id), permission_id=int(pid)))
                    created_links += 1

                # Remove stale (only those in the catalog)
                for link in existing_links:
                    if int(link.permission_id) not in desired_perm_ids:
                        db.session.delete(link)
                        deleted_links += 1

            db.session.flush()

        return {
            "skipped_due_to_lock": 0,
            "created_permissions": int(created_permissions),
            "updated_permissions": int(updated_permissions),
            "created_roles": int(created_roles),
            "updated_roles": int(updated_roles),
            "created_role_permission_links": int(created_links),
            "deleted_role_permission_links": int(deleted_links),
        }
    finally:
        if lock_acquired:
            try:
                db.session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": int(lock_key)})
            except Exception as e:
                logger.debug("RBAC seed: pg_advisory_unlock failed: %s", e)
