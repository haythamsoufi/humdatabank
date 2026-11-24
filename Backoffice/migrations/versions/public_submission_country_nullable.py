"""Allow public submissions without a country.

Revision ID: public_submission_country_nullable
Revises: rename_global_award_singular
Create Date: 2026-11-24

Public links can now collect surveys and other forms that are not tied to a
country, so ``public_submission.country_id`` becomes nullable. Existing rows
keep their country. The downgrade refuses to run while country-less rows exist
rather than deleting or guessing a country for them.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "public_submission_country_nullable"
down_revision = "rename_global_award_singular"
branch_labels = None
depends_on = None


def _country_id_column():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "public_submission" not in inspector.get_table_names():
        return None
    for col in inspector.get_columns("public_submission"):
        if col["name"] == "country_id":
            return col
    return None


def upgrade():
    col = _country_id_column()
    if col is None or col.get("nullable"):
        return
    op.alter_column(
        "public_submission",
        "country_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    col = _country_id_column()
    if col is None or not col.get("nullable"):
        return
    bind = op.get_bind()
    orphaned = bind.execute(
        sa.text("SELECT COUNT(*) FROM public_submission WHERE country_id IS NULL")
    ).scalar()
    if orphaned:
        raise RuntimeError(
            f"Cannot restore NOT NULL on public_submission.country_id: "
            f"{orphaned} submission(s) have no country. Assign or delete them first."
        )
    op.alter_column(
        "public_submission",
        "country_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
