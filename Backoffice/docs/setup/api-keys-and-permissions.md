# API keys and permissions

How database API keys authorize requests to `/api/v1/*` (and the legacy indicator-bank compat routes), how to create keys with the right access, and how older keys were migrated.

**Where to manage keys:** Admin → API Management → **API Key Management** (`/admin/api-management/api-keys`). Requires `admin.api.manage` (or System Manager).

Code map: vocabulary and parser `app/services/security/api_key_permissions.py`; request pipeline and enforcement `app/services/security/api_authentication.py`; decorators `app/utils/auth.py`; live route catalog `app/services/security/api_key_route_catalog.py`; migration `migrations/versions/api_key_permissions_v2.py`.

## 1. The model in plain language

A key holds a list of **capabilities**. Each route that accepts a key declares the one capability it needs. A request is allowed only if the key holds that capability. Nothing is implied: no capabilities means no access, and anything the server cannot interpret grants nothing.

Some capabilities can be narrowed by a **data scope** (specific templates and/or countries). The scope is applied to lists and to single-record (detail) routes alike.

Capabilities (source of truth: `CAPABILITIES` in `api_key_permissions.py`; the admin form shows the live endpoint list for each):

| Capability | Sensitivity | Scopable | Unlocks |
|---|---|---|---|
| `data:read` | sensitive | yes | `GET /data`, `/templates/<id>/data`, `/countries/<id>/data`, UPR data feeds |
| `submissions:read` | sensitive | yes | `GET /submissions`, `/submissions/<id>`, `/assigned-forms` |
| `templates:read` | standard | yes | `GET /templates`, `/templates/<id>`, `/form-items`, `/form-items/<id>` |
| `documents:read` | sensitive | no | Non-public submitted documents; documents attached to a submission |
| `users:read` | **personal data** | no | `GET /users`, `/users/<id>`, `/quiz/leaderboard`, submitter contact details on submissions |
| `reference:read` | standard | no | Countries, national societies, periods, sectors, subsectors, lookup lists, indicator bank and compat routes |
| `content:read` | standard | no | Resources, embed content, common words, public approved documents, FDRS published-data feed |
| `indicators:suggest` | standard | no | `POST /indicator-suggestions` (write) |
| `indicators:manage` | **personal data** | no | Read and review indicator suggestions (includes submitter emails; write) |
| `mobile:client` | standard | no | Allows the key to be sent as `X-Mobile-Auth` (no data access on its own) |
| `mcp:use` | standard | no | Backoffice proxy to the Databank MCP server |

Presets in the admin form: **Public website / embed**, **BI / analytics (read-only data)**, **Website back end (server-side only)**, **Mobile app client**.

### Scope rules

- No `data_scope`: unrestricted for the capabilities the key holds.
- `data_scope` with template and/or country ids: the key sees only matching rows on **lists and detail routes**. Out-of-scope detail requests return `404` (not `403`), so ids are not confirmed.
- `data_scope` with both lists empty: no data at all (fail closed).
- A scoped key calling a scopable route that does not implement scoping is denied (`403`) rather than served unscoped.
- `/data` also has an anonymous public mode (rows with `privacy=public` when public filter parameters are used). A key that lacks `data:read` and sends those filters is treated as anonymous and gets exactly what an anonymous caller gets.

### Personal data

Names, email addresses and contact details are returned only to keys holding `users:read` (or `indicators:manage` for indicator suggestions). Submissions and assignments omit public-submitter contact fields otherwise.

### Sending the key

- Use `Authorization: Bearer <key>`.
- `?api_key=` in the URL is **refused** unless the key was created with "Allow `?api_key=` in the URL" (`allow_query_api_key`). That option is unavailable together with personal-data capabilities, because URLs end up in logs, browser history and referrers. Responses to query-string requests carry `Cache-Control: no-store` and a `Warning` header; `api_key` values are redacted from request logs.
- The deprecated environment key `MOBILE_APP_API_KEY` is header-only.

### Pagination ceilings

Key-authenticated requests always paginate. Maximum `per_page`: `API_KEY_MAX_PER_PAGE` (default 10000). `MAX_PER_PAGE` in `app/utils/api_helpers.py` is 10000 for all callers (was 100000). `/users`, `/indicator-suggestions` and `/resources` are capped at 500.

### Rate limits

- Per key: `rate_limit_per_minute` on the key (set at creation), enforced per worker process in memory.
- Endpoints decorated with `@api_rate_limit()` are additionally limited per key (or client IP when anonymous).
- Because state is in-process, the effective ceiling is roughly `limit × number of workers`. Moving this to Redis is a follow-up.

### Errors

- `401` – no or invalid/expired/revoked key.
- `403` – valid key that lacks the capability. The body includes `required_permission`. A hint field explains a refused `?api_key=`.
- `404` – detail record outside the key's data scope.
- `429` – rate limit.

### Session or key routes

Routes marked "api_key_or_session" in the catalog accept a logged-in Backoffice session as an alternative. A session user is authorized by their normal role/RBAC rules, not by API-key capabilities. The UPR feeds and FDRS published-data do not apply RBAC country scoping to sessions and refuse scoped keys.

## 2. Route classification

Every key-accepting route must declare a capability; `undeclared_key_routes(app)` must stay empty (tested). Routes without a declared capability are denied for keys (fail closed).

