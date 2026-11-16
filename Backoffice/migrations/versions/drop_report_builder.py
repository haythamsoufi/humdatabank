"""Remove the admin report builder tables and RBAC.

Drops saved report definitions, revisions, and publish runs, and deletes the
report-builder permissions and roles. Saved report rows are not recoverable.
Uploaded images and published files under the storage category ``reports`` are
left in place.

Revision ID: drop_report_builder
Revises: add_guidance_folder_path
Create Date: 2026-11-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision = "drop_report_builder"
down_revision = "add_guidance_folder_path"
branch_labels = None
depends_on = None

_PERMISSIONS = (
    ("admin.reports.view", "Reports: View", "View reports within assigned scope"),
    ("admin.reports.edit", "Reports: Edit", "Create and edit own reports"),
    ("admin.reports.manage", "Reports: Manage all", "View and edit all reports (system managers)"),
    (
        "admin.data_explore.reports",
        "Data Explorer: Reports",
        "Access published reports in Data Explorer",
    ),
)

_ROLES = (
    (
        "admin_reports_viewer",
        "Admin: Reports (View)",
        "View published reports within scope.",
        ("admin.reports.view",),
    ),
    (
        "admin_reports_editor",
        "Admin: Reports (Edit)",
        "Create and edit reports within scope.",
        ("admin.reports.view", "admin.reports.edit"),
    ),
    (
        "admin_data_explorer_reports",
        "Admin: Data Explorer (Reports)",
        "Access published reports in Data Explorer.",
        ("admin.data_explore.reports",),
    ),
)

_TABLES = ("report_definition_revision", "report_run", "report_definition")


def _delete_rbac(conn) -> None:
    insp = inspect(conn)
    if not insp.has_table("rbac_permission") or not insp.has_table("rbac_role"):
        return

    for role_code, _, _, _ in _ROLES:
        row = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": role_code},
        ).fetchone()
        if not row:
            continue
        role_id = row[0]
        if insp.has_table("rbac_access_grant"):
            conn.execute(
                text(
                    """
                    DELETE FROM rbac_access_grant
                    WHERE principal_type = 'role' AND principal_id = :role_id
                    """
                ),
                {"role_id": role_id},
            )
        conn.execute(
            text("DELETE FROM rbac_user_role WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"),
            {"role_id": role_id},
        )
        conn.execute(text("DELETE FROM rbac_role WHERE id = :role_id"), {"role_id": role_id})

    for code, _, _ in _PERMISSIONS:
        row = conn.execute(
            text("SELECT id FROM rbac_permission WHERE code = :code"),
            {"code": code},
        ).fetchone()
        if not row:
            continue
        permission_id = row[0]
        if insp.has_table("rbac_access_grant"):
            conn.execute(
                text("DELETE FROM rbac_access_grant WHERE permission_id = :permission_id"),
                {"permission_id": permission_id},
            )
        conn.execute(
            text("DELETE FROM rbac_role_permission WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
        conn.execute(
            text("DELETE FROM rbac_permission WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )


def upgrade():
    conn = op.get_bind()
    insp = inspect(conn)
    for table in _TABLES:
        if insp.has_table(table):
            op.drop_table(table)
    _delete_rbac(conn)


def _ensure_permission(conn, code, name, description):
    row = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        text(
            """
            INSERT INTO rbac_permission (code, name, description, created_at)
            VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """
        ),
        {"code": code, "name": name, "description": description},
    )
    return conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": code},
    ).fetchone()[0]


def _ensure_role(conn, code, name, description, perm_codes):
    row = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if not row:
        conn.execute(
            text(
                """
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
                """
            ),
            {"code": code, "name": name, "description": description},
        )
        row = conn.execute(
            text("SELECT id FROM rbac_role WHERE code = :code"),
            {"code": code},
        ).fetchone()
    role_id = row[0]
    for perm_code in perm_codes:
        perm = conn.execute(
            text("SELECT id FROM rbac_permission WHERE code = :code"),
            {"code": perm_code},
        ).fetchone()
        if not perm:
            continue
        conn.execute(
            text(
                """
                INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
            ),
            {"role_id": role_id, "perm_id": perm[0]},
        )


def downgrade():
    """Recreate empty tables and the dedicated roles. Saved reports are not restored."""
    op.create_table(
        "report_definition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "definition_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "scope_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
    )
    op.create_index("ix_report_definition_slug", "report_definition", ["slug"], unique=True)
    op.create_index("ix_report_definition_status", "report_definition", ["status"])
    op.create_index("ix_report_definition_owner_user_id", "report_definition", ["owner_user_id"])
    op.create_index(
        "ix_report_definition_owner_status",
        "report_definition",
        ["owner_user_id", "status"],
    )

    op.create_table(
        "report_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("report_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("build_stage", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("triggered_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_report_run_report_id", "report_run", ["report_id"])
    op.create_index("ix_report_run_status", "report_run", ["status"])

    op.create_table(
        "report_definition_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("report_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "definition_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_report_definition_revision_report_id",
        "report_definition_revision",
        ["report_id"],
    )

    conn = op.get_bind()
    if inspect(conn).has_table("rbac_permission"):
        for code, name, description in _PERMISSIONS:
            _ensure_permission(conn, code, name, description)
        for role_code, role_name, role_desc, perm_codes in _ROLES:
            _ensure_role(conn, role_code, role_name, role_desc, perm_codes)
