# Add New User

Use this guide to create a new Backoffice account and assign appropriate roles.

## Before you start

- You need **Admin** access with user creation permissions.
- Understand the **RBAC (Role-Based Access Control)** system - users can have multiple roles.
- For users who will work with assignments, know which **country/countries** or **organizations** they should access.

## Steps

1. Open **Admin Panel** → **User Management** → **Manage Users**.
2. Click **Add New User**.
3. Fill in the required fields in the **User Details** tab:
   - **Email**: this will be the login username
   - **Full name**
   - **Title** (optional): job title
   - **Initial password** (follow your organization's password policy)
4. Select **Role Type**:
   - **Admin**: for users who need administrative access
   - **Focal Point**: for users who will enter and submit assignment data
5. Assign **Roles** based on the role type:
   - **For Admins**: Select from Admin roles (e.g., Admin: Full, Admin: Core, or specific manager roles like Admin: Templates Manager)
   - **For Focal Points**: Select Assignment roles (typically `Assignment Editor & Submitter` for data entry)
   - Users can have multiple roles - see [User Roles and Permissions](user-roles.md) for details
6. Go to the **Entity Permissions** tab:
   - Assign **at least one country** (or organization) for focal points - they need this to see assignments
   - Admins may also need country assignments depending on their roles
7. Click **Create User**.

## After you create the user

- Share the login details with the user **securely**.
- If the user cannot see expected data, review their **roles** and **entity assignments** (countries/organizations).

## Tips

- **Start with presets**: Use "Admin: Core" or "Admin: Full" presets for administrators, then add specific roles as needed.
- **Focal points need countries**: Users with assignment roles must be assigned to specific countries/organizations to see assignments.
- **Multiple roles**: Users can have both admin and assignment roles if needed.
- See [User Roles and Permissions](user-roles.md) for detailed role descriptions.

## Common problems

- **The user can log in but sees no assignments**: they likely have no country/organization assigned. Assign at least one entity in the Entity Permissions tab.
- **Access denied to admin pages**: confirm they have appropriate admin roles assigned (check the Roles section).
- **User can't assign roles to others**: only users with `admin.users.roles.assign` permission can assign roles.

## Related

- [User Roles and Permissions](user-roles.md) - Understanding different roles and when to use them
- [Manage users](manage-users.md)
- [Troubleshooting access (Admin)](troubleshooting-access.md)
