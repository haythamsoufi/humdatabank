"""Build SG_Report-shaped datasets from Indicator Bank + live FDRS/UPR form data."""

from __future__ import annotations

import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import and_, func, or_

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.form_items import FormItem
from app.models.forms import FormData
from app.models.indicator_bank import IndicatorBank
from app.services.platform import storage_service
from plugins.pb_progress.plugin_data_store import (
    EXCEL_NAME,
    PBProgressDataStore,
    STORAGE_CATEGORY,
    SYSTEM_GENERATED_NAME,
)
from plugins.pb_progress.versions import REPORT_VERSIONS, validate_version, version_storage_prefix

FDRS_TEMPLATE_ID = 21
UPR_TEMPLATE_ID = 33
MAPPING_HEADER_ROW = 3
SECTION_COLUMN = "Strategic Priority / Enabling Function"

_LANG_KEYS = {"en": "English", "fr": "French", "es": "Spanish", "ar": "Arabic"}
_AGG_LABEL_LANG_MAP = {"English": "en", "French": "fr", "Spanish": "es", "Arabic": "ar"}


class DbSourceError(RuntimeError):
    """Raised when system dataset generation fails."""


class WorkbookValidationError(ValueError):
    """Raised when an uploaded SG Report workbook fails validation."""


REQUIRED_UPLOAD_SHEETS: tuple[str, ...] = ("Mapping", "Final", "TotalReported")
OPTIONAL_UPLOAD_SHEETS: tuple[str, ...] = ("Translations", "SectionOrder")


def _visuals_scripts_path() -> Path:
    return Path(__file__).resolve().parent / "visuals" / "scripts"


def validate_uploaded_workbook(path: Path | str) -> dict[str, Any]:
    """Validate an SG Report workbook before accepting it for report generation."""
    workbook_path = Path(path)
    if not workbook_path.is_file():
        raise WorkbookValidationError(f"Workbook not found: {workbook_path}")

    try:
        excel_file = pd.ExcelFile(workbook_path)
    except Exception as exc:
        raise WorkbookValidationError(f"Cannot read Excel file: {exc}") from exc

    missing_required = [sheet for sheet in REQUIRED_UPLOAD_SHEETS if sheet not in excel_file.sheet_names]
    if missing_required:
        raise WorkbookValidationError(
            "Workbook is missing required sheet(s): "
            f"{', '.join(missing_required)}."
        )

    warnings: list[str] = []
    for sheet in OPTIONAL_UPLOAD_SHEETS:
        if sheet not in excel_file.sheet_names:
            warnings.append(
                f"Sheet '{sheet}' is missing; built-in defaults will be used during report generation."
            )

    mapping_df = pd.read_excel(workbook_path, sheet_name="Mapping", header=MAPPING_HEADER_ROW)
    if mapping_df.empty or "ID" not in mapping_df.columns:
        raise WorkbookValidationError(
            "Mapping sheet is empty or missing an ID column (expected header row 4)."
        )
    indicator_ids = mapping_df["ID"].map(_normalize_id)
    if not indicator_ids.replace("", pd.NA).dropna().any():
        raise WorkbookValidationError("Mapping sheet has no indicator IDs.")

    scripts_path = _visuals_scripts_path()
    scripts_path_str = str(scripts_path)
    if scripts_path_str not in sys.path:
        sys.path.insert(0, scripts_path_str)

    from pb_figures.data import DataModelError, build_model

    try:
        model = build_model(workbook_path)
    except DataModelError as exc:
        raise WorkbookValidationError(str(exc)) from exc

    sections = sorted(model["section"].dropna().astype(str).unique())
    return {
        "valid": True,
        "warnings": warnings,
        "indicator_count": int(model["ID"].nunique()),
        "row_count": len(model),
        "sections": sections,
    }


def _section_from_area(area: str | None) -> str:
    text = (area or "").strip()
    if not text:
        return "Cross-cutting"
    if text.upper() == "CC1":
        return "Cross-cutting"
    return text


def _normalize_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _template_ids_for_source(source: str) -> tuple[int, ...]:
    if source == "FDRS":
        return (FDRS_TEMPLATE_ID,)
    if source == "UPR":
        return (UPR_TEMPLATE_ID,)
    return ()


