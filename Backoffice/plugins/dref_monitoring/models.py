"""Tables for DREF operational monitoring. Prefix ``dref_mon_``."""

from __future__ import annotations

from sqlalchemy import JSON, true
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.common.datetime_helpers import utcnow

_JSON = JSON().with_variant(JSONB, "postgresql")


class DrefOperation(db.Model):
    __tablename__ = "dref_mon_operation"

    id = db.Column(db.Integer, primary_key=True)
    appeal_code = db.Column(db.String(32), nullable=False, unique=True)
    go_appeal_id = db.Column(db.Integer, nullable=True)
    disaster_name = db.Column(db.String(255), nullable=False, default="")
    pillar = db.Column(db.String(32), nullable=False, default="")
    appeal_type = db.Column(db.String(32), nullable=False, default="")
    allocation_type = db.Column(db.String(32), nullable=False, default="")
    country_name = db.Column(db.String(120), nullable=False, default="")
    country_iso3 = db.Column(db.String(3), nullable=False, default="")
    country_id = db.Column(db.Integer, db.ForeignKey("country.id", ondelete="SET NULL"), nullable=True)
    hazard = db.Column(db.String(120), nullable=False, default="")
    districts = db.Column(db.Text, nullable=False, default="")
    region = db.Column(db.String(80), nullable=False, default="")
    onset = db.Column(db.String(32), nullable=False, default="")
    crisis_category = db.Column(db.String(32), nullable=False, default="")
    amount_approved = db.Column(db.Numeric(14, 2), nullable=True)
    total_approved = db.Column(db.Numeric(14, 2), nullable=True)
    people_affected = db.Column(db.Integer, nullable=True)
    people_targeted = db.Column(db.Integer, nullable=True)
    date_of_disaster = db.Column(db.Date, nullable=True)
    date_of_approval = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    operation_timeframe_months = db.Column(db.Integer, nullable=True)
    operation_status = db.Column(db.String(16), nullable=False, default="active")
    workflow_status = db.Column(db.String(32), nullable=False, default="stub")
    project_id = db.Column(db.Integer, db.ForeignKey("project.id", ondelete="SET NULL"), nullable=True)
    sign_off_authority = db.Column(db.String(16), nullable=False, default="ns")
    reporting_frequency = db.Column(db.String(16), nullable=False, default="monthly")
    # First day the reporting periods count from. Empty means the operation start date, as for a DREF.
    # An Emergency Appeal that began years ago starts reporting when its plan is confirmed.
    reporting_start = db.Column(db.Date, nullable=True)
    funds_received = db.Column(db.Boolean, nullable=False, default=False)
    funds_received_on = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        db.Index("ix_dref_mon_operation_country", "country_id"),
        db.Index("ix_dref_mon_operation_status", "operation_status", "workflow_status"),
        db.Index("ix_dref_mon_operation_project", "project_id"),
    )


class DrefMember(db.Model):
    __tablename__ = "dref_mon_member"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    tier = db.Column(db.String(16), nullable=False, default="enter")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("operation_id", "user_id", name="uq_dref_mon_member_op_user"),
    )


class DrefBaseline(db.Model):
    """One approved GO stage. The latest stage is the bound NS edits are checked against."""

    __tablename__ = "dref_mon_baseline"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    go_stage_id = db.Column(db.String(64), nullable=False, unique=True)
    stage = db.Column(db.String(64), nullable=False, default="")
    allocation = db.Column(db.String(64), nullable=False, default="")
    amount_approved = db.Column(db.Numeric(14, 2), nullable=True)
    total_approved = db.Column(db.Numeric(14, 2), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    people_targeted = db.Column(db.Integer, nullable=True)
    people_assisted = db.Column(db.Integer, nullable=True)
    sectors = db.Column(_JSON, nullable=False, default=list)
    application = db.Column(_JSON, nullable=True)
    is_latest = db.Column(db.Boolean, nullable=False, default=False)
    synced_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.Index("ix_dref_mon_baseline_operation", "operation_id", "is_latest"),
    )


class DrefPlan(db.Model):
    __tablename__ = "dref_mon_plan"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="draft")
    source = db.Column(db.String(16), nullable=False, default="generated")
    validation_due = db.Column(db.Date, nullable=True)
    validation_reminded_on = db.Column(db.Date, nullable=True)
    validated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    validated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("operation_id", "version", name="uq_dref_mon_plan_version"),
    )


