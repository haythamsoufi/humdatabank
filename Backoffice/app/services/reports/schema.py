"""Report definition JSON schema loading, validation, and v1→v2 migration."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.reports.translation_helpers import normalize_language, wrap_legacy_text
from app.utils.schema_validation import SchemaValidationError, validate_plugin_config

_SCHEMA_V2_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report_definition_v2.json"

DEFAULT_GRID_COLUMNS = 12
DEFAULT_ROW_HEIGHT = 80
DEFAULT_WIDGET_HEIGHT = 4
DEFAULT_WIDGET_WIDTH = 6


@lru_cache(maxsize=1)
def load_report_definition_schema() -> dict[str, Any]:
    with _SCHEMA_V2_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_report_definition(definition: dict[str, Any]) -> None:
    """Validate a report definition against the v2 JSON schema."""
    schema = load_report_definition_schema()
    try:
        validate_plugin_config(definition, schema)
    except SchemaValidationError as exc:
        raise ValueError(str(exc)) from exc


def default_definition(*, languages: list[str] | None = None) -> dict[str, Any]:
    langs = languages or ["en"]
    default_lang = normalize_language(langs[0])
    return {
        "schema_version": 2,
        "languages": [normalize_language(lang) for lang in langs],
        "default_language": default_lang,
        "theme": {
            "primary_color": "#0d9488",
            "font_family": "Inter, system-ui, sans-serif",
        },
        "filters": {
            "template_ids": [],
            "period_names": [],
            "country_ids": [],
            "assignment_statuses": ["submitted", "approved"],
            "include_public_submissions": False,
        },
        "sections": [],
    }


def default_section_grid() -> dict[str, int]:
    return {"columns": DEFAULT_GRID_COLUMNS, "row_height": DEFAULT_ROW_HEIGHT}


def default_widget_layout(*, x: int = 0, y: int = 0, w: int = DEFAULT_WIDGET_WIDTH, h: int = DEFAULT_WIDGET_HEIGHT) -> dict[str, int]:
    return {"x": x, "y": y, "w": w, "h": h}


def _widget_default_height(widget_type: str) -> int:
    return {
        "kpi": 2,
        "divider": 1,
        "text": 3,
        "image": 4,
        "embed": 4,
        "map": 5,
        "indicator_dashboard": 6,
        "table": 4,
    }.get(widget_type, DEFAULT_WIDGET_HEIGHT)


def assign_sequential_layouts(widgets: list[dict[str, Any]], *, columns: int = DEFAULT_GRID_COLUMNS) -> list[dict[str, Any]]:
    """Assign grid positions to widgets lacking layout (stacked full-width rows)."""
    y = 0
    result: list[dict[str, Any]] = []
    for widget in widgets:
        w = dict(widget)
        if not w.get("layout"):
            h = _widget_default_height(w.get("type") or "kpi")
            w["layout"] = default_widget_layout(x=0, y=y, w=columns, h=h)
            y += h
        result.append(w)
    return result


def migrate_v1_to_v2(definition: dict[str, Any] | None, *, default_language: str = "en") -> dict[str, Any]:
    """Convert a v1 (or partial) definition into schema v2 shape."""
    src = copy.deepcopy(definition or {})
    if int(src.get("schema_version") or 0) >= 2:
        return src

    lang = normalize_language(default_language)
    languages = src.get("languages") or [lang]
    if lang not in [normalize_language(item) for item in languages]:
        languages = [lang, *[normalize_language(item) for item in languages if normalize_language(item) != lang]]

    out: dict[str, Any] = {
        "schema_version": 2,
        "languages": languages,
        "default_language": lang,
        "theme": src.get("theme") or {
            "primary_color": "#0d9488",
            "font_family": "Inter, system-ui, sans-serif",
        },
        "filters": src.get("filters") or {
            "template_ids": [],
            "period_names": [],
            "country_ids": [],
            "assignment_statuses": ["submitted", "approved"],
            "include_public_submissions": False,
        },
        "sections": [],
    }

    for section in src.get("sections") or []:
        sec: dict[str, Any] = {
            "id": section.get("id") or "section",
            "order": int(section.get("order") or 0),
            "title_translations": section.get("title_translations") or wrap_legacy_text(section.get("title"), language=lang),
            "footnote_translations": section.get("footnote_translations") or wrap_legacy_text(section.get("footnote"), language=lang),
            "grid": section.get("grid") or default_section_grid(),
            "widgets": [],
        }
        if section.get("dynamic_indicators"):
            dyn = copy.deepcopy(section["dynamic_indicators"])
            if dyn.get("indicator_footnotes") and isinstance(dyn["indicator_footnotes"], dict):
                converted: dict[str, dict[str, str]] = {}
                for key, val in dyn["indicator_footnotes"].items():
                    if isinstance(val, dict):
                        converted[str(key)] = val
                    elif isinstance(val, str) and val.strip():
                        converted[str(key)] = {lang: val.strip()}
                dyn["indicator_footnotes"] = converted
            if not dyn.get("default_widget_layout"):
                dyn["default_widget_layout"] = default_widget_layout(w=DEFAULT_GRID_COLUMNS, h=DEFAULT_WIDGET_HEIGHT)
            sec["dynamic_indicators"] = dyn
        if section.get("interactions"):
            sec["interactions"] = section["interactions"]

        widgets: list[dict[str, Any]] = []
        for widget in section.get("widgets") or []:
            w: dict[str, Any] = {
                "id": widget.get("id") or "widget",
                "type": widget.get("type") or "text",
                "title_translations": widget.get("title_translations") or wrap_legacy_text(widget.get("title"), language=lang),
                "footnote_translations": widget.get("footnote_translations") or wrap_legacy_text(widget.get("footnote"), language=lang),
                "layout": widget.get("layout") or None,
            }
            if widget.get("data_source"):
                w["data_source"] = widget["data_source"]
            if widget.get("chart_options"):
                w["chart_options"] = widget["chart_options"]
            if widget.get("content_translations"):
                w["content_translations"] = widget["content_translations"]
            elif widget.get("content"):
                w["content_translations"] = wrap_legacy_text(widget.get("content"), language=lang)
            if widget.get("asset_key"):
                w["asset_key"] = widget["asset_key"]
            if widget.get("embed_url"):
                w["embed_url"] = widget["embed_url"]
            if widget.get("embed_html"):
                w["embed_html"] = widget["embed_html"]
            widgets.append(w)

        sec["widgets"] = assign_sequential_layouts(widgets, columns=sec["grid"]["columns"])
        out["sections"].append(sec)

    out["sections"].sort(key=lambda s: int(s.get("order") or 0))
    return out
