"""Rename DREF monitoring to Emergency Operations.

Revision ID: rename_emergency_operations_monitoring
Revises: add_trace_user_feedback
Create Date: 2026-11-25

Stored names follow the plugin rename: plugin id, permissions, roles, the
access group, the portfolio on linked projects, the monitoring template, and
reminder links. Existing grants stay attached because those rows are renamed
in place. GO appeal codes (DREF, i-DREF) are unchanged.
"""

from alembic import op
from sqlalchemy import inspect, text


revision = "rename_emergency_operations_monitoring"
down_revision = "add_trace_user_feedback"
branch_labels = None
depends_on = None

_OLD_PLUGIN = "dref_monitoring"
_NEW_PLUGIN = "emergency_operations_monitoring"
_OLD_PORTFOLIO = "DREF"
_NEW_PORTFOLIO = "Emergency Operations"
_OLD_TEMPLATE = "DREF operational monitoring"
_NEW_TEMPLATE = "Emergency Operations"
_OLD_GROUP = "group_dref"
_NEW_GROUP = "group_emergency_operations"
_OLD_FIELD = "plugin_dref_operational_report"
_NEW_FIELD = "plugin_emergency_operations_report"
_OLD_JOB = "dref.draft"
_NEW_JOB = "emergency_operations.draft"

_PERMISSIONS = (
    (
        "admin.dref_monitoring.manage",
        "admin.emergency_operations_monitoring.manage",
        "Emergency Operations: manage",
        "Open Emergency Operations settings and run a GO sync",
        "DREF monitoring: manage",
        "Open DREF monitoring settings and run a GO sync",
    ),
    (
        "admin.dref_monitoring.enter",
        "admin.emergency_operations_monitoring.enter",
        "Emergency Operations: data entry",
        "File monitoring updates on operations in scope",
        "DREF monitoring: data entry",
        "File monitoring updates on operations in scope",
    ),
    (
        "admin.dref_monitoring.validate",
        "admin.emergency_operations_monitoring.validate",
        "Emergency Operations: validation",
        "Validate monitoring plans and reports for the National Society",
        "DREF monitoring: validation",
        "Validate monitoring plans and reports for the National Society",
    ),
    (
        "admin.dref_monitoring.review",
        "admin.emergency_operations_monitoring.review",
        "Emergency Operations: technical review",
        "Review reports and sign off delegation-owned changes",
        "DREF monitoring: technical review",
        "Review reports and sign off delegation-owned changes",
    ),
    (
        "admin.dref_monitoring.portfolio",
        "admin.emergency_operations_monitoring.portfolio",
        "Emergency Operations: portfolio",
        "See every emergency operation and the portfolio overview",
        "DREF monitoring: portfolio",
        "See every DREF operation and the portfolio overview",
    ),
    (
        "admin.data_explore.dref_monitoring",
        "admin.data_explore.emergency_operations_monitoring",
        "Data Explorer: Emergency Operations",
        "Open the Emergency Operations tab in Data Explorer",
        "Data Explorer: DREF monitoring",
        "Open the DREF monitoring tab in Data Explorer",
    ),
)
_ROLES = (
    (
        "dref_monitoring_entry",
        "emergency_operations_monitoring_entry",
        "Emergency Operations: data entry",
        "Files activity, reach, expenditure, and procurement updates.",
        "DREF monitoring: data entry",
        "Files activity, reach, expenditure, and procurement updates.",
    ),
    (
        "dref_monitoring_validation",
        "emergency_operations_monitoring_validation",
        "Emergency Operations: validation",
        "National Society leadership. Validates the plan and submitted reports.",
        "DREF monitoring: validation",
        "National Society leadership. Validates the plan and submitted reports.",
    ),
    (
        "dref_monitoring_review",
        "emergency_operations_monitoring_review",
        "Emergency Operations: technical review",
        "IFRC delegation review of reports and out-of-bounds changes.",
        "DREF monitoring: technical review",
        "IFRC delegation review of reports and out-of-bounds changes.",
    ),
    (
        "dref_monitoring_portfolio",
        "emergency_operations_monitoring_portfolio",
        "Emergency Operations: portfolio",
        "Emergency Operations and PMER portfolio oversight, including the Data Explorer tab.",
        "DREF monitoring: portfolio",
        "DREF and PMER portfolio oversight, including the Data Explorer tab.",
    ),
    (
        "admin_dref_monitoring",
        "admin_emergency_operations_monitoring",
        "Emergency Operations: admin",
        "Settings, GO sync, and portfolio oversight.",
        "DREF monitoring: admin",
        "Settings, GO sync, and portfolio oversight.",
    ),
)


