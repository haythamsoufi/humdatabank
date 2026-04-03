"""
Migrate Data Explorer permission from single 'Use' to three granular permissions:
- Data Table
- Analysis
- Compliance

This migration:
1. Creates the new permissions and roles via RBAC seeding
2. Migrates users who had the old admin_data_explorer role to all three new roles
3. Removes the old admin_data_explorer role and admin.data_explore.use permission
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'migrate_data_explorer_perms'
down_revision = 'add_ai_formdata_validation'
branch_labels = None
depends_on = None


def upgrade():
    """
    Migrate from single Data Explorer permission to three granular permissions.
    """
    conn = op.get_bind()

    # Step 1: Create new permissions if they don't exist
    new_permissions = [
        ('admin.data_explore.data_table', 'Data Explorer: Data Table', 'Access the Data Table tab in Data Explorer'),
        ('admin.data_explore.analysis', 'Data Explorer: Analysis', 'Access the Analysis tab in Data Explorer'),
        ('admin.data_explore.compliance', 'Data Explorer: Compliance', 'Access the Compliance tab in Data Explorer'),
    ]

    for code, name, description in new_permissions:
        # Check if permission exists
        result = conn.execute(text(
            "SELECT id FROM rbac_permission WHERE code = :code"
        ), {"code": code}).fetchone()

        if not result:
            conn.execute(text("""
                INSERT INTO rbac_permission (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """), {"code": code, "name": name, "description": description})

    # Step 2: Create new roles if they don't exist
    new_roles = [
        ('admin_data_explorer_data_table', 'Admin: Data Explorer (Data Table)', 'Access the Data Table tab in Data Explorer.', 'admin.data_explore.data_table'),
        ('admin_data_explorer_analysis', 'Admin: Data Explorer (Analysis)', 'Access the Analysis tab in Data Explorer.', 'admin.data_explore.analysis'),
        ('admin_data_explorer_compliance', 'Admin: Data Explorer (Compliance)', 'Access the Compliance tab in Data Explorer.', 'admin.data_explore.compliance'),
    ]

    for role_code, role_name, role_desc, perm_code in new_roles:
        # Check if role exists
        result = conn.execute(text(
            "SELECT id FROM rbac_role WHERE code = :code"
        ), {"code": role_code}).fetchone()

        if not result:
            # Create role
            conn.execute(text("""
                INSERT INTO rbac_role (code, name, description, created_at)
                VALUES (:code, :name, :description, CURRENT_TIMESTAMP)
            """), {"code": role_code, "name": role_name, "description": role_desc})

            # Get the new role ID
            role_result = conn.execute(text(
                "SELECT id FROM rbac_role WHERE code = :code"
            ), {"code": role_code}).fetchone()

            if role_result:
                role_id = role_result[0]

                # Get permission ID
                perm_result = conn.execute(text(
                    "SELECT id FROM rbac_permission WHERE code = :code"
                ), {"code": perm_code}).fetchone()

                if perm_result:
                    perm_id = perm_result[0]

                    # Link role to permission
                    conn.execute(text("""
                        INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
                        VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                    """), {"role_id": role_id, "perm_id": perm_id})

    # Step 3: Find users who have the old admin_data_explorer role
    old_role = conn.execute(text(
        "SELECT id FROM rbac_role WHERE code = 'admin_data_explorer'"
    )).fetchone()

    if old_role:
        old_role_id = old_role[0]

        # Get all user IDs with the old role
        user_ids = conn.execute(text(
            "SELECT user_id FROM rbac_user_role WHERE role_id = :role_id"
        ), {"role_id": old_role_id}).fetchall()

        # Get IDs of new roles
        new_role_ids = []
        for role_code, _, _, _ in new_roles:
            result = conn.execute(text(
                "SELECT id FROM rbac_role WHERE code = :code"
            ), {"code": role_code}).fetchone()
            if result:
                new_role_ids.append(result[0])

        # Assign all new roles to users who had the old role
        for (user_id,) in user_ids:
            for new_role_id in new_role_ids:
                conn.execute(text("""
                    INSERT INTO rbac_user_role (user_id, role_id, created_at)
                    VALUES (:user_id, :role_id, CURRENT_TIMESTAMP)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "role_id": new_role_id})

        # Remove old role assignments
        conn.execute(text(
            "DELETE FROM rbac_user_role WHERE role_id = :role_id"
        ), {"role_id": old_role_id})

        # Remove old role-permission links
        conn.execute(text(
            "DELETE FROM rbac_role_permission WHERE role_id = :role_id"
        ), {"role_id": old_role_id})

        # Delete old role
        conn.execute(text(
            "DELETE FROM rbac_role WHERE id = :id"
        ), {"id": old_role_id})

    # Step 4: Remove old permission
    old_perm = conn.execute(text(
        "SELECT id FROM rbac_permission WHERE code = 'admin.data_explore.use'"
    )).fetchone()

    if old_perm:
        old_perm_id = old_perm[0]

        # Remove any remaining role-permission links
        conn.execute(text(
            "DELETE FROM rbac_role_permission WHERE permission_id = :perm_id"
        ), {"perm_id": old_perm_id})

        # Delete old permission
        conn.execute(text(
            "DELETE FROM rbac_permission WHERE id = :id"
        ), {"id": old_perm_id})


