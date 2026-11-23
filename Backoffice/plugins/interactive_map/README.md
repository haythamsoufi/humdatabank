# Interactive Map (`interactive_map`)

Adds the **Interactive Map** form field so a user can pick a location on a map while filling in a form. The plugin also serves map tiles through a same-origin proxy (so the page CSP does not need external tile hosts and API keys stay on the server) and geocodes addresses.

## Permissions

The plugin seeds no permissions or roles. Its admin routes use `plugin_admin_route_wrapper`, so they need the plugin management permission (`admin.plugins.manage`) or System Manager. Tile and geocoding endpoints use `plugin_route_wrapper`, so they answer only while the plugin is active; geocoding is rate limited (Nominatim requests per minute).

## Settings

Admin → Plugins → Interactive Map → Settings (`/admin/plugins/interactive_map/settings`):

- default map provider (OpenStreetMap, Mapbox, and the other providers listed in `config.py`);
- geocoding service (`nominatim` or `google`), plus optional language and region bias for Google;
- API keys for Mapbox and Google geocoding;
- clear the tile cache and see usage statistics.

API keys are secret: they are redacted in settings responses and kept when the placeholder is posted back (`SECRET_PATHS`). Errors from the geocoding services are logged through `safe_request_error`, never with the request URL.

## Configuration

Defaults are in `config.py` (`DEFAULT_PLUGIN_CONFIG`) and `plugin_config.json`, imported once into the plugin's `plugin_data` row. Installing the plugin sets `INTERACTIVE_MAP_DEFAULT_CENTER` and `INTERACTIVE_MAP_TILE_PROVIDER` in the app config when they are missing, and uninstalling removes them.

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin interactive_map
python -m pytest plugins/interactive_map/tests tests/unit/test_plugins/test_interactive_map_tile_proxy.py --no-cov
```

Then activate the plugin, open the settings page as an admin, and add the field to a form template. Entry forms should show the map and place a marker on click.
