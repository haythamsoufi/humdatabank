"""Allow AI opinions for virtual missing rows

Revision ID: b6c8a1f3d2e4
Revises: 1680ccc4c512
Create Date: 2026-02-15

Extend ai_formdata_validation so we can persist opinions for non-reported (virtual) items
keyed by (assignment_entity_status_id, form_item_id) without creating placeholder form_data rows.
"""

from alembic import op
import sqlalchemy as sa


revision = "b6c8a1f3d2e4"
down_revision = "1680ccc4c512"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Allow NULL form_data_id (needed for virtual targets)
    op.alter_column(
        "ai_formdata_validation",
        "form_data_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 2) Add virtual-target columns
    op.add_column(
        "ai_formdata_validation",
        sa.Column("assignment_entity_status_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_formdata_validation",
        sa.Column("form_item_id", sa.Integer(), nullable=True),
    )

    # 3) Foreign keys
    op.create_foreign_key(
        "fk_ai_formdata_validation_assignment_entity_status_id",
        "ai_formdata_validation",
        "assignment_entity_status",
        ["assignment_entity_status_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_ai_formdata_validation_form_item_id",
        "ai_formdata_validation",
        "form_item",
        ["form_item_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 4) Indexes and constraints
    op.create_index(
        "ix_ai_formdata_validation_assignment_entity_status_id",
        "ai_formdata_validation",
        ["assignment_entity_status_id"],
        unique=False,
    )
    op.create_index(
        "ix_ai_formdata_validation_form_item_id",
        "ai_formdata_validation",
        ["form_item_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_ai_formdata_validation_aes_item",
        "ai_formdata_validation",
        ["assignment_entity_status_id", "form_item_id"],
    )
    op.create_check_constraint(
        "ck_ai_formdata_validation_target",
        "ai_formdata_validation",
        "(form_data_id IS NOT NULL) OR (assignment_entity_status_id IS NOT NULL AND form_item_id IS NOT NULL)",
    )


def downgrade():
    op.drop_constraint("ck_ai_formdata_validation_target", "ai_formdata_validation", type_="check")
    op.drop_constraint("uq_ai_formdata_validation_aes_item", "ai_formdata_validation", type_="unique")
    op.drop_index("ix_ai_formdata_validation_form_item_id", table_name="ai_formdata_validation")
    op.drop_index("ix_ai_formdata_validation_assignment_entity_status_id", table_name="ai_formdata_validation")
    op.drop_constraint(
        "fk_ai_formdata_validation_form_item_id",
        "ai_formdata_validation",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_ai_formdata_validation_assignment_entity_status_id",
        "ai_formdata_validation",
        type_="foreignkey",
    )
    op.drop_column("ai_formdata_validation", "form_item_id")
    op.drop_column("ai_formdata_validation", "assignment_entity_status_id")

    # WARNING: downgrading to non-null requires there be no rows with NULL form_data_id.
    op.alter_column(
        "ai_formdata_validation",
        "form_data_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

