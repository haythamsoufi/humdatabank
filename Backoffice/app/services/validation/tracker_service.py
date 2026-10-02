"""Validation dashboard tracker — assignment progress by country and reporting period."""

from __future__ import annotations

import logging
import threading
from contextlib import ExitStack, contextmanager, nullcontext
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy.orm import joinedload

from app.models import FormData, FormItem, SubmittedDocument
from app.models.core import Country
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.enums import status_display_label
from app.services.data_quality.helpers import (
    active_country_map_query,
    load_form_data_by_kpi,
    parse_period_year,
    resolve_assignment_aes,
)
from app.services.organization.country_service import fds_member_user_display_name
from app.services.validation.pack_registry import ValidationTracker, get_pack, list_packs
from app.services.data_quality.service import get_rule_pack_for_template
from .dashboard_service import global_periods_for_template

_STATUS_RANK = {
    "approved": 5,
    "submitted": 4,
    "sent_for_review": 3,
    "requires_revision": 3,
    "in_progress": 2,
    "pending": 1,
}


def _status_column_meta(spec: dict[str, Any]) -> dict[str, Any]:
    """Pass a product tracker's status column through without interpreting it."""
    meta: dict[str, Any] = {"key": spec.get("key"), "label": spec.get("label") or ""}
    legend = spec.get("legend") or ()
    filters = spec.get("filters") or ()
    if legend:
        meta["legend"] = [str(item) for item in legend if item]
    filter_rows = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        label = item.get("label")
        if value and label:
            filter_rows.append({"value": str(value), "label": str(label)})
    if filter_rows:
        meta["filters"] = filter_rows
    return meta


def _status_value(aes: AssignmentEntityStatus | None) -> str:
    if aes is None:
        return "no_assignment"
    raw = aes.status.value if hasattr(aes.status, "value") else str(aes.status)
    return raw or "pending"


def _section_fill_status(ratio: float) -> str:
    if ratio <= 0:
        return "not_started"
    if ratio >= 0.999:
        return "complete"
    return "in_progress"


def _overall_completion_rate(section_ratios: dict[str, float]) -> float:
    if not section_ratios:
        return 0.0
    values = list(section_ratios.values())
    return round(sum(values) / len(values) * 100, 1)


def _document_field_map(
    template_id: int,
    document_specs: tuple[dict[str, str], ...],
    document_matches,
) -> dict[str, list[int]]:
    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.item_type == "document_field",
            FormItem.archived == False,  # noqa: E712
        ).all()
    )
    mapping: dict[str, list[int]] = {spec["key"]: [] for spec in document_specs}
    for item in items:
        label = (item.label or "").strip()
        configured = ""
        cfg = getattr(item, "config", None)
        if isinstance(cfg, dict) and isinstance(cfg.get("document_type"), str):
            configured = cfg["document_type"].strip()
        for spec in document_specs:
            spec_label = spec["label"]
            configured_match = bool(configured) and (
                configured == spec_label
                or (document_matches is not None and document_matches(configured, spec_label))
            )
            label_match = label == spec_label or (
                document_matches is not None and document_matches(label, spec_label)
            )
            if configured_match or label_match:
                mapping[spec["key"]].append(item.id)
                break
    return mapping


def _bulk_kpi_data_by_aes(
    aes_ids: list[int],
    template_id: int,
    version_id: int | None,
    indicator_code,
) -> dict[int, dict[str, tuple[FormData | None, FormItem | None]]]:
    if not aes_ids:
        return {}

    items = (
        FormItem.query.filter(
            FormItem.template_id == template_id,
            FormItem.archived == False,  # noqa: E712
            FormItem.indicator_bank_id.isnot(None),
        )
        .options(joinedload(FormItem.indicator_bank))
        .all()
    )
    if version_id:
        items = [i for i in items if i.version_id == version_id or i.version_id is None]

    kpi_to_item: dict[str, FormItem] = {}
    for item in items:
        bank = item.indicator_bank
        code = indicator_code(bank) if indicator_code is not None else None
        if not code or code in kpi_to_item:
            continue
        kpi_to_item[code] = item

    item_ids = [i.id for i in kpi_to_item.values()]
    data_rows = (
        FormData.query.filter(
            FormData.assignment_entity_status_id.in_(aes_ids),
            FormData.form_item_id.in_(item_ids),
        ).all()
        if item_ids
        else []
    )

    data_by_aes_item: dict[tuple[int, int], FormData] = {}
    for row in data_rows:
        data_by_aes_item[(row.assignment_entity_status_id, row.form_item_id)] = row

    result: dict[int, dict[str, tuple[FormData | None, FormItem | None]]] = {}
    for aes_id in aes_ids:
        per_aes: dict[str, tuple[FormData | None, FormItem | None]] = {}
        for code, item in kpi_to_item.items():
            per_aes[code] = (data_by_aes_item.get((aes_id, item.id)), item)
        result[aes_id] = per_aes
    return result


