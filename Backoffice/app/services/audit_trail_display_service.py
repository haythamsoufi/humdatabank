"""
Audit trail display helpers: consolidate activity types, human-readable descriptions,
entity extraction, and batched form-context resolution (avoids N+1 on AES/template).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.utils.activity_types import normalize_activity_type
from app.utils.activity_endpoint_overrides import (
    description_for_activity_type,
    infer_activity_type_from_legacy_description,
    infer_activity_type_from_submitted_line,
    resolve_delete_activity_type,
    resolve_post_activity_type,
)
from app.utils.activity_endpoint_catalog import resolve_activity_catalog_spec
from app.utils.activity_endpoint_catalog.defaults import describe_get_request_without_catalog

@dataclass(frozen=True)
class FormContextLookups:
    """Preloaded template/assignment labels keyed by AES id and template id."""

    aes_by_id: Dict[int, Dict[str, Optional[str]]]
    template_name_by_id: Dict[int, str]


def consolidate_activity_type(
    activity_type: Optional[str],
    action_type: Optional[str] = None,
) -> str:
    """Map stored activity/action types to canonical keys for filtering and badges."""
    if activity_type:
        normalized_activity_type = normalize_activity_type(activity_type)
        if normalized_activity_type:
            return normalized_activity_type
        if "view" in activity_type.lower():
            return "page_view"
        return activity_type

    if action_type:
        if "view" in action_type.lower():
            return "page_view"
        return action_type

    return "unknown"


def refine_activity_row_consolidated_type(
    log_activity_type: Optional[str],
    activity_description: Optional[str],
    endpoint: Optional[str],
    http_method: Optional[str] = None,
) -> str:
    """Apply request/data_deleted inference used when merging activity log rows."""
    consolidated_type = consolidate_activity_type(log_activity_type)
    if endpoint and http_method:
        spec = resolve_activity_catalog_spec(http_method, endpoint)
        if spec and spec.activity_type:
            if consolidated_type in (
                "request",
                "page_view",
                "data_deleted",
                "data_modified",
                "file_uploaded",
                "settings_updated",
            ) or (consolidated_type and str(consolidated_type).startswith("admin_")):
                return spec.activity_type
    if consolidated_type == "request":
        refined = infer_activity_type_from_legacy_description(activity_description)
        if not refined:
            refined = infer_activity_type_from_submitted_line(activity_description)
        if not refined and endpoint:
            refined = resolve_post_activity_type(endpoint)
        if refined:
            return refined
    elif consolidated_type == "data_deleted" and endpoint:
        refined = resolve_delete_activity_type(endpoint)
        if refined:
            return refined
    return consolidated_type


def _extract_aes_and_template_ids_from_context(
    context_data: Optional[Dict[str, Any]],
) -> Tuple[Optional[int], Optional[int]]:
    """Parse AES / template ids from stored context (mirrors legacy audit_trail logic)."""
    if not context_data or not isinstance(context_data, dict):
        return None, None
    try:
        form_data = context_data.get("form_data", {}) or {}
        aes_raw = (
            form_data.get("aes_id")
            or context_data.get("aes_id")
            or form_data.get("assignment_id")
            or context_data.get("assignment_id")
        )
        template_raw = form_data.get("template_id") or context_data.get("template_id")

        aes_id: Optional[int] = None
        if aes_raw is not None and str(aes_raw).isdigit():
            aes_id = int(aes_raw)
        elif not aes_raw:
            url_path = context_data.get("url_path") or ""
            if url_path:
                m = re.search(r"/enter_data/(\d+)", url_path)
                if m:
                    aes_id = int(m.group(1))

        template_id: Optional[int] = None
        if template_raw is not None and str(template_raw).isdigit():
            template_id = int(template_raw)

        return aes_id, template_id
    except (TypeError, ValueError, AttributeError):
        return None, None


def build_form_context_lookups_from_activity_logs(
    logs: List[Any],
) -> FormContextLookups:
    """
    Batch-load AssignmentEntityStatus and FormTemplate rows referenced by activity logs.

    ``logs`` are ORM ``UserActivityLog`` instances (only ``context_data`` and
    ``url_path`` are read).
    """
    aes_ids: set[int] = set()
    template_ids: set[int] = set()

    for log in logs:
        ctx: Dict[str, Any] = dict(log.context_data or {})
        if getattr(log, "url_path", None) and "url_path" not in ctx:
            ctx["url_path"] = log.url_path
        aid, tid = _extract_aes_and_template_ids_from_context(ctx)
        if aid is not None:
            aes_ids.add(aid)
        if tid is not None:
            template_ids.add(tid)

    aes_by_id: Dict[int, Dict[str, Optional[str]]] = {}
    if aes_ids:
        from app.models.assignments import AssignmentEntityStatus, AssignedForm
        from sqlalchemy.orm import joinedload

        rows = (
            AssignmentEntityStatus.query.filter(AssignmentEntityStatus.id.in_(aes_ids))
            .options(
                joinedload(AssignmentEntityStatus.assigned_form).joinedload(
                    AssignedForm.template
                ),
            )
            .all()
        )
        for aes in rows:
            template_name = assignment_name = country_name = None
            try:
                af = aes.assigned_form
                if af and af.template:
                    template_name = af.template.name
                if af:
                    assignment_name = af.period_name
                c = aes.country
                if c and hasattr(c, "name"):
                    country_name = c.name
            except Exception:
                pass
            aes_by_id[aes.id] = {
                "template_name": template_name,
                "assignment_name": assignment_name,
                "country_name": country_name,
            }

    template_name_by_id: Dict[int, str] = {}
    if template_ids:
        from app.models import FormTemplate

        for tmpl in FormTemplate.query.filter(FormTemplate.id.in_(template_ids)).all():
            template_name_by_id[tmpl.id] = tmpl.name or ""

    return FormContextLookups(aes_by_id=aes_by_id, template_name_by_id=template_name_by_id)


def _resolve_form_context(
    context_data: Optional[Dict[str, Any]],
    endpoint: Optional[str],
    lookups: Optional[FormContextLookups],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (template_name, assignment_name, country_name)."""
    template_name = assignment_name = country_name = None
    if not context_data or not isinstance(context_data, dict):
        return template_name, assignment_name, country_name

    aes_id, template_id = _extract_aes_and_template_ids_from_context(context_data)

    if aes_id is not None and lookups and aes_id in lookups.aes_by_id:
        d = lookups.aes_by_id[aes_id]
        return d.get("template_name"), d.get("assignment_name"), d.get("country_name")

    if template_id is not None and lookups and template_id in lookups.template_name_by_id:
        return lookups.template_name_by_id[template_id], None, None

    # Fallback: single-row queries (missed preload or legacy row)
    try:
        if aes_id is not None:
            from app.models import AssignmentEntityStatus

            aes = AssignmentEntityStatus.query.get(aes_id)
            if aes:
                if aes.assigned_form and aes.assigned_form.template:
                    template_name = aes.assigned_form.template.name
                assignment_name = aes.assigned_form.period_name if aes.assigned_form else None
                if aes.country:
                    country_name = aes.country.name
        elif template_id is not None:
            from app.models import FormTemplate

            tmpl = FormTemplate.query.get(template_id)
            if tmpl:
                template_name = tmpl.name
    except Exception as e:
        try:
            from flask import current_app

            current_app.logger.warning("Error resolving form context for description: %s", e)
        except Exception:
            pass

    return template_name, assignment_name, country_name


