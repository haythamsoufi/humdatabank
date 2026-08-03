"""Add report_definition and report_run tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_report_definition_table"
down_revision = "add_usl_perf_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_definition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "definition_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "scope_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
    )
    op.create_index("ix_report_definition_slug", "report_definition", ["slug"], unique=True)
    op.create_index("ix_report_definition_status", "report_definition", ["status"])
    op.create_index("ix_report_definition_owner_user_id", "report_definition", ["owner_user_id"])
    op.create_index("ix_report_definition_owner_status", "report_definition", ["owner_user_id", "status"])

    op.create_table(
        "report_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("report_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("build_stage", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("triggered_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_report_run_report_id", "report_run", ["report_id"])
    op.create_index("ix_report_run_status", "report_run", ["status"])


def downgrade():
    op.drop_index("ix_report_run_status", table_name="report_run")
    op.drop_index("ix_report_run_report_id", table_name="report_run")
    op.drop_table("report_run")
    op.drop_index("ix_report_definition_owner_status", table_name="report_definition")
    op.drop_index("ix_report_definition_owner_user_id", table_name="report_definition")
    op.drop_index("ix_report_definition_status", table_name="report_definition")
    op.drop_index("ix_report_definition_slug", table_name="report_definition")
    op.drop_table("report_definition")