class DrefGroup(db.Model):
    __tablename__ = "dref_mon_group"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("dref_mon_plan.id", ondelete="CASCADE"), nullable=False)
    key = db.Column(db.String(80), nullable=False)
    label = db.Column(db.String(180), nullable=False)
    group_kind = db.Column(db.String(32), nullable=False, default="sector")
    budget_chf = db.Column(db.Numeric(14, 2), nullable=True)
    people_targeted = db.Column(db.Integer, nullable=True)
    bank_sector_id = db.Column(db.Integer, nullable=True)
    unmatched = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)


class DrefActivity(db.Model):
    __tablename__ = "dref_mon_activity"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("dref_mon_group.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="planned")
    percent = db.Column(db.Integer, nullable=True)
    budget_chf = db.Column(db.Numeric(14, 2), nullable=True)
    target = db.Column(db.Numeric(14, 2), nullable=True)
    activity_type = db.Column(db.String(64), nullable=False, default="")
    carried_out_by = db.Column(db.String(64), nullable=False, default="")
    indicator_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "dref_mon_indicator.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_dref_mon_activity_indicator",
        ),
        nullable=True,
    )
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.Index("ix_dref_mon_activity_indicator", "indicator_id"),
    )


class DrefIndicator(db.Model):
    __tablename__ = "dref_mon_indicator"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("dref_mon_activity.id", ondelete="CASCADE"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("dref_mon_group.id", ondelete="CASCADE"), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="process")
    standard_code = db.Column(db.String(64), nullable=True)
    target = db.Column(db.Numeric(14, 2), nullable=True)
    unit = db.Column(db.String(32), nullable=False, default="")
    beneficiary_unit = db.Column(db.String(16), nullable=False, default="none")
    indicator_bank_id = db.Column(db.Integer, nullable=True)
    unmatched = db.Column(db.Boolean, nullable=False, default=False)
    # True when the temporary GO-title adapter supplied indicator_bank_id.
    bank_adapted = db.Column(db.Boolean, nullable=False, default=False)
    # An Emergency Appeal plan lists every emergency indicator of the bank. The team switches off the
    # ones it will not report on before confirming. A switched-off row stays on the plan, out of the form.
    enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=true())


