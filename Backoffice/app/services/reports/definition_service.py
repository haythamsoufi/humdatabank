"""CRUD and scope enforcement for report definitions."""

from __future__ import annotations

import re
import uuid
from typing import Any

from flask_login import current_user

from app import db
from app.models import ReportDefinition, User
from app.services.organization.authorization_service import AuthorizationService
from app.services.reports.schema import default_definition, validate_report_definition
from app.services.security.api_authentication import (
    _get_user_allowed_country_ids,
    get_user_allowed_template_ids,
)
from app.utils.datetime_helpers import utcnow

REPORTS_VIEW = "admin.reports.view"
REPORTS_EDIT = "admin.reports.edit"
REPORTS_MANAGE = "admin.reports.manage"


class ReportDefinitionError(ValueError):
    pass


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (text or "report").lower()).strip("-")
    return base or "report"


def _unique_slug(base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 2
    while ReportDefinition.query.filter_by(slug=candidate).first() is not None:
        candidate = f"{slug}-{suffix}"
        suffix += 1
    return candidate


def user_can_manage_all(user: User) -> bool:
    return AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, REPORTS_MANAGE
    )


def user_can_edit_report(user: User, report: ReportDefinition) -> bool:
    if user_can_manage_all(user):
        return True
    if not AuthorizationService.has_rbac_permission(user, REPORTS_EDIT):
        return False
    return report.owner_user_id == user.id


def user_can_view_report(user: User, report: ReportDefinition) -> bool:
    if user_can_manage_all(user):
        return True
    if not AuthorizationService.has_rbac_permission(user, REPORTS_VIEW):
        return False
    if report.owner_user_id == user.id:
        return True
    if report.status != "published":
        return False
    return True


def resolve_user_scope(user: User) -> dict[str, list[int] | None]:
    """Return allowed template/country IDs; None means unrestricted (system manager)."""
    if user_can_manage_all(user):
        return {"template_ids": None, "country_ids": None}
    return {
        "template_ids": get_user_allowed_template_ids(user.id),
        "country_ids": _get_user_allowed_country_ids(user.id),
    }


def narrow_id_list(requested: list[int] | None, allowed: list[int] | None) -> tuple[list[int], list[str]]:
    """Intersect requested IDs with allowed set. Empty requested = all allowed."""
    warnings: list[str] = []
    if allowed is None:
        return list(requested or []), warnings
    allowed_set = set(allowed)
    if not requested:
        return list(allowed_set), warnings
    narrowed = [i for i in requested if i in allowed_set]
    dropped = set(requested) - set(narrowed)
    if dropped:
        warnings.append(f"Removed out-of-scope IDs: {sorted(dropped)}")
    return narrowed, warnings


class ReportDefinitionService:
    @staticmethod
    def list_reports(user: User) -> list[ReportDefinition]:
        q = ReportDefinition.query.filter(ReportDefinition.status != "archived")
        if not user_can_manage_all(user):
            q = q.filter(
                db.or_(
                    ReportDefinition.owner_user_id == user.id,
                    ReportDefinition.status == "published",
                )
            )
        return q.order_by(ReportDefinition.updated_at.desc()).all()

    @staticmethod
    def get_report(report_id: int, user: User) -> ReportDefinition:
        report = db.session.get(ReportDefinition, report_id)
        if not report:
            raise ReportDefinitionError("Report not found")
        if not user_can_view_report(user, report):
            raise ReportDefinitionError("Access denied")
        return report

    @staticmethod
    def create_report(
        user: User,
        *,
        title: str,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
        scope_json: dict[str, Any] | None = None,
    ) -> ReportDefinition:
        if not AuthorizationService.has_rbac_permission(user, REPORTS_EDIT) and not user_can_manage_all(user):
            raise ReportDefinitionError("Access denied")

        definition = definition or default_definition()
        validate_report_definition(definition)
        scope_json = scope_json or {}
        user_scope = resolve_user_scope(user)

        template_ids, _ = narrow_id_list(scope_json.get("template_ids"), user_scope["template_ids"])
        country_ids, _ = narrow_id_list(scope_json.get("country_ids"), user_scope["country_ids"])
        scope_json = {"template_ids": template_ids, "country_ids": country_ids}

        report = ReportDefinition(
            slug=_unique_slug(title),
            title=title.strip() or "Untitled report",
            description=(description or "").strip() or None,
            definition_json=definition,
            schema_version=definition.get("schema_version", 1),
            status="draft",
            owner_user_id=user.id,
            scope_json=scope_json,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.session.add(report)
        db.session.commit()
        return report

    @staticmethod
    def update_report(
        report_id: int,
        user: User,
        *,
        title: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
        scope_json: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> ReportDefinition:
        report = ReportDefinitionService.get_report(report_id, user)
        if not user_can_edit_report(user, report):
            raise ReportDefinitionError("Access denied")

        if title is not None:
            report.title = title.strip() or report.title
        if description is not None:
            report.description = (description or "").strip() or None
        if definition is not None:
            validate_report_definition(definition)
            report.definition_json = definition
            report.schema_version = definition.get("schema_version", 1)
        if scope_json is not None:
            user_scope = resolve_user_scope(user)
            template_ids, _ = narrow_id_list(scope_json.get("template_ids"), user_scope["template_ids"])
            country_ids, _ = narrow_id_list(scope_json.get("country_ids"), user_scope["country_ids"])
            report.scope_json = {"template_ids": template_ids, "country_ids": country_ids}
        if status is not None:
            status = status.strip().lower()
            if status not in {"draft", "published", "archived"}:
                raise ReportDefinitionError("Invalid status")
            report.status = status
            if status == "published":
                report.published_at = utcnow()

        report.updated_by_id = user.id
        db.session.commit()
        return report

    @staticmethod
    def delete_report(report_id: int, user: User) -> None:
        report = ReportDefinitionService.get_report(report_id, user)
        if not user_can_edit_report(user, report):
            raise ReportDefinitionError("Access denied")
        db.session.delete(report)
        db.session.commit()

    @staticmethod
    def clone_report(report_id: int, user: User) -> ReportDefinition:
        source = ReportDefinitionService.get_report(report_id, user)
        if not user_can_view_report(user, source):
            raise ReportDefinitionError("Access denied")
        return ReportDefinitionService.create_report(
            user,
            title=f"{source.title} (copy)",
            description=source.description,
            definition=dict(source.definition_json or {}),
            scope_json=dict(source.scope_json or {}),
        )

    @staticmethod
    def serialize(report: ReportDefinition) -> dict[str, Any]:
        return {
            "id": report.id,
            "slug": report.slug,
            "title": report.title,
            "description": report.description,
            "definition": report.definition_json,
            "schema_version": report.schema_version,
            "status": report.status,
            "owner_user_id": report.owner_user_id,
            "scope": report.scope_json,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None,
            "published_at": report.published_at.isoformat() if report.published_at else None,
        }
