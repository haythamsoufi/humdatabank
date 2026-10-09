"""Bundle-wide UPR visuals: one report that adds up every country in a text category."""

from __future__ import annotations

import re
from typing import Any

from flask_login import current_user

from app.models.assignments import AssignmentEntityStatus
from app.models.organization import NationalSociety
from app.services.organization.authorization_service import AuthorizationService
from app.utils.country_utils import (
    PART_OF_CATEGORY_TEXT,
    load_part_of_category_catalog,
)
from plugins.upr.catalog import dashboards_for_kind
from plugins.upr.data import _dashboard_title, build_payload
from plugins.upr.errors import UprError
from plugins.upr.formatters import format_compact_chf, format_count, format_percent, format_thousands
from plugins.upr.i18n import t
from plugins.upr.support import support_total_from_rows

BUNDLE_CATEGORY_KEY = "bundle"


def bundle_category_name() -> str:
    """Catalog name of the text category that groups countries into bundles."""
    catalog = load_part_of_category_catalog()
    for name, kind in catalog.items():
        if kind == PART_OF_CATEGORY_TEXT and name.strip().lower() == BUNDLE_CATEGORY_KEY:
            return name
    return "Bundle"


def bundle_options_for_aes(aes: AssignmentEntityStatus) -> list[dict[str, Any]]:
    """Bundles this assignment's country belongs to, when another country on the same assignment shares it."""
    country = aes.country
    if country is None:
        return []
    category = bundle_category_name()
    value = _bundle_value_for_country(country.id, category)
    if not value:
        return []
    members = _member_statuses(aes, category, value)
    if len(members) < 2:
        return []
    names = []
    for member in members:
        member_country = member.country
        label = (getattr(member_country, "name", None) or "").strip()
        if label:
            names.append(label)
    return [
        {
            "value": value,
            "category": category,
            "country_count": len(names),
            "countries": names,
        }
    ]


def build_bundle_payload(aes_id: int, bundle_value: str, *, inline_icons: bool = False) -> dict[str, Any]:
    """Visual payload for every accessible country in this bundle on the same assignment."""
    from plugins.upr.loaders import _load_aes

    label = (bundle_value or "").strip()
    if not label:
        raise UprError("Choose a bundle.")
    aes = _load_aes(aes_id)
    category = bundle_category_name()
    own = _bundle_value_for_country(aes.country.id, category) if aes.country else ""
    if own.casefold() != label.casefold():
        raise UprError("This assignment is not part of that bundle.")
    members = _member_statuses(aes, category, own)
    if len(members) < 2:
        raise UprError("This bundle has no other countries on this assignment.")
    payloads = [build_payload(member.id, inline_icons=inline_icons) for member in members]
    names = [
        str((payload.get("meta") or {}).get("country_name") or "").strip()
        for payload in payloads
    ]
    return merge_upr_payloads(payloads, bundle_name=own, country_names=[name for name in names if name])


def merge_upr_payloads(
    payloads: list[dict[str, Any]],
    *,
    bundle_name: str,
    country_names: list[str],
) -> dict[str, Any]:
    """Add country visuals into one bundle visual. The first payload supplies labels and kind."""
    if not payloads:
        raise UprError("This bundle has no assignment data.")
    base = payloads[0]
    meta = dict(base.get("meta") or {})
    kind = str(meta.get("kind") or "report")
    merged: dict[str, Any] = {
        "meta": meta,
        "kpis": _merge_kpis(payloads),
        "people_reached": _merge_people(payloads),
        "financial": _merge_financial(payloads),
        "support": _merge_support(payloads),
        "core_indicators": _merge_indicators(payloads, "core_indicators"),
        "enabling_indicators": _merge_indicators(payloads, "enabling_indicators"),
        "emergencies": _merge_emergencies(payloads),
        "dashboards": [],
    }
    merged["support_total"] = support_total_from_rows(merged["support"])
    slots = {int(em.get("slot") or 0) for em in merged["emergencies"]}
    merged["dashboards"] = [
        {
            "id": spec.id,
            "title": t(_dashboard_title(spec, kind)),
            "description": spec.description,
            "width": spec.width,
            "height": spec.height,
        }
        for spec in dashboards_for_kind(kind, emergency_slots=slots)
    ]
    _retitle(merged, bundle_name=bundle_name, country_names=country_names)
    return merged


