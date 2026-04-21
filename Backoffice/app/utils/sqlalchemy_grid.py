"""Shared SQLAlchemy model-to-grid serialization helpers.

Centralizes the repeated pattern of introspecting SQLAlchemy model columns
and converting model instances to flat dictionaries for AG Grid / JS consumption.
"""

from datetime import datetime
from sqlalchemy import inspect as sa_inspect


def build_columns_config(model_class, *, multilingual_name=False, include_types=True):
    """Build a columns-config list from a SQLAlchemy model class.

    Args:
        model_class: SQLAlchemy model class to introspect.
        multilingual_name: If True, mark the ``name`` column with
            ``"multilingual": True`` so the JS layer can render a
            language-aware cell.
        include_types: If True (default), each entry includes a ``"type"``
            key (``string`` / ``number`` / ``boolean`` / ``date``).
            Set to False for a minimal config (name only).

    Returns:
        list[dict]: Column descriptors, e.g.
        ``[{"name": "code", "type": "string"}, ...]``
    """
    inspector = sa_inspect(model_class)
    columns_config = []

    for column in inspector.columns:
        if column.name == 'id':
            continue
        if column.name == 'name_translations':
            continue

        col_entry = {"name": column.name}

        if include_types:
            col_type = "string"
            if hasattr(column.type, 'python_type'):
                py_type = column.type.python_type
                if py_type in (int, float):
                    col_type = "number"
                elif py_type is bool:
                    col_type = "boolean"
                elif py_type is datetime:
                    col_type = "date"
            col_entry["type"] = col_type

        if multilingual_name and column.name == 'name':
            col_entry["multilingual"] = True

        columns_config.append(col_entry)

    return columns_config


def model_to_dict(obj, columns_config):
    """Convert a SQLAlchemy model instance to a flat dictionary.

    Args:
        obj: Model instance.
        columns_config: List produced by :func:`build_columns_config`.

    Returns:
        dict: Column-name → value mapping.  ``None`` values become ``''``;
        dict (JSONB) values are stringified.
    """
    data = {}
    for col in columns_config:
        col_name = col['name']
        if hasattr(obj, col_name):
            value = getattr(obj, col_name)
            if value is None:
                data[col_name] = ''
            elif isinstance(value, dict):
                data[col_name] = str(value) if value else ''
            else:
                data[col_name] = value
        else:
            data[col_name] = ''
    return data
