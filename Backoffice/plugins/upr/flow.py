"""PNS → host-country support flows for the Analysis "flow map".

The Analysis tab draws a Power BI-style flow map: a curved line is drawn from
every Participating National Society (PNS, the donor) to each country it supports
bilaterally. This module turns the same live master extract the other Analysis
visuals use (:func:`plugins.upr.upr_data.build_upr_master`) into the node/edge
geometry the browser needs.

* A **node** is a country (donor and/or host) placed on its centroid.
* An **edge** is a donor → host relationship. The browser shows one year at a
  time and draws that pair once, even when the same year has a plan and a report.

Donor coordinates come from the PNS's own National Society country; host
coordinates from the reporting country. Both are resolved to a centroid via the
vendored ``geo/country_centroids.json`` table (keyed by ISO-2).

The figures are *indicative* and summed from the Unified Plans and Reports
currently in the database, like the rest of the Analysis feature.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from plugins.upr import _PLUGIN_DIR
from plugins.upr.catalog import AREA_LABELS, SUPPORT_AREA_CODES
from plugins.upr.matrix import _area_code
from plugins.upr.analysis_common import (
    iso3s_in_region,
    load_countries,
    norm,
    num,
    round_calendar_year,
    round_kind,
    round_prefix,
    round_sort_key,
)
from plugins.upr.api_cache import get_or_build_upr_payload

__all__ = ["build_support_flows"]

# Master rows that describe one PNS supporting one host country.
_SUPPORT_SECTIONS = {"support", "activities"}
_AREA_ORDER = ("SP2", "SP3", "SP4", "SP1", "EFs", "SP5")
_FIGURE_METRICS = {
    "funding": "funding",
    "expenditure": "expenditure",
    "funding requirement": "requirement",
}


@lru_cache(maxsize=1)
def _centroids() -> dict[str, tuple[float, float]]:
    """``{ISO2: (lat, lng)}`` country centroids vendored with the plugin."""
    path = _PLUGIN_DIR / "geo" / "country_centroids.json"
    try:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for iso2, latlng in raw.items():
        if isinstance(latlng, (list, tuple)) and len(latlng) == 2:
            try:
                out[str(iso2).upper()] = (float(latlng[0]), float(latlng[1]))
            except (TypeError, ValueError):
                continue
    return out


def _donor_name_to_iso3() -> dict[str, str]:
    """Map a National Society display name (as stored on master rows) to its ISO3.

    Built from the same source the master builder uses for the ``NS`` field, so a
    lookup by the stored name resolves to the society's own country.
    """
    from plugins.upr.upr_data import _load_national_societies

    by_id, _by_country, country_by_ns = _load_national_societies()
    out: dict[str, str] = {}
    for ns_id, name in by_id.items():
        info = country_by_ns.get(ns_id) or {}
        iso3 = str(info.get("iso3") or "").strip().upper()
        key = norm(name)
        if key and iso3:
            out[key] = iso3
    return out


def _coord(iso3: str, countries: dict[str, Any], centroids: dict[str, tuple[float, float]]):
    info = countries.get(iso3) or {}
    iso2 = str(info.get("iso2") or "").strip().upper()
    if not iso2:
        return None
    return centroids.get(iso2)


def aggregate_flows(
    master_rows: list[dict[str, Any]],
    *,
    countries: dict[str, Any],
    donor_iso3_by_name: dict[str, str],
    host_iso3s: set[str] | None,
) -> dict[str, Any]:
    """Pure reducer: master rows → nodes, edges and diagnostics.

    ``host_iso3s`` restricts the hosts (a region filter). Donors are kept
    wherever they sit, so support *into* a region from outside it still shows.
    """
    centroids = _centroids()
    edges: dict[tuple[str, str], set[str]] = {}
    unresolved: set[str] = set()
    rounds_seen: set[str] = set()

    for row in master_rows:
        if norm(row.get("Section")) not in _SUPPORT_SECTIONS:
            continue
        if norm(row.get("Entity")) != "pns":
            continue
        host_iso3 = str(row.get("ISO3") or "").strip().upper()
        if not host_iso3:
            continue
        if host_iso3s is not None and host_iso3 not in host_iso3s:
            continue
        donor_name = str(row.get("NS") or "").strip()
        donor_iso3 = donor_iso3_by_name.get(norm(donor_name))
        if not donor_iso3:
            if donor_name:
                unresolved.add(donor_name)
            continue
        if donor_iso3 == host_iso3:
            # A society "supporting" its own country adds no flow line.
            continue
        code = str(row.get("Round") or "").strip()
        if code:
            rounds_seen.add(code)
        edges.setdefault((donor_iso3, host_iso3), set()).add(code)

    _add_reported_support_edges(
        master_rows,
        edges=edges,
        unresolved=unresolved,
        rounds_seen=rounds_seen,
        donor_iso3_by_name=donor_iso3_by_name,
        host_iso3s=host_iso3s,
    )

    # Only keep edges whose both ends have a known centroid.
    nodes: dict[str, dict[str, Any]] = {}
    edge_list: list[dict[str, Any]] = []
    for (donor_iso3, host_iso3), round_set in edges.items():
        donor_pos = _coord(donor_iso3, countries, centroids)
        host_pos = _coord(host_iso3, countries, centroids)
        if not donor_pos or not host_pos:
            continue
        ordered_rounds = sorted((r for r in round_set if r), key=round_sort_key)
        years = sorted(
            {y for y in (round_calendar_year(code) for code in ordered_rounds) if y is not None}
        )
        # One link per donor–host. The year filter on the map decides which
        # years are drawn; weight stays 1 so a plan and a report of the same
        # year are not two lines.
        weight = 1
        _touch_node(nodes, donor_iso3, countries, donor_pos)
        _touch_node(nodes, host_iso3, countries, host_pos)
        nodes[donor_iso3]["out_weight"] += weight
        nodes[host_iso3]["in_weight"] += weight
        edge_list.append(
            {
                "from": donor_iso3,
                "to": host_iso3,
                "weight": weight,
                "years": years,
                "rounds": ordered_rounds,
                "latest_round": ordered_rounds[-1] if ordered_rounds else None,
            }
        )

    for node in nodes.values():
        out_w = node["out_weight"]
        in_w = node["in_weight"]
        node["role"] = "both" if out_w and in_w else ("donor" if out_w else "host")

    edge_list.sort(key=lambda e: e["weight"], reverse=True)
    node_list = sorted(nodes.values(), key=lambda n: str(n["name"]).lower())

    years = sorted(
        {year for edge in edge_list for year in edge["years"]},
        reverse=True,
    )
    funding = _funding_links(
        master_rows,
        donor_iso3_by_name=donor_iso3_by_name,
        host_iso3s=host_iso3s,
        countries=countries,
    )
    figures = _support_figures(
        master_rows,
        donor_iso3_by_name=donor_iso3_by_name,
        host_iso3s=host_iso3s,
    )
    years = sorted(
        set(years) | {link["year"] for link in funding} | {row["year"] for row in figures},
        reverse=True,
    )
    return {
        "nodes": node_list,
        "edges": edge_list,
        "funding": funding,
        "figures": figures,
        "coverage": _coverage_points(figures, countries),
        "inform": {"edition": _inform_edition()},
        "areas": [
            {"code": code, "label": AREA_LABELS.get(code, code)}
            for code in _AREA_ORDER
            if code in SUPPORT_AREA_CODES
        ],
        "years": years,
        "rounds": sorted(rounds_seen, key=round_sort_key),
        "unresolved_donors": sorted(unresolved),
        "has_data": bool(edge_list),
    }


def _funding_links(
    master_rows: list[dict[str, Any]],
    *,
    donor_iso3_by_name: dict[str, str],
    host_iso3s: set[str] | None,
    countries: dict[str, Any],
) -> list[dict[str, Any]]:
    """PNS self-reported bilateral funding, one report round per year.

    The annual report wins over the mid-year report for the same year, so a
    figure is not counted twice. Each link is one donor society to one host
    country. The browser ranks donors (funding sent) and hosts (funding received).
    """
    raw: list[dict[str, Any]] = []
    rounds_by_year: dict[int, set[str]] = {}
    for row in master_rows:
        if norm(row.get("Source")) != "pns data" or norm(row.get("Indicator")) != "funding":
            continue
        value = num(row.get("ValueNum"))
        if not value:
            continue
        code = str(row.get("Round") or "").strip()
        year = round_calendar_year(code)
        if year is None or round_kind(code) != "report":
            continue
        host = str(row.get("ISO3") or "").strip().upper()
        donor_name = str(row.get("NS") or "").strip()
        donor = donor_iso3_by_name.get(norm(donor_name), "")
        if not host or (donor and host == donor):
            continue
        if host_iso3s is not None and host not in host_iso3s:
            continue
        rounds_by_year.setdefault(year, set()).add(code)
        host_info = countries.get(host) or {}
        raw.append(
            {
                "year": year,
                "round": code,
                "from": donor,
                "from_name": donor_name or donor or host,
                "to": host,
                "to_name": host_info.get("name") or str(row.get("Country") or "").strip() or host,
                "value": float(value),
            }
        )
    chosen: dict[int, str] = {}
    for year, codes in rounds_by_year.items():
        annual = [code for code in codes if round_prefix(code) == "AR"]
        pool = annual or list(codes)
        chosen[year] = sorted(pool, key=round_sort_key)[-1]

    merged: dict[tuple, dict[str, Any]] = {}
    for item in raw:
        if item["round"] != chosen.get(item["year"]):
            continue
        key = (item["year"], item["from"] or norm(item["from_name"]), item["to"])
        current = merged.get(key)
        if current is None:
            merged[key] = {
                "year": item["year"],
                "from": item["from"],
                "from_name": item["from_name"],
                "to": item["to"],
                "to_name": item["to_name"],
                "value": item["value"],
            }
        else:
            current["value"] += item["value"]
            if item["from_name"]:
                current["from_name"] = item["from_name"]
    links = list(merged.values())
    for link in links:
        link["value"] = round(link["value"], 2)
    links.sort(key=lambda link: link["value"], reverse=True)
    return links


def _chart_area(area: str) -> str | None:
    """Strategic priority / enabling-function code, or ``None`` for a total column."""
    code = _area_code(area)
    if code in {"EF1", "EF2", "EF3", "EF4"}:
        code = "EFs"
    if code in SUPPORT_AREA_CODES:
        return code
    label = norm(area)
    for known in SUPPORT_AREA_CODES:
        if norm(AREA_LABELS.get(known)) == label:
            return known
    return None


def _prefer_report(candidate: str, incumbent: str) -> bool:
    """True when *candidate* should replace *incumbent* for the same year.

    The annual report wins over the mid-year report. A later round wins within
    the same kind. A mid-year figure is kept when the annual report has no row
    for that country.
    """
    candidate_annual = round_prefix(candidate) == "AR"
    incumbent_annual = round_prefix(incumbent) == "AR"
    if candidate_annual != incumbent_annual:
        return candidate_annual
    return round_sort_key(candidate) > round_sort_key(incumbent)


def _support_figures(
    master_rows: list[dict[str, Any]],
    *,
    donor_iso3_by_name: dict[str, str],
    host_iso3s: set[str] | None,
) -> list[dict[str, Any]]:
    """Requirement, funding and expenditure for one year, optionally by priority.

    Reported funding and expenditure are Participating Society self-reports
    (``Source = PNS Data``). On the PNS reporting form, the strategic-priority
    columns are the expenditure breakdown. For the same country and priority,
    the annual report wins over the mid-year report. A mid-year amount is kept
    when the annual report does not mention that country. The funding
    requirement is the PNS amount on the plan. ``area`` is empty on the
    headline total. A host National Society's own priority breakdown is not
    included.
    """
    raw: list[dict[str, Any]] = []
    for row in master_rows:
        metric = _FIGURE_METRICS.get(norm(row.get("Indicator")))
        if metric is None:
            continue
        value = num(row.get("ValueNum"))
        if not value:
            continue
        code = str(row.get("Round") or "").strip()
        year = round_calendar_year(code)
        kind = round_kind(code)
        if year is None or kind is None:
            continue
        source = norm(row.get("Source"))
        area = _chart_area(str(row.get("Area") or ""))
        if metric == "requirement":
            if kind != "plan" or norm(row.get("Entity")) != "pns":
                continue
        else:
            if kind != "report" or source != "pns data":
                continue
        host = str(row.get("ISO3") or "").strip().upper()
        # On a plan the NS column is the host, not the supporting society.
        donor = ""
        if metric != "requirement":
            donor_name = str(row.get("NS") or "").strip()
            donor = donor_iso3_by_name.get(norm(donor_name), "")
            if donor and host == donor:
                continue
        if host_iso3s is not None and host and host not in host_iso3s:
            continue
        raw.append(
            {
                "year": year,
                "round": code,
                "metric": metric,
                "from": donor,
                "to": host,
                "area": area,
                "value": float(value),
            }
        )
    chosen: dict[tuple, str] = {}
    for item in raw:
        if item["metric"] == "requirement":
            continue
        key = (item["year"], item["from"], item["to"], item["area"] or "", item["metric"])
        current = chosen.get(key)
        if current is None or _prefer_report(item["round"], current):
            chosen[key] = item["round"]

    merged: dict[tuple, dict[str, Any]] = {}
    for item in raw:
        if item["metric"] != "requirement":
            key = (item["year"], item["from"], item["to"], item["area"] or "", item["metric"])
            if item["round"] != chosen.get(key):
                continue
        key = (item["year"], item["from"], item["to"], item["area"] or "")
        current = merged.setdefault(
            key,
            {
                "year": item["year"],
                "from": item["from"],
                "to": item["to"],
                "area": item["area"] or "",
                "requirement": 0.0,
                "funding": 0.0,
                "expenditure": 0.0,
            },
        )
        current[item["metric"]] += item["value"]
    figures = list(merged.values())
    for row in figures:
        for metric in ("requirement", "funding", "expenditure"):
            row[metric] = round(row[metric], 2)
    return figures


def _inform_payload() -> dict[str, Any]:
    path = _PLUGIN_DIR / "geo" / "inform_risk.json"
    try:
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _inform_edition() -> str:
    return str(_inform_payload().get("edition") or "INFORM Risk")


def inform_class(score: float) -> str:
    """Four INFORM classes. Scores under 3.5 are Low, including Very Low."""
    if score >= 6.5:
        return "very_high"
    if score >= 5:
        return "high"
    if score >= 3.5:
        return "medium"
    return "low"


def _coverage_points(
    figures: list[dict[str, Any]],
    countries: dict[str, Any],
) -> list[dict[str, Any]]:
    """One point per host country and year: requirement, funding met, INFORM class."""
    scores = _inform_payload().get("scores") or {}
    buckets: dict[tuple, dict[str, float]] = {}
    for row in figures:
        host = str(row.get("to") or "").strip().upper()
        year = row.get("year")
        if not host or year is None:
            continue
        bucket = buckets.setdefault(
            (int(year), host),
            {"requirement_total": 0.0, "requirement_areas": 0.0, "funding": 0.0},
        )
        if row.get("area"):
            bucket["requirement_areas"] += float(row.get("requirement") or 0)
        else:
            bucket["requirement_total"] += float(row.get("requirement") or 0)
            bucket["funding"] += float(row.get("funding") or 0)
    points = []
    for (year, host), bucket in buckets.items():
        requirement = bucket["requirement_total"] or bucket["requirement_areas"]
        if requirement <= 0:
            continue
        funding = bucket["funding"]
        score = scores.get(host)
        try:
            score_value = None if score is None else float(score)
        except (TypeError, ValueError):
            score_value = None
        info = countries.get(host) or {}
        points.append(
            {
                "year": year,
                "iso3": host,
                "name": info.get("name") or host,
                "requirement": round(requirement, 2),
                "funding": round(funding, 2),
                "met": round(funding / requirement * 100, 1),
                "inform_class": inform_class(score_value) if score_value is not None else "",
                "inform_score": score_value,
            }
        )
    points.sort(key=lambda point: (-point["year"], -point["requirement"], str(point["name"])))
    return points


def _add_reported_support_edges(
    master_rows: list[dict[str, Any]],
    *,
    edges: dict[tuple[str, str], set[str]],
    unresolved: set[str],
    rounds_seen: set[str],
    donor_iso3_by_name: dict[str, str],
    host_iso3s: set[str] | None,
) -> None:
    """Draw a support line when a society reports funding or expenditure for a country.

    The support matrix is not the only place bilateral support is recorded.
    For one society and country, the annual report replaces the mid-year
    report. A mid-year country with no annual-report row is kept.
    """
    pending: list[tuple[str, str, str]] = []
    for row in master_rows:
        if norm(row.get("Source")) != "pns data":
            continue
        if norm(row.get("Indicator")) not in {"funding", "expenditure"}:
            continue
        if not num(row.get("ValueNum")):
            continue
        code = str(row.get("Round") or "").strip()
        if round_calendar_year(code) is None or round_kind(code) != "report":
            continue
        host = str(row.get("ISO3") or "").strip().upper()
        donor_name = str(row.get("NS") or "").strip()
        donor = donor_iso3_by_name.get(norm(donor_name), "")
        if not donor:
            if donor_name:
                unresolved.add(donor_name)
            continue
        if not host or donor == host:
            continue
        if host_iso3s is not None and host not in host_iso3s:
            continue
        pending.append((donor, host, code))
    best: dict[tuple[str, str, int], str] = {}
    for donor, host, code in pending:
        year = round_calendar_year(code)
        if year is None:
            continue
        key = (donor, host, year)
        current = best.get(key)
        if current is None or _prefer_report(code, current):
            best[key] = code
    for donor, host, code in pending:
        year = round_calendar_year(code)
        if year is None or best.get((donor, host, year)) != code:
            continue
        edges.setdefault((donor, host), set()).add(code)
        rounds_seen.add(code)


def _touch_node(
    nodes: dict[str, dict[str, Any]],
    iso3: str,
    countries: dict[str, Any],
    pos: tuple[float, float],
) -> None:
    if iso3 in nodes:
        return
    info = countries.get(iso3) or {}
    nodes[iso3] = {
        "iso3": iso3,
        "iso2": str(info.get("iso2") or "").upper() or None,
        "name": info.get("name") or iso3,
        "region": info.get("region"),
        "lat": pos[0],
        "lng": pos[1],
        "out_weight": 0,
        "in_weight": 0,
        "role": "host",
    }


def _mapbox_token_configured() -> bool:
    """True when either the plugin key or ``MAPBOX_ACCESS_TOKEN`` is set.

    The token itself stays on the server. The browser only receives the proxy URL.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context() and (current_app.config.get("MAPBOX_ACCESS_TOKEN") or "").strip():
            return True
    except Exception:  # noqa: BLE001 - missing app context falls through to the plugin key
        pass
    try:
        from plugins.interactive_map.config import plugin_config as im_config

        return bool(im_config.is_provider_enabled("mapbox") and (im_config.get_api_key("mapbox") or "").strip())
    except Exception:  # noqa: BLE001 - plugin config is optional
        return False


