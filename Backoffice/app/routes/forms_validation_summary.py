"""
Validation summary export routes for forms.

Keeps `forms.py` slimmer by registering these routes onto the existing `forms` blueprint.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import io
import json
import os
import threading
import time
import uuid

from flask import Response, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_babel import _
from flask_login import current_user, login_required
from sqlalchemy.orm import aliased, contains_eager, joinedload
from werkzeug.exceptions import NotFound

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_ok, json_server_error
from app.models import AssignedForm, AssignmentEntityStatus, FormData, FormItem, FormPage, FormSection
from app.utils.constants import LOOKUP_ROW_TEMP_ORDER
from app.utils.datetime_helpers import utcnow
from app.utils.form_localization import (
    get_localized_country_name,
    get_localized_indicator_name,
    get_localized_page_name,
    get_localized_section_name,
    get_localized_template_name,
    get_translation_key,
)

# Best-effort cancellation store (works reliably in single-process deployments).
# In multi-worker deployments, cancellation is best-effort unless backed by shared storage.
logger = logging.getLogger(__name__)

_CANCEL_LOCK = threading.Lock()
_CANCEL_FLAGS: dict[str, float] = {}  # run_id -> epoch seconds when cancelled
_CANCEL_TTL_SECONDS = 60 * 60  # 1 hour


def register_validation_summary_routes(bp) -> None:
    def _cleanup_cancel_flags() -> None:
        now = time.time()
        with _CANCEL_LOCK:
            stale = [k for k, ts in _CANCEL_FLAGS.items() if (now - ts) > _CANCEL_TTL_SECONDS]
            for k in stale:
                _CANCEL_FLAGS.pop(k, None)

    def _mark_cancelled(run_id: str) -> None:
        if not run_id:
            return
        _cleanup_cancel_flags()
        with _CANCEL_LOCK:
            _CANCEL_FLAGS[str(run_id)] = time.time()

    def _is_cancelled(run_id: str) -> bool:
        if not run_id:
            return False
        _cleanup_cancel_flags()
        with _CANCEL_LOCK:
            return str(run_id) in _CANCEL_FLAGS

    def _ai_beta_denied_json():
        """Return JSON denial response when AI beta access is restricted."""
        try:
            from app.services.app_settings_service import is_ai_beta_restricted, user_has_ai_beta_access

            if not is_ai_beta_restricted():
                return None
            if not getattr(current_user, "is_authenticated", False):
                return json_forbidden("AI beta access is limited to selected users.")
            if not user_has_ai_beta_access(current_user):
                return json_forbidden("AI beta access is limited to selected users.")
        except Exception as e:
            logger.debug("forms_validation_summary AI beta gate check failed: %s", e, exc_info=True)
        return None

    def _ai_beta_denied_sse_response():
        """Return SSE-style denial response when AI beta access is restricted."""
        denied = _ai_beta_denied_json()
        if denied is None:
            return None
        return Response(
            "event: error\ndata: " + json.dumps({"error": "AI beta access is limited to selected users."}) + "\n\n",
            mimetype="text/event-stream",
        )

    def _parse_hidden_ids_arg(arg_name: str) -> set[int]:
        raw = (request.args.get(arg_name) or "").strip()
        if not raw:
            return set()
        out: set[int] = set()
        for part in raw.split(","):
            part = (part or "").strip()
            if not part:
                continue
            if part.isdigit():
                with suppress(Exception):
                    out.add(int(part))
        return out

    def _build_page_section_item_sort_key(assignment_entity_status: AssignmentEntityStatus):
        """
        Build a sort key function for entries so they follow page → section → subsection → item order.
        Returns (group_index, item_order) for each entry.
        """
        form_template = (
            getattr(assignment_entity_status, "assigned_form", None)
            and getattr(assignment_entity_status.assigned_form, "template", None)
        ) or None
        ordered_group_tuples: list[tuple] = []  # (page_id, section_id, subsection_id)
        section_by_id: dict = {}

        if not form_template or not getattr(form_template, "id", None):
            def _fallback_sort_key(entry):
                fi = getattr(entry, "form_item", None)
                item_order = int(getattr(fi, "order", 0) or 0) if fi else 0
                return (0, item_order)
            return _fallback_sort_key

        published_vid = getattr(form_template, "published_version_id", None)
        q_sections = FormSection.query.filter(
            FormSection.template_id == int(form_template.id),
            FormSection.archived == False,  # noqa: E712
        )
        if published_vid is not None:
            with suppress(Exception):
                q_sections = q_sections.filter(FormSection.version_id == int(published_vid))
        sections_list = q_sections.order_by(FormSection.order).all()
        section_by_id = {int(s.id): s for s in sections_list if s and getattr(s, "id", None)}

        sections_by_page_id: dict = {}
        for s in sections_list:
            if not s or getattr(s, "parent_section_id", None) is not None:
                continue
            pid = int(s.page_id) if getattr(s, "page_id", None) is not None else 0
            sections_by_page_id.setdefault(pid, []).append(s)
        for pid in sections_by_page_id:
            sections_by_page_id[pid].sort(key=lambda x: (getattr(x, "order", 0) or 0))

        children_by_parent: dict = {}
        for s in sections_list:
            if not s or getattr(s, "parent_section_id", None) is None:
                continue
            pid = int(s.parent_section_id)
            children_by_parent.setdefault(pid, []).append(s)
        for pid in children_by_parent:
            children_by_parent[pid].sort(key=lambda x: (getattr(x, "order", 0) or 0))

        pages_list: list = []
        with suppress(Exception):
            if published_vid is not None:
                pages_list = (
                    FormPage.query
                    .filter_by(template_id=int(form_template.id), version_id=int(published_vid))
                    .order_by(FormPage.order.asc())
                    .all()
                )
        if not pages_list:
            with suppress(Exception):
                rel = getattr(form_template, "pages", None)
                if rel is not None and hasattr(rel, "order_by"):
                    pages_list = list(rel.order_by(FormPage.order.asc()).all())
                else:
                    pages_list = sorted(list(rel) if rel else [], key=lambda p: (getattr(p, "order", 0) or 0))

        page_ids_in_order = [int(p.id) for p in pages_list if p and getattr(p, "id", None) is not None]
        if 0 in sections_by_page_id and 0 not in page_ids_in_order:
            page_ids_in_order.append(0)
        if not page_ids_in_order:
            page_ids_in_order = [0]

        for page_id in page_ids_in_order:
            roots = sections_by_page_id.get(page_id, []) if page_id else sections_by_page_id.get(0, [])
            roots = sorted(roots, key=lambda r: (getattr(r, "order", 0) or 0))
            for root in roots:
                ordered_group_tuples.append((page_id, int(root.id), None))
                for sub in children_by_parent.get(int(root.id), []):
                    ordered_group_tuples.append((page_id, int(root.id), int(sub.id)))

        group_to_index = {g: i for i, g in enumerate(ordered_group_tuples)}

        def _entry_group_tuple(entry) -> tuple:
            fi = getattr(entry, "form_item", None)
            section_id_val = getattr(fi, "section_id", None) or getattr(fi, "form_section_id", None)
            if not fi or not section_id_val:
                return (0, 0, None)
            sec = section_by_id.get(int(section_id_val))
            if not sec:
                return (0, 0, None)
            if getattr(sec, "parent_section_id", None) is not None:
                parent = section_by_id.get(int(sec.parent_section_id))
                if parent:
                    page_id = int(parent.page_id) if getattr(parent, "page_id", None) is not None else 0
                    return (page_id, int(parent.id), int(sec.id))
            page_id = int(sec.page_id) if getattr(sec, "page_id", None) is not None else 0
            return (page_id, int(sec.id), None)

        def sort_key(entry) -> tuple:
            gt = _entry_group_tuple(entry)
            group_index = group_to_index.get(gt, LOOKUP_ROW_TEMP_ORDER)
            fi = getattr(entry, "form_item", None)
            item_order = int(getattr(fi, "order", 0) or 0) if fi else 0
            return (group_index, item_order)

        return sort_key

    def _parse_ai_sources_arg():
        """
        Parse ai_sources query param like:
          ai_sources=historical,system_documents,upr_documents
        Returns a normalized list in input order, or None when not provided/invalid.
        """
        raw = (request.args.get("ai_sources") or "").strip()
        if not raw:
            return None
        allowed = {"historical", "system_documents", "upr_documents"}
        out: list[str] = []
        seen: set[str] = set()
        for part in raw.split(","):
            p = (part or "").strip()
            if not p or p in seen:
                continue
            if p in allowed:
                out.append(p)
                seen.add(p)
        return out or None

    def _load_assignment_or_404(aes_id: int) -> AssignmentEntityStatus:
        aes = (
            AssignmentEntityStatus.query.options(
                joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template)
            )
            .get(aes_id)
        )
        if not aes:
            raise NotFound()
        return aes

    def _get_entries_for_summary(
        assignment_entity_status: AssignmentEntityStatus,
        *,
        hidden_field_ids: set[int],
        hidden_section_ids: set[int],
        include_non_reported: bool,
    ):
        """
        Return FormData entries to show/run validations for.

        - Default behavior: only include "eligible" entries (those that have a reported value/disagg or NA/DNA flag).
        - include_non_reported=True: include ALL visible form items for the template using **virtual, in-memory**
          rows for missing items (no DB writes; never create placeholder FormData rows).
        """

        def _visible_form_item_ids() -> list[int]:
            assignment = assignment_entity_status.assigned_form
            tmpl = assignment.template if assignment else None
            if not tmpl or not getattr(tmpl, "id", None):
                return []
            published_vid = getattr(tmpl, "published_version_id", None)
            q_fi = FormItem.query.filter(FormItem.template_id == int(tmpl.id))
            if published_vid is not None:
                with suppress(Exception):
                    q_fi = q_fi.filter(FormItem.version_id == int(published_vid))
            # Skip archived items
            with suppress(Exception):
                q_fi = q_fi.filter(FormItem.archived == False)  # noqa: E712
            if hidden_field_ids:
                q_fi = q_fi.filter(~FormItem.id.in_(list(hidden_field_ids)))
            # Best-effort: hidden_sections refers to FormSection.id
            if hidden_section_ids:
                q_fi = q_fi.filter(~FormItem.section_id.in_(list(hidden_section_ids)))
            q_fi = q_fi.order_by(FormItem.order.asc())
            return [int(x) for (x,) in q_fi.with_entities(FormItem.id).all() if x]

        # Important: avoid alias mismatch between joined eager loads and ORDER BY.
        # When using joined eager loading, SQLAlchemy may alias FormItem (e.g. form_item_1),
        # so ordering by the base FormItem table name would generate invalid SQL in Postgres.
        fi = aliased(FormItem)
        tmpl = getattr(getattr(assignment_entity_status, "assigned_form", None), "template", None)
        published_vid = getattr(tmpl, "published_version_id", None) if tmpl else None

        q = (
            FormData.query
            .outerjoin(fi, FormData.form_item_id == fi.id)
            .options(contains_eager(FormData.form_item, alias=fi))
            .filter(FormData.assignment_entity_status_id == assignment_entity_status.id)
        )
        if published_vid is not None:
            with suppress(Exception):
                q = q.filter(fi.version_id == int(published_vid))
        if hidden_field_ids:
            q = q.filter(~FormData.form_item_id.in_(list(hidden_field_ids)))
        if hidden_section_ids:
            # Best-effort: hidden_sections refers to FormSection.id
            with suppress(Exception):
                q = q.filter(~fi.section_id.in_(list(hidden_section_ids)))

        q = q.order_by(fi.order.asc())
        all_entries = q.all()

        # If include_non_reported, synthesize virtual rows (no DB writes) for visible items that have no FormData row.
        if include_non_reported:
            visible_ids = _visible_form_item_ids()
            if not visible_ids:
                return list(all_entries)

            # Map existing by form_item_id, keep first seen (DB may already contain duplicates).
            by_item_id: dict[int, FormData] = {}
            for e in all_entries:
                if not e or not e.form_item_id:
                    continue
                by_item_id.setdefault(int(e.form_item_id), e)

            # Load the visible FormItems in the same order used by _visible_form_item_ids.
            # (We do this to attach form_item on virtual rows so templates can render labels/types.)
            items_q = FormItem.query.filter(FormItem.id.in_(list(visible_ids)))
            items_q = items_q.order_by(FormItem.order.asc())
            visible_items = items_q.all()
            visible_items_by_id = {int(fi.id): fi for fi in visible_items if fi and getattr(fi, "id", None)}

            out: list[FormData] = []
            for fid in visible_ids:
                fid_int = int(fid)
                existing = by_item_id.get(fid_int)
                if existing:
                    out.append(existing)
                    continue

                # Virtual/transient row: never add to session, never commit.
                fd = FormData(
                    assignment_entity_status_id=int(assignment_entity_status.id),
                    form_item_id=fid_int,
                )
                # Explicitly reflect "no flags set"
                fd.data_not_available = False
                fd.not_applicable = False
                # Attach the FormItem so UI/PDF can render label/type.
                fd.form_item = visible_items_by_id.get(fid_int)
                out.append(fd)

            return out

        def _is_eligible(entry: FormData) -> bool:
            if not entry:
                return False
            if entry.data_not_available or entry.not_applicable:
                return True
            if entry.disagg_data is not None:
                return True
            if entry.value is None:
                return False
            try:
                return bool(str(entry.value).strip())
            except Exception as e:
                logger.debug("entry value check failed: %s", e)
                return False

        return [e for e in all_entries if _is_eligible(e)]

    def _localized_form_item_label(fi: FormItem, translation_key: str) -> str:
        if not fi:
            return ""
        try:
            if getattr(fi, "is_indicator", False) and getattr(fi, "indicator_bank", None):
                return get_localized_indicator_name(fi.indicator_bank) or (fi.label or "")
        except Exception as e:
            logger.debug("label get failed: %s", e)

        raw_trans = getattr(fi, "label_translations", None)
        translations_dict = {}
        if isinstance(raw_trans, dict):
            translations_dict = raw_trans
        elif isinstance(raw_trans, str):
            with suppress(Exception):
                translations_dict = json.loads(raw_trans) or {}

        if translations_dict:
            for key in [translation_key, "en"]:
                val = translations_dict.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return (fi.label or "").strip()

    def _value_display(fd: FormData) -> str:
        if not fd:
            return ""
        if fd.data_not_available:
            return _("Data not available")
        if fd.not_applicable:
            return _("Not applicable")
        if fd.disagg_data is not None:
            total = None
            with suppress(Exception):
                if fd.value is not None:
                    total = fd.value
                else:
                    values = (fd.disagg_data or {}).get("values", {})
                    if values:
                        total = sum(v for v in values.values() if v is not None)
            if total is not None:
                return str(total)
            return ""
        v = fd.value
        if v is None:
            return ""
        return str(v)

    def _serialize_validation(rec) -> dict:
        if not rec:
            return {}
        evidence = getattr(rec, "evidence", None)
        opinion_ui = None
        suggestion = None
        try:
            if isinstance(evidence, dict):
                opinion_ui = evidence.get("opinion_ui")
                suggestion = evidence.get("suggestion")
        except Exception as e:
            logger.debug("opinion_ui parse failed: %s", e)
            opinion_ui = None
            suggestion = None
        # opinion_ui is a dict like: {summary, details, decision, basis, sources}
        if not isinstance(opinion_ui, dict):
            opinion_ui = None
        if not isinstance(suggestion, dict):
            suggestion = None
        return {
            "id": int(getattr(rec, "id", 0) or 0) or None,
            "form_data_id": int(getattr(rec, "form_data_id", 0) or 0) or None,
            "status": getattr(rec, "status", None),
            "verdict": getattr(rec, "verdict", None),
            "confidence": getattr(rec, "confidence", None),
            "opinion_text": getattr(rec, "opinion_text", None),
            "opinion_summary": (opinion_ui.get("summary") if opinion_ui else None) or getattr(rec, "opinion_text", None),
            "opinion_details": (opinion_ui.get("details") if opinion_ui else None),
            "decision": (opinion_ui.get("decision") if opinion_ui else None),
            "opinion_basis": (opinion_ui.get("basis") if opinion_ui else None),
            "opinion_sources": (opinion_ui.get("sources") if opinion_ui else None),
            "suggestion": suggestion,
            "provider": getattr(rec, "provider", None),
            "model": getattr(rec, "model", None),
            "updated_at": rec.updated_at.isoformat() if getattr(rec, "updated_at", None) else None,
        }

    @bp.route("/assignment_status/<int:aes_id>/validation_summary", methods=["GET"])
    @login_required
    def validation_summary_progress_page(aes_id: int):
        """
        Progress UI for running validations in bulk for authorized users.
        Uses SSE to stream item-level results as they complete.
        """
        assignment_entity_status = _load_assignment_or_404(int(aes_id))

        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            flash("You are not authorized to view this assignment.", "warning")
            return redirect(url_for("main.dashboard"))

        hidden_field_ids_from_client = _parse_hidden_ids_arg("hidden_fields")
        hidden_section_ids_from_client = _parse_hidden_ids_arg("hidden_sections")
        translation_key = get_translation_key()

        include_non_reported = str(request.args.get("include_non_reported") or "").strip().lower() in ("1", "true", "yes", "y", "on")
        entries = _get_entries_for_summary(
            assignment_entity_status,
            hidden_field_ids=hidden_field_ids_from_client,
            hidden_section_ids=hidden_section_ids_from_client,
            include_non_reported=include_non_reported,
        )
        form_data_ids = [int(e.id) for e in entries if e and e.id]

        from app.models.ai_validation import AIFormDataValidation

        existing = {}
        if form_data_ids:
            rows = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
            existing = {int(v.form_data_id): v for v in rows if v and v.form_data_id}

        # Load persisted opinions for virtual missing rows (keyed by AES + FormItem).
        missing_existing = {}
        if include_non_reported:
            try:
                missing_item_ids = [int(fd.form_item_id) for fd in entries if fd and not getattr(fd, "id", None) and fd.form_item_id]
                missing_item_ids = list(dict.fromkeys(missing_item_ids))
                if missing_item_ids:
                    rows = (
                        AIFormDataValidation.query
                        .filter(AIFormDataValidation.form_data_id.is_(None))
                        .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                        .filter(AIFormDataValidation.form_item_id.in_(missing_item_ids))
                        .all()
                    )
                    missing_existing = {int(v.form_item_id): v for v in rows if v and v.form_item_id}
            except Exception as e:
                logger.debug("missing_existing build failed: %s", e)
                missing_existing = {}

        # Build section/page hierarchy for grouping (page -> section -> subsection)
        form_template = assignment_entity_status.assigned_form.template if assignment_entity_status.assigned_form else None
        ordered_groups: list[tuple] = []  # (page_id, section_id, subsection_id, page_name, section_name, subsection_name)
        section_by_id: dict = {}
        if form_template and getattr(form_template, "id", None):
            published_vid = getattr(form_template, "published_version_id", None)
            q_sections = FormSection.query.filter(
                FormSection.template_id == int(form_template.id),
                FormSection.archived == False,  # noqa: E712
            )
            if published_vid is not None:
                with suppress(Exception):
                    q_sections = q_sections.filter(FormSection.version_id == int(published_vid))
            sections_list = q_sections.order_by(FormSection.order).all()
            section_by_id = {int(s.id): s for s in sections_list if s and getattr(s, "id", None)}
            # Root sections by page_id
            sections_by_page_id: dict = {}
            for s in sections_list:
                if not s or getattr(s, "parent_section_id", None) is not None:
                    continue
                pid = int(s.page_id) if getattr(s, "page_id", None) is not None else 0
                sections_by_page_id.setdefault(pid, []).append(s)
            for pid in sections_by_page_id:
                sections_by_page_id[pid].sort(key=lambda x: (getattr(x, "order", 0) or 0))
            # Children (subsections) by parent_section_id
            children_by_parent: dict = {}
            for s in sections_list:
                if not s or getattr(s, "parent_section_id", None) is None:
                    continue
                pid = int(s.parent_section_id)
                children_by_parent.setdefault(pid, []).append(s)
            for pid in children_by_parent:
                children_by_parent[pid].sort(key=lambda x: (getattr(x, "order", 0) or 0))
            # Pages in order (prefer published-version pages when available).
            pages_list: list[FormPage] = []
            with suppress(Exception):
                published_vid = getattr(form_template, "published_version_id", None)
                if published_vid is not None:
                    pages_list = (
                        FormPage.query
                        .filter_by(template_id=int(form_template.id), version_id=int(published_vid))
                        .order_by(FormPage.order.asc())
                        .all()
                    )
            if not pages_list:
                with suppress(Exception):
                    rel = getattr(form_template, "pages", None)
                    if rel is not None and hasattr(rel, "order_by"):
                        pages_list = list(rel.order_by(FormPage.order.asc()).all())
                    else:
                        pages_list = sorted(list(rel) if rel else [], key=lambda p: (getattr(p, "order", 0) or 0))

            # Build ordered page id sequence.
            # Important: also include page_id=0 bucket (no page) when there are sections under it,
            # otherwise those groups fall back to index 0 and appear unsorted.
            page_ids_in_order: list[int] = [int(p.id) for p in pages_list if p and getattr(p, "id", None) is not None]
            if 0 in sections_by_page_id and 0 not in page_ids_in_order:
                page_ids_in_order.append(0)
            if not page_ids_in_order:
                page_ids_in_order = [0]

            # Friendly page display names (avoid "Page: Page").
            _data_entry = _("Data Entry")
            _page_label = _("Page")
            page_id_to_name: dict[int, str] = {0: str(_data_entry)}
            if pages_list:
                for i, p in enumerate([x for x in pages_list if x and getattr(x, "id", None) is not None]):
                    raw = (get_localized_page_name(p) or getattr(p, "name", None) or "").strip()
                    if not raw or raw.lower() == str(_page_label).strip().lower():
                        raw = f"{_page_label} {i + 1}"
                    page_id_to_name[int(p.id)] = str(raw).strip() or f"{_page_label} {i + 1}"

            # Build ordered_groups: (page_id, section_id, subsection_id, page_name, section_name, subsection_name)
            # Force strings so lazy translations evaluate and we have fallbacks for empty names
            _page_fallback = _data_entry
            _section_fallback = _("Section")
            _subsection_fallback = _("Subsection")
            for page_id in page_ids_in_order:
                page_name = page_id_to_name.get(int(page_id), str(_page_fallback))
                page_name = str(page_name or _page_fallback).strip() or str(_page_fallback)
                roots = sections_by_page_id.get(page_id, []) if page_id else sections_by_page_id.get(0, [])
                roots = sorted(roots, key=lambda r: (getattr(r, "order", 0) or 0))
                for root in roots:
                    sec_name = str(get_localized_section_name(root) or getattr(root, "name", None) or _section_fallback).strip() or str(_section_fallback)
                    ordered_groups.append((page_id, int(root.id), None, page_name, sec_name, None))
                    for sub in children_by_parent.get(int(root.id), []):
                        sub_name = str(get_localized_section_name(sub) or getattr(sub, "name", None) or _subsection_fallback).strip() or str(_subsection_fallback)
                        ordered_groups.append((page_id, int(root.id), int(sub.id), page_name, sec_name, sub_name))

        def _group_key_for_entry(fd):
            _dash = _("—")
            _page_fb = _("Page")
            _sec_fb = _("Section")
            _sub_fb = _("Subsection")
            fi = fd.form_item
            # FormItem uses section_id (not form_section_id)
            section_id_val = getattr(fi, "section_id", None) or getattr(fi, "form_section_id", None)
            if not fi or not section_id_val:
                return (0, 0, 0, str(_dash), str(_dash), str(_dash))
            sec = section_by_id.get(int(section_id_val))
            if not sec:
                return (0, 0, 0, str(_dash), str(_dash), str(_dash))
            if getattr(sec, "parent_section_id", None) is not None:
                parent = section_by_id.get(int(sec.parent_section_id))
                if parent:
                    # Subsections should inherit the parent's page bucket for ordering.
                    # (Child sections may have NULL/different page_id, but ordered_groups uses the parent's page_id.)
                    page_id = int(parent.page_id) if getattr(parent, "page_id", None) is not None else 0
                    section_id = int(parent.id)
                    subsection_id = int(sec.id)
                    sec_name = str(get_localized_section_name(parent) or getattr(parent, "name", None) or _sec_fb).strip() or str(_sec_fb)
                    sub_name = str(get_localized_section_name(sec) or getattr(sec, "name", None) or _sub_fb).strip() or str(_sub_fb)
                    page_name = page_id_to_name.get(int(parent.page_id) if getattr(parent, "page_id", None) is not None else 0, _page_fb)
                    page_name = str(page_name or _page_fb).strip() or str(_page_fb)
                    for og in ordered_groups:
                        if len(og) >= 6 and og[0] == page_id and og[1] == section_id and og[2] == subsection_id:
                            return og
                    return (page_id, section_id, subsection_id, page_name, sec_name, sub_name)
            # Non-subsection: page comes from the section itself.
            page_id = int(sec.page_id) if getattr(sec, "page_id", None) is not None else 0
            sec_name = str(get_localized_section_name(sec) or getattr(sec, "name", None) or _sec_fb).strip() or str(_sec_fb)
            page_name = page_id_to_name.get(int(sec.page_id) if getattr(sec, "page_id", None) is not None else 0, _page_fb)
            page_name = str(page_name or _page_fb).strip() or str(_page_fb)
            for og in ordered_groups:
                if len(og) >= 6 and og[0] == page_id and og[1] == int(sec.id) and og[2] is None:
                    return og
            return (page_id, int(sec.id), None, page_name, sec_name, None)

        items = []
        for idx, fd in enumerate(entries):
            fi = fd.form_item
            key = str(int(fd.id)) if getattr(fd, "id", None) else f"m:{int(assignment_entity_status.id)}:{int(fd.form_item_id)}"
            _dash = str(_("—"))
            group_key = _group_key_for_entry(fd) if form_template else (0, 0, 0, _dash, _dash, _dash)
            group_index = next((i for i, og in enumerate(ordered_groups) if len(og) >= 6 and og[0] == group_key[0] and og[1] == group_key[1] and og[2] == group_key[2]), 0)
            item_order = 0
            with suppress(Exception):
                item_order = int(getattr(fi, "order", 0) or 0) if fi else 0
            items.append({
                "_order": idx,
                "_item_order": item_order,
                "form_data_id": key,
                "form_item_id": int(fd.form_item_id) if fd.form_item_id else None,
                "item_type": (getattr(fi, "item_type", None) or "").lower() if fi else "",
                "label": _localized_form_item_label(fi, translation_key) if fi else "",
                "value_display": _value_display(fd),
                "validation": (
                    _serialize_validation(existing.get(int(fd.id))) if getattr(fd, "id", None)
                    else _serialize_validation(missing_existing.get(int(fd.form_item_id))) if (fd and fd.form_item_id)
                    else None
                ),
                "group_index": group_index,
                "page_display_name": str(group_key[3]) if group_key[3] else _dash,
                "section_display_name": str(group_key[4]) if group_key[4] else _dash,
                # Only set subsection when there is one (section has parent); otherwise None so we don't show "Subsection: —"
                "subsection_display_name": str(group_key[5]) if group_key[5] else None,
            })

        # Group items for template: only emit a header for a level when that level *changed*
        # (so Page appears once, then Section rows under it, not "Page" repeated per section)
        items_sorted = sorted(items, key=lambda x: (x["group_index"], x.get("_item_order", 0), x.get("_order", 0)))
        items_grouped = []
        prev_page, prev_section, prev_subsection = None, None, None
        for it in items_sorted:
            h0 = (it.get("page_display_name") or "").strip() if it.get("page_display_name") else ""
            h1 = (it.get("section_display_name") or "").strip() if it.get("section_display_name") else ""
            h2 = (it.get("subsection_display_name") or "").strip() if it.get("subsection_display_name") else ""
            page_val = h0 or None
            section_val = h1 or None
            subsection_val = h2 or None
            if (page_val, section_val, subsection_val) != (prev_page, prev_section, prev_subsection):
                group_headers = []
                if page_val and page_val != prev_page:
                    group_headers.append((0, str(page_val)))
                if section_val and section_val != prev_section:
                    group_headers.append((1, str(section_val)))
                if subsection_val and subsection_val != prev_subsection:
                    group_headers.append((2, str(subsection_val)))
                items_grouped.append({"headers": group_headers, "items": []})
                prev_page, prev_section, prev_subsection = page_val, section_val, subsection_val
            items_grouped[-1]["items"].append(it)

        run_id = (request.args.get("run_id") or "").strip() or str(uuid.uuid4())

        # Default behavior:
        # - If include_non_reported is enabled, do NOT auto-run (user will click "Run" explicitly).
        # - Otherwise keep legacy behavior (auto-run) unless run=0 is provided.
        default_run = "0" if include_non_reported else "1"
        sse_url = url_for(
            "forms.validation_summary_events",
            aes_id=int(aes_id),
            hidden_fields=(request.args.get("hidden_fields") or ""),
            hidden_sections=(request.args.get("hidden_sections") or ""),
            include_non_reported=("1" if include_non_reported else "0"),
            run=(request.args.get("run") or default_run),
            run_mode=(request.args.get("run_mode") or "missing"),
            concurrency=(request.args.get("concurrency") or ""),
            ai_sources=(request.args.get("ai_sources") or ""),
            run_id=run_id,
        )
        cancel_url = url_for("forms.validation_summary_cancel", aes_id=int(aes_id))
        pdf_url = url_for(
            "forms.export_assignment_validation_summary_pdf",
            aes_id=int(aes_id),
            hidden_fields=(request.args.get("hidden_fields") or ""),
            hidden_sections=(request.args.get("hidden_sections") or ""),
            include_non_reported=("1" if include_non_reported else "0"),
            ai_sources=(request.args.get("ai_sources") or ""),
            run="0",
        )

        # Localized display names for header
        assignment = assignment_entity_status.assigned_form
        country = assignment_entity_status.country
        form_template = assignment.template if assignment else None
        assignment_display_name = None
        with suppress(Exception):
            assignment_display_name = get_localized_template_name(form_template, locale=translation_key) if form_template else None
        country_display_name = None
        with suppress(Exception):
            country_display_name = get_localized_country_name(country) if country else None

        return render_template(
            "forms/entry_form/validation_summary_progress.html",
            aes=assignment_entity_status,
            assignment=assignment,
            assignment_display_name=assignment_display_name,
            country=country,
            country_display_name=country_display_name,
            items=items,
            items_grouped=items_grouped,
            sse_url=sse_url,
            cancel_url=cancel_url,
            run_id=run_id,
            pdf_url=pdf_url,
        )

    @bp.route("/assignment_status/<int:aes_id>/validation_summary/cancel", methods=["POST"])
    @login_required
    def validation_summary_cancel(aes_id: int):
        """
        Best-effort cancel for a running validation summary stream.
        """
        assignment_entity_status = _load_assignment_or_404(int(aes_id))

        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            return json_forbidden("Access denied", success=False)

        payload = get_json_safe()
        run_id = (payload.get("run_id") or "").strip()
        if not run_id:
            return json_bad_request("run_id is required", success=False)

        _mark_cancelled(run_id)
        return {"success": True, "run_id": run_id}

    @bp.route("/assignment_status/<int:aes_id>/validation_summary/events", methods=["GET"])
    @login_required
    def validation_summary_events(aes_id: int):
        """
        Server-Sent Events stream for running validations in bulk and streaming progress.
        """
        assignment_entity_status = _load_assignment_or_404(int(aes_id))

        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            return Response("event: error\ndata: " + json.dumps({"error": "Access denied"}) + "\n\n", mimetype="text/event-stream")

        hidden_field_ids_from_client = _parse_hidden_ids_arg("hidden_fields")
        hidden_section_ids_from_client = _parse_hidden_ids_arg("hidden_sections")
        translation_key = get_translation_key()
        include_non_reported = str(request.args.get("include_non_reported") or "").strip().lower() in ("1", "true", "yes", "y", "on")
        entries = _get_entries_for_summary(
            assignment_entity_status,
            hidden_field_ids=hidden_field_ids_from_client,
            hidden_section_ids=hidden_section_ids_from_client,
            include_non_reported=include_non_reported,
        )
        form_data_ids = [int(e.id) for e in entries if e and e.id]

        from app.models.ai_validation import AIFormDataValidation

        existing = {}
        if form_data_ids:
            rows = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
            existing = {int(v.form_data_id): v for v in rows if v and v.form_data_id}

        # Persisted opinions for virtual missing rows
        missing_existing = {}
        if include_non_reported:
            try:
                missing_item_ids = [int(fd.form_item_id) for fd in entries if fd and not getattr(fd, "id", None) and fd.form_item_id]
                missing_item_ids = list(dict.fromkeys(missing_item_ids))
                if missing_item_ids:
                    rows = (
                        AIFormDataValidation.query
                        .filter(AIFormDataValidation.form_data_id.is_(None))
                        .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                        .filter(AIFormDataValidation.form_item_id.in_(missing_item_ids))
                        .all()
                    )
                    missing_existing = {int(v.form_item_id): v for v in rows if v and v.form_item_id}
            except Exception as e:
                logger.debug("missing_existing build failed: %s", e)
                missing_existing = {}

        run_id = (request.args.get("run_id") or "").strip()
        run = (request.args.get("run", "1") or "1").strip().lower() not in ("0", "false", "no", "off")
        run_mode = (request.args.get("run_mode", "missing") or "missing").strip().lower()
        run_all = run_mode == "all"
        ai_sources = _parse_ai_sources_arg()

        # Determine which FormData IDs need running
        to_run: list[int] = []
        if run and form_data_ids:
            for fid in form_data_ids:
                rec = existing.get(int(fid))
                if run_all:
                    to_run.append(int(fid))
                else:
                    # missing OR non-completed
                    if not rec or (getattr(rec, "status", "") or "").lower() != "completed":
                        to_run.append(int(fid))

        # Concurrency control (default assumes PostgreSQL)
        req_conc = request.args.get("concurrency", type=int)
        default_conc = int(current_app.config.get("AI_VALIDATION_CONCURRENCY", 8) or 8)
        concurrency = int(req_conc) if isinstance(req_conc, int) and req_conc > 0 else default_conc
        # Hard safety cap to avoid accidental overload
        concurrency = max(1, min(concurrency, 20))

        app_obj = current_app._get_current_object()
        user_id = int(getattr(current_user, "id", 0) or 0) or None

        def _send(event_name: str, payload: dict) -> str:
            return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        def _worker_validate_one(form_data_id: int) -> dict:
            # Ensure Flask app context inside the thread
            with app_obj.app_context():
                try:
                    from app.services.ai_formdata_validation_service import AIFormDataValidationService
                    from app.models.ai_validation import AIFormDataValidation

                    svc = AIFormDataValidationService()
                    rec, _val_result = svc.upsert_validation(
                        form_data_id=int(form_data_id),
                        run_by_user_id=user_id,
                        sources=ai_sources,
                    )

                    # Read back a fresh instance to ensure updated_at/opinion_text are present
                    fresh = AIFormDataValidation.query.filter_by(form_data_id=int(form_data_id)).first()
                    return _serialize_validation(fresh or rec)
                except Exception as e:
                    return {
                        "form_data_id": int(form_data_id),
                        "status": "failed",
                        "verdict": "uncertain",
                        "confidence": None,
                        "opinion_text": f"Validation failed: {e}",
                        "updated_at": None,
                    }

        def _compute_counts(items_map: dict) -> dict:
            counts = {"good": 0, "discrepancy": 0, "uncertain": 0, "failed": 0, "missing": 0}
            for v in items_map.values():
                status = (v.get("status") or "").lower()
                verdict = (v.get("verdict") or "").lower()
                if not verdict:
                    counts["missing"] += 1
                    continue
                if status == "failed":
                    counts["failed"] += 1
                elif verdict == "good":
                    counts["good"] += 1
                elif verdict == "discrepancy":
                    counts["discrepancy"] += 1
                else:
                    counts["uncertain"] += 1
            return counts

        def _entry_key(fd) -> str:
            if getattr(fd, "id", None):
                return str(int(fd.id))
            return f"m:{int(assignment_entity_status.id)}:{int(fd.form_item_id or 0)}"

        def _validation_for_entry(fd):
            if getattr(fd, "id", None):
                return _serialize_validation(existing.get(int(fd.id)))
            return _serialize_validation(missing_existing.get(int(fd.form_item_id))) if (fd and fd.form_item_id) else {}

        # Map of fid (int) -> validation dict for real entries (updated when worker returns)
        validations_map: dict[int, dict] = {int(fid): _serialize_validation(existing.get(int(fid))) for fid in form_data_ids}
        # Full map (all entries, string key) for counts and completed
        validations_map_full: dict[str, dict] = {_entry_key(fd): _validation_for_entry(fd) for fd in entries}

        def _count_completed() -> int:
            return sum(
                1
                for v in validations_map_full.values()
                if (v or {}).get("verdict") or ((v or {}).get("status") or "").lower() == "completed"
            )

        total_entries = len(entries)

        def generate():
            # Initial payload: total = all entries (reported + non-reported when included), completed = those with a validation
            init_payload = {
                "total_items": total_entries,
                "to_run": to_run,
                "completed": _count_completed(),
                "concurrency": concurrency,
                "counts": _compute_counts(validations_map_full),
            }
            yield _send("init", init_payload)

            # Keepalive to prevent proxy timeouts
            yield ": keepalive\n\n"

            # Send a baseline snapshot of all items (so UI can render immediately)
            snapshot_items = []
            for fd in entries:
                fi = fd.form_item
                key = str(int(fd.id)) if getattr(fd, "id", None) else f"m:{int(assignment_entity_status.id)}:{int(fd.form_item_id)}"
                snapshot_items.append({
                    "form_data_id": key,
                    "label": _localized_form_item_label(fi, translation_key) if fi else "",
                    "item_type": (getattr(fi, "item_type", None) or "").lower() if fi else "",
                    "value_display": _value_display(fd),
                    "validation": (
                        validations_map.get(int(fd.id), {}) if getattr(fd, "id", None)
                        else _serialize_validation(missing_existing.get(int(fd.form_item_id))) if (fd and fd.form_item_id)
                        else {}
                    ),
                })
            yield _send("snapshot", {"items": snapshot_items})

            if not to_run:
                yield _send("done", {
                    "counts": _compute_counts(validations_map_full),
                    "ran_count": 0,
                    "completed": _count_completed(),
                    "total_items": total_entries,
                })
                return

            ran = 0

            # Bulk validate with bounded concurrency; allow best-effort cancel (stop submitting new work)
            ex = ThreadPoolExecutor(max_workers=concurrency)
            try:
                pending_iter = iter([int(x) for x in to_run])
                running: dict = {}

                def _shutdown_executor_fast():
                    # Cancel queued futures and don't wait for running ones (best-effort).
                    with suppress(TypeError):
                        ex.shutdown(wait=False, cancel_futures=True)  # py>=3.9
                        return
                    with suppress(Exception):
                        ex.shutdown(wait=False)

                def _submit_next() -> bool:
                    try:
                        fid_next = next(pending_iter)
                    except StopIteration:
                        return False
                    if run_id and _is_cancelled(run_id):
                        return False
                    yield _send("started", {"form_data_id": int(fid_next)})
                    running[ex.submit(_worker_validate_one, int(fid_next))] = int(fid_next)
                    return True

                # Prime the pool
                for _i in range(min(concurrency, len(to_run))):
                    ok = yield from _submit_next()
                    if ok is False:
                        break

                while running:
                    if run_id and _is_cancelled(run_id):
                        # Cancel queued futures not yet running (best-effort) and return quickly.
                        for fut in list(running.keys()):
                            with suppress(Exception):
                                fut.cancel()
                        _shutdown_executor_fast()
                        yield _send("cancelled", {
                            "counts": _compute_counts(validations_map_full),
                            "ran_count": ran,
                            "completed": _count_completed(),
                            "total_items": total_entries,
                        })
                        return

                    done, _not_done = wait(list(running.keys()), timeout=0.75, return_when=FIRST_COMPLETED)
                    if not done:
                        yield ": keepalive\n\n"
                        continue

                    for fut in done:
                        fid = running.pop(fut, None)
                        try:
                            data = fut.result()
                        except Exception as e:
                            data = {
                                "form_data_id": int(fid) if fid is not None else None,
                                "status": "failed",
                                "verdict": "uncertain",
                                "opinion_text": f"Validation failed: {e}",
                            }
                        if fid is not None:
                            validations_map[int(fid)] = data or {}
                            validations_map_full[str(fid)] = data or {}
                        ran += 1
                        yield _send(
                            "item",
                            {
                                "form_data_id": int(fid) if fid is not None else None,
                                "validation": data,
                                "counts": _compute_counts(validations_map_full),
                                "completed": _count_completed(),
                                "total_items": total_entries,
                                "total_to_run": len(to_run),
                            },
                        )
                        yield ": keepalive\n\n"

                        # Keep the pool full
                        if not (run_id and _is_cancelled(run_id)):
                            if len(running) < concurrency:
                                ok = yield from _submit_next()
                                if ok is False:
                                    continue

                yield _send("done", {
                    "counts": _compute_counts(validations_map_full),
                    "ran_count": ran,
                    "completed": _count_completed(),
                    "total_items": total_entries,
                })
            except GeneratorExit:
                # Client disconnected; stop submitting new work.
                if run_id:
                    _mark_cancelled(run_id)
                with suppress(Exception):
                    ex.shutdown(wait=False)
                raise
            finally:
                # Ensure we don't block on shutdown.
                with suppress(Exception):
                    ex.shutdown(wait=False)

        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @bp.route("/assignment_status/<int:aes_id>/validation_summary_pdf", methods=["GET"])
    @login_required
    def export_assignment_validation_summary_pdf(aes_id):
        """
        Generate a PDF validation summary for one assignment.

        Uses the latest AI validation opinions stored in AIFormDataValidation, and can (optionally)
        run missing validations for eligible FormData items before generating the PDF.

        Query params:
        - run: 1|0 (default 0) - run missing validations before exporting
        - run_mode: missing|all (default missing)
        - hidden_fields: comma-separated FormItem ids hidden in the UI (optional)
        """
        try:
            assignment_entity_status = _load_assignment_or_404(int(aes_id))

            from app.services.authorization_service import AuthorizationService

            if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
                flash("You are not authorized to export data for this assignment and country.", "warning")
                return redirect(url_for("main.dashboard"))

            assignment = assignment_entity_status.assigned_form
            country = assignment_entity_status.country
            form_template = assignment.template if assignment else None
            published_vid = getattr(form_template, "published_version_id", None) if form_template else None

            hidden_field_ids_from_client = _parse_hidden_ids_arg("hidden_fields")
            hidden_section_ids_from_client = _parse_hidden_ids_arg("hidden_sections")
            include_non_reported = str(request.args.get("include_non_reported") or "").strip().lower() in ("1", "true", "yes", "y", "on")

            if not form_template:
                flash("Template not found for this assignment.", "warning")
                return redirect(url_for("main.dashboard"))

            # Build section tree (similar ordering to export_pdf)
            sections_by_page = {}
            default_page_id = 0
            section_nodes_by_id = {}
            ordered_section_ids = []

            q_sections = FormSection.query.filter(
                FormSection.template_id == int(form_template.id),
                FormSection.archived == False,  # noqa: E712
            )
            if published_vid is not None:
                with suppress(Exception):
                    q_sections = q_sections.filter(FormSection.version_id == int(published_vid))
            for section_model in q_sections.order_by(FormSection.order).all():
                if getattr(section_model, "archived", False):
                    continue
                sec_name = None
                with suppress(Exception):
                    sec_name = get_localized_section_name(section_model)
                if not sec_name:
                    sec_name = getattr(section_model, "display_name", None) or section_model.name

                node = {
                    "id": int(section_model.id),
                    "page_id": int(section_model.page_id) if section_model.page_id is not None else None,
                    "parent_section_id": int(section_model.parent_section_id) if section_model.parent_section_id is not None else None,
                    "display_name": sec_name,
                    # Match export_pdf.html naming to avoid Jinja collisions (dict.items)
                    "fields_ordered": [],
                    "subsections": [],
                }
                section_nodes_by_id[int(section_model.id)] = node
                ordered_section_ids.append(int(section_model.id))

            # Attach children
            for sid in ordered_section_ids:
                node = section_nodes_by_id.get(int(sid))
                if not node:
                    continue
                parent_id = node.get("parent_section_id")
                if parent_id and parent_id in section_nodes_by_id:
                    section_nodes_by_id[parent_id]["subsections"].append(node)

            # Root nodes grouped by page
            for sid in ordered_section_ids:
                node = section_nodes_by_id.get(int(sid))
                if not node or node.get("parent_section_id") is not None:
                    continue
                page_id = node.get("page_id") if node.get("page_id") is not None else default_page_id
                sections_by_page.setdefault(page_id, []).append(node)

            # include_non_reported: do NOT create placeholder FormData rows.
            # Missing items are rendered as "no data" by joining FormItems with existing FormData below.

            # Load all FormItems for template and map them to sections
            q_items = FormItem.query.filter_by(template_id=int(form_template.id), archived=False)
            if published_vid is not None:
                with suppress(Exception):
                    q_items = q_items.filter(FormItem.version_id == int(published_vid))
            form_items = q_items.order_by(FormItem.section_id.asc(), FormItem.order.asc()).all()

            # Load FormData entries for this assignment
            existing_q = (
                FormData.query
                .options(joinedload(FormData.form_item))
                .filter(FormData.assignment_entity_status_id == assignment_entity_status.id)
            )
            if published_vid is not None:
                with suppress(Exception):
                    existing_q = existing_q.join(FormItem, FormData.form_item_id == FormItem.id).filter(FormItem.version_id == int(published_vid))
            existing_entries = existing_q.all()
            entry_by_form_item_id = {}
            form_data_ids = []
            for e in existing_entries:
                if not e or not e.form_item_id:
                    continue
                entry_by_form_item_id[int(e.form_item_id)] = e
                if e.id:
                    form_data_ids.append(int(e.id))

            # Load AI validations
            from app.models.ai_validation import AIFormDataValidation

            by_form_data_id = {}
            if form_data_ids:
                validations = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
                by_form_data_id = {int(v.form_data_id): v for v in validations if v and v.form_data_id}

            # Persisted opinions for "virtual missing" rows (keyed by AES + FormItem).
            # Note: this does NOT create placeholder FormData rows.
            missing_by_form_item_id = {}
            try:
                fi_ids = [int(fi.id) for fi in form_items if fi and getattr(fi, "id", None)]
                if fi_ids:
                    miss_rows = (
                        AIFormDataValidation.query
                        .filter(AIFormDataValidation.form_data_id.is_(None))
                        .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                        .filter(AIFormDataValidation.form_item_id.in_(fi_ids))
                        .all()
                    )
                    missing_by_form_item_id = {int(v.form_item_id): v for v in miss_rows if v and v.form_item_id}
            except Exception as e:
                logger.debug("missing_by_form_item_id build failed: %s", e)
                missing_by_form_item_id = {}

            run = (request.args.get("run", "0") or "0").strip().lower() not in ("0", "false", "no", "off")
            run_mode = (request.args.get("run_mode", "missing") or "missing").strip().lower()
            run_all = run_mode == "all"
            ai_sources = _parse_ai_sources_arg()

            ran_count = 0
            if run and form_data_ids:
                from app.services.ai_formdata_validation_service import AIFormDataValidationService

                svc = AIFormDataValidationService()
                for fid in list(dict.fromkeys(form_data_ids)):
                    existing = by_form_data_id.get(int(fid))
                    if not run_all and existing and (existing.status or "").lower() == "completed":
                        continue
                    try:
                        rec, _val_result = svc.upsert_validation(
                            form_data_id=int(fid),
                            run_by_user_id=int(current_user.id),
                            sources=ai_sources,
                        )
                        by_form_data_id[int(fid)] = rec
                        ran_count += 1
                    except Exception as e:
                        current_app.logger.warning(
                            "Validation summary: AI validation failed for FormData %s: %s",
                            fid,
                            e,
                            exc_info=True,
                        )
                        # Keep any existing record; otherwise the template will show "not run"

                # Refresh from DB to ensure we have latest updated_at/opinion_text for PDF render
                validations = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
                by_form_data_id = {int(v.form_data_id): v for v in validations if v and v.form_data_id}

            # If include_non_reported and run=1, also (best-effort) run missing-row suggestions without creating FormData.
            if include_non_reported and run:
                try:
                    from app.services.ai_formdata_validation_service import AIFormDataValidationService

                    svc = AIFormDataValidationService()
                    for fi in form_items:
                        if not fi or not getattr(fi, "id", None):
                            continue
                        fi_id = int(fi.id)
                        if entry_by_form_item_id.get(fi_id):
                            continue  # already handled by persisted FormData path
                        existing_miss = missing_by_form_item_id.get(fi_id)
                        if not run_all and existing_miss and (existing_miss.status or "").lower() == "completed":
                            continue
                        try:
                            rec, _vr = svc.upsert_missing_assigned_validation(
                                assignment_entity_status_id=int(assignment_entity_status.id),
                                form_item_id=int(fi_id),
                                run_by_user_id=int(current_user.id),
                                sources=ai_sources,
                            )
                            missing_by_form_item_id[int(fi_id)] = rec
                            ran_count += 1
                        except Exception as e:
                            current_app.logger.warning(
                                "Validation summary: AI validation failed for missing item (ACS=%s, FormItem=%s): %s",
                                assignment_entity_status.id,
                                fi_id,
                                e,
                                exc_info=True,
                            )
                except Exception as e:
                    logger.debug("localization failed: %s", e)

            # Localized display names
            translation_key = get_translation_key()
            assignment_display_name = None
            with suppress(Exception):
                assignment_display_name = (
                    get_localized_template_name(form_template, locale=translation_key) if form_template else None
                )
            country_display_name = None
            with suppress(Exception):
                country_display_name = get_localized_country_name(country) if country else None

            # Attach items to section tree
            def _item_kind(fi: FormItem) -> str:
                if not fi:
                    return "question"
                it = (getattr(fi, "item_type", None) or "").strip().lower()
                if it in ("note",):
                    return "note"
                if it in ("matrix",):
                    return "matrix"
                # Heuristic: matrix-like config
                cfg = getattr(fi, "config", None)
                if isinstance(cfg, dict) and isinstance(cfg.get("matrix_config"), dict):
                    return "matrix"
                if getattr(fi, "is_document_field", False):
                    return "document"
                if getattr(fi, "is_indicator", False):
                    return "indicator"
                if getattr(fi, "is_question", False):
                    return "question"
                return it or "question"

            for fi in form_items:
                if not fi or not fi.section_id:
                    continue
                if hidden_field_ids_from_client and int(fi.id) in hidden_field_ids_from_client:
                    continue
                node = section_nodes_by_id.get(int(fi.section_id))
                if not node:
                    continue

                entry = entry_by_form_item_id.get(int(fi.id))
                rec = (
                    by_form_data_id.get(int(entry.id)) if entry and entry.id
                    else missing_by_form_item_id.get(int(fi.id))
                )
                node["fields_ordered"].append({
                    "form_item_id": int(fi.id),
                    "kind": _item_kind(fi),
                    "label": _localized_form_item_label(fi, translation_key),
                    "model": fi,
                    "form_data_id": int(entry.id) if entry and entry.id else None,
                    "value": entry.disagg_data if (entry and entry.disagg_data is not None) else (entry.value if entry else None),
                    "data_not_available": bool(entry.data_not_available) if entry else False,
                    "not_applicable": bool(entry.not_applicable) if entry else False,
                    "ai_validation": rec,
                })

            # Filter out hidden sections (and recurse)
            def _filter_section_node(section_node):
                if not isinstance(section_node, dict):
                    return None
                try:
                    if hidden_section_ids_from_client and int(section_node.get("id")) in hidden_section_ids_from_client:
                        return None
                except Exception as e:
                    logger.debug("child filter failed: %s", e)
                kept_children = []
                for child in (section_node.get("subsections") or []):
                    kept = _filter_section_node(child)
                    if kept is not None:
                        kept_children.append(kept)
                section_node["subsections"] = kept_children
                return section_node

            filtered_sections_by_page = {}
            for page_id, root_sections in (sections_by_page or {}).items():
                kept_roots = []
                for sec in (root_sections or []):
                    kept = _filter_section_node(sec)
                    if kept is not None:
                        kept_roots.append(kept)
                filtered_sections_by_page[page_id] = kept_roots
            sections_by_page = filtered_sections_by_page

            # Stats by verdict/status
            stats = {
                "total_items": 0,
                "good": 0,
                "discrepancy": 0,
                "uncertain": 0,
                "failed": 0,
                "missing": 0,
                "ran_count": ran_count,
            }
            for _page_id, roots in (sections_by_page or {}).items():
                for root in (roots or []):
                    stack = [root]
                    while stack:
                        sec = stack.pop()
                        for it in (sec.get("fields_ordered") or []):
                            stats["total_items"] += 1
                            v = it.get("ai_validation")
                            if not v or not getattr(v, "verdict", None):
                                stats["missing"] += 1
                                continue
                            status = (getattr(v, "status", "") or "").lower()
                            verdict = (getattr(v, "verdict", "") or "").lower()
                            if status == "failed":
                                stats["failed"] += 1
                            elif verdict == "good":
                                stats["good"] += 1
                            elif verdict == "discrepancy":
                                stats["discrepancy"] += 1
                            else:
                                stats["uncertain"] += 1
                        for child in (sec.get("subsections") or []):
                            stack.append(child)

            # Pages list (published version only; preserve page order; if none, single default)
            pages = [None]
            if getattr(form_template, "is_paginated", False):
                if published_vid is not None:
                    with suppress(Exception):
                        pages = (
                            FormPage.query
                            .filter_by(template_id=int(form_template.id), version_id=int(published_vid))
                            .order_by(FormPage.order.asc())
                            .all()
                        ) or [None]
                else:
                    pages = list(form_template.pages) if getattr(form_template, "pages", None) is not None else [None]

            # Render print-optimized HTML
            html_content = render_template(
                "forms/entry_form/validation_summary_pdf.html",
                assignment=assignment,
                assignment_display_name=assignment_display_name,
                country=country,
                country_display_name=country_display_name,
                aes=assignment_entity_status,
                form_template=form_template,
                generated_at=utcnow(),
                pages=pages,
                sections_by_page=sections_by_page,
                get_localized_page_name=get_localized_page_name,
                stats=stats,
            )

            # Lazy import WeasyPrint to avoid hard dependency unless used
            try:
                from weasyprint import CSS, HTML  # type: ignore
            except Exception as e:
                current_app.logger.error(f"WeasyPrint not available: {e}")
                return current_app.response_class(
                    response="PDF generation is not available on this deployment.",
                    status=503,
                    mimetype="text/plain",
                )

            static_dir = os.path.join(current_app.root_path, "static")

            # Keep CSS self-contained (matching export_pdf look-and-feel)
            pdf_css_string = """
                @page {
                    size: A4;
                    margin: 20mm 15mm 20mm 15mm;
                    @bottom-right { content: "Page " counter(page); font-size: 10pt; color: #6b7280; }
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Arial, sans-serif;
                    color: #111827;
                    line-height: 1.5;
                }
                h1, h2, h3, h4 { margin: 0 0 10px 0; }
                h1 { font-size: 20pt; }
                h2 { font-size: 14pt; border-bottom: 2px solid #cc0000; padding-bottom: 4px; margin-top: 16px; margin-bottom: 12px; }
                h3 { font-size: 12pt; margin-top: 10px; margin-bottom: 8px; color: #374151; }
                h4 { font-size: 11pt; margin-top: 8px; margin-bottom: 6px; color: #374151; }
                .form-page-title { page-break-after: avoid; }
                .meta {
                    color: #374151;
                    font-size: 10pt;
                    margin-bottom: 16px;
                    padding: 8px;
                    background: #f9fafb;
                    border-left: 3px solid #cc0000;
                }
                .meta div { margin: 4px 0; }
                .section { margin-bottom: 16px; }
                .section-empty-note { color: #6b7280; font-size: 10pt; font-style: italic; margin: 8px 0 0 0; }

                .summary-grid {
                    display: grid;
                    grid-template-columns: repeat(5, 1fr);
                    gap: 8px;
                }
                .summary-card {
                    border: 1px solid #e5e7eb;
                    padding: 10px 12px;
                    background: #ffffff;
                }
                .summary-label { font-size: 9pt; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; }
                .summary-value { font-size: 16pt; font-weight: 700; margin-top: 2px; }
                .summary-good { border-left: 4px solid #10b981; }
                .summary-discrepancy { border-left: 4px solid #f97316; }
                .summary-uncertain { border-left: 4px solid #9ca3af; }
                .summary-failed { border-left: 4px solid #ef4444; }
                .summary-missing { border-left: 4px solid #d1d5db; }

                /* Field box styling (like export_pdf) */
                .field-box {
                    border: 1.5px solid #e5e7eb;
                    border-radius: 4px;
                    margin: 8px 0;
                    page-break-inside: avoid;
                    background: #ffffff;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
                }
                .field-filled { border-left: 4px solid #10b981; }
                .field-empty-required { border-left: 4px solid #ef4444; background: #fef2f2; }
                .field-empty-optional { border-left: 4px solid #d1d5db; background: #f9fafb; }
                .field-header {
                    background: #f9fafb;
                    padding: 8px 12px;
                    border-bottom: 1px solid #e5e7eb;
                    font-weight: 600;
                }
                .field-label { color: #111827; font-size: 11pt; display: block; }
                .field-content { padding: 10px 12px; min-height: 20px; }
                .field-value { color: #111827; font-size: 10pt; word-wrap: break-word; display: block; }
                .not-reported { color: #dc2626; font-size: 10pt; }
                .not-reported-optional { color: #6b7280; font-size: 10pt; font-style: italic; }

                .ai-block {
                    margin-top: 10px;
                    padding-top: 8px;
                    border-top: 1px dashed #e5e7eb;
                }
                .ai-title { font-size: 9pt; font-weight: 700; color: #374151; margin-bottom: 4px; }
                .ai-meta { font-size: 8.5pt; color: #6b7280; margin-top: 4px; }
                .ai-opinion { white-space: pre-wrap; word-wrap: break-word; font-size: 9.5pt; color: #111827; margin-top: 6px; }

                .badge {
                    display: inline-block;
                    font-size: 9pt;
                    font-weight: 600;
                    padding: 2px 8px;
                    border-radius: 999px;
                }
                .badge-good { background: #dcfce7; color: #166534; }
                .badge-discrepancy { background: #ffedd5; color: #9a3412; }
                .badge-uncertain { background: #f3f4f6; color: #374151; }
                .badge-failed { background: #fee2e2; color: #991b1b; }
                .badge-missing { background: #f9fafb; color: #6b7280; border: 1px solid #e5e7eb; }
                .page-break { page-break-before: always; }
            """
            with suppress(Exception):
                pdf_css_string = pdf_css_string.replace('content: "Page "', f'content: "{_("Page")} "')
            pdf_css = CSS(string=pdf_css_string)

            pdf_buffer = io.BytesIO()
            HTML(string=html_content, base_url=static_dir).write_pdf(
                pdf_buffer,
                stylesheets=[pdf_css],
                optimize_size=("fonts", "images"),
            )
            pdf_buffer.seek(0)

            filename = (
                f"validation_summary_{country.iso3 if country else 'country'}_"
                f"{str(assignment.period_name).replace(' ', '_') if assignment else 'period'}.pdf"
            )
            return send_file(
                pdf_buffer,
                download_name=filename,
                as_attachment=True,
                mimetype="application/pdf",
            )
        except Exception as e:
            current_app.logger.error(
                f"Error generating validation summary PDF for ACS {aes_id}: {e}",
                exc_info=True,
            )
            flash("Failed to generate validation summary.", "danger")
            return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    @bp.route("/assignment_status/<int:aes_id>/validation_summary/opinions", methods=["GET"])
    @login_required
    def validation_summary_opinions(aes_id: int):
        """
        Return latest AI validation opinions keyed by form_item_id for an assignment.

        Includes both:
        - Persisted FormData-linked validations.
        - Virtual/missing-item validations keyed by (assignment_entity_status_id, form_item_id).
        """
        try:
            denied = _ai_beta_denied_json()
            if denied is not None:
                return denied

            assignment_entity_status = _load_assignment_or_404(int(aes_id))

            from app.services.authorization_service import AuthorizationService
            from app.models.ai_validation import AIFormDataValidation

            if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
                return json_forbidden("Access denied")

            def _collect_opinions_by_form_item() -> dict[str, dict]:
                linked_rows = (
                    AIFormDataValidation.query
                    .join(FormData, AIFormDataValidation.form_data_id == FormData.id)
                    .filter(FormData.assignment_entity_status_id == int(assignment_entity_status.id))
                    .all()
                )
                missing_rows = (
                    AIFormDataValidation.query
                    .filter(AIFormDataValidation.form_data_id.is_(None))
                    .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                    .all()
                )

                merged_by_form_item: dict[int, object] = {}

                def _pick_latest(existing_rec, candidate_rec):
                    if not existing_rec:
                        return candidate_rec
                    ex_updated = getattr(existing_rec, "updated_at", None)
                    ca_updated = getattr(candidate_rec, "updated_at", None)
                    if ex_updated and ca_updated:
                        return candidate_rec if ca_updated >= ex_updated else existing_rec
                    if ca_updated and not ex_updated:
                        return candidate_rec
                    if ex_updated and not ca_updated:
                        return existing_rec
                    ex_id = int(getattr(existing_rec, "id", 0) or 0)
                    ca_id = int(getattr(candidate_rec, "id", 0) or 0)
                    return candidate_rec if ca_id >= ex_id else existing_rec

                for rec in linked_rows:
                    fi_id = None
                    try:
                        fd = getattr(rec, "form_data", None)
                        fi_id = int(getattr(fd, "form_item_id", 0) or 0)
                    except Exception as e:
                        logger.debug("form_item_id get failed: %s", e)
                        fi_id = None
                    if not fi_id:
                        continue
                    merged_by_form_item[fi_id] = _pick_latest(merged_by_form_item.get(fi_id), rec)

                for rec in missing_rows:
                    fi_id = None
                    try:
                        fi_id = int(getattr(rec, "form_item_id", 0) or 0)
                    except Exception as e:
                        logger.debug("form_item_id get failed: %s", e)
                        fi_id = None
                    if not fi_id:
                        continue
                    merged_by_form_item[fi_id] = _pick_latest(merged_by_form_item.get(fi_id), rec)

                return {
                    str(fi_id): _serialize_validation(rec)
                    for fi_id, rec in merged_by_form_item.items()
                }

            payload = _collect_opinions_by_form_item()
            return json_ok(opinionsByFormItemId=payload)
        except Exception as e:
            current_app.logger.error(
                "Error loading validation summary opinions for ACS %s: %s",
                aes_id,
                e,
                exc_info=True,
            )
            return json_server_error("Failed to load AI opinions")

    @bp.route("/assignment_status/<int:aes_id>/validation_summary/opinions/run", methods=["POST"])
    @login_required
    def validation_summary_run_and_load_opinions(aes_id: int):
        """
        Run assignment-level AI opinions and return latest opinions keyed by form_item_id.
        """
        try:
            denied = _ai_beta_denied_json()
            if denied is not None:
                return denied

            assignment_entity_status = _load_assignment_or_404(int(aes_id))

            from app.services.authorization_service import AuthorizationService
            from app.models.ai_validation import AIFormDataValidation
            from app.services.ai_formdata_validation_service import AIFormDataValidationService

            if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
                return json_forbidden("Access denied")

            payload = get_json_safe()
            mode = str(payload.get("mode") or "missing").strip().lower()
            run_all = mode == "all"
            include_non_reported = bool(payload.get("include_non_reported"))

            def _parse_ids(values) -> set[int]:
                out: set[int] = set()
                if not isinstance(values, (list, tuple)):
                    return out
                for v in values:
                    with suppress(Exception):
                        n = int(v)
                        if n > 0:
                            out.add(n)
                return out

            hidden_field_ids = _parse_ids(payload.get("hidden_fields"))
            hidden_section_ids = _parse_ids(payload.get("hidden_sections"))

            raw_sources = payload.get("sources")
            allowed_sources = {"historical", "system_documents", "upr_documents"}
            ai_sources = None
            if isinstance(raw_sources, list):
                norm = []
                seen = set()
                for v in raw_sources:
                    s = str(v or "").strip()
                    if not s or s in seen or s not in allowed_sources:
                        continue
                    seen.add(s)
                    norm.append(s)
                ai_sources = norm or None

            entries = _get_entries_for_summary(
                assignment_entity_status,
                hidden_field_ids=hidden_field_ids,
                hidden_section_ids=hidden_section_ids,
                include_non_reported=include_non_reported,
            )

            def _is_document_entry(entry) -> bool:
                try:
                    fi = getattr(entry, "form_item", None)
                    if not fi:
                        return False
                    item_type = str(getattr(fi, "item_type", "") or "").strip().lower()
                    if item_type == "document_field":
                        return True
                    return bool(getattr(fi, "is_document_field", False))
                except Exception as e:
                    logger.debug("is_document_field check failed: %s", e)
                    return False

            # Explicitly skip document fields for this entry-form AI opinions flow.
            entries = [e for e in entries if e and not _is_document_entry(e)]

            # Sort by page → section → subsection → item order so processing follows form layout.
            sort_key_fn = _build_page_section_item_sort_key(assignment_entity_status)
            entries = sorted(entries, key=sort_key_fn)

            form_data_ids = [int(e.id) for e in entries if e and getattr(e, "id", None)]
            existing_by_fd = {}
            if form_data_ids:
                rows = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
                existing_by_fd = {int(v.form_data_id): v for v in rows if v and v.form_data_id}

            missing_item_ids = [int(e.form_item_id) for e in entries if e and not getattr(e, "id", None) and e.form_item_id]
            missing_item_ids = list(dict.fromkeys(missing_item_ids))
            existing_missing = {}
            if missing_item_ids:
                rows = (
                    AIFormDataValidation.query
                    .filter(AIFormDataValidation.form_data_id.is_(None))
                    .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                    .filter(AIFormDataValidation.form_item_id.in_(missing_item_ids))
                    .all()
                )
                existing_missing = {int(v.form_item_id): v for v in rows if v and v.form_item_id}

            svc = AIFormDataValidationService()
            ran_count = 0

            for entry in entries:
                if not entry:
                    continue
                try:
                    if getattr(entry, "id", None):
                        fd_id = int(entry.id)
                        existing = existing_by_fd.get(fd_id)
                        if (not run_all) and existing and (getattr(existing, "status", "") or "").lower() == "completed":
                            continue
                        rec, _ = svc.upsert_validation(
                            form_data_id=fd_id,
                            run_by_user_id=int(current_user.id),
                            sources=ai_sources,
                        )
                        existing_by_fd[fd_id] = rec
                        ran_count += 1
                        continue

                    fi_id = int(entry.form_item_id) if entry.form_item_id else None
                    if not fi_id:
                        continue
                    existing = existing_missing.get(fi_id)
                    if (not run_all) and existing and (getattr(existing, "status", "") or "").lower() == "completed":
                        continue
                    rec, _ = svc.upsert_missing_assigned_validation(
                        assignment_entity_status_id=int(assignment_entity_status.id),
                        form_item_id=int(fi_id),
                        run_by_user_id=int(current_user.id),
                        sources=ai_sources,
                    )
                    existing_missing[fi_id] = rec
                    ran_count += 1
                except Exception as e:
                    logger.debug("AI opinion run failed: %s", e)
                    current_app.logger.warning(
                        "AI opinion run failed for assignment=%s entry=%s",
                        assignment_entity_status.id,
                        getattr(entry, "id", None) or f"m:{getattr(entry, 'form_item_id', None)}",
                        exc_info=True,
                    )

            # Reuse the same aggregation logic as read route.
            linked_rows = (
                AIFormDataValidation.query
                .join(FormData, AIFormDataValidation.form_data_id == FormData.id)
                .filter(FormData.assignment_entity_status_id == int(assignment_entity_status.id))
                .all()
            )
            missing_rows = (
                AIFormDataValidation.query
                .filter(AIFormDataValidation.form_data_id.is_(None))
                .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                .all()
            )

            merged_by_form_item: dict[int, object] = {}

            def _pick_latest(existing_rec, candidate_rec):
                if not existing_rec:
                    return candidate_rec
                ex_updated = getattr(existing_rec, "updated_at", None)
                ca_updated = getattr(candidate_rec, "updated_at", None)
                if ex_updated and ca_updated:
                    return candidate_rec if ca_updated >= ex_updated else existing_rec
                if ca_updated and not ex_updated:
                    return candidate_rec
                if ex_updated and not ca_updated:
                    return existing_rec
                ex_id = int(getattr(existing_rec, "id", 0) or 0)
                ca_id = int(getattr(candidate_rec, "id", 0) or 0)
                return candidate_rec if ca_id >= ex_id else existing_rec

            for rec in linked_rows:
                fi_id = None
                try:
                    fd = getattr(rec, "form_data", None)
                    fi_id = int(getattr(fd, "form_item_id", 0) or 0)
                except Exception as e:
                    logger.debug("form_item_id get failed: %s", e)
                    fi_id = None
                if not fi_id:
                    continue
                merged_by_form_item[fi_id] = _pick_latest(merged_by_form_item.get(fi_id), rec)

            for rec in missing_rows:
                fi_id = None
                try:
                    fi_id = int(getattr(rec, "form_item_id", 0) or 0)
                except Exception as e:
                    logger.debug("form_item_id get failed: %s", e)
                    fi_id = None
                if not fi_id:
                    continue
                merged_by_form_item[fi_id] = _pick_latest(merged_by_form_item.get(fi_id), rec)

            opinions = {
                str(fi_id): _serialize_validation(rec)
                for fi_id, rec in merged_by_form_item.items()
            }
            return json_ok(
                success=True,
                ran_count=int(ran_count),
                opinionsByFormItemId=opinions,
            )
        except Exception as e:
            current_app.logger.error(
                "Error running validation summary opinions for ACS %s: %s",
                aes_id,
                e,
                exc_info=True,
            )
            return json_server_error("Failed to run AI opinions")

    @bp.route("/assignment_status/<int:aes_id>/validation_summary/opinions/events", methods=["GET"])
    @login_required
    def validation_summary_opinions_events(aes_id: int):
        """
        Stream assignment AI opinions item-by-item for entry form UI.

        Query params:
        - run_mode: missing|all (default missing)
        - include_non_reported: 1|0 (default 1)
        - hidden_fields: comma-separated FormItem ids to skip
        - hidden_sections: comma-separated FormSection ids to skip
        - ai_sources: comma-separated source list
        """
        denied_stream = _ai_beta_denied_sse_response()
        if denied_stream is not None:
            return denied_stream

        assignment_entity_status = _load_assignment_or_404(int(aes_id))

        from app.services.authorization_service import AuthorizationService
        from app.models.ai_validation import AIFormDataValidation
        from app.services.ai_formdata_validation_service import AIFormDataValidationService

        if not AuthorizationService.can_access_assignment(assignment_entity_status, current_user):
            return Response(
                "event: error\ndata: " + json.dumps({"error": "Access denied"}) + "\n\n",
                mimetype="text/event-stream",
            )

        hidden_field_ids = _parse_hidden_ids_arg("hidden_fields")
        hidden_section_ids = _parse_hidden_ids_arg("hidden_sections")
        include_non_reported = str(request.args.get("include_non_reported") or "1").strip().lower() in ("1", "true", "yes", "y", "on")
        run_mode = (request.args.get("run_mode", "missing") or "missing").strip().lower()
        run_all = run_mode == "all"
        ai_sources = _parse_ai_sources_arg()

        entries = _get_entries_for_summary(
            assignment_entity_status,
            hidden_field_ids=hidden_field_ids,
            hidden_section_ids=hidden_section_ids,
            include_non_reported=include_non_reported,
        )

        def _is_document_entry(entry) -> bool:
            try:
                fi = getattr(entry, "form_item", None)
                if not fi:
                    return False
                item_type = str(getattr(fi, "item_type", "") or "").strip().lower()
                if item_type == "document_field":
                    return True
                return bool(getattr(fi, "is_document_field", False))
            except Exception as e:
                logger.debug("is_document_field check failed: %s", e)
                return False

        # Explicitly skip document fields for this entry-form AI opinions flow.
        entries = [e for e in entries if e and not _is_document_entry(e)]

        # Sort by page → section → subsection → item order so processing follows form layout.
        sort_key_fn = _build_page_section_item_sort_key(assignment_entity_status)
        entries = sorted(entries, key=sort_key_fn)

        form_data_ids = [int(e.id) for e in entries if e and getattr(e, "id", None)]
        existing_fd = {}
        if form_data_ids:
            rows = AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all()
            existing_fd = {int(v.form_data_id): v for v in rows if v and v.form_data_id}

        missing_item_ids = [int(e.form_item_id) for e in entries if e and not getattr(e, "id", None) and e.form_item_id]
        missing_item_ids = list(dict.fromkeys(missing_item_ids))
        existing_missing = {}
        if missing_item_ids:
            rows = (
                AIFormDataValidation.query
                .filter(AIFormDataValidation.form_data_id.is_(None))
                .filter(AIFormDataValidation.assignment_entity_status_id == int(assignment_entity_status.id))
                .filter(AIFormDataValidation.form_item_id.in_(missing_item_ids))
                .all()
            )
            existing_missing = {int(v.form_item_id): v for v in rows if v and v.form_item_id}

        def _entry_fi(entry):
            try:
                if entry and getattr(entry, "form_item_id", None):
                    return int(entry.form_item_id)
            except Exception as e:
                logger.debug("form_item_id int failed: %s", e)
                return None
            return None

        def _entry_existing_validation(entry):
            try:
                if entry and getattr(entry, "id", None):
                    return existing_fd.get(int(entry.id))
                fi_id = _entry_fi(entry)
                return existing_missing.get(int(fi_id)) if fi_id else None
            except Exception as e:
                logger.debug("existing_missing get failed: %s", e)
                return None

        existing_by_form_item: dict[str, dict] = {}
        to_run = []
        for entry in entries:
            fi_id = _entry_fi(entry)
            if not fi_id:
                continue
            existing_rec = _entry_existing_validation(entry)
            existing_payload = _serialize_validation(existing_rec) if existing_rec else {}
            if existing_payload:
                existing_by_form_item[str(fi_id)] = existing_payload

            if run_all:
                to_run.append(entry)
            else:
                status = (getattr(existing_rec, "status", "") or "").lower() if existing_rec else ""
                if not existing_rec or status != "completed":
                    to_run.append(entry)

        app_obj = current_app._get_current_object()
        user_id = int(getattr(current_user, "id", 0) or 0) or None

        def _send(event_name: str, payload: dict) -> str:
            return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        def generate():
            total_items = len(entries)
            completed = len(existing_by_form_item)
            yield _send("init", {
                "total_items": total_items,
                "completed": completed,
                "to_run_count": len(to_run),
                "existingOpinionsByFormItemId": existing_by_form_item,
            })
            yield ": keepalive\n\n"

            if not to_run:
                yield _send("done", {
                    "completed": completed,
                    "total_items": total_items,
                    "opinionsByFormItemId": existing_by_form_item,
                })
                return

            with app_obj.app_context():
                svc = AIFormDataValidationService()
                opinions_map = dict(existing_by_form_item)
                for entry in to_run:
                    fi_id = _entry_fi(entry)
                    if not fi_id:
                        continue
                    yield _send("started", {"form_item_id": int(fi_id)})
                    try:
                        if getattr(entry, "id", None):
                            rec, _ = svc.upsert_validation(
                                form_data_id=int(entry.id),
                                run_by_user_id=user_id,
                                sources=ai_sources,
                            )
                        else:
                            rec, _ = svc.upsert_missing_assigned_validation(
                                assignment_entity_status_id=int(assignment_entity_status.id),
                                form_item_id=int(fi_id),
                                run_by_user_id=user_id,
                                sources=ai_sources,
                            )
                        payload = _serialize_validation(rec)
                    except Exception as e:
                        payload = {
                            "status": "failed",
                            "verdict": "uncertain",
                            "opinion_text": f"Validation failed: {e}",
                            "suggestion": None,
                        }
                        current_app.logger.warning(
                            "AI opinion stream failed for assignment=%s form_item=%s",
                            assignment_entity_status.id,
                            fi_id,
                            exc_info=True,
                        )

                    opinions_map[str(fi_id)] = payload
                    completed += 1
                    yield _send("item", {
                        "form_item_id": int(fi_id),
                        "validation": payload,
                        "completed": completed,
                        "total_items": total_items,
                    })
                    yield ": keepalive\n\n"

                yield _send("done", {
                    "completed": completed,
                    "total_items": total_items,
                    "opinionsByFormItemId": opinions_map,
                })

        resp = Response(generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

