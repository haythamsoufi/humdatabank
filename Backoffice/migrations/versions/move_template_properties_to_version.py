"""Move template properties from form_template to form_template_version

Revision ID: move_template_props_to_version
Revises: add_api_key_management
Create Date: 2025-01-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'move_template_props_to_version'
down_revision = 'add_api_key_management'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    # Step 1: Copy data from form_template to form_template_version for existing versions
    # Only update versions where the field is NULL (to preserve any existing version-specific values)
    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET description = t.description
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.description IS NULL
        AND t.description IS NOT NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET template_type = t.template_type
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.template_type IS NULL
        AND t.template_type IS NOT NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET add_to_self_report = t.add_to_self_report
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.add_to_self_report IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET display_order_visible = t.display_order_visible
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.display_order_visible IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET is_paginated = t.is_paginated
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.is_paginated IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET enable_export_pdf = t.enable_export_pdf
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.enable_export_pdf IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET enable_export_excel = t.enable_export_excel
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.enable_export_excel IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version v
        SET enable_import_excel = t.enable_import_excel
        FROM form_template t
        WHERE v.template_id = t.id
        AND v.enable_import_excel IS NULL
    """))

    # Step 2: Set defaults for any remaining NULL values in form_template_version
    # (in case there are versions without a corresponding template or templates with NULL values)
    connection.execute(sa.text("""
        UPDATE form_template_version
        SET template_type = 'operational'
        WHERE template_type IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET add_to_self_report = false
        WHERE add_to_self_report IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET display_order_visible = true
        WHERE display_order_visible IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET is_paginated = false
        WHERE is_paginated IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET enable_export_pdf = true
        WHERE enable_export_pdf IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET enable_export_excel = true
        WHERE enable_export_excel IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_template_version
        SET enable_import_excel = true
        WHERE enable_import_excel IS NULL
    """))

    # Step 3: Make fields non-nullable in form_template_version
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.alter_column('template_type',
                            existing_type=sa.String(length=50),
                            nullable=False,
                            server_default='operational')
        batch_op.alter_column('add_to_self_report',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='false')
        batch_op.alter_column('display_order_visible',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('is_paginated',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='false')
        batch_op.alter_column('enable_export_pdf',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('enable_export_excel',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('enable_import_excel',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')

    # Step 4: Drop indexes from form_template that reference the columns we're removing
    # Check if indexes exist before dropping
    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_template'
            AND indexname = 'ix_form_template_type'
        )
    """)).scalar()

    if index_exists:
        op.drop_index('ix_form_template_type', table_name='form_template')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_template'
            AND indexname = 'ix_form_template_is_paginated'
        )
    """)).scalar()

    if index_exists:
        op.drop_index('ix_form_template_is_paginated', table_name='form_template')

    # Step 5: Drop columns from form_template
    # Check if columns exist before dropping
    columns_to_drop = []
    existing_columns = connection.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'form_template'
        AND column_name IN ('description', 'template_type', 'add_to_self_report',
                           'display_order_visible', 'is_paginated', 'enable_export_pdf',
                           'enable_export_excel', 'enable_import_excel')
    """)).fetchall()

    existing_column_names = [row[0] for row in existing_columns]

    if 'description' in existing_column_names:
        op.drop_column('form_template', 'description')
    if 'template_type' in existing_column_names:
        op.drop_column('form_template', 'template_type')
    if 'add_to_self_report' in existing_column_names:
        op.drop_column('form_template', 'add_to_self_report')
    if 'display_order_visible' in existing_column_names:
        op.drop_column('form_template', 'display_order_visible')
    if 'is_paginated' in existing_column_names:
        op.drop_column('form_template', 'is_paginated')
    if 'enable_export_pdf' in existing_column_names:
        op.drop_column('form_template', 'enable_export_pdf')
    if 'enable_export_excel' in existing_column_names:
        op.drop_column('form_template', 'enable_export_excel')
    if 'enable_import_excel' in existing_column_names:
        op.drop_column('form_template', 'enable_import_excel')

    # Step 6: Update form_page, form_section, and form_item to use version_id as primary reference
    # First, populate version_id for records that don't have it (use first version of template)
    connection.execute(sa.text("""
        UPDATE form_page p
        SET version_id = (
            SELECT v.id
            FROM form_template_version v
            WHERE v.template_id = p.template_id
            ORDER BY v.created_at ASC
            LIMIT 1
        )
        WHERE p.version_id IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_section s
        SET version_id = (
            SELECT v.id
            FROM form_template_version v
            WHERE v.template_id = s.template_id
            ORDER BY v.created_at ASC
            LIMIT 1
        )
        WHERE s.version_id IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_item i
        SET version_id = (
            SELECT v.id
            FROM form_template_version v
            WHERE v.template_id = i.template_id
            ORDER BY v.created_at ASC
            LIMIT 1
        )
        WHERE i.version_id IS NULL
    """))

    # Step 7: Make version_id required and template_id nullable
    with op.batch_alter_table('form_page', schema=None) as batch_op:
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    with op.batch_alter_table('form_section', schema=None) as batch_op:
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    with op.batch_alter_table('form_item', schema=None) as batch_op:
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    # Step 8: Update indexes - drop old ones and create new ones
    # Drop old indexes
    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_page'
            AND indexname = 'ix_form_page_template_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_page_template_order', table_name='form_page')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_section'
            AND indexname = 'ix_form_section_template_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_section_template_order', table_name='form_section')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_item'
            AND indexname = 'ix_form_item_template_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_item_template_order', table_name='form_item')

    # Create new indexes with version_id
    op.create_index('ix_form_page_version_order', 'form_page', ['version_id', 'order'], unique=False)
    op.create_index('ix_form_section_version_order', 'form_section', ['version_id', 'order'], unique=False)
    op.create_index('ix_form_item_version_order', 'form_item', ['version_id', 'order'], unique=False)

    # Create template_id indexes for backward compatibility queries
    op.create_index('ix_form_page_template', 'form_page', ['template_id'], unique=False)
    op.create_index('ix_form_section_template', 'form_section', ['template_id'], unique=False)
    op.create_index('ix_form_item_template', 'form_item', ['template_id'], unique=False)


def downgrade():
    connection = op.get_bind()

    # Step 1: Add columns back to form_template
    op.add_column('form_template', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('form_template', sa.Column('template_type', sa.String(length=50), nullable=True))
    op.add_column('form_template', sa.Column('add_to_self_report', sa.Boolean(), nullable=True))
    op.add_column('form_template', sa.Column('display_order_visible', sa.Boolean(), nullable=True))
    op.add_column('form_template', sa.Column('is_paginated', sa.Boolean(), nullable=True))
    op.add_column('form_template', sa.Column('enable_export_pdf', sa.Boolean(), nullable=True))
    op.add_column('form_template', sa.Column('enable_export_excel', sa.Boolean(), nullable=True))
    op.add_column('form_template', sa.Column('enable_import_excel', sa.Boolean(), nullable=True))

    # Step 2: Copy data from published version (or first version) back to template
    connection.execute(sa.text("""
        UPDATE form_template t
        SET description = (
            SELECT COALESCE(
                (SELECT v.description FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.description FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1)
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET template_type = (
            SELECT COALESCE(
                (SELECT v.template_type FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.template_type FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                'operational'
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET add_to_self_report = (
            SELECT COALESCE(
                (SELECT v.add_to_self_report FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.add_to_self_report FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                false
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET display_order_visible = (
            SELECT COALESCE(
                (SELECT v.display_order_visible FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.display_order_visible FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                true
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET is_paginated = (
            SELECT COALESCE(
                (SELECT v.is_paginated FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.is_paginated FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                false
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET enable_export_pdf = (
            SELECT COALESCE(
                (SELECT v.enable_export_pdf FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.enable_export_pdf FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                true
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET enable_export_excel = (
            SELECT COALESCE(
                (SELECT v.enable_export_excel FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.enable_export_excel FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                true
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET enable_import_excel = (
            SELECT COALESCE(
                (SELECT v.enable_import_excel FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.enable_import_excel FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                true
            )
        )
    """))

    # Step 3: Set NOT NULL constraints and defaults on form_template
    with op.batch_alter_table('form_template', schema=None) as batch_op:
        batch_op.alter_column('template_type',
                            existing_type=sa.String(length=50),
                            nullable=False,
                            server_default='operational')
        batch_op.alter_column('add_to_self_report',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='false')
        batch_op.alter_column('display_order_visible',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('is_paginated',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='false')
        batch_op.alter_column('enable_export_pdf',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('enable_export_excel',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')
        batch_op.alter_column('enable_import_excel',
                            existing_type=sa.Boolean(),
                            nullable=False,
                            server_default='true')

    # Step 4: Recreate indexes on form_template
    op.create_index('ix_form_template_type', 'form_template', ['template_type'], unique=False)
    op.create_index('ix_form_template_is_paginated', 'form_template', ['is_paginated'], unique=False)

    # Step 5: Make fields nullable again in form_template_version
    with op.batch_alter_table('form_template_version', schema=None) as batch_op:
        batch_op.alter_column('template_type',
                            existing_type=sa.String(length=50),
                            nullable=True)
        batch_op.alter_column('add_to_self_report',
                            existing_type=sa.Boolean(),
                            nullable=True)
        batch_op.alter_column('display_order_visible',
                            existing_type=sa.Boolean(),
                            nullable=True)
        batch_op.alter_column('is_paginated',
                            existing_type=sa.Boolean(),
                            nullable=True)
        batch_op.alter_column('enable_export_pdf',
                            existing_type=sa.Boolean(),
                            nullable=True)
        batch_op.alter_column('enable_export_excel',
                            existing_type=sa.Boolean(),
                            nullable=True)
        batch_op.alter_column('enable_import_excel',
                            existing_type=sa.Boolean(),
                            nullable=True)

    # Step 6: Revert form_page, form_section, and form_item to use template_id as primary
    # Drop new indexes
    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_page'
            AND indexname = 'ix_form_page_version_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_page_version_order', table_name='form_page')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_section'
            AND indexname = 'ix_form_section_version_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_section_version_order', table_name='form_section')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_item'
            AND indexname = 'ix_form_item_version_order'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_item_version_order', table_name='form_item')

    # Drop template_id indexes
    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_page'
            AND indexname = 'ix_form_page_template'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_page_template', table_name='form_page')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_section'
            AND indexname = 'ix_form_section_template'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_section_template', table_name='form_section')

    index_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'form_item'
            AND indexname = 'ix_form_item_template'
        )
    """)).scalar()
    if index_exists:
        op.drop_index('ix_form_item_template', table_name='form_item')

    # Populate template_id from version_id for records where template_id is NULL
    connection.execute(sa.text("""
        UPDATE form_page p
        SET template_id = (
            SELECT v.template_id
            FROM form_template_version v
            WHERE v.id = p.version_id
        )
        WHERE p.template_id IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_section s
        SET template_id = (
            SELECT v.template_id
            FROM form_template_version v
            WHERE v.id = s.version_id
        )
        WHERE s.template_id IS NULL
    """))

    connection.execute(sa.text("""
        UPDATE form_item i
        SET template_id = (
            SELECT v.template_id
            FROM form_template_version v
            WHERE v.id = i.version_id
        )
        WHERE i.template_id IS NULL
    """))

    # Make template_id required and version_id nullable
    with op.batch_alter_table('form_page', schema=None) as batch_op:
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    with op.batch_alter_table('form_section', schema=None) as batch_op:
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    with op.batch_alter_table('form_item', schema=None) as batch_op:
        batch_op.alter_column('template_id',
                            existing_type=sa.Integer(),
                            nullable=False)
        batch_op.alter_column('version_id',
                            existing_type=sa.Integer(),
                            nullable=True)

    # Recreate old indexes
    op.create_index('ix_form_page_template_order', 'form_page', ['template_id', 'order'], unique=False)
    op.create_index('ix_form_section_template_order', 'form_section', ['template_id', 'order'], unique=False)
    op.create_index('ix_form_item_template_order', 'form_item', ['template_id', 'order'], unique=False)
    op.create_index('ix_form_page_version', 'form_page', ['version_id'], unique=False)
    op.create_index('ix_form_section_version', 'form_section', ['version_id'], unique=False)
    op.create_index('ix_form_item_version', 'form_item', ['version_id'], unique=False)
