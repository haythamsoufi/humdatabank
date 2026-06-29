"""
Country Service - Centralized service for country-related database operations.

This service provides a unified interface for country queries, replacing
direct database queries in route handlers.
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import Country, User
from app.models.core import UserEntityPermission
from app.models.rbac import RbacRole, RbacUserRole
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
            Query object (call .all() to execute)
        """
        query = Country.query
        if ordered:
            query = query.order_by(Country.name)
        return query

    @staticmethod
    def get_all_with_national_societies(ordered: bool = True):
        """Get all countries with national_societies eagerly loaded in one JOIN.

        Avoids the N+1 pattern that arises when ``country.primary_national_society``
        is accessed inside a loop over a plain ``get_all()`` result.

        Returns:
            SQLAlchemy query — call ``.all()`` to execute.
        """
        query = Country.query.options(joinedload(Country.national_societies))
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


def fds_member_user_display_name(user: User | None) -> str:
    """Human-readable label for a platform user assigned as FDS member."""
    if not user:
        return ''
    name = (user.name or '').strip()
    if name:
        return name
    return (user.email or '').strip() or f'User {user.id}'


def get_fds_member_user_options_for_country(country_id: int) -> list[dict]:
    """Org admins with entity coverage for this country — eligible FDS member pickers."""
    rows = (
        User.query.filter(User.active.is_(True))
        .join(UserEntityPermission, UserEntityPermission.user_id == User.id)
        .join(RbacUserRole, RbacUserRole.user_id == User.id)
        .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
        .filter(
            UserEntityPermission.entity_type == 'country',
            UserEntityPermission.entity_id == int(country_id),
            or_(
                RbacRole.code == 'admin_core',
                RbacRole.code.like('admin\\_%', escape='\\'),
            ),
        )
        .order_by(User.name, User.email)
        .distinct()
        .all()
    )
    return [
        {
            'id': user.id,
            'label': fds_member_user_display_name(user),
            'email': user.email or '',
        }
        for user in rows
    ]


def parse_fds_member_user_id(raw_value) -> int | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        user_id = int(float(text))
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def resolve_fds_member_user_id_from_import(
    raw_user_id=None,
    raw_email=None,
) -> int | None:
    """Resolve FDS member from Excel import columns (user id preferred over email)."""
    parsed_id = parse_fds_member_user_id(raw_user_id)
    if parsed_id is not None:
        return parsed_id

    email = str(raw_email).strip() if raw_email is not None and str(raw_email).strip() else None
    if not email:
        return None

    user = User.query.filter(
        User.active.is_(True),
        db.func.lower(User.email) == email.lower(),
    ).first()
    if not user:
        raise ValueError(f'No active user found with email "{email}".')
    return user.id


def assign_country_fds_member_user(country: Country, user_id: int | None) -> None:
    """Set the country's FDS member to an org admin covering that country."""
    if user_id is None:
        country.fds_member_user_id = None
        return

    eligible_ids = {option['id'] for option in get_fds_member_user_options_for_country(country.id)}
    if user_id not in eligible_ids:
        raise ValueError('Selected FDS member must be an org admin covering this country.')

    country.fds_member_user_id = user_id


def countries_with_fds_member_query():
    """Countries query with FDS member user eager-loaded for admin tables."""
    return Country.query.options(joinedload(Country.fds_member_user))


def user_is_fds_member(user_id: int | None) -> bool:
    """True when the user is assigned as FDS member for at least one country."""
    if not user_id:
        return False
    return (
        Country.query.filter(
            Country.fds_member_user_id == int(user_id),
        ).limit(1).first()
        is not None
    )


def get_fds_member_filter_options() -> list[dict]:
    """Distinct FDS members assigned on countries, sorted by display name."""
    rows = (
        User.query.filter(User.active.is_(True))
        .join(Country, Country.fds_member_user_id == User.id)
        .order_by(User.name, User.email)
        .distinct()
        .all()
    )
    return [
        {
            'id': user.id,
            'label': fds_member_user_display_name(user),
        }
        for user in rows
    ]
