"""Store FDRS DON code and zone on national_societies, and drop fdrs_society.

Revision ID: fdrs_fields_on_ns
Revises: add_user_assignment_template_access
Create Date: 2026-10-19

The public FDRS site identifies a society by DON code. Those fields belong on
``national_societies``. Rows already loaded into ``fdrs_society`` are copied
onto the National Society for the same country, then the extra table is removed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "fdrs_fields_on_ns"
down_revision = "add_user_assignment_template_access"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("fdrs_don_code", sa.String(length=20)),
    ("fdrs_zone_code", sa.String(length=2)),
    ("fdrs_zone_name", sa.String(length=100)),
    ("latitude", sa.Float()),
    ("longitude", sa.Float()),
    ("admission_date", sa.Date()),
    ("admission_date_note", sa.Text()),
    ("currency_code", sa.String(length=3)),
    ("fdrs_search_string", sa.Text()),
    ("website", sa.Text()),
    ("facebook", sa.Text()),
    ("twitter", sa.Text()),
    ("other_social", sa.Text()),
)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("national_societies")}
    with op.batch_alter_table("national_societies", schema=None) as batch:
        for name, type_ in _COLUMNS:
            if name not in existing:
                batch.add_column(sa.Column(name, type_, nullable=True))
    if "ix_national_societies_fdrs_don_code" not in {
        idx["name"] for idx in inspector.get_indexes("national_societies")
    }:
        op.create_index(
            "ix_national_societies_fdrs_don_code",
            "national_societies",
            ["fdrs_don_code"],
            unique=True,
        )
    if "ix_national_societies_fdrs_zone_code" not in {
        idx["name"] for idx in inspect(bind).get_indexes("national_societies")
    }:
        op.create_index(
            "ix_national_societies_fdrs_zone_code",
            "national_societies",
            ["fdrs_zone_code"],
        )

    if "fdrs_society" in inspector.get_table_names():
        bind.execute(
            sa.text(
                """
                UPDATE national_societies AS ns
                SET fdrs_don_code = src.don_code,
                    fdrs_zone_code = src.zone_code,
                    fdrs_zone_name = src.zone_name,
                    latitude = src.latitude,
                    longitude = src.longitude,
                    admission_date = src.admission_date,
                    admission_date_note = src.admission_date_note,
                    currency_code = src.currency_code,
                    fdrs_search_string = src.search_string,
                    website = src.website,
                    facebook = src.facebook,
                    twitter = src.twitter,
                    other_social = src.other_social
                FROM fdrs_society AS src
                WHERE src.country_id = ns.country_id
                  AND ns.fdrs_don_code IS NULL
                  AND ns.id = (
                      SELECT id FROM national_societies
                      WHERE country_id = src.country_id
                      ORDER BY is_active DESC, id ASC
                      LIMIT 1
                  )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO national_societies (
                    name, country_id, status, is_active, created_at, updated_at,
                    fdrs_don_code, fdrs_zone_code, fdrs_zone_name,
                    latitude, longitude, admission_date, admission_date_note,
                    currency_code, fdrs_search_string, website, facebook, twitter, other_social
                )
                SELECT
                    src.name, src.country_id, 'Active', true, NOW(), NOW(),
                    src.don_code, src.zone_code, src.zone_name,
                    src.latitude, src.longitude, src.admission_date, src.admission_date_note,
                    src.currency_code, src.search_string, src.website, src.facebook, src.twitter, src.other_social
                FROM fdrs_society AS src
                WHERE src.country_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM national_societies ns
                      WHERE ns.fdrs_don_code = src.don_code
                         OR ns.country_id = src.country_id
                  )
                """
            )
        )
        op.drop_index("ix_fdrs_society_zone_code", table_name="fdrs_society")
        op.drop_index("ix_fdrs_society_country_id", table_name="fdrs_society")
        op.drop_index("ix_fdrs_society_don_code", table_name="fdrs_society")
        op.drop_table("fdrs_society")


def downgrade():
    op.drop_index("ix_national_societies_fdrs_zone_code", table_name="national_societies")
    op.drop_index("ix_national_societies_fdrs_don_code", table_name="national_societies")
    with op.batch_alter_table("national_societies", schema=None) as batch:
        for name, _type in reversed(_COLUMNS):
            batch.drop_column(name)
