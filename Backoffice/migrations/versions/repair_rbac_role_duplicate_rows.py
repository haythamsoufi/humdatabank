"""Repair duplicate rbac_role/rbac_role_permission rows and restore missing RBAC constraints

Investigation found that on at least one environment, `rbac_role` had lost its
PRIMARY KEY (id) / UNIQUE (code) constraints, `rbac_role_permission` had lost its
PRIMARY KEY (role_id, permission_id) and both foreign keys, and `rbac_user_role` had
lost its foreign key to `rbac_role.id`. Nothing in the migration history (see
add_rbac_tables, which defines all of the above) ever drops them, so they must have
been removed out-of-band -- most likely as an ad hoc workaround for a duplicate-key
error rather than a fix for the actual cause.

Without those constraints, the `RbacRole.query.filter_by(code=...)`-style "get or
create" checks used by rbac_seed_service / seeding.py are racy: nothing in the
database stops two processes/requests from both concluding "this code doesn't exist
yet" and inserting it. Over time this produced two physical `rbac_role` rows for
nearly every baseline role code, with real `rbac_user_role` assignments split
unpredictably across both rows for the same logical role (e.g. an "Admin: Full" role
split across 2 role ids, with different admins assigned to each) and duplicated /
orphaned `rbac_role_permission` link rows. The user management UI renders one
checkbox per `rbac_role` row and groups them by RBAC role code, so this surfaced as
duplicate-looking / silently-empty role groups, and it made `flask rbac seed` itself
fail outright with a SQLAlchemy StaleDataError (an UPDATE by id matched 2 rows
instead of 1).

This migration is defensive and idempotent: on environments where the constraints
are already intact (and therefore have no duplicates), every DELETE/UPDATE below
matches zero rows and every constraint-adding block is skipped because the
constraint already exists.

Revision ID: repair_rbac_role_duplicate_rows
Revises: add_missing_notification_types
Create Date: 2026-07-20
"""

from alembic import op


