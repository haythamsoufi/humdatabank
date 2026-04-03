"""Rename form_item.item_id to id

Revision ID: rename_form_item_id
Revises: add_performance_indexes
Create Date: 2025-01-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rename_form_item_id'
down_revision = 'add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    # Get the connection to query constraint names
    conn = op.get_bind()

    # Function to get foreign key constraint name for a table and column
    def get_fk_constraint_name(table_name, column_name, referenced_table, referenced_column):
        result = conn.execute(sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = :table_name
                AND kcu.column_name = :column_name
                AND ccu.table_name = :ref_table
                AND ccu.column_name = :ref_column
        """), {
            'table_name': table_name,
            'column_name': column_name,
            'ref_table': referenced_table,
            'ref_column': referenced_column
        })
        row = result.fetchone()
        return row[0] if row else None

    # Get and drop foreign key constraints
    fk_constraints = [
        ('form_data', 'form_item_id', 'form_item', 'item_id'),
        ('repeat_group_data', 'form_item_id', 'form_item', 'item_id'),
        ('submitted_document', 'form_item_id', 'form_item', 'item_id'),
    ]

    constraint_names = {}
    for table, col, ref_table, ref_col in fk_constraints:
        constraint_name = get_fk_constraint_name(table, col, ref_table, ref_col)
        if constraint_name:
            constraint_names[(table, col)] = constraint_name
            op.drop_constraint(constraint_name, table, type_='foreignkey')

    # Rename the column from item_id to id
    op.alter_column('form_item', 'item_id', new_column_name='id')

    # Recreate foreign key constraints to reference form_item.id
    # Use the same constraint names if they were found, otherwise let PostgreSQL auto-generate
    for table, col, ref_table, ref_col in fk_constraints:
        constraint_name = constraint_names.get((table, col))
        if constraint_name:
            op.create_foreign_key(
                constraint_name,
                table, ref_table,
                [col], ['id']
            )
        else:
            # If constraint name wasn't found, let PostgreSQL auto-generate
            op.create_foreign_key(
                None,  # Let PostgreSQL auto-generate the name
                table, ref_table,
                [col], ['id']
            )


def downgrade():
    # Get the connection to query constraint names
    conn = op.get_bind()

    # Function to get foreign key constraint name for a table and column
    def get_fk_constraint_name(table_name, column_name, referenced_table, referenced_column):
        result = conn.execute(sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = :table_name
                AND kcu.column_name = :column_name
                AND ccu.table_name = :ref_table
                AND ccu.column_name = :ref_column
        """), {
            'table_name': table_name,
            'column_name': column_name,
            'ref_table': referenced_table,
            'ref_column': referenced_column
        })
        row = result.fetchone()
        return row[0] if row else None

    # Get and drop foreign key constraints (now referencing 'id')
    fk_constraints = [
        ('form_data', 'form_item_id', 'form_item', 'id'),
        ('repeat_group_data', 'form_item_id', 'form_item', 'id'),
        ('submitted_document', 'form_item_id', 'form_item', 'id'),
    ]

    constraint_names = {}
    for table, col, ref_table, ref_col in fk_constraints:
        constraint_name = get_fk_constraint_name(table, col, ref_table, ref_col)
        if constraint_name:
            constraint_names[(table, col)] = constraint_name
            op.drop_constraint(constraint_name, table, type_='foreignkey')

    # Rename the column back from id to item_id
    op.alter_column('form_item', 'id', new_column_name='item_id')

    # Recreate foreign key constraints to reference form_item.item_id
    for table, col, ref_table, ref_col in fk_constraints:
        constraint_name = constraint_names.get((table, col))
        if constraint_name:
            op.create_foreign_key(
                constraint_name,
                table, 'form_item',
                [col], ['item_id']
            )
        else:
            # If constraint name wasn't found, let PostgreSQL auto-generate
            op.create_foreign_key(
                None,  # Let PostgreSQL auto-generate the name
                table, 'form_item',
                [col], ['item_id']
            )
