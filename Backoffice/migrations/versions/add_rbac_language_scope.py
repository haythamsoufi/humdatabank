"""Add language scope to RBAC access grants for inline translation review

Revision ID: add_rbac_language_scope
Revises: add_plugin_data_table
Create Date: 2026-07-15 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_rbac_language_scope'
down_revision = 'add_plugin_data_table'
branch_labels = None
depends_on = None


# Guard drops with IF EXISTS: some environments bootstrap this table via
# ``db.create_all()`` (which only creates the plain btree indexes declared on
# the model, not the Alembic-only partial unique indexes/constraints), so
# these objects may legitimately be absent even though earlier migrations
# nominally "ran".
def _drop_index_if_exists(bind, name: str) -> None:
    bind.execute(sa.text(f'DROP INDEX IF EXISTS "{name}"'))


def _drop_constraint_if_exists(bind, table: str, name: str) -> None:
    bind.execute(sa.text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{name}"'))


def upgrade():
    bind = op.get_bind()

    op.add_column(
        'rbac_access_grant',
        sa.Column('language_code', sa.String(length=10), nullable=True),
    )

    # Drop constraints/indexes that will be recreated with language scope support.
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_global')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_entity')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_template')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_assignment')
    _drop_constraint_if_exists(bind, 'rbac_access_grant', 'ck_rbac_access_grant_scope_payload')
    _drop_constraint_if_exists(bind, 'rbac_access_grant', 'ck_rbac_access_grant_scope_kind')

    op.create_check_constraint(
        'ck_rbac_access_grant_scope_kind',
        'rbac_access_grant',
        "scope_kind IN ('global','entity','template','assignment','language')",
    )
    op.create_check_constraint(
        'ck_rbac_access_grant_scope_payload',
        'rbac_access_grant',
        """
        (
          (scope_kind = 'global'
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND assigned_form_id IS NULL AND language_code IS NULL)
          OR
          (scope_kind = 'entity'
            AND entity_type IS NOT NULL AND entity_type <> '' AND entity_id IS NOT NULL
            AND template_id IS NULL AND assigned_form_id IS NULL AND language_code IS NULL)
          OR
          (scope_kind = 'template'
            AND template_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND assigned_form_id IS NULL AND language_code IS NULL)
          OR
          (scope_kind = 'assignment'
            AND assigned_form_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND language_code IS NULL)
          OR
          (scope_kind = 'language'
            AND language_code IS NOT NULL AND language_code <> ''
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND assigned_form_id IS NULL)
        )
        """,
    )

    _drop_index_if_exists(bind, 'uq_rbac_access_grant_language')
    _drop_index_if_exists(bind, 'ix_rbac_access_grant_scope_language')

    op.create_index(
        'uq_rbac_access_grant_global',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'global'"),
    )
    op.create_index(
        'uq_rbac_access_grant_entity',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'entity_type', 'entity_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'entity'"),
    )
    op.create_index(
        'uq_rbac_access_grant_template',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'template_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'template'"),
    )
    op.create_index(
        'uq_rbac_access_grant_assignment',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'assigned_form_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'assignment'"),
    )
    op.create_index(
        'uq_rbac_access_grant_language',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'language_code'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'language'"),
    )
    op.create_index(
        'ix_rbac_access_grant_scope_language',
        'rbac_access_grant',
        ['scope_kind', 'language_code'],
        unique=False,
    )

    # Best-effort migration from the short-lived translator_language_assignment table, if present.
    inspector = sa.inspect(bind)
    if 'translator_language_assignment' in inspector.get_table_names():
        perm_id = bind.execute(
            sa.text("SELECT id FROM rbac_permission WHERE code = 'translations.review.use' LIMIT 1")
        ).scalar()
        if perm_id:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO rbac_access_grant (
                        principal_type, principal_id, permission_id, scope_kind,
                        language_code, effect, created_at
                    )
                    SELECT
                        'user',
                        t.user_id,
                        :perm_id,
                        'language',
                        lower(t.language_code),
                        'allow',
                        COALESCE(t.created_at, CURRENT_TIMESTAMP)
                    FROM translator_language_assignment t
                    WHERE lower(t.language_code) <> 'en'
                      AND NOT EXISTS (
                        SELECT 1 FROM rbac_access_grant g
                        WHERE g.principal_type = 'user'
                          AND g.principal_id = t.user_id
                          AND g.permission_id = :perm_id
                          AND g.scope_kind = 'language'
                          AND lower(g.language_code) = lower(t.language_code)
                      )
                    """
                ),
                {'perm_id': int(perm_id)},
            )
        op.drop_table('translator_language_assignment')


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM rbac_access_grant WHERE scope_kind = 'language'")
    )

    _drop_index_if_exists(bind, 'ix_rbac_access_grant_scope_language')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_language')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_assignment')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_template')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_entity')
    _drop_index_if_exists(bind, 'uq_rbac_access_grant_global')
    _drop_constraint_if_exists(bind, 'rbac_access_grant', 'ck_rbac_access_grant_scope_payload')
    _drop_constraint_if_exists(bind, 'rbac_access_grant', 'ck_rbac_access_grant_scope_kind')

    op.create_check_constraint(
        'ck_rbac_access_grant_scope_kind',
        'rbac_access_grant',
        "scope_kind IN ('global','entity','template','assignment')",
    )
    op.create_check_constraint(
        'ck_rbac_access_grant_scope_payload',
        'rbac_access_grant',
        """
        (
          (scope_kind = 'global'
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'entity'
            AND entity_type IS NOT NULL AND entity_type <> '' AND entity_id IS NOT NULL
            AND template_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'template'
            AND template_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND assigned_form_id IS NULL)
          OR
          (scope_kind = 'assignment'
            AND assigned_form_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL)
        )
        """,
    )

    op.create_index(
        'uq_rbac_access_grant_global',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'global'"),
    )
    op.create_index(
        'uq_rbac_access_grant_entity',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'entity_type', 'entity_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'entity'"),
    )
    op.create_index(
        'uq_rbac_access_grant_template',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'template_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'template'"),
    )
    op.create_index(
        'uq_rbac_access_grant_assignment',
        'rbac_access_grant',
        ['principal_type', 'principal_id', 'permission_id', 'assigned_form_id'],
        unique=True,
        postgresql_where=sa.text("scope_kind = 'assignment'"),
    )

    op.drop_column('rbac_access_grant', 'language_code')
