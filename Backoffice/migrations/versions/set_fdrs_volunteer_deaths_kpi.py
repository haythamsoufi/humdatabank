"""Map volunteer deaths on duty to its FDRS base KPI.

The indicator behind form item 935 had no ``fdrs_kpi_code``, so
``KPI_noVolDeathsDuty_Tot`` could not match it. The bank stores the base
code, the same way staff deaths store ``KPI_PStaffDeathsDuty``. The ``_Tot``
row is the value for that indicator.

Revision ID: fdrs_volunteer_deaths_kpi
Revises: fdrs_chf_companion_items
"""

from alembic import op

revision = "fdrs_volunteer_deaths_kpi"
down_revision = "fdrs_chf_companion_items"
branch_labels = None
depends_on = None

_NAME = "Number of volunteer deaths on duty."
_CODE = "KPI_noVolDeathsDuty"


def upgrade():
    op.execute(
        f"""
        UPDATE indicator_bank
        SET fdrs_kpi_code = '{_CODE}'
        WHERE name = '{_NAME}'
          AND (fdrs_kpi_code IS NULL OR btrim(fdrs_kpi_code) = '')
        """
    )


def downgrade():
    op.execute(
        f"""
        UPDATE indicator_bank
        SET fdrs_kpi_code = NULL
        WHERE name = '{_NAME}'
          AND fdrs_kpi_code = '{_CODE}'
        """
    )
