"""Narrative participation for Unified Plans and Reports — Analysis tab.

The Analysis tab's coverage series (:mod:`plugins.upr.impact`) only knows the
**data** half of a round: a National Society "participates" when it has an
assignment / submission in the databank. The **narrative** half (the Unified
Plan / Report PDF) lives in the IFRC GO document store and has two stages:

* **Internal narrative** — the document a country submits to the Secretariat
  (``/Api/FedNetAppeals``, types 1844 / 10008 / 10010). A country that hands in
  a narrative is participating even if it never completes the data form.
* **Public narrative** — the document published on the public site
  (``/Api/PublicSiteAppeals``, types 1851 / 10009 / 10011); the same catalogue
  the mobile app and the documents gallery show.

Both feeds are parsed with one rule set (a port of the Power Query used by the
UPR team) so a country/round is counted once per stage:

* hidden rows, rows without a country, and Switzerland (Geneva Secretariat) are dropped;
* the round is the document family (``P`` / ``MYR`` / ``AR``) plus the first
  year 2023–2030 found in ``AppealOrigType`` or ``BaseAppealNumber``;
* only *country* appeals are kept — the two characters after ``MAA``/``MGR`` in
  the appeal number must not contain a digit (regional appeals such as
  ``MAA50001`` are excluded);
* one document per ``ISO3 + round`` (first row wins).

:func:`aggregate_participation` is pure (no database / network) so it can be
unit tested with synthetic rows; :func:`build_narrative_participation` wires it
to the live sources.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable, Mapping

import requests

from plugins.upr.impact import round_sort_key

logger = logging.getLogger(__name__)

FEDNET_APPEALS_URL = "https://go-api.ifrc.org/Api/FedNetAppeals"
PUBLIC_APPEALS_URL = "https://go-api.ifrc.org/Api/PublicSiteAppeals"

# AppealsTypeId -> round family.
INTERNAL_TYPE_PREFIX: dict[int, str] = {1844: "P", 10010: "AR", 10008: "MYR"}
PUBLIC_TYPE_PREFIX: dict[int, str] = {1851: "P", 10011: "AR", 10009: "MYR"}

_EXCLUDED_ISO2 = frozenset({"CH"})
_YEARS = tuple(range(2023, 2031))
TRACKS = ("P", "MYR", "AR")

_SUBMITTED_STATUSES = frozenset({"submitted", "approved", "validated"})
# A round is "in progress" when far fewer countries took part than in the
# fullest round of the same family (plans vs plans, annual vs annual).
_MATURE_RATIO = 0.6

_CACHE_TTL_SECONDS = 10 * 60
_FETCH_TIMEOUT_SECONDS = 60

_ROUND_RE = re.compile(r"^(P|MYR|AR)(\d{2})$")


class NarrativeSourceUnavailable(Exception):
    """An IFRC document feed could not be loaded. ``code`` is a short reason."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


# ---------------------------------------------------------------------------
# Parsing (pure)
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def round_year(*fields: Any) -> int | None:
    """First year (2023 → 2030) that appears in any of ``fields``."""
    haystacks = [_text(f) for f in fields]
    for year in _YEARS:
        token = str(year)
        if any(token in hay for hay in haystacks):
            return year
    return None


def is_country_appeal_number(base_appeal_number: Any) -> bool:
    """True for country appeals (``…MAAxx###``), False for regional / global ones.

    Ports the Power Query ``iso2_from_code`` step: take the 8 characters from the
    first ``MAA`` (else ``MGR``) tag, read the two after the tag, and reject the
    row when they contain a digit. A missing number or tag also rejects the row.
    """
    if base_appeal_number is None:
        return False
    text = str(base_appeal_number)
    pos = text.find("MAA") if "MAA" in text else text.find("MGR")
    if pos == -1:
        return False
    tag_code = text[pos : pos + 8][3:5]
    return not any(ch.isdigit() for ch in tag_code)