class DrefStandardIndicator(db.Model):
    __tablename__ = "dref_mon_standard_indicator"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), nullable=False, unique=True)
    title = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    unit = db.Column(db.String(32), nullable=False, default="")
    sector_key = db.Column(db.String(80), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class DrefPeriod(db.Model):
    __tablename__ = "dref_mon_period"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="open")
    assigned_form_id = db.Column(
        db.Integer, db.ForeignKey("assigned_form.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint("operation_id", "sequence", name="uq_dref_mon_period_seq"),
        db.Index("ix_dref_mon_period_assignment", "assigned_form_id"),
    )


class DrefReport(db.Model):
    __tablename__ = "dref_mon_report"

    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey("dref_mon_period.id", ondelete="CASCADE"), nullable=False, unique=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="draft")
    expenditure_total = db.Column(db.Numeric(14, 2), nullable=True)
    narrative = db.Column(db.Text, nullable=False, default="")
    submitted_at = db.Column(db.DateTime, nullable=True)
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    validated_at = db.Column(db.DateTime, nullable=True)
    validated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefActivityUpdate(db.Model):
    __tablename__ = "dref_mon_activity_update"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("dref_mon_report.id", ondelete="CASCADE"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("dref_mon_activity.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="planned")
    percent = db.Column(db.Integer, nullable=True)
    people_households = db.Column(db.Integer, nullable=True)
    people_individuals = db.Column(db.Integer, nullable=True)
    disaggregation = db.Column(_JSON, nullable=True)
    disaggregation_na = db.Column(db.Boolean, nullable=False, default=False)
    expenditure = db.Column(db.Numeric(14, 2), nullable=True)
    note = db.Column(db.Text, nullable=False, default="")

    __table_args__ = (
        db.UniqueConstraint("report_id", "activity_id", name="uq_dref_mon_update_activity"),
    )


class DrefIndicatorValue(db.Model):
    __tablename__ = "dref_mon_indicator_value"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("dref_mon_report.id", ondelete="CASCADE"), nullable=False)
    indicator_id = db.Column(db.Integer, db.ForeignKey("dref_mon_indicator.id", ondelete="CASCADE"), nullable=False)
    actual = db.Column(db.Numeric(14, 2), nullable=True)
    note = db.Column(db.Text, nullable=False, default="")

    __table_args__ = (
        db.UniqueConstraint("report_id", "indicator_id", name="uq_dref_mon_value_indicator"),
    )


class DrefProcurement(db.Model):
    __tablename__ = "dref_mon_procurement"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    item = db.Column(db.String(255), nullable=False)
    milestone = db.Column(db.String(32), nullable=False, default="not_started")
    note = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class DrefDateHistory(db.Model):
    __tablename__ = "dref_mon_date_history"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("dref_mon_activity.id", ondelete="CASCADE"), nullable=False)
    field = db.Column(db.String(32), nullable=False)
    old_value = db.Column(db.String(32), nullable=True)
    new_value = db.Column(db.String(32), nullable=True)
    justification = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefChangeRequest(db.Model):
    __tablename__ = "dref_mon_change_request"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("dref_mon_plan.id", ondelete="CASCADE"), nullable=True)
    target_type = db.Column(db.String(16), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    field = db.Column(db.String(32), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    within_bounds = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    justification = db.Column(db.Text, nullable=False, default="")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefDelay(db.Model):
    __tablename__ = "dref_mon_delay"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("dref_mon_activity.id", ondelete="SET NULL"), nullable=True)
    report_id = db.Column(db.Integer, db.ForeignKey("dref_mon_report.id", ondelete="SET NULL"), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefEscalation(db.Model):
    __tablename__ = "dref_mon_escalation"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey("dref_mon_period.id", ondelete="CASCADE"), nullable=False)
    level = db.Column(db.String(16), nullable=False)
    notified_user_ids = db.Column(_JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefDraft(db.Model):
    __tablename__ = "dref_mon_draft"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    report_kind = db.Column(db.String(32), nullable=False)
    model = db.Column(db.String(64), nullable=False, default="")
    prompt_version = db.Column(db.String(16), nullable=False, default="1")
    input_hash = db.Column(db.String(64), nullable=False)
    sections = db.Column(_JSON, nullable=False, default=dict)
    body = db.Column(db.Text, nullable=False, default="")
    edited_body = db.Column(db.Text, nullable=True)
    ai_used = db.Column(db.Boolean, nullable=False, default=False)
    language = db.Column(db.String(8), nullable=False, default="en")
    trigger = db.Column(db.String(32), nullable=False, default="manual")
    period_id = db.Column(db.Integer, db.ForeignKey("dref_mon_period.id", ondelete="SET NULL"), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="draft")
    validated_at = db.Column(db.DateTime, nullable=True)
    validated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    go_status = db.Column(db.String(16), nullable=False, default="")
    go_reference = db.Column(db.String(64), nullable=False, default="")
    go_error = db.Column(db.Text, nullable=False, default="")
    go_submitted_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.Index("ix_dref_mon_draft_period", "operation_id", "period_id", "report_kind"),
    )


class DrefSyncLog(db.Model):
    __tablename__ = "dref_mon_sync_log"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="ok")
    created_count = db.Column(db.Integer, nullable=False, default=0)
    updated_count = db.Column(db.Integer, nullable=False, default=0)
    message = db.Column(db.Text, nullable=False, default="")


class DrefFeedback(db.Model):
    __tablename__ = "dref_mon_feedback"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    channel = db.Column(db.String(80), nullable=False, default="")
    summary = db.Column(db.Text, nullable=False)
    received_on = db.Column(db.Date, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefRisk(db.Model):
    __tablename__ = "dref_mon_risk"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    likelihood = db.Column(db.String(16), nullable=False, default="medium")
    impact = db.Column(db.String(16), nullable=False, default="medium")
    mitigation = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(16), nullable=False, default="open")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DrefFundsEvent(db.Model):
    __tablename__ = "dref_mon_funds_event"

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, db.ForeignKey("dref_mon_operation.id", ondelete="CASCADE"), nullable=False)
    received = db.Column(db.Boolean, nullable=False, default=False)
    received_on = db.Column(db.Date, nullable=True)
    note = db.Column(db.Text, nullable=False, default="")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
