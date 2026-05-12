---
id: add-user
title: Add New User
description: Guide for creating a new user account in the system
roles: [admin]
category: user-management
keywords: [create user, new account, register, staff, member, signup]
pages:
  - /admin/users
  - /admin/users/new
---

# Add New User

This workflow guides administrators through creating a new user account in the system.

## Prerequisites

- Administrator role required
- Access to User & Access Management section

## Steps

### Step 1: Navigate to User Management
- **Page**: `/admin/users`
- **Selector**: `a[href="/admin/users/new"]`
- **Action**: Click "Add New User" button
- **Help**: Click the "Add New User" button in the top-right corner to start creating a new user account.
- **ActionText**: Continue

### Step 2: Fill User Details
- **Page**: `/admin/users/new`
- **Selector**: `#user-details-panel`
- **Action**: Fill in the required user information
- **Help**: Enter the user's email, name, role, and set an initial password. All fields marked with * are required.
- **ActionText**: Next

### Step 3: Configure Entity Permissions
- **Page**: `/admin/users/new`
- **Selector**: `#entity-permissions-tab, #entity-permissions-panel`
- **Action**: Click the Entity Permissions tab
- **Help**: Assign countries or organizational entities to the user. Focal Points must have at least one country assigned to access data.
- **ActionText**: Next

### Step 4: Save the New User
- **Page**: `/admin/users/new`
- **Selector**: `form button[type="submit"], .fixed button[type="submit"]`
- **Action**: Click Create User
- **Help**: Review all information and click "Create User" to complete. The user will receive their login credentials.
- **ActionText**: Got it

## Tips

- Users will need to change their password on first login for security
- Focal Points are limited to data from their assigned countries only
- Administrators have full system access across all countries
- You can always edit user details later from the User Management page

## Related Workflows

- [Manage Users](manage-users.md) - Edit and deactivate existing users
