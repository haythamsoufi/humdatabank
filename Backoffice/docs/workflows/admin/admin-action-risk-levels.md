# Admin Action Risk Levels

This document describes the risk level classification system used for administrative actions in the Humanitarian Databank. All admin actions are logged in the audit trail with an assigned risk level that determines how they are monitored and reviewed.

## Risk Level Categories

### Critical
**Reserved for the most severe security threats and system-level compromises.**

Currently, no actions are classified as critical. This level is reserved for future use or exceptional circumstances requiring immediate security response.

### High
**Actions that significantly impact security, system integrity, or user access.**

High-risk actions automatically:
- Create security events that appear in the Security Dashboard
- Require review (`requires_review = True`)
- Are highlighted in admin action logs

**Examples of high-risk actions:**
- **API key creation** (`api_key_create`) — minting a new programmatic credential
- **RBAC role deletion** (`rbac_role_delete`)
- **Certain destructive operations on the mobile admin content API** (`delete_template`, `delete_assignment`, `delete_indicator`)
- **System manager privilege changes** — logged as `user_update` from the web user-edit flow when that role is granted or revoked

### Medium
**Actions that have moderate impact on data integrity, user experience, or system configuration.**

Medium-risk actions are logged for audit purposes but do not automatically trigger security events.

**Examples of Medium-Risk Actions:**
- **Template deletion / version deployment** (`template_delete`, `template_version_deploy`)
- **User deletion** (`user_delete`) — audited at medium; does **not** create a security event
- **User updates with role or password changes** (`user_update`) — medium when below system-manager escalation (see catalog)
- **Security event resolution** (`resolve_security_event`)
- **User creation** (`user_create`)
- **RBAC role create/update** and similar (excluding role deletion)

### Low
**Routine administrative actions with minimal security or data impact.**

Low-risk actions are logged for audit trail purposes but are considered normal operational activities.

**Examples of Low-Risk Actions:**
- **Template duplicate / export / variables** (`template_duplicate`, `template_export`, `template_variables_update`)
- **Template version comments / draft version create** (`template_version_comment`, `template_version_create`)
- **Many form-builder section/item edits** that only mutate structure (`form_section_*`, `form_item_*` except deletes)
- **Access request approve/reject** (`access_request_*`)
- **API key revocation** (`api_key_revoke`)
- **Viewing/reading** — typically **not** logged as admin actions

## Risk Level Assignment Guidelines

When implementing new admin actions or reviewing existing ones, use these guidelines:

1. **High Risk** should be used for:
   - Irreversible or broadly destructive operations where mis-use has outsized impact (e.g. deleting RBAC roles; selected mobile-admin destructive APIs)
   - Changes to **system-level** permissions (notably system manager)
   - Actions that could severely compromise security or integrity if abused

2. **Medium Risk** should be used for:
   - Actions that affect multiple users or assignments
   - Template lifecycle operations (publish, discard, medium-impact edits)
   - Permission and role modifications **below** system-manager scope
   - Actions that require careful review but are part of normal operations

3. **Low Risk** should be used for:
   - Routine data entry and updates
   - Viewing and reporting operations
   - Non-destructive configuration changes
   - Standard administrative tasks

## Action type catalog

Logged `action_type` values and their **configured** severity in code (`log_admin_action(..., risk_level=...)`). Rows are ordered **high → medium → low**, then variable-risk types.

