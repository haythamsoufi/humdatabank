"""Assign canonical stable_key values to template 22 staff and funding matrices.

Revision ID: backfill_t22_matrix_keys
Revises: add_assignment_email_snap
Create Date: 2026-10-06

Rows that already have a stable_key are left unchanged. Null rows on an
unambiguous matrix (one per version, identified by columns) receive the
canonical key, or the single key the group already uses.
"""

import json

from alembic import op
import sqlalchemy as sa

from app.utils.stable_key import (
    T22_FUNDING_MATRIX_STABLE_KEY,
    T22_STAFF_MATRIX_COLUMN,
    T22_STAFF_MATRIX_STABLE_KEY,
)
from app.utils.stable_key_backfill import fill_null_stable_keys


revision = "backfill_t22_matrix_keys"
down_revision = "add_assignment_email_snap"
branch_labels = None
depends_on = None


def _column_names(config):
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (TypeError, ValueError):
            return set()
    if not isinstance(config, dict):
        return set()
    matrix = config.get("matrix_config") if isinstance(config.get("matrix_config"), dict) else config
    names = set()
    if not isinstance(matrix, dict):
        return names
    for col in matrix.get("columns") or []:
        name = col.get("name") if isinstance(col, dict) else col
        if name:
            names.add(str(name).strip().lower())
    return names


class _KeyRow:
    def __init__(self, row_id, version_id, stable_key):
        self.id = row_id
        self.version_id = version_id
        self.stable_key = stable_key


def _apply(canonical_for_kind):
    conn = op.get_bind()
    fetched = conn.execute(
        sa.text(
            """
            SELECT id, version_id, config, stable_key
            FROM form_item
            WHERE template_id = 22
              AND item_type = 'matrix'
              AND archived = false
            """
        )
    ).mappings()
    buckets = {"staff": [], "funding": []}
    for row in fetched:
        names = _column_names(row["config"])
        wrapped = _KeyRow(row["id"], row["version_id"], row["stable_key"])
        if T22_STAFF_MATRIX_COLUMN in names:
            buckets["staff"].append(wrapped)
        elif {"sp1", "efs"} <= names:
            buckets["funding"].append(wrapped)

    for kind, rows in buckets.items():
        by_version = {}
        for row in rows:
            by_version.setdefault(row.version_id, []).append(row)
        before = {row.id: row.stable_key for row in rows}
        fill_null_stable_keys(by_version, canonical_for_kind[kind], lambda: canonical_for_kind[kind])
        for row in rows:
            if row.stable_key and row.stable_key != before[row.id]:
                conn.execute(
                    sa.text(
                        "UPDATE form_item SET stable_key = :key WHERE id = :id AND stable_key IS NULL"
                    ),
                    {"key": row.stable_key, "id": row.id},
                )


def upgrade():
    _apply(
        {
            "staff": T22_STAFF_MATRIX_STABLE_KEY,
            "funding": T22_FUNDING_MATRIX_STABLE_KEY,
        }
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE form_item
            SET stable_key = NULL
            WHERE template_id = 22
              AND stable_key IN (:staff_key, :funding_key)
            """
        ),
        {
            "staff_key": T22_STAFF_MATRIX_STABLE_KEY,
            "funding_key": T22_FUNDING_MATRIX_STABLE_KEY,
        },
    )
