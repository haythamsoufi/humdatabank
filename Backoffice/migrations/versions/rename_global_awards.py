"""Rename US Macro Awards to Global Awards.

Revision ID: rename_global_awards
Revises: add_project_national_society
Create Date: 2026-11-18

Stored names follow the plugin rename: portfolio, template, project codes
(``USMA-`` to ``GA-``), the plugin id in the activation list, and the
import permission and role. Existing grants stay attached because the
permission and role rows are renamed in place.
"""

from alembic import op
from sqlalchemy import inspect, text


revision = "rename_global_awards"
down_revision = "add_project_national_society"
branch_labels = None
depends_on = None

_OLD_NAME = "US Macro Awards"
_NEW_NAME = "Global Awards"
_OLD_PREFIX = "USMA-"
_NEW_PREFIX = "GA-"
_OLD_PLUGIN = "us_macro_awards"
_NEW_PLUGIN = "global_awards"

_OLD_PERMISSION = "admin.us_macro_awards.manage"
_NEW_PERMISSION = "admin.global_awards.manage"
_OLD_ROLE = "admin_us_macro_awards"
_NEW_ROLE = "admin_global_awards"
_PERMISSION_NAME = "Global Awards: import"
_PERMISSION_DESCRIPTION = "Open Global Awards settings and import the MARC logframe"
_ROLE_NAME = "Admin: Global Awards"
_ROLE_DESCRIPTION = "Imports the Global Awards logframe and opens the plugin settings."
_OLD_PERMISSION_NAME = "US Macro Awards: import"
_OLD_PERMISSION_DESCRIPTION = "Open US Macro Awards settings and import the MARC logframe"
_OLD_ROLE_NAME = "Admin: US Macro Awards"
_OLD_ROLE_DESCRIPTION = "Imports the US Macro Awards logframe and opens the plugin settings."


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
        {
            "old_code": old_code,
            "new_code": new_code,
            "name": name,
            "description": description,
        },
    )


def _rename_role(conn, old_code: str, new_code: str, name: str, description: str) -> None:
    if not _has_table(conn, "rbac_role"):
        return
    old = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": old_code},
    ).fetchone()
    if not old:
        return
    new = conn.execute(
        text("SELECT id FROM rbac_role WHERE code = :code"),
        {"code": new_code},
    ).fetchone()
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
            text(
                """
                UPDATE rbac_role
                SET name = :name, description = :description
                WHERE id = :role_id
                """
            ),
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
        {
            "old_code": old_code,
            "new_code": new_code,
            "name": name,
            "description": description,
        },
    )


def _rename_project_codes(conn, old_prefix: str, new_prefix: str, portfolio: str) -> None:
    """Move ``OLD-ISO3`` references to ``NEW-ISO3`` for this portfolio only."""
    if not _has_table(conn, "project"):
        return
    conn.execute(
        text(
            """
            UPDATE project AS p
            SET reference = :new_prefix || substring(p.reference from :start_at)
            WHERE p.portfolio = :portfolio
              AND p.reference LIKE :old_like
              AND NOT EXISTS (
                  SELECT 1
                  FROM project AS other
                  WHERE other.id <> p.id
                    AND other.reference = :new_prefix || substring(p.reference from :start_at)
              )
            """
        ),
        {
            "new_prefix": new_prefix,
            "start_at": len(old_prefix) + 1,
            "portfolio": portfolio,
            "old_like": old_prefix + "%",
        },
    )


def _rename_labels(conn, old_name: str, new_name: str) -> None:
    like = f"%{old_name}%"
    if _has_table(conn, "project"):
        conn.execute(
            text(
                """
                UPDATE project
                SET portfolio = CASE WHEN portfolio = :old_name THEN :new_name ELSE portfolio END,
                    categories = CASE
                        WHEN categories IS NULL THEN NULL
                        ELSE replace(categories, :old_name, :new_name)
                    END,
                    title = CASE
                        WHEN title IS NULL THEN NULL
                        ELSE replace(title, :old_name, :new_name)
                    END,
                    plan_data = CASE
                        WHEN plan_data IS NOT NULL AND plan_data::text LIKE :like
                        THEN replace(plan_data::text, :old_name, :new_name)::jsonb
                        ELSE plan_data
                    END
                WHERE portfolio = :old_name
                   OR categories LIKE :like
                   OR title LIKE :like
                   OR (plan_data IS NOT NULL AND plan_data::text LIKE :like)
                """
            ),
            {"old_name": old_name, "new_name": new_name, "like": like},
        )
    if _has_table(conn, "form_template_version"):
        conn.execute(
            text(
                """
                UPDATE form_template_version
                SET name = CASE WHEN name = :old_name THEN :new_name ELSE name END,
                    description = CASE
                        WHEN description IS NULL THEN NULL
                        ELSE replace(description, :old_name, :new_name)
                    END,
                    name_translations = CASE
                        WHEN name_translations IS NOT NULL AND name_translations::text LIKE :like
                        THEN replace(name_translations::text, :old_name, :new_name)::json
                        ELSE name_translations
                    END,
                    description_translations = CASE
                        WHEN description_translations IS NOT NULL
                             AND description_translations::text LIKE :like
                        THEN replace(description_translations::text, :old_name, :new_name)::json
                        ELSE description_translations
                    END
                WHERE name = :old_name
                   OR description LIKE :like
                   OR (name_translations IS NOT NULL AND name_translations::text LIKE :like)
                   OR (
                       description_translations IS NOT NULL
                       AND description_translations::text LIKE :like
                   )
                """
            ),
            {"old_name": old_name, "new_name": new_name, "like": like},
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
        {
            "old_token": f'"{old_id}"',
            "new_token": f'"{new_id}"',
            "like": f'%"{old_id}"%',
        },
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


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _rename_project_codes(conn, _OLD_PREFIX, _NEW_PREFIX, _OLD_NAME)
    _rename_labels(conn, _OLD_NAME, _NEW_NAME)
    _rename_plugin_id(conn, _OLD_PLUGIN, _NEW_PLUGIN)
    _rename_permission(
        conn,
        _OLD_PERMISSION,
        _NEW_PERMISSION,
        _PERMISSION_NAME,
        _PERMISSION_DESCRIPTION,
    )
    _rename_role(conn, _OLD_ROLE, _NEW_ROLE, _ROLE_NAME, _ROLE_DESCRIPTION)


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _rename_project_codes(conn, _NEW_PREFIX, _OLD_PREFIX, _NEW_NAME)
    _rename_labels(conn, _NEW_NAME, _OLD_NAME)
    _rename_plugin_id(conn, _NEW_PLUGIN, _OLD_PLUGIN)
    _rename_permission(
        conn,
        _NEW_PERMISSION,
        _OLD_PERMISSION,
        _OLD_PERMISSION_NAME,
        _OLD_PERMISSION_DESCRIPTION,
    )
    _rename_role(conn, _NEW_ROLE, _OLD_ROLE, _OLD_ROLE_NAME, _OLD_ROLE_DESCRIPTION)
