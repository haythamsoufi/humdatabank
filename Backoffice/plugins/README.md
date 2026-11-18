# Plugin System Documentation

## Overview

The Humanitarian Databank supports a plugin system that allows developers to extend the application with custom field types, functionality, and integrations.

> **Security notice:** Plugins execute in the host process with full application privileges (database, file system, network, secrets). There is no OS-level sandbox. Only install plugins from trusted sources.

## Plugin contract (enforced)

Plugins are written by different people, teams and AI agents. Everything below is checked automatically; a pull request or push to `main`/`develop` that breaks it fails CI and cannot merge.

**Start from the starter** (`Backoffice/app/sample_plugin_package/`, also `GET /admin/api/plugins/starter/download`). It already satisfies the contract. Do not start from an empty folder.

| # | Rule | Check id | Reference |
|---|---|---|---|
| 1 | Folder name = `plugin_id` = `plugin.json` `plugin_id` (`^[a-z][a-z0-9_]{0,63}$`). | `naming` | |
| 2 | `plugin.json` has `plugin_id`, `name`, `display_name`, `version` (semver), `description`, `author`, `license`; `plugin_id` and `version` equal `plugin.py`. Bump both together. | `manifest` | `global_awards/plugin.json` |
| 3 | **Settings page.** `GET /admin/plugins/<plugin_id>/settings` exists, even when the plugin has nothing to configure (show status, version, the info card). Plugin Management only shows the settings button when this URL resolves. | `settings-route` | `global_awards/routes.py` |
| 4 | The settings route is guarded: `plugin_admin_route_wrapper(...)` or `@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, <your permission>)`. Never expose it with `login_required` alone. | `settings-guard` | |
| 5 | `templates/settings.html` extends `core/layout.html`, uses the `page_header` macro with Admin > Plugins breadcrumbs, and includes `plugins/_plugin_info_card.html` (pass `plugin_info=settings_plugin_info(PLUGIN_ID)`). Render it as `plugins/<plugin_id>/settings.html`. | `settings-template` | |
| 6 | `get_blueprint()` returns the blueprint that holds those routes. `get_settings()` returns a plain dict (it feeds the Plugin Management API). Secrets go through `secret_paths` (see below). | runtime test | |
| 7 | Every other route has an auth decorator (`plugin_route_wrapper`, `plugin_admin_route_wrapper`, `login_required`, `permission_required`, ...). Public routes need an entry in `INTENTIONALLY_UNGUARDED` with a reason. | `test_plugin_route_access.py` | |
| 8 | New permissions and roles come from `get_seed_permissions()` / `get_seed_roles()`. Do not edit core RBAC files. | `test_rbac_catalog_completeness.py` | |
| 9 | `README.md` (200+ characters): what the plugin does, permissions, settings, config, how to test. | `readme` | `nsd_report_forms/README.md` |
| 10 | Tests in `plugins/<id>/tests/test_*.py` (or `tests/unit/test_plugins/test_<id>*.py`): at least the plugin class loads, the settings page renders for an admin, and it is denied to anonymous users. | `tests` | `global_awards/tests/` |
| 11 | The id is listed in `BUNDLED_PLUGIN_IDS` in `plugins/metadata.py` (any plugin folder committed to the repo ships with the image). Add it to `FIRST_PARTY_PLUGIN_IDS` only when it is first-party. | `bundled` | `test_first_party_plugins.py` |
| 12 | Core code never imports `plugins.*`. Add an extension point on `BasePlugin` instead. | `test_core_plugin_boundary.py` | |

Also required by repository-wide CI, not by this contract: no inline `<script>` / `onclick` in templates, no `|safe` on request or DB values, `SafeDom` for DOM writes, Tailwind rebuilt (`npm run build:css`) after adding utility classes, Alembic migrations for schema changes (plugin models under `plugins/` still need a migration in `Backoffice/migrations/`).

