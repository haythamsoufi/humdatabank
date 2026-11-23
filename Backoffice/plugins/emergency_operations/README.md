# Emergency Operations (`emergency_operations`)

Adds the **Emergency Operations (GO)** form field. It lists the IFRC operations that are currently active for the entry's country, using the GO appeals feed (`appealgroupchild`). The field only displays operations; it stores no value (`normalize_value` returns `None`). Up to three operations can be bound to form sections (`EO1`–`EO3`) so a section can show an operation's name and code.

## Permissions

The plugin seeds no permissions or roles. Its admin routes use `plugin_admin_route_wrapper`, so they need the plugin management permission (`admin.plugins.manage`) or System Manager.

## Settings

Admin → Plugins → Emergency Operations → Settings (`/admin/plugins/emergency_operations/settings`). From there an admin can:

- change the operation types shown (`All`, `Emergency Appeal`, `DREF`) and the item limit (1–100);
- choose how the appeals cache refreshes (`data_cache.schedule`, `use_file_cache`);
- clear the plugin cache and see usage statistics.

Saving a config section clears the plugin cache, because list responses are cached for 5 minutes (`CACHE_TTL_SECONDS`).

## Configuration

Defaults are in `plugin_config.json`. They are imported once into the plugin's `plugin_data` row, and existing database rows are never overwritten. The appeals cache is a file written by `data_store.py`; closing dates can be overridden per operation (`end_date_overrides.py`).

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin emergency_operations
python -m pytest plugins/emergency_operations/tests tests/unit/test_plugins/test_emergency_operations_data_store.py tests/unit/test_plugins/test_emergency_operations_end_date_overrides.py tests/unit/test_plugins/test_emergency_operations_query_b64.py tests/unit/test_plugins/test_emergency_section_binding.py --no-cov
```

Then activate the plugin, open the settings page as an admin, and add the field to a form template in the form builder.
