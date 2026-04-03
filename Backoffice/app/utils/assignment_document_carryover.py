"""
Entity document repository for assignment forms.

Focal-point uploads for a given entity and form template build a shared pool of
documents. When a document field has ``config.cross_assignment_period_reuse`` and a
fixed ``config.document_type``, the entry form can satisfy that field from an
existing document in that pool (including one first uploaded under a different
assignment period) if the stored document ``period`` spans all years inferred
from the current assignment's ``period_name``.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy.orm import joinedload

from app.models import AssignedForm, AssignmentEntityStatus, FormItem, SubmittedDocument

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_years_from_text(text: str | None) -> list[int]:
    if not text:
        return []
    return sorted({int(m.group(0)) for m in _YEAR_RE.finditer(str(text))})


def assignment_target_years(period_name: str | None) -> set[int]:
    """Infer which calendar years an assignment period refers to.

    - Single year in the label → that year only.
    - Multiple years: if they form a contiguous range, use every year in the range;
      otherwise use the explicit set of years found (e.g. two non-adjacent years).
    """
    years = extract_years_from_text(period_name)
    if not years:
        return set()
    uniq = sorted(set(years))
    if len(uniq) == 1:
        return {uniq[0]}
    ymin, ymax = uniq[0], uniq[-1]
    if len(uniq) == (ymax - ymin + 1):
        return set(range(ymin, ymax + 1))
    return set(uniq)


def document_period_year_bounds(period_str: str | None) -> tuple[int, int] | None:
    """Min/max year mentioned in the document period string (inclusive span)."""
    years = extract_years_from_text(period_str)
    if not years:
        return None
    return min(years), max(years)


def document_covers_assignment_years(period_str: str | None, assignment_years: set[int]) -> bool:
    if not assignment_years:
        return False
    bounds = document_period_year_bounds(period_str)
    if not bounds:
        return False
    lo, hi = bounds
    return all(lo <= y <= hi for y in assignment_years)


def _norm_doc_type(value: Any) -> str:
    return (str(value).strip().casefold() if value is not None else "")


def document_types_match(field_expected: str | None, submitted_type: str | None) -> bool:
    fe = _norm_doc_type(field_expected)
    st = _norm_doc_type(submitted_type)
    if not fe:
        return False
    return fe == st


def _config_bool_true(value: Any) -> bool:
    """JSON/config flags may be bool, int, or string."""
    if value is True:
        return True
    if value in (1, "1", "true", "True", "on", "yes"):
        return True
    return False


def _same_document_slot_across_versions(source: FormItem | None, field: FormItem) -> bool:
    """Same logical field after template republish (new FormItem row, same template/section/order)."""
    if not source or source.item_type != "document_field":
        return False
    try:
        return (
            source.template_id == field.template_id
            and source.section_id == field.section_id
            and float(source.order) == float(field.order)
        )
    except (TypeError, ValueError):
        return False


def _document_matches_carryover_field(
    doc: SubmittedDocument,
    field: FormItem,
    field_cfg: dict,
    source_items: dict[int, FormItem],
) -> bool:
    """Whether *doc* can satisfy *field* for repository carryover (type / slot semantics)."""
    expected_raw = field_cfg.get("document_type")
    expected_norm = _norm_doc_type(expected_raw) if expected_raw is not None else ""

    if doc.form_item_id == field.id:
        return True

    if expected_norm and document_types_match(expected_raw, doc.document_type):
        return True

    src = source_items.get(doc.form_item_id) if doc.form_item_id else None
    if not src:
        return False

    if not expected_norm and _same_document_slot_across_versions(src, field):
        return True

    src_expected_norm = _norm_doc_type((src.config or {}).get("document_type"))
    if expected_norm and src_expected_norm and expected_norm == src_expected_norm:
        return True

    if expected_norm and _same_document_slot_across_versions(src, field):
        return True

    return False


def find_carryover_documents_for_field(
    field: FormItem,
    assignment_entity_status: AssignmentEntityStatus,
) -> list[SubmittedDocument]:
    """Documents in this entity's repository (other assignment rows, same template) that cover this period."""
    cfg = field.config or {}
    if not _config_bool_true(cfg.get("cross_assignment_period_reuse")):
        return []

    aes = assignment_entity_status
    current_af = aes.assigned_form
    if not current_af:
        return []

    target_years = assignment_target_years(current_af.period_name)
    if not target_years:
        return []

    template_id = current_af.template_id
    q = (
        SubmittedDocument.query.options(joinedload(SubmittedDocument.uploaded_by_user))
        .join(AssignmentEntityStatus, SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(
            AssignmentEntityStatus.entity_type == aes.entity_type,
            AssignmentEntityStatus.entity_id == aes.entity_id,
            AssignmentEntityStatus.id != aes.id,
            AssignedForm.template_id == template_id,
            SubmittedDocument.form_item_id.isnot(None),
        )
        .order_by(SubmittedDocument.uploaded_at.desc())
    )

    candidates = q.all()
    fi_ids = {d.form_item_id for d in candidates if d.form_item_id}
    source_items: dict[int, FormItem] = {}
    if fi_ids:
        for fi in FormItem.query.filter(FormItem.id.in_(fi_ids)):
            source_items[fi.id] = fi

    out: list[SubmittedDocument] = []
    seen: set[int] = set()
    for doc in candidates:
        if doc.id in seen:
            continue
        if not _document_matches_carryover_field(doc, field, cfg, source_items):
            continue
        if not document_covers_assignment_years(doc.period, target_years):
            continue
        out.append(doc)
        seen.add(doc.id)
    return out


def _merge_docs_for_key(
    key: str,
    carryover: Iterable[SubmittedDocument],
    d: dict[str, SubmittedDocument | list[SubmittedDocument]],
) -> None:
    merged: list[SubmittedDocument] = []
    seen_ids: set[int] = set()

    existing = d.get(key)
    if existing:
        if isinstance(existing, list):
            for x in existing:
                if x.id not in seen_ids:
                    merged.append(x)
                    seen_ids.add(x.id)
        else:
            merged.append(existing)
            seen_ids.add(existing.id)

    for c in carryover:
        if c.id in seen_ids:
            continue
        merged.append(c)
        seen_ids.add(c.id)

    if not merged:
        return
    d[key] = merged[0] if len(merged) == 1 else merged


def merge_carryover_into_submitted_documents_dict(
    existing_submitted_documents_dict: dict[str, SubmittedDocument | list[SubmittedDocument]],
    assignment_entity_status: AssignmentEntityStatus,
    all_sections: list[Any],
) -> set[int]:
    """Mutate *existing_submitted_documents_dict* with qualifying repository documents.

    Returns IDs of documents linked to a different assignment row (read-only in this AES UI).
    """
    carryover_ids: set[int] = set()
    for section in all_sections:
        if not hasattr(section, "fields_ordered"):
            continue
        for field in section.fields_ordered:
            if not getattr(field, "is_document_field", False):
                continue
            key = f"field_value[{field.id}]"
            carry = find_carryover_documents_for_field(field, assignment_entity_status)
            if not carry:
                continue
            for c in carry:
                carryover_ids.add(c.id)
            _merge_docs_for_key(key, carry, existing_submitted_documents_dict)
    return carryover_ids