def create_consistent_description(
    entry_type: str,
    activity_type: Optional[str],
    action_type: Optional[str],
    original_description: Optional[str],
    endpoint: Optional[str] = None,
    context_data: Optional[Dict[str, Any]] = None,
    *,
    form_lookups: Optional[FormContextLookups] = None,
    http_method: Optional[str] = None,
) -> str:
    """User-facing description for one audit row (activity or admin_action)."""

    def _form_desc(base_verb: str, suffix: str = "") -> str:
        tn, an, cn = _resolve_form_context(context_data, endpoint, form_lookups)
        parts: List[str] = []
        if tn:
            parts.append(f"'{tn}'")
        if an:
            parts.append(f"({an})")
        if cn:
            parts.append(f"for {cn}")
        if parts:
            return f"{base_verb} {' '.join(parts)}{suffix}"
        if endpoint and "public" in endpoint:
            return f"{base_verb} data via public link{suffix}"
        return f"{base_verb} form data{suffix}"

    if entry_type == "activity":
        t = activity_type or ""
        method_for_catalog = (http_method or (context_data or {}).get("method") or "GET")
        if endpoint:
            spec = resolve_activity_catalog_spec(method_for_catalog, endpoint)
            if spec:
                if t in (
                    "request",
                    "page_view",
                    "data_deleted",
                    "data_modified",
                    "file_uploaded",
                ) or (t.startswith("admin_")):
                    return spec.description

        if t == "page_view" or "view" in t.lower():
            if original_description and (
                original_description.startswith("Viewed ")
                or original_description.startswith("Fetched ")
                or original_description.startswith("Session ")
            ):
                return original_description
            return describe_get_request_without_catalog(endpoint)

        if t == "request":
            inferred = infer_activity_type_from_legacy_description(original_description)
            if not inferred:
                inferred = infer_activity_type_from_submitted_line(original_description)
            if not inferred and endpoint:
                inferred = resolve_post_activity_type(endpoint)
            if inferred:
                msg = description_for_activity_type(inferred)
                if msg:
                    return msg
            if original_description and original_description.startswith("Performed "):
                tail = original_description[len("Performed ") :].strip()
                return f"Submitted {tail}" if tail else "Submitted a request"
            return original_description or "Submitted a request"

        preset = description_for_activity_type(t)
        if preset:
            return preset

        if t in ("form_saved", "form_save"):
            return _form_desc("Saved", " as draft")
        if t in ("form_submitted", "form_submit"):
            return _form_desc("Submitted", " for review")

        if t == "form_approved":
            tn, _an, cn = _resolve_form_context(context_data, endpoint, form_lookups)
            parts = []
            if tn:
                parts.append(f"'{tn}'")
            if cn:
                parts.append(f"for {cn}")
            suffix = f" ({' '.join(parts)})" if parts else ""
            return f"Approved form submission{suffix}"

        if t == "form_reopened":
            tn, _an, cn = _resolve_form_context(context_data, endpoint, form_lookups)
            parts = []
            if tn:
                parts.append(f"'{tn}'")
            if cn:
                parts.append(f"for {cn}")
            suffix = f" ({' '.join(parts)})" if parts else ""
            return f"Reopened form for editing{suffix}"

        if t == "form_validated":
            tn, _an, cn = _resolve_form_context(context_data, endpoint, form_lookups)
            parts = []
            if tn:
                parts.append(f"'{tn}'")
            if cn:
                parts.append(f"for {cn}")
            suffix = f" ({' '.join(parts)})" if parts else ""
            return f"Validated form data{suffix}"

        if t in ("data_modified", "data_update"):
            return original_description if original_description else "Updated data"

        if t in ("data_deleted", "data_delete"):
            inferred = resolve_delete_activity_type(endpoint)
            if inferred:
                msg = description_for_activity_type(inferred)
                if msg:
                    return msg
            return original_description if original_description else "Deleted item"

        if t in ("file_uploaded", "file_upload"):
            return "Uploaded a file"
        if t == "login":
            return "Logged in"
        if t == "logout":
            return "Logged out"
        if t == "profile_update":
            return "Updated profile settings"
        if t == "data_export":
            return "Exported data"
        if t == "account_created":
            return "Account created"

        return original_description or "User activity"

    # admin_action
    if not action_type:
        return original_description or "Admin action"
    if "view" in action_type.lower():
        base = action_type.replace("_", " ").replace("view ", "").strip()
        return original_description or f"Viewed {base.title()}"
    if original_description:
        return original_description
    return action_type.replace("_", " ").title()


