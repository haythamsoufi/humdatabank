# Sample Plugin Package

This is a minimal starter plugin for the Humanitarian Databank.

## Contents

- **plugin.py** – Minimal `BasePlugin` subclass (no custom field types).
- **plugin.json** – Metadata used when uploading the plugin (name must match the package folder name).

## How to use

1. Extract this package into your Backoffice plugins directory as a folder named `sample-package`:
   - Resulting path: `Backoffice/plugins/sample-package/`
2. In the Backoffice admin, go to **Plugins** and use **Upload** to install from a ZIP, or ensure the folder is present and use **Install** / **Activate** for the "Sample Plugin".
3. Use this package as a template: add custom field types, blueprints, or settings by following the existing plugins under `Backoffice/plugins/` (e.g. `emergency_operations`, `interactive_map`).

## Plugin contract

- Folder name under `plugins/` must match the plugin identifier (e.g. `sample-package`).
- `plugin.json` must contain a `name` field matching that identifier (required for upload validation).
- `plugin.py` must define a class that subclasses `app.plugins.base.BasePlugin` and implements `plugin_id`, `display_name`, and `version`.
