# Admin Action Risk Levels

This document describes the risk level classification system used for administrative actions in the NGO Databank. All admin actions are logged in the audit trail with an assigned risk level that determines how they are monitored and reviewed.

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

**Examples of High-Risk Actions:**
- **User Deletion** (`user_delete`) - Permanent removal of user accounts and all associated data
- **RBAC Role Deletion** (`rbac_role_delete`) - Removal of role-based access control roles that may affect permissions
- **System Manager Role Changes** (`user_update`) - Granting or revoking system manager privileges

### Medium
**Actions that have moderate impact on data integrity, user experience, or system configuration.**

Medium-risk actions are logged for audit purposes but do not automatically trigger security events.

**Examples of Medium-Risk Actions:**
- **Template Deletion** (`template_delete`) - Removal of form templates and associated structure
- **Template Version Deployment** (`template_version_deploy`) - Publishing new template versions that affect active assignments
- **User Updates with Role Changes** (`user_update`) - Modifying user roles or permissions (excluding system manager)
- **Security Event Resolution** (`resolve_security_event`) - Marking security events as resolved
- **User Creation** (`user_create`) - Creating new user accounts with specific permissions
- **Assignment Management** - Creating, editing, or deleting assignments
- **RBAC Role Management** - Creating or modifying RBAC roles (excluding deletion)

### Low
**Routine administrative actions with minimal security or data impact.**

Low-risk actions are logged for audit trail purposes but are considered normal operational activities.

**Examples of Low-Risk Actions:**
- **Template Creation** (`template_create`) - Creating new form templates
- **Template Editing** (`template_edit`) - Modifying template structure (non-deployment changes)
- **Data Export** - Exporting data for analysis
- **Settings Updates** - Updating system configuration
- **Content Management** - Managing resources, publications, and other content
- **Viewing/Reading Operations** - Accessing data, logs, or reports (typically not logged as admin actions)

## Risk Level Assignment Guidelines

When implementing new admin actions or reviewing existing ones, use these guidelines:

1. **High Risk** should be used for:
   - Permanent data deletion (users, roles, critical system components)
   - Changes to system-level permissions (system manager, full admin)
   - Actions that could compromise system security or integrity

2. **Medium Risk** should be used for:
   - Actions that affect multiple users or assignments
   - Template and assignment lifecycle operations
   - Permission and role modifications (excluding system-level)
   - Actions that require careful review but are part of normal operations

3. **Low Risk** should be used for:
   - Routine data entry and updates
   - Viewing and reporting operations
   - Non-destructive configuration changes
   - Standard administrative tasks

## Implementation

Risk levels are assigned when logging admin actions using the `log_admin_action()` function:

```python
from app.utils.user_analytics import log_admin_action

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

## Action Type Reference

### Template Management
- `template_create`: Low
- `template_edit`: Low
- `template_delete`: **Medium** (changed from High)
- `template_version_deploy`: **Medium** (changed from High)
- `template_version_create`: Low

### User Management
- `user_create`: Medium
- `user_update`: Medium (High if system manager role changes)
- `user_delete`: High
- `user_activate`: Low
- `user_deactivate`: Medium

### RBAC Management
- `rbac_role_create`: Medium
- `rbac_role_update`: Medium
- `rbac_role_delete`: High
- `rbac_grant`: Medium
- `rbac_revoke`: Medium

### Assignment Management
- `assignment_create`: Medium
- `assignment_update`: Medium
- `assignment_delete`: Medium

### Security
- `resolve_security_event`: Medium
- `security_settings_update`: Medium

## Change History

- **2026-01-26**: Changed `template_delete` and `template_version_deploy` from High to Medium risk level, as these are routine administrative operations that don't pose significant security threats.
