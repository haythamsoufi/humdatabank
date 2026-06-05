"""
Validation questions and reference data for template-agnostic data quality checks.
"""

from __future__ import annotations

from app.extensions import db
from app.utils.datetime_helpers import utcnow


class ValidationQuestion(db.Model):
    __tablename__ = "validation_question"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("form_template.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = db.Column(db.String(32), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    period_name = db.Column(db.String(64), nullable=False, index=True)

    assigned_form_id = db.Column(db.Integer, db.ForeignKey("assigned_form.id", ondelete="SET NULL"), nullable=True)
    assignment_entity_status_id = db.Column(
        db.Integer, db.ForeignKey("assignment_entity_status.id", ondelete="SET NULL"), nullable=True, index=True
    )
    form_item_id = db.Column(db.Integer, db.ForeignKey("form_item.id", ondelete="SET NULL"), nullable=True, index=True)

    rule_code = db.Column(db.String(64), nullable=False, index=True)
    question_text = db.Column(db.Text, nullable=False)
    definition_text = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(16), nullable=False, default="warning")
    status = db.Column(db.String(16), nullable=False, default="open", index=True)
    context = db.Column(db.JSON, nullable=True)
    language = db.Column(db.String(8), nullable=False, default="en")

    source = db.Column(db.String(16), nullable=False, default="auto")
    asked_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    answered_at = db.Column(db.DateTime, nullable=True)
    answered_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    answer_text = db.Column(db.Text, nullable=True)

    dispatch_batch_id = db.Column(
        db.Integer, db.ForeignKey("validation_dispatch_batch.id", ondelete="SET NULL"), nullable=True
    )
    sent_at = db.Column(db.DateTime, nullable=True)
    delivery_channels = db.Column(db.JSON, nullable=True)

    template = db.relationship("FormTemplate", foreign_keys=[template_id])
    form_item = db.relationship("FormItem", foreign_keys=[form_item_id])
    answered_by_user = db.relationship("User", foreign_keys=[answered_by_user_id])

    __table_args__ = (
        db.Index(
            "ix_validation_question_scope",
            "template_id",
            "entity_type",
            "entity_id",
            "period_name",
            "rule_code",
            "form_item_id",
        ),
    )


class ValidationDispatchBatch(db.Model):
    __tablename__ = "validation_dispatch_batch"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("form_template.id", ondelete="CASCADE"), nullable=False)
    period_name = db.Column(db.String(64), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    channels = db.Column(db.JSON, nullable=True)
    scope = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="draft")
    summary = db.Column(db.JSON, nullable=True)
    intro_message = db.Column(db.Text, nullable=True)

    created_by_user = db.relationship("User", foreign_keys=[created_by_user_id])


class ValidationThreshold(db.Model):
    __tablename__ = "validation_threshold"

    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id", ondelete="CASCADE"), nullable=False, index=True)
    kpi_code = db.Column(db.String(64), nullable=False, index=True)
    threshold_fraction = db.Column(db.Float, nullable=False)
    template_id = db.Column(db.Integer, nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("country_id", "kpi_code", "template_id", name="uq_validation_threshold_country_kpi"),
    )


class ValidationKpiCheckType(db.Model):
    __tablename__ = "validation_kpi_check_type"

    id = db.Column(db.Integer, primary_key=True)
    kpi_code = db.Column(db.String(64), nullable=False, index=True)
    check_type = db.Column(db.String(64), nullable=False)
    template_id = db.Column(db.Integer, nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("kpi_code", "template_id", name="uq_validation_kpi_check_type"),
    )


class ValidationQuestionTemplate(db.Model):
    __tablename__ = "validation_question_template"

    id = db.Column(db.Integer, primary_key=True)
    question_code = db.Column(db.String(64), nullable=False, index=True)
    language = db.Column(db.String(8), nullable=False, default="en")
    template_text = db.Column(db.Text, nullable=False)
    needs_ending_value = db.Column(db.Boolean, nullable=False, default=False)
    rule_pack = db.Column(db.String(64), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("question_code", "language", "rule_pack", name="uq_validation_question_template"),
    )


class CountryYearReference(db.Model):
    __tablename__ = "country_year_reference"

    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id", ondelete="CASCADE"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    world_bank_population = db.Column(db.BigInteger, nullable=True)
    awsd_deaths_on_duty = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("country_id", "year", name="uq_country_year_reference"),
    )


class CountryAttribute(db.Model):
    __tablename__ = "country_attribute"

    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("country.id", ondelete="CASCADE"), nullable=False, unique=True)
    grbmp = db.Column(db.String(255), nullable=True)
    extra = db.Column(db.JSON, nullable=True)
