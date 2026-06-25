"""
IFRC Secretariat regional offices used to group countries (Africa, Americas, etc.).

Canonical regions live in ``secretariat_regional_offices``. Legacy ``country.region`` strings
are normalized via aliases when linking countries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.extensions import db

# Canonical IFRC statutory regions (SecretariatRegionalOffice rows).
IFRC_REGION_SEED: List[dict] = [
    {
        "code": "africa",
        "name": "Africa",
        "short_name": "Africa",
        "display_order": 1,
    },
    {
        "code": "americas",
        "name": "Americas",
        "short_name": "Americas",
        "display_order": 2,
    },
    {
        "code": "asia_pacific",
        "name": "Asia Pacific",
        "short_name": "Asia Pacific",
        "display_order": 3,
    },
    {
        "code": "europe_ca",
        "name": "Europe and Central Asia",
        "short_name": "Europe & CA",
        "display_order": 4,
        "short_name_translations": {
            "en": "Europe & CA",
            "fr": "Europe & CA",
            "es": "Europa & CA",
            "ar": "أوروبا وآسيا الوسطى",
            "zh": "欧洲和中亚",
            "ru": "Европа и ЦА",
            "hi": "यूरोप और मध्य एशिया",
        },
    },
    {
        "code": "mena",
        "name": "MENA",
        "short_name": "MENA",
        "display_order": 5,
    },
]

REGION_LABEL_ALIASES: Dict[str, str] = {
    "europe": "Europe and Central Asia",
    "europe & ca": "Europe and Central Asia",
    "europe & central asia": "Europe and Central Asia",
    "eu & ca": "Europe and Central Asia",
    "middle east and north africa": "MENA",
    "asia-pacific": "Asia Pacific",
    "asia pacific": "Asia Pacific",
}


def _region_translations_path() -> Path:
    from flask import current_app

    return Path(current_app.root_path).parent / "config" / "region_translations.json"


def _load_name_translations(canonical_name: str) -> Optional[dict]:
    path = _region_translations_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cfg = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cfg, dict):
        return None
    entry = cfg.get(canonical_name)
    return entry if isinstance(entry, dict) else None


def normalize_region_label(label: str | None) -> Optional[str]:
    """Map a free-text region label to a canonical IFRC region name."""
    if not label:
        return None
    raw = str(label).strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in REGION_LABEL_ALIASES:
        return REGION_LABEL_ALIASES[lowered]
    for seed in IFRC_REGION_SEED:
        if seed["name"].lower() == lowered:
            return seed["name"]
    return raw


def ensure_secretariat_regional_offices(session: Session | None = None) -> Dict[str, int]:
    """Ensure canonical IFRC regional offices exist. Returns mapping code -> id."""
    from app.models.organization import SecretariatRegionalOffice

    sess = session or db.session
    code_to_id: Dict[str, int] = {}

    for seed in IFRC_REGION_SEED:
        office = sess.query(SecretariatRegionalOffice).filter_by(code=seed["code"]).one_or_none()
        if office is None:
            office = sess.query(SecretariatRegionalOffice).filter_by(name=seed["name"]).one_or_none()
        if office is None:
            translations = _load_name_translations(seed["name"])
            office = SecretariatRegionalOffice(
                code=seed["code"],
                name=seed["name"],
                short_name=seed.get("short_name"),
                name_translations=translations,
                short_name_translations=seed.get("short_name_translations"),
                display_order=seed.get("display_order", 0),
                is_active=True,
            )
            sess.add(office)
            sess.flush()
        else:
            if office.code != seed["code"]:
                office.code = seed["code"]
            if not office.short_name and seed.get("short_name"):
                office.short_name = seed["short_name"]
            if not office.name_translations:
                translations = _load_name_translations(seed["name"])
                if translations:
                    office.name_translations = translations
            if not office.short_name_translations and seed.get("short_name_translations"):
                office.short_name_translations = seed["short_name_translations"]
            if office.display_order is None:
                office.display_order = seed.get("display_order", 0)
        code_to_id[seed["code"]] = office.id

    return code_to_id


def resolve_secretariat_regional_office_by_label(
    label: str | None,
    session: Session | None = None,
) -> Optional["SecretariatRegionalOffice"]:
    """Resolve a region label to a ``SecretariatRegionalOffice`` row."""
    from app.models.organization import SecretariatRegionalOffice

    canonical = normalize_region_label(label)
    if not canonical:
        return None

    sess = session or db.session
    ensure_secretariat_regional_offices(sess)

    office = sess.query(SecretariatRegionalOffice).filter(
        SecretariatRegionalOffice.name.ilike(canonical),
    ).one_or_none()
    return office


def sync_country_region_fields(country) -> None:
    """Keep denormalized ``country.region`` aligned with the linked regional office."""
    office = getattr(country, "secretariat_regional_office", None)
    if office is not None:
        country.region = office.name
    elif getattr(country, "secretariat_regional_office_id", None):
        from app.models.organization import SecretariatRegionalOffice

        office = db.session.get(SecretariatRegionalOffice, country.secretariat_regional_office_id)
        if office is not None:
            country.region = office.name


def assign_country_secretariat_regional_office(
    country,
    label: str | None,
) -> Optional["SecretariatRegionalOffice"]:
    """Resolve label and assign ``secretariat_regional_office_id`` on a country."""
    if label:
        office = resolve_secretariat_regional_office_by_label(label)
        if office is not None:
            country.secretariat_regional_office_id = office.id
            country.secretariat_regional_office = office
            country.region = office.name
        return office

    sync_country_region_fields(country)
    return getattr(country, "secretariat_regional_office", None)
