# User & Role Management

Day-to-day guide for the IFRC App team to manage Backoffice users. No code changes are required for any of the tasks on this page.

---

## 1. Roles Overview

| Role | What they can do | Typical person |
|------|-----------------|----------------|
| **System Manager** | Full access: all admin, all countries, system configuration, user management | IFRC App team lead |
| **Admin** | All form/content management for assigned countries; cannot manage system settings or other users | Regional coordinator |
| **Focal Point** | Submit and review forms for their assigned countries only; read-only on other areas | National Society contact |
| **View Only** | Read-only across all assigned areas | Monitoring/auditing staff |

> Roles are additive per user. A user can only see and act on **countries explicitly assigned** to them (except System Manager, who has global access).

---

## 2. Creating a User (Backoffice)

**Route:** Admin → User Management → Create User

**Required fields:**
- Full name
- Email address (used as login username)
- Role (see table above)
- Temporary password (user should change on first login)
- Country assignments (at least one, unless System Manager)

**CLI alternative** (when UI is unavailable — requires server access):
```bash
cd Backoffice
python -m flask create-admin
# Interactive prompt; creates a System Manager account
```

**Seed test accounts** (development/staging only):
```bash
python -m flask seed-test-data
# Creates System Manager, Admin, and Focal Point accounts with test passwords
```

---

## 3. Editing a User

**Route:** Admin → User Management → [select user] → Edit

You can change:
- Name, email
- Role
- Country assignments (add/remove)
- Active/inactive status (deactivating blocks login without deleting history)

> Changing a user's role takes effect on their **next login** (existing session remains valid until it expires or is manually invalidated).

---

## 4. Deactivating a User (Leavers)

When a staff member leaves:

1. Admin → User Management → [select user] → Edit → Set **Active = No**
2. Optionally: Admin → Sessions → find their active session → End session (forces immediate logout)
3. If they also held token-based sessions (Bearer JWT): those tokens expire on their normal lifetime; or rotate `SECRET_KEY` to immediately invalidate **all** token-backed sessions site-wide (see [Session management](../sessions/session-management.md) for impact).

> Do not delete users; deactivation preserves the audit trail for data they submitted or approved.

---

## 5. Country Assignments

A user can be assigned to **multiple countries**. Form submissions, assignments, and data visible to a user are scoped to their assigned countries.

**To add/remove countries:**
Admin → User Management → [select user] → Edit → Country Assignments (multi-select)

**If a focal point reports they cannot see a form:**
1. Check their country assignments match the form's assigned countries.
2. Check their role — Focal Points cannot see admin-only areas.
3. Check the form assignment status (not all forms are open to all focal points simultaneously).

---

## 6. Self-service access requests

Pending requests from users who asked for an account through the self-service flow appear in:

**Route:** Admin → Access Requests

| Action | What it does |
|--------|-------------|
| **Approve** | Creates or activates a Backoffice user linked to the requester; sends confirmation |
| **Reject** | Declines with optional message to the requester |
| **Approve All** | Bulk-approve pending requests (use with caution — review individually first) |

**Approval checklist:**
- Verify the requester's name matches a known IFRC contact.
- Confirm intended role (often Focal Point or View Only for field accounts).
- Assign correct countries before approving.

---

## 7. Password Management

**User resets their own password (preferred):**
Admin → User Management → [select user] → Send Password Reset (if email is configured)

**Admin sets a temporary password:**
Admin → User Management → [select user] → Edit → Set New Password

**Token-based login:** After a password change, existing Bearer tokens may still be valid until they expire or the client obtains new credentials — users should complete logout/login where their client supports it (same backend credentials as the browser login).

---

## 8. RBAC Quick Reference

Permission codes used in the system follow the pattern `admin.<area>.<action>`. Examples:

| Permission | Grants access to |
|-----------|----------------|
| `admin.users.*` | User management screens |
| `admin.assignments.*` | Form assignment management |
| `admin.templates.*` | Form template builder |
| `admin.indicator_bank.*` | Indicator Bank CRUD |
| `admin.analytics.view` | Analytics dashboard |
| `admin.audit.view` | Audit trail |
| `admin.notifications.manage` | Outbound notifications from Admin |
| `admin.organization.manage` | Org structure (branches/sub-branches) |

System Manager has all permissions. Other roles inherit a curated set. Do not hand-assign individual permissions without updating the RBAC seed in `python -m flask rbac seed`.

**See also:** [RBAC audit exemptions](../security/rbac-admin-route-audit-exemptions.md) for routes deliberately exempt from permission checks.

---

## 9. Viewing Active Sessions

```bash
cd Backoffice
python -m flask show-all-sessions
```

To kill all sessions for a specific user: deactivate the user account (see §4) or rotate `SECRET_KEY` (site-wide impact — coordinate first).

---

## 10. Troubleshooting Common Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| User can log in but sees no data | No country assignments | Add at least one country |
| User says "access denied" on a page | Role lacks permission | Upgrade role or add specific country |
| Client reports `401` after password change | Old Bearer JWT still valid | Tokens expire naturally; have user obtain fresh credentials / full logout |
| Duplicate accounts created | User submitted twice via access requests | Merge manually: deactivate duplicate, reassign country in the primary account |
