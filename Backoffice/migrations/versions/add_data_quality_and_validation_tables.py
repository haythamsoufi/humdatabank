"""Add data quality template fields and validation question tables.

Revision ID: add_data_quality_validation
Revises: rename_requires_delegation_review
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "add_data_quality_validation"
down_revision = "rename_requires_delegation_review"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("form_template_version", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("enable_data_quality", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("data_quality_methodology", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("validation_rule_pack", sa.String(length=64), nullable=True))

    op.create_table(
        "validation_dispatch_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("period_name", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("channels", sa.JSON(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("intro_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["form_template.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "validation_question",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("period_name", sa.String(length=64), nullable=False),
        sa.Column("assigned_form_id", sa.Integer(), nullable=True),
        sa.Column("assignment_entity_status_id", sa.Integer(), nullable=True),
        sa.Column("form_item_id", sa.Integer(), nullable=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("definition_text", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("asked_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.Column("answered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("dispatch_batch_id", sa.Integer(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivery_channels", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["answered_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_form_id"], ["assigned_form.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignment_entity_status_id"], ["assignment_entity_status.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dispatch_batch_id"], ["validation_dispatch_batch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["form_item_id"], ["form_item.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["form_template.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_question_template_id", "validation_question", ["template_id"])
    op.create_index("ix_validation_question_entity", "validation_question", ["entity_type", "entity_id"])
    op.create_index("ix_validation_question_period", "validation_question", ["period_name"])
    op.create_index("ix_validation_question_status", "validation_question", ["status"])
    op.create_index("ix_validation_question_rule_code", "validation_question", ["rule_code"])
    op.create_index(
        "ix_validation_question_scope",
        "validation_question",
        ["template_id", "entity_type", "entity_id", "period_name", "rule_code", "form_item_id"],
    )

    op.create_table(
        "validation_threshold",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("kpi_code", sa.String(length=64), nullable=False),
        sa.Column("threshold_fraction", sa.Float(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", "kpi_code", "template_id", name="uq_validation_threshold_country_kpi"),
    )

    op.create_table(
        "validation_kpi_check_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kpi_code", sa.String(length=64), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kpi_code", "template_id", name="uq_validation_kpi_check_type"),
    )

    op.create_table(
        "validation_question_template",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_code", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("needs_ending_value", sa.Boolean(), nullable=False),
        sa.Column("rule_pack", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_code", "language", "rule_pack", name="uq_validation_question_template"),
    )

    op.create_table(
        "country_year_reference",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("world_bank_population", sa.BigInteger(), nullable=True),
        sa.Column("awsd_deaths_on_duty", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", "year", name="uq_country_year_reference"),
    )

    op.create_table(
        "country_attribute",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("grbmp", sa.String(length=255), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["country_id"], ["country.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id"),
    )

    # Enable FDRS template 21 QoD on published version when present
    op.execute(
        """
        UPDATE form_template_version ftv
        SET enable_data_quality = TRUE,
            data_quality_methodology = 'fdrs_v1',
            validation_rule_pack = 'fdrs_matrix_v1'
        FROM form_template ft
        WHERE ft.id = 21
          AND ft.published_version_id = ftv.id
        """
    )

    # Seed EN validation question templates for FDRS matrix v1 (18 rules)
    rule_pack = "fdrs_matrix_v1"
    templates = [
        ("volunteer_deaths", "One or more volunteer deaths on duty were reported.", False),
        ("staff_deaths", "One or more staff deaths on duty were reported.", False),
        ("non_zero", "This indicator is reported as zero. Please confirm this is correct.", False),
        ("past_year_threshold", "This value changed by more than the allowed threshold compared to the prior year:", True),
        ("past_3years_avg", "This value changed by more than the allowed threshold compared to the three-year average:", True),
        ("not_reported", "This indicator was reported last year but is missing this year.", False),
        ("branches_higher_units", "The number of branches exceeds the number of local units (local units:", True),
        ("higher_health", "A health sub-indicator exceeds the total people reached in health.", False),
        ("higher_than_pop", "People reached exceeds the country population (population:", True),
        ("significant_pop", "People reached is a significant share of the country population (ratio:", True),
        ("typeofprograms", "Programme type indicators were reported but disaster/emergency programme reach is zero:", True),
        ("grbmp", "GRBMP applies to this country but migration reach is not reported.", False),
        ("awsd_check", "Reported on-duty deaths do not match the AWSD reference figure (AWSD:", True),
        ("fiscal_year", "Fiscal year length exceeds 365 days (days:", True),
        ("missing_ar", "Annual Report document is missing.", False),
        ("missing_sp", "Audited Financial Statement document is missing.", False),
        ("similar_ind_reach", "Indigenous reach values vary significantly across programmes.", False),
    ]
    conn = op.get_bind()
    for code, text, needs_suffix in templates:
        conn.execute(
            sa.text(
                """
                INSERT INTO validation_question_template
                    (question_code, language, template_text, needs_ending_value, rule_pack)
                VALUES (:code, 'en', :text, :needs_suffix, :rule_pack)
                ON CONFLICT (question_code, language, rule_pack) DO NOTHING
                """
            ),
            {"code": code, "text": text, "needs_suffix": needs_suffix, "rule_pack": rule_pack},
        )


def downgrade():
    op.drop_table("country_attribute")
    op.drop_table("country_year_reference")
    op.drop_table("validation_question_template")
    op.drop_table("validation_kpi_check_type")
    op.drop_table("validation_threshold")
    op.drop_index("ix_validation_question_scope", table_name="validation_question")
    op.drop_index("ix_validation_question_rule_code", table_name="validation_question")
    op.drop_index("ix_validation_question_status", table_name="validation_question")
    op.drop_index("ix_validation_question_period", table_name="validation_question")
    op.drop_index("ix_validation_question_entity", table_name="validation_question")
    op.drop_index("ix_validation_question_template_id", table_name="validation_question")
    op.drop_table("validation_question")
    op.drop_table("validation_dispatch_batch")

    with op.batch_alter_table("form_template_version", schema=None) as batch_op:
        batch_op.drop_column("validation_rule_pack")
        batch_op.drop_column("data_quality_methodology")
        batch_op.drop_column("enable_data_quality")