def _has_table(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _rename_permission(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    if not _has_table(conn, "rbac_permission"):
        return
    old = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": old_code},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_permission WHERE code = :code"),
        {"code": new_code},
    ).fetchone()
    if new:
        conn.execute(
            text(
                """
                DELETE FROM rbac_role_permission
                WHERE permission_id = :old_id
                  AND role_id IN (
                      SELECT role_id FROM rbac_role_permission WHERE permission_id = :new_id
                  )
                """
            ),
            {"new_id": new[0], "old_id": old[0]},
        )
        conn.execute(
            text("UPDATE rbac_role_permission SET permission_id = :new_id WHERE permission_id = :old_id"),
            {"new_id": new[0], "old_id": old[0]},
        )
        conn.execute(text("DELETE FROM rbac_permission WHERE id = :perm_id"), {"perm_id": old[0]})
        conn.execute(
            text(
                """
                UPDATE rbac_permission
                SET name = :name, description = :description
                WHERE id = :perm_id
                """
            ),
            {"perm_id": new[0], "name": name, "description": description},
        )
        return
    conn.execute(
        text(
            """
            UPDATE rbac_permission
            SET code = :new_code, name = :name, description = :description
            WHERE code = :old_code
            """
        ),
        {"old_code": old_code, "new_code": new_code, "name": name, "description": description},
    )


def _rename_role(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    if not _has_table(conn, "rbac_role"):
        return
    old = conn.execute(text("SELECT id FROM rbac_role WHERE code = :code"), {"code": old_code}).fetchone()
    if not old:
        return
    new = conn.execute(text("SELECT id FROM rbac_role WHERE code = :code"), {"code": new_code}).fetchone()
    if new:
        conn.execute(
            text(
                """
                INSERT INTO rbac_user_role (user_id, role_id, created_at)
                SELECT user_id, :new_role_id, created_at
                FROM rbac_user_role
                WHERE role_id = :old_role_id
                ON CONFLICT DO NOTHING
                """
            ),
            {"old_role_id": old[0], "new_role_id": new[0]},
        )
        conn.execute(text("DELETE FROM rbac_user_role WHERE role_id = :role_id"), {"role_id": old[0]})
        conn.execute(text("DELETE FROM rbac_role_permission WHERE role_id = :role_id"), {"role_id": old[0]})
        conn.execute(text("DELETE FROM rbac_role WHERE id = :role_id"), {"role_id": old[0]})
        conn.execute(
            text("UPDATE rbac_role SET name = :name, description = :description WHERE id = :role_id"),
            {"role_id": new[0], "name": name, "description": description},
        )
        return
    conn.execute(
        text(
            """
            UPDATE rbac_role
            SET code = :new_code, name = :name, description = :description
            WHERE code = :old_code
            """
        ),
        {"old_code": old_code, "new_code": new_code, "name": name, "description": description},
    )


def _rename_plugin_id(conn, old_id: str, new_id: str) -> None:
    if not _has_table(conn, "plugin_data"):
        return
    conn.execute(
        text(
            """
            UPDATE plugin_data
            SET data = replace(data::text, :old_token, :new_token)::jsonb
            WHERE data::text LIKE :like
            """
        ),
        {"old_token": f'"{old_id}"', "new_token": f'"{new_id}"', "like": f'%"{old_id}"%'},
    )
    conn.execute(
        text(
            """
            UPDATE plugin_data
            SET plugin_id = :new_id
            WHERE plugin_id = :old_id
              AND NOT EXISTS (
                  SELECT 1 FROM plugin_data AS other WHERE other.plugin_id = :new_id
              )
            """
        ),
        {"old_id": old_id, "new_id": new_id},
    )


def _rename_portfolio(conn, source: str, target: str) -> None:
    if not _has_table(conn, "project") or not _has_table(conn, "dref_mon_operation"):
        return
    conn.execute(
        text(
            """
            UPDATE project
            SET portfolio = :target
            WHERE portfolio = :source
              AND (
                  id IN (SELECT project_id FROM dref_mon_operation WHERE project_id IS NOT NULL)
                  OR (plan_data IS NOT NULL AND plan_data::text LIKE '%dref_operation_id%')
              )
            """
        ),
        {"source": source, "target": target},
    )


def _rename_template(conn, source: str, target: str) -> None:
    if not _has_table(conn, "form_template_version"):
        return
    conn.execute(
        text(
            """
            UPDATE form_template_version
            SET name = :target,
                description = CASE
                    WHEN description IS NULL THEN NULL
                    ELSE replace(
                        replace(description, 'Routine DREF monitoring', 'Routine Emergency Operations monitoring'),
                        'DREF operational monitoring',
                        :target
                    )
                END
            WHERE name = :source
            """
        ),
        {"source": source, "target": target},
    )


def _rename_group(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    if not _has_table(conn, "rbac_role"):
        return
    exists = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": new_code},
    ).fetchone()
    if exists:
        return
    conn.execute(
        text(
            """
            UPDATE rbac_role
            SET code = :new_code, name = :name, description = :description
            WHERE code = :old_code
            """
        ),
        {"old_code": old_code, "new_code": new_code, "name": name, "description": description},
    )


def _replace_where(conn, table: str, column: str, old: str, new: str, *, like: bool = False) -> None:
    if not _has_table(conn, table):
        return
    if like:
        conn.execute(
            text(
                f"""
                UPDATE {table}
                SET {column} = replace({column}, :old, :new)
                WHERE {column} LIKE :pattern
                """
            ),
            {"old": old, "new": new, "pattern": f"%{old}%"},
        )
        return
    conn.execute(
        text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),
        {"old": old, "new": new},
    )


