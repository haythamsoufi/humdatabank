# Local Windows: slow Backoffice navigation

Azure App Service stays responsive. The same build on a managed Windows laptop can sit for many seconds — sometimes more than a minute — before a page paints. This is a workstation issue, not a database or memory issue.

## What we measured (2026-10-19)

`python run.py` on a corporate Windows laptop, local PostgreSQL (`127.0.0.1:5432/hum_databank`):

| Check | Result |
|---|---|
| `GET /` (`main.dashboard`) | Reached Flask immediately (`>> GET /`), then **97s** until HTTP 200. `[STUCK_REQUEST]` at 16s and 24s with `db_pool_out` 1–2 of 20. |
| Same queries run outside the app | `SELECT 1` ~10ms. `entity_activity_log` (1,607 rows) count and country group-by ~10ms. `form_data` count (99,881 rows) 0.2s. No blocked sessions. |
| Machine | 63 GB RAM, ~32 GB free. Not memory pressure. |
| `Get-MpComputerStatus` | **~60s** to return two booleans. Real-time protection on. Exclusion list not readable without administrator rights. |

The wait is inside the dev process while Windows endpoint protection scans file opens (imports, template compiles, static reads). App Service containers do not run that scanner on the request path, so production stays fast. A page is often slow the first time each module or template is touched after a restart, then faster until the next restart.

## How to see it

In debug (`python run.py`, `LOG_MODE=normal`), the terminal prints:

- `>> GET /path` when the request reaches Flask
- the Werkzeug access line when the response finishes

Static files are omitted. A gap **before** `>>` is the browser. A gap **between** `>>` and the access line is the server process (this runbook). `[STUCK_REQUEST]` / `[SLOW_REQUEST]` use the same window. Production does not print Werkzeug lines; Gunicorn writes the access log.

## What helps without an IT exclusion

These stay in the dev server so a navigation opens fewer files and runs fewer queries. They do not remove the scanner.

- Versioned static URLs (`?v=`) are cached in the browser in debug, the same as production. The token includes a content hash that updates when the file’s mtime or size changes, so a CSS/JS edit still shows on the next HTML load. Unversioned `/static/...` stays `no-store`.
- Debug does not register a service worker, and unregisters one left over from a non-debug run. A leftover worker forces a network reload of every script and stylesheet.
- Static requests do not load the user row.
- System settings are read once per request.

`FLASK_USE_RELOADER=false` avoids a second process and mid-request restarts. It does not stop real-time scanning.

## If IT will add exclusions

The durable fix is a performance exclusion for local dev, not an app change. On a managed laptop this needs an administrator. Ask for:

- the clone, e.g. `C:\Humanitarian Databank`
- the Python install and its `site-packages`
- `python.exe` / `py.exe` as a trusted process

Do not treat a refused exclusion as an application defect. Confirm with the timings above before changing dashboard queries.