def _exact_period_assignments(template_id: int, period_name: str) -> list:
    """Assignments whose period name matches exactly.

    When several share the name, the caller picks per country instead of using
    whichever row the database returns first.
    """
    query = AssignedForm.query.filter(
        AssignedForm.template_id == template_id,
        AssignedForm.period_name == period_name,
    )
    ordered = query.order_by(AssignedForm.id.desc())
    rows = ordered.all()
    if isinstance(rows, list):
        return rows
    single = query.first()
    return [single] if single is not None else []


def _merge_trackers(trackers: list[ValidationTracker]) -> ValidationTracker | None:
    """Combine product trackers. A single tracker is returned unchanged."""
    present = [tracker for tracker in trackers if tracker is not None]
    if not present:
        return None
    if len(present) == 1:
        return present[0]

    def section_ratios(kpi_data, **kwargs):
        merged: dict[str, float] = {}
        for tracker in present:
            if tracker.section_ratios is None:
                continue
            merged.update(tracker.section_ratios(kpi_data, **kwargs) or {})
        return merged

    def assignment_statuses(*args, **kwargs):
        merged: dict[str, dict] = {}
        for tracker in present:
            if tracker.assignment_statuses is None:
                continue
            merged.update(tracker.assignment_statuses(*args, **kwargs) or {})
        return merged

    document_matches = next((tracker.document_matches for tracker in present if tracker.document_matches), None)
    indicator_code = next((tracker.indicator_code for tracker in present if tracker.indicator_code), None)
    required: list[str] = []
    for tracker in present:
        for key in tracker.required_document_keys:
            if key not in required:
                required.append(key)
    prepares = [tracker.prepare_rows for tracker in present if tracker.prepare_rows is not None]

    @contextmanager
    def prepare_rows(aes_list):
        with ExitStack() as stack:
            for prepare in prepares:
                stack.enter_context(prepare(aes_list))
            yield

    return ValidationTracker(
        sections=tuple(spec for tracker in present for spec in tracker.sections),
        documents=tuple(spec for tracker in present for spec in tracker.documents),
        section_ratios=section_ratios if any(tracker.section_ratios for tracker in present) else None,
        document_matches=document_matches,
        indicator_code=indicator_code,
        required_document_keys=tuple(required),
        statuses=tuple(spec for tracker in present for spec in tracker.statuses),
        assignment_statuses=(
            assignment_statuses if any(tracker.assignment_statuses for tracker in present) else None
        ),
        prepare_rows=prepare_rows if prepares else None,
    )


def _tracker_for_template(template) -> ValidationTracker | None:
    """Tracker columns for this template.

    The saved rule pack contributes its columns. Packs that name this template
    add theirs as well, so a product check can show up when the template still
    uses the general pack.
    """
    version = getattr(template, "published_version", None)
    data_quality_on = getattr(version, "enable_data_quality", None) is True
    pack = None
    primary = None
    if data_quality_on:
        pack_code = get_rule_pack_for_template(template)
        pack = get_pack(pack_code) if isinstance(pack_code, str) else None
        primary = pack.tracker if pack is not None else None
    extras: list[ValidationTracker] = []
    template_id = getattr(template, "id", None)
    if isinstance(template_id, int):
        for extra in list_packs():
            if pack is not None and extra.code == pack.code:
                continue
            if template_id not in extra.template_ids:
                continue
            if extra.tracker is not None:
                extras.append(extra.tracker)
    if not extras:
        return primary
    return _merge_trackers([primary, *extras])


_tracker_flight_lock = threading.Lock()
_tracker_flight: dict[tuple, tuple[threading.Event, dict]] = {}


