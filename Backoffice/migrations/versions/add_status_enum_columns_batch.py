"""Convert remaining varchar status columns to PostgreSQL enums.

Revision ID: add_status_enum_columns_batch
Revises: add_assignment_entity_status_enum
Create Date: 2026-06-03
"""

from alembic import op


revision = 'add_status_enum_columns_batch'
down_revision = 'add_assignment_entity_status_enum'
branch_labels = None
depends_on = None


def _create_enum(name: str, values: tuple[str, ...]) -> None:
    quoted = ", ".join(repr(v) for v in values)
    op.execute(f"CREATE TYPE {name} AS ENUM ({quoted})")


def _drop_enum(name: str) -> None:
    op.execute(f"DROP TYPE IF EXISTS {name}")


def _convert_column(
    table: str,
    column: str,
    enum_name: str,
    *,
    varchar_len: int | None = None,
    default: str | None = None,
    nullable: bool = True,
    normalize_sql: list[str] | None = None,
) -> None:
    for sql in normalize_sql or []:
        op.execute(sql)

    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(
        f"""
        ALTER TABLE {table}
        ALTER COLUMN {column} TYPE {enum_name}
        USING {column}::{enum_name}
        """
    )
    if default is not None:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'::{enum_name}"
        )
    if not nullable:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")


def _revert_column(
    table: str,
    column: str,
    *,
    varchar_len: int = 50,
    default: str | None = None,
) -> None:
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(
        f"""
        ALTER TABLE {table}
        ALTER COLUMN {column} TYPE VARCHAR({varchar_len})
        USING {column}::text
        """
    )
    if default is not None:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")


