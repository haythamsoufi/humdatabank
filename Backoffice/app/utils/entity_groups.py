from typing import Iterable, List, Sequence, Set

import logging

try:
    from flask import current_app
except Exception as e:  # pragma: no cover - allow usage outside app context
    logging.getLogger(__name__).debug("Flask import fallback: %s", e)
    current_app = None  # type: ignore

from config import Config
from app.models.enums import EntityType

# Mapping of high-level entity groups to their concrete entity type identifiers
ENTITY_GROUP_TYPE_MAP = {
    'countries': [
        EntityType.country.value,
    ],
    'ns_structure': [
        EntityType.ns_branch.value,
        EntityType.ns_subbranch.value,
        EntityType.ns_localunit.value,
    ],
    'secretariat': [
        EntityType.division.value,
        EntityType.department.value,
        EntityType.regional_office.value,
        EntityType.cluster_office.value,
    ],
}


def _get_default_groups() -> List[str]:
    return list(getattr(Config, 'DEFAULT_ENABLED_ENTITY_TYPES', ['countries', 'ns_structure', 'secretariat']))


def get_enabled_entity_groups() -> List[str]:
    """
    Return the list of enabled entity groups from the Flask app config, falling back to defaults.
    Ensures only known groups are returned and preserves the configured order.
    """
    groups: Sequence[str]
    try:
        groups = current_app.config.get('ENABLED_ENTITY_TYPES', _get_default_groups())  # type: ignore[attr-defined]
    except Exception as e:
        logging.getLogger(__name__).debug("ENABLED_ENTITY_TYPES fallback: %s", e)
        groups = _get_default_groups()

    cleaned: List[str] = []
    for group in groups:
        key = str(group).strip().lower()
        if key in ENTITY_GROUP_TYPE_MAP and key not in cleaned:
            cleaned.append(key)
    # If configuration becomes empty after cleaning, fall back to defaults
    if not cleaned:
        return _get_default_groups()
    return cleaned


def get_allowed_entity_type_codes(enabled_groups: Iterable[str] = None) -> Set[str]:
    """
    Expand enabled entity groups into the concrete entity type codes used across the app.
    """
    groups = list(enabled_groups) if enabled_groups is not None else get_enabled_entity_groups()
    allowed: Set[str] = set()
    for group in groups:
        allowed.update(ENTITY_GROUP_TYPE_MAP.get(group, []))
    return allowed


def is_entity_group_enabled(group_key: str, enabled_groups: Iterable[str] = None) -> bool:
    """
    Convenience helper to check if a specific high-level entity group is enabled.
    """
    groups = list(enabled_groups) if enabled_groups is not None else get_enabled_entity_groups()
    return group_key in groups
