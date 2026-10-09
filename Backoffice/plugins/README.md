# Plugin System Documentation

## Overview

The Humanitarian Databank supports a plugin system that allows developers to extend the application with custom field types, functionality, and integrations.

> **Security notice:** Plugins execute in the host process with full application privileges (database, file system, network, secrets). There is no OS-level sandbox. Only install plugins from trusted sources.

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

### 2. `routes.py`
- Must define a `create_blueprint()` function that returns a Flask Blueprint
- Can contain plugin-specific API endpoints and routes

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
        'js_module': 'JavaScriptModuleName',
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

- Contract: `Backoffice/app/plugins/base.py` (`BasePlugin`, optional `get_data_explorer_tab()`, `get_seed_permissions()`, `get_seed_roles()`, `get_csp_overrides()`, `get_panel_render_context()`, `get_api_endpoints()` for Admin → API Management)
- Discovery: `Backoffice/app/plugins/manager.py` scans `plugins/*/plugin.py`
- Example: `pb_progress/` (P&B Visuals + Quarto/Playwright pipeline in `visuals/`)
- FDRS: `fdrs/` (backend-only data-api sync, documents, matrix validation, quality methodology)
- UPR: `upr/` (dashboards, Excel, GO-API documents, AI/RAG document intelligence)

Required file: `plugin.py` with a concrete `BasePlugin` subclass. Set `get_field_types()` to `[]` for admin-only tools. Optional: `routes.py`, `service.py`, `templates/`, `static/`, and tool subfolders.

First-party plugins share author metadata from `plugins/metadata.py` (`Haytham Alsoufi`, `https://github.com/haythamsoufi`). Settings pages should render that via `settings_plugin_info()` rather than hardcoding.

Admin-feature plugins (`is_admin_feature()`) are always on: they cannot be deactivated. Templates are referenced as `plugins/<plugin_id>/...`.

## Lifecycle

| State | Meaning |
|---|---|
| Discovered | Folder under `plugins/` with a loadable `plugin.py`. |
| Installed | `install_plugin` ran; recorded in `plugin_states.json`. |
| Active | Field types, templates and routes are served. |

- Every plugin blueprint is registered at application start, whatever its state. A guard returns 404 for plugins that are not active, so activating or deactivating takes effect without a restart.
- A plugin installed after start (upload or **Scan for plugins**) is loaded at once, but its blueprint and any changed view code only appear after a restart. **Reload** re-imports `plugin.py` and keeps the old version if the new one fails to load.
- State is shared between workers through `plugin_states.json`; each request checks its modification time and re-reads it when it changed.
- Declare plugins that must be active first with `get_required_plugins()`. Activation is refused while a requirement is missing or inactive, and a plugin that others require cannot be deactivated or uninstalled.
- First-party plugins (`plugins/metadata.py::FIRST_PARTY_PLUGIN_IDS`) cannot be uninstalled from the UI because that would delete tracked code.
- `update_settings()` returns `False` by default. Override it together with `supports_settings_update()` to expose a settings form.

### Secrets in plugin settings

Pass `secret_paths` to `BasePluginRoutes` so API keys are replaced by a placeholder in responses and kept unchanged when the placeholder is posted back (`redact_secrets` / `restore_secrets` in `app/plugins/plugin_utils.py`).

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