### Run the checks locally

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py                       # static rules, a few seconds, no database
python scripts/ci/check_plugin_contract.py --plugin my_plugin    # one plugin
python -m pytest tests/unit/test_plugins/test_plugin_contract.py tests/unit/test_plugins/test_plugin_route_access.py tests/unit/test_plugins/test_first_party_plugins.py --no-cov
```

### What runs in GitHub

| Workflow | Trigger | Gate |
|---|---|---|
| `Plugin contract` (`.github/workflows/plugin-contract.yml`) | every PR to `main`/`develop`, every push to `main`/`develop` | Static contract above; the exemption list may only shrink. Required status check on `main`. |
| `Backoffice CI` (`.github/workflows/backoffice-ci.yml`) | PR / push touching `Backoffice/**` | Code guards, Bandit, then pytest on the changed files. Plugin changes always include `test_plugin_contract.py`, `test_plugin_route_access.py` and `test_first_party_plugins.py`. |
| `CodeQL` | PR / push | Required status check on `main`. |

### Exemptions

`EXEMPT` in `scripts/ci/check_plugin_contract.py` lists the older bundled plugins that predate a rule (each with a reason). It can only shrink: a stale entry fails CI, and the `Plugin contract` workflow rejects any added entry. New plugins comply; they do not get exemptions.

### Instructions for AI agents

`.cursor/rules/plugin-development.mdc` attaches these rules whenever a file under `Backoffice/plugins/` or `Backoffice/app/plugins/` is touched. An agent creating or changing a plugin must: copy the starter, add the settings page first, run the commands above, and open the settings URL in the browser (log in with the dev "Act as Admin" preset) before reporting the work as done. Activate the plugin in Admin > Plugins and restart the dev server: blueprints register at application start, so a new plugin's routes return 404 until restart.

## Plugin Directory Structure

All plugins must be placed in the `Backoffice/plugins/` directory and follow this structure:

```
Backoffice/plugins/
├── plugin_name/
│   ├── plugin.py              # Main plugin class and field type definitions
│   ├── routes.py              # Plugin-specific routes and API endpoints
│   ├── static/                # Static assets (JS, CSS, images)
│   │   ├── js/               # JavaScript files
│   │   ├── css/              # CSS files
│   │   └── images/           # Image files
│   └── templates/             # HTML templates
│       ├── builder.html       # Form builder configuration template
│       └── field.html         # Entry form field rendering template
```

## Required Files

### 1. `plugin.py`
- Must contain a class that inherits from `BasePlugin`
- Must define custom field types that inherit from `BaseFieldType`
- Must implement all required methods and properties

### 2. `routes.py` (required: holds the settings page, see the contract above)
- The manager only calls `BasePlugin.get_blueprint()` (and `get_additional_blueprints()`). `routes.py` is a convention: bundled plugins expose `create_blueprint()` there and return it from `get_blueprint()`.
- Every route needs an auth decorator (`plugin_route_wrapper`, `plugin_admin_route_wrapper`, `login_required`, `permission_required`, ...). `tests/unit/test_plugins/test_plugin_route_access.py` fails for routes without one unless they are listed there on purpose.

### 3. Static Assets
- **JavaScript files**: Must be in `static/js/` directory
- **CSS files**: Must be in `static/css/` directory
- **Images**: Must be in `static/images/` directory

### 4. Templates
- **`builder.html`**: Configuration interface for form builders
- **`field.html`**: Field rendering for entry forms

## Plugin Configuration

### Form Builder Configuration
```python
def get_form_builder_config(self) -> Dict[str, Any]:
    return {
        'title': 'Field Configuration Title',
        'icon': 'fas fa-icon-name',
        'custom_template': 'plugin_name/builder.html',  # Optional: custom template
        'fields': [
            # Configuration field definitions
        ],
        'validation_rules': True,
        'condition_types': True
    }
```

### Entry Form Configuration
```python
def get_entry_form_config(self) -> Dict[str, Any]:
    return {
        'template': 'plugins/plugin_name/field.html',
        'es_module_path': '/plugins/static/plugin_name/js/field.js',
        'es_module_class': 'JavaScriptClassName',
        'css_files': ['plugin_name/static/css/style.css'],
        'data_attributes': ['data-attr1', 'data-attr2']
    }
```

## File Paths

### Static File URLs
- **JavaScript**: `/plugins/static/plugin_name/js/filename.js`
- **CSS**: `/plugins/static/plugin_name/css/filename.css`
- **Images**: `/plugins/static/plugin_name/images/filename.png`

### Template Paths
- **Builder template**: `plugin_name/builder.html`
- **Field template**: `plugins/plugin_name/field.html`

## Example Plugin

See `interactive_map/` for a complete example plugin implementation.

## Admin feature plugins (org-specific tools)

For **org-specific admin tools** (Data Explorer tabs, custom report pipelines, etc.) that should be removable without editing core app code, use a **plugin** with optional admin hooks on `BasePlugin` — same `plugin.py` entry point as form-field plugins.

- Contract: `Backoffice/app/plugins/base.py` (`BasePlugin`). Hooks consumed by core: `get_field_types()`, `get_blueprint()` / `get_additional_blueprints()`, `get_data_explorer_tabs()`, `get_seed_permissions()`, `get_seed_roles()`, `get_csp_overrides()`, `get_panel_render_context()`, `get_api_endpoints()` (Admin → API Management), `get_embed_visuals()`, `get_assignment_badges()`, `get_national_society_columns()`, `get_entry_form_assets()`, `get_documentation_source()`, `register_validation_packs()`, `get_required_plugins()` / `get_optional_plugins()`, and the ones added for decoupling: `get_nav_items()` (sidebar links, shown only while active), `get_scheduled_jobs()` (APScheduler jobs, skipped while inactive), `get_ai_tools()` (`AiToolSet` for the AI assistant), `get_list_option_count()` (size of a plugin-owned lookup list, for completion rates) and `materialize_document()` (fetch a missing document file). CLI commands live in `plugins/<id>/cli.py` as `register_cli(app)`; they are discovered from the file system (`app/plugins/cli_discovery.py`) so they exist even when plugins are not loaded. `get_admin_menu_items()`, `get_models()` and `get_migrations()` are informational and not consumed.
- Field types may override `normalize_value()` (what is stored; return `None` for display-only fields) and `validate_value()` (return an error message to reject a submission).
- Core must not import from `plugins.*`: `tests/unit/test_plugins/test_core_plugin_boundary.py` holds a ratchet baseline that can only shrink. Add an extension point instead of a new import.
- Discovery: `Backoffice/app/plugins/manager.py` scans `plugins/*/plugin.py`
- Example: `ifrc/` (PPP embeds + P&B Visuals under `ifrc/pb_progress/`)
- FDRS: `fdrs/` (backend-only data-api sync, documents, matrix validation, quality methodology)
- UPR: `upr/` (dashboards, Excel, GO-API documents, AI/RAG document intelligence)

Required file: `plugin.py` with a concrete `BasePlugin` subclass. Set `get_field_types()` to `[]` for admin-only tools. Optional: `routes.py`, `service.py`, `templates/`, `static/`, and tool subfolders.

First-party plugins share author metadata from `plugins/metadata.py` (`Haytham Alsoufi`, `https://github.com/haythamsoufi`). Settings pages should render that via `settings_plugin_info()` rather than hardcoding.