| Capability | Routes (methods) |
|---|---|
| `reference:read` | `/api/v1/countrymap`, `/nationalsocietymap`, `/periods`, `/sectors`, `/subsectors`, `/sectors-subsectors`, `/lookup-lists`, `/lookup-lists/<id>`; compat `/Indicator*`, `/Sector`, `/Subsector`, `/CommonWord`, `/Excel`, `/list-home` |
| `content:read` | `/api/v1/resources`, `/embed-content`, `/common-words`, `/submitted-documents`, `/fdrs/published-data` |
| `data:read` (scope-aware) | `/api/v1/data`, `/templates/<id>/data`, `/countries/<id>/data`; `/api/v1/upr*` (refuse scoped keys) |
| `submissions:read` (scope-aware) | `/api/v1/submissions`, `/submissions/<id>`, `/assigned-forms` |
| `templates:read` (scope-aware) | `/api/v1/templates`, `/templates/<id>`, `/form-items`, `/form-items/<id>` |
| `users:read` | `/api/v1/users`, `/users/<id>`, `/quiz/leaderboard` |
| `indicators:suggest` | `POST /api/v1/indicator-suggestions`, `POST /Indicator/Suggestion` |
| `indicators:manage` | `GET /api/v1/indicator-suggestions`, `/indicator-suggestions/<id>`, `PUT /indicator-suggestions/<id>/status` |
| `mobile:client` | `X-Mobile-Auth` CSRF marker (mobile session routes) |
| `mcp:use` | MCP proxy (`app/routes/mcp.py`) |

## 3. The environment mobile key

`MOBILE_APP_API_KEY` (env) is deprecated. It no longer means "full access". Its capabilities come from `MOBILE_APP_API_KEY_CAPABILITIES` (default `reference:read,content:read,mobile:client`), it is accepted in the `Authorization` header only, and it is rate limited (`MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE`). Prefer a database key with the **Mobile app client** preset. `X-Mobile-Auth` requires `mobile:client`.

## 4. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `MOBILE_APP_API_KEY_CAPABILITIES` | `reference:read,content:read,mobile:client` | Capabilities of the env mobile key |
| `API_KEY_ALLOW_LEGACY_FULL_ACCESS` | `true` | Kill switch: set to `false` to stop honoring keys marked `legacy.full_access` (they then hold nothing until edited) |
| `API_KEY_MAX_PER_PAGE` | `10000` | `per_page` ceiling for key requests |

## 5. How permissions worked before (and why it was misleading)

- The create/edit forms never wrote `api_keys.permissions`, so it was `NULL` for almost every key.
- `permissions` was a JSON object of the form `{"data": "read_all" | "read_scoped" | "none"}` (plus `"mcp": true` for the MCP proxy). Only `resolve_api_key_data_access` read it, and it failed **open**: `NULL`, malformed or unknown values meant `read_all`.
- `@require_api_key` only checked that the key was valid; it never consulted `permissions`. A `data: none` key could still call users, submissions, templates and the rest. `read_scoped` was honoured only on `GET /data`.
- Unscoped listings returned organisation-wide data, including public-submitter emails; `/users` and `/quiz/leaderboard` returned personal data; `GET /submissions/<id>` opened any submission.
- `?api_key=` was accepted although comments claimed Bearer only.
- The env `MOBILE_APP_API_KEY` was accepted as an elevated key with no scoping.
- `per_page` allowed up to 100000.
- Three separate credential-handling stacks existed and disagreed.
- The admin UI showed a "permissions" presentation that did not correspond to what the server enforced.

## 6. Migration and rollback

`api_key_permissions_v2` rewrites `permissions` for existing rows and is reversible.

| Old value | New document |
|---|---|
| `NULL` / `read_all` | `legacy.full_access = true`: every key-protected capability except `mcp:use`, and `allow_query_api_key = true` (so existing integrations keep working) |
| `read_scoped` | `data:read` + `reference:read` with the old scope |
| `none` | `reference:read` + `content:read` |
| unknown / malformed | no capabilities (fail closed) |
| `mcp: true` | adds `mcp:use` |

`legacy.original` stores the exact prior value; `downgrade` restores it. Keys show a **Legacy: full access** banner in the admin UI. On the edit form, "Keep legacy full access" (with an explicit confirmation) leaves the stored row untouched; unticking it and saving explicit capabilities replaces the legacy document. Schema v1 documents are still parsed for rolling deploys.

Recommended follow-up: edit each legacy key to the smallest preset that fits, then set `API_KEY_ALLOW_LEGACY_FULL_ACCESS=false`.

## 7. Admin UI guide

- Create/edit show plain-language capability checkboxes with the exact endpoints each unlocks, sensitivity badges, and presets.
- Choosing sensitive or personal-data capabilities asks for confirmation; personal-data capabilities disable the `?api_key=` option.
- A scope panel appears when a scopable capability is selected. Leaving both lists empty while scope is enabled is rejected in the form.
- List and details pages show the **effective access** (capabilities, scope, `?api_key=` allowed, legacy full access). The API Management registry shows the required capability per endpoint.
- Create/edit/rotate/revoke are audit-logged, including a summary of the granted access.

## 8. Deployment notes

- **Website**: the Next.js site must not ship a data-capable key to browsers. A key in `NEXT_PUBLIC_*` is public; use a server-side key with the **Website back end** preset and send it in the `Authorization` header, not `?api_key=`.
- **FDRS remote importer** and any integration that reads `/fdrs/published-data`, `/data` or submissions needs the corresponding capability (`content:read`, `data:read`, `submissions:read`).
- The `User.api_key` column and `flask generate-api-key` command are unused by the API.
