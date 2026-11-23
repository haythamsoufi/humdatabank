# IFRC (`ifrc`)

IFRC programme tools, all admin-feature (no form field types):

- **PPP** (`ppp/`): Pilot Programmatic Partnership embeds and sync.
- **Plan & Budget progress** (`pb_progress/`): Data Explorer tab, a manage page, and the Quarto/Playwright report pipeline under `pb_progress/visuals/`.
- **Decision Maker** (`decisions/`): evidence, flags and methodology for Federation-wide decisions.

## Permissions

| Permission | Role | Use |
|---|---|---|
| `admin.data_explore.pb_progress` | `admin_data_explorer_pb_progress` | Plan & Budget progress tab in Data Explorer |
| `decisions.view` | `decisions_viewer` | Read Decision Maker |
| `admin.decisions.manage` | `admin_decisions_manager` | Manage Decision Maker content |

They are created through `get_seed_permissions()` / `get_seed_roles()`.

## Settings

Admin → Plugins → IFRC → Settings shows the plugin status, version and info card. Embed pages and the P&B report are served with their own CSP overrides (`_IFRC_EMBED_CSP`, `_PB_REPORT_CSP`) so they can be framed by approved hosts.

## Configuration

The plugin adds embeds to Admin → Embed Content (`get_embed_visuals()`), sidebar links (`get_nav_items()`) and tools for the AI assistant (`get_ai_tools()`). The report pipeline needs Quarto and Playwright on the machine that builds reports; see `pb_progress/visuals/`.

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin ifrc
python -m pytest plugins/ifrc/tests --no-cov
```

Then activate the plugin, open the settings page as an admin, and open Data Explorer → Plan & Budget progress.
