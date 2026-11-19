"""Plugin field that renders the DREF report for the current project cycle."""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import has_request_context, request

from app.plugins.base import BaseFieldType
from plugins.dref_monitoring.constants import FIELD_TYPE


class DrefOperationalReportField(BaseFieldType):
    """One field. The figures stay in the DREF tables, not as generic form items."""

    @property
    def type_name(self) -> str:
        return FIELD_TYPE

    @property
    def display_name(self) -> str:
        return "DREF operational report"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "Activity status, people reached, expenditure, and indicator actuals for one DREF reporting period."

    @property
    def icon(self) -> str:
        return "fas fa-clipboard-list"

    def get_form_builder_config(self) -> Dict[str, Any]:
        return {
            "title": "DREF operational report",
            "icon": self.icon,
            "custom_template": "builder.html",
            "fields": [],
        }

    def get_entry_form_config(self) -> Dict[str, Any]:
        return {
            "template": "field.html",
            "es_module_path": "/plugins/static/dref_monitoring/js/report_field.js",
            "es_module_class": "DrefOperationalReportField",
            "css_files": [],
            "schema_version": "1.0.0",
            "data_attributes": ["data-field-id", "data-can-edit"],
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return True

    def get_data_storage_config(self) -> Dict[str, Any]:
        return {"type": "json", "fields": [], "max_size": 500000}

    def normalize_value(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(data, dict):
            return None
        if "activities" not in data and "narrative" not in data and "indicators" not in data:
            return None
        error = _save(data)
        if error:
            return {"error": error}
        return None

    def validate_value(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
        if isinstance(data, dict):
            message = data.get("error")
            if message:
                return str(message)
        return None


def _save(data: dict) -> str | None:
    if not has_request_context():
        return "Open this report from the project cycle."
    aes_id = (request.view_args or {}).get("aes_id")
    if not aes_id:
        return "Open this report from the project cycle."
    from plugins.dref_monitoring.services.reporting import apply_cycle_payload, context_for_assignment

    found = context_for_assignment(int(aes_id))
    if found is None:
        return "This cycle is not a DREF reporting period."
    operation, period = found
    from flask_login import current_user

    user_id = current_user.id if getattr(current_user, "is_authenticated", False) else None
    return apply_cycle_payload(operation, period, data, user_id)
