"""Helpers for PostgreSQL native string enums in SQLAlchemy models."""

from sqlalchemy import Enum

from app.extensions import db


def pg_str_enum_column(enum_class, type_name, *, default, nullable=False, index=False, **kwargs):
    """Map a ``str``-backed Python enum to a PostgreSQL ENUM storing ``.value`` strings."""
    column_type = Enum(
        enum_class,
        name=type_name,
        values_callable=lambda obj: [member.value for member in obj],
    )
    return db.Column(column_type, default=default, nullable=nullable, index=index, **kwargs)