def list_tagged_indicators(tag: str) -> list[dict[str, Any]]:
    if not tag:
        return []

    query = IndicatorBank.query.filter(IndicatorBank.archived.is_(False))
    dialect = db.session.bind.dialect.name if db.session.bind else ""
    if dialect == "postgresql":
        query = query.filter(IndicatorBank._related_programs_list.contains([tag]))  # type: ignore[attr-defined]
        rows = query.order_by(IndicatorBank.id).all()
    else:
        rows = [
            row
            for row in query.order_by(IndicatorBank.id).all()
            if tag in (row.related_programs_list or [])
        ]

    return [_serialize_tagged_indicator(row) for row in rows]


def _serialize_tagged_indicator(indicator: IndicatorBank) -> dict[str, Any]:
    availability = _form_item_templates(indicator.id)
    labels = _indicator_labels(indicator)
    return {
        "id": str(indicator.id),
        "section": _section_from_area(indicator.area),
        "aggregated_label": labels["English"],
        "labels": labels,
        "fdrs_kpi": indicator.fdrs_kpi_code,
        "type": indicator.type,
        "unit": indicator.unit,
        "source_availability": availability,
        "default_source": _default_source(availability),
    }


def _form_item_templates(indicator_bank_id: int) -> dict[str, bool]:
    rows = (
        db.session.query(FormItem.template_id)
        .filter(FormItem.indicator_bank_id == indicator_bank_id)
        .distinct()
        .all()
    )
    template_ids = {row[0] for row in rows}
    return {
        "fdrs": FDRS_TEMPLATE_ID in template_ids,
        "upr": UPR_TEMPLATE_ID in template_ids,
    }


def _default_source(availability: dict[str, bool]) -> str | None:
    if availability.get("fdrs") and not availability.get("upr"):
        return "FDRS"
    if availability.get("upr") and not availability.get("fdrs"):
        return "UPR"
    if availability.get("fdrs") and availability.get("upr"):
        return None
    return "Manual"


def _resolve_source_for_availability(source: str, availability: dict[str, bool]) -> str:
    """Pick FDRS/UPR/Manual based on template field availability."""
    normalized = (source or "Manual").strip() or "Manual"
    if normalized not in {"FDRS", "UPR"}:
        return _default_source(availability) or "Manual"
    if normalized == "FDRS" and availability.get("fdrs"):
        return "FDRS"
    if normalized == "UPR" and availability.get("upr"):
        return "UPR"
    fallback = _default_source(availability)
    return fallback or "Manual"


def _indicator_labels(indicator: IndicatorBank, override: str | None = None) -> dict[str, str]:
    labels = {lang: "" for lang in _LANG_KEYS.values()}
    if override and str(override).strip():
        labels["English"] = str(override).strip()
        return labels

    english = (indicator.aggregated_label or indicator.name or "").strip()
    labels["English"] = english
    translations = indicator.aggregated_label_translations or {}
    if isinstance(translations, dict):
        for lang_code, excel_col in _AGG_LABEL_LANG_MAP.items():
            if lang_code == "en":
                continue
            value = translations.get(lang_code)
            if isinstance(value, str) and value.strip():
                labels[excel_col] = value.strip()
    return labels


