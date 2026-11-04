"""Read and publish versioned decision and rule configuration."""

from __future__ import annotations

import copy
import logging
from typing import Any

from app.extensions import db
from plugins.ifrc.decisions import config
from plugins.ifrc.decisions.metrics import METRIC_REGISTRY
from plugins.ifrc.decisions.models import DecisionConfigVersion

logger = logging.getLogger(__name__)


def _latest_rows(kind: str) -> dict[str, DecisionConfigVersion]:
    """Highest published version per key. A missing table (not migrated yet) means defaults only."""
    try:
        rows = (
            DecisionConfigVersion.query.filter_by(kind=kind, status="published")
            .order_by(DecisionConfigVersion.key, DecisionConfigVersion.version.desc())
            .all()
        )
    except Exception:
        db.session.rollback()
        logger.warning("Decision config table unavailable; using code defaults", exc_info=True)
        return {}
    latest: dict[str, DecisionConfigVersion] = {}
    for row in rows:
        latest.setdefault(row.key, row)
    return latest


def load_decisions() -> dict[str, dict[str, Any]]:
    decisions = config.default_decisions()
    for key, row in _latest_rows("decision").items():
        if key in decisions:
            payload = copy.deepcopy(row.payload)
            payload["version"] = row.version
            decisions[key] = payload
    return decisions


def load_rules() -> dict[str, dict[str, Any]]:
    rules = config.default_rules()
    for key, row in _latest_rows("rule").items():
        if key in rules:
            payload = copy.deepcopy(row.payload)
            payload["version"] = row.version
            rules[key] = payload
    return rules


def history(kind: str, key: str) -> list[dict[str, Any]]:
    rows = (
        DecisionConfigVersion.query.filter_by(kind=kind, key=key).order_by(DecisionConfigVersion.version.desc()).all()
    )
    return [
        {
            "version": row.version,
            "status": row.status,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by_user_id": row.created_by_user_id,
            "payload": row.payload,
        }
        for row in rows
    ]


def _publish(kind: str, key: str, payload: dict[str, Any], user_id: int | None, note: str | None) -> int:
    current = (
        db.session.query(db.func.max(DecisionConfigVersion.version)).filter_by(kind=kind, key=key).scalar()
    )
    version = int(current or 0)
    if not version:
        version = int((_DEFAULT_VERSIONS[kind].get(key) or {}).get("version") or 1)
    version += 1
    DecisionConfigVersion.query.filter_by(kind=kind, key=key, status="published").update({"status": "archived"})
    body = copy.deepcopy(payload)
    body["version"] = version
    db.session.add(
        DecisionConfigVersion(
            kind=kind,
            key=key,
            version=version,
            status="published",
            payload=body,
            note=(note or "")[:2000] or None,
            created_by_user_id=user_id,
        )
    )
    db.session.commit()
    return version


_DEFAULT_VERSIONS = {"rule": config.default_rules(), "decision": config.default_decisions()}


def publish_rule(rule_id: str, changes: dict[str, Any], *, user_id: int | None, note: str | None) -> dict[str, Any]:
    rules = load_rules()
    if rule_id not in rules:
        raise config.ConfigError(["Unknown rule."])
    merged = copy.deepcopy(rules[rule_id])
    condition_changes = changes.get("condition")
    for field in ("enabled", "severity", "minimum_data_quality", "message_template", "recommended_follow_up", "provisional"):
        if field in changes:
            merged[field] = changes[field]
    if isinstance(condition_changes, dict):
        merged["condition"] = {**merged["condition"], **condition_changes}
    errors = config.validate_rule_payload(merged, known_metrics=set(METRIC_REGISTRY))
    if errors:
        raise config.ConfigError(errors)
    version = _publish("rule", rule_id, merged, user_id, note)
    _audit("decision_rule_publish", rule_id, rules[rule_id], merged, version)
    return {**merged, "version": version}


def publish_decision(
    decision_id: str, changes: dict[str, Any], *, user_id: int | None, note: str | None
) -> dict[str, Any]:
    decisions = load_decisions()
    if decision_id not in decisions:
        raise config.ConfigError(["Unknown decision."])
    merged = copy.deepcopy(decisions[decision_id])
    for field in (
        "title",
        "question",
        "description",
        "status",
        "visibility",
        "allowed_roles",
        "metric_ids",
        "rule_ids",
        "methodology_markdown",
        "owner_team",
    ):
        if field in changes:
            merged[field] = changes[field]
    errors = config.validate_decision_payload(
        merged, known_metrics=set(METRIC_REGISTRY), known_rules=set(load_rules())
    )
    if errors:
        raise config.ConfigError(errors)
    version = _publish("decision", decision_id, merged, user_id, note)
    _audit("decision_publish", decision_id, decisions[decision_id], merged, version)
    return {**merged, "version": version}


def _audit(action: str, key: str, before: dict[str, Any], after: dict[str, Any], version: int) -> None:
    try:
        from app.services.platform.user_analytics_service import log_admin_action

        log_admin_action(
            action_type=action,
            description=f"Published {key} version {version}",
            target_type="decision_config",
            target_description=key,
            old_values={"version": before.get("version"), "condition": before.get("condition"), "status": before.get("status")},
            new_values={"version": version, "condition": after.get("condition"), "status": after.get("status")},
            risk_level="medium",
        )
    except Exception:
        logger.warning("Could not write admin audit event for %s", key, exc_info=True)