def _bundle_file_token(name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", name or "").upper()[:16]
    return token or "BUNDLE"


def _bundle_value_for_country(country_id: int, category: str) -> str:
    societies = NationalSociety.query.filter(NationalSociety.country_id == country_id).all()
    for ns in societies:
        texts = ns.category_text if isinstance(ns.category_text, dict) else {}
        value = str(texts.get(category) or "").strip()
        if value:
            return value
    return ""


def _member_statuses(aes: AssignmentEntityStatus, category: str, value: str) -> list[AssignmentEntityStatus]:
    societies = NationalSociety.query.filter(NationalSociety.category_text.isnot(None)).all()
    country_ids = set()
    wanted = value.casefold()
    for ns in societies:
        texts = ns.category_text if isinstance(ns.category_text, dict) else {}
        stored = str(texts.get(category) or "").strip()
        if stored.casefold() == wanted and ns.country_id:
            country_ids.add(int(ns.country_id))
    if not country_ids:
        return []
    rows = (
        AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.assigned_form_id == aes.assigned_form_id,
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.entity_id.in_(country_ids),
        )
        .all()
    )
    visible = [
        row
        for row in rows
        if AuthorizationService.can_access_assignment(row, current_user)
    ]
    visible.sort(key=lambda row: (0 if row.id == aes.id else 1, (getattr(row.country, "name", None) or "").lower()))
    return visible


def _retitle(payload: dict[str, Any], *, bundle_name: str, country_names: list[str]) -> None:
    meta = payload["meta"]
    assignment_title = ""
    document_title = str(meta.get("document_title") or "")
    if "—" in document_title:
        assignment_title = document_title.split("—", 1)[1].strip()
    elif " - " in document_title:
        assignment_title = document_title.split(" - ", 1)[1].strip()
    title = " — ".join(part for part in (bundle_name, assignment_title) if part) or bundle_name
    subtitle = str(meta.get("document_subtitle") or "").strip()
    count_label = f"{len(country_names)} countries" if country_names else ""
    if count_label:
        subtitle = f"{subtitle} · {count_label}" if subtitle else count_label
    meta.update(
        {
            "country_name": bundle_name,
            "country_name_en": bundle_name,
            "national_society": bundle_name,
            "iso3": _bundle_file_token(bundle_name),
            "iso2": "",
            "ns_logo_src": "",
            "appeal_code": "",
            "document_title": title,
            "document_title_en": title,
            "document_subtitle": subtitle,
            "bundle": True,
            "bundle_name": bundle_name,
            "bundle_countries": country_names,
        }
    )


