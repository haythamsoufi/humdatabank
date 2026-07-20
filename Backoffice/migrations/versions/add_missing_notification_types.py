"""Add assignment_sent_for_review, assignment_returned_for_revision, validation_questions to notificationtype enum

These NotificationType members were added to app/models/enums.py but the corresponding
Postgres enum values were never created, so every attempt to INSERT a Notification row of
these types raised psycopg2.errors.InvalidTextRepresentation. create_notification() catches
that as a generic Exception, rolls back, logs an error, and returns None — so the failure
was silent: no in-app notification, no email, no user-visible error.

Revision ID: add_missing_notification_types
Revises: add_translation_review_tool_toggle
Create Date: 2026-07-20
"""

from alembic import op


revision = 'add_missing_notification_types'
down_revision = 'add_translation_review_tool_toggle'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'assignment_sent_for_review'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'assignment_returned_for_revision'")
    op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'validation_questions'")


def downgrade():
    # PostgreSQL does not support removing enum values without rebuilding the type; left in place on downgrade.
    pass