revision = 'repair_rbac_role_duplicate_rows'
down_revision = 'add_missing_notification_types'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Collapse literal duplicate physical rows that share the same id (only possible
    #    because rbac_role.id currently has no PRIMARY KEY enforcing uniqueness).
    op.execute("""
        DELETE FROM rbac_role a
        USING rbac_role b
        WHERE a.ctid < b.ctid
          AND a.id = b.id
    """)

    # 2) Merge same-code-different-id duplicates: pick the lowest id per code as the
    #    survivor, move rbac_user_role assignments and role-principal rbac_access_grant
    #    rows from every other id onto it (skipping any that would collide with an
    #    assignment/grant the survivor already has), then drop the losers' role rows.
    #    Their rbac_role_permission links are dropped (not merged) because they are
    #    fully re-derived from code by `flask rbac seed` / the deferred auto-seed right
    #    after this migration runs.
    op.execute("""
        CREATE TEMP TABLE _rbac_role_merge_map AS
        SELECT code, MIN(id) AS keep_id, unnest(array_agg(id)) AS any_id
        FROM rbac_role
        GROUP BY code
    """)
    op.execute("""
        CREATE TEMP TABLE _rbac_role_losers AS
        SELECT DISTINCT any_id AS loser_id, keep_id
        FROM _rbac_role_merge_map
        WHERE any_id <> keep_id
    """)

    op.execute("""
        UPDATE rbac_user_role ur
        SET role_id = m.keep_id
        FROM _rbac_role_losers m
        WHERE ur.role_id = m.loser_id
          AND NOT EXISTS (
              SELECT 1 FROM rbac_user_role ur2
              WHERE ur2.user_id = ur.user_id AND ur2.role_id = m.keep_id
          )
    """)
    op.execute("""
        DELETE FROM rbac_user_role ur
        USING _rbac_role_losers m
        WHERE ur.role_id = m.loser_id
    """)

    op.execute("""
        UPDATE rbac_access_grant g
        SET principal_id = m.keep_id
        FROM _rbac_role_losers m
        WHERE g.principal_type = 'role'
          AND g.principal_id = m.loser_id
          AND NOT EXISTS (
              SELECT 1 FROM rbac_access_grant g2
              WHERE g2.principal_type = 'role'
                AND g2.principal_id = m.keep_id
                AND g2.permission_id = g.permission_id
                AND g2.scope_kind = g.scope_kind
                AND COALESCE(g2.entity_type, '') = COALESCE(g.entity_type, '')
                AND COALESCE(g2.entity_id, -1) = COALESCE(g.entity_id, -1)
                AND COALESCE(g2.template_id, -1) = COALESCE(g.template_id, -1)
                AND COALESCE(g2.assigned_form_id, -1) = COALESCE(g.assigned_form_id, -1)
          )
    """)
    op.execute("""
        DELETE FROM rbac_access_grant g
        USING _rbac_role_losers m
        WHERE g.principal_type = 'role' AND g.principal_id = m.loser_id
    """)

    op.execute("""
        DELETE FROM rbac_role_permission rp
        USING _rbac_role_losers m
        WHERE rp.role_id = m.loser_id
    """)

    op.execute("""
        DELETE FROM rbac_role r
        USING _rbac_role_losers m
        WHERE r.id = m.loser_id
    """)

    op.execute("DROP TABLE _rbac_role_losers")
    op.execute("DROP TABLE _rbac_role_merge_map")

    # 3) Dedupe exact-duplicate (role_id, permission_id) link rows regardless of source.
    op.execute("""
        DELETE FROM rbac_role_permission a
        USING rbac_role_permission b
        WHERE a.ctid < b.ctid
          AND a.role_id = b.role_id
          AND a.permission_id = b.permission_id
    """)

    # 4) Drop any remaining orphaned link rows so the foreign keys below can be added
    #    (e.g. permission rows deleted/renamed by an older code version without the
    #    matching link cleanup, back when there was no FK to stop that from happening).
    op.execute("""
        DELETE FROM rbac_role_permission rp
        WHERE NOT EXISTS (SELECT 1 FROM rbac_role r WHERE r.id = rp.role_id)
           OR NOT EXISTS (SELECT 1 FROM rbac_permission p WHERE p.id = rp.permission_id)
    """)
    op.execute("""
        DELETE FROM rbac_user_role ur
        WHERE NOT EXISTS (SELECT 1 FROM rbac_role r WHERE r.id = ur.role_id)
    """)

    # 5) Restore the constraints defined in add_rbac_tables (idempotent: skipped on
    #    environments that never lost them).
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rbac_role_pkey') THEN
                ALTER TABLE rbac_role ADD CONSTRAINT rbac_role_pkey PRIMARY KEY (id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_rbac_role_code') THEN
                ALTER TABLE rbac_role ADD CONSTRAINT uq_rbac_role_code UNIQUE (code);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_rbac_role_code') THEN
                CREATE INDEX ix_rbac_role_code ON rbac_role (code);
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rbac_role_permission_pkey') THEN
                ALTER TABLE rbac_role_permission
                    ADD CONSTRAINT rbac_role_permission_pkey PRIMARY KEY (role_id, permission_id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rbac_role_permission_role_id_fkey') THEN
                ALTER TABLE rbac_role_permission
                    ADD CONSTRAINT rbac_role_permission_role_id_fkey
                    FOREIGN KEY (role_id) REFERENCES rbac_role (id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rbac_role_permission_permission_id_fkey') THEN
                ALTER TABLE rbac_role_permission
                    ADD CONSTRAINT rbac_role_permission_permission_id_fkey
                    FOREIGN KEY (permission_id) REFERENCES rbac_permission (id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_rbac_role_permission_role') THEN
                CREATE INDEX ix_rbac_role_permission_role ON rbac_role_permission (role_id);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_rbac_role_permission_permission') THEN
                CREATE INDEX ix_rbac_role_permission_permission ON rbac_role_permission (permission_id);
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'rbac_user_role_role_id_fkey') THEN
                ALTER TABLE rbac_user_role
                    ADD CONSTRAINT rbac_user_role_role_id_fkey
                    FOREIGN KEY (role_id) REFERENCES rbac_role (id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)


def downgrade():
    # Data merge/dedup is irreversible; leave data and restored constraints in place.
    pass
