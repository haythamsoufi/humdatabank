"""Add short_name fields to secretariat_regional_offices

Revision ID: secretariat_ro_short_name
Revises: country_secretariat_ro
Create Date: 2026-06-25
"""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "secretariat_ro_short_name"
down_revision = "country_secretariat_ro"
branch_labels = None
depends_on = None

SHORT_NAME_BY_NAME = {
    "Africa": "Africa",
    "Americas": "Americas",
    "Asia Pacific": "Asia Pacific",
    "Europe and Central Asia": "Europe & CA",
    "MENA": "MENA",
}

SHORT_NAME_TRANSLATIONS = {
    "Europe and Central Asia": {
        "en": "Europe & CA",
        "fr": "Europe & CA",
        "es": "Europa & CA",
        "ar": "أوروبا وآسيا الوسطى",
        "zh": "欧洲和中亚",
        "ru": "Европа и ЦА",
        "hi": "यूरोप और मध्य एशिया",
    },
}


def upgrade():
    with op.batch_alter_table("secretariat_regional_offices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("short_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("short_name_translations", JSONB(), nullable=True))

    bind = op.get_bind()
    offices = bind.execute(
        sa.text("SELECT id, name FROM secretariat_regional_offices")
    ).fetchall()
    for office_id, name in offices:
        short_name = SHORT_NAME_BY_NAME.get(name)
        if not short_name:
            continue
        short_trans = SHORT_NAME_TRANSLATIONS.get(name)
        bind.execute(
            sa.text(
                """
                UPDATE secretariat_regional_offices
                SET short_name = :short_name,
                    short_name_translations = CAST(:short_trans AS JSONB)
                WHERE id = :office_id
                """
            ),
            {
                "short_name": short_name,
                "short_trans": json.dumps(short_trans) if short_trans else None,
                "office_id": office_id,
            },
        )


def downgrade():
    with op.batch_alter_table("secretariat_regional_offices", schema=None) as batch_op:
        batch_op.drop_column("short_name_translations")
        batch_op.drop_column("short_name")
