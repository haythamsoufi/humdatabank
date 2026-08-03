"""Report definition JSON schema loading and validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.utils.schema_validation import SchemaValidationError, validate_plugin_config

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report_definition_v1.json"


@lru_cache(maxsize=1)
def load_report_definition_schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_report_definition(definition: dict[str, Any]) -> None:
    """Validate a report definition against the v1 JSON schema."""
    schema = load_report_definition_schema()
    try:
        validate_plugin_config(definition, schema)
    except SchemaValidationError as exc:
        raise ValueError(str(exc)) from exc


def default_definition() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "filters": {
            "template_ids": [],
            "period_names": [],
            "country_ids": [],
            "assignment_statuses": ["submitted", "approved"],
            "include_public_submissions": False,
        },
        "sections": [],
    }
