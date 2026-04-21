# Role recipes (common admin tasks)

Use this page when you’re not sure which roles to assign for a specific task.

## Before you start

- Roles control **what pages/actions** a user can access.
- Many users also need **country access** to see assignments for specific countries.

## Recipe: Standard focal point (data entry)

Give the user:

- Role: `assignment_editor_submitter`
- Country access: assign at least one country

They can:

- view assignments for their countries
- enter data and submit

## Recipe: Focal point who also approves

Give the user:

- Roles: `assignment_editor_submitter`, `assignment_approver`
- Country access: assign the relevant countries

## Recipe: Read-only viewer

Give the user:

- Role: `assignment_viewer`
- Country access: optional (depends on how your system is configured)

## Recipe: Template designer (no user management)

Give the user:

- A template management role (for example: `admin_templates_manager`)

Optionally also:

- `assignment_viewer` (so they can see how templates are used)

## Recipe: Assignment manager (no template edits)

Give the user:

- `admin_assignments_manager`

Optionally:

- `assignment_viewer` or `assignment_approver` if they also review submissions

## Recipe: User manager (HR / access admin)

Give the user:

- `admin_users_manager`

They can create/manage users and assign roles (within their allowed scope).

## Recipe: Document uploader only

Give the user:

- `assignment_documents_uploader`
- Country access (if required by your setup)

They can upload supporting documents but not submit form data.

## Common problems

- **User can’t see assignments**: they usually need both (1) an assignment role and (2) country access.
- **User sees “Access denied”**: they’re missing the specific role for that admin module.

## Related

- [User roles and permissions](user-roles.md)
- [Manage users](manage-users.md)
- [Troubleshooting access (Admin)](troubleshooting-access.md)