def _tile_config() -> dict[str, Any]:
    """Map tiles, matching the IFRC Mapbox style the Interactive Map plugin uses.

    Falls back to OpenStreetMap when neither the plugin key nor
    ``MAPBOX_ACCESS_TOKEN`` is set, so the map still renders in a bare dev environment.
    """
    osm = {
        "provider": "openstreetmap",
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
        "max_zoom": 19,
        "subdomains": "abc",
    }
    if not _mapbox_token_configured():
        return osm
    attribution = "© Mapbox © OpenStreetMap"
    max_zoom = 22
    try:
        from plugins.interactive_map.config import plugin_config as im_config

        mb = im_config.get_provider_config("mapbox")
        attribution = mb.get("attribution") or attribution
        max_zoom = mb.get("max_zoom") or max_zoom
    except Exception:  # noqa: BLE001 - the env token is enough; style defaults still apply
        pass
    return {
        "provider": "mapbox",
        # Same server-side proxy the Interactive Map uses: the token
        # never reaches the browser. Raster tiles for this style are 512px.
        "url": "/admin/plugins/interactive_map/api/tiles/mapbox/{z}/{x}/{y}.png",
        "attribution": attribution,
        "max_zoom": max_zoom,
        "subdomains": "",
        "tile_size": 512,
        "zoom_offset": -1,
    }


