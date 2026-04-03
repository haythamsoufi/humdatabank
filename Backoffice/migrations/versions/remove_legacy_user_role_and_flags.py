"""Remove legacy User.role and can_manage_* flags (RBAC-only)

Revision ID: remove_legacy_user_role_and_flags
Revises: remove_template_type
Create Date: 2026-01-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "remove_legacy_user_role_and_flags"
down_revision = "expand_alembic_version_num"
branch_labels = None
depends_on = None


def _ensure_role(bind, *, code: str, name: str, description: str):
    """
    Ensure a role exists (idempotent).

    Note: We only create roles here so we can safely map existing users before
    dropping legacy columns. Permissions and role-permission links are seeded
    by the app (flask rbac seed).
    """
    bind.execute(
        sa.text(
            """
            INSERT INTO rbac_role (code, name, description, created_at, created_by_user_id)
            SELECT :code, :name, :description, NOW(), NULL
            WHERE NOT EXISTS (SELECT 1 FROM rbac_role WHERE code = :code)
            """
        ),
        {"code": code, "name": name, "description": description},
    )


def upgrade():
    bind = op.get_bind()

    # ---------------------------------------------------------------------
    # 1) Ensure baseline RBAC roles exist (so we can map users deterministically)
    # ---------------------------------------------------------------------
    baseline_roles = [
        ("system_manager", "System Manager", "Full access to all platform capabilities (superuser)."),
        ("admin_core", "Admin: Core (Essentials only)", "Essential, mostly read-only access across key admin areas."),
        ("admin_full", "Admin: Full (All admin roles)", "Full access to all admin modules (non-system-manager)."),
        ("admin_users_manager", "Admin: Users (Manage)", "Manage users."),
        ("admin_templates_manager", "Admin: Templates (Manage)", "Manage templates."),
        ("admin_assignments_manager", "Admin: Assignments (Manage)", "Manage assignments."),
        ("admin_countries_manager", "Admin: Countries & Organization (Manage)", "Manage countries and organization structure."),
        ("admin_indicator_bank_manager", "Admin: Indicator Bank (Manage)", "Manage indicator bank."),
        ("admin_content_manager", "Admin: Content (Manage)", "Manage resources/publications/documents."),
        ("admin_settings_manager", "Admin: Settings (Manage)", "Manage system settings."),
        ("admin_api_manager", "Admin: API (Manage)", "Manage API keys and API settings."),
        ("admin_plugins_manager", "Admin: Plugins (Manage)", "Manage plugins."),
        ("admin_data_explorer", "Admin: Data Explorer", "Use data exploration tools."),
        ("admin_analytics_viewer", "Admin: Analytics (View)", "View analytics."),
        ("admin_audit_viewer", "Admin: Audit Trail (View)", "View audit trail."),
        ("assignment_viewer", "Assignment Viewer", "Read-only access to assignments."),
        ("assignment_editor_submitter", "Assignment Editor & Submitter", "Can enter data and submit assignments."),
        ("assignment_approver", "Assignment Approver", "Can approve and reopen assignments."),
    ]
    for code, name, desc in baseline_roles:
        _ensure_role(bind, code=code, name=name, description=desc)

    role_rows = bind.execute(
        sa.text("SELECT id, code FROM rbac_role WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": [c for c, _, _ in baseline_roles]},
    ).fetchall()
    role_id_by_code = {r.code: r.id for r in role_rows}

    # ---------------------------------------------------------------------
    # 2) Migrate existing users from legacy role/flags into RBAC user roles
    # ---------------------------------------------------------------------
    # We mirror the mapping logic from the old `flask rbac bootstrap-users` command.
    user_rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                role,
                can_manage_users,
                can_manage_templates,
                can_manage_assignments,
                can_manage_countries,
                can_manage_publications,
                can_manage_indicator_bank,
                can_manage_settings,
                can_view_analytics,
                can_manage_public_assignments,
                can_view_admin_dashboard,
                can_view_audit_trail,
                can_manage_api,
                can_manage_plugins,
                can_explore_data
            FROM "user"
            """
        )
    ).fetchall()

    for u in user_rows:
        legacy_role = (u.role or "").strip()
        target_codes = []

        if legacy_role == "system_manager":
            target_codes = ["system_manager"]
        elif legacy_role == "focal_point":
            target_codes = ["assignment_editor_submitter"]
        elif legacy_role == "admin":
            # Map legacy admin boolean flags to granular RBAC module roles
            if bool(u.can_manage_users):
                target_codes.append("admin_users_manager")
            if bool(u.can_manage_templates):
                target_codes.append("admin_templates_manager")
            if bool(u.can_manage_assignments) or bool(u.can_manage_public_assignments):
                target_codes.append("admin_assignments_manager")
            if bool(u.can_manage_countries):
                target_codes.append("admin_countries_manager")
            if bool(u.can_manage_indicator_bank):
                target_codes.append("admin_indicator_bank_manager")
            if bool(u.can_manage_publications):
                target_codes.append("admin_content_manager")
            if bool(u.can_manage_settings):
                target_codes.append("admin_settings_manager")
            if bool(u.can_manage_api):
                target_codes.append("admin_api_manager")
            if bool(u.can_manage_plugins):
                target_codes.append("admin_plugins_manager")
            if bool(u.can_explore_data):
                target_codes.append("admin_data_explorer")
            if bool(u.can_view_analytics):
                target_codes.append("admin_analytics_viewer")
            if bool(u.can_view_audit_trail):
                target_codes.append("admin_audit_viewer")

            # If an admin has no granular flags set, keep them functional by assigning admin_core.
            if not target_codes and bool(getattr(u, "can_view_admin_dashboard", False)):
                target_codes = ["admin_core"]

        # Any remaining legacy role values become assignment viewers by default (safe baseline).
        if not target_codes:
            target_codes = ["assignment_viewer"]

        for code in target_codes:
            role_id = role_id_by_code.get(code)
            if not role_id:
                continue
            bind.execute(
                sa.text(
                    """
                    INSERT INTO rbac_user_role (user_id, role_id, created_at)
                    VALUES (:user_id, :role_id, NOW())
                    ON CONFLICT (user_id, role_id) DO NOTHING
                    """
                ),
                {"user_id": int(u.id), "role_id": int(role_id)},
            )

    # ---------------------------------------------------------------------
    # 3) Drop legacy columns (breaking change)
    # ---------------------------------------------------------------------
    op.drop_column("user", "role")
    op.drop_column("user", "can_manage_users")
    op.drop_column("user", "can_manage_templates")
    op.drop_column("user", "can_manage_assignments")
    op.drop_column("user", "can_manage_countries")
    op.drop_column("user", "can_manage_publications")
    op.drop_column("user", "can_manage_indicator_bank")
    op.drop_column("user", "can_manage_settings")
    op.drop_column("user", "can_view_analytics")
    op.drop_column("user", "can_manage_public_assignments")
    op.drop_column("user", "can_view_admin_dashboard")
    op.drop_column("user", "can_view_audit_trail")
    op.drop_column("user", "can_manage_api")
    op.drop_column("user", "can_manage_plugins")
    op.drop_column("user", "can_explore_data")


def downgrade():
    # Re-introduce legacy columns (best-effort). Data is not restored.
    op.add_column("user", sa.Column("role", sa.String(length=64), nullable=True))
    op.add_column("user", sa.Column("can_manage_users", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_templates", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_assignments", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_countries", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_publications", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_indicator_bank", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_settings", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_view_analytics", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_public_assignments", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_view_admin_dashboard", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_view_audit_trail", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_api", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_manage_plugins", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("user", sa.Column("can_explore_data", sa.Boolean(), nullable=False, server_default=sa.text("true")))
