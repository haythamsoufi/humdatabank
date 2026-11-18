# Sample Plugin Package

Minimal starter plugin for the Humanitarian Databank.

## Contents

- **plugin.py** - Minimal `BasePlugin` subclass (no custom field types).
- **routes.py** - Blueprint with the mandatory settings page, `GET /admin/plugins/sample_plugin/settings`, guarded by `plugin_admin_route_wrapper`.
- **templates/settings.html** - Settings page (core layout, page header, plugin info card).
- **plugin.json** - Manifest read when the ZIP is uploaded. `plugin_id` must match `plugin_id` in `plugin.py`.
- **__init__.py** - Makes the folder an importable Python package.

## How to use

1. Install it, either:
   - Upload the ZIP on **Admin > Plugins** (requires `PLUGIN_UPLOAD_ENABLED=true` and the System Manager role; the archive is imported as Python code, so only upload plugins you trust), or
   - Extract it to `Backoffice/plugins/sample_plugin/` and restart the application, then use **Install**.
2. Activate the plugin from the plugin management page.
3. Use it as a template: add field types, blueprints or settings by following the plugins under `Backoffice/plugins/` (for example `emergency_operations`, `interactive_map`).

## Plugin contract

This package is checked by CI. Keep the settings page when you copy it: every plugin must serve `/admin/plugins/<plugin_id>/settings`. Also add a `tests/` folder and register the id in `plugins/metadata.py::BUNDLED_PLUGIN_IDS`. The full enforced list is in `Backoffice/plugins/README.md` ("Plugin contract (enforced)"); run `python scripts/ci/check_plugin_contract.py` from `Backoffice/`.

- The folder name under `plugins/` must equal the plugin id and be a valid Python identifier (lowercase letters, digits, underscores).
- `plugin.json` needs a `plugin_id` (or `name`) with that id.
- `plugin.py` must define a `BasePlugin` subclass implementing `plugin_id`, `display_name` and `version`.
- Blueprints returned by `get_blueprint()` are registered at application start, so a restart is needed after installing a plugin that provides routes.
- Use `get_required_plugins()` to declare other plugins that must be active first.
