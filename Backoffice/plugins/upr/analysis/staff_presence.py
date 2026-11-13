"""PNS staff presence by host country from UPR template 22 Staff contributions.

Template 22 stores one matrix per Participating National Society (AES = PNS
home country). Cells are ``{host_ns_id}_{column}`` with delegate / national
staff counts. Presence is any positive total across columns for that host row.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from plugins.upr.dashboards.catalog import PNS_PLAN_TEMPLATE_ID
from plugins.upr.dashboards.matrix import _iter_matrix_numbers, _matrix_cells


@dataclass(frozen=True)
class StaffPresenceLink:
    year: int
    pns_iso3: str
    pns_name: str
    host_iso3: str
    host_name: str
    staff: float


def clear_staff_presence_cache() -> None:
    staff_presence_links.cache_clear()
    _resolve_staff_item_id.cache_clear()


@lru_cache(maxsize=1)
def _resolve_staff_item_id() -> int | None:
    """Published T22 staff matrix id (stable_key, then staff column, then label)."""
    from app.models import FormItem, FormTemplate
    from app.utils.templates.stable_key import T22_STAFF_MATRIX_COLUMN, T22_STAFF_MATRIX_STABLE_KEY, resolve_published_form_item_id

    item_id = resolve_published_form_item_id(PNS_PLAN_TEMPLATE_ID, T22_STAFF_MATRIX_STABLE_KEY)
    if item_id:
        return int(item_id)

    template = FormTemplate.query.get(PNS_PLAN_TEMPLATE_ID)
    version_id = getattr(template, "published_version_id", None) if template else None
    if not version_id:
        return None

    items = (
        FormItem.query.filter_by(
            template_id=PNS_PLAN_TEMPLATE_ID,
            version_id=int(version_id),
            archived=False,
            item_type="matrix",
        ).all()
    )
    for item in items:
        config = item.config if isinstance(item.config, dict) else {}
        matrix_cfg = config.get("matrix_config") if isinstance(config.get("matrix_config"), dict) else config
        columns = matrix_cfg.get("columns") or [] if isinstance(matrix_cfg, dict) else []
        names: set[str] = set()
        for col in columns:
            if isinstance(col, dict):
                name = col.get("name") or col.get("text") or col.get("label")
            else:
                name = col
            if name:
                names.add(str(name).strip().lower())
        if T22_STAFF_MATRIX_COLUMN in names:
            return int(item.id)

    for item in items:
        label = (item.label or "").strip().lower()
        if "staff contribution" in label or "pns staff" in label:
            return int(item.id)
    return None


def host_staff_totals(cells: dict[str, Any]) -> dict[int, float]:
    """Sum numeric staff cells per host National Society id."""
    totals: dict[int, float] = {}
    for row, _col, number in _iter_matrix_numbers(cells):
        if not str(row).isdigit():
            continue
        host_id = int(row)
        totals[host_id] = totals.get(host_id, 0.0) + float(number)
    return totals


def _period_year(period_name: str | None) -> int | None:
    text = (period_name or "").strip()
    if not text:
        return None
    # Prefer a bare calendar year; otherwise take the first 4-digit year token.
    if text.isdigit() and len(text) == 4:
        return int(text)
    for token in text.replace("/", " ").replace("-", " ").split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return None


@lru_cache(maxsize=1)
def staff_presence_links() -> tuple[StaffPresenceLink, ...]:
    """All positive staff-presence links from published T22 staff matrices."""
    from app.extensions import db
    from app.models import (
        AssignedForm,
        AssignmentEntityStatus,
        Country,
        FormData,
        NationalSociety,
    )

    item_id = _resolve_staff_item_id()
    if not item_id:
        return ()

    rows = (
        db.session.query(FormData, AssignmentEntityStatus, AssignedForm, Country)
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(AssignedForm.template_id == PNS_PLAN_TEMPLATE_ID)
        .filter(FormData.form_item_id == int(item_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .all()
    )
    if not rows:
        return ()

    host_ns_ids: set[int] = set()
    parsed: list[tuple[int, str, str, dict[int, float]]] = []
    for entry, _aes, assigned, pns_country in rows:
        year = _period_year(getattr(assigned, "period_name", None))
        if year is None:
            continue
        pns_iso3 = (pns_country.iso3 or "").strip().upper()
        if len(pns_iso3) != 3 or not pns_iso3.isalpha():
            continue
        totals = host_staff_totals(_matrix_cells(entry))
        if not totals:
            continue
        host_ns_ids.update(totals)
        pns_name = (pns_country.name or pns_iso3).strip() or pns_iso3
        parsed.append((year, pns_iso3, pns_name, totals))

    if not parsed:
        return ()

    ns_rows = (
        NationalSociety.query.filter(NationalSociety.id.in_(sorted(host_ns_ids)))
        .filter(NationalSociety.is_active.is_(True))
        .order_by(NationalSociety.display_order.asc().nullslast(), NationalSociety.id.asc())
        .all()
    )
    host_by_ns: dict[int, tuple[str, str]] = {}
    country_ids = {int(ns.country_id) for ns in ns_rows if ns.country_id}
    countries = {
        int(c.id): c
        for c in Country.query.filter(Country.id.in_(sorted(country_ids))).all()
    } if country_ids else {}
    for ns in ns_rows:
        country = countries.get(int(ns.country_id)) if ns.country_id else None
        if not country:
            continue
        iso3 = (country.iso3 or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        name = (country.name or iso3).strip() or iso3
        host_by_ns.setdefault(int(ns.id), (iso3, name))

    # Prefer NS name for the PNS side when available (host view labels).
    pns_iso3s = sorted({iso3 for _year, iso3, _name, _totals in parsed})
    pns_ns_name: dict[str, str] = {}
    if pns_iso3s:
        pns_countries = {
            (c.iso3 or "").strip().upper(): c
            for c in Country.query.filter(db.func.upper(Country.iso3).in_(pns_iso3s)).all()
        }
        pns_country_ids = [int(c.id) for c in pns_countries.values()]
        if pns_country_ids:
            for ns in (
                NationalSociety.query.filter(NationalSociety.country_id.in_(pns_country_ids))
                .filter(NationalSociety.is_active.is_(True))
                .order_by(NationalSociety.display_order.asc().nullslast(), NationalSociety.id.asc())
                .all()
            ):
                country = next(
                    (c for c in pns_countries.values() if int(c.id) == int(ns.country_id)),
                    None,
                )
                if not country:
                    continue
                code = (country.iso3 or "").strip().upper()
                pns_ns_name.setdefault(code, (ns.name or "").strip())

    links: list[StaffPresenceLink] = []
    for year, pns_iso3, pns_country_name, totals in parsed:
        pns_name = pns_ns_name.get(pns_iso3) or pns_country_name
        for host_ns_id, staff in totals.items():
            host = host_by_ns.get(int(host_ns_id))
            if not host:
                continue
            host_iso3, host_name = host
            if host_iso3 == pns_iso3:
                continue
            links.append(
                StaffPresenceLink(
                    year=year,
                    pns_iso3=pns_iso3,
                    pns_name=pns_name,
                    host_iso3=host_iso3,
                    host_name=host_name,
                    staff=float(staff),
                )
            )

    links.sort(
        key=lambda link: (
            -link.year,
            link.pns_iso3,
            link.host_iso3,
        )
    )
    return tuple(links)


def _pick_year(years: set[int], preferred_year: int | None) -> int | None:
    if preferred_year is not None and preferred_year in years:
        return preferred_year
    if not years:
        return preferred_year
    return max(years)


def build_staff_presence(
    *,
    iso3: str,
    is_pns: bool,
    preferred_year: int | None = None,
) -> dict[str, Any]:
    """Staff-presence payload for one country International tab."""
    code = (iso3 or "").strip().upper()
    empty = {"year": preferred_year, "count": 0, "entries": []}
    if len(code) != 3 or not code.isalpha():
        return empty

    links = staff_presence_links()
    if is_pns:
        relevant = [link for link in links if link.pns_iso3 == code]
    else:
        relevant = [link for link in links if link.host_iso3 == code]
    if not relevant:
        return empty

    year = _pick_year({link.year for link in relevant}, preferred_year)
    year_links = [link for link in relevant if year is None or link.year == year]

    # Aggregate duplicate host/pns rows (multiple columns already summed; periods may overlap).
    merged: dict[str, dict[str, Any]] = {}
    for link in year_links:
        if is_pns:
            key = link.host_iso3
            row = {
                "iso3": link.host_iso3,
                "name": link.host_name,
                "staff": link.staff,
            }
        else:
            key = link.pns_iso3
            row = {
                "iso3": link.pns_iso3,
                "name": link.pns_name,
                "staff": link.staff,
            }
        existing = merged.get(key)
        if existing is None:
            merged[key] = row
        else:
            existing["staff"] = float(existing.get("staff") or 0) + float(link.staff)

    ordered = sorted(
        merged.values(),
        key=lambda row: (-float(row.get("staff") or 0), str(row.get("name") or "").lower()),
    )
    staff_total = round(sum(float(row.get("staff") or 0) for row in ordered), 2)
    return {
        "year": year,
        "count": len(ordered),
        "staff_total": staff_total,
        "entries": ordered,
    }
