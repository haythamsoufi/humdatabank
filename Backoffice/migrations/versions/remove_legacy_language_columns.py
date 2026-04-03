"""Remove legacy language columns from sector and sub_sector tables

Revision ID: remove_legacy_lang_cols
Revises: sector_subsector_name_trans
Create Date: 2026-01-11

This migration removes the legacy per-language columns (name_french, name_spanish, etc.)
from sector and sub_sector tables after migrating to JSONB name_translations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'remove_legacy_lang_cols'
down_revision = 'sector_subsector_name_trans'
branch_labels = None
depends_on = None


def upgrade():
    # First, ensure any remaining data in legacy columns is migrated to JSONB
    # This is a safety check in case any data was added after the previous migration
    op.execute(
        """
        UPDATE sector
        SET name_translations = COALESCE(
            name_translations,
            '{}'::jsonb
        ) || jsonb_strip_nulls(
            jsonb_build_object(
                'fr', CASE WHEN name_french IS NOT NULL AND (name_translations IS NULL OR name_translations->>'fr' IS NULL) THEN name_french ELSE NULL END,
                'es', CASE WHEN name_spanish IS NOT NULL AND (name_translations IS NULL OR name_translations->>'es' IS NULL) THEN name_spanish ELSE NULL END,
                'ar', CASE WHEN name_arabic IS NOT NULL AND (name_translations IS NULL OR name_translations->>'ar' IS NULL) THEN name_arabic ELSE NULL END,
                'zh', CASE WHEN name_chinese IS NOT NULL AND (name_translations IS NULL OR name_translations->>'zh' IS NULL) THEN name_chinese ELSE NULL END,
                'ru', CASE WHEN name_russian IS NOT NULL AND (name_translations IS NULL OR name_translations->>'ru' IS NULL) THEN name_russian ELSE NULL END,
                'hi', CASE WHEN name_hindi IS NOT NULL AND (name_translations IS NULL OR name_translations->>'hi' IS NULL) THEN name_hindi ELSE NULL END
            )
        )
        WHERE name_french IS NOT NULL OR name_spanish IS NOT NULL OR name_arabic IS NOT NULL OR
              name_chinese IS NOT NULL OR name_russian IS NOT NULL OR name_hindi IS NOT NULL;
        """
    )

    op.execute(
        """
        UPDATE sub_sector
        SET name_translations = COALESCE(
            name_translations,
            '{}'::jsonb
        ) || jsonb_strip_nulls(
            jsonb_build_object(
                'fr', CASE WHEN name_french IS NOT NULL AND (name_translations IS NULL OR name_translations->>'fr' IS NULL) THEN name_french ELSE NULL END,
                'es', CASE WHEN name_spanish IS NOT NULL AND (name_translations IS NULL OR name_translations->>'es' IS NULL) THEN name_spanish ELSE NULL END,
                'ar', CASE WHEN name_arabic IS NOT NULL AND (name_translations IS NULL OR name_translations->>'ar' IS NULL) THEN name_arabic ELSE NULL END,
                'zh', CASE WHEN name_chinese IS NOT NULL AND (name_translations IS NULL OR name_translations->>'zh' IS NULL) THEN name_chinese ELSE NULL END,
                'ru', CASE WHEN name_russian IS NOT NULL AND (name_translations IS NULL OR name_translations->>'ru' IS NULL) THEN name_russian ELSE NULL END,
                'hi', CASE WHEN name_hindi IS NOT NULL AND (name_translations IS NULL OR name_translations->>'hi' IS NULL) THEN name_hindi ELSE NULL END
            )
        )
        WHERE name_french IS NOT NULL OR name_spanish IS NOT NULL OR name_arabic IS NOT NULL OR
              name_chinese IS NOT NULL OR name_russian IS NOT NULL OR name_hindi IS NOT NULL;
        """
    )

    # Clean up empty JSONB objects
    op.execute(
        """
        UPDATE sector
        SET name_translations = NULL
        WHERE name_translations = '{}'::jsonb;
        """
    )

    op.execute(
        """
        UPDATE sub_sector
        SET name_translations = NULL
        WHERE name_translations = '{}'::jsonb;
        """
    )

    # Now drop the legacy columns from sector table
    op.drop_column('sector', 'name_french')
    op.drop_column('sector', 'name_spanish')
    op.drop_column('sector', 'name_arabic')
    op.drop_column('sector', 'name_chinese')
    op.drop_column('sector', 'name_russian')
    op.drop_column('sector', 'name_hindi')

    # Drop the legacy columns from sub_sector table
    op.drop_column('sub_sector', 'name_french')
    op.drop_column('sub_sector', 'name_spanish')
    op.drop_column('sub_sector', 'name_arabic')
    op.drop_column('sub_sector', 'name_chinese')
    op.drop_column('sub_sector', 'name_russian')
    op.drop_column('sub_sector', 'name_hindi')


def downgrade():
    # Re-add the legacy columns
    op.add_column('sector', sa.Column('name_french', sa.String(length=100), nullable=True))
    op.add_column('sector', sa.Column('name_spanish', sa.String(length=100), nullable=True))
    op.add_column('sector', sa.Column('name_arabic', sa.String(length=100), nullable=True))
    op.add_column('sector', sa.Column('name_chinese', sa.String(length=100), nullable=True))
    op.add_column('sector', sa.Column('name_russian', sa.String(length=100), nullable=True))
    op.add_column('sector', sa.Column('name_hindi', sa.String(length=100), nullable=True))

    op.add_column('sub_sector', sa.Column('name_french', sa.String(length=100), nullable=True))
    op.add_column('sub_sector', sa.Column('name_spanish', sa.String(length=100), nullable=True))
    op.add_column('sub_sector', sa.Column('name_arabic', sa.String(length=100), nullable=True))
    op.add_column('sub_sector', sa.Column('name_chinese', sa.String(length=100), nullable=True))
    op.add_column('sub_sector', sa.Column('name_russian', sa.String(length=100), nullable=True))
    op.add_column('sub_sector', sa.Column('name_hindi', sa.String(length=100), nullable=True))

    # Backfill legacy columns from JSONB (reverse migration)
    op.execute(
        """
        UPDATE sector
        SET name_french = name_translations->>'fr',
            name_spanish = name_translations->>'es',
            name_arabic = name_translations->>'ar',
            name_chinese = name_translations->>'zh',
            name_russian = name_translations->>'ru',
            name_hindi = name_translations->>'hi'
        WHERE name_translations IS NOT NULL;
        """
    )

    op.execute(
        """
        UPDATE sub_sector
        SET name_french = name_translations->>'fr',
            name_spanish = name_translations->>'es',
            name_arabic = name_translations->>'ar',
            name_chinese = name_translations->>'zh',
            name_russian = name_translations->>'ru',
            name_hindi = name_translations->>'hi'
        WHERE name_translations IS NOT NULL;
        """
    )
