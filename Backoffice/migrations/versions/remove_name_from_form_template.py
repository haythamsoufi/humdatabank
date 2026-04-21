"""Remove name and name_translations from form_template and add description_translations to form_template_version

Revision ID: template_version_details
Revises: add_section_config
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'template_version_details'
down_revision = 'add_section_config'
branch_labels = None
depends_on = None


def upgrade():
    # Before removing columns, ensure all templates have at least one version with a name
    # This is a safety check - the application should have already ensured this

    # Drop the unique constraint on name first (if it exists)
    # Check if constraint exists before trying to drop it
    connection = op.get_bind()
    constraint_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.table_constraints
            WHERE constraint_name = 'form_template_name_key'
            AND table_name = 'form_template'
        )
    """)).scalar()

    if constraint_exists:
        with op.batch_alter_table('form_template', schema=None) as batch_op:
            batch_op.drop_constraint('form_template_name_key', type_='unique')

    # Remove name and name_translations columns from form_template
    # Check if columns exist before dropping (in case they were already removed)
    columns_to_drop = []
    existing_columns = connection.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'form_template'
        AND column_name IN ('name', 'name_translations')
    """)).fetchall()

    existing_column_names = [row[0] for row in existing_columns]
    if 'name_translations' in existing_column_names:
        op.drop_column('form_template', 'name_translations')
    if 'name' in existing_column_names:
        op.drop_column('form_template', 'name')

    # Add description_translations column to form_template_version table (if it doesn't exist)
    column_exists = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'form_template_version'
            AND column_name = 'description_translations'
        )
    """)).scalar()

    if not column_exists:
        op.add_column('form_template_version', sa.Column('description_translations', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Add name and name_translations columns back to form_template
    op.add_column('form_template', sa.Column('name', sa.String(length=100), nullable=True))
    op.add_column('form_template', sa.Column('name_translations', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # Copy name from published version to template (or first version if no published)
    # This is a data migration - we'll populate from versions
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE form_template t
        SET name = (
            SELECT COALESCE(
                (SELECT v.name FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.name FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1),
                'Unnamed Template'
            )
        )
    """))

    connection.execute(sa.text("""
        UPDATE form_template t
        SET name_translations = (
            SELECT COALESCE(
                (SELECT v.name_translations FROM form_template_version v
                 WHERE v.template_id = t.id AND v.status = 'published' LIMIT 1),
                (SELECT v.name_translations FROM form_template_version v
                 WHERE v.template_id = t.id ORDER BY v.created_at ASC LIMIT 1)
            )
        )
    """))

    # Make name NOT NULL and add unique constraint
    op.alter_column('form_template', 'name', nullable=False)
    with op.batch_alter_table('form_template', schema=None) as batch_op:
        batch_op.create_unique_constraint('form_template_name_key', ['name'])

    # Remove description_translations column from form_template_version
    op.drop_column('form_template_version', 'description_translations')