def upgrade():
    # --- submitted_document.status ---
    _create_enum('documentstatus', ('Pending', 'Approved', 'Rejected'))
    _convert_column(
        'submitted_document',
        'status',
        'documentstatus',
        default='Pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE submitted_document SET status = 'Pending'
            WHERE status IS NULL OR TRIM(status) = ''
            """,
            """
            UPDATE submitted_document SET status = 'Pending'
            WHERE LOWER(TRIM(status)) = 'pending'
            """,
            """
            UPDATE submitted_document SET status = 'Approved'
            WHERE LOWER(TRIM(status)) = 'approved'
            """,
            """
            UPDATE submitted_document SET status = 'Rejected'
            WHERE LOWER(TRIM(status)) = 'rejected'
            """,
            """
            UPDATE submitted_document SET status = 'Pending'
            WHERE status NOT IN ('Pending', 'Approved', 'Rejected')
            """,
        ],
    )

    # --- country_access_request.status ---
    _create_enum('countryaccessrequeststatus', ('pending', 'approved', 'rejected'))
    _convert_column(
        'country_access_request',
        'status',
        'countryaccessrequeststatus',
        default='pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE country_access_request SET status = 'pending'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN ('pending', 'approved', 'rejected')
            """,
            """
            UPDATE country_access_request SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- form_template_version.status ---
    _create_enum('formtemplateversionstatus', ('draft', 'published', 'archived'))
    _convert_column(
        'form_template_version',
        'status',
        'formtemplateversionstatus',
        default='draft',
        nullable=False,
        normalize_sql=[
            """
            UPDATE form_template_version SET status = 'draft'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN ('draft', 'published', 'archived')
            """,
            """
            UPDATE form_template_version SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- indicator_suggestion ---
    _create_enum(
        'indicatorsuggestiontype',
        ('correction', 'improvement', 'new_indicator', 'other'),
    )
    _create_enum(
        'indicatorsuggestionstatus',
        ('pending', 'reviewed', 'approved', 'rejected', 'implemented'),
    )
    _convert_column(
        'indicator_suggestion',
        'suggestion_type',
        'indicatorsuggestiontype',
        default='other',
        nullable=False,
        normalize_sql=[
            """
            UPDATE indicator_suggestion SET suggestion_type = 'other'
            WHERE suggestion_type IS NULL OR TRIM(suggestion_type) = ''
               OR LOWER(TRIM(suggestion_type)) NOT IN (
                   'correction', 'improvement', 'new_indicator', 'other'
               )
            """,
            """
            UPDATE indicator_suggestion SET suggestion_type = LOWER(TRIM(suggestion_type))
            WHERE suggestion_type IS NOT NULL
            """,
        ],
    )
    _convert_column(
        'indicator_suggestion',
        'status',
        'indicatorsuggestionstatus',
        default='pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE indicator_suggestion SET status = 'pending'
            WHERE status IS NULL OR TRIM(status) = ''
            """,
            """
            UPDATE indicator_suggestion SET status = 'pending'
            WHERE LOWER(TRIM(status)) IN ('pending', 'pending review')
               OR status IN ('Pending', 'Pending Review')
            """,
            """
            UPDATE indicator_suggestion SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
            """
            UPDATE indicator_suggestion SET status = 'pending'
            WHERE status NOT IN ('pending', 'reviewed', 'approved', 'rejected', 'implemented')
            """,
        ],
    )

    # --- notification_campaign.status ---
    _create_enum(
        'notificationcampaignstatus',
        ('draft', 'scheduled', 'sent', 'failed', 'cancelled'),
    )
    _convert_column(
        'notification_campaign',
        'status',
        'notificationcampaignstatus',
        default='draft',
        nullable=False,
        normalize_sql=[
            """
            UPDATE notification_campaign SET status = 'draft'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN (
                   'draft', 'scheduled', 'sent', 'failed', 'cancelled'
               )
            """,
            """
            UPDATE notification_campaign SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- email_delivery_log.status ---
    _create_enum('emaildeliverystatus', ('pending', 'sent', 'failed', 'retrying'))
    _convert_column(
        'email_delivery_log',
        'status',
        'emaildeliverystatus',
        default='pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE email_delivery_log SET status = 'pending'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN ('pending', 'sent', 'failed', 'retrying')
            """,
            """
            UPDATE email_delivery_log SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- ai_jobs / ai_job_items ---
    _create_enum(
        'aijobstatus',
        ('queued', 'running', 'completed', 'failed', 'cancel_requested', 'cancelled'),
    )
    _create_enum(
        'aijobitemstatus',
        ('queued', 'downloading', 'processing', 'completed', 'failed', 'cancelled'),
    )
    _convert_column(
        'ai_jobs',
        'status',
        'aijobstatus',
        default='queued',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_jobs SET status = 'queued'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN (
                   'queued', 'running', 'completed', 'failed', 'cancel_requested', 'cancelled'
               )
            """,
            """
            UPDATE ai_jobs SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )
    _convert_column(
        'ai_job_items',
        'status',
        'aijobitemstatus',
        default='queued',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_job_items SET status = 'queued'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN (
                   'queued', 'downloading', 'processing', 'completed', 'failed', 'cancelled'
               )
            """,
            """
            UPDATE ai_job_items SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- ai_documents.processing_status ---
    _create_enum(
        'aidocumentprocessingstatus',
        ('pending', 'processing', 'completed', 'failed'),
    )
    _convert_column(
        'ai_documents',
        'processing_status',
        'aidocumentprocessingstatus',
        default='pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_documents SET processing_status = 'pending'
            WHERE processing_status IS NULL OR TRIM(processing_status) = ''
               OR LOWER(TRIM(processing_status)) NOT IN (
                   'pending', 'processing', 'completed', 'failed'
               )
            """,
            """
            UPDATE ai_documents SET processing_status = LOWER(TRIM(processing_status))
            WHERE processing_status IS NOT NULL
            """,
        ],
    )

    # --- ai_reasoning_traces.status ---
    _create_enum(
        'aireasoningtracestatus',
        (
            'completed',
            'timeout',
            'error',
            'cost_limit_exceeded',
            'max_iterations_exceeded',
        ),
    )
    _convert_column(
        'ai_reasoning_traces',
        'status',
        'aireasoningtracestatus',
        default='completed',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_reasoning_traces SET status = 'completed'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN (
                   'completed', 'timeout', 'error',
                   'cost_limit_exceeded', 'max_iterations_exceeded'
               )
            """,
            """
            UPDATE ai_reasoning_traces SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )

    # --- ai_trace_reviews ---
    _create_enum(
        'aitracereviewstatus',
        ('pending', 'in_review', 'completed', 'dismissed'),
    )
    _create_enum(
        'aitracereviewverdict',
        ('correct', 'partially_correct', 'incorrect', 'needs_improvement'),
    )
    _convert_column(
        'ai_trace_reviews',
        'status',
        'aitracereviewstatus',
        default='pending',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_trace_reviews SET status = 'pending'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN (
                   'pending', 'in_review', 'completed', 'dismissed'
               )
            """,
            """
            UPDATE ai_trace_reviews SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )
    _convert_column(
        'ai_trace_reviews',
        'verdict',
        'aitracereviewverdict',
        nullable=True,
        normalize_sql=[
            """
            UPDATE ai_trace_reviews SET verdict = NULL
            WHERE verdict IS NOT NULL
              AND TRIM(verdict) = ''
            """,
            """
            UPDATE ai_trace_reviews SET verdict = LOWER(TRIM(verdict))
            WHERE verdict IS NOT NULL
            """,
            """
            UPDATE ai_trace_reviews SET verdict = NULL
            WHERE verdict IS NOT NULL
              AND verdict NOT IN (
                  'correct', 'partially_correct', 'incorrect', 'needs_improvement'
              )
            """,
        ],
    )

    # --- ai_formdata_validation ---
    _create_enum('aiformdatavalidationstatus', ('completed', 'failed', 'pending'))
    _create_enum('aiformdatavalidationverdict', ('good', 'discrepancy', 'uncertain'))
    _convert_column(
        'ai_formdata_validation',
        'status',
        'aiformdatavalidationstatus',
        default='completed',
        nullable=False,
        normalize_sql=[
            """
            UPDATE ai_formdata_validation SET status = 'completed'
            WHERE status IS NULL OR TRIM(status) = ''
               OR LOWER(TRIM(status)) NOT IN ('completed', 'failed', 'pending')
            """,
            """
            UPDATE ai_formdata_validation SET status = LOWER(TRIM(status))
            WHERE status IS NOT NULL
            """,
        ],
    )
    _convert_column(
        'ai_formdata_validation',
        'verdict',
        'aiformdatavalidationverdict',
        nullable=True,
        normalize_sql=[
            """
            UPDATE ai_formdata_validation SET verdict = NULL
            WHERE verdict IS NOT NULL AND TRIM(verdict) = ''
            """,
            """
            UPDATE ai_formdata_validation SET verdict = LOWER(TRIM(verdict))
            WHERE verdict IS NOT NULL
            """,
            """
            UPDATE ai_formdata_validation SET verdict = NULL
            WHERE verdict IS NOT NULL
              AND verdict NOT IN ('good', 'discrepancy', 'uncertain')
            """,
        ],
    )


