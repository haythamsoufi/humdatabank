"""
IFRC Indicator Bank Web API compatibility layer.

Exposes the legacy IFRC Indicator Bank HTTP contract (used by the Blazor public
client) backed by Humanitarian Databank Backoffice data. Auth accepts X-API-Key
(as the Blazor client sends) or Authorization: Bearer.
"""

from __future__ import annotations

import io
import os
from functools import wraps
from typing import Any, Dict, List, Optional, Set, Tuple

import requests as http_requests
from flask import Blueprint, current_app, g, jsonify, make_response, request
from openpyxl import Workbook

from app import db
from app.models import (
    CommonWord,
    IndicatorBank,
    IndicatorBankType,
    IndicatorBankUnit,
    IndicatorSuggestion,
    Sector,
    SubSector,
)
from app.routes.api.indicators import (
    _build_sector_subsector_names,
    _get_localized_type_unit,
)
from app.services.indicator_resolution_service import IndicatorResolutionService
from app.services import storage_service as storage
from app.services.security.api_authentication import authenticate_db_api_key_only
from app.utils.api_helpers import api_error, get_json_safe
from app.utils.datetime_helpers import utcnow
from app.utils.rate_limiting import api_rate_limit
from app.utils.sql_utils import safe_ilike_pattern

indicator_bank_compat_bp = Blueprint("indicator_bank_compat", __name__)

_SECTOR_LEVELS = ("primary", "secondary", "tertiary")

_EXCEL_HEADERS = [
    "id",
    "indicator",
    "definition",
    "unit of measurement",
    "type of measurement",
    "comments",
    "q1",
    "q2",
    "q3",
    "emergency",
    "date modified",
    "archived",
    "indicator source",
    "disaggregation",
    "primary sector",
    "primary subsector",
    "secondary sector",
    "secondary subsector",
    "tertiary sector",
    "tertiary subsector",
    "related programmes",
    "tags",
    "SPEF",
]


def _compat_locale() -> str:
    raw = (request.headers.get("X-Language") or request.args.get("language") or "en").strip()
    return raw.lower().split("_", 1)[0].split("-", 1)[0] or "en"


def _localized_text(translations: Optional[dict], locale: str, fallback: Optional[str]) -> str:
    if translations and isinstance(translations, dict):
        val = translations.get(locale)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return (fallback or "").strip()


def _require_compat_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_result = authenticate_db_api_key_only()
        if hasattr(auth_result, "status_code"):
            return auth_result
        g.skip_auth = True
        return f(*args, **kwargs)

    decorated._ep_auth = "api_key"
    return decorated


def _verify_recaptcha(token: str) -> bool:
    """Validate Google reCAPTCHA Enterprise token for suggestion submissions."""
    token = (token or "").strip()
    if not token:
        return False

    project = (current_app.config.get("RECAPTCHA_PROJECT_ID") or "").strip()
    api_key = (current_app.config.get("RECAPTCHA_API_KEY") or "").strip()
    site_key = (current_app.config.get("RECAPTCHA_SITE_KEY") or "").strip()
    expected_action = (current_app.config.get("RECAPTCHA_EXPECTED_ACTION") or "SendSuggestion").strip()
    threshold = float(current_app.config.get("RECAPTCHA_MIN_SCORE") or 0.5)

    if not project or not api_key:
        current_app.logger.warning(
            "reCAPTCHA validation skipped (RECAPTCHA_PROJECT_ID / RECAPTCHA_API_KEY not configured)"
        )
        return True

    url = (
        f"https://recaptchaenterprise.googleapis.com/v1/projects/{project}"
        f"/assessments?key={api_key}"
    )
    payload = {
        "event": {
            "token": token,
            "siteKey": site_key or None,
            "expectedAction": expected_action,
        }
    }
    try:
        resp = http_requests.post(url, json=payload, timeout=5)
        if not resp.ok:
            current_app.logger.warning("reCAPTCHA assessment HTTP %s: %s", resp.status_code, resp.text[:300])
            return False
        data = resp.json()
        token_props = data.get("tokenProperties") or {}
        if not token_props.get("valid"):
            return False
        if token_props.get("action") and token_props.get("action") != expected_action:
            return False
        score = (data.get("riskAnalysis") or {}).get("score", 0)
        return float(score) >= threshold
    except Exception as exc:
        current_app.logger.warning("reCAPTCHA validation failed: %s", exc)
        return False


