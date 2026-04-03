"""
Country Service - Centralized service for country-related database operations.

This service provides a unified interface for country queries, replacing
direct database queries in route handlers.
"""

from typing import Optional
from app.models import Country
from app import db


class CountryService:
    """Service class for country operations."""

    @staticmethod
    def get_by_id(country_id: int) -> Optional[Country]:
        """Get a country by ID.

        Args:
            country_id: Country ID

        Returns:
            Country instance or None if not found
        """
        return Country.query.get(country_id)

    @staticmethod
    def get_by_iso2(iso2: str) -> Optional[Country]:
        """Get a country by ISO2 code.

        Args:
            iso2: ISO2 country code (2 characters)

        Returns:
            Country instance or None if not found
        """
        return Country.query.filter_by(iso2=iso2.upper().strip()).first()

    @staticmethod
    def get_by_iso3(iso3: str) -> Optional[Country]:
        """Get a country by ISO3 code.

        Args:
            iso3: ISO3 country code (3 characters)

        Returns:
            Country instance or None if not found
        """
        return Country.query.filter_by(iso3=iso3.upper().strip()).first()

    @staticmethod
    def get_all(ordered: bool = True):
        """Get all countries.

        Args:
            ordered: If True, order by name

        Returns:
            Query object or list of countries
        """
        query = Country.query
        if ordered:
            query = query.order_by(Country.name)
        return query

    @staticmethod
    def exists(country_id: int) -> bool:
        """Check if a country exists.

        Args:
            country_id: Country ID

        Returns:
            True if country exists, False otherwise
        """
        return Country.query.filter_by(id=country_id).first() is not None
