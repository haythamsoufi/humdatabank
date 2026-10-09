from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Union
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from app.models import Country
from app import db


SANDBOX_COUNTRY_ISO3 = "TST"
SANDBOX_COUNTRY_NAME = "testland"
PART_OF_CATEGORY_CATALOG_KEY = "ns_part_of_category_catalog"
PART_OF_CATEGORY_CHECKBOX = "checkbox"
PART_OF_CATEGORY_TEXT = "text"
PART_OF_CATEGORY_TYPES = (PART_OF_CATEGORY_CHECKBOX, PART_OF_CATEGORY_TEXT)


def _normalize_part_of_category_name(name) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip()


def _normalize_part_of_category_type(category_type) -> str:
    kind = (category_type or PART_OF_CATEGORY_CHECKBOX).strip().lower()
    if kind not in PART_OF_CATEGORY_TYPES:
        return PART_OF_CATEGORY_CHECKBOX
    return kind


def _catalog_item(item) -> Optional[Tuple[str, str]]:
    if isinstance(item, str):
        label = _normalize_part_of_category_name(item)
        if not label:
            return None
        return label, PART_OF_CATEGORY_CHECKBOX
    if isinstance(item, dict):
        label = _normalize_part_of_category_name(item.get("name") or item.get("category_name") or "")
        if not label:
            return None
        return label, _normalize_part_of_category_type(item.get("type") or item.get("category_type"))
    return None


def load_part_of_category_catalog() -> Dict[str, str]:
    """Category name to type. Types are 'checkbox' or 'text'.

    Older catalogs stored plain names; those stay tick-box categories.
    """
    from app.models.system import SystemSettings

    raw = SystemSettings.get_value(PART_OF_CATEGORY_CATALOG_KEY, default=[])
    if not isinstance(raw, list):
        return {}
    catalog: Dict[str, str] = {}
    for item in raw:
        parsed = _catalog_item(item)
        if parsed:
            catalog[parsed[0]] = parsed[1]
    return catalog


def _save_part_of_category_catalog(catalog: Dict[str, str]) -> None:
    from app.models.system import SystemSettings

    payload = [
        {"name": name, "type": _normalize_part_of_category_type(kind)}
        for name, kind in sorted(catalog.items())
    ]
    SystemSettings.set_value(
        PART_OF_CATEGORY_CATALOG_KEY,
        payload,
        description="National Society categories (tick box or text) that stay available before any value is saved.",
    )


def remember_part_of_category(name: str, category_type: str = PART_OF_CATEGORY_CHECKBOX) -> None:
    """Persist a category so Add Category survives a reload before any value is saved."""
    label = _normalize_part_of_category_name(name)
    if not label:
        return
    catalog = load_part_of_category_catalog()
    if label in catalog:
        return
    catalog[label] = _normalize_part_of_category_type(category_type)
    _save_part_of_category_catalog(catalog)


def update_part_of_category_type(name: str, category_type: str) -> str:
    """Set an existing category's type. Returns the stored type."""
    label = _normalize_part_of_category_name(name)
    if not label:
        return ""
    kind = _normalize_part_of_category_type(category_type)
    catalog = load_part_of_category_catalog()
    if catalog.get(label) == kind:
        return kind
    catalog[label] = kind
    _save_part_of_category_catalog(catalog)
    return kind


def forget_part_of_category(name: str) -> None:
    label = _normalize_part_of_category_name(name)
    if not label:
        return
    catalog = load_part_of_category_catalog()
    if label not in catalog:
        return
    catalog.pop(label, None)
    _save_part_of_category_catalog(catalog)


def part_of_category_names_from_societies(societies) -> set:
    names = set()
    for ns in societies or []:
        part_of = getattr(ns, "part_of", None)
        if not part_of or not isinstance(part_of, list):
            continue
        for item in part_of:
            label = _normalize_part_of_category_name(item)
            if label:
                names.add(label)
    return names


