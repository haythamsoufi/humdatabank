"""Link countries to secretariat_regional_offices; remove ifrc_region table

Revision ID: country_secretariat_ro
Revises: add_ifrc_region
Create Date: 2026-06-25
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "country_secretariat_ro"
down_revision = "add_ifrc_region"
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
    bind = op.get_bind()
    now = datetime.utcnow()

    for code, name, display_order in IFRC_REGION_SEED:
        existing = bind.execute(
            sa.text("SELECT id FROM secretariat_regional_offices WHERE code = :code OR name = :name"),
            {"code": code, "name": name},
        ).fetchone()
        if existing is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO secretariat_regional_offices
                        (name, code, display_order, is_active, created_at, updated_at)
                    VALUES (:name, :code, :display_order, true, :now, :now)
                    """
                ),
                {
                    "name": name,
                    "code": code,
                    "display_order": display_order,
                    "now": now,
                },
            )

    office_code_to_id = {
        row[0]: row[1]
        for row in bind.execute(
            sa.text("SELECT code, id FROM secretariat_regional_offices WHERE code IS NOT NULL")
        ).fetchall()
    }
    office_name_to_id = {
        row[0]: row[1]
        for row in bind.execute(sa.text("SELECT name, id FROM secretariat_regional_offices")).fetchall()
    }

    with op.batch_alter_table("country", schema=None) as batch_op:
        batch_op.add_column(sa.Column("secretariat_regional_office_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_country_secretariat_regional_office",
            "secretariat_regional_offices",
            ["secretariat_regional_office_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_country_secretariat_regional_office_id", ["secretariat_regional_office_id"])

    # Prefer mapping from ifrc_region when that table exists (previous migration).
    inspector = sa.inspect(bind)
    if "ifrc_region" in inspector.get_table_names():
        ifrc_code_to_id = {
            row[0]: row[1]
            for row in bind.execute(sa.text("SELECT code, id FROM ifrc_region")).fetchall()
        }
        for ifrc_code, office_id in office_code_to_id.items():
            ifrc_id = ifrc_code_to_id.get(ifrc_code)
            if ifrc_id is None:
                continue
            bind.execute(
                sa.text(
                    """
                    UPDATE country
                    SET secretariat_regional_office_id = :office_id
                    WHERE ifrc_region_id = :ifrc_id
                    """
                ),
                {"office_id": office_id, "ifrc_id": ifrc_id},
            )

    countries = bind.execute(sa.text("SELECT id, region FROM country")).fetchall()
    for country_id, region_label in countries:
        linked = bind.execute(
            sa.text(
                "SELECT secretariat_regional_office_id FROM country WHERE id = :country_id"
            ),
            {"country_id": country_id},
        ).fetchone()
        if linked and linked[0] is not None:
            continue

        canonical = _normalize_region_label(region_label)
        office_id = office_name_to_id.get(canonical)
        if office_id is None and canonical:
            office_id = next(
                (rid for name, rid in office_name_to_id.items() if name.lower() == canonical.lower()),
                None,
            )
        if office_id is not None:
            canonical_name = next(name for name, rid in office_name_to_id.items() if rid == office_id)
            bind.execute(
                sa.text(
                    """
                    UPDATE country
                    SET secretariat_regional_office_id = :office_id, region = :region_name
                    WHERE id = :country_id
                    """
                ),
                {
                    "office_id": office_id,
                    "region_name": canonical_name,
                    "country_id": country_id,
                },
            )

    with op.batch_alter_table("country", schema=None) as batch_op:
        batch_op.drop_index("ix_country_ifrc_region_id")
        batch_op.drop_constraint("fk_country_ifrc_region", type_="foreignkey")
        batch_op.drop_column("ifrc_region_id")

    op.drop_table("ifrc_region")


def downgrade():
    from sqlalchemy.dialects.postgresql import JSONB

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
        batch_op.add_column(sa.Column("ifrc_region_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_country_ifrc_region",
            "ifrc_region",
            ["ifrc_region_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_country_ifrc_region_id", ["ifrc_region_id"])

    office_code_to_id = {
        row[0]: row[1]
        for row in bind.execute(
            sa.text("SELECT code, id FROM secretariat_regional_offices WHERE code IS NOT NULL")
        ).fetchall()
    }
    ifrc_code_to_id = {
        row[0]: row[1]
        for row in bind.execute(sa.text("SELECT code, id FROM ifrc_region")).fetchall()
    }
    for code, office_id in office_code_to_id.items():
        ifrc_id = ifrc_code_to_id.get(code)
        if ifrc_id is None:
            continue
        bind.execute(
            sa.text(
                """
                UPDATE country
                SET ifrc_region_id = :ifrc_id
                WHERE secretariat_regional_office_id = :office_id
                """
            ),
            {"ifrc_id": ifrc_id, "office_id": office_id},
        )

    with op.batch_alter_table("country", schema=None) as batch_op:
        batch_op.drop_index("ix_country_secretariat_regional_office_id")
        batch_op.drop_constraint("fk_country_secretariat_regional_office", type_="foreignkey")
        batch_op.drop_column("secretariat_regional_office_id")
