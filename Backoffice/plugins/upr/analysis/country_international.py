"""Country-scoped international bilateral support for the mobile country profile.

A country is treated as a Participating National Society (PNS) when it has an
assignment on the UPR PNS plan or report templates (22 / 23). Those countries
see outbound bilateral-support embeds; other countries see inbound support
(PNSs supporting them) plus received-funding figures from the public flow map.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from flask import url_for

from plugins.upr.dashboards.catalog import PNS_PLAN_TEMPLATE_ID, PNS_REPORT_TEMPLATE_ID

_PNS_TEMPLATE_IDS = (PNS_PLAN_TEMPLATE_ID, PNS_REPORT_TEMPLATE_ID)


@lru_cache(maxsize=1)
def pns_country_iso3s() -> frozenset[str]:
    """ISO3 codes assigned to UPR PNS plan or report templates."""
    from app.extensions import db
    from app.models import AssignedForm, AssignmentEntityStatus, Country

    rows = (
        db.session.query(db.func.upper(Country.iso3))
        .join(AssignmentEntityStatus, AssignmentEntityStatus.entity_id == Country.id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignedForm.template_id.in_(_PNS_TEMPLATE_IDS),
            Country.iso3.isnot(None),
        )
        .distinct()
        .all()
    )
    out: set[str] = set()
    for (iso3,) in rows:
        code = (iso3 or "").strip().upper()
        if len(code) == 3 and code.isalpha():
            out.add(code)
    return frozenset(out)


def clear_pns_country_iso3s_cache() -> None:
    pns_country_iso3s.cache_clear()


def country_is_pns(iso3: str) -> bool:
    code = (iso3 or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        return False
    return code in pns_country_iso3s()


def _latest_year(flows: dict[str, Any]) -> int | None:
    years = flows.get("years") or []
    for year in years:
        try:
            return int(year)
        except (TypeError, ValueError):
            continue
    return None


def _money_total(rows: list[dict[str, Any]], key: str) -> float:
    totals = [row for row in rows if not row.get("area")]
    if totals:
        return float(sum(float(row.get(key) or 0) for row in totals))
    return float(sum(float(row.get(key) or 0) for row in rows if row.get("area")))


def _partner_rows_for_pns(
    *,
    iso3: str,
    year: int | None,
    flows: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Countries this PNS supports, with optional funding sent."""
    funding_by_host: dict[str, float] = {}
    for link in flows.get("funding") or []:
        if year is not None and int(link.get("year") or 0) != year:
            continue
        if str(link.get("from") or "").upper() != iso3:
            continue
        host = str(link.get("to") or "").upper()
        if not host:
            continue
        funding_by_host[host] = funding_by_host.get(host, 0.0) + float(link.get("value") or 0)

    names = {
        str(node.get("iso3") or "").upper(): str(node.get("name") or node.get("iso3") or "")
        for node in (flows.get("nodes") or [])
    }
    hosts: dict[str, dict[str, Any]] = {}
    for edge in flows.get("edges") or []:
        if str(edge.get("from") or "").upper() != iso3:
            continue
        if year is not None and year not in (edge.get("years") or []):
            continue
        host = str(edge.get("to") or "").upper()
        if not host:
            continue
        hosts[host] = {
            "iso3": host,
            "name": names.get(host) or host,
            "funding": funding_by_host.get(host),
        }
    for host, amount in funding_by_host.items():
        hosts.setdefault(
            host,
            {"iso3": host, "name": names.get(host) or host, "funding": amount},
        )
        hosts[host]["funding"] = amount

    ordered = sorted(
        hosts.values(),
        key=lambda row: (-(row.get("funding") or 0), str(row.get("name") or "").lower()),
    )
    return ordered, funding_by_host


