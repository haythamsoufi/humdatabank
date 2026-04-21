from collections import defaultdict
from typing import Optional, Tuple, Union
from sqlalchemy import or_
from app.models import Country
from app import db


def get_countries_by_region():
    """Get all countries grouped by region.

    Returns:
        dict: A dictionary where keys are region names and values are lists of countries in that region.
    """
    countries_by_region = defaultdict(list)
    all_countries = Country.query.order_by(Country.region, Country.name).all()
    for country in all_countries:
        region_name = country.region if country.region else "Unassigned Region"
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