def _apply(conn, *, forward: bool) -> None:
    if forward:
        _rename_plugin_id(conn, _OLD_PLUGIN, _NEW_PLUGIN)
        _rename_portfolio(conn, _OLD_PORTFOLIO, _NEW_PORTFOLIO)
        _rename_template(conn, _OLD_TEMPLATE, _NEW_TEMPLATE)
        _rename_group(
            conn,
            _OLD_GROUP,
            _NEW_GROUP,
            "Emergency Operations",
            "People who may open and file Emergency Operations assignments.",
        )
        for old_code, new_code, name, description, _old_name, _old_description in _PERMISSIONS:
            _rename_permission(conn, old_code, new_code, name, description)
        for old_code, new_code, name, description, _old_name, _old_description in _ROLES:
            _rename_role(conn, old_code, new_code, name, description)
        _replace_where(conn, "form_item", "item_type", _OLD_FIELD, _NEW_FIELD)
        _replace_where(conn, "ai_jobs", "job_type", _OLD_JOB, _NEW_JOB)
        _replace_where(conn, "notification", "category", _OLD_PLUGIN, _NEW_PLUGIN)
        _replace_where(
            conn,
            "notification",
            "title_key",
            "notification.dref_monitoring.reminder.title",
            "notification.emergency_operations_monitoring.reminder.title",
        )
        _replace_where(
            conn,
            "notification",
            "title",
            "DREF monitoring reminder:",
            "Emergency Operations reminder:",
            like=True,
        )
        _replace_where(conn, "notification", "related_url", "/dref-monitoring/", "/emergency-operations/", like=True)
        return
    _rename_plugin_id(conn, _NEW_PLUGIN, _OLD_PLUGIN)
    _rename_portfolio(conn, _NEW_PORTFOLIO, _OLD_PORTFOLIO)
    _rename_template(conn, _NEW_TEMPLATE, _OLD_TEMPLATE)
    _rename_group(
        conn,
        _NEW_GROUP,
        _OLD_GROUP,
        "DREF",
        "People who may open and file DREF monitoring assignments.",
    )
    for old_code, new_code, _name, _description, old_name, old_description in _PERMISSIONS:
        _rename_permission(conn, new_code, old_code, old_name, old_description)
    for old_code, new_code, _name, _description, old_name, old_description in _ROLES:
        _rename_role(conn, new_code, old_code, old_name, old_description)
    _replace_where(conn, "form_item", "item_type", _NEW_FIELD, _OLD_FIELD)
    _replace_where(conn, "ai_jobs", "job_type", _NEW_JOB, _OLD_JOB)
    _replace_where(conn, "notification", "category", _NEW_PLUGIN, _OLD_PLUGIN)
    _replace_where(
        conn,
        "notification",
        "title_key",
        "notification.emergency_operations_monitoring.reminder.title",
        "notification.dref_monitoring.reminder.title",
    )
    _replace_where(
        conn,
        "notification",
        "title",
        "Emergency Operations reminder:",
        "DREF monitoring reminder:",
        like=True,
    )
    _replace_where(conn, "notification", "related_url", "/emergency-operations/", "/dref-monitoring/", like=True)


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _apply(conn, forward=True)


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _apply(conn, forward=False)
