"""Keep saved data and references in step with matrix column code renames.

Matrix cells are saved under ``"{rowId}_{columnCode}"`` and selectable column headers
under ``"col_header|{columnCode}"``. Renaming a column code in the form builder
(``SP1`` -> ``SP1_[assignment_year]``) would orphan everything already saved under the
old code. This service moves that data, and the references to the code, to the new one.

What it updates, for one matrix item:

* ``form_data`` and ``repeat_group_data`` payloads (reported, prefilled, imputed and
  published) saved against that item.
* Template variables whose ``matrix_column_name`` points at the renamed column of this
  item (``FormTemplateVersion.variables``).
* Column references inside custom formulas of the matrix config itself.

Column codes may contain ``[variables]``. Saved keys use the code *resolved for that
assignment*, so the old and the new code are resolved per assignment before the keys
are rewritten (``SP1`` -> ``SP1_2026`` on a 2026 assignment, ``SP1_2027`` on a 2027 one).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import update
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models import (
    AssignmentEntityStatus,
    FormData,
    FormTemplateVersion,
    RepeatGroupData,
    RepeatGroupInstance,
)
from app.utils.matrix_calculation import rename_formula_refs

logger = logging.getLogger(__name__)

# Saved selectable column-header choices. Both prefixes end in the column code.
_COLUMN_KEY_PREFIXES = ('col_header_go_unmatched|', 'col_header|')
# Prefixed metadata that is keyed by row, not by column code.
_ROW_METADATA_PREFIXES = ('row_go_unmatched|',)

FORM_DATA_PAYLOAD_FIELDS = (
    'disagg_data',
    'prefilled_disagg_data',
    'imputed_disagg_data',
    'published_disagg_data',
)
REPEAT_DATA_PAYLOAD_FIELDS = (
    'disagg_data',
    'prefilled_disagg_data',
    'imputed_disagg_data',
)


# ---------------------------------------------------------------------------
# Pure helpers (no database)
# ---------------------------------------------------------------------------

def column_codes(columns: Optional[Iterable[Any]]) -> List[str]:
    """Column codes of a matrix config's ``columns`` list, in order."""
    codes: List[str] = []
    for col in columns or []:
        name = col.get('name') if isinstance(col, dict) else col
        if isinstance(name, str) and name.strip():
            codes.append(name.strip())
    return codes


def validate_renames(
    requested: Any,
    old_codes: Sequence[str],
    new_codes: Sequence[str],
) -> List[Tuple[str, str]]:
    """Keep only renames that are consistent with the old and the new config.

    ``requested`` is what the form builder reports: a list of ``{from, to}``. An entry
    survives when ``from`` was a column code before the edit, ``to`` is a column code
    after it, and the two differ. Duplicate sources or targets are dropped.
    """
    if not isinstance(requested, list):
        return []
    old_set = set(old_codes)
    new_set = set(new_codes)
    seen_from: set = set()
    seen_to: set = set()
    out: List[Tuple[str, str]] = []
    for item in requested:
        if not isinstance(item, dict):
            continue
        src = item.get('from')
        dst = item.get('to')
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        src, dst = src.strip(), dst.strip()
        if not src or not dst or src == dst:
            continue
        if src not in old_set or dst not in new_set:
            continue
        if src in seen_from or dst in seen_to:
            continue
        seen_from.add(src)
        seen_to.add(dst)
        out.append((src, dst))
    return out


