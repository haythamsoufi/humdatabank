"""Rename Global Awards to Global Award.

Revision ID: rename_global_award_singular
Revises: dref_monitoring_indicator_adapter
Create Date: 2026-11-20

Stored names follow the plugin rename: portfolio, template, the plugin id
in the activation list, and the import and Data Explorer permissions and
roles. Existing grants stay attached because those rows are renamed in place.

``Global Award`` is a prefix of ``Global Awards``, so the reverse text
replace parks the plural form first. Running either direction twice is a no-op.
"""

from alembic import op
from sqlalchemy import inspect, text


revision = "rename_global_award_singular"
down_revision = "dref_monitoring_indicator_adapter"
branch_labels = None
depends_on = None

_OLD_NAME = "Global Awards"
_NEW_NAME = "Global Award"
_PLACEHOLDER = "<<GLOBAL_AWARD_PLURAL>>"
_OLD_PLUGIN = "global_awards"
_NEW_PLUGIN = "global_award"

_PERMISSIONS = (
    (
        "admin.global_awards.manage",
        "admin.global_award.manage",
        "Global Award: import",
        "Open Global Award settings and import the MARC logframe",
        "Global Awards: import",
        "Open Global Awards settings and import the MARC logframe",
    ),
    (
        "admin.data_explore.global_awards",
        "admin.data_explore.global_award",
        "Data Explorer: Global Award",
        "Access the Global Award tab in Data Explorer",
        "Data Explorer: Global Awards",
        "Access the Global Awards tab in Data Explorer",
    ),
)
_ROLES = (
    (
        "admin_global_awards",
        "admin_global_award",
        "Admin: Global Award",
        "Imports the Global Award logframe and opens the plugin settings.",
        "Admin: Global Awards",
        "Imports the Global Awards logframe and opens the plugin settings.",
    ),
    (
        "admin_data_explorer_global_awards",
        "admin_data_explorer_global_award",
        "Admin: Data Explorer (Global Award)",
        "Access the Global Award tab in Data Explorer.",
        "Admin: Data Explorer (Global Awards)",
        "Access the Global Awards tab in Data Explorer.",
    ),
)


def _has_table(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _swap_label(value_sql: str, *, forward: bool) -> str:
    """Replace the product name without turning ``Global Awards`` into ``Global Awardss``.

    Forward is a plain replace: ``Global Award`` does not contain ``Global Awards``.
    Reverse parks the plural form first, then expands the remaining singular.
    """
    if forward:
        return f"replace({value_sql}, :source, :target)"
    return (
        f"replace(replace(replace({value_sql}, :plural, :placeholder), :singular, :target), "
        ":placeholder, :plural)"
    )


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


def _rename_labels(conn, source: str, target: str) -> None:
    """Rewrite the product name. ``source`` is the form currently stored."""
    forward = source == _OLD_NAME
    binds = {
        "source": source,
        "target": target,
        "plural": _OLD_NAME,
        "singular": _NEW_NAME,
        "placeholder": _PLACEHOLDER,
        "like": f"%{source}%",
    }
    title_sql = _swap_label("title", forward=forward)
    categories_sql = _swap_label("categories", forward=forward)
    plan_sql = _swap_label("plan_data::text", forward=forward)
    description_sql = _swap_label("description", forward=forward)
    name_i18n_sql = _swap_label("name_translations::text", forward=forward)
    description_i18n_sql = _swap_label("description_translations::text", forward=forward)
    if _has_table(conn, "project"):
        conn.execute(
            text(
                f"""
                UPDATE project
                SET portfolio = CASE WHEN portfolio = :source THEN :target ELSE portfolio END,
                    categories = CASE
                        WHEN categories IS NULL THEN NULL
                        ELSE {categories_sql}
                    END,
                    title = CASE
                        WHEN title IS NULL THEN NULL
                        ELSE {title_sql}
                    END,
                    plan_data = CASE
                        WHEN plan_data IS NOT NULL AND plan_data::text LIKE :like
                        THEN ({plan_sql})::jsonb
                        ELSE plan_data
                    END
                WHERE portfolio = :source
                   OR categories LIKE :like
                   OR title LIKE :like
                   OR (plan_data IS NOT NULL AND plan_data::text LIKE :like)
                """
            ),
            binds,
        )
    if _has_table(conn, "form_template_version"):
        conn.execute(
            text(
                f"""
                UPDATE form_template_version
                SET name = CASE WHEN name = :source THEN :target ELSE name END,
                    description = CASE
                        WHEN description IS NULL THEN NULL
                        ELSE {description_sql}
                    END,
                    name_translations = CASE
                        WHEN name_translations IS NOT NULL AND name_translations::text LIKE :like
                        THEN ({name_i18n_sql})::json
                        ELSE name_translations
                    END,
                    description_translations = CASE
                        WHEN description_translations IS NOT NULL
                             AND description_translations::text LIKE :like
                        THEN ({description_i18n_sql})::json
                        ELSE description_translations
                    END
                WHERE name = :source
                   OR description LIKE :like
                   OR (name_translations IS NOT NULL AND name_translations::text LIKE :like)
                   OR (
                       description_translations IS NOT NULL
                       AND description_translations::text LIKE :like
                   )
                """
            ),
            binds,
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


def _apply(conn, source_name: str, target_name: str, forward: bool) -> None:
    _rename_labels(conn, source_name, target_name)
    if forward:
        _rename_plugin_id(conn, _OLD_PLUGIN, _NEW_PLUGIN)
        for old_code, new_code, name, description, _old_name, _old_description in _PERMISSIONS:
            _rename_permission(conn, old_code, new_code, name, description)
        for old_code, new_code, name, description, _old_name, _old_description in _ROLES:
            _rename_role(conn, old_code, new_code, name, description)
        return
    _rename_plugin_id(conn, _NEW_PLUGIN, _OLD_PLUGIN)
    for old_code, new_code, _name, _description, old_name, old_description in _PERMISSIONS:
        _rename_permission(conn, new_code, old_code, old_name, old_description)
    for old_code, new_code, _name, _description, old_name, old_description in _ROLES:
        _rename_role(conn, new_code, old_code, old_name, old_description)


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _apply(conn, _OLD_NAME, _NEW_NAME, forward=True)


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    _apply(conn, _NEW_NAME, _OLD_NAME, forward=False)
