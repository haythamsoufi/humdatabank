"""Ensure core ``project`` table exists after draft-schema stamp mishaps.

Revision ID: ensure_core_project_table
Revises: aes_entity_type_project
Create Date: 2026-10-28

Safety net for environments that stamped ``add_nsd_project_table`` while an
earlier draft still created ``nsd_project`` (Alembic will not re-run that
revision). Fresh prod upgrades are a no-op: ``project`` already exists from
the previous revision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = "ensure_core_project_table"
down_revision = "aes_entity_type_project"
branch_labels = None
depends_on = None


_COLUMN_RENAMES = (
    ("national_society_name", "organization_name"),
    ("amount_granted_chf", "amount_granted"),
    ("expected_spending_chf", "expected_spending"),
    ("ns_focal_name", "focal_name"),
    ("ns_focal_email", "focal_email"),
    ("ifrc_pm_name", "manager_name"),
    ("ifrc_pm_email", "manager_email"),
    ("logframe", "plan_data"),
)

_INDEX_RENAMES = (
    ("ix_nsd_project_country", "ix_project_country"),
    ("ix_nsd_project_status", "ix_project_status"),
    ("ix_nsd_project_pm_email", "ix_project_manager_email"),
    ("ix_nsd_project_focal_email", "ix_project_focal_email"),
    ("ix_nsd_project_fund", "ix_project_fund"),
)

_CONSTRAINT_RENAMES = (
    ("uq_nsd_project_reference", "uq_project_reference"),
    ("nsd_project_pkey", "project_pkey"),
    ("nsd_project_country_id_fkey", "project_country_id_fkey"),
)

_INDEXES = (
    ("ix_project_country", ["country_id"]),
    ("ix_project_status", ["status"]),
    ("ix_project_fund", ["fund"]),
    ("ix_project_manager_email", ["manager_email"]),
    ("ix_project_focal_email", ["focal_email"]),
)


def _inspector():
    return inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _column_names(table: str) -> set[str]:
    return {c["name"] for c in _inspector().get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {idx["name"] for idx in _inspector().get_indexes(table) if idx.get("name")}


def _rename_constraint_if_exists(table: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{old}') "
            f"AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{new}') THEN "
            f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}"; '
            "END IF; END $$;"
        )
    )


def _normalize_draft_columns(table: str = "project") -> None:
    cols = _column_names(table)
    for old, new in _COLUMN_RENAMES:
        if old in cols and new not in cols:
            op.alter_column(table, old, new_column_name=new)


def _ensure_indexes(table: str = "project") -> None:
    existing = _index_names(table)
    for name, cols in _INDEXES:
        if name not in existing:
            op.create_index(name, table, cols)


def _promote_draft_nsd_project() -> None:
    op.rename_table("nsd_project", "project")
    for old, new in _INDEX_RENAMES:
        op.execute(sa.text(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"'))
    for old, new in _CONSTRAINT_RENAMES:
        _rename_constraint_if_exists("project", old, new)
    _normalize_draft_columns("project")
    _ensure_indexes("project")


def _create_project_table() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(length=80), nullable=False),
        sa.Column("fund", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("organization_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="Open"),
        sa.Column("funding_modality", sa.String(length=120), nullable=True),
        sa.Column("categories", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("amount_granted", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_spending", sa.Numeric(14, 2), nullable=True),
        sa.Column("planned_overview", sa.Text(), nullable=True),
        sa.Column("focal_name", sa.String(length=255), nullable=True),
        sa.Column("focal_email", sa.String(length=255), nullable=True),
        sa.Column("manager_name", sa.String(length=255), nullable=True),
        sa.Column("manager_email", sa.String(length=255), nullable=True),
        sa.Column(
            "plan_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["country.id"],
            name="project_country_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("reference", name="uq_project_reference"),
    )
    for name, cols in _INDEXES:
        op.create_index(name, "project", cols)


def upgrade():
    if _has_table("nsd_project") and not _has_table("project"):
        _promote_draft_nsd_project()
        return

    if not _has_table("project"):
        _create_project_table()
        return

    _normalize_draft_columns("project")
    _ensure_indexes("project")


def downgrade():
    # Non-destructive: this revision only ensures schema presence.
    pass