def validate_mapping_config(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate mapping rows with source availability warnings."""
    validated: list[dict[str, Any]] = []
    for row in rows:
        item = copy_mapping_row(row)
        indicator_id = _normalize_id(item.get("id"))
        source = str(item.get("source") or "Manual").strip() or "Manual"
        if indicator_id.isdigit():
            availability = _form_item_templates(int(indicator_id))
            item["source_availability"] = availability
            resolved = _resolve_source_for_availability(source, availability)
            if resolved != source:
                item["source"] = resolved
                source = resolved
            if source == "FDRS" and not availability.get("fdrs"):
                item["source_warning"] = "FDRS template field not found for this indicator."
            elif source == "UPR" and not availability.get("upr"):
                item["source_warning"] = "UPR template field not found for this indicator."
        validated.append(item)
    return validated


def sync_mapping_from_indicator_bank(version: str) -> dict[str, Any]:
    version = validate_version(version)
    tag = REPORT_VERSIONS[version].get("related_program_tag") or ""
    if not tag:
        raise DbSourceError(f"No related_program_tag configured for version {version!r}.")

    tagged = {row["id"]: row for row in list_tagged_indicators(tag)}
    existing_rows = PBProgressDataStore.get_mapping_config(version)
    existing_by_id = {_normalize_id(row.get("id")): row for row in existing_rows if _normalize_id(row.get("id"))}

    merged: list[dict[str, Any]] = []
    added = 0
    flagged = 0

    for indicator_id, tagged_row in tagged.items():
        current = existing_by_id.get(indicator_id)
        if current:
            current = copy_mapping_row(current)
            current.pop("tag_missing", None)
            availability = tagged_row.get("source_availability") or {}
            if not current.get("source"):
                current["source"] = tagged_row.get("default_source") or "Manual"
            else:
                current["source"] = _resolve_source_for_availability(str(current.get("source")), availability)
            merged.append(current)
            continue

        merged.append(
            {
                "id": indicator_id,
                "section": tagged_row.get("section") or "Cross-cutting",
                "core_or_other": "Core",
                "type": "Cumulative",
                "unit": tagged_row.get("unit"),
                "source": tagged_row.get("default_source") or "Manual",
                "fdrs_kpi": tagged_row.get("fdrs_kpi"),
                "label_override": None,
                "annual_target": "",
                "annual_target_ar": "",
                "target": "",
                "target_ar": "",
                "target_value": None,
                "sp_titles": {"en": "", "fr": "", "es": "", "ar": ""},
                "comments": "",
                "manual_values": [],
            }
        )
        added += 1

    for indicator_id, row in existing_by_id.items():
        if indicator_id in tagged:
            continue
        updated = copy_mapping_row(row)
        updated["tag_missing"] = True
        merged.append(updated)
        flagged += 1

    PBProgressDataStore.save_mapping_config(version, merged)
    validated = validate_mapping_config(merged)
    PBProgressDataStore.save_mapping_config(version, validated)
    return {
        "version": version,
        "tag": tag,
        "total": len(merged),
        "added": added,
        "flagged_missing_tag": flagged,
    }


def copy_mapping_row(row: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(row)


def _excel_path_for_version(version: str) -> Path:
    rel = f"versions/{version}/{EXCEL_NAME}"
    if not storage_service.exists(STORAGE_CATEGORY, rel):
        raise DbSourceError("Upload an Excel workbook before importing config.")
    return Path(storage_service.get_absolute_path(STORAGE_CATEGORY, rel))


def import_config_from_excel(version: str) -> dict[str, Any]:
    version = validate_version(version)
    path = _excel_path_for_version(version)

    mapping_df = pd.read_excel(path, sheet_name="Mapping", header=MAPPING_HEADER_ROW)
    mapping_rows: list[dict[str, Any]] = []
    for _, row in mapping_df.iterrows():
        indicator_id = _normalize_id(row.get("ID"))
        if not indicator_id:
            continue
        mapping_rows.append(
            {
                "id": indicator_id,
                "section": str(row.get(SECTION_COLUMN) or "").strip() or "Cross-cutting",
                "core_or_other": str(row.get("Core/other") or "Core").strip() or "Core",
                "type": str(row.get("Type") or "Cumulative").strip() or "Cumulative",
                "unit": None if pd.isna(row.get("Unit")) else str(row.get("Unit")).strip(),
                "source": str(row.get("Source") or "Manual").strip() or "Manual",
                "fdrs_kpi": None if pd.isna(row.get("FDRS KPI")) else str(row.get("FDRS KPI")).strip(),
                "label_override": None,
                "annual_target": "" if pd.isna(row.get("Annual Target")) else str(row.get("Annual Target")).strip(),
                "annual_target_ar": "" if pd.isna(row.get("Annual Target AR")) else str(row.get("Annual Target AR")).strip(),
                "target": "" if pd.isna(row.get("Target")) else str(row.get("Target")).strip(),
                "target_ar": "" if pd.isna(row.get("Target AR")) else str(row.get("Target AR")).strip(),
                "target_value": None if pd.isna(row.get("Target value")) else row.get("Target value"),
                "sp_titles": {
                    "en": "" if pd.isna(row.get("SP EN")) else str(row.get("SP EN")).strip(),
                    "fr": "" if pd.isna(row.get("SP FR")) else str(row.get("SP FR")).strip(),
                    "es": "" if pd.isna(row.get("SP SP")) else str(row.get("SP SP")).strip(),
                    "ar": "" if pd.isna(row.get("SP AR")) else str(row.get("SP AR")).strip(),
                },
                "comments": "" if pd.isna(row.get("Comments")) else str(row.get("Comments")).strip(),
                "manual_values": [],
            }
        )

    try:
        other_df = pd.read_excel(path, sheet_name="OtherSources")
        for _, row in other_df.iterrows():
            indicator_id = _normalize_id(row.get("indicatorId"))
            if not indicator_id:
                continue
            manual_values = []
            year = row.get("Year")
            total = row.get("Total")
            if not pd.isna(year):
                manual_values.append(
                    {
                        "year": str(int(year)) if float(year).is_integer() else str(year),
                        "value": None if pd.isna(total) else float(total),
                    }
                )
            mapping_rows.append(
                {
                    "id": indicator_id,
                    "section": "SP2",
                    "core_or_other": "Other",
                    "type": "Distinct",
                    "unit": None,
                    "source": "Manual",
                    "fdrs_kpi": None,
                    "label_override": str(row.get("Indicator") or "").strip() or indicator_id,
                    "annual_target": "",
                    "annual_target_ar": "",
                    "target": "",
                    "target_ar": "",
                    "target_value": None,
                    "sp_titles": {"en": "", "fr": "", "es": "", "ar": ""},
                    "comments": "" if pd.isna(row.get("Comment")) else str(row.get("Comment")).strip(),
                    "manual_values": manual_values,
                }
            )
    except ValueError:
        pass

    translations_rows: list[dict[str, Any]] = []
    try:
        translations_df = pd.read_excel(path, sheet_name="Translations")
        for _, row in translations_df.iterrows():
            key = str(row.get("id") or "").strip()
            if not key:
                continue
            translations_rows.append(
                {
                    "id": key,
                    "EN": "" if pd.isna(row.get("EN")) else str(row.get("EN")).strip(),
                    "FR": "" if pd.isna(row.get("FR")) else str(row.get("FR")).strip(),
                    "SP": "" if pd.isna(row.get("SP")) else str(row.get("SP")).strip(),
                    "AR": "" if pd.isna(row.get("AR")) else str(row.get("AR")).strip(),
                }
            )
    except ValueError:
        pass

    section_order_rows: list[dict[str, Any]] = []
    try:
        section_order_df = pd.read_excel(path, sheet_name="SectionOrder")
        for _, row in section_order_df.iterrows():
            section_order_rows.append(
                {
                    "part": str(row.get("part") or "").strip(),
                    "section": str(row.get("section") or "").strip(),
                    "order": int(row.get("order")) if not pd.isna(row.get("order")) else 0,
                }
            )
    except ValueError:
        pass

    PBProgressDataStore.save_mapping_config(version, mapping_rows)
    mapping_rows = validate_mapping_config(mapping_rows)
    PBProgressDataStore.save_mapping_config(version, mapping_rows)
    if not translations_rows:
        from plugins.pb_progress.report_defaults import default_translations_config_rows

        translations_rows = default_translations_config_rows()
    if not section_order_rows:
        from plugins.pb_progress.report_defaults import default_section_order_config_rows

        section_order_rows = default_section_order_config_rows()
    PBProgressDataStore.save_translations_config(version, translations_rows)
    PBProgressDataStore.save_section_order_config(version, section_order_rows)
    return {
        "version": version,
        "mapping_count": len(mapping_rows),
        "translations_count": len(translations_rows),
        "section_order_count": len(section_order_rows),
    }


def list_available_years(version: str) -> list[str]:
    """Union of assignment years (FDRS/UPR) and manual mapping years."""
    version = validate_version(version)
    years: set[str] = set(_years_for_template(FDRS_TEMPLATE_ID))
    years.update(_years_for_template(UPR_TEMPLATE_ID))
    for row in PBProgressDataStore.get_mapping_config(version):
        if str(row.get("source") or "").strip() != "Manual":
            continue
        for entry in row.get("manual_values") or []:
            if not isinstance(entry, dict):
                continue
            year = _normalize_id(entry.get("year"))
            if year:
                years.add(year)
    return sorted(years)


def resolve_build_years(version: str) -> set[str]:
    """Years to include in system-generated Final / TotalReported."""
    available = set(list_available_years(version))
    selected = PBProgressDataStore.get_selected_years(version)
    if not selected:
        return available
    filtered = {year for year in selected if year in available}
    return filtered if filtered else available


def _years_for_template(template_id: int) -> list[str]:
    rows = (
        db.session.query(AssignedForm.period_name)
        .filter(AssignedForm.template_id == template_id)
        .distinct()
        .all()
    )
    years: set[str] = set()
    for (period_name,) in rows:
        if not period_name:
            continue
        match = re.search(r"\b(19|20|21)\d{2}\b", str(period_name))
        if match:
            years.add(match.group(0))
        elif str(period_name).strip().isdigit():
            years.add(str(period_name).strip())
    return sorted(years)


def _aggregate_indicator_year(template_id: int, indicator_bank_id: int, year: str) -> dict[str, Any]:
    """Per-indicator/year NS counts.

    ``implementing`` = NSs that reported into this data-collection round for this
    indicator: a real value (incl. 0) OR an explicit "applicable, data not available"
    flag. Mirrors the legacy Excel/Power Query semantics, where data-not-available
    rows were exported as 0 and therefore also counted as "reported".

    ``reported_count`` (-> Final "Count") = the narrower subset that reported an
    actual value greater than zero.
    """
    base = (
        db.session.query(
            func.sum(FormData.numeric_value).label("total_value"),
            func.count(FormData.id)
            .filter(
                or_(
                    FormData.numeric_value.isnot(None),
                    FormData.data_not_available.is_(True),
                )
            )
            .label("implementing"),
            func.count(FormData.id)
            .filter(and_(FormData.numeric_value.isnot(None), FormData.numeric_value > 0))
            .label("reported_count"),
        )
        .join(FormItem, FormItem.id == FormData.form_item_id)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.id == FormData.assignment_entity_status_id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            FormItem.indicator_bank_id == indicator_bank_id,
            FormItem.template_id == template_id,
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
            or_(
                AssignedForm.period_name == year,
                AssignedForm.period_name.ilike(f"%{year}%"),
            ),
            FormData.not_applicable.isnot(True),
        )
    )
    row = base.one()
    total_value = row.total_value
    return {
        "value": float(total_value) if total_value is not None else None,
        "implementing": int(row.implementing or 0),
        "count": int(row.reported_count or 0),
    }


def _build_final_rows(mapping_config: list[dict[str, Any]], *, version: str) -> list[dict[str, Any]]:
    final_rows: list[dict[str, Any]] = []
    index = 1
    indicator_ids = [_normalize_id(row.get("id")) for row in mapping_config if _normalize_id(row.get("id"))]
    indicators = {
        str(item.id): item
        for item in IndicatorBank.query.filter(IndicatorBank.id.in_([int(i) for i in indicator_ids if i.isdigit()])).all()
    }

    allowed_years = resolve_build_years(version)
    years_by_source: dict[str, set[str]] = {
        "FDRS": set(_years_for_template(FDRS_TEMPLATE_ID)) & allowed_years,
        "UPR": set(_years_for_template(UPR_TEMPLATE_ID)) & allowed_years,
        "Manual": set(),
    }

    for row in mapping_config:
        indicator_id = _normalize_id(row.get("id"))
        if not indicator_id:
            continue
        source = str(row.get("source") or "Manual").strip() or "Manual"
        section = str(row.get("section") or "Cross-cutting").strip() or "Cross-cutting"

        if source == "Manual":
            manual_values = row.get("manual_values") or []
            for entry in manual_values:
                if not isinstance(entry, dict):
                    continue
                year = str(entry.get("year") or "").strip()
                if not year or year not in allowed_years:
                    continue
                years_by_source["Manual"].add(year)
                value = entry.get("value")
                final_rows.append(
                    {
                        "Index": index,
                        SECTION_COLUMN: section,
                        "ID": indicator_id,
                        "Source": source,
                        "Year": year,
                        "Value": value,
                        "Implementing": entry.get("implementing"),
                        "Count": entry.get("count"),
                    }
                )
            index += 1
            continue

        template_id = FDRS_TEMPLATE_ID if source == "FDRS" else UPR_TEMPLATE_ID
        bank_id = int(indicator_id) if indicator_id.isdigit() else None
        if bank_id is None:
            continue
        for year in sorted(years_by_source.get(source, set())):
            stats = _aggregate_indicator_year(template_id, bank_id, year)
            if stats["value"] is None and stats["implementing"] == 0 and stats["count"] == 0:
                continue
            final_rows.append(
                {
                    "Index": index,
                    SECTION_COLUMN: section,
                    "ID": indicator_id,
                    "Source": source,
                    "Year": year,
                    "Value": stats["value"],
                    "Implementing": stats["implementing"],
                    "Count": stats["count"],
                }
            )
        index += 1
    return final_rows


def _build_total_reported(final_df: pd.DataFrame) -> pd.DataFrame:
    if final_df.empty:
        return pd.DataFrame(columns=["Source", "Year", "TotalReported"])

    rows: list[dict[str, Any]] = []
    grouped = final_df.groupby(["Source", "Year"], dropna=False)
    for (source, year), group in grouped:
        if str(source) == "Manual":
            continue
        template_id = FDRS_TEMPLATE_ID if str(source) == "FDRS" else UPR_TEMPLATE_ID
        count = (
            db.session.query(func.count(func.distinct(AssignmentEntityStatus.entity_id)))
            .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(
                AssignedForm.template_id == template_id,
                AssignmentEntityStatus.entity_type == "country",
                or_(
                    AssignedForm.period_name == str(year),
                    AssignedForm.period_name.ilike(f"%{year}%"),
                ),
                AssignmentEntityStatus.status.in_(("approved", "submitted")),
            )
            .scalar()
        )
        rows.append({"Source": source, "Year": str(year), "TotalReported": int(count or 0)})

        if str(source) in {"FDRS", "UPR"}:
            merged_count = max(int(group["Implementing"].max() or 0), int(count or 0))
            rows.append({"Source": "Merged", "Year": str(year), "TotalReported": merged_count})

    return pd.DataFrame(rows)


def _build_mapping_dataframe(mapping_config: list[dict[str, Any]]) -> pd.DataFrame:
    indicator_ids = [_normalize_id(row.get("id")) for row in mapping_config if _normalize_id(row.get("id"))]
    indicators = {
        str(item.id): item
        for item in IndicatorBank.query.filter(IndicatorBank.id.in_([int(i) for i in indicator_ids if i.isdigit()])).all()
    }

    rows: list[dict[str, Any]] = []
    for row in mapping_config:
        indicator_id = _normalize_id(row.get("id"))
        indicator = indicators.get(indicator_id)
        labels = _indicator_labels(indicator, row.get("label_override")) if indicator else {
            lang: (row.get("label_override") or "") for lang in _LANG_KEYS.values()
        }
        rows.append(
            {
                SECTION_COLUMN: row.get("section") or "Cross-cutting",
                "ID": indicator_id,
                "Core/other": row.get("core_or_other") or "Core",
                "Type": row.get("type") or "Cumulative",
                "Unit": row.get("unit"),
                "FDRS KPI": row.get("fdrs_kpi"),
                "Source": row.get("source") or "Manual",
                "Annual Target": row.get("annual_target") or "",
                "Annual Target AR": row.get("annual_target_ar") or "",
                "Target value": row.get("target_value"),
                "Target": row.get("target") or "",
                "Target AR": row.get("target_ar") or "",
                "English": labels.get("English", ""),
                "Arabic": labels.get("Arabic", ""),
                "French": labels.get("French", ""),
                "Spanish": labels.get("Spanish", ""),
                "SP EN": (row.get("sp_titles") or {}).get("en", ""),
                "SP FR": (row.get("sp_titles") or {}).get("fr", ""),
                "SP SP": (row.get("sp_titles") or {}).get("es", ""),
                "SP AR": (row.get("sp_titles") or {}).get("ar", ""),
                "Comments": row.get("comments") or "",
            }
        )
    return pd.DataFrame(rows)


def build_dataset(version: str) -> dict[str, pd.DataFrame]:
    version = validate_version(version)
    mapping_config = PBProgressDataStore.get_mapping_config(version)
    translations_config = PBProgressDataStore.get_translations_config(version)
    section_order_config = PBProgressDataStore.get_section_order_config(version)

    if not mapping_config:
        raise DbSourceError("Mapping config is empty. Sync from Indicator Bank or import from Excel first.")

    mapping_df = _build_mapping_dataframe(mapping_config)
    final_rows = _build_final_rows(mapping_config, version=version)
    final_df = pd.DataFrame(final_rows)
    total_reported_df = _build_total_reported(final_df)
    translations_df = pd.DataFrame(translations_config or [], columns=["id", "EN", "FR", "SP", "AR"])
    section_order_df = pd.DataFrame(section_order_config or [], columns=["part", "section", "order"])

    return {
        "mapping": mapping_df,
        "final": final_df,
        "total_reported": total_reported_df,
        "translations": translations_df,
        "sectionorder": section_order_df,
    }


def export_dataset_to_excel(version: str, output_path: Path | str) -> Path:
    from plugins.pb_progress.report_defaults import (
        default_section_order_config_rows,
        default_translations_config_rows,
    )

    sheets = build_dataset(version)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    translations_df = sheets["translations"]
    if translations_df.empty:
        translations_df = pd.DataFrame(default_translations_config_rows())

    section_order_df = sheets["sectionorder"]
    if section_order_df.empty:
        section_order_df = pd.DataFrame(default_section_order_config_rows())

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        empty = pd.DataFrame()
        empty.to_excel(writer, sheet_name="Mapping", index=False, startrow=MAPPING_HEADER_ROW)
        sheets["mapping"].to_excel(writer, sheet_name="Mapping", index=False, startrow=MAPPING_HEADER_ROW)
        sheets["final"].to_excel(writer, sheet_name="Final", index=False)
        sheets["total_reported"].to_excel(writer, sheet_name="TotalReported", index=False)
        translations_df.to_excel(writer, sheet_name="Translations", index=False)
        section_order_df.to_excel(writer, sheet_name="SectionOrder", index=False)
    return output_path


def compare_final_with_uploaded(version: str) -> dict[str, Any]:
    version = validate_version(version)
    generated = build_dataset(version)["final"]
    uploaded_path = _excel_path_for_version(version)
    uploaded = pd.read_excel(uploaded_path, sheet_name="Final")

    key_cols = ["ID", "Source", "Year"]
    generated = generated.copy()
    uploaded = uploaded.copy()
    for frame in (generated, uploaded):
        frame["ID"] = frame["ID"].astype(str).str.strip()
        frame["Source"] = frame["Source"].astype(str).str.strip()
        frame["Year"] = frame["Year"].astype(str).str.strip()

    generated_keys = {tuple(row[c] for c in key_cols): row for _, row in generated.iterrows()}
    uploaded_keys = {tuple(row[c] for c in key_cols): row for _, row in uploaded.iterrows()}

    mismatches: list[dict[str, Any]] = []
    for key, uploaded_row in uploaded_keys.items():
        generated_row = generated_keys.get(key)
        if generated_row is None:
            mismatches.append({"key": key, "issue": "missing_in_system"})
            continue
        for col in ("Value", "Implementing", "Count"):
            up_val = uploaded_row.get(col)
            gen_val = generated_row.get(col)
            if pd.isna(up_val) and pd.isna(gen_val):
                continue
            if pd.isna(up_val) or pd.isna(gen_val) or float(up_val) != float(gen_val):
                mismatches.append(
                    {
                        "key": key,
                        "issue": "value_mismatch",
                        "column": col,
                        "excel": up_val,
                        "system": gen_val,
                    }
                )

    return {
        "version": version,
        "excel_rows": len(uploaded_keys),
        "system_rows": len(generated_keys),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:200],
    }


def generate_system_dataset(version: str) -> dict[str, Any]:
    version = validate_version(version)
    rel = f"{version_storage_prefix(version)}{SYSTEM_GENERATED_NAME}"
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            temp_path = tmp.name
        local_path = Path(temp_path)
        export_dataset_to_excel(version, local_path)
        with open(local_path, "rb") as handle:
            storage_service.upload(STORAGE_CATEGORY, rel, handle.read())
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
    sheets = build_dataset(version)
    return {
        "version": version,
        "output_path": rel,
        "mapping_rows": len(sheets["mapping"]),
        "final_rows": len(sheets["final"]),
        "total_reported_rows": len(sheets["total_reported"]),
    }