def build_support_flows(*, region: str | None = None, public_tiles: bool = False) -> dict[str, Any]:
    """Flow-map payload for the whole network, or one region.

    Cached per database revision, like the other UPR Analysis extracts.
    """

    def _loader() -> dict[str, Any]:
        from plugins.upr.upr_data import build_upr_master

        master = build_upr_master()["data"]
        countries = load_countries()
        host_iso3s = iso3s_in_region(countries, region)
        payload = aggregate_flows(
            master,
            countries=countries,
            donor_iso3_by_name=_donor_name_to_iso3(),
            host_iso3s=host_iso3s,
        )
        payload["region"] = region or None
        payload["regions"] = sorted(
            {str(info.get("region")).strip() for info in countries.values() if info.get("region")}
        )
        return payload

    payload, _cache_hit = get_or_build_upr_payload(
        "support_flows", {"region": region or None, "series": "pns-flow-v9"}, _loader
    )
    # Tiles depend on runtime plugin config, not the DB revision — resolve fresh.
    tiles = _tile_config()
    # The admin Mapbox proxy requires a signed-in session. The public embed
    # uses its own tile route so a framed page can still load the IFRC style.
    if public_tiles and tiles.get("provider") == "mapbox":
        tiles = {**tiles, "url": "/upr/support-flow/tiles/{z}/{x}/{y}.png"}
    payload["tiles"] = tiles
    return payload