def extract_entity_info(
    entry_type: str,
    context_data: Optional[Dict[str, Any]],
    details: Optional[Dict[str, Any]] = None,
    admin_action: Any = None,
):
    """Return (entity_type, entity_id, entity_name) for grid / API."""
    entity_type = None
    entity_id = None
    entity_name = None

    try:
        if entry_type == "activity" and context_data and isinstance(context_data, dict):
            entity_type = context_data.get("entity_type")
            entity_id = context_data.get("entity_id")
            entity_name = context_data.get("entity_name")

            if not entity_id:
                cid = context_data.get("country_id")
                cname = context_data.get("country_name")
                if not cid:
                    form_data = context_data.get("form_data", {}) or {}
                    cid = form_data.get("country_id")
                    cname = cname or form_data.get("country_name")
                if cid:
                    entity_type = "country"
                    entity_id = cid
                    entity_name = cname

            if entity_id and not entity_name and entity_type:
                try:
                    from app.services.entity_service import EntityService

                    entity_name = EntityService.get_entity_display_name(
                        entity_type, int(entity_id)
                    )
                except Exception:
                    pass

        elif entry_type == "admin_action":
            cid = None
            cname = None
            if details and isinstance(details, dict):
                cid = details.get("country_id")
                cname = details.get("country_name")
            if not cid and admin_action:
                for vals in (admin_action.new_values, admin_action.old_values):
                    if vals and isinstance(vals, dict):
                        cid = vals.get("country_id")
                        if cid:
                            cname = vals.get("country_name")
                            break
                        cids = vals.get("country_ids")
                        if cids and isinstance(cids, list) and len(cids) == 1:
                            cid = cids[0]
                            break
                if not cid and admin_action.target_type == "country" and admin_action.target_id:
                    cid = admin_action.target_id
            if cid:
                entity_type = "country"
                entity_id = cid
                if not cname:
                    try:
                        from app.models import Country

                        country = Country.query.get(int(cid))
                        cname = country.name if country else None
                    except Exception:
                        pass
                entity_name = cname

    except Exception as e:
        try:
            from flask import current_app

            current_app.logger.warning("Error extracting entity info: %s", e)
        except Exception:
            pass

    return entity_type, entity_id, entity_name
