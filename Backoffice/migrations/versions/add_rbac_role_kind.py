"""Add rbac_role.kind to separate Access Groups from permission roles.

Revision ID: add_rbac_role_kind
Revises: add_fdrs_society
Create Date: 2026-10-17

``rbac_role.kind`` distinguishes classic permission-bundle roles
(``'permission'``, the default) from Access Groups (``'group'``) such as
Finance or HR. Access Groups carry no permissions; they only express
organizational membership used to scope which assignments a user can reach.

Backfill: every existing role defaults to ``'permission'``. Any role that is
NOT a code-defined baseline/plugin role AND currently has zero permission links
is reclassified as a ``'group'`` -- these are the custom roles a System Manager
created for the assignment access-control feature, which is exactly what Access
Groups are meant to replace. Baseline roles (even permission-less ones like
``translator``) always stay ``'permission'``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "add_rbac_role_kind"
down_revision = "add_fdrs_society"
branch_labels = None
depends_on = None


def _baseline_role_codes() -> set:
    """Best-effort set of code-defined (baseline + plugin) role codes.

    Returns an empty set on any failure so the backfill degrades to "touch
    nothing" rather than misclassifying a permission role as a group.
    """
    try:
        from app.services.organization.rbac_seed_service import get_baseline_role_codes

        return set(get_baseline_role_codes())
    except Exception:
        return set()


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)

    columns = {col["name"] for col in inspector.get_columns("rbac_role")}
    if "kind" not in columns:
        op.add_column(
            "rbac_role",
            sa.Column(
                "kind",
                sa.String(length=20),
                nullable=False,
                server_default="permission",
            ),
        )

    op.execute("ALTER TABLE rbac_role DROP CONSTRAINT IF EXISTS ck_rbac_role_kind")
    op.create_check_constraint(
        "ck_rbac_role_kind",
        "rbac_role",
        "kind IN ('permission','group')",
    )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("rbac_role")}
    if "ix_rbac_role_kind" not in existing_indexes:
        op.create_index("ix_rbac_role_kind", "rbac_role", ["kind"])

    # Backfill: non-baseline, permission-less roles become Access Groups.
    baseline = _baseline_role_codes()
    roles = conn.execute(sa.text("SELECT id, code FROM rbac_role")).fetchall()
    perm_rows = conn.execute(
        sa.text("SELECT role_id, COUNT(*) AS c FROM rbac_role_permission GROUP BY role_id")
    ).fetchall()
    perm_count = {int(r[0]): int(r[1]) for r in perm_rows}

    group_ids = [
        int(r[0])
        for r in roles
        if str(r[1]) not in baseline and perm_count.get(int(r[0]), 0) == 0
    ]
    if group_ids:
        conn.execute(
            sa.text("UPDATE rbac_role SET kind = 'group' WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": group_ids},
        )


def downgrade():
    inspector = inspect(op.get_bind())
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("rbac_role")}
    if "ix_rbac_role_kind" in existing_indexes:
        op.drop_index("ix_rbac_role_kind", table_name="rbac_role")
    op.execute("ALTER TABLE rbac_role DROP CONSTRAINT IF EXISTS ck_rbac_role_kind")
    columns = {col["name"] for col in inspector.get_columns("rbac_role")}
    if "kind" in columns:
        op.drop_column("rbac_role", "kind")
