from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Union
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from app.models import Country
from app import db


def get_country_region_name(country) -> str:
    """Return the IFRC region label for a country."""
    if getattr(country, "secretariat_regional_office", None) is not None:
        return country.secretariat_regional_office.name
    return country.region if country.region else "Unassigned Region"


def get_part_of_category_data() -> Tuple[List[str], Dict[str, List[int]]]:
    """Return sorted Part of category names and category -> country_id mapping from NS records."""
    _, programs, mapping = get_countries_by_region_with_part_of()
    return programs, mapping


def _part_of_from_national_societies(country_id: int, national_societies) -> Tuple[set, Dict[str, set]]:
    """Extract Part of categories and mapping entries from a country's NS records."""
    categories: set = set()
    category_to_countries: Dict[str, set] = defaultdict(set)
    for ns in national_societies or []:
        part_of = ns.part_of
        if not part_of or not isinstance(part_of, list):
            continue
        for item in part_of:
            if item and isinstance(item, str):
                category = item.strip()
                if category:
                    categories.add(category)
                    category_to_countries[category].add(country_id)
    return categories, category_to_countries


def get_countries_by_region_with_part_of() -> Tuple[dict, List[str], Dict[str, List[int]]]:
    """Load countries grouped by region and Part of filter data in one query batch.

    Returns:
        countries_by_region, sorted part_of category names, category -> country_ids mapping
    """
    countries_by_region = defaultdict(list)
    all_categories: set = set()
    category_to_countries: Dict[str, set] = defaultdict(set)

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
        ns_categories, ns_mapping = _part_of_from_national_societies(country.id, country.national_societies)
        all_categories.update(ns_categories)
        for category, country_ids in ns_mapping.items():
            category_to_countries[category].update(country_ids)

    programs = sorted(all_categories)
    mapping = {category: sorted(ids) for category, ids in category_to_countries.items()}
    return countries_by_region, programs, mapping


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