Severity triggers automatic security events only for **`high`** and **`critical`** (see [Automatic security event creation](#automatic-security-event-creation)).

| Severity | Action type | Where / notes |
|----------|-------------|----------------|
| High | `api_key_create` | API key management |
| High | `delete_assignment` | Mobile admin content API |
| High | `delete_indicator` | Mobile admin content API |
| High | `delete_template` | Mobile admin content API |
| High | `rbac_role_delete` | Admin RBAC UI |
| Medium | `cleanup_sessions` | Admin analytics (bulk session cleanup) |
| Medium | `delete_document` | Mobile admin content API |
| Medium | `delete_resource` | Mobile admin content API |
| Medium | `end_user_session` | Admin analytics / API (terminate another user’s session) |
| Medium | `form_item_delete` | Form builder |
| Medium | `form_section_delete` | Form builder |
| Medium | `kickout_device` | User admin (device session end) |
| Medium | `rbac_grant_create` | RBAC UI |
| Medium | `rbac_grant_delete` | RBAC UI |
| Medium | `rbac_role_create` | RBAC UI |
| Medium | `rbac_role_update` | RBAC UI |
| Medium | `remove_device` | User admin (device registry removal) |
| Medium | `resolve_security_event` | Admin analytics / security |
| Medium | `template_create` | Form builder |
| Medium | `template_delete` | Form builder |
| Medium | `template_import` | Form builder |
| Medium | `template_import_excel` | Form builder |
| Medium | `template_sharing_update` | Form builder |
| Medium | `template_update` | Form builder |
| Medium | `template_version_delete` | Form builder |
| Medium | `template_version_deploy` | Form builder |
| Medium | `template_version_discard` | Form builder |
| Medium | `update_indicator` | Mobile admin content API |
| Medium | `user_create` | User admin |
| Medium | `user_delete` | User admin (audit only at this level; does **not** open a security event) |
| Low | `access_request_approve` | Access requests (HTML + API, including bulk approve) |
| Low | `access_request_reject` | Access requests (API) |
| Low | `api_key_revoke` | API key management |
| Low | `form_item_create` | Form builder |
| Low | `form_item_duplicate` | Form builder |
| Low | `form_item_unarchive` | Form builder |
| Low | `form_item_update` | Form builder |
| Low | `form_section_configure` | Form builder |
| Low | `form_section_create` | Form builder |
| Low | `form_section_duplicate` | Form builder |
| Low | `form_section_unarchive` | Form builder |
| Low | `form_section_update` | Form builder |
| Low | `template_duplicate` | Form builder |
| Low | `template_export` | Form builder |
| Low | `template_variables_update` | Form builder |
| Low | `template_version_comment` | Form builder |
| Low | `template_version_create` | Form builder |
| Variable | `user_update` | **High** — web user edit only: system manager RBAC role granted or revoked. **Medium** — e.g. activate/deactivate or archive toggle (API/HTML), password change, other RBAC changes on web edit. **Low** — API/mobile user PATCH when neither `active` nor `rbac_role_ids` changes. |

**Critical:** No action types use `critical` yet.

When adding or changing a logged admin action, update this table in the same PR.

## Implementation

Risk levels are assigned when logging admin actions using the `log_admin_action()` function:

```python
from app.services.user_analytics_service import log_admin_action

log_admin_action(
    action_type='template_delete',
    description=f"Deleted template '{template_name}'",
    target_type='form_template',
    target_id=template_id,
    risk_level='medium'  # Risk level assignment
)
```

### Automatic Security Event Creation

When an action is logged with `risk_level='high'` or `risk_level='critical'`, the system automatically:
1. Creates a security event in the Security Events log
2. Sets `requires_review=True` on the admin action log entry
3. Makes the action visible in the Security Dashboard

## Monitoring and Review

### Security Dashboard
High and critical risk actions appear in the Security Dashboard under "Recent High Risk Admin Actions" for immediate visibility.

### Admin Actions Log
All admin actions are logged in the Admin Actions view (`/admin/analytics/admin-actions`) where they can be filtered by risk level.

### Audit Trail
All actions are included in the comprehensive audit trail for compliance and troubleshooting purposes.

## Best Practices

1. **Consistency**: Use consistent risk level assignments for similar action types across the system
2. **Documentation**: When adding new admin actions, document the risk level choice in code comments
3. **Review**: Periodically review risk level assignments to ensure they remain appropriate
4. **Updates**: If operational patterns change, update risk levels accordingly (e.g., if template deletion becomes more routine, consider changing from high to medium)

## Change History

- **2026-01-26**: Changed `template_delete` and `template_version_deploy` from High to Medium risk level, as these are routine administrative operations that don't pose significant security threats.
- **2026-05-13**: Added action type catalog (ordered from High downward); aligned examples with code (`user_delete` is Medium and does not create a security event). Raised `api_key_create` from Low to High (security event + `requires_review`).