def collect_part_of_category_definitions(societies=None) -> List[dict]:
    """Sorted categories with type. Tick-box names on societies stay checkbox if uncatalogued."""
    catalog = load_part_of_category_catalog()
    for name in part_of_category_names_from_societies(societies):
        catalog.setdefault(name, PART_OF_CATEGORY_CHECKBOX)
    return [
        {"name": name, "type": catalog[name]}
        for name in sorted(catalog)
    ]


def part_of_text_filter_key(category: str, value: str) -> str:
    """Stable map key for one text-category value in the assignment Part of filter."""
    return f"text:{category}\x1f{value}"


def collect_part_of_category_names(societies=None) -> List[str]:
    """Sorted tick-box category names. Text categories are excluded from membership filters."""
    return [
        item["name"]
        for item in collect_part_of_category_definitions(societies)
        if item["type"] == PART_OF_CATEGORY_CHECKBOX
    ]


def is_sandbox_country(country=None, *, name=None, iso3=None) -> bool:
    """True for the seeded Testland country (ISO3 TST)."""
    if country is not None:
        if name is None:
            name = getattr(country, "name", None)
        if iso3 is None:
            iso3 = getattr(country, "iso3", None)
    if str(iso3 or "").strip().upper() == SANDBOX_COUNTRY_ISO3:
        return True
    return str(name or "").strip().lower() == SANDBOX_COUNTRY_NAME


def exclude_sandbox_countries(query, country_model=Country):
    """Drop Testland from a query that already includes the Country table."""
    return query.filter(
        or_(
            country_model.iso3.is_(None),
            func.upper(country_model.iso3) != SANDBOX_COUNTRY_ISO3,
        ),
        func.lower(func.coalesce(country_model.name, "")) != SANDBOX_COUNTRY_NAME,
    )


def get_country_region_name(country) -> str:
    """Return the IFRC region label for a country."""
    if getattr(country, "secretariat_regional_office", None) is not None:
        return country.secretariat_regional_office.name
    return country.region if country.region else "Unassigned Region"


def get_part_of_category_data() -> Tuple[List[str], Dict[str, List[int]]]:
    """Return sorted Part of category names and category -> country_id mapping from NS records."""
    _, programs, mapping, _text_groups = get_countries_by_region_with_part_of()
    return programs, mapping


def _part_of_from_national_societies(country_id: int, national_societies, text_names=None) -> Tuple[set, Dict[str, set]]:
    """Extract tick-box Part of categories and mapping entries from a country's NS records."""
    skip = text_names or set()
    categories: set = set()
    category_to_countries: Dict[str, set] = defaultdict(set)
    for ns in national_societies or []:
        part_of = ns.part_of
        if not part_of or not isinstance(part_of, list):
            continue
        for item in part_of:
            if item and isinstance(item, str):
                category = item.strip()
                if category and category not in skip:
                    categories.add(category)
                    category_to_countries[category].add(country_id)
    return categories, category_to_countries


def _text_category_filter_entries(country_id: int, national_societies, text_names):
    """Map each non-empty text-category value to the countries that use it."""
    values_by_name = defaultdict(set)
    category_to_countries = defaultdict(set)
    if not text_names:
        return values_by_name, category_to_countries
    for ns in national_societies or []:
        texts = ns.category_text if isinstance(ns.category_text, dict) else {}
        for raw_name, raw_value in texts.items():
            name = _normalize_part_of_category_name(raw_name)
            if name not in text_names:
                continue
            value = str(raw_value).strip() if raw_value is not None else ""
            if not value:
                continue
            values_by_name[name].add(value)
            category_to_countries[part_of_text_filter_key(name, value)].add(country_id)
    return values_by_name, category_to_countries


