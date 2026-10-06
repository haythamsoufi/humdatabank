"""Export and import for the T22 PNS Planning and T23 PNS Reporting workbooks."""

from __future__ import annotations

import io
import os
import tempfile
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from flask import current_app

from plugins.upr.excel._scripts_path import ensure_scripts_in_path as _ensure_scripts_in_path

PNS_PLANNING_LABEL = "PNS Planning"
PNS_REPORTING_LABEL = "PNS Reporting"


def _save_workbook(wb, template_path: str) -> io.BytesIO:
    from unified_country_plan_excel_template import (
        _ensure_workbook_recalculates_on_open,
        restore_workbook_dynamic_array_metadata,
    )

    _ensure_workbook_recalculates_on_open(wb)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.close()
    try:
        wb.save(tmp.name)
        wb.close()
        restore_workbook_dynamic_array_metadata(template_path, tmp.name)
        with open(tmp.name, "rb") as handle:
            output = io.BytesIO(handle.read())
        output.seek(0)
        return output
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _filename(prefix: str, country_name: str, iso3: str, period: str) -> str:
    import re

    safe_country = re.sub(r"[^\w\-]+", "_", country_name or iso3 or "country").strip("_") or "country"
    safe_period = re.sub(r"[^\w\-]+", "_", period or "period").strip("_") or "period"
    return f"{prefix}_{safe_country}_{safe_period}.xlsx"


def _assignment_identity(aes) -> Tuple[str, str, str, Optional[int], str]:
    from app.models.organization import NationalSociety
    from app.utils.api_serialization import _country_for_aes
    from import_upr_excel_data import _period_year_token

    country = _country_for_aes(aes)
    country_name = (country.name if country else "") or ""
    iso3 = ((country.iso3 if country else "") or "").strip().upper()
    period = (aes.assigned_form.period_name if aes.assigned_form else "") or ""
    ns_name = country_name
    if country is not None:
        ns = (
            NationalSociety.query.filter_by(country_id=country.id, is_active=True)
            .order_by(NationalSociety.display_order.asc(), NationalSociety.id.asc())
            .first()
        )
        if ns and (ns.name or "").strip():
            ns_name = ns.name.strip()
    return ns_name.strip(), country_name.strip(), iso3, _period_year_token(period), period.strip()


def _matrix_cells(aes_id: int, item_id: int) -> Dict[str, Any]:
    from app.models.forms import FormData

    if not item_id:
        return {}
    entry = FormData.query.filter_by(
        assignment_entity_status_id=int(aes_id),
        form_item_id=int(item_id),
    ).first()
    raw = getattr(entry, "disagg_data", None) if entry else None
    if isinstance(raw, dict):
        return raw
    return {}


def _form_columns(item) -> List[str]:
    from import_upr_excel_data import _form_item_matrix_column_names

    return _form_item_matrix_column_names(item)


def _indexes():
    from import_upr_excel_data import _build_ns_home_country_index, _build_ns_name_index

    ns_name_to_id = _build_ns_name_index()
    _ns_home, country_id_by_iso3, iso3_to_ns_id = _build_ns_home_country_index()
    return ns_name_to_id, country_id_by_iso3, iso3_to_ns_id


def _country_name_maps(wb, country_id_by_iso3: Mapping[str, int], iso3_to_ns_id: Mapping[str, int]):
    from pns_form_excel import sheet_country_index

    by_name = sheet_country_index(wb)
    name_to_country_id: Dict[str, int] = {}
    name_to_ns_id: Dict[str, int] = {}
    country_id_to_name: Dict[int, str] = {}
    ns_id_to_country: Dict[int, Dict[str, str]] = {}
    ns_id_to_iso3 = {ns_id: iso3 for iso3, ns_id in iso3_to_ns_id.items()}
    for key, row in by_name.items():
        iso3 = row["iso3"]
        country_id = country_id_by_iso3.get(iso3)
        ns_id = iso3_to_ns_id.get(iso3)
        if country_id:
            name_to_country_id[key] = country_id
            country_id_to_name[country_id] = row["country"]
        if ns_id:
            name_to_ns_id[key] = ns_id
            ns_id_to_country[ns_id] = row
    return name_to_country_id, name_to_ns_id, country_id_to_name, ns_id_to_country, ns_id_to_iso3


def _load_workbook(file_bytes: bytes):
    from app.utils.safe_workbook import load_workbook_safe

    return load_workbook_safe(file_bytes, read_only=False, data_only=False)


