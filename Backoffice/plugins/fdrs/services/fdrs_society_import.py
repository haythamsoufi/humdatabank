"""Fill FDRS identity on ``national_societies`` from a legacy ``GET /api/entities/ns`` payload.

Run once before pointing the public site at the adapter. A society is a National
Society, so a DON code with no matching ``country`` is reported and not inserted.
Re-running only fills blanks unless ``overwrite`` is set.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from app.extensions import db
from app.models import Country, NationalSociety

# Legacy payload keys that are stored on the National Society. ISO codes stay on Country.
_NS_COLUMNS = {
    "name": "name",
    "zone_code": "fdrs_zone_code",
    "zone_name": "fdrs_zone_name",
    "latitude": "latitude",
    "longitude": "longitude",
    "admission_date": "admission_date",
    "admission_date_note": "admission_date_note",
    "currency_code": "currency_code",
    "search_string": "fdrs_search_string",
    "website": "website",
    "facebook": "facebook",
    "twitter": "twitter",
    "other_social": "other_social",
}

DEFAULT_LEGACY_BASE = "https://data-api.ifrc.org"
_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y")


def fetch_entities(base_url: Optional[str], api_key: Optional[str], *, timeout: int = 120) -> list[dict]:
    """Download the current ``entities/ns`` list from the legacy data API."""
    base = (base_url or DEFAULT_LEGACY_BASE).rstrip("/")
    url = f"{base}/api/entities/ns"
    if api_key:
        url += f"?apiKey={urllib.parse.quote(api_key)}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - operator-supplied base
        payload = json.loads(response.read().decode("utf-8"))
    return [row for row in payload or [] if isinstance(row, dict)]


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> Optional[date]:
    text = _text(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def entity_fields(entity: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Column values for one legacy entity, or ``None`` when it has no DON code."""
    don = _text(entity.get("KPI_DON_code") or entity.get("DonCode") or entity.get("doncode"))
    if not don:
        return None
    country_name = _text(entity.get("country"))
    zone = _text(entity.get("ZON_Code"))
    iso2 = _text(entity.get("iso_2") or entity.get("ISO2"))
    iso3 = _text(entity.get("iso_3") or entity.get("ISO3"))
    return {
        "don_code": don.upper(),
        "name": _text(entity.get("NSO_DON_name")) or country_name or don,
        "country_name": country_name,
        "iso2": iso2.upper()[:2] if iso2 else None,
        "iso3": iso3.upper()[:3] if iso3 else None,
        "zone_code": zone.upper()[:2] if zone else None,
        "zone_name": _text(entity.get("NSO_ZON_name")),
        "latitude": _float(entity.get("lat")),
        "longitude": _float(entity.get("long")),
        "admission_date": _date(entity.get("admission_date")),
        "admission_date_note": _text(entity.get("admission_date_note")),
        "currency_code": (_text(entity.get("cur_code")) or "")[:3] or None,
        "search_string": _text(entity.get("SearchString")),
        "website": _text(entity.get("Url") or entity.get("url")),
        "facebook": _text(entity.get("facebook")),
        "twitter": _text(entity.get("twitter")),
        "other_social": _text(entity.get("othersocial")),
    }


def _find_country(fields: Mapping[str, Any]) -> Optional[Country]:
    if fields.get("iso3"):
        country = Country.query.filter(Country.iso3 == fields["iso3"]).first()
        if country:
            return country
    if fields.get("iso2"):
        return Country.query.filter(Country.iso2 == fields["iso2"]).first()
    return None


def _find_society(don_code: str, country: Optional[Country]) -> Optional[NationalSociety]:
    society = NationalSociety.query.filter(NationalSociety.fdrs_don_code == don_code).first()
    if society is not None or country is None:
        return society
    return (
        NationalSociety.query.filter(
            NationalSociety.country_id == country.id,
            NationalSociety.fdrs_don_code.is_(None),
        )
        .order_by(NationalSociety.is_active.desc(), NationalSociety.id.asc())
        .first()
    )


def upsert_societies(
    entities: Iterable[Mapping[str, Any]],
    *,
    apply: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create or update National Society FDRS fields. ``apply=False`` computes the stats only."""
    stats: dict[str, Any] = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0, "unlinked": []}
    seen: set[str] = set()
    for entity in entities:
        fields = entity_fields(entity)
        if fields is None or fields["don_code"] in seen:
            stats["skipped"] += 1
            continue
        seen.add(fields["don_code"])
        country = _find_country(fields)
        if country is None:
            stats["unlinked"].append(fields["don_code"])
            continue

        society = _find_society(fields["don_code"], country)
        if society is None:
            stats["created"] += 1
            if apply:
                society = NationalSociety(country_id=country.id, name=fields["name"], fdrs_don_code=fields["don_code"])
                for source, column in _NS_COLUMNS.items():
                    if source == "name":
                        continue
                    setattr(society, column, fields.get(source))
                db.session.add(society)
            continue

        changed = False
        if not society.fdrs_don_code:
            changed = True
            if apply:
                society.fdrs_don_code = fields["don_code"]
        for source, column in _NS_COLUMNS.items():
            value = fields.get(source)
            if value is None:
                continue
            if overwrite or getattr(society, column) in (None, ""):
                if getattr(society, column) != value:
                    changed = True
                    if apply:
                        setattr(society, column, value)
        stats["updated" if changed else "unchanged"] += 1

    if apply:
        db.session.commit()
    return stats