def downgrade():
    """
    Revert to single Data Explorer permission.
    """
    conn = op.get_bind()

    # Create old permission
    conn.execute(text("""
        INSERT INTO rbac_permission (code, name, description, created_at)
        VALUES ('admin.data_explore.use', 'Use data exploration', 'Use data exploration', CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
    """))

    # Create old role
    conn.execute(text("""
        INSERT INTO rbac_role (code, name, description, created_at)
        VALUES ('admin_data_explorer', 'Admin: Data Explorer (Use)', 'Use data exploration tools.', CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
    """))

    # Get old role and permission IDs
    old_role = conn.execute(text(
        "SELECT id FROM rbac_role WHERE code = 'admin_data_explorer'"
    )).fetchone()
    old_perm = conn.execute(text(
        "SELECT id FROM rbac_permission WHERE code = 'admin.data_explore.use'"
    )).fetchone()

    if old_role and old_perm:
        # Link role to permission
        conn.execute(text("""
            INSERT INTO rbac_role_permission (role_id, permission_id, created_at)
            VALUES (:role_id, :perm_id, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
        """), {"role_id": old_role[0], "perm_id": old_perm[0]})

    # Find users who have any of the new roles and give them the old role
    new_role_codes = [
        'admin_data_explorer_data_table',
        'admin_data_explorer_analysis',
        'admin_data_explorer_compliance',
    ]

    if old_role:
        for role_code in new_role_codes:
            result = conn.execute(text(
                "SELECT id FROM rbac_role WHERE code = :code"
            ), {"code": role_code}).fetchone()

            if result:
                new_role_id = result[0]

                # Get users with this role
                users = conn.execute(text(
                    "SELECT user_id FROM rbac_user_role WHERE role_id = :role_id"
                ), {"role_id": new_role_id}).fetchall()

                for (user_id,) in users:
                    conn.execute(text("""
                        INSERT INTO rbac_user_role (user_id, role_id, created_at)
                        VALUES (:user_id, :role_id, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                    """), {"user_id": user_id, "role_id": old_role[0]})

    # Remove new roles and permissions
    for role_code in new_role_codes:
        result = conn.execute(text(
            "SELECT id FROM rbac_role WHERE code = :code"
        ), {"code": role_code}).fetchone()

        if result:
            role_id = result[0]
            conn.execute(text("DELETE FROM rbac_user_role WHERE role_id = :id"), {"id": role_id})
            conn.execute(text("DELETE FROM rbac_role_permission WHERE role_id = :id"), {"id": role_id})
            conn.execute(text("DELETE FROM rbac_role WHERE id = :id"), {"id": role_id})

    new_perm_codes = [
        'admin.data_explore.data_table',
        'admin.data_explore.analysis',
        'admin.data_explore.compliance',
    ]

    for perm_code in new_perm_codes:
        result = conn.execute(text(
            "SELECT id FROM rbac_permission WHERE code = :code"
        ), {"code": perm_code}).fetchone()

        if result:
            perm_id = result[0]
            conn.execute(text("DELETE FROM rbac_role_permission WHERE permission_id = :id"), {"id": perm_id})
            conn.execute(text("DELETE FROM rbac_permission WHERE id = :id"), {"id": perm_id})
