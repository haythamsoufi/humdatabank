# UPR (`upr`)

Unified Plan and Report. It is an admin-feature plugin (no form field types) with:

- live dashboards and visuals for planning and reporting assignments, with export;
- Excel import and export of UPR data (`excel/`, `scripts/`), including the import wizard under `/admin/upr-excel-import`;
- GO-API documents, the public documents gallery (`documents/`) and the public mobile handlers for unified planning;
- AI/RAG document intelligence and validation (`ai/`), registered as a validation pack and used by the AI assistant.

## Permissions

| Permission | Role |
|---|---|
| `admin.data_explore.upr_visuals` | `admin_data_explorer_upr_visuals` |
| `admin.data_explore.upr_impact` | `admin_data_explorer_upr_impact` |

They are created through `get_seed_permissions()` / `get_seed_roles()`. A few routes are public on purpose (documents gallery, key-data lookup, support-flow tiles); each one is listed with a reason in `tests/unit/test_plugins/test_plugin_route_access.py`.

## Settings

Admin → Plugins → UPR → Settings (`/admin/plugins/upr/settings`) holds the Excel import panel, the global plan panel and the guidance tools. Web assets under `/upr/static/` are public so framed embeds work without a session; Excel templates stay authenticated. The PDF viewer, support-flow and documents gallery pages carry their own CSP overrides (`get_csp_overrides()`); the gallery allows scripts from its own origin only.

## Configuration

No plugin-level settings. The plugin adds pages to Admin → Embed Content (`get_embed_visuals()`). AI features use the platform AI configuration.

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin upr
python -m pytest plugins/upr/tests --no-cov
```

Then activate the plugin, open the settings page as an admin, and open Data Explorer → UPR.
