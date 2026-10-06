"""Export and import for the template 21 FDRS data-collection workbook."""

from __future__ import annotations

import io
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from plugins.fdrs.excel.fdrs_form_excel import (
    read_fdrs_workbook,
    workbook_has_fdrs_structure,
    write_fdrs_answers,
    write_fdrs_identity,
)
from plugins.fdrs.scripts_path import ensure_fdrs_scripts_in_path


def _fdrs_constants():
    ensure_fdrs_scripts_in_path()
    from fdrs_sync_constants import (
        FDRS_INCOME_SOURCES_MATRIX_COLUMN,
        FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
        FDRS_NETWORK_SUPPORT_GIVEN_COLUMN,
        FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
        FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN,
        FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
        FDRS_QUESTION_KPI_TO_ITEM,
    )

    return {
        "income_column": FDRS_INCOME_SOURCES_MATRIX_COLUMN,
        "income_item": FDRS_INCOME_SOURCES_MATRIX_ITEM_ID,
        "given_column": FDRS_NETWORK_SUPPORT_GIVEN_COLUMN,
        "given_item": FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID,
        "received_column": FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN,
        "received_item": FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID,
        "question_items": FDRS_QUESTION_KPI_TO_ITEM,
    }

FDRS_EXCEL_LABEL = "FDRS"


