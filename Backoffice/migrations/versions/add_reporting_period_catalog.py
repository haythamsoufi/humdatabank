"""Add reporting period catalog and typed assignment period dates

Revision ID: add_reporting_period_catalog
Revises: add_disagg_type_column
Create Date: 2026-06-03
"""

from datetime import date
import re

from alembic import op
import sqlalchemy as sa


revision = 'add_reporting_period_catalog'
down_revision = 'add_disagg_type_column'
branch_labels = None
depends_on = None


def _parse_period(value):
    """Return (period_type, start, end) for known period labels."""
    raw = (value or "").strip()
    if not raw:
        return None

    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", raw)]
    if not years:
        return None

    if len(years) == 1:
        year = years[0]
        return "annual", date(year, 1, 1), date(year, 12, 31)

    start_year = min(years)
    end_year = max(years)
    return "custom", date(start_year, 1, 1), date(end_year, 12, 31)


def upgrade():
    op.create_table(
        'reporting_period',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_reporting_period_name'),
    )
    op.create_index('ix_reporting_period_dates', 'reporting_period', ['period_start', 'period_end'])
    op.create_index('ix_reporting_period_type', 'reporting_period', ['period_type'])

    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.add_column(sa.Column('period_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('period_start', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('period_end', sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            'fk_assigned_form_period',
            'reporting_period',
            ['period_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_assigned_form_period', ['period_id'])

    bind = op.get_bind()
    assigned_forms = bind.execute(
        sa.text("SELECT id, period_name FROM assigned_form WHERE period_name IS NOT NULL")
    ).fetchall()

    period_ids = {}
    for assigned_form_id, period_name in assigned_forms:
        parsed = _parse_period(period_name)
        if parsed is None:
            continue

        period_type, period_start, period_end = parsed
        period_key = str(period_name).strip()
        if period_key not in period_ids:
            existing = bind.execute(
                sa.text("SELECT id FROM reporting_period WHERE name = :name"),
                {"name": period_key},
            ).scalar()
            if existing is None:
                result = bind.execute(
                    sa.text(
                        """
                        INSERT INTO reporting_period (name, period_type, period_start, period_end)
                        VALUES (:name, :period_type, :period_start, :period_end)
                        RETURNING id
                        """
                    ),
                    {
                        "name": period_key,
                        "period_type": period_type,
                        "period_start": period_start,
                        "period_end": period_end,
                    },
                )
                existing = result.scalar()
            period_ids[period_key] = existing

        bind.execute(
            sa.text(
                """
                UPDATE assigned_form
                SET period_id = :period_id,
                    period_start = :period_start,
                    period_end = :period_end
                WHERE id = :assigned_form_id
                """
            ),
            {
                "period_id": period_ids[period_key],
                "period_start": period_start,
                "period_end": period_end,
                "assigned_form_id": assigned_form_id,
            },
        )


def downgrade():
    with op.batch_alter_table('assigned_form', schema=None) as batch_op:
        batch_op.drop_index('ix_assigned_form_period')
        batch_op.drop_constraint('fk_assigned_form_period', type_='foreignkey')
        batch_op.drop_column('period_end')
        batch_op.drop_column('period_start')
        batch_op.drop_column('period_id')

    op.drop_table('reporting_period')
