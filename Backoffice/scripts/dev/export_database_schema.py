#!/usr/bin/env python3
"""
Export Backoffice PostgreSQL schema (from SQLAlchemy metadata) for architecture review.

Generates:
  - docs/architecture/database-schema.md           — human-readable reference (share as PDF/Word)
  - docs/architecture/database-schema-catalog.csv  — table/column catalog for Excel
  - docs/architecture/database-schema.html         — interactive browser viewer (single file)

Run from Backoffice/:
  python scripts/dev/export_database_schema.py
  python scripts/dev/export_database_schema.py --output-dir docs/architecture
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
from _bootstrap import backoffice_dir, setup_cli_paths

_ROOT = setup_cli_paths(__file__)[0]
os.chdir(_ROOT)
if not os.environ.get("FLASK_APP"):
    os.environ["FLASK_APP"] = "run.py"
if not os.environ.get("FLASK_CONFIG"):
    os.environ["FLASK_CONFIG"] = "testing"

DEFAULT_OUTPUT_DIR = _ROOT / "docs" / "architecture"
GITHUB_BLOB_BASE = "https://github.com/IFRC-C2/IFRCNetworkDatabank/blob/main"

# Domain groupings for architecture reviewers (table name → domain label).
TABLE_DOMAINS: dict[str, str] = {
    # Identity & access
    "user": "Identity & access",
    "user_entity_permissions": "Identity & access",
    "password_reset_tokens": "Identity & access",
    "rbac_permission": "Identity & access",
    "rbac_role": "Identity & access",
    "rbac_role_permission": "Identity & access",
    "rbac_user_role": "Identity & access",
    "rbac_access_grant": "Identity & access",
    "api_keys": "Identity & access",
    "api_key_usage": "Identity & access",
    "api_usage": "Identity & access",
    # Geography & organization
    "country": "Geography & organization",
    "national_societies": "Geography & organization",
    "ns_branches": "Geography & organization",
    "ns_subbranches": "Geography & organization",
    "ns_localunits": "Geography & organization",
    "secretariat_divisions": "Geography & organization",
    "secretariat_regional_offices": "Geography & organization",
    "secretariat_cluster_offices": "Geography & organization",
    "secretariat_departments": "Geography & organization",
    "country_access_request": "Geography & organization",
    "country_attribute": "Geography & organization",
    "country_year_reference": "Geography & organization",
    # Form authoring
    "form_template": "Form authoring",
    "form_template_version": "Form authoring",
    "form_page": "Form authoring",
    "form_section": "Form authoring",
    "form_item": "Form authoring",
    "template_share": "Form authoring",
    "lookup_list": "Form authoring",
    "lookup_list_row": "Form authoring",
    "embed_content": "Form authoring",
    # Assignments & workflow
    "reporting_period": "Assignments & workflow",
    "assigned_form": "Assignments & workflow",
    "assignment_entity_status": "Assignments & workflow",
    "public_submission": "Assignments & workflow",
    # Submission data (answers)
    "form_data": "Submission data",
    "dynamic_indicator_data": "Submission data",
    "dynamic_section_context": "Submission data",
    "repeat_group_instance": "Submission data",
    "repeat_group_data": "Submission data",
    "plugin_data": "Submission data",
    # Indicator bank
    "indicator_bank": "Indicator bank",
    "indicator_bank_history": "Indicator bank",
    "indicator_bank_type": "Indicator bank",
    "indicator_bank_spef": "Indicator bank",
    "indicator_bank_unit": "Indicator bank",
    "indicator_suggestion": "Indicator bank",
    "indicator_bank_embeddings": "Indicator bank",
    "sector": "Indicator bank",
    "sub_sector": "Indicator bank",
    "common_word": "Indicator bank",
    # Documents & resources
    "submitted_document": "Documents & resources",
    "submitted_document_countries": "Documents & resources",
    "resource": "Documents & resources",
    "resource_subcategory": "Documents & resources",
    "resource_translation": "Documents & resources",
    # Notifications & communications
    "notification": "Notifications & communications",
    "notification_preferences": "Notifications & communications",
    "notification_campaign": "Notifications & communications",
    "email_delivery_log": "Notifications & communications",
    # Audit, security & telemetry
    "admin_action_log": "Audit & security",
    "security_event": "Audit & security",
    "entity_activity_log": "Audit & security",
    "user_login_log": "Audit & security",
    "user_activity_log": "Audit & security",
    "user_session_log": "Audit & security",
    "user_devices": "Audit & security",
    "system_settings": "Audit & security",
    "chatbot_telemetry": "Audit & security",
    # AI & RAG
    "ai_documents": "AI & RAG",
    "ai_document_countries": "AI & RAG",
    "ai_document_chunks": "AI & RAG",
    "ai_embeddings": "AI & RAG",
    "ai_conversation": "AI & RAG",
    "ai_message": "AI & RAG",
    "ai_reasoning_traces": "AI & RAG",
    "ai_tool_usage": "AI & RAG",
    "ai_trace_reviews": "AI & RAG",
    "ai_jobs": "AI & RAG",
    "ai_job_items": "AI & RAG",
    "ai_formdata_validation": "AI & RAG",
    "ai_term_concepts": "AI & RAG",
    "ai_term_glossary": "AI & RAG",
    "ai_term_concept_embeddings": "AI & RAG",
    # Data quality / validation
    "validation_question": "Data quality",
    "validation_dispatch_batch": "Data quality",
    "validation_threshold": "Data quality",
    "validation_kpi_check_type": "Data quality",
    "validation_question_template": "Data quality",
}

DOMAIN_ORDER = [
    "Identity & access",
    "Geography & organization",
    "Form authoring",
    "Assignments & workflow",
    "Submission data",
    "Indicator bank",
    "Documents & resources",
    "Notifications & communications",
    "Audit & security",
    "AI & RAG",
    "Data quality",
    "Other",
]

# Tables defined in Alembic migrations but without a SQLAlchemy model class.
SUPPLEMENTAL_TABLES: list[dict] = [
    {
        "name": "chatbot_telemetry",
        "domain": "Audit & security",
        "note": "Defined in migration add_chatbot_telemetry_table; no ORM model.",
        "columns": [
            {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True, "foreign_keys": []},
            {"name": "user_id", "type": "INTEGER", "nullable": False, "primary_key": False, "foreign_keys": []},
            {"name": "session_id", "type": "VARCHAR(255)", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "timestamp", "type": "TIMESTAMP WITHOUT TIME ZONE", "nullable": False, "primary_key": False, "foreign_keys": []},
            {"name": "message_length", "type": "INTEGER", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "language", "type": "VARCHAR(50)", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "page_context", "type": "TEXT", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "llm_provider", "type": "VARCHAR(50)", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "model_name", "type": "VARCHAR(100)", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "function_calls_made", "type": "TEXT", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "response_time_ms", "type": "DOUBLE PRECISION", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "success", "type": "BOOLEAN", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "error_type", "type": "VARCHAR(255)", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "input_tokens", "type": "INTEGER", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "output_tokens", "type": "INTEGER", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "estimated_cost_usd", "type": "DOUBLE PRECISION", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "response_length", "type": "INTEGER", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "used_provenance", "type": "BOOLEAN", "nullable": True, "primary_key": False, "foreign_keys": []},
            {"name": "created_at", "type": "TIMESTAMP WITHOUT TIME ZONE", "nullable": True, "primary_key": False, "foreign_keys": []},
        ],
        "constraints": [],
        "indexes": ["INDEX (user_id, timestamp DESC)"],
        "foreign_keys": [],
    },
]


def _load_metadata():
    from app import create_app
    import app.models as models  # noqa: F401 — register all models

    # Eager-load lazy pgvector models so metadata is complete.
    for name in models._LAZY_MODEL_MODULES:
        getattr(models, name)

    app = create_app()
    with app.app_context():
        return app.extensions["sqlalchemy"].metadata


def _column_type(col) -> str:
    try:
        return col.type.compile(dialect=postgresql.dialect())
    except Exception:
        return str(col.type)


def _table_domain(name: str) -> str:
    if name in TABLE_DOMAINS:
        return TABLE_DOMAINS[name]
    if name.startswith(("ai_", "chatbot_")):
        return "AI & RAG"
    if name.startswith("validation_"):
        return "Data quality"
    if name.startswith(("form_", "template_", "lookup_", "embed_")):
        return "Form authoring"
    if name.startswith(("indicator_", "sector", "sub_sector", "common_word")):
        return "Indicator bank"
    if name.startswith(("rbac_", "api_", "password_")) or name == "user":
        return "Identity & access"
    return "Other"


def _collect_table_info(table) -> dict:
    pk_cols = {c.name for c in table.primary_key.columns}
    columns = []
    for col in table.columns:
        fk_targets = []
        for fk in col.foreign_keys:
            fk_targets.append(f"{fk.column.table.name}.{fk.column.name}")
        columns.append(
            {
                "name": col.name,
                "type": _column_type(col),
                "nullable": col.nullable,
                "primary_key": col.name in pk_cols,
                "foreign_keys": fk_targets,
                "default": str(col.server_default) if col.server_default is not None else "",
            }
        )

    constraints = []
    indexes = []
    for constraint in table.constraints:
        if isinstance(constraint, ForeignKeyConstraint):
            continue
        if constraint is table.primary_key:
            continue
        label = constraint.__class__.__name__
        if isinstance(constraint, UniqueConstraint):
            cols = ", ".join(c.name for c in constraint.columns)
            constraints.append(f"UNIQUE ({cols})")
        elif isinstance(constraint, CheckConstraint):
            constraints.append(f"CHECK {constraint.sqltext}")
        elif isinstance(constraint, Index):
            cols = ", ".join(c.name for c in constraint.columns)
            unique = "UNIQUE " if constraint.unique else ""
            indexes.append(f"{unique}INDEX ({cols})")
        else:
            constraints.append(label)

    for idx in table.indexes:
        cols = ", ".join(c.name for c in idx.columns)
        unique = "UNIQUE " if idx.unique else ""
        entry = f"{unique}INDEX ({cols})"
        if entry not in indexes:
            indexes.append(entry)

    outgoing_fks = []
    for fk in table.foreign_key_constraints:
        local = ", ".join(c.name for c in fk.columns)
        remote = ", ".join(
            f"{elem.column.table.name}.{elem.column.name}" for elem in fk.elements
        )
        outgoing_fks.append(f"{local} → {remote}")

    return {
        "name": table.name,
        "domain": _table_domain(table.name),
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "foreign_keys": outgoing_fks,
        "column_count": len(columns),
    }


def _domain_summary(tables: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for t in tables:
        counts[t["domain"]] += 1
    ordered = [(d, counts[d]) for d in DOMAIN_ORDER if counts.get(d)]
    for d, n in sorted(counts.items()):
        if d not in DOMAIN_ORDER:
            ordered.append((d, n))
    return ordered


def _build_reverse_references(tables: list[dict]) -> dict[str, list[dict]]:
    """Map target table → list of incoming FK references."""
    incoming: dict[str, list[dict]] = defaultdict(list)
    for table in tables:
        for col in table["columns"]:
            for fk in col["foreign_keys"]:
                if "." not in fk:
                    continue
                target_table, target_col = fk.split(".", 1)
                incoming[target_table].append(
                    {
                        "from_table": table["name"],
                        "from_column": col["name"],
                        "to_column": target_col,
                    }
                )
    return dict(incoming)


def _build_graph_payload(tables: list[dict], reverse_refs: dict[str, list[dict]]) -> dict:
    """Build relationship graph data for the interactive HTML viewer."""
    table_by_name = {t["name"]: t for t in tables}
    table_edges: list[dict] = []
    domain_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    degree: dict[str, int] = defaultdict(int)

    for table in tables:
        for col in table["columns"]:
            for fk in col["foreign_keys"]:
                if "." not in fk:
                    continue
                target_name, target_col = fk.split(".", 1)
                target = table_by_name.get(target_name)
                if not target:
                    continue
                table_edges.append(
                    {
                        "from": table["name"],
                        "to": target_name,
                        "from_domain": table["domain"],
                        "to_domain": target["domain"],
                        "from_column": col["name"],
                        "to_column": target_col,
                    }
                )
                domain_pair_counts[(table["domain"], target["domain"])] += 1
                degree[table["name"]] += 1
                degree[target_name] += 1

    domain_edges = [
        {"from": src, "to": dst, "count": count}
        for (src, dst), count in sorted(domain_pair_counts.items(), key=lambda item: -item[1])
    ]

    core_tables = [
        "form_template",
        "form_template_version",
        "form_page",
        "form_section",
        "form_item",
        "assigned_form",
        "assignment_entity_status",
        "public_submission",
        "reporting_period",
        "form_data",
        "dynamic_indicator_data",
        "repeat_group_instance",
        "repeat_group_data",
        "indicator_bank",
        "country",
        "user",
        "submitted_document",
    ]
    core_set = set(core_tables) & set(table_by_name)
    core_edges = [e for e in table_edges if e["from"] in core_set and e["to"] in core_set]

    hub_limit = 36
    hub_names = [
        name
        for name, _ in sorted(degree.items(), key=lambda item: -item[1])[:hub_limit]
        if name in table_by_name
    ]
    hub_set = set(hub_names)
    hub_edges = [e for e in table_edges if e["from"] in hub_set and e["to"] in hub_set]

    domain_colors = {
        "Identity & access": "#5b6abf",
        "Geography & organization": "#2a9d8f",
        "Form authoring": "#c8102e",
        "Assignments & workflow": "#e76f51",
        "Submission data": "#f4a261",
        "Indicator bank": "#457b9d",
        "Documents & resources": "#6d597a",
        "Notifications & communications": "#bc6c25",
        "Audit & security": "#7f5539",
        "AI & RAG": "#9b5de5",
        "Data quality": "#06d6a0",
        "Other": "#6c757d",
    }

    return {
        "domain_edges": domain_edges,
        "table_edges": table_edges,
        "all_tables": sorted(table_by_name.keys()),
        "core_tables": sorted(core_set),
        "core_edges": core_edges,
        "hub_tables": hub_names,
        "hub_edges": hub_edges,
        "domain_colors": domain_colors,
        "edge_count": len(table_edges),
    }


def _write_html(path: Path, tables: list[dict], domain_summary: list[tuple[str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    reverse_refs = _build_reverse_references(tables)
    graph = _build_graph_payload(tables, reverse_refs)
    payload = {
        "generated": today,
        "table_count": len(tables),
        "domains": [{"name": d, "count": c} for d, c in domain_summary],
        "domain_order": DOMAIN_ORDER,
        "patterns": [
            "Versioned form templates — form_template holds identity; form_template_version holds publishable snapshots.",
            "Dual-parent submission data — form_data, dynamic_indicator_data, and repeat_group_instance link to either assignment_entity_status_id or public_submission_id (CHECK constraints).",
            "Unified form items — indicators, questions, matrix cells, and plugin fields share form_item with a typed discriminator.",
            "Polymorphic entity permissions — user_entity_permissions grants access by (entity_type, entity_id).",
            "RBAC with scoped grants — roles plus optional language/country scopes via rbac_access_grant.",
            "Vector search — ai_embeddings and indicator_bank_embeddings use pgvector for RAG and semantic lookup.",
        ],
        "tables": tables,
        "referenced_by": reverse_refs,
        "graph": graph,
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    # Prevent </script> breakage if any string ever contained that sequence.
    data_json = data_json.replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>IFRC Network Databank — Database Schema</title>
  <style>
    :root {{
      --ifrc-red: #c8102e;
      --ifrc-red-dark: #9b0c24;
      --bg: #f4f5f7;
      --surface: #ffffff;
      --border: #d8dce3;
      --text: #1a1f2e;
      --muted: #5c6578;
      --accent-soft: #fdecee;
      --sidebar-w: 300px;
      --mono: ui-monospace, "Cascadia Code", "Segoe UI Mono", monospace;
      --sans: "Segoe UI", system-ui, -apple-system, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    header {{
      background: var(--ifrc-red);
      color: #fff;
      padding: 1rem 1.25rem;
      position: sticky;
      top: 0;
      z-index: 20;
      box-shadow: 0 2px 8px rgba(0,0,0,.12);
    }}
    header h1 {{
      margin: 0 0 .25rem;
      font-size: 1.15rem;
      font-weight: 600;
    }}
    header p {{
      margin: 0;
      opacity: .92;
      font-size: .85rem;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: .6rem;
      align-items: center;
      margin-top: .75rem;
    }}
    .toolbar input[type="search"] {{
      flex: 1 1 220px;
      min-width: 180px;
      padding: .5rem .75rem;
      border: none;
      border-radius: 6px;
      font-size: .95rem;
    }}
    .toolbar select {{
      padding: .5rem .65rem;
      border: none;
      border-radius: 6px;
      font-size: .9rem;
      max-width: 220px;
    }}
    .stats {{
      font-size: .8rem;
      opacity: .95;
      white-space: nowrap;
    }}
    .layout {{
      display: flex;
      min-height: calc(100vh - 110px);
    }}
    nav.sidebar {{
      width: var(--sidebar-w);
      flex-shrink: 0;
      background: var(--surface);
      border-right: 1px solid var(--border);
      overflow-y: auto;
      max-height: calc(100vh - 110px);
      position: sticky;
      top: 110px;
    }}
    nav.sidebar .sidebar-overview {{
      padding: .65rem .85rem;
      border-bottom: 1px solid var(--border);
      background: #fff;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    nav.sidebar .sidebar-overview button {{
      display: block;
      width: 100%;
      text-align: left;
      border: 1px solid var(--border);
      background: #f8f9fb;
      border-radius: 8px;
      padding: .5rem .75rem;
      font-size: .82rem;
      font-weight: 600;
      cursor: pointer;
      color: var(--text);
    }}
    nav.sidebar .sidebar-overview button:hover {{
      background: var(--accent-soft);
      border-color: var(--ifrc-red);
    }}
    nav.sidebar .sidebar-overview button.active {{
      background: var(--ifrc-red);
      border-color: var(--ifrc-red);
      color: #fff;
    }}
    nav.sidebar .domain-block {{
      border-bottom: 1px solid var(--border);
    }}
    nav.sidebar .domain-title {{
      padding: .55rem .85rem;
      font-size: .72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .04em;
      color: var(--muted);
      background: #f8f9fb;
      cursor: pointer;
      user-select: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    nav.sidebar .domain-title:hover {{ background: #eef0f4; }}
    nav.sidebar .domain-title .count {{
      background: #e4e8ef;
      border-radius: 999px;
      padding: .1rem .45rem;
      font-size: .68rem;
    }}
    nav.sidebar ul {{
      list-style: none;
      margin: 0;
      padding: .25rem 0 .5rem;
    }}
    nav.sidebar li button {{
      display: block;
      width: 100%;
      text-align: left;
      border: none;
      background: none;
      padding: .35rem .85rem .35rem 1.1rem;
      font-family: var(--mono);
      font-size: .78rem;
      cursor: pointer;
      color: var(--text);
    }}
    nav.sidebar li button:hover {{ background: var(--accent-soft); }}
    nav.sidebar li button.active {{
      background: var(--ifrc-red);
      color: #fff;
    }}
    main {{
      flex: 1;
      padding: 1.25rem 1.5rem 2rem;
      overflow-x: auto;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }}
    .panel h2 {{
      margin: 0 0 .75rem;
      font-size: 1.05rem;
    }}
    .panel h3 {{
      margin: 1.25rem 0 .5rem;
      font-size: .92rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .03em;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: .75rem;
    }}
    .meta-card {{
      background: #f8f9fb;
      border-radius: 8px;
      padding: .75rem;
      border: 1px solid var(--border);
    }}
    .meta-card .label {{
      font-size: .72rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .meta-card .value {{
      font-size: 1.1rem;
      font-weight: 600;
      margin-top: .15rem;
    }}
    .domain-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: .4rem;
    }}
    .chip {{
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 999px;
      padding: .25rem .65rem;
      font-size: .78rem;
      cursor: pointer;
    }}
    .chip:hover, .chip.active {{
      border-color: var(--ifrc-red);
      background: var(--accent-soft);
      color: var(--ifrc-red-dark);
    }}
    .patterns ol {{
      margin: 0;
      padding-left: 1.2rem;
      color: var(--muted);
      font-size: .9rem;
    }}
    .table-header {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: .5rem 1rem;
      margin-bottom: .5rem;
    }}
    .table-header h2 {{
      font-family: var(--mono);
      font-size: 1.35rem;
      margin: 0;
    }}
    .badge {{
      display: inline-block;
      font-size: .72rem;
      padding: .15rem .5rem;
      border-radius: 999px;
      background: #e8ecf2;
      color: var(--muted);
    }}
    .badge.pk {{ background: #fff3cd; color: #856404; }}
    .badge.fk {{ background: #d1ecf1; color: #0c5460; cursor: pointer; }}
    .badge.fk:hover {{ text-decoration: underline; }}
    .note {{
      color: var(--muted);
      font-size: .88rem;
      font-style: italic;
      margin-bottom: .75rem;
    }}
    table.data {{
      width: 100%;
      border-collapse: collapse;
      font-size: .86rem;
    }}
    table.data th, table.data td {{
      border-bottom: 1px solid var(--border);
      padding: .45rem .55rem;
      text-align: left;
      vertical-align: top;
    }}
    table.data th {{
      font-size: .72rem;
      text-transform: uppercase;
      letter-spacing: .03em;
      color: var(--muted);
      background: #f8f9fb;
      position: sticky;
      top: 0;
    }}
    table.data td.mono {{
      font-family: var(--mono);
      font-size: .8rem;
    }}
    .fk-link {{
      color: #0b5cab;
      cursor: pointer;
      text-decoration: none;
      font-family: var(--mono);
      font-size: .78rem;
    }}
    .fk-link:hover {{ text-decoration: underline; }}
    .tag-list {{
      display: flex;
      flex-wrap: wrap;
      gap: .35rem;
    }}
    .tag {{
      font-family: var(--mono);
      font-size: .75rem;
      background: #f0f2f6;
      border-radius: 4px;
      padding: .2rem .45rem;
    }}
    .empty {{
      color: var(--muted);
      font-style: italic;
      padding: 2rem;
      text-align: center;
    }}
    .hidden {{ display: none !important; }}
    .view-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: .4rem;
      margin-bottom: .85rem;
    }}
    .view-tabs button {{
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 999px;
      padding: .35rem .8rem;
      font-size: .82rem;
      cursor: pointer;
    }}
    .view-tabs button.active {{
      background: var(--ifrc-red);
      border-color: var(--ifrc-red);
      color: #fff;
    }}
    .diagram-wrap {{
      border: 1px solid var(--border);
      border-radius: 10px;
      background: linear-gradient(180deg, #fafbfd 0%, #fff 100%);
      overflow: hidden;
      margin-bottom: 1rem;
    }}
    .diagram-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: .5rem 1rem;
      align-items: center;
      justify-content: space-between;
      padding: .55rem .85rem;
      border-bottom: 1px solid var(--border);
      background: #f8f9fb;
      font-size: .78rem;
      color: var(--muted);
    }}
    .diagram-toolbar .hint {{ max-width: 520px; }}
    .diagram-canvas {{
      width: 100%;
      min-height: 420px;
      display: block;
      touch-action: none;
    }}
    .diagram-canvas.small {{ min-height: 280px; }}
    svg.graph-svg {{ width: 100%; height: 100%; min-height: inherit; display: block; }}
    .graph-node {{
      cursor: pointer;
    }}
    .graph-node circle, .graph-node rect {{
      stroke: #fff;
      stroke-width: 2px;
      transition: filter .15s ease;
    }}
    .graph-node:hover circle, .graph-node:hover rect {{
      filter: brightness(1.08);
    }}
    .graph-node.selected circle, .graph-node.selected rect {{
      stroke: #111;
      stroke-width: 3px;
    }}
    .graph-node text {{
      font-family: var(--mono);
      font-size: 10px;
      fill: #1a1f2e;
      pointer-events: none;
    }}
    .graph-node.domain text {{
      font-family: var(--sans);
      font-size: 11px;
      font-weight: 600;
    }}
    .graph-edge {{
      fill: none;
      stroke: #98a2b3;
      opacity: .75;
    }}
    .graph-edge.core {{ stroke: #c8102e; opacity: .55; }}
    .graph-edge.highlight {{ stroke: #c8102e; opacity: 1; stroke-width: 3px; }}
    .graph-edge-label {{
      font-size: 9px;
      fill: var(--muted);
      font-family: var(--sans);
    }}
    .diagram-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: .45rem .8rem;
      padding: .55rem .85rem .75rem;
      border-top: 1px solid var(--border);
      font-size: .75rem;
      color: var(--muted);
    }}
    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: .35rem;
    }}
    .legend-swatch {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .overview-grid {{
      display: grid;
      grid-template-columns: 1.4fr .9fr;
      gap: 1rem;
      margin-top: .25rem;
    }}
    .diagram-canvas.full {{
      min-height: min(72vh, 720px);
    }}
    .diagram-canvas.full .graph-svg {{
      min-height: min(72vh, 720px);
      cursor: grab;
    }}
    .diagram-canvas.full .graph-svg.panning {{
      cursor: grabbing;
    }}
    .zoom-controls {{
      display: inline-flex;
      gap: .25rem;
    }}
    .zoom-controls button {{
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 4px;
      width: 28px;
      height: 28px;
      cursor: pointer;
      font-size: .95rem;
      line-height: 1;
    }}
    .zoom-controls button:hover {{
      background: var(--accent-soft);
      border-color: var(--ifrc-red);
    }}
    .graph-node.compact text {{
      font-size: 8px;
      fill: #1a1f2e;
    }}
    .graph-node.compact circle {{
      stroke: #fff;
      stroke-width: 1.5px;
    }}
    .graph-edge.thin {{
      stroke-width: 0.6px;
      opacity: .35;
    }}
    .graph-edge.thin.highlight {{
      opacity: .95;
      stroke-width: 1.5px;
      stroke: var(--ifrc-red);
    }}
    .domain-hull {{
      fill: none;
      stroke-width: 1px;
      opacity: .25;
    }}
    @media (max-width: 1100px) {{
      .overview-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 900px) {{
      .layout {{ flex-direction: column; }}
      nav.sidebar {{
        width: 100%;
        max-height: 240px;
        position: static;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>IFRC Network Databank — Backoffice Database Schema</h1>
    <p>PostgreSQL 16 · SQLAlchemy · generated <span id="gen-date"></span></p>
    <div class="toolbar">
      <input type="search" id="search" placeholder="Search tables and columns…" autocomplete="off" aria-label="Search">
      <select id="domain-filter" aria-label="Filter by domain">
        <option value="">All domains</option>
      </select>
      <span class="stats" id="match-stats"></span>
    </div>
  </header>
  <div class="layout">
    <nav class="sidebar" id="sidebar" aria-label="Table navigation"></nav>
    <main id="main">
      <div class="panel" id="overview">
        <h2>Schema relationships</h2>
        <div class="view-tabs" id="diagram-tabs">
          <button type="button" class="active" data-diagram="full">Full schema</button>
          <button type="button" data-diagram="domain">Domain map</button>
          <button type="button" data-diagram="core">Core data flow</button>
          <button type="button" data-diagram="hub">Key tables (36)</button>
        </div>
        <div class="diagram-wrap" id="diagram-full">
          <div class="diagram-toolbar">
            <span class="hint">All tables and foreign-key relationships, clustered by domain. Scroll to zoom · drag background to pan · click a table for detail.</span>
            <div class="zoom-controls" id="full-zoom-controls">
              <button type="button" data-zoom="in" title="Zoom in">+</button>
              <button type="button" data-zoom="out" title="Zoom out">−</button>
              <button type="button" data-zoom="fit" title="Fit to view">Fit</button>
            </div>
          </div>
          <div class="diagram-canvas full" id="canvas-full"></div>
          <div class="diagram-legend" id="legend-full"></div>
        </div>
        <div class="diagram-wrap hidden" id="diagram-domain">
          <div class="diagram-toolbar">
            <span class="hint">Foreign-key traffic between domains. Click a domain to filter the table list; line thickness shows relationship volume.</span>
            <span id="domain-edge-count"></span>
          </div>
          <div class="diagram-canvas" id="canvas-domain"></div>
          <div class="diagram-legend" id="legend-domain"></div>
        </div>
        <div class="diagram-wrap hidden" id="diagram-core">
          <div class="diagram-toolbar">
            <span class="hint">Main reporting path: template authoring → assignment → entity submission → answer tables. Click any table for full detail.</span>
          </div>
          <div class="diagram-canvas" id="canvas-core"></div>
        </div>
        <div class="diagram-wrap hidden" id="diagram-hub">
          <div class="diagram-toolbar">
            <span class="hint">Most connected tables by foreign-key degree. Drag nodes to rearrange; scroll to zoom.</span>
            <span id="hub-edge-count"></span>
          </div>
          <div class="diagram-canvas" id="canvas-hub"></div>
          <div class="diagram-legend" id="legend-hub"></div>
        </div>
        <div class="overview-grid">
          <div>
            <h3>Summary</h3>
            <div class="meta-grid" id="meta-grid"></div>
            <h3>Domains</h3>
            <div class="domain-chips" id="domain-chips"></div>
          </div>
          <div>
            <h3>Key design patterns</h3>
            <div class="patterns"><ol id="patterns"></ol></div>
          </div>
        </div>
      </div>
      <div class="panel hidden" id="table-detail">
        <div class="table-header">
          <h2 id="detail-name"></h2>
          <span class="badge" id="detail-domain"></span>
          <span class="badge" id="detail-cols"></span>
        </div>
        <p class="note hidden" id="detail-note"></p>
        <h3>Direct relationships</h3>
        <div class="diagram-wrap">
          <div class="diagram-toolbar">
            <span class="hint">One-hop foreign keys: tables this table references (left) and tables that reference it (right).</span>
          </div>
          <div class="diagram-canvas small" id="canvas-ego"></div>
        </div>
        <h3>Columns</h3>
        <table class="data" id="columns-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Null</th>
              <th>Key</th>
              <th>References</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
        <h3 id="refs-heading">Referenced by</h3>
        <div class="tag-list" id="referenced-by"></div>
        <h3 id="fk-heading">Table foreign keys</h3>
        <div class="tag-list" id="table-fks"></div>
        <h3 id="constraints-heading">Constraints</h3>
        <div class="tag-list" id="constraints"></div>
        <h3 id="indexes-heading">Indexes</h3>
        <div class="tag-list" id="indexes"></div>
      </div>
      <p class="empty hidden" id="no-results">No tables match your search.</p>
    </main>
  </div>
  <script id="schema-data" type="application/json">{data_json}</script>
  <script>
(function () {{
  const DATA = JSON.parse(document.getElementById('schema-data').textContent);
  const GRAPH = DATA.graph;
  const COLORS = GRAPH.domain_colors;
  const tableByName = Object.fromEntries(DATA.tables.map(t => [t.name, t]));
  const searchEl = document.getElementById('search');
  const domainFilterEl = document.getElementById('domain-filter');
  const sidebarEl = document.getElementById('sidebar');
  const overviewEl = document.getElementById('overview');
  const detailEl = document.getElementById('table-detail');
  const noResultsEl = document.getElementById('no-results');
  let activeTable = null;
  let activeDiagram = 'full';
  let collapsedDomains = new Set();
  let hubLayout = null;
  let fullLayout = null;
  let fullPanZoom = null;
  let svgCounter = 0;

  document.getElementById('gen-date').textContent = DATA.generated;
  document.getElementById('domain-edge-count').textContent = `${{GRAPH.domain_edges.length}} cross-domain links · ${{GRAPH.edge_count}} total FKs`;
  document.getElementById('hub-edge-count').textContent = `${{GRAPH.hub_edges.length}} links among hub tables`;

  function esc(s) {{
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }}

  function domainColor(domain) {{
    return COLORS[domain] || COLORS.Other || '#6c757d';
  }}

  function fkLink(ref) {{
    const dot = ref.indexOf('.');
    if (dot === -1) return esc(ref);
    const tbl = ref.slice(0, dot);
    const col = ref.slice(dot + 1);
    if (!tableByName[tbl]) return esc(ref);
    return `<a class="fk-link" data-table="${{esc(tbl)}}" href="#table=${{encodeURIComponent(tbl)}}">${{esc(tbl)}}.${{esc(col)}}</a>`;
  }}

  function tableMatchesQuery(table, q) {{
    if (!q) return true;
    if (table.name.includes(q)) return true;
    if (table.domain.toLowerCase().includes(q)) return true;
    return table.columns.some(c =>
      c.name.includes(q) || c.type.toLowerCase().includes(q) ||
      c.foreign_keys.some(fk => fk.toLowerCase().includes(q))
    );
  }}

  function filteredTables() {{
    const q = searchEl.value.trim().toLowerCase();
    const domain = domainFilterEl.value;
    return DATA.tables.filter(t => {{
      if (domain && t.domain !== domain) return false;
      return tableMatchesQuery(t, q);
    }});
  }}

  function mountSvg(container, viewW, viewH, opts) {{
    opts = opts || {{}};
    container.innerHTML = '';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${{viewW}} ${{viewH}}`);
    svg.setAttribute('class', 'graph-svg');
    svg.setAttribute('role', 'img');
    const markerId = 'arrow-' + (++svgCounter);
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', markerId);
    marker.setAttribute('viewBox', '0 0 10 10');
    marker.setAttribute('refX', '9');
    marker.setAttribute('refY', '5');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('orient', 'auto-start-reverse');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
    path.setAttribute('fill', '#98a2b3');
    marker.appendChild(path);
    defs.appendChild(marker);
    svg.appendChild(defs);
    const gViewport = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const gHulls = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const gEdges = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const gNodes = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    gViewport.appendChild(gHulls);
    gViewport.appendChild(gEdges);
    gViewport.appendChild(gNodes);
    svg.appendChild(gViewport);
    container.appendChild(svg);
    const api = {{ svg, gHulls, gEdges, gNodes, gViewport, viewW, viewH, markerId }};
    if (opts.panZoom) {{
      api.panZoom = enablePanZoom(svg, gViewport, viewW, viewH);
    }}
    return api;
  }}

  function enablePanZoom(svg, g, viewW, viewH) {{
    const state = {{ tx: 0, ty: 0, scale: 1 }};
    function apply() {{
      g.setAttribute('transform', `translate(${{state.tx}},${{state.ty}}) scale(${{state.scale}})`);
    }}
    function zoomBy(factor, cx, cy) {{
      const rect = svg.getBoundingClientRect();
      const px = cx != null ? cx : rect.width / 2;
      const py = cy != null ? cy : rect.height / 2;
      const sx = (px - state.tx) / state.scale;
      const sy = (py - state.ty) / state.scale;
      state.scale = Math.min(4, Math.max(0.15, state.scale * factor));
      state.tx = px - sx * state.scale;
      state.ty = py - sy * state.scale;
      apply();
    }}
    function fit() {{
      state.tx = 20;
      state.ty = 20;
      state.scale = 0.85;
      apply();
    }}
    let panning = false, lastX = 0, lastY = 0;
    svg.addEventListener('wheel', e => {{
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      zoomBy(e.deltaY > 0 ? 0.92 : 1.08, e.clientX - rect.left, e.clientY - rect.top);
    }}, {{ passive: false }});
    svg.addEventListener('mousedown', e => {{
      if (e.target.closest('.graph-node')) return;
      panning = true;
      lastX = e.clientX;
      lastY = e.clientY;
      svg.classList.add('panning');
    }});
    window.addEventListener('mousemove', e => {{
      if (!panning) return;
      state.tx += e.clientX - lastX;
      state.ty += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      apply();
    }});
    window.addEventListener('mouseup', () => {{
      panning = false;
      svg.classList.remove('panning');
    }});
    fit();
    return {{ zoomBy, fit, state }};
  }}

  function curvePath(x1, y1, x2, y2, bend) {{
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const cx = mx + bend * (y2 - y1);
    const cy = my - bend * (x2 - x1);
    return `M ${{x1}} ${{y1}} Q ${{cx}} ${{cy}} ${{x2}} ${{y2}}`;
  }}

  function renderDomainMap() {{
    const host = document.getElementById('canvas-domain');
    const domains = DATA.domains.map(d => d.name);
    const n = domains.length;
    const positions = {{}};
    const cx = 430, cy = 260, R = 185;
    domains.forEach((name, i) => {{
      const angle = (2 * Math.PI * i) / n - Math.PI / 2;
      positions[name] = {{ x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle), name }};
    }});
    const {{ gEdges, gNodes, markerId }} = mountSvg(host, 860, 520);
    const maxCount = Math.max(1, ...GRAPH.domain_edges.map(e => e.count));
    GRAPH.domain_edges.forEach(edge => {{
      const a = positions[edge.from];
      const b = positions[edge.to];
      if (!a || !b) return;
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', curvePath(a.x, a.y, b.x, b.y, 0.12));
      p.setAttribute('class', 'graph-edge');
      p.setAttribute('stroke-width', String(1 + (edge.count / maxCount) * 8));
      p.setAttribute('marker-end', `url(#${{markerId}})`);
      gEdges.appendChild(p);
      if (edge.count >= 3 && edge.from !== edge.to) {{
        const lx = (a.x + b.x) / 2;
        const ly = (a.y + b.y) / 2 - 8;
        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', lx);
        label.setAttribute('y', ly);
        label.setAttribute('text-anchor', 'middle');
        label.setAttribute('class', 'graph-edge-label');
        label.textContent = edge.count;
        gEdges.appendChild(label);
      }}
    }});
    domains.forEach(name => {{
      const pos = positions[name];
      const count = DATA.domains.find(d => d.name === name)?.count || 0;
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'graph-node domain');
      g.setAttribute('transform', `translate(${{pos.x}},${{pos.y}})`);
      g.dataset.domain = name;
      const r = 16 + Math.min(count, 12);
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('r', String(r));
      c.setAttribute('fill', domainColor(name));
      g.appendChild(c);
      const t1 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t1.setAttribute('y', String(r + 14));
      t1.setAttribute('text-anchor', 'middle');
      const parts = name.split(' ');
      t1.textContent = parts.slice(0, 2).join(' ');
      g.appendChild(t1);
      if (parts.length > 2) {{
        const t2 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t2.setAttribute('y', String(r + 26));
        t2.setAttribute('text-anchor', 'middle');
        t2.textContent = parts.slice(2).join(' ');
        g.appendChild(t2);
      }}
      const t3 = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t3.setAttribute('y', String(r + (parts.length > 2 ? 38 : 26)));
      t3.setAttribute('text-anchor', 'middle');
      t3.setAttribute('fill', '#5c6578');
      t3.textContent = `${{count}} tables`;
      g.appendChild(t3);
      gNodes.appendChild(g);
    }});
    document.getElementById('legend-domain').innerHTML = domains.map(name =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${{domainColor(name)}}"></span>${{esc(name)}}</span>`
    ).join('');
  }}

  function layoutLayeredTables(tableNames, edges) {{
    const layers = {{
      'Form authoring': 0,
      'Indicator bank': 0,
      'Geography & organization': 1,
      'Assignments & workflow': 2,
      'Submission data': 3,
      'Documents & resources': 3,
      'Identity & access': 1,
    }};
    const byLayer = {{}};
    tableNames.forEach(name => {{
      const layer = layers[tableByName[name]?.domain] ?? 2;
      (byLayer[layer] ||= []).push(name);
    }});
    const positions = {{}};
    Object.keys(byLayer).sort((a, b) => a - b).forEach(layerKey => {{
      const list = byLayer[layerKey].sort();
      const yBase = 70 + Number(layerKey) * 95;
      const span = 760;
      const step = list.length > 1 ? span / (list.length - 1) : 0;
      list.forEach((name, i) => {{
        positions[name] = {{ x: 50 + (list.length === 1 ? span / 2 : step * i), y: yBase, name }};
      }});
    }});
    return positions;
  }}

  function runForceLayout(names, edges, positions, opts) {{
    opts = opts || {{}};
    const domainCenters = opts.domainCenters || {{}};
    const iterations = opts.iterations || 160;
    const repulse = opts.repulse || 5200;
    const ideal = opts.ideal || 88;
    const domainPull = opts.domainPull || 0.018;
    for (let iter = 0; iter < iterations; iter++) {{
      for (let i = 0; i < names.length; i++) {{
        for (let j = i + 1; j < names.length; j++) {{
          const a = names[i], b = names[j];
          const pa = positions[a], pb = positions[b];
          let dx = pa.x - pb.x, dy = pa.y - pb.y;
          let dist = Math.hypot(dx, dy) || 1;
          const force = repulse / (dist * dist);
          pa.x += (dx / dist) * force;
          pa.y += (dy / dist) * force;
          pb.x -= (dx / dist) * force;
          pb.y -= (dy / dist) * force;
        }}
      }}
      edges.forEach(e => {{
        const pa = positions[e.from], pb = positions[e.to];
        if (!pa || !pb) return;
        const dx = pb.x - pa.x, dy = pb.y - pa.y;
        const dist = Math.hypot(dx, dy) || 1;
        const pull = (dist - ideal) * 0.035;
        pa.x += (dx / dist) * pull;
        pa.y += (dy / dist) * pull;
        pb.x -= (dx / dist) * pull;
        pb.y -= (dy / dist) * pull;
      }});
      names.forEach(name => {{
        const domain = tableByName[name]?.domain;
        const center = domainCenters[domain];
        if (!center) return;
        positions[name].x += (center.x - positions[name].x) * domainPull;
        positions[name].y += (center.y - positions[name].y) * domainPull;
      }});
    }}
    return positions;
  }}

  function layoutByDomainClusters(names) {{
    const byDomain = {{}};
    names.forEach(name => {{
      const domain = tableByName[name]?.domain || 'Other';
      (byDomain[domain] ||= []).push(name);
    }});
    const domains = DATA.domain_order.filter(d => byDomain[d]?.length);
    const positions = {{}};
    const domainCenters = {{}};
    const cx = 620, cy = 480, R = 360;
    domains.forEach((domain, i) => {{
      const angle = (2 * Math.PI * i) / domains.length - Math.PI / 2;
      domainCenters[domain] = {{ x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) }};
      const list = byDomain[domain];
      list.forEach((name, j) => {{
        const a = (2 * Math.PI * j) / list.length;
        const r = 28 + Math.min(list.length * 3, 50);
        positions[name] = {{
          x: domainCenters[domain].x + r * Math.cos(a),
          y: domainCenters[domain].y + r * Math.sin(a),
          name,
        }};
      }});
    }});
    return {{ positions, domainCenters, byDomain }};
  }}

  function renderTableGraph(containerId, tableNames, edges, opts) {{
    opts = opts || {{}};
    const host = document.getElementById(containerId);
    const positions = opts.positions || layoutLayeredTables(tableNames, edges);
    const mount = mountSvg(host, opts.viewW || 860, opts.viewH || 460, {{ panZoom: !!opts.panZoom }});
    const {{ gHulls, gEdges, gNodes, markerId, viewW, viewH }} = mount;
    if (opts.panZoom) {{
      if (containerId === 'canvas-full') fullPanZoom = mount.panZoom;
    }}
    const edgeClass = opts.edgeClass || 'core';
    edges.forEach(edge => {{
      const a = positions[edge.from];
      const b = positions[edge.to];
      if (!a || !b) return;
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', curvePath(a.x, a.y, b.x, b.y, opts.compact ? 0.04 : 0.08));
      p.setAttribute('class', `graph-edge ${{edgeClass}}`);
      p.setAttribute('data-from', edge.from);
      p.setAttribute('data-to', edge.to);
      if (!opts.compact) p.setAttribute('stroke-width', '1.5');
      if (!opts.compact || edges.length < 200) p.setAttribute('marker-end', `url(#${{markerId}})`);
      gEdges.appendChild(p);
    }});
    if (opts.domainHulls && opts.byDomain) {{
      Object.entries(opts.byDomain).forEach(([domain, list]) => {{
        const pts = list.map(n => positions[n]).filter(Boolean);
        if (pts.length < 2) return;
        const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
        const minX = Math.min(...xs) - 24, maxX = Math.max(...xs) + 24;
        const minY = Math.min(...ys) - 24, maxY = Math.max(...ys) + 24;
        const ell = document.createElementNS('http://www.w3.org/2000/svg', 'ellipse');
        ell.setAttribute('cx', String((minX + maxX) / 2));
        ell.setAttribute('cy', String((minY + maxY) / 2));
        ell.setAttribute('rx', String((maxX - minX) / 2));
        ell.setAttribute('ry', String((maxY - minY) / 2));
        ell.setAttribute('class', 'domain-hull');
        ell.setAttribute('stroke', domainColor(domain));
        gHulls.appendChild(ell);
      }});
    }}
    tableNames.forEach(name => {{
      const pos = positions[name];
      if (!pos) return;
      const domain = tableByName[name]?.domain || 'Other';
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'graph-node' + (opts.compact ? ' compact' : ''));
      g.setAttribute('transform', `translate(${{pos.x}},${{pos.y}})`);
      g.dataset.table = name;
      if (opts.compact) {{
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('r', '5');
        c.setAttribute('fill', domainColor(domain));
        g.appendChild(c);
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('y', '16');
        t.setAttribute('text-anchor', 'middle');
        t.textContent = name.length > 18 ? name.slice(0, 16) + '…' : name;
        g.appendChild(t);
      }} else {{
        const w = Math.max(84, name.length * 5.8);
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('x', String(-w / 2));
        rect.setAttribute('y', '-14');
        rect.setAttribute('width', String(w));
        rect.setAttribute('height', '28');
        rect.setAttribute('rx', '6');
        rect.setAttribute('fill', domainColor(domain));
        g.appendChild(rect);
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('y', '4');
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('fill', '#fff');
        t.textContent = name.length > 22 ? name.slice(0, 20) + '…' : name;
        g.appendChild(t);
      }}
      gNodes.appendChild(g);
    }});
    if (opts.highlightTable) {{
      host.querySelectorAll('.graph-node').forEach(n => {{
        if (n.dataset.table === opts.highlightTable) n.classList.add('selected');
      }});
    }}
  }}

  function layoutFullSchema() {{
    if (fullLayout) return fullLayout;
    const names = GRAPH.all_tables;
    const {{ positions, domainCenters, byDomain }} = layoutByDomainClusters(names);
    runForceLayout(names, GRAPH.table_edges, positions, {{
      domainCenters,
      iterations: 220,
      repulse: 6400,
      ideal: 72,
      domainPull: 0.022,
    }});
    fullLayout = {{ positions, byDomain }};
    return fullLayout;
  }}

  function renderFullSchemaGraph() {{
    const {{ positions, byDomain }} = layoutFullSchema();
    renderTableGraph('canvas-full', GRAPH.all_tables, GRAPH.table_edges, {{
      positions,
      byDomain,
      viewW: 1240,
      viewH: 960,
      panZoom: true,
      compact: true,
      edgeClass: 'thin',
      domainHulls: true,
    }});
    document.getElementById('legend-full').innerHTML = DATA.domains.map(d =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${{domainColor(d.name)}}"></span>${{esc(d.name)}} (${{d.count}})</span>`
    ).join('');
  }}

  function renderCoreFlow() {{
    renderTableGraph('canvas-core', GRAPH.core_tables, GRAPH.core_edges, {{ viewH: 500 }});
  }}

  function renderHubGraph() {{
    const host = document.getElementById('canvas-hub');
    if (!hubLayout) {{
      const names = GRAPH.hub_tables;
      const positions = {{}};
      const cx = 430, cy = 250;
      names.forEach((name, i) => {{
        const angle = (2 * Math.PI * i) / names.length;
        positions[name] = {{
          x: cx + 170 * Math.cos(angle) + (Math.random() - 0.5) * 20,
          y: cy + 170 * Math.sin(angle) + (Math.random() - 0.5) * 20,
          name,
        }};
      }});
      const edges = GRAPH.hub_edges;
      for (let iter = 0; iter < 140; iter++) {{
        names.forEach(a => {{
          names.forEach(b => {{
            if (a >= b) return;
            const pa = positions[a], pb = positions[b];
            let dx = pa.x - pb.x, dy = pa.y - pb.y;
            let dist = Math.hypot(dx, dy) || 1;
            const repulse = 9000 / (dist * dist);
            pa.x += (dx / dist) * repulse;
            pa.y += (dy / dist) * repulse;
            pb.x -= (dx / dist) * repulse;
            pb.y -= (dy / dist) * repulse;
          }});
        }});
        edges.forEach(e => {{
          const pa = positions[e.from], pb = positions[e.to];
          if (!pa || !pb) return;
          const dx = pb.x - pa.x, dy = pb.y - pa.y;
          const dist = Math.hypot(dx, dy) || 1;
          const pull = (dist - 120) * 0.04;
          pa.x += (dx / dist) * pull;
          pa.y += (dy / dist) * pull;
          pb.x -= (dx / dist) * pull;
          pb.y -= (dy / dist) * pull;
        }});
        names.forEach(name => {{
          positions[name].x += (430 - positions[name].x) * 0.01;
          positions[name].y += (250 - positions[name].y) * 0.01;
        }});
      }}
      hubLayout = positions;
    }}
    renderTableGraph('canvas-hub', GRAPH.hub_tables, GRAPH.hub_edges, {{
      positions: hubLayout,
      viewW: 860,
      viewH: 500,
    }});
    const legendHost = document.getElementById('legend-hub');
    const usedDomains = [...new Set(GRAPH.hub_tables.map(n => tableByName[n]?.domain).filter(Boolean))];
    legendHost.innerHTML = usedDomains.map(name =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${{domainColor(name)}}"></span>${{esc(name)}}</span>`
    ).join('');
  }}

  function renderEgoGraph(tableName) {{
    const host = document.getElementById('canvas-ego');
    const outgoing = new Set();
    const incoming = new Set();
    GRAPH.table_edges.forEach(e => {{
      if (e.from === tableName) outgoing.add(e.to);
      if (e.to === tableName) incoming.add(e.from);
    }});
    const left = [...outgoing].sort();
    const right = [...incoming].sort();
    const positions = {{}};
    positions[tableName] = {{ x: 430, y: 140, name: tableName }};
    left.forEach((name, i) => {{
      positions[name] = {{ x: 120, y: 40 + i * 42, name }};
    }});
    right.forEach((name, i) => {{
      positions[name] = {{ x: 740, y: 40 + i * 42, name }};
    }});
    const nodes = [tableName, ...left, ...right];
    const edges = GRAPH.table_edges.filter(e =>
      (e.from === tableName && outgoing.has(e.to)) || (e.to === tableName && incoming.has(e.from))
    );
    renderTableGraph('canvas-ego', nodes, edges, {{ viewH: Math.max(280, 60 + Math.max(left.length, right.length, 1) * 42), viewW: 860, positions }});
    const center = host.querySelector(`[data-table="${{CSS.escape(tableName)}}"]`);
    if (center) center.classList.add('selected');
  }}

  function setDiagram(name) {{
    activeDiagram = name;
    document.querySelectorAll('#diagram-tabs button').forEach(btn => {{
      btn.classList.toggle('active', btn.dataset.diagram === name);
    }});
    ['full', 'domain', 'core', 'hub'].forEach(key => {{
      document.getElementById('diagram-' + key).classList.toggle('hidden', key !== name);
    }});
    if (name === 'full') renderFullSchemaGraph();
    if (name === 'domain') renderDomainMap();
    if (name === 'core') renderCoreFlow();
    if (name === 'hub') renderHubGraph();
    history.replaceState(null, '', '#overview=' + name);
  }}

  function renderOverview() {{
    document.getElementById('meta-grid').innerHTML = `
      <div class="meta-card"><div class="label">Tables</div><div class="value">${{DATA.table_count}}</div></div>
      <div class="meta-card"><div class="label">Foreign keys</div><div class="value">${{GRAPH.edge_count}}</div></div>
      <div class="meta-card"><div class="label">Domains</div><div class="value">${{DATA.domains.length}}</div></div>
      <div class="meta-card"><div class="label">Engine</div><div class="value">PostgreSQL 16</div></div>`;
    document.getElementById('patterns').innerHTML = DATA.patterns.map(p => `<li>${{esc(p)}}</li>`).join('');
    document.getElementById('domain-chips').innerHTML = DATA.domains.map(d =>
      `<button type="button" class="chip" data-domain="${{esc(d.name)}}">${{esc(d.name)}} (${{d.count}})</button>`
    ).join('');
    setDiagram(activeDiagram);
  }}

  function renderDomainFilter() {{
    domainFilterEl.innerHTML = '<option value="">All domains</option>' +
      DATA.domains.map(d => `<option value="${{esc(d.name)}}">${{esc(d.name)}} (${{d.count}})</option>`).join('');
  }}

  function renderSidebar(tables) {{
    const byDomain = {{}};
    for (const t of tables) {{
      (byDomain[t.domain] ||= []).push(t);
    }}
    let html = `<div class="sidebar-overview">
      <button type="button" data-overview class="${{activeTable ? '' : 'active'}}">Schema overview</button>
    </div>`;
    for (const domain of DATA.domain_order) {{
      const list = byDomain[domain];
      if (!list || !list.length) continue;
      list.sort((a, b) => a.name.localeCompare(b.name));
      const collapsed = collapsedDomains.has(domain);
      html += `<div class="domain-block">
        <div class="domain-title" data-domain-toggle="${{esc(domain)}}">
          <span>${{esc(domain)}}</span>
          <span class="count">${{list.length}}</span>
        </div>
        <ul class="${{collapsed ? 'hidden' : ''}}">
          ${{list.map(t => `<li><button type="button" data-table="${{esc(t.name)}}" class="${{activeTable === t.name ? 'active' : ''}}">${{esc(t.name)}}</button></li>`).join('')}}
        </ul>
      </div>`;
    }}
    sidebarEl.innerHTML = html || '<p class="empty">No tables</p>';
    document.getElementById('match-stats').textContent =
      tables.length === DATA.table_count
        ? `${{DATA.table_count}} tables`
        : `${{tables.length}} / ${{DATA.table_count}} tables`;
  }}

  function renderTags(containerId, items, emptyText) {{
    const el = document.getElementById(containerId);
    if (!items || !items.length) {{
      el.innerHTML = `<span class="note">${{esc(emptyText)}}</span>`;
      return;
    }}
    el.innerHTML = items.map(item => {{
      if (typeof item === 'string') return `<span class="tag">${{esc(item)}}</span>`;
      const label = `${{item.from_table}}.${{item.from_column}} → ${{item.to_column}}`;
      return `<a class="tag fk-link" data-table="${{esc(item.from_table)}}" href="#table=${{encodeURIComponent(item.from_table)}}">${{esc(label)}}</a>`;
    }}).join('');
  }}

  function showTable(name) {{
    const table = tableByName[name];
    if (!table) return;
    activeTable = name;
    overviewEl.classList.add('hidden');
    detailEl.classList.remove('hidden');
    noResultsEl.classList.add('hidden');
    document.getElementById('detail-name').textContent = table.name;
    document.getElementById('detail-domain').textContent = table.domain;
    document.getElementById('detail-cols').textContent = `${{table.column_count}} columns`;
    const noteEl = document.getElementById('detail-note');
    if (table.note) {{
      noteEl.textContent = table.note;
      noteEl.classList.remove('hidden');
    }} else {{
      noteEl.classList.add('hidden');
    }}
    renderEgoGraph(table.name);
    const tbody = document.querySelector('#columns-table tbody');
    tbody.innerHTML = table.columns.map(col => {{
      const keys = [];
      if (col.primary_key) keys.push('<span class="badge pk">PK</span>');
      const refs = col.foreign_keys.map(fk => fkLink(fk)).join('<br>') || '—';
      return `<tr>
        <td class="mono">${{esc(col.name)}}</td>
        <td class="mono">${{esc(col.type)}}</td>
        <td>${{col.nullable ? 'yes' : 'no'}}</td>
        <td>${{keys.join(' ') || '—'}}</td>
        <td>${{refs}}</td>
      </tr>`;
    }}).join('');
    renderTags('referenced-by', DATA.referenced_by[table.name] || [], 'No incoming foreign keys.');
    renderTags('table-fks', table.foreign_keys || [], 'No composite/outgoing FK constraints listed.');
    renderTags('constraints', table.constraints || [], 'No additional constraints.');
    renderTags('indexes', table.indexes || [], 'No indexes beyond primary key.');
    renderSidebar(filteredTables());
    history.replaceState(null, '', '#table=' + encodeURIComponent(name));
  }}

  function showOverview(diagram) {{
    activeTable = null;
    overviewEl.classList.remove('hidden');
    detailEl.classList.add('hidden');
    if (diagram) activeDiagram = diagram;
    renderOverview();
    renderSidebar(filteredTables());
    if (!diagram) history.replaceState(null, '', '#overview=' + activeDiagram);
  }}

  function refresh() {{
    const tables = filteredTables();
    renderSidebar(tables);
    if (!tables.length) {{
      overviewEl.classList.add('hidden');
      detailEl.classList.add('hidden');
      noResultsEl.classList.remove('hidden');
      return;
    }}
    noResultsEl.classList.add('hidden');
    if (activeTable && !tables.some(t => t.name === activeTable)) {{
      showOverview(activeDiagram);
    }} else if (activeTable) {{
      showTable(activeTable);
    }} else {{
      overviewEl.classList.remove('hidden');
      renderOverview();
    }}
  }}

  document.addEventListener('click', e => {{
    const zoomBtn = e.target.closest('#full-zoom-controls button');
    if (zoomBtn && fullPanZoom) {{
      const action = zoomBtn.dataset.zoom;
      if (action === 'in') fullPanZoom.zoomBy(1.2);
      if (action === 'out') fullPanZoom.zoomBy(1 / 1.2);
      if (action === 'fit') fullPanZoom.fit();
      return;
    }}
    const diagramBtn = e.target.closest('#diagram-tabs button');
    if (diagramBtn) {{
      setDiagram(diagramBtn.dataset.diagram);
      return;
    }}
    const domainNode = e.target.closest('.graph-node.domain');
    if (domainNode && domainNode.dataset.domain) {{
      domainFilterEl.value = domainNode.dataset.domain;
      refresh();
      return;
    }}
    const tbl = e.target.closest('[data-table]');
    if (tbl) {{
      e.preventDefault();
      showTable(tbl.dataset.table);
      return;
    }}
    const overviewBtn = e.target.closest('[data-overview]');
    if (overviewBtn) {{
      e.preventDefault();
      showOverview(activeDiagram);
      return;
    }}
    const chip = e.target.closest('.chip[data-domain]');
    if (chip) {{
      domainFilterEl.value = chip.dataset.domain;
      refresh();
      return;
    }}
    const toggle = e.target.closest('[data-domain-toggle]');
    if (toggle) {{
      const d = toggle.dataset.domainToggle;
      if (collapsedDomains.has(d)) collapsedDomains.delete(d);
      else collapsedDomains.add(d);
      renderSidebar(filteredTables());
    }}
  }});

  searchEl.addEventListener('input', refresh);
  domainFilterEl.addEventListener('change', refresh);

  renderDomainFilter();
  renderSidebar(DATA.tables);

  const hash = location.hash.replace(/^#/, '');
  if (hash.startsWith('table=')) {{
    showTable(decodeURIComponent(hash.slice(6)));
  }} else if (hash.startsWith('overview=')) {{
    showOverview(hash.slice(9));
  }} else {{
    showOverview('full');
  }}

  window.addEventListener('hashchange', () => {{
    const h = location.hash.replace(/^#/, '');
    if (h.startsWith('table=')) showTable(decodeURIComponent(h.slice(6)));
    else if (h.startsWith('overview=')) showOverview(h.slice(9));
    else showOverview('full');
  }});
}})();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _write_csv(path: Path, tables: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "domain",
                "table",
                "column",
                "data_type",
                "nullable",
                "primary_key",
                "foreign_key_references",
            ]
        )
        for table in tables:
            for col in table["columns"]:
                writer.writerow(
                    [
                        table["domain"],
                        table["name"],
                        col["name"],
                        col["type"],
                        "yes" if col["nullable"] else "no",
                        "yes" if col["primary_key"] else "",
                        "; ".join(col["foreign_keys"]),
                    ]
                )


def _write_markdown(path: Path, metadata, tables: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    domain_summary = _domain_summary(tables)
    ddl_sample_path = path.with_name("database-schema-ddl.sql")

    lines: list[str] = [
        "# IFRC Network Databank — Backoffice Database Schema",
        "",
        f"> Generated from SQLAlchemy models on {today}. "
        "Regenerate with `python scripts/dev/export_database_schema.py` from `Backoffice/`.",
        "",
        "## Executive summary",
        "",
        "| Item | Value |",
        "|------|-------|",
        "| Database engine | PostgreSQL 16 (production); [pgvector](https://github.com/pgvector/pgvector) for embeddings |",
        "| ORM | SQLAlchemy (Flask-SQLAlchemy) |",
        "| Schema migrations | Flask-Migrate / Alembic (`Backoffice/migrations/`) |",
        f"| Application tables | {len(tables)} (excludes `alembic_version`) |",
        "| Primary consumers | Backoffice web app, mobile API, public website (read paths), AI/RAG services |",
        "",
        "### Domain overview",
        "",
        "| Domain | Tables |",
        "|--------|--------|",
    ]
    for domain, count in domain_summary:
        lines.append(f"| {domain} | {count} |")

    lines.extend(
        [
            "",
            "### High-level data flow",
            "",
            "```mermaid",
            "flowchart LR",
            "  subgraph authoring [Form authoring]",
            "    FT[form_template]",
            "    FV[form_template_version]",
            "    FI[form_item]",
            "  end",
            "  subgraph workflow [Assignments]",
            "    AF[assigned_form]",
            "    AES[assignment_entity_status]",
            "  end",
            "  subgraph answers [Submission data]",
            "    FD[form_data]",
            "    DID[dynamic_indicator_data]",
            "    RG[repeat_group_data]",
            "  end",
            "  subgraph ref [Reference data]",
            "    IB[indicator_bank]",
            "    CO[country]",
            "  end",
            "  FT --> FV --> FI",
            "  FV --> AF --> AES",
            "  AES --> FD",
            "  AES --> DID",
            "  AES --> RG",
            "  FI --> FD",
            "  IB --> FI",
            "  CO --> AES",
            "```",
            "",
            "### Key design patterns",
            "",
            "1. **Versioned form templates** — `form_template` holds identity; "
            "`form_template_version` holds publishable snapshots (sections, items, config).",
            "2. **Dual-parent submission data** — `form_data`, `dynamic_indicator_data`, and "
            "`repeat_group_instance` link to either `assignment_entity_status_id` (authenticated) "
            "or `public_submission_id` (public URL), enforced by PostgreSQL `CHECK` constraints.",
            "3. **Unified form items** — Indicators, questions, matrix cells, and plugin fields "
            "share the `form_item` table with a typed discriminator.",
            "4. **Polymorphic entity permissions** — `user_entity_permissions` grants access by "
            "`(entity_type, entity_id)` across countries and NS hierarchy nodes.",
            "5. **RBAC with scoped grants** — Roles (`rbac_*`) plus optional language/country scopes "
            "via `rbac_access_grant`.",
            "6. **Vector search** — `ai_embeddings`, `indicator_bank_embeddings`, and related tables "
            "use pgvector columns for RAG and semantic indicator lookup.",
            "",
            "---",
            "",
            "## Table reference",
            "",
        ]
    )

    by_domain: dict[str, list[dict]] = defaultdict(list)
    for table in tables:
        by_domain[table["domain"]].append(table)

    for domain in DOMAIN_ORDER:
        domain_tables = by_domain.get(domain)
        if not domain_tables:
            continue
        lines.append(f"### {domain}")
        lines.append("")
        for table in sorted(domain_tables, key=lambda t: t["name"]):
            lines.append(f"#### `{table['name']}`")
            if table.get("note"):
                lines.append("")
                lines.append(f"*{table['note']}*")
            lines.append("")
            lines.append("| Column | Type | Nullable | PK | FK references |")
            lines.append("|--------|------|----------|----|---------------|")
            for col in table["columns"]:
                fk = ", ".join(f"`{r}`" for r in col["foreign_keys"]) or "—"
                pk = "yes" if col["primary_key"] else ""
                null = "yes" if col["nullable"] else "no"
                lines.append(
                    f"| `{col['name']}` | `{col['type']}` | {null} | {pk} | {fk} |"
                )
            if table["constraints"]:
                lines.append("")
                lines.append("**Constraints:** " + "; ".join(f"`{c}`" for c in table["constraints"]))
            if table["indexes"]:
                lines.append("")
                lines.append("**Indexes:** " + "; ".join(f"`{i}`" for i in table["indexes"]))
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Companion files",
            "",
            f"- [`database-schema.html`](database-schema.html) — interactive browser viewer (single file; open locally or host statically)",
            f"- [`database-schema-catalog.csv`](database-schema-catalog.csv) — full column catalog for Excel/filtering",
            f"- [`database-schema-ddl.sql`](database-schema-ddl.sql) — PostgreSQL DDL from SQLAlchemy metadata (approximate; apply migrations for authoritative DDL)",
            "",
            "## Related documentation",
            "",
            f"- [DEVELOPER-HANDBOOK.md — Database architecture]({GITHUB_BLOB_BASE}/docs/DEVELOPER-HANDBOOK.md)",
            f"- [Backoffice migrations README]({GITHUB_BLOB_BASE}/Backoffice/migrations/README.md)",
            f"- [Flask-Migrate and pgvector runbook]({GITHUB_BLOB_BASE}/Backoffice/docs/runbooks/data/flask-migrate-and-pgvector.md)",
            f"- [Redis provisioning runbook]({GITHUB_BLOB_BASE}/Backoffice/docs/runbooks/deployment/redis-provisioning.md)",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")

    # DDL companion (CREATE TABLE statements only; no extensions/indexes from raw SQL).
    ddl_lines = [
        "-- IFRC Network Databank Backoffice schema (SQLAlchemy metadata export)",
        f"-- Generated {today}. For production DDL use pg_dump --schema-only on a migrated database.",
        "",
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "",
    ]
    for table in metadata.sorted_tables:
        if table.name == "alembic_version":
            continue
        ddl_lines.append(str(CreateTable(table).compile(dialect=postgresql.dialect())))
        ddl_lines.append("")
    ddl_sample_path.write_text("\n".join(ddl_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Backoffice DB schema for architecture review.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR.relative_to(_ROOT)})",
    )
    args = parser.parse_args()

    metadata = _load_metadata()
    tables = []
    for table in metadata.sorted_tables:
        if table.name == "alembic_version":
            continue
        tables.append(_collect_table_info(table))

    existing = {t["name"] for t in tables}
    for extra in SUPPLEMENTAL_TABLES:
        if extra["name"] not in existing:
            entry = dict(extra)
            entry["column_count"] = len(entry["columns"])
            tables.append(entry)

    out_dir = args.output_dir if args.output_dir.is_absolute() else _ROOT / args.output_dir
    md_path = out_dir / "database-schema.md"
    csv_path = out_dir / "database-schema-catalog.csv"
    html_path = out_dir / "database-schema.html"

    domain_summary = _domain_summary(tables)
    _write_markdown(md_path, metadata, tables)
    _write_csv(csv_path, tables)
    _write_html(html_path, tables, domain_summary)

    print(f"Wrote {md_path} ({len(tables)} tables)")
    print(f"Wrote {csv_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {out_dir / 'database-schema-ddl.sql'}")


if __name__ == "__main__":
    main()
