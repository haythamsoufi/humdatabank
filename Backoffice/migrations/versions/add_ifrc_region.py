"""Add ifrc_region table and link countries to IFRC regions

Revision ID: add_ifrc_region
Revises: add_custom_name_trans_af
Create Date: 2026-06-25
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "add_ifrc_region"
down_revision = "add_custom_name_trans_af"
branch_labels = None
depends_on = None

IFRC_REGION_SEED = [
    ("africa", "Africa", 1),
    ("americas", "Americas", 2),
    ("asia_pacific", "Asia Pacific", 3),
    ("europe_ca", "Europe and Central Asia", 4),
    ("mena", "MENA", 5),
]

REGION_LABEL_ALIASES = {
    "europe": "Europe and Central Asia",
    "europe & ca": "Europe and Central Asia",
    "europe & central asia": "Europe and Central Asia",
    "eu & ca": "Europe and Central Asia",
    "middle east and north africa": "MENA",
    "asia-pacific": "Asia Pacific",
    "asia pacific": "Asia Pacific",
}


def _normalize_region_label(label):
    if not label:
        return None
    raw = str(label).strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in REGION_LABEL_ALIASES:
        return REGION_LABEL_ALIASES[lowered]
    for _, name, _ in IFRC_REGION_SEED:
        if name.lower() == lowered:
            return name
    return raw


def upgrade():
    now = datetime.utcnow()
    op.create_table(
        "ifrc_region",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("name_translations", JSONB(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_ifrc_region_code"),
        sa.UniqueConstraint("name", name="uq_ifrc_region_name"),
    )

    bind = op.get_bind()
    for code, name, display_order in IFRC_REGION_SEED:
        bind.execute(
            sa.text(
                """
                INSERT INTO ifrc_region (code, name, display_order, is_active, created_at, updated_at)
                VALUES (:code, :name, :display_order, true, :now, :now)
                """
            ),
            {"code": code, "name": name, "display_order": display_order, "now": now},
        )

    with op.batch_alter_table("country", schema=None) as batch_op:
        batch_op.alter_column(
            "region",
            existing_type=sa.String(length=15),
            type_=sa.String(length=100),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("ifrc_region_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_country_ifrc_region",
            "ifrc_region",
            ["ifrc_region_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_country_ifrc_region_id", ["ifrc_region_id"])

    name_to_id = {
        row[0]: row[1]
        for row in bind.execute(sa.text("SELECT name, id FROM ifrc_region")).fetchall()
    }

    countries = bind.execute(sa.text("SELECT id, region FROM country")).fetchall()
    for country_id, region_label in countries:
        canonical = _normalize_region_label(region_label)
        region_id = name_to_id.get(canonical)
        if region_id is None and canonical:
            region_id = next(
                (rid for name, rid in name_to_id.items() if name.lower() == canonical.lower()),
                None,
            )
        if region_id is not None:
            canonical_name = next(name for name, rid in name_to_id.items() if rid == region_id)
            bind.execute(
                sa.text(
                    """
                    UPDATE country
                    SET ifrc_region_id = :region_id, region = :region_name
                    WHERE id = :country_id
                    """
                ),
                {
                    "region_id": region_id,
                    "region_name": canonical_name,
                    "country_id": country_id,
                },
            )


def downgrade():
    with op.batch_alter_table("country", schema=None) as batch_op:
        batch_op.drop_index("ix_country_ifrc_region_id")
        batch_op.drop_constraint("fk_country_ifrc_region", type_="foreignkey")
        batch_op.drop_column("ifrc_region_id")
        batch_op.alter_column(
            "region",
            existing_type=sa.String(length=100),
            type_=sa.String(length=15),
            existing_nullable=False,
        )

    op.drop_table("ifrc_region")
