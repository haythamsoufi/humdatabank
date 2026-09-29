# RBAC Admin Route Audit Exemptions

This runbook documents `/admin` routes that are intentionally exempt from the startup RBAC guard audit.

## Purpose

The app performs a startup audit that warns when an `/admin` route does not have an RBAC guard decorator (`@admin_required`, `@permission_required`, or related).

Some endpoints are intentionally public (or protected by non-standard controls). Those routes are marked with `@rbac_guard_audit_exempt("<reason>")` to:

- keep the audit signal clean;
- avoid masking real accidental exposures;
- force an explicit justification in code.

## Exempted Routes

| Route | Endpoint | File | Why exempt |
|---|---|---|---|
| `/admin/documents/serve/<int:doc_id>` | `content_management.serve_document_file` | `app/routes/admin/content_management.py` | Public rendering of approved public cover images; route also enforces `document_type == "Cover Image"` and `is_public`. |
| `/admin/sectors/<int:sector_id>/logo` | `system_admin.sector_logo` | `app/routes/admin/system_admin.py` | Public logo asset delivery for sector logos. |
| `/admin/organization/api/public/branches/<int:country_id>` | `organization.api_get_branches_by_country_public` | `app/routes/admin/organization.py` | Public dynamic selector data for branches. |
| `/admin/organization/api/public/subbranches/<int:branch_id>` | `organization.api_get_subbranches_by_branch_public` | `app/routes/admin/organization.py` | Public dynamic selector data for sub-branches. |
| `/admin/organization/api/public/subbranches/by-country/<int:country_id>` | `organization.api_get_subbranches_by_country_public` | `app/routes/admin/organization.py` | Public dynamic selector data for sub-branches by country. |
| `/plugins/static/<plugin_name>/<path:filename>` | `plugin_static.serve_plugin_static` | `app/routes/admin/plugin_management.py` | Outside `/admin` but audited. Requires login unless the plugin id is listed in `PLUGIN_PUBLIC_STATIC_PLUGINS`; only allow-listed asset extensions are served; non-public responses are `Cache-Control: private`. |

## Non-Exempt Route Fixes Applied

The following routes were previously detected as unguarded and were fixed by adding `@admin_required` (not exempted):

- `/admin/api/refresh_csrf_token`
- `/admin/api/refresh-csrf-token`

## Other audit findings (not exemptions)

The audit also reports policy findings that are fixed in code, not exempted: `non_admin_permission`, `read_permission_on_mutating_route`, `get_side_effect_name`, `csrf_exempt_mutation` and violations of the tables in `app/routes/admin/route_policy.py`. Deliberate exceptions live in that module's allowlists (`READ_ONLY_POST_ALLOWLIST`, `CSRF_EXEMPT_MUTATION_ALLOWLIST`, `LOGIN_ONLY_POST_ALLOWLIST`, `GET_SIDE_EFFECT_NAME_ALLOWLIST`), each with a justification; adding an entry needs the same review as a new exemption and an update to this document.

## Rules for Adding New Exemptions

Only add `@rbac_guard_audit_exempt` when all of the following are true:

1. The route must be publicly reachable (or uses a custom protection model the audit cannot infer).
2. The route performs strict validation and returns only low-risk data/assets.
3. A clear reason string is provided in the decorator.
4. This document is updated in the same change.

Preferred approach: if a route should be admin-only, add a standard RBAC guard instead of exempting it.

## Validation Checklist

After any exemption change:

1. Start app and confirm no unexpected RBAC startup warnings.
2. Verify exempt route behavior for both valid and invalid inputs.
3. Confirm no sensitive data is exposed anonymously.
4. Re-run a quick grep for exemptions:
   - `rg "rbac_guard_audit_exempt\\(" Backoffice/app/routes/admin`
