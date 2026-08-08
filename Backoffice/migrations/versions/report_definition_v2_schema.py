"""Add report_definition_revision table and migrate report definitions to schema v2."""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "report_definition_v2_schema"
down_revision = "add_ai_doc_processing_hb"
branch_labels = None
depends_on = None


def _migrate_definition_v1_to_v2(definition: dict | None) -> dict:
    """Inline migration helper (mirrors app.services.reports.schema.migrate_v1_to_v2)."""
    if not definition:
        definition = {}
    if int(definition.get("schema_version") or 0) >= 2:
        return definition

    lang = "en"
    out = {
        "schema_version": 2,
        "languages": ["en"],
        "default_language": lang,
        "theme": {
            "primary_color": "#0d9488",
            "font_family": "Inter, system-ui, sans-serif",
        },
        "filters": definition.get("filters")
        or {
            "template_ids": [],
            "period_names": [],
            "country_ids": [],
            "assignment_statuses": ["submitted", "approved"],
            "include_public_submissions": False,
        },
        "sections": [],
    }

    columns = 12
    for section in definition.get("sections") or []:
        sec = {
            "id": section.get("id") or "section",
            "order": int(section.get("order") or 0),
            "title_translations": (
                section.get("title_translations")
                or ({lang: section["title"].strip()} if section.get("title") else {})
            ),
            "footnote_translations": (
                section.get("footnote_translations")
                or ({lang: section["footnote"].strip()} if section.get("footnote") else {})
            ),
            "grid": section.get("grid") or {"columns": columns, "row_height": 80},
            "widgets": [],
        }
        if section.get("dynamic_indicators"):
            dyn = dict(section["dynamic_indicators"])
            footnotes = dyn.get("indicator_footnotes")
            if isinstance(footnotes, dict):
                converted = {}
                for key, val in footnotes.items():
                    if isinstance(val, dict):
                        converted[str(key)] = val
                    elif isinstance(val, str) and val.strip():
                        converted[str(key)] = {lang: val.strip()}
                dyn["indicator_footnotes"] = converted
            if not dyn.get("default_widget_layout"):
                dyn["default_widget_layout"] = {"x": 0, "y": 0, "w": columns, "h": 4}
            sec["dynamic_indicators"] = dyn

        y = 0
        for widget in section.get("widgets") or []:
            wtype = widget.get("type") or "text"
            h = {"kpi": 2, "divider": 1, "text": 3, "image": 4, "embed": 4, "map": 5, "indicator_dashboard": 6, "table": 4}.get(wtype, 4)
            w = {
                "id": widget.get("id") or "widget",
                "type": wtype,
                "title_translations": (
                    widget.get("title_translations")
                    or ({lang: widget["title"].strip()} if widget.get("title") else {})
                ),
                "footnote_translations": (
                    widget.get("footnote_translations")
                    or ({lang: widget["footnote"].strip()} if widget.get("footnote") else {})
                ),
                "layout": widget.get("layout") or {"x": 0, "y": y, "w": columns, "h": h},
            }
            y += h
            if widget.get("data_source"):
                w["data_source"] = widget["data_source"]
            if widget.get("chart_options"):
                w["chart_options"] = widget["chart_options"]
            if widget.get("content_translations"):
                w["content_translations"] = widget["content_translations"]
            elif widget.get("content"):
                w["content_translations"] = {lang: widget["content"].strip()}
            sec["widgets"].append(w)
        out["sections"].append(sec)

    out["sections"].sort(key=lambda s: int(s.get("order") or 0))
    return out


def upgrade():
    op.create_table(
        "report_definition_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("report_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "definition_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_report_definition_revision_report_id", "report_definition_revision", ["report_id"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, definition_json, schema_version FROM report_definition")).fetchall()
    for row_id, definition_json, schema_version in rows:
        if isinstance(definition_json, str):
            definition_json = json.loads(definition_json)
        if int(schema_version or 0) >= 2 and int((definition_json or {}).get("schema_version") or 0) >= 2:
            continue
        migrated = _migrate_definition_v1_to_v2(definition_json or {})
        conn.execute(
            sa.text(
                "UPDATE report_definition SET definition_json = CAST(:definition AS jsonb), schema_version = 2 WHERE id = :id"
            ),
            {"definition": json.dumps(migrated), "id": row_id},
        )


def downgrade():
    op.drop_index("ix_report_definition_revision_report_id", table_name="report_definition_revision")
    op.drop_table("report_definition_revision")