def build_tracker_data(template_id: int, period_name: str) -> dict[str, Any]:
    """Rows, aggregate stats, and map payload for the validation dashboard tracker tab.

    Overlapping requests for the same template and period share one computation.
    """
    key = (int(template_id), str(period_name))
    with _tracker_flight_lock:
        current = _tracker_flight.get(key)
        if current is None:
            done = threading.Event()
            box: dict[str, Any] = {}
            _tracker_flight[key] = (done, box)
            leader = True
        else:
            done, box = current
            leader = False
    if not leader:
        done.wait(timeout=120)
        if "error" in box:
            raise box["error"]
        if "result" in box:
            return box["result"]
    try:
        result = _compute_tracker_data(template_id, period_name)
        if leader:
            box["result"] = result
        return result
    except Exception as exc:
        if leader:
            box["error"] = exc
        raise
    finally:
        if leader:
            done.set()
            with _tracker_flight_lock:
                if _tracker_flight.get(key, (None,))[0] is done:
                    _tracker_flight.pop(key, None)


def _compute_tracker_data(template_id: int, period_name: str) -> dict[str, Any]:
    assignments = _exact_period_assignments(template_id, period_name)
    primary = max(assignments, key=lambda item: item.id or 0) if assignments else None

    countries = (
        active_country_map_query()
        .options(joinedload(Country.fds_member_user))
        .all()
    )

    template = primary.template if primary else None
    version_id = template.published_version_id if template else None
    tracker = _tracker_for_template(template)
    section_specs = tracker.sections if tracker else ()
    document_specs = tracker.documents if tracker else ()
    status_specs = tracker.statuses if tracker else ()
    doc_field_map = (
        _document_field_map(template_id, document_specs, tracker.document_matches if tracker else None)
        if document_specs
        else {}
    )
    all_doc_item_ids = [iid for ids in doc_field_map.values() for iid in ids]
    delegation_review_enabled = any(
        bool(getattr(item, "requires_delegation_review", False)) for item in assignments
    )

    aes_by_country: dict[int, AssignmentEntityStatus] = {}
    resolved_period_by_country: dict[int, str] = {}
    if assignments:
        assignment_ids = [item.id for item in assignments]
        rank = {item.id: item.id or 0 for item in assignments}
        aes_rows = (
            AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.assigned_form_id.in_(assignment_ids),
                AssignmentEntityStatus.entity_type == "country",
            ).all()
        )
        for aes in aes_rows:
            current = aes_by_country.get(aes.entity_id)
            if current is None or rank.get(aes.assigned_form_id, 0) >= rank.get(current.assigned_form_id, 0):
                aes_by_country[aes.entity_id] = aes
                resolved_period_by_country[aes.entity_id] = period_name
    else:
        for country in countries:
            aes, resolved = resolve_assignment_aes(template_id, "country", country.id, period_name)
            if aes:
                aes_by_country[country.id] = aes
                resolved_period_by_country[country.id] = resolved

    aes_ids = [aes.id for aes in aes_by_country.values()]
    kpi_by_aes = (
        _bulk_kpi_data_by_aes(
            aes_ids,
            template_id,
            version_id,
            tracker.indicator_code if tracker else None,
        )
        if section_specs
        else {}
    )

    submitted_docs: list[SubmittedDocument] = []
    if aes_ids and all_doc_item_ids:
        submitted_docs = (
            SubmittedDocument.query.filter(
                SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                SubmittedDocument.form_item_id.in_(all_doc_item_ids),
            ).all()
        )
    doc_lookup: set[tuple[int, str]] = set()
    reverse_item_key: dict[int, str] = {}
    for key, item_ids in doc_field_map.items():
        for item_id in item_ids:
            reverse_item_key[item_id] = key
    for doc in submitted_docs:
        doc_key = reverse_item_key.get(doc.form_item_id)
        if doc_key:
            doc_lookup.add((doc.assignment_entity_status_id, doc_key))

    rows: list[dict[str, Any]] = []
    map_countries: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    section_complete_counts = {spec["key"]: 0 for spec in section_specs}
    docs_both_required = 0

    scope = (
        tracker.prepare_rows(list(aes_by_country.values()))
        if tracker is not None and tracker.prepare_rows is not None
        else nullcontext()
    )
    with scope:
        for country in countries:
            aes = aes_by_country.get(country.id)
            if not aes:
                continue

            status = _status_value(aes)
            status_counts[status] = status_counts.get(status, 0) + 1

            sections: dict[str, str] = {spec["key"]: "not_started" for spec in section_specs}
            section_ratios: dict[str, float] = {spec["key"]: 0.0 for spec in section_specs}
            if section_specs and tracker is not None and tracker.section_ratios is not None:
                kpi_data = kpi_by_aes.get(aes.id)
                if kpi_data is None:
                    kpi_data = load_form_data_by_kpi(aes.id, template_id, version_id)
                ratios = tracker.section_ratios(
                    kpi_data,
                    aes_id=aes.id,
                    template_id=template_id,
                    version_id=version_id,
                )
                for key, ratio in ratios.items():
                    if key not in section_ratios:
                        continue
                    section_ratios[key] = ratio
                    fill = _section_fill_status(ratio)
                    sections[key] = fill
                    if fill == "complete":
                        section_complete_counts[key] = section_complete_counts.get(key, 0) + 1

            documents: dict[str, bool] = {spec["key"]: False for spec in document_specs}
            for spec in document_specs:
                documents[spec["key"]] = (aes.id, spec["key"]) in doc_lookup

            required_keys = tracker.required_document_keys if tracker else ()
            if required_keys and all(documents.get(key) for key in required_keys):
                docs_both_required += 1

            statuses: dict[str, dict] = {spec["key"]: {"state": "unknown", "label": "—", "detail": ""} for spec in status_specs}
            if status_specs and tracker is not None and tracker.assignment_statuses is not None:
                try:
                    computed = tracker.assignment_statuses(
                        aes,
                        template_id=template_id,
                        version_id=version_id,
                    ) or {}
                except Exception:
                    logger.exception("Tracker status failed for assignment %s", aes.id)
                    computed = {}
                for spec in status_specs:
                    cell = computed.get(spec["key"])
                    if isinstance(cell, dict) and cell.get("state"):
                        statuses[spec["key"]] = cell

            fds_user = country.fds_member_user
            row = {
                "country_id": country.id,
                "country_name": country.name,
                "country_iso3": country.iso3,
                "region": country.region,
                "fds_member_user_id": country.fds_member_user_id,
                "fds_member_name": fds_member_user_display_name(fds_user) or None,
                "period_name": resolved_period_by_country.get(country.id),
                "assignment_id": aes.assigned_form_id,
                "status": status,
                "status_label": status_display_label(status),
                "submitted_at": aes.submitted_at.isoformat() if aes.submitted_at else None,
                "sections": sections,
                "section_ratios": section_ratios,
                "completion_rate": _overall_completion_rate(section_ratios),
                "documents": documents,
                "statuses": statuses,
            }
            rows.append(row)

            map_countries.append(
                {
                    "country_id": country.id,
                    "iso3": country.iso3,
                    "label": country.name,
                    "status": status,
                    "status_rank": _STATUS_RANK.get(status, 0),
                }
            )

    submitted_like = sum(
        1 for r in rows
        if r["status"] in (
            ("submitted", "approved", "sent_for_review")
            if delegation_review_enabled
            else ("submitted", "approved")
        )
    )
    approved_count = sum(1 for r in rows if r["status"] == "approved")

    stats = {
        "country_count": len(rows),
        "assigned_count": len(rows),
        "by_status": status_counts,
        "delegation_review_enabled": delegation_review_enabled,
        "submitted_count": submitted_like,
        "approved_count": approved_count,
        "in_progress_count": status_counts.get("in_progress", 0),
        "pending_count": status_counts.get("pending", 0),
        "documents_both_required_count": docs_both_required,
        "section_complete_counts": section_complete_counts,
        "reporting_year": parse_period_year(period_name),
    }

    return {
        "template_id": template_id,
        "period_name": period_name,
        "delegation_review_enabled": delegation_review_enabled,
        "rows": rows,
        "stats": stats,
        "map": {"countries": map_countries},
        "documents_meta": [{"key": s["key"], "label": s["label"]} for s in document_specs],
        "sections_meta": [{"key": s["key"], "label": s["label"]} for s in section_specs],
        "statuses_meta": [_status_column_meta(spec) for spec in status_specs],
        "required_document_keys": list(tracker.required_document_keys) if tracker else [],
    }


def tracker_periods_for_template(template_id: int) -> list[str]:
    return global_periods_for_template(template_id)
