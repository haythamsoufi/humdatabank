"""Add Decision Support tables (versioned config, flag state, feedback, rule runs).

Revision ID: add_ifrc_decision_support
Revises: add_project_portfolio
Create Date: 2026-11-04

Decision definitions and rules ship as code defaults. Publishing a change writes a
new immutable version here, so thresholds change without a deployment and earlier
versions stay available for audit. Flags are recalculated on demand; only their
review state, feedback and rule execution history are stored.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "add_ifrc_decision_support"
down_revision = "add_project_portfolio"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ifrc_decision_config_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("kind", "key", "version", name="uq_ifrc_decision_config_version"),
    )
    op.create_index("ix_ifrc_decision_config_kind_key", "ifrc_decision_config_version", ["kind", "key"])

    op.create_table(
        "ifrc_decision_flag_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flag_key", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("rule_id", sa.String(length=80), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("flag_key", name="uq_ifrc_decision_flag_state_key"),
    )

    op.create_table(
        "ifrc_decision_flag_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flag_key", sa.String(length=64), nullable=False),
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("rule_id", sa.String(length=80), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ifrc_decision_flag_feedback_flag_key", "ifrc_decision_flag_feedback", ["flag_key"])

    op.create_table(
        "ifrc_decision_rule_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.String(length=40), nullable=False),
        sa.Column("rule_id", sa.String(length=80), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("entities_evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flags_raised", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ran_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ran_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["ran_by_user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ifrc_decision_rule_run_ran_at", "ifrc_decision_rule_run", ["ran_at"])


def downgrade():
    op.drop_index("ix_ifrc_decision_rule_run_ran_at", table_name="ifrc_decision_rule_run")
    op.drop_table("ifrc_decision_rule_run")
    op.drop_index("ix_ifrc_decision_flag_feedback_flag_key", table_name="ifrc_decision_flag_feedback")
    op.drop_table("ifrc_decision_flag_feedback")
    op.drop_table("ifrc_decision_flag_state")
    op.drop_index("ix_ifrc_decision_config_kind_key", table_name="ifrc_decision_config_version")
    op.drop_table("ifrc_decision_config_version")