def _parse_date(raw: Any) -> str | None:
    text = _text(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def parse_unified_documents(
    items: Any,
    *,
    type_prefix: Mapping[int, str],
    iso2_to_iso3: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Reduce a FedNet / PublicSite appeals payload to one record per ``ISO3 + round``."""
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("Hidden") is True:
            continue
        type_id = _as_int(item.get("AppealsTypeId"))
        prefix = type_prefix.get(type_id) if type_id is not None else None
        if prefix is None:
            continue
        iso2 = _text(item.get("LocationCountryCode")).strip().upper()
        if not iso2 or iso2 in _EXCLUDED_ISO2:
            continue
        year = round_year(item.get("AppealOrigType"), item.get("BaseAppealNumber"))
        if year is None:
            continue
        iso3 = iso2_to_iso3.get(iso2)
        if not iso3:
            continue
        if not is_country_appeal_number(item.get("BaseAppealNumber")):
            continue
        code = f"{prefix}{year % 100:02d}"
        key = f"{iso3}{code}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "uprcode": key,
                "iso3": iso3,
                "iso2": iso2,
                "round": code,
                "type_id": type_id,
                "title": " ".join(_text(item.get("AppealsName")).split()) or None,
                "appeal_number": _text(item.get("BaseAppealNumber")) or None,
                "date": _parse_date(item.get("AppealsDate")),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Aggregation (pure)
# ---------------------------------------------------------------------------


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _prefix(code: str) -> str:
    match = _ROUND_RE.match(code or "")
    return match.group(1) if match else ""


def _year(code: str) -> int | None:
    match = _ROUND_RE.match(code or "")
    return 2000 + int(match.group(2)) if match else None


def _by_round(rows: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in rows:
        code = row.get("round")
        iso3 = row.get("iso3")
        if code and iso3:
            out.setdefault(code, set()).add(iso3)
    return out


def _data_sets(
    submissions: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(assigned, submitted) country sets per round from the data assignments."""
    assigned: dict[str, set[str]] = {}
    submitted: dict[str, set[str]] = {}
    for row in submissions:
        code = row.get("Round")
        iso3 = str(row.get("ISO3") or "").strip().upper()
        if not code or not iso3:
            continue
        assigned.setdefault(code, set()).add(iso3)
        if _norm(row.get("status")) in _SUBMITTED_STATUSES:
            submitted.setdefault(code, set()).add(iso3)
    return assigned, submitted


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100.0, 1) if whole else None


def _round_record(
    code: str,
    internal: set[str],
    public: set[str],
    data: set[str],
    assigned: set[str],
    universe: int,
) -> dict[str, Any]:
    anyone = internal | data
    published = public & internal
    return {
        "round": code,
        "year": _year(code),
        "internal": len(internal),
        "public": len(public),
        "data_assigned": len(assigned),
        "data_submitted": len(data),
        "any": len(anyone),
        "both": len(internal & data),
        "narrative_only": len(internal - data),
        "data_only": len(data - internal),
        "published": len(published),
        "unpublished": len(internal - public),
        "public_only": len(public - internal),
        "participation_pct": _pct(len(anyone), universe),
        "publication_pct": _pct(len(published), len(internal)),
    }


def _round_countries(
    catalog: Mapping[str, Mapping[str, Any]],
    *,
    internal: set[str],
    public: set[str],
    data: set[str],
    previous: set[str] | None,
    baseline: bool = False,
    include_new: bool = True,
) -> list[dict[str, Any]]:
    """Per-country flags for one round, so a year row can expand in the table."""
    anyone = internal | data
    scope = set(anyone) | set(public)
    if previous is not None:
        scope |= previous
    rows: list[dict[str, Any]] = []
    for iso in scope:
        info = catalog.get(iso) or {}
        has_internal = iso in internal
        has_public = iso in public
        has_data = iso in data
        has_any = iso in anyone
        row: dict[str, Any] = {
            "iso3": iso,
            "country": info.get("name") or iso,
            "data_submitted": int(has_data),
            "internal": int(has_internal),
            "public": int(has_public),
            "any": int(has_any),
            "both": int(has_internal and has_data),
            "narrative_only": int(has_internal and not has_data),
            "data_only": int(has_data and not has_internal),
            "published": int(has_public and has_internal),
            "unpublished": int(has_internal and not has_public),
            "public_only": int(has_public and not has_internal),
        }
        if baseline:
            row["baseline"] = int(has_any)
        if previous is not None:
            in_prev = iso in previous
            row["retained"] = int(in_prev and has_any)
            if include_new:
                row["new"] = int(has_any and not in_prev)
            row["lapsed"] = int(in_prev and not has_any)
        rows.append(row)
    rows.sort(key=lambda item: (str(item["country"]).lower(), item["iso3"]))
    return rows


def _names(iso3s: Iterable[str], countries: Mapping[str, Mapping[str, Any]]) -> list[dict[str, str]]:
    rows = [
        {
            "iso3": iso3,
            "name": (countries.get(iso3) or {}).get("name") or iso3,
            "region": (countries.get(iso3) or {}).get("region") or "",
        }
        for iso3 in iso3s
    ]
    rows.sort(key=lambda r: (r["name"].lower(), r["iso3"]))
    return rows


def _delta(latest: Mapping[str, Any] | None, previous: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "latest": latest.get(key) if latest else None,
        "latest_year": latest.get("year") if latest else None,
        "latest_round": latest.get("round") if latest else None,
        "previous": previous.get(key) if previous else None,
        "previous_year": previous.get("year") if previous else None,
        "change_pct": None,
    }
    if latest and previous:
        prev = previous.get(key) or 0
        cur = latest.get(key) or 0
        if prev:
            out["change_pct"] = round((cur - prev) / prev * 100.0, 1)
    return out


def aggregate_participation(
    *,
    internal: Iterable[Mapping[str, Any]],
    public: Iterable[Mapping[str, Any]],
    submissions: Iterable[Mapping[str, Any]],
    countries: Mapping[str, Mapping[str, Any]],
    region: str | None = None,
) -> dict[str, Any]:
    """Combine data, internal-narrative and public-narrative participation.

    A National Society **participates** in a round when it has an internal
    narrative document *or* a submitted data form. ``internal``/``public`` are
    :func:`parse_unified_documents` records, ``submissions`` are the UPR
    submission rows and ``countries`` maps ISO3 -> ``{name, region}``.
    """
    allowed: set[str] | None = None
    if region:
        wanted = region.strip().lower()
        allowed = {iso3 for iso3, c in countries.items() if _norm(c.get("region")) == wanted}

    def keep(iso3: str) -> bool:
        return allowed is None or iso3 in allowed

    internal_by = {c: {i for i in s if keep(i)} for c, s in _by_round(internal).items()}
    public_by = {c: {i for i in s if keep(i)} for c, s in _by_round(public).items()}
    assigned_raw, submitted_raw = _data_sets(submissions)
    assigned_by = {c: {i for i in s if keep(i)} for c, s in assigned_raw.items()}
    data_by = {c: {i for i in s if keep(i)} for c, s in submitted_raw.items()}

    rounds = sorted(
        {c for d in (internal_by, public_by, assigned_by, data_by) for c in d if _ROUND_RE.match(c)},
        key=round_sort_key,
    )
    empty: set[str] = set()

    # Everyone seen participating (data submitted or narrative) in any round.
    universe_set: set[str] = set()
    for code in rounds:
        universe_set |= internal_by.get(code, empty) | public_by.get(code, empty) | data_by.get(code, empty)
    universe = len(universe_set)

    records = {
        code: _round_record(
            code,
            internal_by.get(code, empty),
            public_by.get(code, empty),
            data_by.get(code, empty),
            assigned_by.get(code, empty),
            universe,
        )
        for code in rounds
    }
    anyone_by = {code: internal_by.get(code, empty) | data_by.get(code, empty) for code in rounds}

    tracks: dict[str, list[dict[str, Any]]] = {}
    in_progress: list[str] = []
    records_low: dict[str, bool] = {}
    for prefix in TRACKS:
        family = [c for c in rounds if _prefix(c) == prefix]
        if not family:
            tracks[prefix] = []
            continue
        fullest = max(records[c]["any"] for c in family)
        series: list[dict[str, Any]] = []
        previous_code: str | None = None
        for code in family:
            rec = dict(records[code])
            # Chronological position across round types (plan, mid-year, annual).
            sort_year, sort_kind, _ = round_sort_key(code)
            rec["order"] = sort_year * 10 + sort_kind
            # ``low`` = far fewer participants than the fullest round of this
            # family: either a round still collecting (the newest one) or an old
            # round the sources only partly cover. Neither supports churn figures.
            low = bool(fullest) and rec["any"] / fullest < _MATURE_RATIO
            rec["low_participation"] = low
            rec["in_progress"] = low and code == family[-1]
            if rec["in_progress"]:
                in_progress.append(code)
            # Without data assignments (rounds that pre-date the databank) the
            # narrative/data split is meaningless, so it is left blank.
            if rec["in_progress"]:
                # Documents are still being published; a rate now would mislead.
                rec["publication_pct"] = None
            # Churn needs a well-covered current round. "Carried on" and
            # "dropped out" only depend on countries visible in the previous
            # round, so they hold even if it is partly covered; "joined" does
            # not (countries the previous round simply missed would look new),
            # so it needs both rounds well covered. The drill-down follows the
            # same rule as the totals.
            comparable = previous_code is not None and not low
            full_comparison = comparable and not records_low.get(previous_code)
            rec["countries"] = _round_countries(
                countries,
                internal=internal_by.get(code, empty),
                public=public_by.get(code, empty),
                data=data_by.get(code, empty),
                previous=anyone_by[previous_code] if comparable else None,
                baseline=previous_code is None,
                include_new=full_comparison,
            )
            rec["data_available"] = rec["data_assigned"] > 0
            if not rec["data_available"]:
                rec["both"] = rec["narrative_only"] = rec["data_only"] = None
            if comparable:
                prev_set = anyone_by[previous_code]
                cur_set = anyone_by[code]
                rec["retained"] = len(prev_set & cur_set)
                rec["new"] = len(cur_set - prev_set) if full_comparison else None
                rec["lapsed"] = len(prev_set - cur_set)
            else:
                rec["retained"] = rec["new"] = rec["lapsed"] = None
            # The first round of a track has nothing to compare with; its
            # participant count is the baseline the chart shows in grey.
            rec["baseline"] = rec["any"] if previous_code is None else None
            records_low[code] = low
            series.append(rec)
            previous_code = code
        tracks[prefix] = series

    # Headline + gaps use the latest *settled* round of each track.
    headline: dict[str, Any] = {}
    gaps: dict[str, Any] = {}
    for prefix, series in tracks.items():
        settled = [r for r in series if not r["low_participation"]]
        latest = settled[-1] if settled else None
        previous = settled[-2] if len(settled) >= 2 else None
        headline[prefix] = {
            "any": _delta(latest, previous, "any"),
            "internal": _delta(latest, previous, "internal"),
            "public": _delta(latest, previous, "public"),
            "narrative_only": _delta(latest, previous, "narrative_only"),
            "publication_pct": _delta(latest, previous, "publication_pct"),
        }
        if not latest:
            continue
        code = latest["round"]
        prev_year_code = next((r["round"] for r in series if r["year"] == (latest["year"] or 0) - 1), None)
        # Valid even when the previous year is partly covered: it only lists
        # countries that were seen there and are missing now.
        lapsed = anyone_by[prev_year_code] - anyone_by[code] if prev_year_code else empty
        internal_set = internal_by.get(code, empty)
        data_set = data_by.get(code, empty)
        public_set = public_by.get(code, empty)
        gaps[prefix] = {
            "round": code,
            "year": latest["year"],
            "narrative_only": _names(internal_set - data_set, countries),
            "data_only": _names(data_set - internal_set, countries),
            "unpublished": _names(internal_set - public_set, countries),
            "lapsed": _names(lapsed, countries),
        }

    matrix = []
    for iso3 in sorted(universe_set, key=lambda i: (((countries.get(i) or {}).get("name") or i).lower(), i)):
        cells: dict[str, str] = {}
        for code in rounds:
            flags = (
                ("D" if iso3 in data_by.get(code, empty) else "")
                + ("N" if iso3 in internal_by.get(code, empty) else "")
                + ("P" if iso3 in public_by.get(code, empty) else "")
            )
            if flags:
                cells[code] = flags
        info = countries.get(iso3) or {}
        matrix.append(
            {
                "iso3": iso3,
                "name": info.get("name") or iso3,
                "region": info.get("region") or "",
                "rounds": cells,
                "rounds_active": len(cells),
            }
        )

    return {
        "rounds": rounds,
        "universe": universe,
        "tracks": tracks,
        "in_progress": sorted(in_progress, key=round_sort_key),
        "headline": headline,
        "gaps": gaps,
        "overview": _overview(rounds, tracks, anyone_by, records_low, universe_set, countries),
        "matrix": matrix,
        "region": region or None,
    }


def _overview(
    rounds: list[str],
    tracks: Mapping[str, list[dict[str, Any]]],
    anyone_by: Mapping[str, set[str]],
    records_low: Mapping[str, bool],
    universe_set: set[str],
    countries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Cross-round view: plan-to-report completion and how consistently countries take part.

    Only *settled* rounds count (well covered by the sources and not still open),
    so a country is not penalised for a round the data cannot see yet.
    """
    settled = [c for c in rounds if not records_low.get(c)]
    depth: dict[str, int] = {iso3: 0 for iso3 in universe_set}
    for code in settled:
        for iso3 in anyone_by.get(code, set()):
            if iso3 in depth:
                depth[iso3] += 1
    total = len(settled)

    histogram: dict[int, int] = {}
    for count in depth.values():
        histogram[count] = histogram.get(count, 0) + 1
    engagement = [{"rounds": n, "countries": histogram.get(n, 0)} for n in range(total + 1)]

    always = {i for i, n in depth.items() if total and n == total}
    never = {i for i, n in depth.items() if n == 0}
    intermittent = set(depth) - always - never

    # Plan -> report completion for the latest year whose plan and annual
    # report are both settled.
    cycle: dict[str, Any] | None = None
    plans = {r["year"]: r for r in tracks.get("P", []) if not r["low_participation"]}
    reports = {r["year"]: r for r in tracks.get("AR", []) if not r["low_participation"]}
    shared = sorted(set(plans) & set(reports))
    if shared:
        year = shared[-1]
        plan_set = anyone_by[plans[year]["round"]]
        report_set = anyone_by[reports[year]["round"]]
        done = plan_set & report_set
        cycle = {
            "year": year,
            "plan_round": plans[year]["round"],
            "report_round": reports[year]["round"],
            "plan": len(plan_set),
            "report": len(report_set),
            "both": len(done),
            "completion_pct": _pct(len(done), len(plan_set)),
            "planned_not_reported": _names(plan_set - report_set, countries),
        }

    return {
        "settled_rounds": settled,
        "engagement": engagement,
        "cycle": cycle,
        "gaps": {
            "always": _names(always, countries),
            "intermittent": _names(intermittent, countries),
            "never": _names(never, countries),
        },
    }


# ---------------------------------------------------------------------------
# Live sources
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, list[Any]]] = {}
_cache_lock = Lock()
_fetch_lock = Lock()


def reset_narrative_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


def _cached(key: str, *, fresh_only: bool) -> list[Any] | None:
    with _cache_lock:
        hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, payload = hit
    if fresh_only and time.monotonic() - stored_at >= _CACHE_TTL_SECONDS:
        return None
    return payload


def _fetch_appeals(url: str) -> list[Any]:
    from app.routes.ai_documents.helpers import _get_ifrc_basic_auth

    auth = _get_ifrc_basic_auth()
    if auth is None:
        raise NarrativeSourceUnavailable("credentials")
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"},
            auth=auth,
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        logger.warning("UPR narrative source HTTP %s", status)
        raise NarrativeSourceUnavailable("auth" if status in (401, 403) else "upstream") from exc
    except (requests.RequestException, ValueError) as exc:
        logger.warning("UPR narrative source fetch failed: %s", type(exc).__name__)
        raise NarrativeSourceUnavailable("upstream") from exc
    if not isinstance(payload, list):
        raise NarrativeSourceUnavailable("upstream")
    return payload


def load_appeals(key: str, url: str) -> list[Any]:
    """Raw appeals list, cached for a few minutes; serves stale data if IFRC is down."""
    fresh = _cached(key, fresh_only=True)
    if fresh is not None:
        return fresh
    with _fetch_lock:
        fresh = _cached(key, fresh_only=True)
        if fresh is not None:
            return fresh
        try:
            payload = _fetch_appeals(url)
        except NarrativeSourceUnavailable:
            stale = _cached(key, fresh_only=False)
            if stale is not None:
                logger.warning("UPR narrative serving stale %s feed after refresh failed", key)
                return stale
            raise
        with _cache_lock:
            _cache[key] = (time.monotonic(), payload)
        return payload


def _load_countries() -> dict[str, dict[str, Any]]:
    from app.models import Country

    rows = Country.query.with_entities(Country.iso2, Country.iso3, Country.name, Country.region).all()
    return {
        str(iso3).upper(): {"iso2": (iso2 or "").upper() or None, "name": name, "region": region}
        for iso2, iso3, name, region in rows
        if iso3
    }


def _load_data_submissions() -> list[dict[str, Any]]:
    """Slim (round, country, status) rows, cached with the other UPR extracts."""
    from plugins.upr.api_cache import get_or_build_upr_payload
    from plugins.upr.upr_data import build_upr_submissions

    def _loader() -> list[dict[str, Any]]:
        return [
            {"Round": r.get("Round"), "ISO3": r.get("ISO3"), "status": r.get("status")}
            for r in build_upr_submissions()["data"]
        ]

    rows, _hit = get_or_build_upr_payload("impact-narrative-submissions", {"v": 1}, _loader)
    return rows


_WARNING_TEXT = {
    "credentials": "IFRC document API credentials are not configured.",
    "auth": "IFRC rejected the document API credentials.",
    "upstream": "The IFRC document API could not be reached.",
}


def build_narrative_participation(*, region: str | None = None) -> dict[str, Any]:
    """Live narrative-participation analysis for the whole network, or one region.

    A failing document feed degrades gracefully: that stage is reported as
    unavailable (see ``sources``) and the rest is still returned.
    """
    countries = _load_countries()
    iso2_to_iso3 = {c["iso2"]: iso3 for iso3, c in countries.items() if c.get("iso2")}

    sources: dict[str, dict[str, Any]] = {}
    parsed: dict[str, list[dict[str, Any]]] = {}
    for name, url, mapping in (
        ("internal", FEDNET_APPEALS_URL, INTERNAL_TYPE_PREFIX),
        ("public", PUBLIC_APPEALS_URL, PUBLIC_TYPE_PREFIX),
    ):
        try:
            raw = load_appeals(name, url)
            parsed[name] = parse_unified_documents(raw, type_prefix=mapping, iso2_to_iso3=iso2_to_iso3)
            sources[name] = {"available": True, "documents": len(parsed[name])}
        except NarrativeSourceUnavailable as exc:
            parsed[name] = []
            sources[name] = {
                "available": False,
                "documents": 0,
                "message": _WARNING_TEXT.get(exc.code, _WARNING_TEXT["upstream"]),
            }

    payload = aggregate_participation(
        internal=parsed["internal"],
        public=parsed["public"],
        submissions=_load_data_submissions(),
        countries=countries,
        region=region,
    )
    payload["sources"] = sources
    return payload
