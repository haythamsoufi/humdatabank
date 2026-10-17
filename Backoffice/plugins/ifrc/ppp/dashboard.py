"""Aggregate approved PPP submissions for the public embed dashboards.

Each National Society can submit the same form more than once, with its own
reporting window. The dashboard keeps the latest approved window per society
and per form, then adds those figures across societies. Pillar totals are
people reached by that result; the headline is the unique total from the
overview form, so a person counted in two pillars is not counted twice there.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from plugins.ifrc.ppp.catalogue import (
    HIGHLIGHTS,
    KOBO_MARKER,
    PILLARS,
    TEMPLATE_KEYS,
    display_label,
    highlight_for_item,
    is_activity_field,
    is_overview_reach,
    is_pillar_reach,
    is_public_indicator,
    narrative_kobo_name,
)

_NARRATIVE_LIMIT = 2000
_CENTROIDS_PATH = Path(__file__).resolve().parents[2] / "upr" / "geo" / "country_centroids.json"


def choose_latest(rows: list[dict]) -> list[dict]:
    """Keep the newest approved row for each template and country."""
    best: dict[tuple, dict] = {}
    for row in rows:
        if row.get("status") != "approved":
            continue
        key = (row.get("template_key"), row.get("country_id"))
        if not key[0] or key[1] is None:
            continue
        current = best.get(key)
        if current is None or _is_newer(row, current):
            best[key] = row
    return list(best.values())


def _is_newer(candidate: dict, current: dict) -> bool:
    candidate_end = candidate.get("period_end") or date.min
    current_end = current.get("period_end") or date.min
    if candidate_end != current_end:
        return candidate_end > current_end
    return int(candidate.get("aes_id") or 0) > int(current.get("aes_id") or 0)


def assemble_dashboard(rows: list[dict]) -> dict:
    """Turn the latest per-country rows into the JSON the embed pages render."""
    latest = choose_latest(rows)
    countries: dict[int, dict] = {}
    for row in latest:
        country = countries.setdefault(
            int(row["country_id"]),
            {
                "id": int(row["country_id"]),
                "name": row.get("name") or "",
                "iso2": (row.get("iso2") or "").upper(),
                "iso3": (row.get("iso3") or "").upper(),
                "region": row.get("region") or "",
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "reached": 0,
                "pillars": {},
                "highlights": {},
                "indicators": {},
                "activities": {},
            },
        )
        _apply_row(country, row)

    country_list = [item for item in countries.values() if _country_has_figures(item)]
    country_list.sort(key=lambda item: (item.get("name") or "").lower())
    regions = sorted({item["region"] for item in country_list if item.get("region")})
    return {
        "countries": country_list,
        "regions": regions,
        "pillars": [
            {"id": pillar["id"], "title": pillar["title"], "icon": pillar["icon"]}
            for pillar in PILLARS
        ],
        "highlights": [
            {"id": item["id"], "title": item["title"], "icon": item["icon"]}
            for item in HIGHLIGHTS
        ],
        "indicator_catalogue": _indicator_catalogue(latest),
        "activity_catalogue": _activity_catalogue(latest),
    }


def _country_has_figures(country: dict) -> bool:
    if country.get("reached"):
        return True
    if any(country.get("pillars", {}).values()):
        return True
    if any(country.get("highlights", {}).values()):
        return True
    return bool(country.get("activities"))


def _apply_row(country: dict, row: dict) -> None:
    template_key = row.get("template_key")
    for field in row.get("fields") or []:
        kobo_name = field.get("kobo_name") or ""
        label = field.get("label") or ""
        if template_key == "overview" and is_overview_reach(kobo_name, label):
            number = _number(field)
            if number is not None:
                country["reached"] = number
            continue
        if is_pillar_reach(template_key, kobo_name, label):
            number = _number(field)
            if number is not None:
                country["pillars"][template_key] = number
            continue
        highlight = highlight_for_item(kobo_name, label)
        if highlight:
            number = _number(field)
            if number is not None:
                country["highlights"][highlight["id"]] = number
            continue
        if is_activity_field(kobo_name):
            activity = country["activities"].setdefault(
                kobo_name,
                {"applicable": False, "narrative": ""},
            )
            if _is_applicable(field.get("text")):
                activity["applicable"] = True
            continue
        if kobo_name.endswith("_nar"):
            activity_name = kobo_name[: -len("_nar")]
            if is_activity_field(activity_name):
                activity = country["activities"].setdefault(
                    activity_name,
                    {"applicable": False, "narrative": ""},
                )
                text = (field.get("text") or "").strip()
                if text:
                    activity["narrative"] = text[:_NARRATIVE_LIMIT]
            continue
        if is_public_indicator(kobo_name, label, field.get("item_type") or "", field.get("question_type") or ""):
            if (field.get("question_type") or "") == "yesno":
                if str(field.get("text") or "").strip().lower() == "yes":
                    country["indicators"][kobo_name] = 1
            else:
                number = _number(field)
                if number is not None:
                    country["indicators"][kobo_name] = number


def _indicator_catalogue(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        pillar = row.get("template_key")
        if pillar == "overview":
            continue
        for field in row.get("fields") or []:
            kobo_name = field.get("kobo_name") or ""
            if kobo_name in seen:
                continue
            if not is_public_indicator(
                kobo_name,
                field.get("label") or "",
                field.get("item_type") or "",
                field.get("question_type") or "",
            ):
                continue
            seen[kobo_name] = {
                "id": kobo_name,
                "pillar": pillar,
                "title": display_label(field.get("label") or kobo_name),
                "kind": "yesno" if field.get("question_type") == "yesno" else "number",
                "order": field.get("order") or 0,
            }
    return _sorted_catalogue(seen)


def _activity_catalogue(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        pillar = row.get("template_key")
        if pillar == "overview":
            continue
        for field in row.get("fields") or []:
            kobo_name = field.get("kobo_name") or ""
            if not is_activity_field(kobo_name) or kobo_name in seen:
                continue
            seen[kobo_name] = {
                "id": kobo_name,
                "pillar": pillar,
                "title": display_label(field.get("label") or kobo_name),
                "narrative_kobo": narrative_kobo_name(kobo_name),
                "order": field.get("order") or 0,
            }
    return _sorted_catalogue(seen)


def _sorted_catalogue(seen: dict[str, dict]) -> list[dict]:
    pillar_order = {pillar["id"]: index for index, pillar in enumerate(PILLARS)}
    return sorted(
        seen.values(),
        key=lambda item: (pillar_order.get(item.get("pillar"), 99), float(item.get("order") or 0), item.get("title") or ""),
    )


def _number(field: dict):
    if field.get("not_applicable"):
        return None
    value = field.get("number")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_applicable(value) -> bool:
    return str(value or "").strip().lower() == "applicable"


def _centroids() -> dict[str, tuple[float, float]]:
    try:
        raw = json.loads(_CENTROIDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    points = {}
    if not isinstance(raw, dict):
        return points
    for iso2, pair in raw.items():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            try:
                points[str(iso2).upper()] = (float(pair[0]), float(pair[1]))
            except (TypeError, ValueError):
                continue
    return points


def _entry_number(entry) -> float | None:
    if getattr(entry, "not_applicable", False) or getattr(entry, "data_not_available", False):
        return None
    number = getattr(entry, "numeric_value", None)
    if number is not None:
        try:
            return float(number)
        except (TypeError, ValueError):
            return None
    text = str(getattr(entry, "value", "") or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _entry_text(entry) -> str:
    if getattr(entry, "not_applicable", False):
        return ""
    return str(getattr(entry, "value", "") or "").strip()


def load_ppp_dashboard() -> dict:
    """Read the live database and return the embed payload."""
    from app.models import AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem, FormTemplateVersion

    versions = FormTemplateVersion.query.filter(
        FormTemplateVersion.description.contains(KOBO_MARKER)
    ).all()
    template_keys = {}
    for version in versions:
        description = version.description or ""
        for uid, key in TEMPLATE_KEYS.items():
            if uid in description:
                template_keys[version.template_id] = key
    if not template_keys:
        return assemble_dashboard([])

    template_ids = list(template_keys)
    items = FormItem.query.filter(FormItem.template_id.in_(template_ids), FormItem.archived.is_(False)).all()
    item_by_id = {}
    for item in items:
        kobo_name = str((item.config or {}).get("kobo_name") or "")
        if not kobo_name:
            continue
        item_by_id[item.id] = {
            "kobo_name": kobo_name,
            "label": item.label or "",
            "item_type": item.item_type or "",
            "question_type": item.type or "",
            "template_key": template_keys.get(item.template_id),
            "order": item.order or 0,
        }

    assignments = (
        AssignmentEntityStatus.query.join(AssignedForm)
        .filter(
            AssignedForm.template_id.in_(template_ids),
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.status == "approved",
        )
        .all()
    )
    if not assignments:
        return assemble_dashboard([])

    country_ids = {row.entity_id for row in assignments}
    countries = {
        country.id: country
        for country in Country.query.filter(Country.id.in_(country_ids)).all()
    }
    points = _centroids()
    aes_meta = {}
    for row in assignments:
        country = countries.get(row.entity_id)
        if country is None:
            continue
        iso2 = (country.iso2 or "").upper()
        point = points.get(iso2)
        period_end = None
        assigned = row.assigned_form
        if assigned is not None:
            period_end = assigned.period_end
        aes_meta[row.id] = {
            "aes_id": row.id,
            "status": "approved",
            "template_key": template_keys.get(assigned.template_id if assigned else None),
            "country_id": country.id,
            "name": country.name,
            "iso2": iso2,
            "iso3": (country.iso3 or "").upper(),
            "region": country.region or "",
            "lat": point[0] if point else None,
            "lng": point[1] if point else None,
            "period_end": period_end,
            "fields": [],
        }

    chosen_ids = [row["aes_id"] for row in choose_latest(list(aes_meta.values()))]
    if not chosen_ids:
        return assemble_dashboard([])
    data_rows = FormData.query.filter(
        FormData.assignment_entity_status_id.in_(chosen_ids),
        FormData.form_item_id.in_(list(item_by_id)),
    ).all()
    for entry in data_rows:
        meta = aes_meta.get(entry.assignment_entity_status_id)
        spec = item_by_id.get(entry.form_item_id)
        if meta is None or spec is None:
            continue
        meta["fields"].append({
            **spec,
            "number": _entry_number(entry),
            "text": _entry_text(entry),
            "not_applicable": bool(entry.not_applicable),
        })
    payload = assemble_dashboard([aes_meta[aes_id] for aes_id in chosen_ids if aes_id in aes_meta])
    indicators, activities = catalogues_from_items(list(item_by_id.values()))
    if indicators:
        payload["indicator_catalogue"] = indicators
    if activities:
        payload["activity_catalogue"] = activities
    return payload


def catalogues_from_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Activity and indicator labels from the form, including questions nobody answered."""
    indicators = _indicator_catalogue([
        {"template_key": item.get("template_key"), "status": "approved", "country_id": 0, "fields": [item]}
        for item in items
    ])
    activities = _activity_catalogue([
        {"template_key": item.get("template_key"), "status": "approved", "country_id": 0, "fields": [item]}
        for item in items
    ])
    return indicators, activities