def _stage(aes, payload: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    from app.services.imports.scoped_import_guard import filter_staged_import_payload

    extra = filter_staged_import_payload(aes, payload)
    warning_texts = list(warnings) + [item.get("message", str(item)) if isinstance(item, dict) else str(item) for item in (extra.get("warnings") or [])]
    return {
        "success": True,
        "stage_only": True,
        "payload": payload,
        "warnings": warning_texts,
        "warning_items": extra.get("warning_items") or [],
        "updated_count": extra.get("updated_count", 0),
    }


class PnsPlanningExcelService:
    TEMPLATE_PATH_CONFIG_KEY = "PNS_PLANNING_TEMPLATE_PATH"
    DEFAULT_TEMPLATE_NAME = "pns_planning_form.xlsx"

    @classmethod
    def get_template_path(cls) -> str:
        configured = current_app.config.get(cls.TEMPLATE_PATH_CONFIG_KEY)
        if configured and os.path.isfile(configured):
            return configured
        plugin_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "static", "templates", cls.DEFAULT_TEMPLATE_NAME)
        )
        if os.path.isfile(plugin_path):
            return plugin_path
        raise FileNotFoundError(
            f"{PNS_PLANNING_LABEL} template not found. "
            f"Set {cls.TEMPLATE_PATH_CONFIG_KEY} or place the file at {plugin_path}"
        )

    @classmethod
    def build_workbook(cls, aes) -> Tuple[io.BytesIO, str]:
        _ensure_scripts_in_path()
        from app.utils.safe_workbook import load_workbook_safe
        from import_upr_excel_data import build_import_context
        from pns_form_excel import (
            prepare_planning_workbook,
            write_planning_funding_rows,
            write_staff_rows,
        )

        template_path = cls.get_template_path()
        wb = load_workbook_safe(template_path, read_only=False, data_only=False)
        try:
            ns_name, country_name, iso3, year, period = _assignment_identity(aes)
            ctx = build_import_context([22])
            funding_item = ctx.t22_funding_item_id
            staff_item = ctx.staff_matrix_item_id
            _ns_names, country_id_by_iso3, iso3_to_ns_id = _indexes()
            _name_to_country, _name_to_ns, country_id_to_name, _ns_country, ns_id_to_iso3 = _country_name_maps(
                wb, country_id_by_iso3, iso3_to_ns_id
            )
            prepare_planning_workbook(wb, ns_name=ns_name, year=year)
            if year is not None and funding_item:
                from import_upr_excel_data import T22_BREAKDOWN_AREAS, T22_ROW_TOTAL_COLUMN

                columns = _form_columns(_published_item(22, funding_item)) or list(T22_BREAKDOWN_AREAS) + [
                    T22_ROW_TOTAL_COLUMN
                ]
                write_planning_funding_rows(
                    wb,
                    _matrix_cells(aes.id, funding_item),
                    ns_name=ns_name,
                    year=year,
                    country_id_to_name=country_id_to_name,
                    form_columns=columns,
                )
            if staff_item:
                from import_upr_excel_data import STAFF_INDICATOR_COLUMNS

                columns = _form_columns(_published_item(22, staff_item)) or list(STAFF_INDICATOR_COLUMNS.values())
                write_staff_rows(
                    wb,
                    _matrix_cells(aes.id, staff_item),
                    ns_id_to_iso3=ns_id_to_iso3,
                    form_columns=columns,
                )
            output = _save_workbook(wb, template_path)
            return output, _filename("PNS_Planning", country_name, iso3, period)
        except Exception:
            wb.close()
            raise

    @classmethod
    def validate_import_file(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        _ensure_scripts_in_path()
        from pns_form_excel import names_match, selected_national_society, workbook_has_planning_structure

        ns_name, _country, _iso3, year, _period = _assignment_identity(aes)
        try:
            wb = _load_workbook(file_bytes)
        except Exception:
            return _invalid("Invalid Excel file. Check the file format and try again.")
        try:
            if not workbook_has_planning_structure(wb):
                return _invalid("This file is not the PNS Planning workbook.")
            selected = selected_national_society(wb, planning=True)
            if selected and not names_match(selected, ns_name):
                return _invalid(
                    f"The workbook is for {selected}, but this assignment is {ns_name}."
                )
            warnings = []
            if year is None:
                warnings.append("This assignment has no planning year, so funding rows cannot be matched.")
            return {"valid": True, "message": "Workbook matches this PNS Planning assignment.", "errors": [], "warnings": warnings, "preview": {}}
        finally:
            wb.close()

    @classmethod
    def import_data_for_form(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        _ensure_scripts_in_path()
        from import_upr_excel_data import (
            STAFF_INDICATOR_COLUMNS,
            T22_BREAKDOWN_AREAS,
            T22_ROW_TOTAL_COLUMN,
            build_import_context,
        )
        from pns_form_excel import (
            names_match,
            planning_funding_cells,
            read_planning_data_rows,
            read_planning_grid_overrides,
            read_staff_rows,
            selected_national_society,
            staff_cells,
            workbook_has_planning_structure,
        )

        ns_name, _country, _iso3, year, period = _assignment_identity(aes)
        try:
            wb = _load_workbook(file_bytes)
        except Exception as exc:
            return {"success": False, "message": f"Invalid Excel file: {exc}", "updated_count": 0}
        try:
            if not workbook_has_planning_structure(wb):
                return {"success": False, "message": "This file is not the PNS Planning workbook.", "updated_count": 0}
            selected = selected_national_society(wb, planning=True)
            if selected and not names_match(selected, ns_name):
                return {
                    "success": False,
                    "message": f"The workbook is for {selected}, but this assignment is {ns_name}.",
                    "updated_count": 0,
                }
            ctx = build_import_context([22])
            warnings = list(ctx.warnings)
            if year is None:
                return {
                    "success": False,
                    "message": "This assignment has no planning year, so the workbook cannot be imported.",
                    "updated_count": 0,
                }
            _ns_names, country_id_by_iso3, iso3_to_ns_id = _indexes()
            name_to_country, _name_to_ns, _country_names, _ns_country, _ns_iso = _country_name_maps(
                wb, country_id_by_iso3, iso3_to_ns_id
            )
            data_rows = read_planning_data_rows(wb)
            source_rows = [row for row in data_rows if names_match(row["ns"], ns_name) and row["year"] == year]
            if not source_rows:
                source_rows = [
                    row
                    for row in read_planning_grid_overrides(wb)
                    if not row.get("ns") or names_match(row["ns"], ns_name)
                ]
            funding_columns = _form_columns(_published_item(22, ctx.t22_funding_item_id)) or list(
                T22_BREAKDOWN_AREAS
            ) + [T22_ROW_TOTAL_COLUMN]
            staff_columns = _form_columns(_published_item(22, ctx.staff_matrix_item_id)) or list(
                STAFF_INDICATOR_COLUMNS.values()
            )
            matrices: Dict[str, Any] = {}
            if ctx.t22_funding_item_id:
                cells, funding_warnings = planning_funding_cells(
                    source_rows,
                    ns_name=ns_name,
                    year=year,
                    country_name_to_id=name_to_country,
                    form_columns=funding_columns,
                )
                warnings.extend(funding_warnings)
                if cells:
                    matrices[str(ctx.t22_funding_item_id)] = cells
            else:
                warnings.append("The published PNS Planning funding matrix was not found.")
            if ctx.staff_matrix_item_id:
                cells, staff_warnings = staff_cells(
                    read_staff_rows(wb),
                    iso3_to_ns_id=iso3_to_ns_id,
                    form_columns=staff_columns,
                )
                warnings.extend(staff_warnings)
                if cells:
                    matrices[str(ctx.staff_matrix_item_id)] = cells
            payload = _empty_payload(period)
            payload["matrices"] = matrices
            return _stage(aes, payload, _dedupe(warnings))
        finally:
            wb.close()


class PnsReportingExcelService:
    TEMPLATE_PATH_CONFIG_KEY = "PNS_REPORTING_TEMPLATE_PATH"
    DEFAULT_TEMPLATE_NAME = "pns_reporting_form.xlsx"

    @classmethod
    def get_template_path(cls) -> str:
        configured = current_app.config.get(cls.TEMPLATE_PATH_CONFIG_KEY)
        if configured and os.path.isfile(configured):
            return configured
        plugin_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "static", "templates", cls.DEFAULT_TEMPLATE_NAME)
        )
        if os.path.isfile(plugin_path):
            return plugin_path
        raise FileNotFoundError(
            f"{PNS_REPORTING_LABEL} template not found. "
            f"Set {cls.TEMPLATE_PATH_CONFIG_KEY} or place the file at {plugin_path}"
        )

    @classmethod
    def build_workbook(cls, aes) -> Tuple[io.BytesIO, str]:
        _ensure_scripts_in_path()
        from app.utils.safe_workbook import load_workbook_safe
        from import_upr_excel_data import T23_PNS_FUNDING_COLUMNS, build_import_context
        from pns_form_excel import prepare_reporting_workbook, reporting_column_map, write_reporting_funding_rows

        template_path = cls.get_template_path()
        wb = load_workbook_safe(template_path, read_only=False, data_only=False)
        try:
            ns_name, country_name, iso3, _year, period = _assignment_identity(aes)
            ctx = build_import_context([23])
            _ns_names, country_id_by_iso3, iso3_to_ns_id = _indexes()
            _name_to_country, _name_to_ns, _country_names, ns_id_to_country, _ns_iso = _country_name_maps(
                wb, country_id_by_iso3, iso3_to_ns_id
            )
            prepare_reporting_workbook(wb, ns_name=ns_name)
            columns = _form_columns(_published_item(23, ctx.pns_funding_item_id)) or list(
                T23_PNS_FUNDING_COLUMNS.values()
            )
            if ctx.pns_funding_item_id:
                write_reporting_funding_rows(
                    wb,
                    _matrix_cells(aes.id, ctx.pns_funding_item_id),
                    ns_id_to_country=ns_id_to_country,
                    column_map=reporting_column_map(columns),
                )
            output = _save_workbook(wb, template_path)
            return output, _filename("PNS_Reporting", country_name, iso3, period)
        except Exception:
            wb.close()
            raise

    @classmethod
    def validate_import_file(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        _ensure_scripts_in_path()
        from pns_form_excel import names_match, selected_national_society, workbook_has_reporting_structure

        ns_name, *_rest = _assignment_identity(aes)
        try:
            wb = _load_workbook(file_bytes)
        except Exception:
            return _invalid("Invalid Excel file. Check the file format and try again.")
        try:
            if not workbook_has_reporting_structure(wb):
                return _invalid("This file is not the PNS Reporting workbook.")
            selected = selected_national_society(wb, planning=False)
            if selected and not names_match(selected, ns_name):
                return _invalid(f"The workbook is for {selected}, but this assignment is {ns_name}.")
            return {
                "valid": True,
                "message": "Workbook matches this PNS Reporting assignment.",
                "errors": [],
                "warnings": [],
                "preview": {},
            }
        finally:
            wb.close()

    @classmethod
    def import_data_for_form(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        _ensure_scripts_in_path()
        from import_upr_excel_data import T23_PNS_FUNDING_COLUMNS, build_import_context
        from pns_form_excel import (
            names_match,
            read_reporting_funding_rows,
            reporting_column_map,
            reporting_funding_cells,
            selected_national_society,
            workbook_has_reporting_structure,
        )

        ns_name, _country, _iso3, _year, period = _assignment_identity(aes)
        try:
            wb = _load_workbook(file_bytes)
        except Exception as exc:
            return {"success": False, "message": f"Invalid Excel file: {exc}", "updated_count": 0}
        try:
            if not workbook_has_reporting_structure(wb):
                return {"success": False, "message": "This file is not the PNS Reporting workbook.", "updated_count": 0}
            selected = selected_national_society(wb, planning=False)
            if selected and not names_match(selected, ns_name):
                return {
                    "success": False,
                    "message": f"The workbook is for {selected}, but this assignment is {ns_name}.",
                    "updated_count": 0,
                }
            ctx = build_import_context([23])
            warnings = list(ctx.warnings)
            _ns_names, country_id_by_iso3, iso3_to_ns_id = _indexes()
            _name_to_country, name_to_ns, _country_names, _ns_country, _ns_iso = _country_name_maps(
                wb, country_id_by_iso3, iso3_to_ns_id
            )
            columns = _form_columns(_published_item(23, ctx.pns_funding_item_id)) or list(
                T23_PNS_FUNDING_COLUMNS.values()
            )
            matrices: Dict[str, Any] = {}
            if ctx.pns_funding_item_id:
                cells, row_warnings = reporting_funding_cells(
                    read_reporting_funding_rows(wb),
                    country_name_to_ns_id=name_to_ns,
                    column_map=reporting_column_map(columns),
                )
                warnings.extend(row_warnings)
                if cells:
                    matrices[str(ctx.pns_funding_item_id)] = cells
            else:
                warnings.append("The published PNS Reporting funding matrix was not found.")
            payload = _empty_payload(period)
            payload["matrices"] = matrices
            return _stage(aes, payload, _dedupe(warnings))
        finally:
            wb.close()


def _published_item(_template_id: int, item_id: int):
    from app.models.form_items import FormItem

    if not item_id:
        return None
    return FormItem.query.get(int(item_id))


def _empty_payload(period: str) -> Dict[str, Any]:
    return {
        "fields": {},
        "matrices": {},
        "dynamic_indicators": [],
        "repeat_slots": [],
        "meta": {"period": period},
    }


def _invalid(message: str) -> Dict[str, Any]:
    return {"valid": False, "message": message, "errors": [message], "warnings": [], "preview": {}}


def _dedupe(warnings: Sequence[str]) -> List[str]:
    seen = set()
    out = []
    for warning in warnings:
        text = str(warning).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
