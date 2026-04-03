"""Add JSONB name_translations to sector/sub_sector

Revision ID: sector_subsector_name_trans
Revises: add_ai_chat_archiving
Create Date: 2026-01-10

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "sector_subsector_name_trans"
down_revision = "add_ai_chat_archiving"
branch_labels = None
depends_on = None


def upgrade():
    # Add JSONB columns
    op.add_column("sector", sa.Column("name_translations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("sub_sector", sa.Column("name_translations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Backfill from legacy per-language columns where present
    # Keep only non-null keys using jsonb_strip_nulls
    op.execute(
        """
        UPDATE sector
        SET name_translations = NULLIF(
            jsonb_strip_nulls(
                jsonb_build_object(
                    'fr', name_french,
                    'es', name_spanish,
                    'ar', name_arabic,
                    'zh', name_chinese,
                    'ru', name_russian,
                    'hi', name_hindi
                )
            ),
            '{}'::jsonb
        )
        WHERE name_translations IS NULL
          AND (name_french IS NOT NULL OR name_spanish IS NOT NULL OR name_arabic IS NOT NULL OR
               name_chinese IS NOT NULL OR name_russian IS NOT NULL OR name_hindi IS NOT NULL);
        """
    )

    op.execute(
        """
        UPDATE sub_sector
        SET name_translations = NULLIF(
            jsonb_strip_nulls(
                jsonb_build_object(
                    'fr', name_french,
                    'es', name_spanish,
                    'ar', name_arabic,
                    'zh', name_chinese,
                    'ru', name_russian,
                    'hi', name_hindi
                )
            ),
            '{}'::jsonb
        )
        WHERE name_translations IS NULL
          AND (name_french IS NOT NULL OR name_spanish IS NOT NULL OR name_arabic IS NOT NULL OR
               name_chinese IS NOT NULL OR name_russian IS NOT NULL OR name_hindi IS NOT NULL);
        """
    )


def downgrade():
    op.drop_column("sub_sector", "name_translations")
    op.drop_column("sector", "name_translations")