Admin-feature plugins (`is_admin_feature()`) register via the admin-feature blueprint path but are still activation-gated (404 while inactive). Templates are referenced as `plugins/<plugin_id>/...`.

## Lifecycle

| State | Meaning |
|---|---|
| Discovered | Folder under `plugins/` with a loadable `plugin.py`. |
| Installed | `install_plugin` ran; tracked in memory / installation history. |
| Active | Listed in `plugin_data` (`plugin_id=__plugin_lifecycle__`, `active_plugin_ids`); field types, templates and routes are served. |

- Plugins are **inactive by default**. Only IDs in the lifecycle `plugin_data` row are active.
- Every plugin blueprint is registered at application start, whatever its state. A guard returns 404 for plugins that are not active, so activating or deactivating takes effect without a restart.
- A plugin installed after start (upload or **Scan for plugins**) is loaded at once, but its blueprint and any changed view code only appear after a restart. **Reload** re-imports `plugin.py` and keeps the old version if the new one fails to load.
- State is shared between workers through the lifecycle `plugin_data` row; each request compares `updated_at` and reloads when it changed.
- On first boot, if that row is missing and `instance/plugin_states.json` exists, its `active_plugin_ids` are imported once. Each `plugins/*/plugin_config.json` is imported into that plugin’s `plugin_data` row when no row exists yet (existing DB rows are never overwritten).
- Declare plugins that must be active first with `get_required_plugins()`. Activation is refused while a requirement is missing or inactive, and a plugin that others require cannot be deactivated or uninstalled.
- Bundled plugins (`plugins/metadata.py::BUNDLED_PLUGIN_IDS`: their code ships in the repository and core imports it) cannot be uninstalled, because that would delete tracked code. They can be deactivated unless another active plugin requires them. `FIRST_PARTY_PLUGIN_IDS` only drives author metadata.
- `get_optional_plugins()` declares soft dependencies: the plugin works without them, and the management page warns while they are inactive. Required-dependency cycles are logged at load.
- Activation state is re-read from the database at most every `PLUGIN_ACTIVATION_SYNC_TTL_SECONDS` seconds per worker (default 2; `0` checks on every request). Static assets of inactive plugins answer 404 unless `PLUGIN_STATIC_REQUIRE_ACTIVE=false`.
- Optional settings: `PLUGIN_FIELD_CONFIG_ENFORCE=true` rejects invalid plugin field config on save (default: log only); `PLUGIN_SECRETS_KEY` encrypts secret-looking plugin settings (`api_key`, `token`, `password`, ...) at rest as `enc:v1:...` (default: off; plaintext keeps reading, losing the key makes encrypted values unreadable); `PLUGIN_LOGGER_OWN_HANDLER_ONLY=true` stops plugin loggers propagating to root handlers.
- Uploaded plugins are written to the local `plugins/` folder of one instance only; with several instances they must be deployed with the image instead.
- Install, uninstall, activate, deactivate and upload are recorded in the admin audit trail (`plugin_<action>`).
- `update_settings()` returns `False` by default. Override it together with `supports_settings_update()` to expose a settings form.