def downgrade():
    _revert_column('ai_formdata_validation', 'verdict', varchar_len=32)
    _revert_column('ai_formdata_validation', 'status', varchar_len=32, default='completed')
    _drop_enum('aiformdatavalidationverdict')
    _drop_enum('aiformdatavalidationstatus')

    _revert_column('ai_trace_reviews', 'verdict', varchar_len=30)
    _revert_column('ai_trace_reviews', 'status', varchar_len=30, default='pending')
    _drop_enum('aitracereviewverdict')
    _drop_enum('aitracereviewstatus')

    _revert_column('ai_reasoning_traces', 'status', varchar_len=50, default='completed')
    _drop_enum('aireasoningtracestatus')

    _revert_column('ai_documents', 'processing_status', varchar_len=50, default='pending')
    _drop_enum('aidocumentprocessingstatus')

    _revert_column('ai_job_items', 'status', varchar_len=32, default='queued')
    _revert_column('ai_jobs', 'status', varchar_len=32, default='queued')
    _drop_enum('aijobitemstatus')
    _drop_enum('aijobstatus')

    _revert_column('email_delivery_log', 'status', varchar_len=50, default='pending')
    _drop_enum('emaildeliverystatus')

    _revert_column('notification_campaign', 'status', varchar_len=20, default='draft')
    _drop_enum('notificationcampaignstatus')

    _revert_column('indicator_suggestion', 'status', varchar_len=20, default='Pending')
    _revert_column('indicator_suggestion', 'suggestion_type', varchar_len=50)
    _drop_enum('indicatorsuggestionstatus')
    _drop_enum('indicatorsuggestiontype')

    _revert_column('form_template_version', 'status', varchar_len=20, default='draft')
    _drop_enum('formtemplateversionstatus')

    _revert_column('country_access_request', 'status', varchar_len=20, default='pending')
    _drop_enum('countryaccessrequeststatus')

    _revert_column('submitted_document', 'status', varchar_len=50, default='Pending')
    _drop_enum('documentstatus')