class FdrsExcelService:
    TEMPLATE_PATH_CONFIG_KEY = "FDRS_EXCEL_TEMPLATE_PATH"
    DEFAULT_TEMPLATE_NAME = "fdrs_form.xlsx"

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
            f"{FDRS_EXCEL_LABEL} template not found. "
            f"Set {cls.TEMPLATE_PATH_CONFIG_KEY} or place the file at {plugin_path}"
        )

    @classmethod
    def build_workbook(cls, aes) -> Tuple[io.BytesIO, str]:
        from app.utils.safe_workbook import load_workbook_safe

        template_path = cls.get_template_path()
        wb = load_workbook_safe(template_path, read_only=False, data_only=False)
        try:
            ns_name, country_name, iso3, year, period = _assignment_identity(aes)
            write_fdrs_identity(wb, ns_name=ns_name, year=year)
            write_fdrs_answers(wb, _answers_from_assignment(aes.id))
            output = _save_workbook(wb, template_path)
            return output, _filename(country_name, iso3, period)
        except Exception:
            wb.close()
            raise

    @classmethod
    def validate_import_file(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        from app.utils.safe_workbook import load_workbook_safe

        try:
            wb = load_workbook_safe(file_bytes, read_only=False, data_only=False)
        except Exception:
            return _invalid("Invalid Excel file. Check the file format and try again.")
        try:
            if not workbook_has_fdrs_structure(wb):
                return _invalid("This file is not the FDRS data-collection workbook.")
            _ns_name, _country, _iso3, year, _period = _assignment_identity(aes)
            warnings = []
            if year is None:
                warnings.append("This assignment has no reporting year. The workbook year was not checked.")
            return {
                "valid": True,
                "message": "Workbook matches the FDRS data-collection form.",
                "errors": [],
                "warnings": warnings,
                "preview": {},
            }
        finally:
            wb.close()

    @classmethod
    def import_data_for_form(cls, aes, file_bytes: bytes) -> Dict[str, Any]:
        from app.services.imports.scoped_import_guard import filter_staged_import_payload
        from app.utils.safe_workbook import load_workbook_safe

        try:
            wb = load_workbook_safe(file_bytes, read_only=False, data_only=False)
        except Exception as exc:
            return {"success": False, "message": f"Invalid Excel file: {exc}", "updated_count": 0}
        try:
            if not workbook_has_fdrs_structure(wb):
                return {"success": False, "message": "This file is not the FDRS data-collection workbook.", "updated_count": 0}
            parsed = read_fdrs_workbook(wb)
            _ns_name, _country, _iso3, _year, period = _assignment_identity(aes)
            payload = _payload_from_answers(parsed, period)
            extra = filter_staged_import_payload(aes, payload)
            warnings = list(parsed.get("warnings") or [])
            warnings.extend(
                item.get("message", str(item)) if isinstance(item, dict) else str(item)
                for item in (extra.get("warnings") or [])
            )
            return {
                "success": True,
                "stage_only": True,
                "payload": payload,
                "warnings": warnings,
                "warning_items": extra.get("warning_items") or [],
                "updated_count": extra.get("updated_count", 0),
            }
        finally:
            wb.close()


def _assignment_identity(aes) -> Tuple[str, str, str, Optional[int], str]:
    from app.models.organization import NationalSociety
    from app.utils.api_serialization import _country_for_aes

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
    return ns_name.strip(), country_name.strip(), iso3, _period_year(period), period.strip()


def _period_year(period_name: str) -> Optional[int]:
    for token in (period_name or "").replace("-", " ").split():
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1990 <= year <= 2100:
                return year
    return None


def _published_items():
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplate

    template = FormTemplate.query.get(21)
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return []
    return FormItem.query.filter_by(template_id=21, version_id=int(version_id), archived=False).all()


def _kpi_to_item_id() -> Dict[str, int]:
    items = _published_items()
    published_ids = {int(item.id) for item in items}
    found: Dict[str, int] = {}
    for item in items:
        bank = getattr(item, "indicator_bank", None)
        code = (getattr(bank, "fdrs_kpi_code", None) or "").strip()
        if code and code not in found:
            found[code] = int(item.id)
    for kpi, item_id in _fdrs_constants()["question_items"].items():
        if int(item_id) in published_ids:
            found.setdefault(kpi, int(item_id))
    return found


def _item_on_published(item_id: int):
    items = {int(item.id): item for item in _published_items()}
    return items.get(int(item_id))


def _matrix_column(item, fallback: str) -> str:
    config = getattr(item, "config", None) or {}
    matrix = config.get("matrix_config") if isinstance(config, dict) else None
    columns = (matrix or {}).get("columns") if isinstance(matrix, dict) else None
    if columns:
        first = columns[0]
        name = first.get("name") if isinstance(first, dict) else first
        if name:
            return str(name)
    return fallback


def _form_data(aes_id: int, item_id: int):
    from app.models.forms import FormData

    if not item_id:
        return None
    return FormData.query.filter_by(
        assignment_entity_status_id=int(aes_id),
        form_item_id=int(item_id),
    ).first()


def _answers_from_assignment(aes_id: int) -> Dict[str, Any]:
    by_kpi = _kpi_to_item_id()
    scalars: Dict[str, Any] = {}
    disagg: Dict[str, Any] = {}
    for kpi, item_id in by_kpi.items():
        entry = _form_data(aes_id, item_id)
        if not entry:
            continue
        raw = getattr(entry, "disagg_data", None)
        if isinstance(raw, dict) and raw.get("mode") == "sex_age":
            disagg[kpi] = raw
            continue
        value = getattr(entry, "value", None)
        if value not in (None, ""):
            scalars[kpi] = value
    constants = _fdrs_constants()
    income_item = _item_on_published(constants["income_item"])
    income_column = _matrix_column(income_item, constants["income_column"])
    income = _matrix_amounts(_form_data(aes_id, constants["income_item"]), income_column)
    given_item = _item_on_published(constants["given_item"])
    given_column = _matrix_column(given_item, constants["given_column"])
    received_item = _item_on_published(constants["received_item"])
    received_column = _matrix_column(received_item, constants["received_column"])
    return {
        "scalars": scalars,
        "disagg": disagg,
        "income": income,
        "support_given": _support_rows(_form_data(aes_id, constants["given_item"]), given_column),
        "support_received": _support_rows(_form_data(aes_id, constants["received_item"]), received_column),
    }


def _matrix_amounts(entry, column: str) -> Dict[str, Any]:
    cells = _matrix_dict(entry)
    suffix = f"_{column}"
    amounts = {}
    for key, value in cells.items():
        if isinstance(key, str) and key.endswith(suffix):
            amounts[key[: -len(suffix)]] = value
    return amounts


def _support_rows(entry, column: str) -> List[Dict[str, Any]]:
    amounts = _matrix_amounts(entry, column)
    return [{"name": name, "amount": amount} for name, amount in amounts.items()]


def _matrix_dict(entry) -> Dict[str, Any]:
    raw = getattr(entry, "disagg_data", None) if entry else None
    return raw if isinstance(raw, dict) else {}


def _staged_disagg(disagg: Dict[str, Any]) -> Dict[str, Any]:
    """Drop a null indirect reach so staging does not clear that form field."""
    values = dict(disagg.get("values") or {})
    if values.get("indirect") is None:
        values.pop("indirect", None)
    return {**disagg, "values": values}


def _payload_from_answers(parsed: Dict[str, Any], period: str) -> Dict[str, Any]:
    by_kpi = _kpi_to_item_id()
    fields: Dict[str, Any] = {}
    for kpi, value in (parsed.get("scalars") or {}).items():
        item_id = by_kpi.get(kpi)
        if item_id:
            fields[str(item_id)] = {"value": value}
    for kpi, disagg in (parsed.get("disagg") or {}).items():
        item_id = by_kpi.get(kpi)
        if item_id and (disagg.get("values") or {}).get("direct"):
            fields[str(item_id)] = {"disagg_data": _staged_disagg(disagg)}
    matrices: Dict[str, Any] = {}
    constants = _fdrs_constants()
    income_item = _item_on_published(constants["income_item"])
    if income_item and parsed.get("income"):
        column = _matrix_column(income_item, constants["income_column"])
        matrices[str(income_item.id)] = {
            f"{label}_{column}": amount for label, amount in parsed["income"].items()
        }
    _put_support_matrix(
        matrices,
        _item_on_published(constants["given_item"]),
        constants["given_column"],
        parsed.get("support_given") or [],
    )
    _put_support_matrix(
        matrices,
        _item_on_published(constants["received_item"]),
        constants["received_column"],
        parsed.get("support_received") or [],
    )
    return {
        "fields": fields,
        "matrices": matrices,
        "dynamic_indicators": [],
        "repeat_slots": [],
        "meta": {"period": period},
    }


def _put_support_matrix(matrices: Dict[str, Any], item, fallback_column: str, rows: List[Dict[str, Any]]) -> None:
    if not item or not rows:
        return
    column = _matrix_column(item, fallback_column)
    matrices[str(item.id)] = {f"{row['name']}_{column}": row["amount"] for row in rows if row.get("name")}


def _save_workbook(wb, template_path: str) -> io.BytesIO:
    from plugins.upr.excel._scripts_path import ensure_scripts_in_path

    ensure_scripts_in_path()
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


def _filename(country_name: str, iso3: str, period: str) -> str:
    safe_country = re.sub(r"[^\w\-]+", "_", country_name or iso3 or "country").strip("_") or "country"
    safe_period = re.sub(r"[^\w\-]+", "_", period or "period").strip("_") or "period"
    return f"FDRS_{safe_country}_{safe_period}.xlsx"


def _invalid(message: str) -> Dict[str, Any]:
    return {"valid": False, "message": message, "errors": [message], "warnings": [], "preview": {}}
