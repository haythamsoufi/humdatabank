"""Bridge revision (no DB changes) — was referenced by some DBs as alembic head.

The revision id must remain in the tree so `flask db upgrade` can resolve
databases that still list `indicator_bank_type_unit_translations` in
`alembic_version`. The real schema work is in
`add_indicator_bank_measurement_lookups` (next in chain).

Revision ID: indicator_bank_type_unit_translations
Revises: add_resource_subcategories
Create Date: 2026-04-22
"""

revision = "indicator_bank_type_unit_translations"
down_revision = "add_resource_subcategories"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
