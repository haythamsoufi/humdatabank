"""Decision Maker tables: versioned configuration, flag state, feedback, rule runs."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.datetime_helpers import utcnow

_JSON = JSON().with_variant(JSONB, "postgresql")


class DecisionConfigVersion(db.Model):
    """One immutable version of a decision definition or rule. The highest published version is live."""

    __tablename__ = "ifrc_decision_config_version"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)  # "decision" | "rule"
    key = db.Column(db.String(80), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="published")
    payload = db.Column(_JSON, nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        db.UniqueConstraint("kind", "key", "version", name="uq_ifrc_decision_config_version"),
        db.Index("ix_ifrc_decision_config_kind_key", "kind", "key"),
    )


class DecisionFlagState(db.Model):
    """Review state of a computed flag. Flags themselves are recalculated, never stored."""

    __tablename__ = "ifrc_decision_flag_state"

    id = db.Column(db.Integer, primary_key=True)
    flag_key = db.Column(db.String(64), nullable=False, unique=True)
    decision_id = db.Column(db.String(40), nullable=False)
    rule_id = db.Column(db.String(80), nullable=False)
    rule_version = db.Column(db.Integer, nullable=False)
    entity_id = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="new")
    note = db.Column(db.Text, nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class DecisionFlagFeedback(db.Model):
    __tablename__ = "ifrc_decision_flag_feedback"

    id = db.Column(db.Integer, primary_key=True)
    flag_key = db.Column(db.String(64), nullable=False, index=True)
    decision_id = db.Column(db.String(40), nullable=False)
    rule_id = db.Column(db.String(80), nullable=False)
    rule_version = db.Column(db.Integer, nullable=False)
    verdict = db.Column(db.String(20), nullable=False)  # useful | not_useful | incorrect | expected
    note = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DecisionRuleRun(db.Model):
    """Execution history of a rule, for the admin view."""

    __tablename__ = "ifrc_decision_rule_run"

    id = db.Column(db.Integer, primary_key=True)
    decision_id = db.Column(db.String(40), nullable=False)
    rule_id = db.Column(db.String(80), nullable=False)
    rule_version = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # ok | error
    entities_evaluated = db.Column(db.Integer, nullable=False, default=0)
    flags_raised = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.Text, nullable=True)
    ran_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    ran_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