def _merge_kpis(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        for key, rec in (payload.get("kpis") or {}).items():
            if key not in merged:
                slot = dict(rec)
                slot["value"] = float(rec.get("value") or 0)
                merged[key] = slot
                continue
            merged[key]["value"] = float(merged[key].get("value") or 0) + float(rec.get("value") or 0)
    for rec in merged.values():
        number = float(rec.get("value") or 0)
        rec["value"] = number or None
        rec["display"] = format_count(number) if number else rec.get("display") or ""
    return merged


def _merge_people(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in payload.get("people_reached") or []:
            code = str(row.get("code") or row.get("label") or "")
            if not code:
                continue
            if code not in buckets:
                buckets[code] = dict(row)
                buckets[code]["value"] = 0.0
                order.append(code)
            buckets[code]["value"] = float(buckets[code].get("value") or 0) + float(row.get("value") or 0)
    rows = []
    for code in order:
        row = buckets[code]
        number = float(row.get("value") or 0)
        row["value"] = number
        row["display"] = format_thousands(number) if number else ""
        row["has_value"] = bool(number)
        rows.append(row)
    return rows


def _merge_indicators(payloads: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    order: list[tuple[str, str]] = []
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for payload in payloads:
        for row in payload.get(field) or []:
            key = (str(row.get("code") or ""), str(row.get("label") or ""))
            kind = str(row.get("kind") or "number")
            slot = buckets.get(key)
            if slot is None:
                slot = dict(row)
                slot["value"] = 0.0
                slot["_samples"] = []
                slot["_yes"] = 0
                slot["_answers"] = 0
                buckets[key] = slot
                order.append(key)
            if kind == "percent":
                if row.get("value") is not None:
                    slot["_samples"].append(float(row["value"]))
            elif kind == "yesno":
                slot["_answers"] += 1
                if float(row.get("value") or 0) >= 1:
                    slot["_yes"] += 1
            else:
                slot["value"] = float(slot.get("value") or 0) + float(row.get("value") or 0)
    rows = []
    for key in order:
        row = buckets[key]
        kind = str(row.get("kind") or "number")
        if kind == "percent":
            samples = row.pop("_samples")
            row.pop("_yes", None)
            row.pop("_answers", None)
            if not samples:
                continue
            number = sum(samples) / len(samples)
            row["value"] = number
            row["display"] = format_percent(number)
        elif kind == "yesno":
            row.pop("_samples", None)
            yes = int(row.pop("_yes") or 0)
            answers = int(row.pop("_answers") or 0)
            row["value"] = float(yes)
            if answers and yes == answers:
                row["display"] = t("Yes")
            elif yes == 0:
                row["display"] = t("No")
            else:
                row["display"] = f"{yes} of {answers}"
        else:
            row.pop("_samples", None)
            row.pop("_yes", None)
            row.pop("_answers", None)
            number = float(row.get("value") or 0)
            row["value"] = number
            row["display"] = format_thousands(number) if number else ""
        rows.append(row)
    return rows


def _merge_emergencies(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for em in payload.get("emergencies") or []:
            key = str(em.get("code") or em.get("name") or "").strip()
            if not key:
                continue
            slot = buckets.get(key)
            if slot is None:
                slot = dict(em)
                slot["people_reached"] = 0.0
                slot["indicators"] = []
                slot["_indicator_payloads"] = []
                buckets[key] = slot
                order.append(key)
            if em.get("people_reached") is not None:
                slot["people_reached"] = float(slot.get("people_reached") or 0) + float(em.get("people_reached") or 0)
            slot["_indicator_payloads"].append({"core_indicators": em.get("indicators") or []})
    rows = []
    for index, key in enumerate(order, start=1):
        em = buckets[key]
        indicators = _merge_indicators(em.pop("_indicator_payloads"), "core_indicators")
        people = float(em.get("people_reached") or 0)
        em["slot"] = index
        em["people_reached"] = people or None
        em["people_display"] = format_count(people) if people else ""
        em["indicators"] = indicators
        rows.append(em)
    return rows


def _merge_support(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[tuple[Any, Any, str]] = []
    buckets: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for payload in payloads:
        for row in payload.get("support") or []:
            key = (row.get("ns_id"), row.get("year"), str(row.get("name") or ""))
            slot = buckets.get(key)
            if slot is None:
                slot = dict(row)
                slot["funding"] = float(row.get("funding") or 0)
                slot["confirmed"] = float(row.get("confirmed") or 0)
                slot["area_amounts"] = {
                    code: float(amount or 0) for code, amount in (row.get("area_amounts") or {}).items()
                }
                buckets[key] = slot
                order.append(key)
                continue
            slot["funding"] = float(slot.get("funding") or 0) + float(row.get("funding") or 0)
            slot["confirmed"] = float(slot.get("confirmed") or 0) + float(row.get("confirmed") or 0)
            areas = dict(slot.get("areas") or {})
            for code, flag in (row.get("areas") or {}).items():
                areas[code] = bool(areas.get(code) or flag)
            slot["areas"] = areas
            amounts = dict(slot.get("area_amounts") or {})
            for code, amount in (row.get("area_amounts") or {}).items():
                amounts[code] = float(amounts.get(code) or 0) + float(amount or 0)
            slot["area_amounts"] = amounts
    rows = []
    for key in order:
        row = buckets[key]
        funding = float(row.get("funding") or 0)
        confirmed = float(row.get("confirmed") or 0)
        row["funding"] = funding or None
        row["funding_display"] = format_compact_chf(funding) if funding else ""
        row["confirmed"] = confirmed or None
        row["confirmed_display"] = format_compact_chf(confirmed) if confirmed else ""
        amounts = row.get("area_amounts") or {}
        row["area_amounts"] = {
            code: (float(amount) if amount else None) for code, amount in amounts.items()
        }
        rows.append(row)
    rows.sort(key=lambda row: ((row.get("name") or "").lower(), int(row.get("year") or 0)))
    return rows


def _merge_financial(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    base = dict((payloads[0].get("financial") or {}))
    base["years"] = _merge_year_rows(payloads)
    base["sources"] = _merge_named_amounts(payloads, "sources")
    base["cover_sources"] = _merge_named_amounts(payloads, "cover_sources")
    base["breakdown"] = _merge_breakdown(payloads)
    base["area_years"] = _merge_area_years(payloads)
    base["ifrc_network"] = _merge_money_block(payloads, "ifrc_network")
    base["national_society"] = _merge_money_block(payloads, "national_society")
    base["network_entities"] = _merge_network_entities(payloads)
    return base


def _merge_year_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[Any] = []
    buckets: dict[Any, dict[str, float]] = {}
    for payload in payloads:
        for row in ((payload.get("financial") or {}).get("years") or []):
            year = row.get("year")
            if year not in buckets:
                buckets[year] = {"hns": 0.0, "ifrc": 0.0, "pns": 0.0, "total": 0.0}
                order.append(year)
            for key in ("hns", "ifrc", "pns", "total"):
                buckets[year][key] += float(row.get(key) or 0)
    rows = []
    for year in order:
        amounts = buckets[year]
        row = {"year": year}
        for key, number in amounts.items():
            row[key] = number
            row[f"{key}_display"] = format_compact_chf(number) if number else ""
        rows.append(row)
    return rows


def _merge_named_amounts(payloads: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in ((payload.get("financial") or {}).get(field) or []):
            key = str(row.get("entity") or row.get("label") or "")
            if not key:
                continue
            slot = buckets.get(key)
            if slot is None:
                slot = dict(row)
                slot["value"] = 0.0
                buckets[key] = slot
                order.append(key)
            slot["value"] = float(slot.get("value") or 0) + float(row.get("value") or 0)
    rows = []
    for key in order:
        row = buckets[key]
        number = float(row.get("value") or 0)
        row["value"] = number
        row["display"] = format_compact_chf(number) if number else t("Not reported")
        rows.append(row)
    return rows


def _merge_breakdown(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in ((payload.get("financial") or {}).get("breakdown") or []):
            code = str(row.get("code") or "")
            if not code:
                continue
            slot = buckets.get(code)
            if slot is None:
                slot = dict(row)
                slot["funding"] = 0.0
                slot["expenditure"] = 0.0
                buckets[code] = slot
                order.append(code)
            slot["funding"] = float(slot.get("funding") or 0) + float(row.get("funding") or 0)
            slot["expenditure"] = float(slot.get("expenditure") or 0) + float(row.get("expenditure") or 0)
    rows = []
    for code in order:
        row = buckets[code]
        row["funding"] = float(row["funding"]) or None
        row["expenditure"] = float(row["expenditure"]) or None
        rows.append(row)
    return rows


def _merge_area_years(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[Any] = []
    buckets: dict[Any, dict[str, dict[str, float]]] = {}
    for payload in payloads:
        for row in ((payload.get("financial") or {}).get("area_years") or []):
            year = row.get("year")
            if year not in buckets:
                buckets[year] = {}
                order.append(year)
            for entity, amounts in (row.get("by_entity") or {}).items():
                dest = buckets[year].setdefault(str(entity), {})
                for code, amount in (amounts or {}).items():
                    dest[code] = float(dest.get(code) or 0) + float(amount or 0)
    return [{"year": year, "by_entity": buckets[year]} for year in order]


def _merge_money_block(payloads: list[dict[str, Any]], field: str) -> dict[str, Any]:
    keys = ("funding_requirement", "funding", "expenditure")
    totals = {key: 0.0 for key in keys}
    seen = {key: False for key in keys}
    template = dict(((payloads[0].get("financial") or {}).get(field) or {}))
    for payload in payloads:
        block = ((payload.get("financial") or {}).get(field) or {})
        for key in keys:
            if block.get(key) is None:
                continue
            seen[key] = True
            totals[key] += float(block.get(key) or 0)
    for key in keys:
        number = totals[key] if seen[key] else None
        template[key] = number or None
        if f"{key}_display" in template or key in {"funding", "expenditure", "funding_requirement"}:
            template[f"{key}_display"] = format_compact_chf(number) if number else t("Not reported")
    return template


def _merge_network_entities(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order: list[str] = []
    buckets: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for entity in ((payload.get("financial") or {}).get("network_entities") or []):
            key = str(entity.get("key") or entity.get("label") or "")
            if not key:
                continue
            slot = buckets.get(key)
            if slot is None:
                slot = {"key": entity.get("key"), "label": entity.get("label"), "metrics": {}}
                buckets[key] = slot
                order.append(key)
            for metric in entity.get("metrics") or []:
                metric_key = str(metric.get("key") or "")
                if not metric_key:
                    continue
                if metric_key not in slot["metrics"]:
                    dest = dict(metric)
                    dest["value"] = float(metric.get("value") or 0)
                    slot["metrics"][metric_key] = dest
                    continue
                dest = slot["metrics"][metric_key]
                dest["value"] = float(dest.get("value") or 0) + float(metric.get("value") or 0)
    rows = []
    for key in order:
        entity = buckets[key]
        metrics = []
        for metric in entity["metrics"].values():
            number = float(metric.get("value") or 0)
            metric["value"] = number
            metric["display"] = format_compact_chf(number) if number else t("Not reported")
            metric["reported"] = bool(number)
            metrics.append(metric)
        rows.append({"key": entity["key"], "label": entity["label"], "metrics": metrics})
    return rows