def get_countries_by_region_with_part_of():
    """Load countries grouped by region and Part of filter data in one query batch.

    Returns:
        countries_by_region, tick-box category names, filter key -> country_ids,
        text groups ``[{name, options: [{label, key}]}]``.
    """
    countries_by_region = defaultdict(list)
    all_categories: set = set()
    category_to_countries: Dict[str, set] = defaultdict(set)
    text_values = defaultdict(set)
    catalog = load_part_of_category_catalog()
    text_names = {name for name, kind in catalog.items() if kind == PART_OF_CATEGORY_TEXT}

    all_countries = (
        Country.query.options(
            joinedload(Country.secretariat_regional_office),
            joinedload(Country.national_societies),
        )
        .order_by(Country.region, Country.name)
        .all()
    )
    for country in all_countries:
        region_name = get_country_region_name(country)
        countries_by_region[region_name].append(country)
        ns_categories, ns_mapping = _part_of_from_national_societies(
            country.id, country.national_societies, text_names
        )
        all_categories.update(ns_categories)
        for category, country_ids in ns_mapping.items():
            category_to_countries[category].update(country_ids)
        country_text_values, text_mapping = _text_category_filter_entries(
            country.id, country.national_societies, text_names
        )
        for name, values in country_text_values.items():
            text_values[name].update(values)
        for key, country_ids in text_mapping.items():
            category_to_countries[key].update(country_ids)

    all_categories.update(
        name for name, kind in catalog.items() if kind == PART_OF_CATEGORY_CHECKBOX
    )
    all_categories -= text_names
    programs = sorted(all_categories)
    mapping = {category: sorted(ids) for category, ids in category_to_countries.items()}
    text_groups = []
    for name in sorted(text_names):
        options = [
            {"label": value, "key": part_of_text_filter_key(name, value)}
            for value in sorted(text_values.get(name, ()))
        ]
        if options:
            text_groups.append({"name": name, "options": options})
    return countries_by_region, programs, mapping, text_groups


def get_countries_by_region():
    """Get all countries grouped by IFRC region.

    Returns:
        dict: A dictionary where keys are region names and values are lists of countries in that region.
    """
    countries_by_region = defaultdict(list)
    all_countries = (
        Country.query.options(joinedload(Country.secretariat_regional_office))
        .order_by(Country.region, Country.name)
        .all()
    )
    for country in all_countries:
        region_name = get_country_region_name(country)
        countries_by_region[region_name].append(country)
    return countries_by_region


def resolve_country_from_iso(iso2: Optional[str] = None, iso3: Optional[str] = None) -> Tuple[Optional[int], Optional[str]]:
    """
    Resolve ISO2 or ISO3 country code to country_id.

    Args:
        iso2: ISO2 country code (2 characters)
        iso3: ISO3 country code (3 characters)

    Returns:
        Tuple of (country_id, error_message)
        - If successful: (country_id, None)
        - If validation error: (None, error_message)
        - If country not found: (None, error_message)

    Usage:
        country_id, error = resolve_country_from_iso(iso2='US', iso3=None)
        if error:
            return api_error(error, 400 if 'Invalid' in error else 404)
    """
    # Validate that at least one code is provided
    if not iso2 and not iso3:
        return None, None  # No ISO codes provided, not an error

    # Normalize and validate ISO2
    if iso2:
        iso2 = iso2.strip().upper()
        if len(iso2) != 2:
            return None, "Invalid ISO2 code format. Must be exactly 2 characters."

    # Normalize and validate ISO3
    if iso3:
        iso3 = iso3.strip().upper()
        if len(iso3) != 3:
            return None, "Invalid ISO3 code format. Must be exactly 3 characters."

    # Build filters
    iso_filters = []
    if iso2:
        iso_filters.append(Country.iso2 == iso2)
    if iso3:
        iso_filters.append(Country.iso3 == iso3)

    if not iso_filters:
        return None, None

    # Query for matching country
    match = Country.query.filter(or_(*iso_filters)).first()
    if match:
        return match.id, None
    else:
        # Country not found for provided ISO codes
        codes = []
        if iso2:
            codes.append(f"ISO2: {iso2}")
        if iso3:
            codes.append(f"ISO3: {iso3}")
        return None, f"Country not found for provided ISO code(s): {', '.join(codes)}"