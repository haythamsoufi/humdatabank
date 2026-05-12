"""Remove profile picture fields from user

Revision ID: remove_profile_picture_fields
Revises: set_ai_validation_default_false
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "remove_profile_picture_fields"
down_revision = "set_ai_validation_default_false"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("use_profile_picture")
        batch_op.drop_column("profile_picture_url")


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("profile_picture_url", sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column(
                "use_profile_picture",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            )
        )