def _partner_rows_for_host(
    *,
    iso3: str,
    year: int | None,
    flows: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """PNSs supporting this country, with optional funding received from each."""
    funding_by_donor: dict[str, float] = {}
    donor_names: dict[str, str] = {}
    for link in flows.get("funding") or []:
        if year is not None and int(link.get("year") or 0) != year:
            continue
        if str(link.get("to") or "").upper() != iso3:
            continue
        donor = str(link.get("from") or "").upper()
        name = str(link.get("from_name") or donor or "").strip()
        if donor:
            funding_by_donor[donor] = funding_by_donor.get(donor, 0.0) + float(link.get("value") or 0)
            if name:
                donor_names[donor] = name
        elif name:
            key = name
            funding_by_donor[key] = funding_by_donor.get(key, 0.0) + float(link.get("value") or 0)
            donor_names[key] = name

    names = {
        str(node.get("iso3") or "").upper(): str(node.get("name") or node.get("iso3") or "")
        for node in (flows.get("nodes") or [])
    }
    donors: dict[str, dict[str, Any]] = {}
    for edge in flows.get("edges") or []:
        if str(edge.get("to") or "").upper() != iso3:
            continue
        if year is not None and year not in (edge.get("years") or []):
            continue
        donor = str(edge.get("from") or "").upper()
        if not donor:
            continue
        donors[donor] = {
            "iso3": donor,
            "name": donor_names.get(donor) or names.get(donor) or donor,
            "funding": funding_by_donor.get(donor),
        }
    for key, amount in funding_by_donor.items():
        code = key if len(key) == 3 and key.isalpha() else None
        donors.setdefault(
            key,
            {
                "iso3": code,
                "name": donor_names.get(key) or names.get(key) or key,
                "funding": amount,
            },
        )
        donors[key]["funding"] = amount

    ordered = sorted(
        donors.values(),
        key=lambda row: (-(row.get("funding") or 0), str(row.get("name") or "").lower()),
    )
    return ordered, funding_by_donor


def _figure_rows(flows: dict[str, Any], *, year: int | None, pns: str | None, recipient: str | None):
    rows = []
    for row in flows.get("figures") or []:
        if year is not None and int(row.get("year") or 0) != year:
            continue
        if pns and str(row.get("from") or "").upper() != pns:
            continue
        if recipient and str(row.get("to") or "").upper() != recipient:
            continue
        rows.append(row)
    return rows


def _embed_urls(*, is_pns: bool, iso3: str, year: int | None) -> dict[str, str]:
    """Public UPR embed paths the mobile WebView can load against the backoffice host."""
    year_args = {"year": str(year)} if year else {}
    if is_pns:
        return {
            "primary": url_for("upr.support_overview_embed", pns=iso3, **year_args),
            "flow": url_for("upr.support_flow_embed", pns=iso3, **year_args),
            "funding": url_for("upr.support_funding_embed", **year_args),
            "coverage": url_for("upr.support_coverage_embed", **year_args),
        }
    return {
        "primary": url_for("upr.support_flow_embed", recipient=iso3, **year_args),
        "flow": url_for("upr.support_flow_embed", recipient=iso3, **year_args),
        "overview": url_for("upr.support_overview_embed", recipient=iso3, **year_args),
    }


def build_country_international(iso3: str) -> dict[str, Any]:
    """Payload for the mobile country International institutional sub-tab."""
    from plugins.upr.analysis.flow import build_support_flows
    from plugins.upr.analysis.staff_presence import build_staff_presence

    code = (iso3 or "").strip().upper()
    is_pns = country_is_pns(code)
    flows = build_support_flows(public_tiles=True)
    year = _latest_year(flows)

    if is_pns:
        partners, _funding = _partner_rows_for_pns(iso3=code, year=year, flows=flows)
        figures = _figure_rows(flows, year=year, pns=code, recipient=None)
        summary = {
            "year": year,
            "countries_supported": len(partners),
            "supporting_partners": None,
            "funding": _money_total(figures, "funding") or sum(
                float(p.get("funding") or 0) for p in partners
            ),
            "requirement": _money_total(figures, "requirement"),
            "expenditure": _money_total(figures, "expenditure"),
        }
        role = "pns"
    else:
        partners, _funding = _partner_rows_for_host(iso3=code, year=year, flows=flows)
        figures = _figure_rows(flows, year=year, pns=None, recipient=code)
        summary = {
            "year": year,
            "countries_supported": None,
            "supporting_partners": len(partners),
            "funding": _money_total(figures, "funding") or sum(
                float(p.get("funding") or 0) for p in partners
            ),
            "requirement": _money_total(figures, "requirement"),
            "expenditure": _money_total(figures, "expenditure"),
        }
        role = "host"

    staff_presence = build_staff_presence(iso3=code, is_pns=is_pns, preferred_year=year)
    summary["staff_presence"] = int(staff_presence.get("count") or 0)

    has_support = (
        bool(partners)
        or bool(summary.get("funding"))
        or bool(summary.get("requirement"))
        or bool(staff_presence.get("count"))
    )
    return {
        "iso3": code,
        "is_pns": is_pns,
        "role": role,
        "has_support": has_support,
        "years": flows.get("years") or [],
        "summary": summary,
        "partners": partners,
        "staff_presence": staff_presence,
        "embeds": _embed_urls(is_pns=is_pns, iso3=code, year=year),
    }
