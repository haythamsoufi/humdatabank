"""Shared assignment settings for each project.

Revision ID: add_project_assignment
Revises: add_dref_monitoring
Create Date: 2026-11-19

One ``project_assignment`` row holds the options an admin edits once per project
(PDF/Excel, review, access groups). Existing project-cycle reports seed that row:
the majority value of each flag, and the published template's export flags when
no report has turned them on.
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "add_project_assignment"
down_revision = "add_dref_monitoring"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

_BOOL_FLAGS = (
    "enable_export_pdf",
    "enable_export_excel",
    "enable_import_excel",
    "email_attach_pdf",
    "email_attach_excel",
    "enable_page_submission",
    "enable_offline_download",
    "requires_delegation_review",
)

_TEMPLATE_SEED_FLAGS = ("enable_export_pdf", "enable_export_excel", "enable_import_excel")


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "t", "true", "yes"}
    return bool(value)


def _majority_bool(values) -> bool:
    if not values:
        return False
    trues = sum(1 for value in values if _truthy(value))
    return trues > (len(values) - trues)


def _majority_value(values, default):
    counts = {}
    for value in values:
        if value in (None, ""):
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return default
    return max(counts.items(), key=lambda item: (item[1], str(item[0])))[0]


def _as_id_list(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    ids = []
    for value in raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _ids_on_majority(per_report):
    """Ids present on more than half of the reports."""
    if not per_report:
        return []
    need = len(per_report) / 2
    counts = {}
    for ids in per_report:
        for role_id in set(ids):
            counts[role_id] = counts.get(role_id, 0) + 1
    return sorted(role_id for role_id, count in counts.items() if count > need)


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("project_assignment"):
        return
    if not insp.has_table("project"):
        return

    op.create_table(
        "project_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("custom_name", sa.String(length=200), nullable=True),
        sa.Column("custom_name_translations", _JSON, nullable=True),
        sa.Column("data_owner_id", sa.Integer(), nullable=True),
        sa.Column("requires_delegation_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enable_page_submission", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enable_offline_download", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enable_export_excel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enable_import_excel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enable_export_pdf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_attach_pdf", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_attach_excel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "submission_review_recipient_mode",
            sa.String(length=20),
            nullable=False,
            server_default="fds_member",
        ),
        sa.Column("allowed_role_ids", _JSON, nullable=True),
        sa.Column("review_recipient_user_ids", _JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["data_owner_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", name="uq_project_assignment_project"),
    )
    op.create_index("ix_project_assignment_data_owner", "project_assignment", ["data_owner_id"])

    if not insp.has_table("assigned_form"):
        return

    flag_sql = ", ".join(f"af.{name}" for name in _BOOL_FLAGS)
    reports = bind.execute(
        sa.text(
            f"""
            SELECT af.id, af.project_id, af.template_id, af.data_owner_id,
                   af.submission_review_recipient_mode, {flag_sql}
            FROM assigned_form af
            WHERE af.scope = 'project_cycle' AND af.project_id IS NOT NULL
            """
        )
    ).mappings().all()
    if not reports:
        return

    template_flags = {}
    if insp.has_table("form_template") and insp.has_table("form_template_version"):
        version_cols = {c["name"] for c in insp.get_columns("form_template_version")}
        select_flags = []
        for name in _TEMPLATE_SEED_FLAGS:
            if name in version_cols:
                select_flags.append(f"ftv.{name} AS {name}")
            else:
                select_flags.append(f"FALSE AS {name}")
        for row in bind.execute(
            sa.text(
                f"""
                SELECT ft.id AS template_id, {", ".join(select_flags)}
                FROM form_template ft
                JOIN form_template_version ftv ON ftv.id = ft.published_version_id
                """
            )
        ).mappings():
            template_flags[int(row["template_id"])] = row

    roles_by_form = {}
    if insp.has_table("assigned_form_allowed_role"):
        for row in bind.execute(
            sa.text("SELECT assigned_form_id, role_id FROM assigned_form_allowed_role")
        ).mappings():
            roles_by_form.setdefault(int(row["assigned_form_id"]), []).append(int(row["role_id"]))

    reviewers_by_form = {}
    if insp.has_table("assigned_form_submission_review_recipient"):
        for row in bind.execute(
            sa.text(
                "SELECT assigned_form_id, user_id FROM assigned_form_submission_review_recipient"
            )
        ).mappings():
            reviewers_by_form.setdefault(int(row["assigned_form_id"]), []).append(int(row["user_id"]))

    by_project = {}
    for row in reports:
        by_project.setdefault(int(row["project_id"]), []).append(row)

    insert_rows = []
    for project_id, group in by_project.items():
        values = {
            "project_id": project_id,
            "data_owner_id": _majority_value([row["data_owner_id"] for row in group], None),
            "submission_review_recipient_mode": _majority_value(
                [row["submission_review_recipient_mode"] for row in group],
                "fds_member",
            )
            or "fds_member",
            "allowed_role_ids": _ids_on_majority(
                [roles_by_form.get(int(row["id"]), []) for row in group]
            )
            or None,
            "review_recipient_user_ids": _ids_on_majority(
                [reviewers_by_form.get(int(row["id"]), []) for row in group]
            )
            or None,
        }
        for name in _BOOL_FLAGS:
            chosen = _majority_bool([row[name] for row in group])
            if (
                not chosen
                and name in _TEMPLATE_SEED_FLAGS
                and not any(_truthy(row[name]) for row in group)
            ):
                chosen = any(
                    _truthy((template_flags.get(int(row["template_id"])) or {}).get(name))
                    for row in group
                    if row["template_id"] is not None
                )
            values[name] = bool(chosen)
        insert_rows.append(values)

    if insert_rows:
        op.bulk_insert(
            sa.table(
                "project_assignment",
                sa.column("project_id", sa.Integer),
                sa.column("data_owner_id", sa.Integer),
                sa.column("submission_review_recipient_mode", sa.String),
                sa.column("allowed_role_ids", _JSON),
                sa.column("review_recipient_user_ids", _JSON),
                *[sa.column(name, sa.Boolean) for name in _BOOL_FLAGS],
            ),
            insert_rows,
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("project_assignment"):
        return
    op.drop_index("ix_project_assignment_data_owner", table_name="project_assignment")
    op.drop_table("project_assignment")
