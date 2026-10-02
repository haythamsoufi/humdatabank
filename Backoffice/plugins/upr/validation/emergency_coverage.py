"""Compare reported emergencies with the calculated list for a UPR assignment.

Reporting stores the choice on a repeat section. Planning stores it as matrix
rows (Emergency Appeals) and as selectable column headers (Funding Requirements).
The calculated list is the set that is applicable right now (country, appeal
type, and the assignment period). This module flags three gaps. None of them
block submission.

- missing: an applicable emergency was not added
- not applicable: the saved emergency is not an operation for this country
- no longer applicable: it is a country operation, but the current filters exclude it
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_COVERAGE_BATCH: ContextVar = ContextVar("upr_coverage_batch", default=None)

RULE_MISSING = "emergency_missing"
RULE_NOT_APPLICABLE = "emergency_not_applicable"
RULE_NO_LONGER_APPLICABLE = "emergency_no_longer_applicable"


@dataclass(frozen=True)
class EmergencyRef:
    code: str
    label: str


@dataclass(frozen=True)
class EmergencyCoverage:
    applicable: tuple[EmergencyRef, ...]
    missing: tuple[EmergencyRef, ...]
    not_applicable: tuple[EmergencyRef, ...]
    no_longer_applicable: tuple[EmergencyRef, ...]

    @property
    def has_issues(self) -> bool:
        return bool(self.missing or self.not_applicable or self.no_longer_applicable)


@dataclass(frozen=True)
class FieldEmergencyCoverage:
    section_name: str
    coverage: EmergencyCoverage


def classify_emergency_coverage(
    applicable: list[EmergencyRef] | tuple[EmergencyRef, ...],
    selected: list[EmergencyRef] | tuple[EmergencyRef, ...],
    country_codes: set[str] | frozenset[str],
) -> EmergencyCoverage:
    """Split a saved selection against the current applicable list."""
    applicable_by_code: dict[str, EmergencyRef] = {}
    for op in applicable:
        code = _code(op.code)
        if code and code not in applicable_by_code:
            applicable_by_code[code] = op

    selected_by_code: dict[str, EmergencyRef] = {}
    unlabeled: list[EmergencyRef] = []
    for op in selected:
        code = _code(op.code)
        if not code:
            if op.label:
                unlabeled.append(op)
            continue
        selected_by_code.setdefault(code, op)

    known = {_code(code) for code in country_codes if _code(code)}
    missing = tuple(op for code, op in applicable_by_code.items() if code not in selected_by_code)
    not_applicable: list[EmergencyRef] = list(unlabeled)
    no_longer: list[EmergencyRef] = []
    for code, op in selected_by_code.items():
        if code in applicable_by_code:
            continue
        if code in known:
            no_longer.append(op)
        else:
            not_applicable.append(op)

    return EmergencyCoverage(
        applicable=tuple(applicable_by_code.values()),
        missing=missing,
        not_applicable=tuple(not_applicable),
        no_longer_applicable=tuple(no_longer),
    )


def coverage_messages(field: FieldEmergencyCoverage) -> list[dict[str, str]]:
    """Warning copy for each gap on one repeat section. Empty when nothing is wrong."""
    coverage = field.coverage
    section = field.section_name or "Emergency appeals"
    messages: list[dict[str, str]] = []
    if coverage.missing:
        messages.append({
            "rule_code": RULE_MISSING,
            "label": "Applicable emergencies not added",
            "message": _missing_message(section, coverage.missing),
        })
    if coverage.not_applicable:
        messages.append({
            "rule_code": RULE_NOT_APPLICABLE,
            "label": "Emergency not applicable",
            "message": _entered_message(
                section,
                coverage.not_applicable,
                "not an applicable emergency for this country",
            ),
        })
    if coverage.no_longer_applicable:
        messages.append({
            "rule_code": RULE_NO_LONGER_APPLICABLE,
            "label": "Emergency no longer applicable",
            "message": _entered_message(
                section,
                coverage.no_longer_applicable,
                "no longer applicable for this reporting period",
            ),
        })
    return messages


def tracker_status(fields: list[FieldEmergencyCoverage] | None) -> dict[str, str]:
    """One tracker cell for every emergency repeat section on the assignment."""
    if fields is None:
        return {
            "state": "unknown",
            "label": "—",
            "detail": "The emergency list is not available yet.",
        }
    if not fields:
        return {"state": "not_used", "label": "—", "detail": ""}

    missing: list[str] = []
    not_applicable: list[str] = []
    no_longer: list[str] = []
    for field in fields:
        missing.extend(op.label for op in field.coverage.missing)
        not_applicable.extend(op.label for op in field.coverage.not_applicable)
        no_longer.extend(op.label for op in field.coverage.no_longer_applicable)

    if not missing and not not_applicable and not no_longer:
        return {
            "state": "ok",
            "label": "Complete",
            "detail": "Every applicable emergency has been added.",
        }

    parts: list[str] = []
    details: list[str] = []
    if missing:
        parts.append(f"Missing {len(missing)}")
        details.append("Not added: " + "; ".join(missing))
    if not_applicable:
        parts.append("Not applicable" if len(not_applicable) == 1 else f"Not applicable {len(not_applicable)}")
        details.append("Not applicable: " + "; ".join(not_applicable))
    if no_longer:
        parts.append(
            "No longer applicable"
            if len(no_longer) == 1
            else f"No longer applicable {len(no_longer)}"
        )
        details.append("No longer applicable: " + "; ".join(no_longer))

    kinds = sum(1 for bucket in (missing, not_applicable, no_longer) if bucket)
    if kinds > 1:
        state = "mixed"
    elif missing:
        state = "missing"
    elif not_applicable:
        state = "not_applicable"
    else:
        state = "no_longer_applicable"
    return {"state": state, "label": " · ".join(parts), "detail": ". ".join(details) + "."}


def checks_from_fields(fields: list[FieldEmergencyCoverage] | None) -> list[dict[str, str]]:
    """Merge every section into one warning per rule, so the dashboard shows each gap once."""
    if not fields:
        return []
    grouped: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for field in fields:
        for message in coverage_messages(field):
            code = message["rule_code"]
            if code not in grouped:
                order.append(code)
                grouped[code] = []
            grouped[code].append(message)
    merged: list[dict[str, str]] = []
    for code in order:
        rows = grouped[code]
        merged.append({
            "rule_code": code,
            "label": rows[0]["label"],
            "message": " ".join(row["message"] for row in rows),
        })
    return merged


def load_field_coverages(aes) -> list[FieldEmergencyCoverage] | None:
    """Read saved emergency rows, headers, and repeat entries against the current list.

    Returns None when the emergency catalogue cannot be read, so callers do not
    treat an empty list as "nothing is applicable".
    """
    batch = _COVERAGE_BATCH.get()
    if batch is not None:
        return batch.coverages(aes)
    return _load_field_coverages(aes)


def _load_field_coverages(aes) -> list[FieldEmergencyCoverage] | None:
    if aes is None or not getattr(aes, "id", None):
        return []
    if not _catalogue_available():
        return None

    sources = _emergency_sources(aes)
    if not sources:
        return []

    from plugins.emergency_operations.section_binding import (
        _assignment_period_for_aes,
        _country_iso_for_aes,
        _fetch_ordered_operations,
    )

    iso = _country_iso_for_aes(aes)
    if not iso:
        return []
    period = _assignment_period_for_aes(aes)
    country_codes = _country_operation_codes(iso)
    if country_codes is None:
        return None

    coverages: list[FieldEmergencyCoverage] = []
    for section_name, plugin_config, selected in sources:
        try:
            operations = _fetch_ordered_operations(iso, plugin_config, period) or []
        except Exception:
            logger.debug("Applicable emergency lookup failed", exc_info=True)
            return None
        applicable = [ref for op in operations if (ref := _ref_from_operation(op))]
        coverages.append(FieldEmergencyCoverage(
            section_name=section_name,
            coverage=classify_emergency_coverage(applicable, selected, country_codes),
        ))
    return coverages


def _code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _labels(ops: tuple[EmergencyRef, ...]) -> str:
    return "; ".join(op.label for op in ops if op.label)


def _missing_message(section: str, missing: tuple[EmergencyRef, ...]) -> str:
    count = len(missing)
    noun = "emergency" if count == 1 else "emergencies"
    verb = "was" if count == 1 else "were"
    return (
        f"{count} applicable {noun} {verb} not added to {section}: {_labels(missing)}. "
        "This does not block submission."
    )


def _entered_message(section: str, entered: tuple[EmergencyRef, ...], reason: str) -> str:
    count = len(entered)
    noun = "emergency" if count == 1 else "emergencies"
    verb = "is" if count == 1 else "are"
    return (
        f"{count} {noun} added to {section} {verb} {reason}: {_labels(entered)}. "
        "This does not block submission."
    )


def _ref_from_operation(op: dict) -> EmergencyRef | None:
    from plugins.emergency_operations.appeal_group import format_operation_label

    code = _code(op.get("code"))
    if not code:
        return None
    label = format_operation_label(op.get("name"), code, op.get("part_of")) or code
    return EmergencyRef(code=code, label=label)


def _ref_from_saved(entry) -> EmergencyRef | None:
    from plugins.emergency_operations.appeal_group import format_operation_label, parse_operation_label

    if entry is None:
        return None
    disagg = getattr(entry, "disagg_data", None)
    code = ""
    name = ""
    if isinstance(disagg, dict):
        code = _code(disagg.get("code"))
        name = str(disagg.get("name") or "").strip()
    text = str(getattr(entry, "value", None) or "").strip()
    if text and not code:
        parsed = parse_operation_label(text)
        code = _code(parsed.get("code"))
        name = name or str(parsed.get("name") or "").strip()
    if not code and not name and not text:
        return None
    label = format_operation_label(name, code) if (name or code) else text
    return EmergencyRef(code=code, label=label or text or code)


def _catalogue_available() -> bool:
    try:
        from plugins.emergency_operations.data_store import get_data_store

        return get_data_store().load_cached() is not None
    except Exception:
        logger.debug("Emergency catalogue availability check failed", exc_info=True)
        return False


def _country_operation_codes(iso: str) -> set[str] | None:
    """Appeal codes that belong to the country, ignoring period and type filters."""
    try:
        from plugins.emergency_operations.routes import get_emergency_operations_data

        operations = get_emergency_operations_data(
            country_iso=iso,
            config={
                "show_closed_operations": True,
                "operation_types": ["All"],
                "end_date_gt": None,
            },
        ) or []
    except Exception:
        logger.debug("Country emergency catalogue failed", exc_info=True)
        return None
    return {_code(op.get("code")) for op in operations if _code(op.get("code"))}


def selected_matrix_row_labels(cells, column_names, *, include_total: bool = True) -> list[str]:
    """Row labels a focal point added on an emergency-operations matrix."""
    suffixes = [f"_{name}" for name in column_names if name]
    if include_total:
        suffixes.append("_Total")
    suffixes.sort(key=len, reverse=True)
    labels: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        text = str(label or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        labels.append(text)

    for key, raw in (cells or {}).items():
        key_s = str(key)
        if key_s.startswith("row_go_unmatched|"):
            flag = _cell_text(raw)
            if flag in {"1", "true"}:
                add(key_s.split("|", 1)[1])
            continue
        if key_s.startswith("col_header") or key_s.startswith("_"):
            continue
        row_id = ""
        for suffix in suffixes:
            if key_s.endswith(suffix) and len(key_s) > len(suffix):
                row_id = key_s[: -len(suffix)]
                break
        add(row_id)
    return labels


def selected_matrix_header_labels(cells, header_columns) -> list[str]:
    """Appeal labels chosen in selectable emergency column headers."""
    labels: list[str] = []
    seen: set[str] = set()
    for column in header_columns:
        text = _cell_text((cells or {}).get(f"col_header|{column}"))
        if not text or text.lower() in {"none", "null", "-", "__other__"}:
            continue
        if text not in seen:
            seen.add(text)
            labels.append(text)
    return labels


def _cell_text(raw) -> str:
    from app.utils.matrix_activity import matrix_cell_display_value

    value = matrix_cell_display_value(raw)
    if value is None or isinstance(value, bool):
        return "true" if value else ""
    return str(value).strip()


def _ref_from_label(text: str) -> EmergencyRef | None:
    from plugins.emergency_operations.appeal_group import format_operation_label, parse_operation_label

    parsed = parse_operation_label(text)
    code = _code(parsed.get("code"))
    name = str(parsed.get("name") or "").strip()
    if not code and not name and not str(text or "").strip():
        return None
    label = format_operation_label(name, code) if (name or code) else str(text).strip()
    return EmergencyRef(code=code, label=label or str(text).strip() or code)


def _emergency_sources(aes) -> list[tuple[str, dict, list[EmergencyRef]]]:
    sources: list[tuple[str, dict, list[EmergencyRef]]] = []
    for item, section_name, plugin_config in _repeat_emergency_fields(aes):
        sources.append((section_name, plugin_config, _selected_emergencies(aes.id, item)))
    sources.extend(_matrix_emergency_sources(aes))
    return sources


def _template_binding(aes):
    assigned = getattr(aes, "assigned_form", None)
    template_id = getattr(assigned, "template_id", None)
    template = getattr(assigned, "template", None)
    version_id = getattr(template, "published_version_id", None) if template is not None else None
    if not isinstance(template_id, int):
        return None, None
    return template_id, version_id


def _matrix_items(template_id: int):
    from sqlalchemy.orm import joinedload

    from app.models.form_items import FormItem

    items = (
        FormItem.query.options(joinedload(FormItem.form_section))
        .filter(
            FormItem.template_id == template_id,
            FormItem.item_type == "matrix",
            FormItem.archived == False,  # noqa: E712
        )
        .all()
    )
    return items if isinstance(items, list) else []


def _matrix_emergency_sources(
    aes,
    items=None,
    cells_for_item=None,
    name_fn=None,
    template_id=None,
    version_id=None,
) -> list[tuple[str, dict, list[EmergencyRef]]]:
    from app.models.forms import FormData

    if template_id is None:
        template_id, version_id = _template_binding(aes)
    if template_id is None or not getattr(aes, "id", None):
        return []

    if items is None:
        items = _matrix_items(template_id)
    if not isinstance(items, list):
        return []

    names = name_fn or _display_names(aes)
    sources: list[tuple[str, dict, list[EmergencyRef]]] = []
    for item in items:
        if version_id and item.version_id not in (version_id, None):
            continue
        config = item.config if isinstance(getattr(item, "config", None), dict) else {}
        matrix = config.get("matrix_config") if isinstance(config.get("matrix_config"), dict) else {}
        columns = [col for col in (matrix.get("columns") or []) if isinstance(col, dict)]
        column_names = [str(col.get("name") or "") for col in columns]
        header_columns = [
            col for col in columns
            if str(col.get("header_lookup_list_id") or "").strip() == "emergency_operations"
        ]
        row_mode = str(matrix.get("row_mode") or "").strip().lower()
        row_lookup = str(matrix.get("lookup_list_id") or getattr(item, "lookup_list_id", "") or "").strip()
        row_source = row_mode in {"list_library", "hybrid"} and row_lookup == "emergency_operations"
        if not row_source and not header_columns:
            continue

        if cells_for_item is not None:
            cells = cells_for_item(item.id)
        else:
            entry = FormData.query.filter_by(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
            ).first()
            cells = entry.get_display_disagg_data() if entry is not None else None
        if not isinstance(cells, dict):
            cells = {}
        section = getattr(item, "form_section", None)
        section_name = names(getattr(item, "label", ""), getattr(section, "name", ""))

        if row_source:
            plugin_config = matrix.get("plugin_config") if isinstance(matrix.get("plugin_config"), dict) else {}
            selected = [
                ref for label in selected_matrix_row_labels(
                    cells,
                    column_names,
                    include_total=matrix.get("show_row_totals", True) is not False,
                )
                if (ref := _ref_from_label(label))
            ]
            sources.append((section_name, plugin_config, selected))

        if header_columns:
            grouped: dict[tuple, tuple[dict, list[str]]] = {}
            matrix_plugin = matrix.get("plugin_config") if isinstance(matrix.get("plugin_config"), dict) else {}
            for col in header_columns:
                plugin_config = col.get("header_plugin_config")
                if not isinstance(plugin_config, dict):
                    plugin_config = matrix_plugin
                key = tuple(sorted((str(k), str(v)) for k, v in plugin_config.items()))
                _cfg, names_for_cfg = grouped.setdefault(key, (plugin_config, []))
                names_for_cfg.append(str(col.get("name") or ""))
            for plugin_config, header_names in grouped.values():
                selected = [
                    ref for label in selected_matrix_header_labels(cells, header_names)
                    if (ref := _ref_from_label(label))
                ]
                sources.append((section_name, plugin_config, selected))
    return sources


def _display_names(aes):
    """Resolve [assignment_period] and the other label tokens once per assignment."""
    resolved = None

    def names(item_label: str, section_name: str) -> str:
        nonlocal resolved
        raw = str(item_label or "").strip()
        if raw in {"", "-", "—"}:
            raw = str(section_name or "").strip()
        if not raw:
            return "Emergency appeals"
        if "[" not in raw:
            return raw
        if resolved is None:
            try:
                from app.services.forms.variable_resolution_service import VariableResolutionService

                resolved = VariableResolutionService.resolve_for_assignment_display(aes)
            except Exception:
                logger.debug("Assignment label variables were not resolved", exc_info=True)
                resolved = ({}, {})
        variables, configs = resolved
        try:
            from app.services.forms.variable_resolution_service import VariableResolutionService

            replaced = VariableResolutionService.replace_variables_if_placeholders(raw, variables, configs)
        except Exception:
            logger.debug("Assignment label replacement failed", exc_info=True)
            return raw
        text = str(replaced or "").strip()
        return text or raw

    return names


def _repeat_emergency_fields(aes) -> list[tuple]:
    template_id, version_id = _template_binding(aes)
    if template_id is None:
        return []
    return _repeat_field_defs(template_id, version_id)


def _repeat_field_defs(template_id: int, version_id) -> list[tuple]:
    from sqlalchemy.orm import joinedload

    from app.models.form_items import FormItem

    query = (
        FormItem.query.options(joinedload(FormItem.form_section))
        .filter(
            FormItem.template_id == template_id,
            FormItem.lookup_list_id == "emergency_operations",
            FormItem.archived == False,  # noqa: E712
        )
    )
    items = query.all()
    if not isinstance(items, list):
        return []
    fields = []
    for item in items:
        if version_id and item.version_id not in (version_id, None):
            continue
        section = getattr(item, "form_section", None)
        if str(getattr(section, "section_type", "") or "").lower() != "repeat":
            continue
        config = item.config if isinstance(getattr(item, "config", None), dict) else {}
        plugin_config = config.get("question_plugin_config")
        if not isinstance(plugin_config, dict):
            plugin_config = {}
        section_name = str(getattr(section, "name", "") or "").strip() or "Emergency appeals"
        fields.append((item, section_name, plugin_config))
    return fields


def _selected_emergencies(aes_id: int, item) -> list[EmergencyRef]:
    from app.models.forms import RepeatGroupData, RepeatGroupInstance

    section_id = getattr(item, "section_id", None)
    item_id = getattr(item, "id", None)
    if not isinstance(section_id, int) or not isinstance(item_id, int):
        return []
    instances = (
        RepeatGroupInstance.query.filter_by(
            assignment_entity_status_id=aes_id,
            section_id=section_id,
        )
        .order_by(RepeatGroupInstance.instance_number.asc())
        .all()
    )
    if not isinstance(instances, list):
        return []
    selected: list[EmergencyRef] = []
    for instance in instances:
        if getattr(instance, "is_hidden", False):
            continue
        entry = RepeatGroupData.query.filter_by(
            repeat_instance_id=instance.id,
            form_item_id=item_id,
        ).first()
        ref = _ref_from_saved(entry)
        if ref is not None:
            selected.append(ref)
    return selected


def _plain_section_name(item_label: str, section_name: str) -> str:
    raw = str(item_label or "").strip()
    if raw in {"", "-", "—"}:
        raw = str(section_name or "").strip()
    return raw or "Emergency appeals"


class _CoverageBatch:
    """One form-item load and one appeals catalogue for every country on the tracker."""

    def __init__(self, aes_list):
        self.aes_list = [aes for aes in aes_list if getattr(aes, "id", None)]
        self.catalogue_ok = _catalogue_available()
        self.forms = {}
        self.countries = {}
        self.repeat_defs = {}
        self.matrix_items = {}
        self.matrix_cells = {}
        self.repeat_selected = {}
        if not self.catalogue_ok or not self.aes_list:
            return
        from app.utils.api_serialization import batch_countries_for_aes_list

        self.countries = batch_countries_for_aes_list(self.aes_list)
        self.forms = _assigned_forms(self.aes_list)
        self._load_fields()

    def coverages(self, aes) -> list[FieldEmergencyCoverage] | None:
        if aes is None or not getattr(aes, "id", None):
            return []
        if not self.catalogue_ok:
            return None
        sources = self._sources(aes)
        if not sources:
            return []

        from plugins.emergency_operations.section_binding import _fetch_ordered_operations

        iso = self._iso(aes)
        if not iso:
            return []
        period = self._period(aes)
        country_codes = _country_operation_codes(iso)
        if country_codes is None:
            return None

        coverages: list[FieldEmergencyCoverage] = []
        for section_name, plugin_config, selected in sources:
            try:
                operations = _fetch_ordered_operations(iso, plugin_config, period) or []
            except Exception:
                logger.debug("Applicable emergency lookup failed", exc_info=True)
                return None
            applicable = [ref for op in operations if (ref := _ref_from_operation(op))]
            coverages.append(FieldEmergencyCoverage(
                section_name=section_name,
                coverage=classify_emergency_coverage(applicable, selected, country_codes),
            ))
        return coverages

    def _sources(self, aes):
        form = self.forms.get(getattr(aes, "assigned_form_id", None))
        template_id = getattr(form, "template_id", None)
        template = getattr(form, "template", None)
        version_id = getattr(template, "published_version_id", None) if template is not None else None
        if not isinstance(template_id, int):
            return []
        sources = []
        for item, section_name, plugin_config in self.repeat_defs.get(template_id, []):
            if version_id and item.version_id not in (version_id, None):
                continue
            sources.append((
                section_name,
                plugin_config,
                self.repeat_selected.get((aes.id, item.id), []),
            ))

        def cells_for_item(item_id):
            return self.matrix_cells.get((aes.id, item_id), {})

        sources.extend(_matrix_emergency_sources(
            aes,
            items=self.matrix_items.get(template_id, []),
            cells_for_item=cells_for_item,
            name_fn=_plain_section_name,
            template_id=template_id,
            version_id=version_id,
        ))
        return sources

    def _iso(self, aes) -> str | None:
        country = self.countries.get((getattr(aes, "entity_type", None), getattr(aes, "entity_id", None)))
        if not country:
            return None
        iso = (getattr(country, "iso2", None) or getattr(country, "iso3", None) or "").strip().upper()
        return iso or None

    def _period(self, aes) -> str | None:
        form = self.forms.get(getattr(aes, "assigned_form_id", None))
        period = getattr(form, "period_name", None) if form is not None else None
        return str(period).strip() if period else None

    def _load_fields(self):
        template_ids = {
            form.template_id for form in self.forms.values() if isinstance(getattr(form, "template_id", None), int)
        }
        versions = {}
        for form in self.forms.values():
            template = getattr(form, "template", None)
            version_id = getattr(template, "published_version_id", None) if template is not None else None
            if isinstance(getattr(form, "template_id", None), int):
                versions[form.template_id] = version_id
        aes_ids = [aes.id for aes in self.aes_list]
        repeat_item_ids = []
        matrix_item_ids = []
        for template_id in template_ids:
            defs = _repeat_field_defs(template_id, versions.get(template_id))
            self.repeat_defs[template_id] = defs
            repeat_item_ids.extend(item.id for item, _, _ in defs if isinstance(getattr(item, "id", None), int))
            items = _matrix_items(template_id)
            self.matrix_items[template_id] = items
            matrix_item_ids.extend(item.id for item in items if isinstance(getattr(item, "id", None), int))
        self.matrix_cells = _bulk_matrix_cells(aes_ids, matrix_item_ids)
        self.repeat_selected = _bulk_repeat_selected(aes_ids, [
            field for defs in self.repeat_defs.values() for field in defs
        ])


def _assigned_forms(aes_list):
    from sqlalchemy.orm import joinedload

    from app.models.assignments import AssignedForm

    ids = {aes.assigned_form_id for aes in aes_list if getattr(aes, "assigned_form_id", None)}
    if not ids:
        return {}
    rows = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(AssignedForm.id.in_(ids))
        .all()
    )
    return {row.id: row for row in rows}


def _bulk_matrix_cells(aes_ids, item_ids):
    from app.models.forms import FormData

    if not aes_ids or not item_ids:
        return {}
    rows = FormData.query.filter(
        FormData.assignment_entity_status_id.in_(aes_ids),
        FormData.form_item_id.in_(item_ids),
    ).all()
    cells = {}
    for entry in rows:
        data = entry.get_display_disagg_data()
        cells[(entry.assignment_entity_status_id, entry.form_item_id)] = data if isinstance(data, dict) else {}
    return cells


def _bulk_repeat_selected(aes_ids, field_defs):
    from app.models.forms import RepeatGroupData, RepeatGroupInstance

    if not aes_ids or not field_defs:
        return {}
    section_ids = {
        item.section_id for item, _, _ in field_defs if isinstance(getattr(item, "section_id", None), int)
    }
    item_ids = {item.id for item, _, _ in field_defs if isinstance(getattr(item, "id", None), int)}
    if not section_ids or not item_ids:
        return {}
    instances = (
        RepeatGroupInstance.query.filter(
            RepeatGroupInstance.assignment_entity_status_id.in_(aes_ids),
            RepeatGroupInstance.section_id.in_(section_ids),
        )
        .order_by(RepeatGroupInstance.instance_number.asc())
        .all()
    )
    by_aes_section = {}
    for instance in instances:
        by_aes_section.setdefault((instance.assignment_entity_status_id, instance.section_id), []).append(instance)
    data_by_key = {}
    instance_ids = [instance.id for instance in instances]
    if instance_ids:
        rows = RepeatGroupData.query.filter(
            RepeatGroupData.repeat_instance_id.in_(instance_ids),
            RepeatGroupData.form_item_id.in_(item_ids),
        ).all()
        for row in rows:
            data_by_key[(row.repeat_instance_id, row.form_item_id)] = row
    selected = {}
    for aes_id in aes_ids:
        for item, _, _ in field_defs:
            refs = []
            for instance in by_aes_section.get((aes_id, item.section_id), []):
                if getattr(instance, "is_hidden", False):
                    continue
                ref = _ref_from_saved(data_by_key.get((instance.id, item.id)))
                if ref is not None:
                    refs.append(ref)
            selected[(aes_id, item.id)] = refs
    return selected


@contextmanager
def tracker_coverage_scope(aes_list):
    """Share form rows and the appeals catalogue across every country in one tracker load."""
    from plugins.emergency_operations.routes import reuse_emergency_operations_catalogue

    batch = _CoverageBatch(list(aes_list or []))
    token = _COVERAGE_BATCH.set(batch)
    try:
        with reuse_emergency_operations_catalogue():
            yield
    finally:
        _COVERAGE_BATCH.reset(token)
