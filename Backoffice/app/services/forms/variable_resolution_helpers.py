"""Shared helpers wrapping VariableResolutionService batch resolution."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_assignment_level_variables(
    template_version,
    assignment_entity_status,
) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Resolve assignment-scoped template variables once.

    Returns ``({'': {...}, 'assignment': {...}}, assignment_level_resolved)``.
    """
    from app.services.forms.variable_resolution_service import VariableResolutionService

    resolved_variables: Dict[str, Dict[str, Any]] = {}
    assignment_level_resolved = None
    if not template_version:
        return resolved_variables, assignment_level_resolved

    variable_configs = getattr(template_version, 'variables', None) or {}
    if not variable_configs:
        return resolved_variables, assignment_level_resolved

    try:
        assignment_level_resolved = VariableResolutionService.resolve_variables(
            template_version,
            assignment_entity_status,
        )
        resolved_variables[''] = assignment_level_resolved or {}
        resolved_variables['assignment'] = assignment_level_resolved or {}
    except Exception as exc:
        logger.debug('assignment-level variable resolve failed: %s', exc)

    return resolved_variables, assignment_level_resolved


def merge_batch_resolved_variables(
    template_version,
    assignment_entity_status,
    row_entity_ids: Iterable[int],
    resolved_variables: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[Any, Dict[str, Any]]:
    """
    Batch-resolve variables for matrix row entities and merge into ``resolved_variables``.

    Returns the raw batch mapping from ``VariableResolutionService.resolve_variables_batch``.
    """
    from app.services.forms.variable_resolution_service import VariableResolutionService

    entity_ids = [int(rid) for rid in row_entity_ids if rid is not None]
    if not template_version or not entity_ids:
        return {}

    target = resolved_variables if resolved_variables is not None else {}
    try:
        batch = VariableResolutionService.resolve_variables_batch(
            template_version,
            assignment_entity_status,
            entity_ids,
        ) or {}
    except Exception as exc:
        logger.debug('batch variable resolve failed: %s', exc)
        return {}

    for rid, vals in batch.items():
        target[str(rid)] = vals
    return batch
