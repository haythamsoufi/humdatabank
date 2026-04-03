# ========== Variable Resolution Service ==========
"""
Service for resolving template variables from form submissions.

Variables allow form items to reference values from other form submissions,
enabling features like:
- Prefilling number fields with values from previous assignments
- Displaying referenced values in text fields (e.g., "You reported [planned_funding] last round")
"""

from flask import current_app
from app import db
from app.models import (
    FormData, FormItem, FormTemplate, FormTemplateVersion,
    AssignedForm, AssignmentEntityStatus
)
from typing import Dict, Any, Optional
import ast
import logging
import operator
import re

logger = logging.getLogger(__name__)


class VariableResolutionService:
    """Service for resolving template variables from form data."""

    # Built-in metadata tokens that can be used directly in template text as: [entity_name], [template_name], etc.
    # These are resolved globally (even if no template variables are defined).
    _BUILTIN_METADATA_TYPES = {
        'entity_name': 'entity_name',
        'entity_name_hierarchy': 'entity_name_hierarchy',
        'entity_id': 'entity_id',
        'entity_type': 'entity_type',
        'national_society_name': 'national_society_name',
        'template_name': 'template_name',
        'assignment_period': 'assignment_period',
    }

    _SAFE_BINARY_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }

    _SAFE_UNARY_OPERATORS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    # Pre-compiled patterns for fast repeated use.
    # - Formula example: [[period]+1]
    # - Variable example: [planned_funding]
    _FORMULA_PATTERN = re.compile(r'\[\[(\w+)\]([+\-*/]\d+(?:\.\d+)?)\]')
    _VAR_PATTERN = re.compile(r'\[(\w+)\]')

    # Plugin label variables (EO1, EO2, EO3) are resolved client-side from Emergency Operations
    # plugin data attributes. Never resolve them server-side so [EO1] stays in the text for the client.
    _PLUGIN_LABEL_VARIABLES = frozenset({'EO1', 'EO2', 'EO3'})

    # Reserved matrix_column_name value: when set, variable reads the row total (sum of all columns) for each row.
    MATRIX_COLUMN_ROW_TOTAL = '_row_total'

    @classmethod
    def _effective_matrix_cell_value(cls, cell_value: Any) -> Any:
        """
        Extract the effective (final) value from a matrix cell.
        Handles variable-column format: { "original": "...", "modified": "...", "isModified": bool }.
        Returns modified if present, else original; otherwise returns the value as-is.
        """
        if cell_value is None:
            return None
        if isinstance(cell_value, dict):
            effective = cell_value.get('modified')
            if effective is not None:
                return effective
            effective = cell_value.get('original')
            if effective is not None:
                return effective
        return cell_value

    @classmethod
    def _matrix_row_total(cls, disagg_data: Optional[Dict], row_entity_id: Any) -> Optional[float]:
        """
        Compute the row total (sum of all column values) for a given row in matrix disagg_data.
        Used when variable config matrix_column_name is MATRIX_COLUMN_ROW_TOTAL.
        Handles variable-column format (original/modified) per cell.
        """
        if not disagg_data or not isinstance(disagg_data, dict):
            return None
        prefix = f"{row_entity_id}_"
        total = 0.0
        for key, cell_value in disagg_data.items():
            if key.startswith('_') or not key.startswith(prefix):
                continue
            effective = cls._effective_matrix_cell_value(cell_value)
            if effective is None:
                continue
            try:
                total += float(str(effective).replace(',', ''))
            except (ValueError, TypeError):
                pass
        return total if total else None

    @classmethod
    def _evaluate_ast_node(cls, node: ast.AST) -> float:
        """Recursively evaluate a limited AST consisting of numeric literals and safe operators."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Only numeric constants are allowed in formulas")
        if isinstance(node, ast.UnaryOp) and type(node.op) in cls._SAFE_UNARY_OPERATORS:
            operand = cls._evaluate_ast_node(node.operand)
            return cls._SAFE_UNARY_OPERATORS[type(node.op)](operand)
        if isinstance(node, ast.BinOp) and type(node.op) in cls._SAFE_BINARY_OPERATORS:
            left = cls._evaluate_ast_node(node.left)
            right = cls._evaluate_ast_node(node.right)
            return cls._SAFE_BINARY_OPERATORS[type(node.op)](left, right)
        raise ValueError(f"Unsupported expression element: {type(node).__name__}")

    @classmethod
    def _safe_eval_expression(cls, expression: str) -> float:
        """Evaluate a sanitized arithmetic expression using Python's AST parser."""
        try:
            parsed = ast.parse(expression, mode='eval')
        except SyntaxError as exc:
            raise ValueError("Invalid formula syntax") from exc
        return cls._evaluate_ast_node(parsed.body)

    @staticmethod
    def _has_nonempty_scalar(value: Any) -> bool:
        """
        Return True when a scalar value is meaningfully present.
        Preserves legitimate 0/False values while treating None/blank strings as empty.
        """
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        return True

    @classmethod
    def resolve_variables(
        cls,
        template_version: FormTemplateVersion,
        assignment_entity_status: AssignmentEntityStatus,
        row_entity_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Resolve all variables for a template version in the context of an assignment.

        Args:
            template_version: The FormTemplateVersion containing variable definitions
            assignment_entity_status: The AssignmentEntityStatus for the current form context

        Returns:
            Dict mapping variable_name -> resolved_value (or None if not found)
        """
        if not assignment_entity_status:
            return {}

        # Always include built-in metadata tokens (even if the template has no variable definitions).
        builtin_resolved = cls._resolve_builtin_metadata_variables(
            assignment_entity_status=assignment_entity_status,
            template_version=template_version
        )

        if not template_version or not template_version.variables:
            return builtin_resolved

        resolved = {}
        variables = template_version.variables

        for variable_name, variable_config in variables.items():
            # EO1, EO2, EO3 are plugin label variables; they are replaced client-side from
            # Emergency Operations field data attributes. Do not resolve them server-side
            # or [EO1] would become empty and section names like "Section name [EO1]" would break.
            if variable_name in cls._PLUGIN_LABEL_VARIABLES:
                continue
            try:
                logger.debug(f"resolve_variables: Resolving variable '{variable_name}' with config: {variable_config}")

                # Check variable type - default to 'lookup' for backward compatibility
                variable_type = variable_config.get('variable_type', 'lookup')

                if variable_type == 'metadata':
                    # Handle metadata variables
                    value = cls._resolve_metadata_variable(
                        variable_config,
                        assignment_entity_status,
                        template_version
                    )
                else:
                    # Handle lookup variables (existing behavior)
                    # match_by_indicator_bank variables are context-dependent and must be resolved per-field.
                    # We do not resolve them globally here (caller should resolve on demand with context).
                    if variable_config.get('match_by_indicator_bank'):
                        value = None
                        resolved[variable_name] = value
                        continue
                    # Add row_entity_id to config temporarily for matrix lookups
                    if row_entity_id is not None:
                        variable_config = dict(variable_config)  # Make a copy
                        variable_config['_row_entity_id'] = row_entity_id
                    value = cls._resolve_single_variable(
                        variable_config,
                        assignment_entity_status
                    )

                # Use default value if resolution returned None
                if value is None:
                    default_value = variable_config.get('default_value')
                    if default_value is not None and default_value != '':
                        value = default_value

                resolved[variable_name] = value
            except Exception as e:
                logger.error(
                    f"Error resolving variable '{variable_name}': {e}",
                    exc_info=True
                )
                # Try to use default value even on error
                default_value = variable_config.get('default_value')
                resolved[variable_name] = default_value if default_value is not None and default_value != '' else None

        # Merge built-ins without overriding user-defined variable names.
        for name, value in (builtin_resolved or {}).items():
            resolved.setdefault(name, value)

        return resolved

    @classmethod
    def resolve_variable_by_indicator_bank(
        cls,
        variable_config: Dict[str, Any],
        assignment_entity_status: AssignmentEntityStatus,
        current_form_item: Any,
        cache: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """
        Resolve a lookup variable by matching the current indicator's indicator_bank_id
        to an indicator in the source template (same indicator_bank_id).

        This is used when variable_config.match_by_indicator_bank is True.
        """
        try:
            if not assignment_entity_status:
                return None
            if not variable_config or not isinstance(variable_config, dict):
                return None
            if not current_form_item:
                return None

            source_template_id = variable_config.get('source_template_id')
            source_assignment_period = variable_config.get('source_assignment_period')
            if not source_template_id or not source_assignment_period:
                return None

            indicator_bank_id = getattr(current_form_item, 'indicator_bank_id', None)
            if not indicator_bank_id:
                return None

            cache = cache if isinstance(cache, dict) else {}
            template_version_cache = cache.setdefault('published_version_by_template', {})
            source_item_cache = cache.setdefault('source_item_by_bank', {})

            # Determine published version id for source template
            source_version_id = template_version_cache.get(source_template_id)
            if not source_version_id:
                tmpl = FormTemplate.query.get(source_template_id)
                source_version_id = getattr(tmpl, 'published_version_id', None) if tmpl else None
                template_version_cache[source_template_id] = source_version_id

            if not source_version_id:
                return None

            # Find matching indicator in source template/version by indicator_bank_id
            cache_key = (int(source_template_id), int(source_version_id), int(indicator_bank_id))
            source_form_item_id = source_item_cache.get(cache_key)
            if source_form_item_id is None:
                match = (
                    FormItem.query
                    .filter_by(
                        template_id=source_template_id,
                        version_id=source_version_id,
                        item_type='indicator',
                        indicator_bank_id=indicator_bank_id,
                        archived=False
                    )
                    .order_by(FormItem.order.asc())
                    .first()
                )
                source_form_item_id = match.id if match else 0
                source_item_cache[cache_key] = source_form_item_id

            if not source_form_item_id:
                return None

            cfg = dict(variable_config)
            cfg['source_form_item_id'] = int(source_form_item_id)
            # Ensure a normal lookup path (entities_containing is matrix-only and does not apply here)
            if cfg.get('entity_scope') == 'entities_containing':
                cfg['entity_scope'] = 'same'

            return cls._resolve_single_variable(cfg, assignment_entity_status)
        except Exception as e:
            logger.debug("_resolve_single_variable failed: %s", e)
            return None

    @classmethod
    def resolve_variables_batch(
        cls,
        template_version: FormTemplateVersion,
        assignment_entity_status: AssignmentEntityStatus,
        row_entity_ids: list
    ) -> Dict[int, Dict[str, Any]]:
        """
        Batch resolve variables for multiple matrix rows efficiently.
        Caches FormData lookups to avoid redundant database queries.

        Args:
            template_version: The FormTemplateVersion containing variable definitions
            assignment_entity_status: The AssignmentEntityStatus for the current form context
            row_entity_ids: List of entity IDs for matrix rows

        Returns:
            Dict mapping row_entity_id -> {variable_name: resolved_value, ...}
        """
        if not assignment_entity_status:
            return {}

        if not row_entity_ids:
            return {}

        # Built-in metadata tokens are the same for all rows.
        builtin_resolved = cls._resolve_builtin_metadata_variables(
            assignment_entity_status=assignment_entity_status,
            template_version=template_version
        )

        if not template_version or not template_version.variables:
            return {int(row_id): dict(builtin_resolved) for row_id in row_entity_ids}

        variables = template_version.variables
        results = {}


        # Pre-fetch and cache FormData entries for all variables
        # This avoids repeated database queries for the same source data
        form_data_cache = {}
        entity_statuses_cache = {}  # Cache entity_statuses lookups too
        assigned_form_cache = {}  # Cache AssignedForm lookups

        # Group variables by their source (template_id, period, form_item_id, entity_scope)
        # to batch fetch FormData entries
        variable_groups = {}
        for variable_name, variable_config in variables.items():
            variable_type = variable_config.get('variable_type', 'lookup')
            if variable_type == 'metadata':
                # Metadata variables don't need FormData
                continue

            source_template_id = variable_config.get('source_template_id')
            source_assignment_period = variable_config.get('source_assignment_period')
            source_form_item_id = variable_config.get('source_form_item_id')
            entity_scope = variable_config.get('entity_scope', 'same')

            if not all([source_template_id, source_assignment_period, source_form_item_id]):
                continue

            cache_key = (source_template_id, source_assignment_period, source_form_item_id, entity_scope)
            if cache_key not in variable_groups:
                variable_groups[cache_key] = []
            variable_groups[cache_key].append((variable_name, variable_config))

        # Pre-fetch FormData for each variable group
        for (source_template_id, source_assignment_period, source_form_item_id, entity_scope), var_list in variable_groups.items():
            # Find the source assignment (cache this lookup)
            assigned_form_key = (source_template_id, source_assignment_period)
            if assigned_form_key not in assigned_form_cache:
                source_assigned_form = AssignedForm.query.filter_by(
                    template_id=source_template_id,
                    period_name=source_assignment_period
                ).first()
                assigned_form_cache[assigned_form_key] = source_assigned_form
            else:
                source_assigned_form = assigned_form_cache[assigned_form_key]

            if not source_assigned_form:
                continue

            # Get entity statuses for this scope (same for all variables in group)
            # Cache this lookup to avoid repeated queries
            status_cache_key = (source_assigned_form.id, entity_scope)
            if status_cache_key not in entity_statuses_cache:
                entity_statuses = cls._get_entity_statuses_for_scope(
                    source_assigned_form,
                    assignment_entity_status,
                    entity_scope,
                    var_list[0][1]  # Use first variable's config
                )
                entity_statuses_cache[status_cache_key] = entity_statuses
            else:
                entity_statuses = entity_statuses_cache[status_cache_key]

            if not entity_statuses:
                continue

            # Fetch FormData entries once for this group
            form_data_entries = FormData.query.filter(
                FormData.assignment_entity_status_id.in_([aes.id for aes in entity_statuses]),
                FormData.form_item_id == source_form_item_id
            ).order_by(FormData.submitted_at.desc()).all()

            # Cache the most recent entry for each entity_status
            for entry in form_data_entries:
                aes_id = entry.assignment_entity_status_id
                if aes_id not in form_data_cache or entry.submitted_at > form_data_cache[aes_id].submitted_at:
                    form_data_cache[aes_id] = entry


        # Resolve variables for each row
        for row_entity_id in row_entity_ids:
            row_results = {}

            for variable_name, variable_config in variables.items():
                if variable_name in cls._PLUGIN_LABEL_VARIABLES:
                    continue
                try:
                    variable_type = variable_config.get('variable_type', 'lookup')

                    if variable_type == 'metadata':
                        # Handle metadata variables (same for all rows)
                        value = cls._resolve_metadata_variable(
                            variable_config,
                            assignment_entity_status,
                            template_version
                        )
                    else:
                        # Handle lookup variables with row context
                        variable_config_copy = dict(variable_config)
                        variable_config_copy['_row_entity_id'] = row_entity_id
                        variable_config_copy['_form_data_cache'] = form_data_cache  # Pass cache
                        variable_config_copy['_entity_statuses_cache'] = entity_statuses_cache  # Pass entity statuses cache
                        variable_config_copy['_assigned_form_cache'] = assigned_form_cache  # Pass assigned form cache
                        value = cls._resolve_single_variable_cached(
                            variable_config_copy,
                            assignment_entity_status
                        )

                    # Use default value if resolution returned None
                    if value is None:
                        default_value = variable_config.get('default_value')
                        if default_value is not None and default_value != '':
                            value = default_value

                    row_results[variable_name] = value
                except Exception as e:
                    logger.error(
                        f"Error resolving variable '{variable_name}' for row {row_entity_id}: {e}",
                        exc_info=True
                    )
                    default_value = variable_config.get('default_value')
                    row_results[variable_name] = default_value if default_value is not None and default_value != '' else None

            # Merge built-ins without overriding user-defined variable names.
            for name, value in (builtin_resolved or {}).items():
                row_results.setdefault(name, value)

            results[row_entity_id] = row_results

        return results

    @classmethod
    def _resolve_builtin_metadata_variables(
        cls,
        assignment_entity_status: AssignmentEntityStatus,
        template_version: Optional[FormTemplateVersion]
    ) -> Dict[str, Any]:
        """
        Resolve built-in metadata tokens that can be used directly as [token] without being defined
        in template_version.variables.

        Does not raise; returns None values on failures.
        """
        resolved: Dict[str, Any] = {}
        for token_name, metadata_type in cls._BUILTIN_METADATA_TYPES.items():
            try:
                resolved[token_name] = cls._resolve_metadata_variable(
                    {'metadata_type': metadata_type},
                    assignment_entity_status,
                    template_version
                )
            except Exception as e:
                logger.debug("token %r resolution failed: %s", token_name, e)
                resolved[token_name] = None
        return resolved

    @classmethod
    def _resolve_single_variable_cached(
        cls,
        variable_config: Dict[str, Any],
        assignment_entity_status: AssignmentEntityStatus
    ) -> Optional[Any]:
        """
        Resolve a single variable using cached FormData entries to avoid redundant queries.
        This is an optimized version of _resolve_single_variable for batch operations.
        The cache is passed via variable_config['_form_data_cache'].
        """
        source_template_id = variable_config.get('source_template_id')
        source_assignment_period = variable_config.get('source_assignment_period')
        source_form_item_id = variable_config.get('source_form_item_id')
        entity_scope = variable_config.get('entity_scope', 'same')
        form_data_cache = variable_config.get('_form_data_cache') or {}

        if not all([source_template_id, source_assignment_period, source_form_item_id]):
            return None

        # Check cache for assigned form and entity statuses first (from batch resolution)
        assigned_form_cache = variable_config.get('_assigned_form_cache') or {}
        entity_statuses_cache = variable_config.get('_entity_statuses_cache') or {}
        entity_statuses = None

        # Try to get assigned form from cache
        assigned_form_key = (source_template_id, source_assignment_period)
        source_assigned_form = assigned_form_cache.get(assigned_form_key)

        # If not in cache, query (shouldn't happen in batch mode, but fallback for safety)
        if not source_assigned_form:
            source_assigned_form = AssignedForm.query.filter_by(
                template_id=source_template_id,
                period_name=source_assignment_period
            ).first()

        if not source_assigned_form:
            return None

        # Try to get entity statuses from cache
        if entity_statuses_cache:
            status_cache_key = (source_assigned_form.id, entity_scope)
            if status_cache_key in entity_statuses_cache:
                entity_statuses = entity_statuses_cache[status_cache_key]

        # If not in cache, query (shouldn't happen in batch mode, but fallback for safety)
        if not entity_statuses:
            # Determine which entity status(es) to query based on entity_scope
            entity_statuses = cls._get_entity_statuses_for_scope(
                source_assigned_form,
                assignment_entity_status,
                entity_scope,
                variable_config
            )

        if not entity_statuses:
            return None

        # Special handling for reverse lookup (entities_containing scope)
        if entity_scope == 'entities_containing':
            row_entity_id = variable_config.get('_row_entity_id')
            if row_entity_id is not None:
                return cls._resolve_entities_containing_for_matrix_cell(
                    entity_statuses,
                    row_entity_id,
                    variable_config,
                    assignment_entity_status
                )
            else:
                return cls._resolve_entities_containing(
                    entity_statuses,
                    variable_config
                )

        # Use cached FormData if available, otherwise fall back to query
        entry = None
        for aes in entity_statuses:
            if aes.id in form_data_cache:
                cached_entry = form_data_cache[aes.id]
                if not entry or cached_entry.submitted_at > entry.submitted_at:
                    entry = cached_entry

        # If not in cache, query (shouldn't happen in batch mode, but fallback for safety)
        if not entry:
            form_data_entries = FormData.query.filter(
                FormData.assignment_entity_status_id.in_([aes.id for aes in entity_statuses]),
                FormData.form_item_id == source_form_item_id
            ).order_by(FormData.submitted_at.desc()).all()

            if form_data_entries:
                entry = form_data_entries[0]

        if not entry:
            return None

        # Check if this is a matrix lookup
        matrix_column_name = variable_config.get('matrix_column_name')
        row_entity_id = variable_config.get('_row_entity_id')

        if matrix_column_name and row_entity_id is not None and entry.disagg_data:
            if isinstance(entry.disagg_data, dict):
                if matrix_column_name == cls.MATRIX_COLUMN_ROW_TOTAL:
                    # Row total: sum of all column values for this row
                    total = cls._matrix_row_total(entry.disagg_data, row_entity_id)
                    return total
                lookup_key = f"{row_entity_id}_{matrix_column_name}"
                matrix_value = entry.disagg_data.get(lookup_key)
                if matrix_value is not None:
                    effective = cls._effective_matrix_cell_value(matrix_value)
                    try:
                        return float(str(effective).replace(',', '')) if effective is not None else None
                    except (ValueError, TypeError):
                        return effective

        # Extract the value from FormData
        if entry.form_item and entry.form_item.is_indicator:
            if cls._has_nonempty_scalar(entry.value):
                try:
                    return float(str(entry.value).replace(',', ''))
                except (ValueError, TypeError):
                    return entry.value
            elif isinstance(entry.disagg_data, dict):
                values = entry.disagg_data.get('values', {})
                if isinstance(values, dict):
                    total = 0.0
                    has_any_value = False
                    for raw in values.values():
                        if raw is None or not isinstance(raw, (int, float, str)):
                            continue
                        raw_text = str(raw).strip()
                        if raw_text == "":
                            continue
                        has_any_value = True
                        try:
                            total += float(raw_text.replace(',', ''))
                        except (ValueError, TypeError):
                            continue
                    if has_any_value:
                        return total
        else:
            return entry.value

        return None

    @classmethod
    def _resolve_metadata_variable(
        cls,
        variable_config: Dict[str, Any],
        assignment_entity_status: AssignmentEntityStatus,
        template_version: FormTemplateVersion
    ) -> Optional[Any]:
        """
        Resolve a metadata variable (entity name, template name, etc.).

        Args:
            variable_config: Variable configuration dict with metadata_type
            assignment_entity_status: Current assignment context
            template_version: Current template version

        Returns:
            Resolved metadata value or None if not found
        """
        metadata_type = variable_config.get('metadata_type')
        if not metadata_type:
            logger.warning(f"_resolve_metadata_variable: Missing metadata_type in config: {variable_config}")
            return None

        logger.debug(f"_resolve_metadata_variable: Resolving metadata type '{metadata_type}'")

        try:
            if metadata_type == 'entity_name':
                # Return entity name without hierarchy
                from app.services.entity_service import EntityService
                entity_name = EntityService.get_localized_entity_name(
                    assignment_entity_status.entity_type,
                    assignment_entity_status.entity_id,
                    include_hierarchy=False
                )
                return entity_name

            elif metadata_type == 'entity_name_hierarchy':
                # Return entity name with full hierarchy
                from app.services.entity_service import EntityService
                entity_name = EntityService.get_localized_entity_name(
                    assignment_entity_status.entity_type,
                    assignment_entity_status.entity_id,
                    include_hierarchy=True
                )
                return entity_name

            elif metadata_type == 'entity_id':
                # Return entity ID as string
                entity_id = str(assignment_entity_status.entity_id)
                return entity_id

            elif metadata_type == 'entity_type':
                # Return entity type
                entity_type = assignment_entity_status.entity_type
                return entity_type

            elif metadata_type == 'national_society_name':
                # Return National Society name for the country associated with the assigned entity
                from app.services.entity_service import EntityService
                from app.utils.form_localization import get_localized_national_society_name
                country = EntityService.get_country_for_entity(
                    assignment_entity_status.entity_type,
                    assignment_entity_status.entity_id
                )
                if not country:
                    logger.debug("_resolve_metadata_variable: national_society_name - no country for entity")
                    return None
                ns_name = get_localized_national_society_name(country)
                logger.debug(f"_resolve_metadata_variable: national_society_name = {ns_name}")
                return ns_name or None

            elif metadata_type == 'template_name':
                # Return template name
                if template_version:
                    template_name = template_version.name or (template_version.template.name if template_version.template else 'Unknown Template')
                    return template_name
                else:
                    logger.warning("_resolve_metadata_variable: template_version is None, cannot get template_name")
                    return None

            elif metadata_type == 'assignment_period':
                # Return assignment period name
                if assignment_entity_status.assigned_form:
                    period_name = assignment_entity_status.assigned_form.period_name
                    return period_name
                else:
                    logger.warning("_resolve_metadata_variable: assigned_form is None, cannot get assignment_period")
                    return None

            else:
                logger.warning(f"_resolve_metadata_variable: Unknown metadata_type '{metadata_type}'")
                return None

        except Exception as e:
            logger.error(
                f"_resolve_metadata_variable: Error resolving metadata type '{metadata_type}': {e}",
                exc_info=True
            )
            return None

    @classmethod
    def _resolve_single_variable(
        cls,
        variable_config: Dict[str, Any],
        assignment_entity_status: AssignmentEntityStatus
    ) -> Optional[Any]:
        """
        Resolve a single variable based on its configuration.

        Args:
            variable_config: Variable configuration dict
            assignment_entity_status: Current assignment context

        Returns:
            Resolved value or None if not found
        """
        source_template_id = variable_config.get('source_template_id')
        source_assignment_period = variable_config.get('source_assignment_period')
        source_form_item_id = variable_config.get('source_form_item_id')
        entity_scope = variable_config.get('entity_scope', 'same')

        logger.debug(f"_resolve_single_variable: Config - template_id={source_template_id}, period={source_assignment_period}, form_item_id={source_form_item_id}, entity_scope={entity_scope}")

        if not all([source_template_id, source_assignment_period, source_form_item_id]):
            logger.warning(f"_resolve_single_variable: Incomplete variable config: {variable_config}")
            return None

        # Find the source assignment
        source_assigned_form = AssignedForm.query.filter_by(
            template_id=source_template_id,
            period_name=source_assignment_period
        ).first()

        if not source_assigned_form:
            logger.warning(
                f"_resolve_single_variable: Source assignment not found: template_id={source_template_id}, "
                f"period={source_assignment_period}"
            )
            return None

        logger.debug(f"_resolve_single_variable: Found source assignment ID={source_assigned_form.id}")

        # Determine which entity status(es) to query based on entity_scope
        entity_statuses = cls._get_entity_statuses_for_scope(
            source_assigned_form,
            assignment_entity_status,
            entity_scope,
            variable_config
        )

        if not entity_statuses:
            logger.debug(
                f"_resolve_single_variable: No entity statuses found for variable with scope '{entity_scope}'"
            )
            return None

        # Special handling for reverse lookup (entities_containing scope)
        if entity_scope == 'entities_containing':
            # Check if this is being used in a matrix cell (row_entity_id is provided)
            row_entity_id = variable_config.get('_row_entity_id')
            if row_entity_id is not None:
                # When used in a matrix cell, look up the actual cell value from the row entity's matrix data
                # The lookup key is "{lookup_entity_id}_{matrix_column_name}" where lookup_entity_id is from current assignment
                return cls._resolve_entities_containing_for_matrix_cell(
                    entity_statuses,
                    row_entity_id,
                    variable_config,
                    assignment_entity_status
                )
            else:
                # When used for auto-load, return the full list
                return cls._resolve_entities_containing(
                    entity_statuses,
                    variable_config
                )

        # Log which entity's submission(s) are being queried
        # Query FormData for the specified form item across all matching entity statuses
        # Use the most recent submission if multiple exist
        form_data_entries = FormData.query.filter(
            FormData.assignment_entity_status_id.in_([aes.id for aes in entity_statuses]),
            FormData.form_item_id == source_form_item_id
        ).order_by(FormData.submitted_at.desc()).all()

        if not form_data_entries:
            return None

        # Use the most recent entry (first after ordering by submitted_at desc)
        entry = form_data_entries[0]

        # Check if this is a matrix lookup (requires matrix_column_name and row_entity_id)
        matrix_column_name = variable_config.get('matrix_column_name')
        row_entity_id = variable_config.get('_row_entity_id')  # Temporary context, not stored in config

        if matrix_column_name and row_entity_id is not None and entry.disagg_data:
            # This is a matrix lookup - parse disagg_data to find the value for this row/column
            # Matrix data is stored as: {"_table": "country", "61_Planned": 456, "61_Supported": 1}
            # or with variable-column format: {"61_Planned": {"original": "...", "modified": "...", "isModified": bool}}
            # When matrix_column_name is _row_total, use sum of all column values for this row.
            if isinstance(entry.disagg_data, dict):
                if matrix_column_name == cls.MATRIX_COLUMN_ROW_TOTAL:
                    total = cls._matrix_row_total(entry.disagg_data, row_entity_id)
                    return total
                lookup_key = f"{row_entity_id}_{matrix_column_name}"
                matrix_value = entry.disagg_data.get(lookup_key)
                if matrix_value is not None:
                    effective = cls._effective_matrix_cell_value(matrix_value)
                    try:
                        resolved_value = float(str(effective).replace(',', '')) if effective is not None else None
                        return resolved_value
                    except (ValueError, TypeError):
                        return effective

        # Extract the value from FormData
        # For indicators, prefer total_value; for questions, use value field
        if entry.form_item and entry.form_item.is_indicator:
            # For indicators, return numeric value if present (including legitimate zero values)
            if cls._has_nonempty_scalar(entry.value):
                try:
                    resolved_value = float(str(entry.value).replace(',', ''))
                    logger.debug(f"_resolve_single_variable: Indicator value resolved to: {resolved_value}")
                    return resolved_value
                except (ValueError, TypeError):
                    logger.debug(f"_resolve_single_variable: Could not convert indicator value to float: {entry.value}")
                    return entry.value
            elif isinstance(entry.disagg_data, dict):
                # Calculate total from disaggregated data (including totals that evaluate to 0)
                values = entry.disagg_data.get('values', {})
                if isinstance(values, dict):
                    total = 0.0
                    has_any_value = False
                    for raw in values.values():
                        if raw is None or not isinstance(raw, (int, float, str)):
                            continue
                        raw_text = str(raw).strip()
                        if raw_text == "":
                            continue
                        has_any_value = True
                        try:
                            total += float(raw_text.replace(',', ''))
                        except (ValueError, TypeError):
                            continue
                    if has_any_value:
                        logger.debug(f"_resolve_single_variable: Indicator disaggregated total resolved to: {total}")
                        return total
        else:
            # For questions and other types, return the value field
            logger.debug(f"_resolve_single_variable: Question/other value resolved to: {entry.value}")
            return entry.value

        # Empty source entries are expected for sparse historical datasets; treat as no-data.
        logger.debug(
            "_resolve_single_variable: Source FormData entry %s has no usable value "
            "(value=%r, disagg_data=%r, data_not_available=%r, not_applicable=%r)",
            entry.id,
            entry.value,
            entry.disagg_data,
            entry.data_not_available,
            entry.not_applicable,
        )
        return None

    @classmethod
    def _resolve_entities_containing_for_matrix_cell(
        cls,
        entity_statuses: list,
        row_entity_id: int,
        variable_config: Dict[str, Any],
        current_assignment_entity_status: AssignmentEntityStatus = None
    ) -> Optional[Any]:
        """
        Resolve reverse lookup for matrix cell: Look up the actual cell value from the row entity's matrix data.
        The lookup key is "{lookup_entity_id}_{matrix_column_name}" where lookup_entity_id is from the current assignment.

        Args:
            entity_statuses: List of AssignmentEntityStatus objects that matched
            row_entity_id: The entity ID of the current matrix row
            variable_config: Variable configuration
            current_assignment_entity_status: Current assignment context (needed for lookup_entity_id)

        Returns:
            The actual cell value from matrix data (e.g., 1 for ticked, 0 for unticked), or 0 if not found
        """
        if not entity_statuses:
            logger.info(f"_resolve_entities_containing_for_matrix_cell: No matching entities found, returning 0 for row_entity_id={row_entity_id}")
            return 0

        # Get the lookup entity ID from current assignment (the entity ID we're looking for in matrix data)
        if not current_assignment_entity_status:
            logger.warning(f"_resolve_entities_containing_for_matrix_cell: current_assignment_entity_status not provided, falling back to membership check")
            # Fallback to old behavior if context not provided
            row_entity_id_int = int(row_entity_id) if row_entity_id else None
            for aes in entity_statuses:
                if aes.entity_id == row_entity_id_int:
                    return 1
            return 0

        lookup_entity_id = current_assignment_entity_status.entity_id
        matrix_column_name = variable_config.get('matrix_column_name')
        source_form_item_id = variable_config.get('source_form_item_id')

        if not matrix_column_name or not source_form_item_id:
            logger.warning(f"_resolve_entities_containing_for_matrix_cell: Missing matrix_column_name or source_form_item_id, falling back to membership check")
            # Fallback to old behavior if config incomplete
            row_entity_id_int = int(row_entity_id) if row_entity_id else None
            for aes in entity_statuses:
                if aes.entity_id == row_entity_id_int:
                    return 1
            return 0

        # Find the entity status that matches the row_entity_id
        row_entity_id_int = int(row_entity_id) if row_entity_id else None
        matching_entity_status = None
        for aes in entity_statuses:
            if aes.entity_id == row_entity_id_int:
                matching_entity_status = aes
                break

        if not matching_entity_status:
            logger.info(f"_resolve_entities_containing_for_matrix_cell: Row entity {row_entity_id} not found in {len(entity_statuses)} matching entities, returning 0")
            return 0

        # Query FormData for the matching entity to get its matrix data
        form_data_entry = FormData.query.filter_by(
            assignment_entity_status_id=matching_entity_status.id,
            form_item_id=source_form_item_id
        ).order_by(FormData.submitted_at.desc()).first()

        if not form_data_entry or not form_data_entry.disagg_data:
            logger.info(f"_resolve_entities_containing_for_matrix_cell: No FormData or matrix data found for row_entity_id={row_entity_id}, returning 0")
            return 0

        # Look up the actual cell value (or row total) using lookup key or row total
        # In entities_containing, the "row" in the source matrix is the current assignment's entity (lookup_entity_id)
        if isinstance(form_data_entry.disagg_data, dict):
            if matrix_column_name == cls.MATRIX_COLUMN_ROW_TOTAL:
                total = cls._matrix_row_total(form_data_entry.disagg_data, lookup_entity_id)
                numeric_value = total if total is not None else 0
                logger.info(
                    f"_resolve_entities_containing_for_matrix_cell: Row total for row_entity_id={row_entity_id} = {numeric_value}"
                )
                return numeric_value
            lookup_key = f"{lookup_entity_id}_{matrix_column_name}"
            cell_value = form_data_entry.disagg_data.get(lookup_key)
            if cell_value is not None:
                # Use effective value (modified if present, else original) for variable-column format
                effective = cls._effective_matrix_cell_value(cell_value)
                # Return the actual value (1 for ticked, 0 for unticked, or whatever value is stored)
                try:
                    # Convert to numeric if possible (for consistency); strip commas for formatted numbers
                    numeric_value = float(str(effective).replace(',', '')) if effective is not None else 0
                    logger.info(
                        f"_resolve_entities_containing_for_matrix_cell: Found cell value for row_entity_id={row_entity_id}, "
                        f"lookup_key='{lookup_key}' = {numeric_value}"
                    )
                    return numeric_value
                except (ValueError, TypeError):
                    logger.info(
                        f"_resolve_entities_containing_for_matrix_cell: Found cell value (non-numeric) for row_entity_id={row_entity_id}, "
                        f"lookup_key='{lookup_key}' = {effective}"
                    )
                    return effective
            else:
                # Cell key not found in matrix data
                available_keys = [k for k in form_data_entry.disagg_data.keys() if k != '_table']
                logger.info(
                    f"_resolve_entities_containing_for_matrix_cell: Cell key '{lookup_key}' not found in matrix data for row_entity_id={row_entity_id}. "
                    f"Available keys: {available_keys}. Returning 0"
                )
                return 0

        logger.info(f"_resolve_entities_containing_for_matrix_cell: Matrix data is not a dict for row_entity_id={row_entity_id}, returning 0")
        return 0

    @classmethod
    def _resolve_entities_containing(
        cls,
        entity_statuses: list,
        variable_config: Dict[str, Any]
    ) -> Optional[str]:
        """
        Resolve reverse lookup: Return a formatted list of entities that contain
        the current assignment's entity ID in their matrix data.

        Args:
            entity_statuses: List of AssignmentEntityStatus objects that matched
            variable_config: Variable configuration with return_format options

        Returns:
            Formatted string with entity IDs or names, or None if no matches
        """
        if not entity_statuses:
            logger.info("_resolve_entities_containing: No matching entities found")
            return None

        return_format = variable_config.get('return_format', 'auto_load_format')  # Default: auto-load format

        logger.info(
            f"_resolve_entities_containing: Formatting {len(entity_statuses)} entities with format '{return_format}'"
        )

        # Extract entity_type from matrix data's _table field (matching auto-load endpoint behavior)
        # This represents the type of entities in the matrix rows (e.g., "country" if rows are countries)
        entity_type_from_table = None
        source_form_item_id = variable_config.get('source_form_item_id')
        if source_form_item_id:
            # Query FormData from first matching entity to get _table value
            first_entity_status = entity_statuses[0]
            form_data_entry = FormData.query.filter_by(
                assignment_entity_status_id=first_entity_status.id,
                form_item_id=source_form_item_id
            ).order_by(FormData.submitted_at.desc()).first()

            if form_data_entry and form_data_entry.disagg_data and isinstance(form_data_entry.disagg_data, dict):
                entity_type_from_table = form_data_entry.disagg_data.get('_table')
                logger.debug(
                    f"_resolve_entities_containing: Extracted entity_type from _table field: {entity_type_from_table}"
                )

        # Extract entity information
        entity_list = []
        for aes in entity_statuses:
            entity_list.append({
                'entity_type': aes.entity_type,
                'entity_id': aes.entity_id
            })

        # Format according to return_format
        if return_format == 'auto_load_format':
            # Auto-load format: JSON matching the /api/v1/matrix/auto-load-entities endpoint response
            # Format: {"entities": [{"entity_id": int, "entity_type": str}, ...], "entity_type": str}
            # Note: entity_type here is from _table field (type of entities in matrix rows),
            # not the entity_type of the entities that own the submissions
            import json
            entities = [{'entity_id': e['entity_id'], 'entity_type': e['entity_type']} for e in entity_list]
            result = json.dumps({
                'entities': entities,
                'entity_type': entity_type_from_table  # Use _table value, matching auto-load endpoint
            })
            logger.info(f"_resolve_entities_containing: Returning auto-load format JSON: {result}")
            return result

        elif return_format == 'ids_comma':
            # Comma-separated entity IDs: "162, 163, 164"
            ids = [str(e['entity_id']) for e in entity_list]
            result = ', '.join(ids)
            logger.info(f"_resolve_entities_containing: Returning comma-separated IDs: {result}")
            return result

        elif return_format == 'ids_json':
            # JSON array of entity IDs: "[162, 163, 164]"
            import json
            ids = [e['entity_id'] for e in entity_list]
            result = json.dumps(ids)
            logger.info(f"_resolve_entities_containing: Returning JSON array of IDs: {result}")
            return result

        elif return_format == 'names_comma':
            # Comma-separated entity names: "France, Germany, Italy"
            from app.services.entity_service import EntityService
            names = []
            for e in entity_list:
                name = EntityService.get_localized_entity_name(
                    e['entity_type'],
                    e['entity_id'],
                    include_hierarchy=False
                )
                names.append(name or f"Entity {e['entity_id']}")
            result = ', '.join(names)
            logger.info(f"_resolve_entities_containing: Returning comma-separated names: {result}")
            return result

        elif return_format == 'ids_and_names_comma':
            # Comma-separated with both IDs and names: "162 (France), 163 (Germany)"
            from app.services.entity_service import EntityService
            formatted = []
            for e in entity_list:
                name = EntityService.get_localized_entity_name(
                    e['entity_type'],
                    e['entity_id'],
                    include_hierarchy=False
                )
                if name:
                    formatted.append(f"{e['entity_id']} ({name})")
                else:
                    formatted.append(str(e['entity_id']))
            result = ', '.join(formatted)
            logger.info(f"_resolve_entities_containing: Returning IDs and names: {result}")
            return result

        else:
            # Default to comma-separated IDs
            ids = [str(e['entity_id']) for e in entity_list]
            result = ', '.join(ids)
            logger.warning(
                f"_resolve_entities_containing: Unknown return_format '{return_format}', "
                f"defaulting to comma-separated IDs: {result}"
            )
            return result

    @classmethod
    def _get_entity_statuses_for_scope(
        cls,
        source_assigned_form: AssignedForm,
        current_assignment_entity_status: AssignmentEntityStatus,
        entity_scope: str,
        variable_config: Dict[str, Any]
    ) -> list:
        """
        Get the list of AssignmentEntityStatus objects to query based on entity scope.

        Args:
            source_assigned_form: The source assignment form
            current_assignment_entity_status: Current assignment context
            entity_scope: 'same', 'any', or 'specific'
            variable_config: Full variable configuration

        Returns:
            List of AssignmentEntityStatus objects
        """
        if entity_scope == 'same':
            # Same entity: same entity_type and entity_id as current assignment
            current_entity_type = current_assignment_entity_status.entity_type
            current_entity_id = current_assignment_entity_status.entity_id
            logger.debug(
                f"_get_entity_statuses_for_scope: 'same' scope - querying for "
                f"entity_type={current_entity_type}, entity_id={current_entity_id}"
            )
            entity_status = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=source_assigned_form.id,
                entity_type=current_entity_type,
                entity_id=current_entity_id
            ).first()
            if entity_status:
                logger.debug(
                    f"_get_entity_statuses_for_scope: Found entity status ID={entity_status.id} "
                    f"for same entity (type={current_entity_type}, id={current_entity_id})"
                )
            else:
                logger.debug(
                    f"_get_entity_statuses_for_scope: No entity status found for same entity "
                    f"(type={current_entity_type}, id={current_entity_id})"
                )
            return [entity_status] if entity_status else []

        elif entity_scope == 'any':
            # Any entity: all entity statuses for the source assignment
            logger.debug(
                f"_get_entity_statuses_for_scope: 'any' scope - querying all entity statuses "
                f"for assigned_form_id={source_assigned_form.id}"
            )
            entity_statuses = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=source_assigned_form.id
            ).all()
            logger.debug(
                f"_get_entity_statuses_for_scope: Found {len(entity_statuses)} entity statuses "
                f"for 'any' scope"
            )
            return entity_statuses

        elif entity_scope == 'specific':
            # Specific entity: entity_type and entity_id from config
            specific_entity_type = variable_config.get('specific_entity_type')
            specific_entity_id = variable_config.get('specific_entity_id')

            if not specific_entity_type or specific_entity_id is None:
                logger.warning(
                    f"_get_entity_statuses_for_scope: Variable config specifies 'specific' scope but missing "
                    f"specific_entity_type or specific_entity_id"
                )
                return []

            logger.debug(
                f"_get_entity_statuses_for_scope: 'specific' scope - querying for "
                f"entity_type={specific_entity_type}, entity_id={specific_entity_id}"
            )
            entity_status = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=source_assigned_form.id,
                entity_type=specific_entity_type,
                entity_id=specific_entity_id
            ).first()
            if entity_status:
                logger.debug(
                    f"_get_entity_statuses_for_scope: Found entity status ID={entity_status.id} "
                    f"for specific entity (type={specific_entity_type}, id={specific_entity_id})"
                )
            else:
                logger.debug(
                    f"_get_entity_statuses_for_scope: No entity status found for specific entity "
                    f"(type={specific_entity_type}, id={specific_entity_id})"
                )
            return [entity_status] if entity_status else []

        elif entity_scope == 'entities_containing':
            # Reverse lookup: Find all entities whose matrix data contains the current assignment's entity ID
            # This is used when you want to find all entities (e.g., countries) that mention
            # the current assignment's entity (e.g., NS 88) in their matrix data keys (e.g., "88_SP2", "88_SP3")
            # The lookup_entity_id is automatically set to the current assignment's entity_id
            lookup_entity_id = current_assignment_entity_status.entity_id

            logger.info(
                f"_get_entity_statuses_for_scope: 'entities_containing' scope - finding all entities whose matrix data "
                f"contains lookup_entity_id={lookup_entity_id} (from current assignment entity_type={current_assignment_entity_status.entity_type}, "
                f"entity_id={current_assignment_entity_status.entity_id})"
            )

            # Get all entity statuses for the source assignment
            all_entity_statuses = AssignmentEntityStatus.query.filter_by(
                assigned_form_id=source_assigned_form.id
            ).all()

            # Filter to find entities whose matrix data contains keys starting with "{lookup_entity_id}_"
            matching_entity_statuses = []
            source_form_item_id = variable_config.get('source_form_item_id')

            if not source_form_item_id:
                logger.warning(
                    f"_get_entity_statuses_for_scope: 'entities_containing' scope requires source_form_item_id "
                    f"to check matrix data"
                )
                return []

            # Query FormData for all entities to check their matrix data
            form_data_entries = FormData.query.filter(
                FormData.assignment_entity_status_id.in_([aes.id for aes in all_entity_statuses]),
                FormData.form_item_id == source_form_item_id
            ).order_by(FormData.submitted_at.desc()).all()

            # Group by entity_status_id to get most recent entry per entity
            entity_data_map = {}
            for entry in form_data_entries:
                aes_id = entry.assignment_entity_status_id
                if aes_id not in entity_data_map:
                    entity_data_map[aes_id] = entry

            # Check each entity's matrix data for keys containing the lookup_entity_id.
            # Use "any key starting with lookup_entity_id_" so entities with blanks in some columns
            # are still included. Per-cell resolution then returns the value or 0 when the key is missing.
            # (Previously we required the exact matrix_column_name key, which excluded entities with
            # blanks and caused batch resolution to return 0 for all columns due to cached entity list.)
            lookup_prefix = f"{lookup_entity_id}_"
            logger.debug(
                f"_get_entity_statuses_for_scope: entities_containing - matching any key starting with '{lookup_prefix}'"
            )

            for aes in all_entity_statuses:
                entry = entity_data_map.get(aes.id)
                if entry and entry.disagg_data and isinstance(entry.disagg_data, dict):
                    has_match = any(
                        key.startswith(lookup_prefix) and not key.startswith('_')
                        for key in entry.disagg_data.keys()
                    )
                    if has_match:
                        matching_entity_statuses.append(aes)
                        logger.debug(
                            f"_get_entity_statuses_for_scope: Found matching entity - "
                            f"entity_type={aes.entity_type}, entity_id={aes.entity_id}, "
                            f"status_id={aes.id}"
                        )

            logger.info(
                f"_get_entity_statuses_for_scope: Found {len(matching_entity_statuses)} entities containing "
                f"lookup_entity_id={lookup_entity_id} in their matrix data"
            )
            return matching_entity_statuses

        else:
            logger.warning(f"Unknown entity_scope: {entity_scope}")
            return []

    @classmethod
    def format_variable_value(
        cls,
        value: Any,
        variable_config: Dict[str, Any]
    ) -> str:
        """
        Format a variable value based on configuration options.

        Args:
            value: The resolved value (typically a number)
            variable_config: Variable configuration dict with formatting options

        Returns:
            Formatted string representation of the value
        """
        if value is None:
            return ''

        # Check if value is numeric
        try:
            num_value = float(value)
        except (ValueError, TypeError):
            # Not a number, return as string
            return str(value)

        # Get formatting options from config
        use_thousands_separator = variable_config.get('format_thousands_separator', False)
        decimal_places = variable_config.get('format_decimal_places', 'auto')  # 'auto', 'whole', or number

        # Determine decimal places
        if decimal_places == 'whole':
            # Round to whole number, no decimals
            num_value = round(num_value)
            decimal_places_int = 0
        elif decimal_places == 'auto':
            # Keep original decimal places if it's a whole number, otherwise keep decimals
            if num_value == int(num_value):
                decimal_places_int = 0
            else:
                # Count decimal places in original value (up to reasonable limit)
                value_str = str(value)
                if '.' in value_str:
                    decimal_part = value_str.split('.')[-1].rstrip('0')
                    decimal_places_int = min(len(decimal_part), 10)  # Cap at 10 decimal places
                else:
                    decimal_places_int = 0
        else:
            # Specific number of decimal places
            try:
                decimal_places_int = int(decimal_places)
                if decimal_places_int < 0:
                    decimal_places_int = 0
            except (ValueError, TypeError):
                decimal_places_int = 0

        # Format the number
        if use_thousands_separator:
            # Format with thousands separator
            if decimal_places_int == 0:
                formatted = f"{int(num_value):,}"
            else:
                formatted = f"{num_value:,.{decimal_places_int}f}"
        else:
            # Format without thousands separator
            if decimal_places_int == 0:
                formatted = f"{int(num_value)}"
            else:
                formatted = f"{num_value:.{decimal_places_int}f}"

        # Remove trailing zeros and decimal point if not needed (only for non-zero decimal places)
        if decimal_places_int > 0 and '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')

        logger.debug(f"format_variable_value: {value} -> {formatted} (thousands={use_thousands_separator}, decimals={decimal_places_int})")

        return formatted

    @classmethod
    def _evaluate_formula(cls, formula: str, variable_value: Any) -> Any:
        """
        Evaluate a formula expression like '+1', '*2', '-5', '/2', etc.

        Args:
            formula: The formula expression (e.g., '+1', '*2', '-5')
            variable_value: The resolved variable value

        Returns:
            The result of the formula evaluation
        """
        if variable_value is None:
            return None

        try:
            # Try to convert to number
            num_value = float(variable_value)
        except (ValueError, TypeError):
            # If not numeric, return original value
            logger.warning(f"_evaluate_formula: Variable value '{variable_value}' is not numeric, cannot evaluate formula '{formula}'")
            return variable_value

        try:
            # Evaluate the formula safely (only allow basic arithmetic operations)
            # Remove any whitespace
            formula = formula.strip()

            # Validate formula contains only safe characters (numbers, +, -, *, /, ., spaces, parentheses)
            if not re.match(r'^[\d+\-*/.()\s]+$', formula):
                logger.warning(f"_evaluate_formula: Formula '{formula}' contains unsafe characters")
                return variable_value

            # Replace [variable] placeholder with the actual value
            # Formula format: ([variable]+1) or ([variable]*2) etc.
            # We'll evaluate: num_value + 1, num_value * 2, etc.
            # First, try to extract the operation and operand
            formula_clean = formula.replace(' ', '')

            # Match patterns like: +1, -5, *2, /3, or more complex: +1-2, *2+3, etc.
            # For simplicity, we'll evaluate the entire expression with the variable value
            # Replace any placeholder or evaluate directly
            expression = formula_clean

            # If formula starts with an operator, prepend the value
            if expression.startswith(('+', '-', '*', '/')):
                expression = str(num_value) + expression
            else:
                # If it's a full expression, try to replace a placeholder
                expression = expression.replace('[variable]', str(num_value))

            # Evaluate the expression using the restricted AST evaluator
            result = cls._safe_eval_expression(expression)

            # Convert result to appropriate type
            if isinstance(result, float) and result.is_integer():
                return int(result)
            return result

        except Exception as e:
            logger.warning(f"_evaluate_formula: Error evaluating formula '{formula}' with value {variable_value}: {e}")
            return variable_value

    @classmethod
    def replace_variables_if_placeholders(
        cls,
        text: str,
        resolved_variables: Dict[str, Any],
        variable_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> str:
        """
        Replace [var] placeholders in text if present; otherwise return text unchanged.
        Use when you want a one-liner instead of: if resolved_variables and '[' in text: ...
        """
        if not text or not resolved_variables or '[' not in str(text):
            return text
        return cls.replace_variables_in_text(text, resolved_variables, variable_configs)

    @classmethod
    def replace_variables_in_text(
        cls,
        text: str,
        resolved_variables: Dict[str, Any],
        variable_configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> str:
        """
        Replace variable syntax [variable_name] and formulas [[variable_name]+1] in text with resolved values.

        Supports both simple variables: [variable_name]
        And formulas: [[variable_name]+1], [[variable_name]*2], [[variable_name]-5], [[variable_name]/2]

        Args:
            text: Text that may contain variable syntax
            resolved_variables: Dict of variable_name -> resolved_value
            variable_configs: Optional dict of variable_name -> variable_config for formatting

        Returns:
            Text with variables replaced
        """
        if not text:
            return text

        # Fast path: no placeholders.
        # This avoids regex work on the overwhelming majority of labels/definitions.
        if '[' not in text:
            return text

        result = text
        original_text = text

        # First, handle formulas like [[variable_name]+1], [[variable_name]*2], etc.
        # Pattern: [[variable_name] followed by operator and expression, then closing bracket]
        # This matches: [[period]+1], [[period]*2], [[period]-5], [[period]/2]
        def replace_formula(match):
            variable_name = match.group(1)
            formula_expr = match.group(2)  # e.g., '+1', '*2', '-5'
            full_match = match.group(0)  # e.g., '([period]+1)'

            if variable_name not in resolved_variables:
                logger.warning(f"replace_variables_in_text: Variable '{variable_name}' in formula not found in resolved variables")
                return full_match  # Return original if variable not resolved

            value = resolved_variables[variable_name]

            # If value is None, check for default
            if value is None:
                var_config = variable_configs.get(variable_name, {}) if variable_configs else {}
                default_value = var_config.get('default_value')
                if default_value is not None and default_value != '':
                    try:
                        value = float(default_value)
                    except (ValueError, TypeError):
                        return full_match  # Can't evaluate formula with non-numeric default
                else:
                    return full_match  # No value to evaluate

            # Evaluate the formula
            try:
                result_value = cls._evaluate_formula(formula_expr, value)

                # Format the result if formatting options are specified
                var_config = variable_configs.get(variable_name, {}) if variable_configs else {}
                if var_config.get('format_thousands_separator') is not None or var_config.get('format_decimal_places'):
                    formatted_value = cls.format_variable_value(result_value, var_config)
                else:
                    formatted_value = str(result_value)

                logger.debug(f"replace_variables_in_text: Evaluated formula {full_match} with value {value} -> {result_value} (formatted: {formatted_value})")
                return formatted_value
            except Exception as e:
                logger.warning(f"replace_variables_in_text: Error evaluating formula {full_match}: {e}")
                return full_match  # Return original on error

        # Replace formulas first
        result = cls._FORMULA_PATTERN.sub(replace_formula, result)

        # Then handle simple variables [variable_name]
        found_variables = cls._VAR_PATTERN.findall(result)

        if found_variables:
            logger.debug(f"replace_variables_in_text: Found variables in text: {found_variables}")
            logger.debug(f"replace_variables_in_text: Available resolved variables: {list(resolved_variables.keys())}")

        # Replace only placeholders that exist in the text (avoid O(num_resolved_vars) work per call).
        # NOTE: Keep behavior consistent with the previous implementation:
        # - unknown placeholders stay untouched (and will be logged as unresolved below)
        # - known placeholders with None values use default_value, else become ''
        def replace_simple(match: re.Match) -> str:
            variable_name = match.group(1)
            full_match = match.group(0)

            if variable_name not in resolved_variables:
                return full_match

            value = resolved_variables.get(variable_name)
            var_config = variable_configs.get(variable_name, {}) if variable_configs else {}

            if value is None:
                default_value = var_config.get('default_value')
                if default_value is not None and default_value != '':
                    # Respect formatting settings when defaults are numeric-like.
                    if var_config.get('format_thousands_separator') is not None or var_config.get('format_decimal_places'):
                        try:
                            return cls.format_variable_value(default_value, var_config)
                        except (ValueError, TypeError):
                            return str(default_value)
                    return str(default_value)
                return ''

            # Format if configured, otherwise stringify.
            if var_config.get('format_thousands_separator') is not None or var_config.get('format_decimal_places'):
                return cls.format_variable_value(value, var_config)
            return str(value)

        result = cls._VAR_PATTERN.sub(replace_simple, result)

        if result != original_text:
            logger.debug(f"replace_variables_in_text: Text changed from '{original_text}' to '{result}'")

        return result