def mapbox_tile(z: int, x: int, y: int):
    """Fetch one IFRC Mapbox raster tile. Returns ``(body, mimetype)`` or an error code.

    The access token stays on the server. ``error`` is ``"unconfigured"``,
    ``"upstream"`` or ``"invalid"``.
    """
    import requests
    from flask import current_app

    if z < 0 or z > 22 or x >= 2**z or y >= 2**z:
        return None, None, "invalid"
    token = ""
    try:
        from plugins.interactive_map.config import plugin_config as im_config

        token = (im_config.get_api_key("mapbox") or "").strip()
    except Exception:  # noqa: BLE001
        token = ""
    if not token:
        token = (current_app.config.get("MAPBOX_ACCESS_TOKEN") or "").strip()
    if not token:
        return None, None, "unconfigured"
    style = (current_app.config.get("MAPBOX_STYLE_ID") or "go-ifrc/ckrfe16ru4c8718phmckdfjh0").strip()
    try:
        upstream = requests.get(
            f"https://api.mapbox.com/styles/v1/{style}/tiles/{z}/{x}/{y}",
            params={"access_token": token},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None, None, "upstream"
    if upstream.status_code != 200:
        return None, None, "upstream"
    mimetype = (upstream.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mimetype not in ("image/png", "image/jpeg", "image/webp"):
        return None, None, "upstream"
    return upstream.content, mimetype, None
