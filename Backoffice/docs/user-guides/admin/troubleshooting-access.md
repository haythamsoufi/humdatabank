# Troubleshooting access (Admin)

Use this page when a user reports that they cannot log in or cannot see the pages/data they need.

## A user can't log in

Checklist:

- Confirm the email address is correct.
- Confirm the account is **active** (not deactivated).
- If your workflow uses password resets, set a new password and share it **securely**.

## A focal point can log in, but can't see assignments

Most common cause: they are **not assigned to a country/organization** or missing assignment roles.

What to check:

1. Open **Admin Panel → User Management → Manage Users**.
2. Open the user.
3. Go to the **User Details** tab and confirm:
   - They have an **Assignment role** (e.g., `assignment_editor_submitter` or `assignment_viewer`)
4. Go to the **Entity Permissions** tab and confirm:
   - At least one **country** (or organization) is assigned
5. Confirm there is an assignment created for that country/organization.

## A user says "Access denied" for an admin page

This usually means they are missing the required permissions.

What to do:

- Confirm whether the user should have **admin roles** or **assignment roles** (or both).
- If they should be an admin, assign the appropriate admin roles (e.g., `admin_full`, `admin_core`, or specific manager roles).
- Only System Managers can assign roles - contact a System Manager to update user roles.

## A user can't see a specific country

Common causes:

- The user is not assigned to that country.
- The user's role does not allow access to that area.

What to do:

1. Go to the user's **Entity Permissions** tab and confirm they are assigned the correct country/countries (or organizations).
2. If this is an admin workflow, confirm they have the relevant admin role(s) (e.g., `admin_countries_manager` for country management).

## Related

- [User Roles and Permissions](user-roles.md) - Understanding different roles and permissions
- [Manage users](manage-users.md)
- [Add a user](add-user.md)
- [Getting help](../common/getting-help.md)
