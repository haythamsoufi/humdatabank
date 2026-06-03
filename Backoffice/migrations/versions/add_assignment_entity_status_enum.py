"""Convert assignment_entity_status.status to PostgreSQL enum

Revision ID: add_assignment_entity_status_enum
Revises: migrate_related_programs_jsonb
Create Date: 2026-06-03

Pilot migration: replace varchar status with native PostgreSQL enum
``assignmententitystatus`` (no lookup table).
"""

from alembic import op


revision = 'add_assignment_entity_status_enum'
down_revision = 'migrate_related_programs_jsonb'
branch_labels = None
depends_on = None

_CANONICAL_STATUSES = (
    'Pending',
    'In Progress',
    'Submitted',
    'Approved',
    'Requires Revision',
)


def upgrade():
    op.execute(
        """
        CREATE TYPE assignmententitystatus AS ENUM (
            'Pending',
            'In Progress',
            'Submitted',
            'Approved',
            'Requires Revision'
        )
        """
    )

    # Normalize legacy / inconsistent values before casting.
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Pending'
        WHERE status IS NULL OR TRIM(status) = ''
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Pending'
        WHERE status IN ('Assigned', 'assigned')
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Approved'
        WHERE status IN ('Completed', 'completed')
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Pending'
        WHERE LOWER(TRIM(status)) = 'pending'
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'In Progress'
        WHERE LOWER(TRIM(status)) = 'in progress'
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Submitted'
        WHERE LOWER(TRIM(status)) = 'submitted'
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Approved'
        WHERE LOWER(TRIM(status)) = 'approved'
        """
    )
    op.execute(
        """
        UPDATE assignment_entity_status
        SET status = 'Requires Revision'
        WHERE LOWER(TRIM(status)) = 'requires revision'
        """
    )
    op.execute(
        f"""
        UPDATE assignment_entity_status
        SET status = 'Pending'
        WHERE status NOT IN ({", ".join(repr(v) for v in _CANONICAL_STATUSES)})
        """
    )

    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status TYPE assignmententitystatus
        USING status::assignmententitystatus
        """
    )
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status SET DEFAULT 'Pending'::assignmententitystatus
        """
    )
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status SET NOT NULL
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status TYPE VARCHAR(50)
        USING status::text
        """
    )
    op.execute(
        """
        ALTER TABLE assignment_entity_status
        ALTER COLUMN status SET DEFAULT 'Pending'
        """
    )
    op.execute("DROP TYPE assignmententitystatus")
