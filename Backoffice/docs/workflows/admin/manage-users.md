---
id: manage-users
title: Manage Existing Users
description: Guide for editing, deactivating, and managing user accounts
roles: [admin]
category: user-management
keywords: [edit user, update user, deactivate, reset password, change role, modify account]
pages:
  - /admin/users
  - /admin/users/edit
---

# Manage Existing Users

This workflow guides administrators through managing existing user accounts including editing, deactivating, and resetting passwords.

## Prerequisites

- Administrator role required
- Access to User & Access Management section

## Steps

### Step 1: Navigate to User Management
- **Page**: `/admin/users`
- **Selector**: `.user-list, [data-testid="user-list"], table`
- **Action**: View the list of all users
- **Help**: The User Management page shows all users in the system. You can search, filter, and sort users from here.
- **ActionText**: Next

### Step 2: Find the User to Manage
- **Page**: `/admin/users`
- **Selector**: `input[type="search"], .search-input, [data-testid="search"]`
- **Action**: Search for the user
- **Help**: Use the search box to find a specific user by name or email. You can also use filters to narrow down the list.
- **ActionText**: Next

### Step 3: Open User Edit Form
- **Page**: `/admin/users`
- **Selector**: `a[href*="/admin/users/edit"], .edit-user-btn, [data-action="edit"]`
- **Action**: Click the edit icon next to the user
- **Help**: Click the edit icon (pencil) next to the user you want to modify. This opens the user edit form.
- **ActionText**: Continue

### Step 4: Modify User Details
- **Page**: `/admin/users/edit`
- **Selector**: `#user-details-panel, form`
- **Action**: Update the user information as needed
- **Help**: You can update the user's name, email, role, and password. Changes take effect immediately after saving.
- **Fields**:
  - Full Name: Update the user's name
  - Email: Change the login email (user will need to verify)
  - Role: Switch between Administrator and Focal Point
  - Password: Leave blank to keep current, or enter new password

### Step 5: Update Permissions
- **Page**: `/admin/users/edit`
- **Selector**: `#entity-permissions-tab`
- **Action**: Modify country assignments
- **Help**: Add or remove countries for Focal Points. Administrators automatically have access to all countries.
- **ActionText**: Next

### Step 6: Save Changes
- **Page**: `/admin/users/edit`
- **Selector**: `form button[type="submit"], .fixed button[type="submit"]`
- **Action**: Click Save Changes
- **Help**: Click "Save Changes" to apply your updates. The user will be notified if their access has changed.
- **ActionText**: Got it

## Additional Actions

### Deactivate a User
To deactivate a user account:
1. Find the user in the list
2. Click the status toggle or deactivate button
3. Confirm the deactivation

Deactivated users cannot log in but their data is preserved.

### Reset Password
To reset a user's password:
1. Open the user edit form
2. Enter a new password in the password field
3. Save changes
4. Share the new password with the user securely

## Tips

- Deactivating a user preserves all their data and submissions
- Role changes take effect on the user's next login
- Consider using the Analytics dashboard to review user activity before making changes
- Audit logs track all user management actions

## Related Workflows

- [Add New User](add-user.md) - Create new user accounts