def _is_blank_cell(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _split_column_key(key: Any, codes_longest_first: Sequence[str]) -> Optional[Tuple[str, Optional[str], str]]:
    """``(prefix, row_id, column_code)`` for a key that is tied to a column, else None."""
    if not isinstance(key, str) or not key:
        return None
    for prefix in _COLUMN_KEY_PREFIXES:
        if key.startswith(prefix):
            rest = key[len(prefix):]
            return (prefix, None, rest) if rest else None
    if key.startswith('_') or any(key.startswith(p) for p in _ROW_METADATA_PREFIXES):
        return None
    for code in codes_longest_first:
        suffix = f'_{code}'
        if key.endswith(suffix) and len(key) > len(suffix):
            return '', key[:-len(suffix)], code
    return None


def rewrite_matrix_payload(
    payload: Any,
    renames: Mapping[str, str],
    known_codes: Iterable[str],
) -> Tuple[Optional[Dict[str, Any]], int, int]:
    """Rename column codes inside one saved matrix payload.

    Returns ``(new_payload, cells_renamed, conflicts)``. ``new_payload`` is None when
    nothing changed. All renames apply in a single pass, so swaps and chains are safe.
    Cell keys are matched against *all* known codes by longest suffix, so renaming
    ``SP1`` never touches a cell that belongs to ``NEW_SP1``. A cell is left where it
    is (and counted as a conflict) when its new key already holds a value.
    """
    if not isinstance(payload, dict) or not payload or not renames:
        return None, 0, 0

    codes = sorted({c for c in known_codes if c} | set(renames), key=len, reverse=True)

    moves: Dict[str, str] = {}
    for key in payload:
        parts = _split_column_key(key, codes)
        if not parts:
            continue
        prefix, row_id, code = parts
        new_code = renames.get(code)
        if not new_code:
            continue
        moves[key] = f'{prefix}{row_id}_{new_code}' if row_id is not None else f'{prefix}{new_code}'

    if not moves:
        return None, 0, 0

    applied: Dict[str, str] = {}
    claimed: set = set()
    conflicts = 0
    for old_key, new_key in moves.items():
        occupied = new_key in payload and new_key not in moves and not _is_blank_cell(payload[new_key])
        if occupied or new_key in claimed:
            conflicts += 1
            continue
        applied[old_key] = new_key
        claimed.add(new_key)

    if not applied:
        return None, 0, conflicts

    overwritten = set(applied.values())
    result: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in applied:
            result[applied[key]] = value
        elif key in overwritten:
            continue  # blank cell replaced by the moved value
        else:
            result[key] = value
    return result, len(applied), conflicts


def rewrite_matrix_config_refs(matrix_config: Any, renames: Mapping[str, str]) -> bool:
    """Update column references inside the matrix config itself, in place.

    Preset calculations are rebuilt by the form builder from their column lists, so
    those lists are only patched defensively. Custom formulas are free text and are
    rewritten here. Returns True when anything changed.
    """
    if not isinstance(matrix_config, dict) or not renames:
        return False
    changed = False
    for col in matrix_config.get('columns') or []:
        calc = col.get('calculation') if isinstance(col, dict) else None
        if not isinstance(calc, dict):
            continue
        for list_key in ('sources', 'subtrahends', 'denominators'):
            names = calc.get(list_key)
            if not isinstance(names, list):
                continue
            renamed = [renames.get(n, n) if isinstance(n, str) else n for n in names]
            if renamed != names:
                calc[list_key] = renamed
                changed = True
        formula = calc.get('formula')
        if isinstance(formula, str) and formula:
            new_formula = rename_formula_refs(formula, renames)
            if new_formula != formula:
                calc['formula'] = new_formula
                changed = True
    return changed


def _empty_stats() -> Dict[str, Any]:
    return {
        'renames': [],
        'rows_scanned': 0,
        'rows_affected': 0,
        'cells': 0,
        'assignments': 0,
        'conflicts': 0,
        'skipped_unresolved': 0,
        'variables': [],
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MatrixColumnMigrationService:
    """Move saved matrix data and references from old column codes to new ones."""

    @classmethod
    def preview(cls, form_item_id: int, renames: Sequence[Tuple[str, str]], old_codes: Sequence[str]) -> Dict[str, Any]:
        """Count what a migration would touch, without changing anything."""
        return cls._run(form_item_id, renames, old_codes, dry_run=True)

    @classmethod
    def apply(cls, form_item_id: int, renames: Sequence[Tuple[str, str]], old_codes: Sequence[str]) -> Dict[str, Any]:
        """Migrate saved data and variable references. Does not commit.

        Runs inside the caller's transaction, so a failure rolls back together with the
        form item edit.
        """
        return cls._run(form_item_id, renames, old_codes, dry_run=False)

    # -- internals ---------------------------------------------------------

    @classmethod
    def _run(
        cls,
        form_item_id: int,
        renames: Sequence[Tuple[str, str]],
        old_codes: Sequence[str],
        *,
        dry_run: bool,
    ) -> Dict[str, Any]:
        stats = _empty_stats()
        stats['renames'] = [{'from': a, 'to': b} for a, b in renames]
        if not renames or not form_item_id:
            return stats

        resolver = _CodeResolver(renames, old_codes)
        affected_assignments: set = set()

        for model, fields in (
            (FormData, FORM_DATA_PAYLOAD_FIELDS),
            (RepeatGroupData, REPEAT_DATA_PAYLOAD_FIELDS),
        ):
            for row in cls._iter_rows(model, form_item_id, fields):
                row_id, aes_id, payloads = row[0], row[1], row[2:]
                stats['rows_scanned'] += 1
                mapping = resolver.mapping_for(aes_id)
                if mapping is None:
                    stats['skipped_unresolved'] += 1
                    continue
                renames_map, known = mapping
                changes: Dict[str, Any] = {}
                for field, payload in zip(fields, payloads):
                    new_payload, cells, conflicts = rewrite_matrix_payload(payload, renames_map, known)
                    stats['conflicts'] += conflicts
                    if new_payload is not None:
                        changes[field] = new_payload
                        stats['cells'] += cells
                if not changes:
                    continue
                stats['rows_affected'] += 1
                if aes_id:
                    affected_assignments.add(aes_id)
                if not dry_run:
                    # Keep submitted_at: a code migration is not a new submission, and
                    # the column's onupdate would otherwise bump it.
                    db.session.execute(
                        update(model)
                        .where(model.id == row_id)
                        .values(submitted_at=model.submitted_at, **changes)
                        .execution_options(synchronize_session=False)
                    )

        stats['assignments'] = len(affected_assignments)
        stats['variables'] = cls._migrate_variable_refs(form_item_id, dict(renames), dry_run=dry_run)
        return stats

    @staticmethod
    def _iter_rows(model, form_item_id: int, fields: Sequence[str], chunk_size: int = 200):
        """Yield ``(row_id, assignment_entity_status_id, *payloads)`` in id chunks.

        Reads ids first and payloads chunk by chunk, so the updates issued while
        iterating never share a cursor with a long-running read.
        """
        ids = [
            row[0]
            for row in db.session.query(model.id)
            .filter(model.form_item_id == form_item_id)
            .order_by(model.id)
            .all()
        ]
        payload_columns = [getattr(model, f) for f in fields]
        for start in range(0, len(ids), chunk_size):
            chunk = ids[start:start + chunk_size]
            if model is RepeatGroupData:
                query = (
                    db.session.query(
                        model.id, RepeatGroupInstance.assignment_entity_status_id, *payload_columns
                    )
                    .join(RepeatGroupInstance, model.repeat_instance_id == RepeatGroupInstance.id)
                )
            else:
                query = db.session.query(model.id, model.assignment_entity_status_id, *payload_columns)
            for row in query.filter(model.id.in_(chunk)).order_by(model.id).all():
                yield row

    @staticmethod
    def _migrate_variable_refs(form_item_id: int, renames: Dict[str, str], *, dry_run: bool) -> List[Dict[str, Any]]:
        """Point template variables that look up a renamed column at the new code."""
        updated: List[Dict[str, Any]] = []
        versions = FormTemplateVersion.query.filter(FormTemplateVersion.variables.isnot(None)).all()
        for version in versions:
            variables = version.variables
            if not isinstance(variables, dict):
                continue
            new_variables = None
            for var_name, cfg in variables.items():
                if not isinstance(cfg, dict):
                    continue
                try:
                    source_id = int(cfg.get('source_form_item_id'))
                except (TypeError, ValueError):
                    continue
                column = cfg.get('matrix_column_name')
                if source_id != int(form_item_id) or column not in renames:
                    continue
                if new_variables is None:
                    new_variables = copy.deepcopy(variables)
                new_variables[var_name]['matrix_column_name'] = renames[column]
                updated.append({
                    'template_id': version.template_id,
                    'version_id': version.id,
                    'variable': var_name,
                    'from': column,
                    'to': renames[column],
                })
            if new_variables is not None and not dry_run:
                version.variables = new_variables
                flag_modified(version, 'variables')
        return updated


class _CodeResolver:
    """Per-assignment ``(renames, known codes)`` with ``[variables]`` resolved.

    Codes without placeholders need no assignment at all and share one mapping.
    """

    def __init__(self, renames: Sequence[Tuple[str, str]], old_codes: Sequence[str]):
        self._renames = list(renames)
        self._old_codes = list(old_codes)
        self._templated = any('[' in c for c in self._old_codes) or any('[' in b for _, b in self._renames)
        self._static = (dict(self._renames), list(self._old_codes))
        self._by_aes: Dict[Any, Optional[Tuple[Dict[str, str], List[str]]]] = {}

    def mapping_for(self, aes_id: Optional[int]) -> Optional[Tuple[Dict[str, str], List[str]]]:
        if not self._templated:
            return self._static
        if aes_id is None:
            return None  # public submission: nothing to resolve [variables] against
        if aes_id not in self._by_aes:
            self._by_aes[aes_id] = self._resolve(aes_id)
        return self._by_aes[aes_id]

    def _resolve(self, aes_id: int) -> Optional[Tuple[Dict[str, str], List[str]]]:
        from app.services.forms.variable_resolution_service import VariableResolutionService

        try:
            aes = db.session.get(AssignmentEntityStatus, aes_id)
            if aes is None:
                return None
            resolved_vars, configs = VariableResolutionService.resolve_for_assignment_display(aes)

            def resolve(code: str) -> str:
                if '[' not in code:
                    return code
                return VariableResolutionService.replace_variables_in_text(code, resolved_vars, configs)

            mapping: Dict[str, str] = {}
            for old, new in self._renames:
                r_old, r_new = resolve(old), resolve(new)
                if '[' in r_old or '[' in r_new:
                    logger.warning(
                        "matrix column migration: unresolved placeholder for assignment %s (%r -> %r)",
                        aes_id, r_old, r_new,
                    )
                    return None
                if r_old != r_new:
                    mapping[r_old] = r_new
            known = [resolve(c) for c in self._old_codes]
            return mapping, known
        except Exception as exc:
            logger.warning("matrix column migration: could not resolve codes for assignment %s: %s", aes_id, exc)
            return None
