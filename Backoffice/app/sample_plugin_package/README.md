# Sample Plugin Package

Minimal starter plugin for the Humanitarian Databank.

## Contents

- **plugin.py** - Minimal `BasePlugin` subclass (no custom field types).
- **plugin.json** - Manifest read when the ZIP is uploaded. `plugin_id` must match `plugin_id` in `plugin.py`.
- **__init__.py** - Makes the folder an importable Python package.

## How to use

1. Install it, either:
   - Upload the ZIP on **Admin > Plugins** (requires `PLUGIN_UPLOAD_ENABLED=true` and the System Manager role; the archive is imported as Python code, so only upload plugins you trust), or
   - Extract it to `Backoffice/plugins/sample_plugin/` and restart the application, then use **Install**.
2. Activate the plugin from the plugin management page.
3. Use it as a template: add field types, blueprints or settings by following the plugins under `Backoffice/plugins/` (for example `emergency_operations`, `interactive_map`).

## Plugin contract

- The folder name under `plugins/` must equal the plugin id and be a valid Python identifier (lowercase letters, digits, underscores).
- `plugin.json` needs a `plugin_id` (or `name`) with that id.
- `plugin.py` must define a `BasePlugin` subclass implementing `plugin_id`, `display_name` and `version`.
- Blueprints returned by `get_blueprint()` are registered at application start, so a restart is needed after installing a plugin that provides routes.
- Use `get_required_plugins()` to declare other plugins that must be active first.