def _emergency_to_string(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else ""
    if value is None:
        return ""
    return str(value).strip()


def _load_sector_maps(indicators: List[IndicatorBank]) -> Tuple[dict, dict, dict, dict]:
    sector_ids: Set[int] = set()
    subsector_ids: Set[int] = set()
    for indicator in indicators:
        if indicator.sector:
            for level in _SECTOR_LEVELS:
                sid = indicator.sector.get(level)
                if sid is not None:
                    sector_ids.add(int(sid))
        if indicator.sub_sector:
            for level in _SECTOR_LEVELS:
                ssid = indicator.sub_sector.get(level)
                if ssid is not None:
                    subsector_ids.add(int(ssid))

    sectors_by_id = {}
    if sector_ids:
        for sector in Sector.query.filter(Sector.id.in_(sector_ids)).all():
            sectors_by_id[sector.id] = sector

    subsectors_by_id = {}
    if subsector_ids:
        for subsector in SubSector.query.filter(SubSector.id.in_(subsector_ids)).all():
            subsectors_by_id[subsector.id] = subsector

    sector_names = {sid: s.name for sid, s in sectors_by_id.items()}
    subsector_names = {ssid: s.name for ssid, s in subsectors_by_id.items()}
    return sectors_by_id, subsectors_by_id, sector_names, subsector_names


def _sector_image_bytes(sector: Sector) -> Optional[List[int]]:
    """Load sector logo bytes from system storage (``uploads/system/sectors/``)."""
    if not sector.logo_filename:
        return None
    rel_path = f"sectors/{sector.logo_filename}"
    try:
        if storage.exists(storage.SYSTEM, rel_path):
            return list(storage.download(storage.SYSTEM, rel_path))
    except Exception as exc:
        current_app.logger.debug("Sector image load failed for sector %s: %s", sector.id, exc)
    return None


def _sector_subsector_names_for_level(
    indicator: IndicatorBank,
    level: str,
    subsectors_by_id: dict,
    sectors_by_id: dict,
    locale: str,
) -> Tuple[Optional[str], Optional[str]]:
    ssid = indicator.sub_sector.get(level) if indicator.sub_sector else None
    if ssid is None:
        return None, None
    subsector = subsectors_by_id.get(int(ssid))
    if not subsector:
        return None, None
    sub_name = (
        subsector.get_name_translation(locale)
        if hasattr(subsector, "get_name_translation")
        else subsector.name
    ) or subsector.name
    sector = sectors_by_id.get(subsector.sector_id)
    sector_name = None
    if sector:
        sector_name = (
            sector.get_name_translation(locale)
            if hasattr(sector, "get_name_translation")
            else sector.name
        ) or sector.name
    return sector_name, sub_name


def _build_legacy_excel_export(locale: str) -> bytes:
    """Build IFRC Indicator Bank public export workbook (legacy ``ExportModel`` layout)."""
    indicators = IndicatorBank.query.order_by(IndicatorBank.id.asc()).all()
    sectors_by_id, subsectors_by_id, _, _ = _load_sector_maps(indicators)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    ws.append(_EXCEL_HEADERS)

    for indicator in indicators:
        localized_type, localized_unit = _get_localized_type_unit(indicator, locale)
        questions = indicator.monitoring_questions_list
        q1 = questions[0] if len(questions) > 0 else None
        q2 = questions[1] if len(questions) > 1 else None
        q3 = questions[2] if len(questions) > 2 else None
        primary_sector, primary_subsector = _sector_subsector_names_for_level(
            indicator, "primary", subsectors_by_id, sectors_by_id, locale
        )
        secondary_sector, secondary_subsector = _sector_subsector_names_for_level(
            indicator, "secondary", subsectors_by_id, sectors_by_id, locale
        )
        tertiary_sector, tertiary_subsector = _sector_subsector_names_for_level(
            indicator, "tertiary", subsectors_by_id, sectors_by_id, locale
        )
        modified = indicator.updated_at or indicator.created_at
        ws.append(
            [
                indicator.id,
                _localized_text(indicator.name_translations, locale, indicator.name),
                _localized_text(indicator.definition_translations, locale, indicator.definition),
                localized_unit or indicator.unit or "",
                localized_type or indicator.type or "",
                indicator.comments or "",
                q1,
                q2,
                q3,
                _emergency_to_string(indicator.emergency),
                modified,
                "Archived" if indicator.archived else None,
                indicator.data_source or "",
                indicator.disaggregation_guidance or "",
                primary_sector,
                primary_subsector,
                secondary_sector,
                secondary_subsector,
                tertiary_sector,
                tertiary_subsector,
                "|".join(indicator.related_programs_list),
                "|".join(indicator.tags_list),
                indicator.area or "",
            ]
        )

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            if cell.value is not None and len(str(cell.value)) > max_length:
                max_length = len(str(cell.value))
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _subsector_model(
    subsector_id: Optional[int],
    subsectors_by_id: dict,
    locale: str,
) -> Optional[dict]:
    if subsector_id is None:
        return None
    subsector = subsectors_by_id.get(int(subsector_id))
    if not subsector:
        return None
    name = subsector.get_name_translation(locale) if hasattr(subsector, "get_name_translation") else subsector.name
    return {
        "parentSectorId": subsector.sector_id,
        "id": subsector.id,
        "subsectorId": subsector.id,
        "name": name or subsector.name or "",
        "order": subsector.display_order or 0,
    }


def _sector_model(sector: Sector, subsectors: List[SubSector], locale: str, include_image: bool) -> dict:
    localized_name = sector.get_name_translation(locale) if hasattr(sector, "get_name_translation") else sector.name
    image = _sector_image_bytes(sector) if include_image else None
    return {
        "id": sector.id,
        "sectorId": sector.id,
        "name": localized_name or sector.name or "",
        "order": sector.display_order or 0,
        "image": image,
        "subsectors": [
            {
                "parentSectorId": sub.sector_id,
                "id": sub.id,
                "subsectorId": sub.id,
                "name": (sub.get_name_translation(locale) if hasattr(sub, "get_name_translation") else sub.name)
                or sub.name
                or "",
                "order": sub.display_order or 0,
            }
            for sub in sorted(subsectors, key=lambda s: (s.display_order or 0, s.name or ""))
            if sub.is_active
        ],
    }


def _indicator_list_item(
    indicator: IndicatorBank,
    locale: str,
    subsectors_by_id: dict,
    subsector_names: dict,
) -> dict:
    primary = _subsector_model(
        indicator.sub_sector.get("primary") if indicator.sub_sector else None,
        subsectors_by_id,
        locale,
    )
    secondary = _subsector_model(
        indicator.sub_sector.get("secondary") if indicator.sub_sector else None,
        subsectors_by_id,
        locale,
    )
    tertiary = _subsector_model(
        indicator.sub_sector.get("tertiary") if indicator.sub_sector else None,
        subsectors_by_id,
        locale,
    )
    return {
        "id": indicator.id,
        "indicatorId": indicator.id,
        "title": _localized_text(indicator.name_translations, locale, indicator.name),
        "definition": _localized_text(indicator.definition_translations, locale, indicator.definition),
        "primarySubsector": primary,
        "secondarySubsector": secondary,
        "tertiarySubsector": tertiary,
        "isArchived": bool(indicator.archived),
    }


def _indicator_detail(
    indicator: IndicatorBank,
    locale: str,
    sectors_by_id: dict,
    subsectors_by_id: dict,
    sector_names: dict,
    subsector_names: dict,
) -> dict:
    sector_sub = _build_sector_subsector_names(indicator, sector_names, subsector_names)
    localized_type, localized_unit = _get_localized_type_unit(indicator, locale)

    def _sector_for_level(level: str) -> Optional[dict]:
        sid = indicator.sector.get(level) if indicator.sector else None
        if sid is None:
            return None
        sector = sectors_by_id.get(int(sid))
        if not sector:
            return None
        return {
            "id": sector.id,
            "sectorId": sector.id,
            "name": sector.get_name_translation(locale) if hasattr(sector, "get_name_translation") else sector.name,
            "order": sector.display_order or 0,
            "image": None,
            "subsectors": [],
        }

    return {
        "id": indicator.id,
        "indicatorId": indicator.id,
        "title": _localized_text(indicator.name_translations, locale, indicator.name),
        "definition": _localized_text(indicator.definition_translations, locale, indicator.definition),
        "unitOfMeasurement": localized_unit or indicator.unit or "",
        "typeOfMeasurement": localized_type or indicator.type or "",
        "comments": indicator.comments or "",
        "emergency": _emergency_to_string(indicator.emergency),
        "disaggregation": indicator.disaggregation_guidance or "",
        "indicatorSource": indicator.data_source or "",
        "spef": indicator.area or "",
        "relatedPrograms": [{"text": p} for p in indicator.related_programs_list],
        "monitoringQuestions": [{"text": q} for q in indicator.monitoring_questions_list],
        "tags": [{"text": t} for t in indicator.tags_list],
        "primarySector": _sector_for_level("primary"),
        "primarySubsector": _subsector_model(
            indicator.sub_sector.get("primary") if indicator.sub_sector else None,
            subsectors_by_id,
            locale,
        ),
        "secondarySector": _sector_for_level("secondary"),
        "secondarySubsector": _subsector_model(
            indicator.sub_sector.get("secondary") if indicator.sub_sector else None,
            subsectors_by_id,
            locale,
        ),
        "tertiarySector": _sector_for_level("tertiary"),
        "tertiarySubsector": _subsector_model(
            indicator.sub_sector.get("tertiary") if indicator.sub_sector else None,
            subsectors_by_id,
            locale,
        ),
        "created": indicator.created_at.isoformat() if indicator.created_at else utcnow().isoformat(),
        "createdBy": "",
        "modified": indicator.updated_at.isoformat() if indicator.updated_at else utcnow().isoformat(),
        "modifiedBy": "",
        "isArchived": bool(indicator.archived),
        "userRatings": [],
    }


def _apply_indicator_filters(query):
    locale = _compat_locale()
    filter_text = (request.args.get("Filter") or request.args.get("filter") or "").strip()
    sector_ids = request.args.getlist("SectorIds") or request.args.getlist("sectorIds")
    subsector_ids = request.args.getlist("SubsectorIds") or request.args.getlist("subsectorIds")
    indicator_ids = request.args.getlist("IndicatorIds") or request.args.getlist("indicatorIds")
    tags = request.args.getlist("Tags") or request.args.getlist("tags")
    show_archived = request.args.get("ShowIsArchived") or request.args.get("showIsArchived")

    if show_archived is not None:
        if str(show_archived).lower() in ("true", "1"):
            query = query.filter(IndicatorBank.archived.is_(True))
        elif str(show_archived).lower() in ("false", "0"):
            query = query.filter(IndicatorBank.archived.is_(False))
    else:
        query = query.filter(IndicatorBank.archived.is_(False))

    if indicator_ids:
        ids = [int(x) for x in indicator_ids if str(x).isdigit()]
        if ids:
            query = query.filter(IndicatorBank.id.in_(ids))

    if filter_text:
        pattern = safe_ilike_pattern(filter_text)
        query = query.filter(
            db.or_(
                IndicatorBank.name.ilike(pattern),
                IndicatorBank.definition.ilike(pattern),
            )
        )

    if sector_ids:
        int_sector_ids = [str(int(x)) for x in sector_ids if str(x).isdigit()]
        if int_sector_ids:
            sector_filters = []
            for sid in int_sector_ids:
                for level in _SECTOR_LEVELS:
                    sector_filters.append(IndicatorBank.sector[level].astext == sid)
            query = query.filter(db.or_(*sector_filters))

    if subsector_ids:
        int_subsector_ids = [str(int(x)) for x in subsector_ids if str(x).isdigit()]
        if int_subsector_ids:
            subsector_filters = []
            for ssid in int_subsector_ids:
                for level in _SECTOR_LEVELS:
                    subsector_filters.append(IndicatorBank.sub_sector[level].astext == ssid)
            query = query.filter(db.or_(*subsector_filters))

    if tags:
        for tag in tags:
            tag = (tag or "").strip()
            if tag:
                query = query.filter(IndicatorBank.tags.contains([tag]))

    return query.order_by(IndicatorBank.name.asc()), locale


def _count_indicators_for_sector(sector_id: int) -> int:
    sid = str(sector_id)
    subsector_ids = [
        str(row[0])
        for row in SubSector.query.filter_by(sector_id=sector_id, is_active=True).with_entities(SubSector.id).all()
    ]
    filters = [
        IndicatorBank.sector["primary"].astext == sid,
        IndicatorBank.sector["secondary"].astext == sid,
        IndicatorBank.sector["tertiary"].astext == sid,
    ]
    for ssid in subsector_ids:
        filters.extend(
            [
                IndicatorBank.sub_sector["primary"].astext == ssid,
                IndicatorBank.sub_sector["secondary"].astext == ssid,
                IndicatorBank.sub_sector["tertiary"].astext == ssid,
            ]
        )
    return (
        IndicatorBank.query.filter(IndicatorBank.archived.is_(False), db.or_(*filters)).count()
        if filters
        else 0
    )


def _select_option(text: str) -> dict:
    value = (text or "").strip()
    return {"text": value, "value": value}


@indicator_bank_compat_bp.route("/Indicator", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def indicator_list():
    query, locale = _apply_indicator_filters(IndicatorBank.query)
    offset = request.args.get("Offset", type=int) or request.args.get("offset", type=int) or 0
    limit = request.args.get("Limit", type=int) or request.args.get("limit", type=int) or 1000
    total = query.count()
    rows = query.offset(max(offset, 0)).limit(max(limit, 1)).all()
    _, subsectors_by_id, _, subsector_names = _load_sector_maps(rows)
    values = [_indicator_list_item(row, locale, subsectors_by_id, subsector_names) for row in rows]
    return jsonify(
        {
            "values": values,
            "count": total,
            "page": {"offset": offset, "limit": limit},
        }
    )


@indicator_bank_compat_bp.route("/Indicator/<int:indicator_id>", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def indicator_detail(indicator_id: int):
    indicator = db.session.get(IndicatorBank, indicator_id)
    if not indicator:
        return api_error("Indicator not found", 404)
    locale = _compat_locale()
    sectors_by_id, subsectors_by_id, sector_names, subsector_names = _load_sector_maps([indicator])
    return jsonify(
        _indicator_detail(indicator, locale, sectors_by_id, subsectors_by_id, sector_names, subsector_names)
    )


@indicator_bank_compat_bp.route("/Indicator/search", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def indicator_search():
    query_text = (request.args.get("filter") or request.args.get("Filter") or "").strip()
    locale = _compat_locale()
    if not query_text:
        return jsonify([])

    svc = IndicatorResolutionService()
    if svc.has_embeddings():
        results = svc.resolve(query_text, top_k=20, exclude_archived=True)
        payload = []
        for indicator, score in results:
            payload.append(
                {
                    "id": indicator.id,
                    "indicatorId": indicator.id,
                    "title": _localized_text(indicator.name_translations, locale, indicator.name),
                    "definition": _localized_text(indicator.definition_translations, locale, indicator.definition),
                    "score": round(float(score), 4),
                    "isArchived": bool(indicator.archived),
                }
            )
        return jsonify(payload)

    pattern = safe_ilike_pattern(query_text)
    indicators = (
        IndicatorBank.query.filter(
            IndicatorBank.archived.is_(False),
            db.or_(IndicatorBank.name.ilike(pattern), IndicatorBank.definition.ilike(pattern)),
        )
        .order_by(IndicatorBank.name.asc())
        .limit(20)
        .all()
    )
    return jsonify(
        [
            {
                "id": ind.id,
                "indicatorId": ind.id,
                "title": _localized_text(ind.name_translations, locale, ind.name),
                "definition": _localized_text(ind.definition_translations, locale, ind.definition),
                "score": 1.0,
                "isArchived": False,
            }
            for ind in indicators
        ]
    )


@indicator_bank_compat_bp.route("/Indicator/tags", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def indicator_tags():
    tags: Set[str] = set()
    for indicator in IndicatorBank.query.filter(IndicatorBank.archived.is_(False)).all():
        for tag in indicator.tags_list:
            tags.add(tag)
    return jsonify(sorted(tags))


@indicator_bank_compat_bp.route("/Indicator/selectOptions", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def indicator_select_options():
    locale = _compat_locale()
    indicators = IndicatorBank.query.filter(IndicatorBank.archived.is_(False)).all()

    units = set()
    types = set()
    disaggregations = set()
    tag_items: Set[str] = set()
    monitoring_items: Set[str] = set()
    program_items: Set[str] = set()

    for indicator in indicators:
        if indicator.unit:
            units.add(indicator.unit.strip())
        if indicator.type:
            types.add(indicator.type.strip())
        if indicator.disaggregation_guidance:
            disaggregations.add(indicator.disaggregation_guidance.strip())
        tag_items.update(indicator.tags_list)
        monitoring_items.update(indicator.monitoring_questions_list)
        program_items.update(indicator.related_programs_list)

    active_types = IndicatorBankType.query.filter_by(is_active=True).order_by(IndicatorBankType.sort_order).all()
    active_units = IndicatorBankUnit.query.filter_by(is_active=True).order_by(IndicatorBankUnit.sort_order).all()
    if active_types:
        types = {t.get_name_translation(locale) if hasattr(t, "get_name_translation") else t.name for t in active_types}
    if active_units:
        units = {u.get_name_translation(locale) if hasattr(u, "get_name_translation") else u.name for u in active_units}

    return jsonify(
        {
            "unitOfMeasurements": [_select_option(x) for x in sorted(units) if x],
            "typeOfMeasurements": [_select_option(x) for x in sorted(types) if x],
            "disaggregations": [_select_option(x) for x in sorted(disaggregations) if x],
            "emergencies": [
                _select_option("Yes"),
                _select_option(""),
            ],
            "spef": [],
            "tags": [_select_option(x) for x in sorted(tag_items)],
            "monitoringQuestions": [_select_option(x) for x in sorted(monitoring_items)],
            "relatedPrograms": [_select_option(x) for x in sorted(program_items)],
        }
    )


@indicator_bank_compat_bp.route("/Indicator/Suggestion", methods=["POST"])
@_require_compat_api_key
@api_rate_limit()
def indicator_suggestion():
    data = get_json_safe() or {}
    token = (data.get("token") or "").strip()
    if not _verify_recaptcha(token):
        return api_error("reCAPTCHA validation failed", 400)

    operation = data.get("operation")
    if isinstance(operation, int):
        operation_map = {0: "new_indicator", 1: "correction", 2: "other"}
        suggestion_type = operation_map.get(operation, "other")
    else:
        op_name = str(operation or "").lower()
        if op_name in ("new", "0"):
            suggestion_type = "new_indicator"
        elif op_name in ("edit", "1"):
            suggestion_type = "correction"
        else:
            suggestion_type = "other"

    indicator_id = data.get("indicatorId") or data.get("indicator_id")
    indicator_name = (data.get("title") or data.get("indicator_name") or data.get("subject") or "Suggestion").strip()
    reason = (data.get("motivation") or data.get("reason") or "").strip()
    submitter_name = (data.get("name") or data.get("submitter_name") or "").strip()
    submitter_email = (data.get("email") or data.get("submitter_email") or "").strip()

    if not submitter_name or not submitter_email or not reason:
        return api_error("Missing required suggestion fields", 400)

    sector_data = None
    if data.get("primarySector") or data.get("secondarySector") or data.get("tertiarySector"):
        sector_data = {
            "primary": (data.get("primarySector") or "").strip() or None,
            "secondary": (data.get("secondarySector") or "").strip() or None,
            "tertiary": (data.get("tertiarySector") or "").strip() or None,
        }
    subsector_data = None
    if data.get("primarySubsector") or data.get("secondarySubsector") or data.get("tertiarySubsector"):
        subsector_data = {
            "primary": (data.get("primarySubsector") or "").strip() or None,
            "secondary": (data.get("secondarySubsector") or "").strip() or None,
            "tertiary": (data.get("tertiarySubsector") or "").strip() or None,
        }

    related = data.get("relatedProgrames") or data.get("relatedPrograms") or []
    if isinstance(related, list):
        related_text = ", ".join(str(x).strip() for x in related if str(x).strip())
    else:
        related_text = str(related).strip()

    notes_parts = [
        f"Subject: {(data.get('subject') or '').strip()}",
        f"Link: {(data.get('link') or '').strip()}",
        f"Comments: {(data.get('comments') or '').strip()}",
        f"Tags: {', '.join(data.get('tags') or [])}",
        f"Monitoring questions: {', '.join(data.get('monitoringQuestions') or [])}",
    ]
    additional_notes = "\n".join(part for part in notes_parts if part.split(":", 1)[-1].strip())

    suggestion = IndicatorSuggestion(
        submitter_name=submitter_name,
        submitter_email=submitter_email,
        suggestion_type=suggestion_type,
        indicator_id=int(indicator_id) if indicator_id else None,
        indicator_name=indicator_name,
        definition=data.get("definition"),
        type=data.get("typeOfMeasurement") or data.get("type"),
        unit=data.get("unitOfMeasurement") or data.get("unit"),
        sector=sector_data,
        sub_sector=subsector_data,
        emergency=_emergency_to_string(data.get("emergency")).lower() in ("yes", "true", "1"),
        related_programs=related_text or None,
        reason=reason,
        additional_notes=additional_notes or None,
        status="Pending",
        submitted_at=utcnow(),
    )
    db.session.add(suggestion)
    db.session.commit()
    return ("", 200)


@indicator_bank_compat_bp.route("/Sector", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def sector_list():
    locale = _compat_locale()
    include_images = request.args.get("includeImages", default=False, type=lambda v: str(v).lower() in ("1", "true", "yes"))
    sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()
    subsectors = SubSector.query.filter_by(is_active=True).order_by(SubSector.display_order, SubSector.name).all()
    by_sector: Dict[int, List[SubSector]] = {}
    for sub in subsectors:
        by_sector.setdefault(sub.sector_id, []).append(sub)
    payload = [_sector_model(sector, by_sector.get(sector.id, []), locale, include_images) for sector in sectors]
    return jsonify(payload)


@indicator_bank_compat_bp.route("/Subsector", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def subsector_list():
    locale = _compat_locale()
    subsectors = SubSector.query.filter_by(is_active=True).order_by(SubSector.display_order, SubSector.name).all()
    payload = []
    for sub in subsectors:
        name = sub.get_name_translation(locale) if hasattr(sub, "get_name_translation") else sub.name
        payload.append(
            {
                "parentSectorId": sub.sector_id,
                "id": sub.id,
                "subsectorId": sub.id,
                "name": name or sub.name or "",
                "order": sub.display_order or 0,
            }
        )
    return jsonify(payload)


@indicator_bank_compat_bp.route("/list-home", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def list_home():
    locale = _compat_locale()
    sectors = Sector.query.filter_by(is_active=True).order_by(Sector.display_order, Sector.name).all()
    payload = []
    for sector in sectors:
        payload.append(
            {
                "id": sector.id,
                "sectorId": sector.id,
                "sectorName": sector.get_name_translation(locale) if hasattr(sector, "get_name_translation") else sector.name,
                "indicatorsCount": _count_indicators_for_sector(sector.id),
                "order": sector.display_order or 0,
                "image": _sector_image_bytes(sector),
            }
        )
    return jsonify(payload)


@indicator_bank_compat_bp.route("/Excel", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def export_excel():
    locale = _compat_locale()
    try:
        excel_bytes = _build_legacy_excel_export(locale)
    except Exception as exc:
        current_app.logger.error("Indicator Bank compat Excel export failed: %s", exc, exc_info=True)
        return api_error("Excel export failed", 500)

    response = make_response(excel_bytes)
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response.headers["Content-Disposition"] = 'attachment; filename="indicatorbank.xlsx"'
    return response


@indicator_bank_compat_bp.route("/CommonWord", methods=["GET"])
@_require_compat_api_key
@api_rate_limit()
def common_word_list():
    locale = _compat_locale()
    words = CommonWord.query.filter_by(is_active=True).order_by(CommonWord.term.asc()).all()
    payload = []
    for word in words:
        meaning = word.get_meaning_translation(locale) if hasattr(word, "get_meaning_translation") else word.meaning
        payload.append(
            {
                "term": word.term,
                "meaning": meaning or word.meaning or "",
                "hasMatch": False,
                "occurences": 0,
            }
        )
    return jsonify(payload)