### Secrets in plugin settings

Pass `secret_paths` to `BasePluginRoutes` so API keys are replaced by a placeholder in responses and kept unchanged when the placeholder is posted back (`redact_secrets` / `restore_secrets` in `app/plugins/plugin_utils.py`). Keys whose name looks secret (`api_key`, `token`, `password`, ...) are masked even when not declared. Never log a request URL that carries a key; use `safe_request_error()`.

### Uploading plugins

`POST /admin/api/plugins/install` (field `plugin_package`) and `POST /admin/api/plugins/<id>/upload` (field `plugin_file`) accept a ZIP whose `plugin.json` declares `plugin_id`. The code is imported into the host process, so the endpoints require the System Manager role and `PLUGIN_UPLOAD_ENABLED=true`. The starter package is at `GET /admin/api/plugins/starter/download`.

## Best Practices

1. **Self-contained**: All plugin files should be within the plugin directory
2. **Naming**: Use descriptive, unique names for plugins
3. **Dependencies**: Minimize external dependencies
4. **Error handling**: Implement proper error handling and validation
5. **Documentation**: Include clear documentation for configuration options

## Security Considerations

1. **File validation**: Validate all uploaded files and user inputs
2. **Access control**: Implement proper permission checks
3. **Sanitization**: Sanitize all user-generated content
4. **Rate limiting**: Implement rate limiting for API endpoints

## Testing

1. Test plugin installation and uninstallation
2. Test field type configuration in form builder
3. Test field rendering in entry forms
4. Test data validation and submission
5. Test error handling and edge cases
