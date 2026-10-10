"""Enforce template version integrity in the database

Adds partial unique indexes so the states the deploy refuses can no longer be created:

* one draft per template
* one ``stable_key`` per field within a version
* one ``stable_key`` per section within a version

Run ``python scripts/ops/audit_template_versions.py`` first. The migration re-checks the data
and aborts, listing the offending rows, instead of failing half-way through.

Revision ID: add_template_version_integrity
Revises: add_ns_category_text
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa


revision = "add_template_version_integrity"
down_revision = "add_ns_category_text"
branch_labels = None
depends_on = None


_CHECKS = (
    (
        "uq_form_template_version_single_draft",
        "form_template_version",
        "template_id",
        "status = 'draft'",
        "SELECT template_id AS scope, count(*) AS rows_found, array_agg(id) AS row_ids "
        "FROM form_template_version WHERE status = 'draft' "
        "GROUP BY template_id HAVING count(*) > 1",
    ),
    (
        "uq_form_item_version_stable_key",
        "form_item",
        "version_id, stable_key",
        "stable_key IS NOT NULL",
        "SELECT version_id || ':' || stable_key AS scope, count(*) AS rows_found, array_agg(id) AS row_ids "
        "FROM form_item WHERE stable_key IS NOT NULL "
        "GROUP BY version_id, stable_key HAVING count(*) > 1",
    ),
    (
        "uq_form_section_version_stable_key",
        "form_section",
        "version_id, stable_key",
        "stable_key IS NOT NULL",
        "SELECT version_id || ':' || stable_key AS scope, count(*) AS rows_found, array_agg(id) AS row_ids "
        "FROM form_section WHERE stable_key IS NOT NULL "
        "GROUP BY version_id, stable_key HAVING count(*) > 1",
    ),
)


def upgrade():
    bind = op.get_bind()
    problems = []
    for index_name, table, _columns, _predicate, violation_sql in _CHECKS:
        rows = bind.execute(sa.text(violation_sql + " LIMIT 20")).fetchall()
        for scope, rows_found, row_ids in rows:
            problems.append(f"{table} [{index_name}] scope={scope} rows={rows_found} ids={list(row_ids)}")
    if problems:
        raise RuntimeError(
            "Cannot add template version integrity constraints: existing data violates them.\n"
            "Run `python scripts/ops/audit_template_versions.py`, fix the findings and retry.\n"
            + "\n".join(problems)
        )

    for index_name, table, columns, predicate, _violation_sql in _CHECKS:
        op.create_index(
            index_name,
            table,
            [column.strip() for column in columns.split(",")],
            unique=True,
            postgresql_where=sa.text(predicate),
        )


def downgrade():
    for index_name, table, _columns, _predicate, _violation_sql in reversed(_CHECKS):
        op.drop_index(index_name, table_name=table)
