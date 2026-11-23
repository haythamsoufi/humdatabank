"""Which legacy public path answers from Databank, and which is forwarded.

FDRS Tools → Endpoints stores the choice on the FDRS ``PluginData`` row. Public
routes in ``public_compat_routes`` call :func:`uses_original_api` before reading
the published snapshot. A path with no Databank implementation stays on the
original data API and cannot be switched.

The public site keeps calling this server. "Original API" means this server
fetches the response from ``FDRS_DATA_API_BASE`` with ``FDRS_DATA_API_KEY``.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Mapping

from flask import current_app, has_app_context
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.plugin_data import PluginData

logger = logging.getLogger(__name__)

PLUGIN_ID = "fdrs"
SECTION = "public_endpoint_source"
SOURCE_DATABANK = "databank"
SOURCE_ORIGINAL = "original"
_SOURCES = frozenset({SOURCE_DATABANK, SOURCE_ORIGINAL})


@dataclass(frozen=True)
class PublicEndpoint:
    id: str
    path: str
    methods: tuple[str, ...]
    label: str
    summary: str
    default_source: str = SOURCE_DATABANK
    switchable: bool = True
    locked_reason: str = ""


PUBLIC_ENDPOINTS: tuple[PublicEndpoint, ...] = (
    PublicEndpoint(
        "lastpublishedyear",
        "/api/lastpublishedyear",
        ("GET",),
        "Last published year",
        "Greatest year with published public FDRS data.",
    ),
    PublicEndpoint(
        "entities_ns",
        "/api/entities/ns",
        ("GET",),
        "National Societies",
        "Society list: DON code, zone, and coordinates.",
    ),
    PublicEndpoint(
        "entities_ns_one",
        "/api/entities/ns/<don_code>",
        ("GET",),
        "One National Society",
        "Society profile for one DON code.",
    ),
    PublicEndpoint(
        "data",
        "/api/data",
        ("GET",),
        "KPI series",
        "Published KPI series as the legacy nested tree.",
    ),
    PublicEndpoint(
        "dataimputed",
        "/api/dataimputed",
        ("GET",),
        "Imputed KPI series",
        "Same tree as /api/data. The client sends codes that include imputed values.",
    ),
    PublicEndpoint(
        "kpi_imputed",
        "/api/KpiImputedValue",
        ("GET",),
        "Imputed map layer",
        "One value per society for a KPI code and year.",
    ),
    PublicEndpoint(
        "global_validation",
        "/api/globalvalidationdata",
        ("GET",),
        "Volunteer headline",
        "Three-year rolling mean of reported volunteers, per zone and worldwide.",
    ),
    PublicEndpoint(
        "kpi_value",
        "/api/kpivalue",
        ("GET",),
        "KPI values",
        "Published value of one KPI for each society.",
    ),
    PublicEndpoint(
        "documents",
        "/api/documents",
        ("GET",),
        "Documents",
        "Publications and, with a DON code, that society's public approved documents.",
    ),
    PublicEndpoint(
        "embeddedcontent",
        "/api/embeddedcontent",
        ("GET",),
        "Embedded content",
        "Databank serves unified planning, the international overview, and global initiatives. "
        "Other types always use the original API. Choosing Original API sends every type upstream.",
    ),
    PublicEndpoint(
        "smarttran",
        "/api/smarttran",
        ("GET",),
        "Page translations",
        "Translation strings for a page.",
        default_source=SOURCE_ORIGINAL,
        switchable=False,
        locked_reason="Page translations are only available from the original data API.",
    ),
    PublicEndpoint(
        "tran",
        "/api/tran",
        ("GET",),
        "Key highlight",
        "One translated string.",
        default_source=SOURCE_ORIGINAL,
        switchable=False,
        locked_reason="Key highlights are only available from the original data API.",
    ),
    PublicEndpoint(
        "offices",
        "/api/offices",
        ("GET",),
        "Offices",
        "Office map.",
        default_source=SOURCE_ORIGINAL,
        switchable=False,
        locked_reason="Offices are only available from the original data API.",
    ),
    PublicEndpoint(
        "document_subscribe",
        "/api/documentSubscribe",
        ("POST",),
        "Document mailing list",
        "Sign-up for document updates.",
        default_source=SOURCE_ORIGINAL,
        switchable=False,
        locked_reason="The mailing list is only available from the original data API.",
    ),
    PublicEndpoint(
        "csv_export",
        "/csv/export",
        ("GET",),
        "Full export",
        "Published public figures as CSV, or Excel when excel=1.",
    ),
    PublicEndpoint(
        "csv_export_ns",
        "/csv/exportns",
        ("GET",),
        "Society export",
        "Published public figures for one society (doncode).",
    ),
)

_BY_ID = {endpoint.id: endpoint for endpoint in PUBLIC_ENDPOINTS}


def _effective(endpoint: PublicEndpoint, stored: Mapping[str, str]) -> str:
    if not endpoint.switchable:
        return endpoint.default_source
    value = stored.get(endpoint.id)
    if value in _SOURCES:
        return value
    return endpoint.default_source


def _stored() -> dict[str, str]:
    if not has_app_context():
        return {}
    row = PluginData.query.filter_by(plugin_id=PLUGIN_ID).first()
    if row is None or not isinstance(row.data, dict):
        return {}
    raw = row.data.get(SECTION)
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in _BY_ID and value in _SOURCES
    }


def uses_original_api(endpoint_id: str) -> bool:
    """True when this path should be fetched from the legacy data API."""
    endpoint = _BY_ID.get(endpoint_id)
    if endpoint is None:
        return False
    return _effective(endpoint, _stored()) == SOURCE_ORIGINAL


def endpoint_choices() -> list[dict]:
    """One row per public path, in catalog order, with the source in effect."""
    stored = _stored()
    return [
        {
            "id": endpoint.id,
            "path": endpoint.path,
            "methods": list(endpoint.methods),
            "label": endpoint.label,
            "summary": endpoint.summary,
            "source": _effective(endpoint, stored),
            "switchable": endpoint.switchable,
            "locked_reason": endpoint.locked_reason,
        }
        for endpoint in PUBLIC_ENDPOINTS
    ]


def original_endpoint_paths() -> list[str]:
    """Switchable paths currently forwarded to the original data API."""
    stored = _stored()
    return [
        endpoint.path
        for endpoint in PUBLIC_ENDPOINTS
        if endpoint.switchable and _effective(endpoint, stored) == SOURCE_ORIGINAL
    ]


def _write_section(section: dict[str, str]) -> bool:
    try:
        row = PluginData.query.filter_by(plugin_id=PLUGIN_ID).with_for_update().first()
        if row is None:
            row = PluginData(plugin_id=PLUGIN_ID, data={SECTION: dict(section)})
            db.session.add(row)
        else:
            data = copy.deepcopy(row.data) if isinstance(row.data, dict) else {}
            data[SECTION] = dict(section)
            row.data = data
            flag_modified(row, "data")
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        if has_app_context():
            current_app.logger.error(
                "Could not save FDRS public endpoint sources: %s", exc, exc_info=True
            )
        else:
            logger.error("Could not save FDRS public endpoint sources: %s", exc, exc_info=True)
        return False


def save_endpoint_sources(choices: Mapping[str, str]) -> str | None:
    """Replace the stored source for every switchable path.

    Defaults are not stored. Returns an error message, or None when saved.
    """
    section: dict[str, str] = {}
    for endpoint in PUBLIC_ENDPOINTS:
        if not endpoint.switchable:
            continue
        if endpoint.id not in choices:
            return f"Choose a source for {endpoint.path}."
        value = choices[endpoint.id]
        if value not in _SOURCES:
            return f"Choose Databank or the original API for {endpoint.path}."
        if value != endpoint.default_source:
            section[endpoint.id] = value
    if not _write_section(section):
        return "Could not save endpoint sources."
    return None


def apply_source_to_all_switchable(source: str) -> str | None:
    """Point every switchable path at ``source``. Locked paths stay as they are."""
    if source not in _SOURCES:
        return "Unknown source."
    return save_endpoint_sources(
        {endpoint.id: source for endpoint in PUBLIC_ENDPOINTS if endpoint.switchable}
    )
