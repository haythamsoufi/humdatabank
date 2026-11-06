"""Read Part of Bundle from NationalSociety.category_text['Bundle']."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.core import Country
from app.models.organization import NationalSociety
from plugins.upr.bundle import BUNDLE_CATEGORY_KEY, bundle_category_name


def _bundle_text_key() -> str:
    """Same category_text key as UPR visual bundles (catalog name, usually Bundle)."""
    return bundle_category_name() or BUNDLE_CATEGORY_KEY


def bundle_value_from_texts(category_text: Any) -> str | None:
    """Read Bundle from category_text (case-insensitive key; not planning_bundle)."""
    texts = category_text if isinstance(category_text, dict) else {}
    if not texts:
        return None
    preferred = _bundle_text_key()
    for candidate in (preferred, "Bundle", BUNDLE_CATEGORY_KEY):
        raw = texts.get(candidate)
        if raw:
            return str(raw).strip() or None
    for stored_key, raw in texts.items():
        if str(stored_key).strip().lower() == BUNDLE_CATEGORY_KEY and raw:
            return str(raw).strip() or None
    return None


def planning_bundle_by_iso3() -> dict[str, str]:
    """ISO3 → Bundle label for active national societies."""
    rows = (
        db.session.query(Country.iso3, NationalSociety.category_text)
        .join(NationalSociety, NationalSociety.country_id == Country.id)
        .filter(NationalSociety.is_active.is_(True))
        .all()
    )
    out: dict[str, str] = {}
    for iso3, category_text in rows:
        code = (iso3 or "").strip().upper()
        if not code or len(code) != 3:
            continue
        value = bundle_value_from_texts(category_text)
        if value:
            out[code] = value
    return out
