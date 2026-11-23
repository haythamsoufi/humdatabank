# FDRS (`fdrs`)

Federation-wide Databank & Reporting System. It is backend-only (no form field types) and covers:

- synchronising FDRS data from the data API and fetching its documents;
- Data Explorer tabs: Disaggregation Analysis, Service income, Everyone Counts report, Compliance;
- matrix validation (a validation pack) and the data-quality methodology;
- the public FDRS-compatible data API, and the public mobile data handlers (`get_mobile_handlers()`, served under `/api/mobile/v1/data/`).

## Permissions

| Permission | Role |
|---|---|
| `admin.data_explore.disaggregation` | `admin_data_explorer_disaggregation` |
| `admin.data_explore.service_income` | `admin_data_explorer_service_income` |
| `admin.data_explore.everyone_counts` | `admin_data_explorer_everyone_counts` |
| `admin.data_explore.compliance` | Compliance tab |

The three split tabs are seeded through `get_seed_permissions()` / `get_seed_roles()`. The mobile and public API endpoints are public by design and rate limited.

## Settings

Admin → Plugins → FDRS → Settings (`/admin/plugins/fdrs/settings`) shows the sync script status and the default reporting years. Syncs, document scans and publication jobs run from the Data Explorer and admin panels. Command line tools are in `cli.py`.

Admin → FDRS Tools → Endpoints (`/admin/fdrs-tools#endpoints`) chooses, for each legacy public path, whether this server answers from Databank or forwards the request to the legacy data API (`FDRS_DATA_API_BASE`, using `FDRS_DATA_API_KEY`). Forwarding is the contingency when a path should be served by the original system again. The public site keeps calling this server either way. Translations, offices, and the document mailing list always forward, because they have no Databank source.

## Configuration

| Key | Purpose |
|---|---|
| `FDRS_DATA_API_KEY` | Key for the legacy data API used for sync and for the public passthrough routes |
| `FDRS_DATA_API_BASE` | Base URL of that API (defaults to the legacy host; must not point at this app) |
| `IFRC_EXCHANGE_RATE_API_KEY` | Exchange rates for currency conversion |

A nightly job (`fdrs_public_export_snapshot`, 04:15 UTC) rebuilds the public CSV and Excel export. UPR is an optional dependency (`get_optional_plugins()`).

## How to test

From `Backoffice/`:

```powershell
python scripts/ci/check_plugin_contract.py --plugin fdrs
python -m pytest plugins/fdrs/tests --no-cov
```

Then activate the plugin, open the settings page as an admin, and open Data Explorer → Disaggregation Analysis.
