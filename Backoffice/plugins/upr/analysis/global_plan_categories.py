"""National Society part_of categories used by Global Plan prioritisation.

ODA and NSIF are checkbox categories on ``NationalSociety.part_of``, managed
under Organization admin. Names are resolved case-insensitively from the
part-of catalog (e.g. ``NSIF``, ``NSIF focus``, ``ODA``).
"""

from __future__ import annotations

from typing import Any, Iterable

from app.extensions import db
from app.models.core import Country
from app.models.organization import NationalSociety
from app.utils.organization.country_utils import load_part_of_category_catalog


def _norm_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def resolve_category_names(*, needles: Iterable[str]) -> list[str]:
    """Catalog category names whose normalized label contains any needle."""
    wanted = [_norm_label(n) for n in needles if _norm_label(n)]
    if not wanted:
        return []
    catalog = load_part_of_category_catalog()
    found: list[str] = []
    for name in catalog:
        label = _norm_label(name)
        if any(needle in label for needle in wanted):
            found.append(name)
    # Also accept exact needle matches even if not yet in the catalog.
    for needle in wanted:
        if not any(_norm_label(n) == needle or needle in _norm_label(n) for n in found):
            found.append(needle)
    return found


def nsif_category_names() -> list[str]:
    return resolve_category_names(needles=("nsif", "nsif focus"))


def oda_category_names() -> list[str]:
    return resolve_category_names(needles=("oda",))


def _part_of_set(part_of: Any) -> set[str]:
    if not isinstance(part_of, list):
        return set()
    return {_norm_label(item) for item in part_of if str(item or "").strip()}


def _matches(part_of: set[str], names: Iterable[str]) -> bool:
    targets = {_norm_label(n) for n in names}
    if not targets or not part_of:
        return False
    for label in part_of:
        if label in targets:
            return True
        if any(t in label or label in t for t in targets):
            return True
    return False


def load_ns_category_flags() -> dict[str, dict[str, Any]]:
    """ISO3 → ``{country, nsif, oda, part_of}`` for active national societies.

    When several societies share a country, flags are OR-ed.
    """
    rows = (
        db.session.query(
            Country.iso3,
            Country.name,
            NationalSociety.part_of,
            NationalSociety.name,
        )
        .join(NationalSociety, NationalSociety.country_id == Country.id)
        .filter(NationalSociety.is_active.is_(True))
        .all()
    )
    nsif_names = nsif_category_names()
    oda_names = oda_category_names()
    out: dict[str, dict[str, Any]] = {}
    for iso3, country, part_of, ns_name in rows:
        code = str(iso3 or "").strip().upper()
        if len(code) != 3:
            continue
        labels = _part_of_set(part_of)
        rec = out.setdefault(
            code,
            {
                "iso3": code,
                "country": country or code,
                "nsif": False,
                "oda": False,
                "part_of": sorted(labels),
                "societies": [],
            },
        )
        if country:
            rec["country"] = country
        rec["nsif"] = bool(rec["nsif"] or _matches(labels, nsif_names))
        rec["oda"] = bool(rec["oda"] or _matches(labels, oda_names))
        rec["part_of"] = sorted(set(rec["part_of"]) | labels)
        if ns_name:
            rec["societies"].append(str(ns_name))
    return out


def has_flag(flags: dict[str, dict[str, Any]], iso3: str, key: str) -> bool:
    rec = flags.get(str(iso3 or "").strip().upper()) or {}
    return bool(rec.get(key))
