# Backoffice security review and hardening (September 2026)

This document records an internal security review of the Backoffice, the fixes made in response, how to roll them out, and what is still open. It is the review guide for the PR that introduced it. Each section maps to one commit.

Reviewed surfaces: authentication and sessions, admin route guards (RBAC), non-admin API and mobile routes, injection and XSS, file handling and outbound requests, secrets and deployment, AI/RAG and data protection.

Method: seven read-only audits produced the findings. Eight fix groups then addressed them, each required to fix the root cause and fit the whole picture (shared helpers, tests, docs) rather than patch single routes. Severity labels below are the audit's and were verified against the code by reading it. Nothing was tested against a live deployment.

## How to review

Commits are ordered so the migration chain stays valid. They are not guaranteed to pass tests one at a time, because a few files (for example `config/config.py`, `app/__init__.py`, `docs/DEVELOPER-HANDBOOK.md`) carry changes from several groups.

| # | Commit | Section |
|---|---|---|
| 1 | Harden container, secrets handling, logging and error responses | [1](#1-container-secrets-logging-and-error-responses) |
| 2 | Require authorization for public documents and add opaque public IDs | [2](#2-public-documents-and-id-enumeration) |
| 3 | Harden authentication, sessions and request perimeter | [3](#3-authentication-sessions-and-perimeter) |
| 4 | Enforce explicit API key capabilities and clarify them in the admin UI | [4](#4-api-key-capabilities) |
| 5 | Enforce a consistent admin guard and scope policy | [5](#5-admin-guards-and-scope) |
| 6 | Apply object-level authorization to form child routes and lock status transitions | [6](#6-form-object-level-authorization-and-locking) |
| 7 | Enforce AI data and document access policy, MCP auth and export safety | [7](#7-ai-rag-mcp-and-exports) |
| 8 | Harden against injection, XSS and resource exhaustion | [8](#8-injection-xss-and-resource-exhaustion) |
| 9 | Document security policies in the developer handbook | [Handbook sections](#handbook-sections) |

Suggested reading order for a reviewer: sections 4 and 5 (they change the permission model), then 2 and 3, then 6 to 8, then 1.

## Rollout checklist

Do these in order.

1. **Database.** Run `flask db upgrade` with or before the deploy. Three migrations, single head: `add_submitted_document_public_id`, then `add_auth_state_entry`, then `api_key_permissions_v2`. Without Redis, the new code needs the `auth_state_entry` table.
2. **Environment.**
   - Set `FLASK_CONFIG` explicitly. **Unset now means production.** Dev containers must set `development`.
   - Set `MOBILE_JWT_SECRET` (32+ characters, different from `SECRET_KEY`). A missing or weak value is flagged on System Configuration and does not block startup. Set `AI_JWT_SECRET` (recommended; it falls back to `SECRET_KEY` with a warning).
   - Set `PROXY_FIX_X_FOR` to the real number of trusted proxy hops, and keep `TRUST_PROXY_HEADERS=true` behind a proxy.
   - Configure Redis (`RATELIMIT_STORAGE_URI` or `REDIS_URL`) for multi-worker deployments; otherwise shared state falls back to the database.
3. **RBAC.** `flask rbac seed` (runs on deploy) adds the permissions and role listed in [section 5](#5-admin-guards-and-scope). Existing `admin_core` and `admin_full` holders lose four capabilities until granted them explicitly.
4. **API keys.** Existing keys migrate to a marked "Legacy: full access" state so nothing breaks. Review them in the admin UI, then set `API_KEY_ALLOW_LEGACY_FULL_ACCESS=false`.
5. **Clients.** Ship the mobile build that uses the OAuth code exchange before switching off `MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK`. Give the Website a server-side API key with the "Website back end" preset ([section 4](#4-api-key-capabilities)).
6. **Container.** Redeploy the image; retire old image tags (they contain the baked-in root password and shared host keys). Set `ENABLE_SSH=true` only while someone needs a shell.
7. **After tokens expire** (refresh tokens last 30 days), turn off `MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY`, `AI_JWT_ACCEPT_LEGACY_SECRET_KEY` and `MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK`.

Behaviour changes users or operators will notice are collected under [Behaviour changes](#behaviour-changes-to-communicate).

---

## 1. Container, secrets, logging and error responses

| Finding | Root cause | Fix |
|---|---|---|
| Known root password in the image (Critical) | The Dockerfile set `root:Docker!` and shared host keys; sshd always started with `PermitRootLogin yes`, password auth, `3des-cbc` and `hmac-sha1` | sshd starts only when `ENABLE_SSH=true` via `docker/start-ssh.sh`, with host keys generated at start, modern crypto only, `sshd -t` before launch, forwarding off. `SSH_AUTH_MODE=key` accepts only keys from `SSH_AUTHORIZED_KEYS`; the Azure password is set only in `platform` mode |
| Secrets exposed to SSH shells (High) | `docker/azure-ssh-profile.sh` exported every app secret | Exports only `FLASK_CONFIG`, `FLASK_APP`, `DATABASE_URL`, `SECRET_KEY`, `MOBILE_JWT_SECRET`, `AI_JWT_SECRET`, `REDIS_URL` |
| Image defaults to `FLASK_CONFIG=development` (Medium) | Dockerfile `ENV` | Default is `production`; new `.dockerignore` |
| Production artifacts tracked (High) | `instance/` was ignored but already tracked; no rule for incident logs or data samples | `prod-logs-incident/`, `prod_data_sample.json` and `instance/` removed from the index (`git rm --cached`) and ignored. **History is not rewritten**; see [Follow-ups](#open-items-and-follow-ups). The logs contain no credentials but do contain 492 client IPs, the hostname and `ARRAffinity` cookies |
| Request payloads stored unredacted; log formats inconsistent (Medium) | Three separate redaction implementations with exact-key matching | One shared policy in `app/utils/logging_security.py` (recursive, case- and separator-insensitive key matching, JWT/bearer scanning) used by the API tracker (payloads capped at 8 KB), activity-form redaction and the gunicorn/werkzeug access logs |
| Error bodies leaked internals; tracebacks persisted (Medium) | Production returned raw `error.description`; security events stored `traceback[:1000]` | Generic production messages, `X-Request-ID` on every response, one JSON envelope for 400/401/403/404/405/413/429/500/502/503 (`Retry-After`, `Allow` where relevant). A 500 stores only the exception type, a traceback hash, top frames, request ID and redacted URL |
| Header gaps (Low) | Missing directives | CSP adds `object-src 'none'`, `base-uri`, `form-action`, `frame-ancestors 'none'`; COOP/CORP; expanded Permissions-Policy. New settings `CSP_STRICT_MODE`, `CSP_IMG_SRC_EXTRA`, `CSP_CONNECT_SRC_EXTRA`. `'unsafe-inline'` in `style-src` and `https:` in `img-src` are kept because templates depend on them |
| Seeding could create predictable accounts (Medium) | Denylist guard, hardcoded `test123`, secret scanner allowlisted it | Allowlist: `FLASK_CONFIG` must be exactly `development` and the DB host local. `test123` removed and no longer allowlisted; `create-admin` confirms and checks strength |
| Dependency hygiene (Medium) | Unpinned `locust` in production requirements; older PyJWT | Pinned; `locust` moved to `requirements-dev.txt`; PyJWT 2.14.0. `pip-audit` on `requirements.txt` is clean. `npm audit` still shows production findings (dompurify, fflate, brace-expansion, nanoid); recommended override `dompurify ^3.4.13` is not applied |
| `Procfile` pointed at a stale entrypoint (Low) | Old factory path | `gunicorn --config config/gunicorn.conf.py run:app` |

Runbooks added: `docs/runbooks/operations/container-ssh-access.md`, `docs/runbooks/security/committed-artifacts-history-purge.md`.

Not verified: `docker build`, Azure Portal SSH or `az webapp ssh`. If the Kudu tunnel fails on key exchange, set `SSH_LEGACY_CRYPTO=true` temporarily. `azure-webapp/azure_webapp_ssh_lib.ps1` forces `hmac-sha1` and needs that setting until its options are updated.

## 2. Public documents and ID enumeration

**Root cause.** `stream_public_download_response` only checked that `public_submission_id` was set, so it ignored `is_public` and approval status. The integer IDs made enumeration trivial, but authorization was the bug.

**Decision on UUIDs.** Yes, as defense in depth only. For a document that is public and approved, enumeration reveals nothing new. A UUID stops scraping by counting and limits the damage if the policy regresses. It does not replace the policy.

**Fix**
- A public download now requires `public_submission_id` **and** `is_public` **and** approved status. Thumbnails and covers require `is_public` and approved. Denied and unknown IDs return the same 404.
- New `submitted_document.public_id` (UUIDv4, unique, NOT NULL) via `add_submitted_document_public_id` (backfills with `gen_random_uuid()`; tested upgrade, downgrade and re-upgrade). All public URLs are built in one place, `app/services/documents/public_access.py`; the API returns UUID URLs plus a `public_id` field.
- Integer URLs keep working under the same policy: download routes 302-redirect (with `Deprecation: true`) to the UUID URL; display and thumbnail integer routes serve directly.
- Download routes are rate-limited (`PUBLIC_DOWNLOAD_RATE_LIMIT`, default `60 per minute` per IP).
- Template image `?preview=` no longer skips login. Anonymous users need `?public_token=<AssignedForm.unique_token>` of an active public form whose published version contains the item.
- Every upload response sets `nosniff` and `Content-Security-Policy: default-src 'none'; sandbox`; HTML, SVG, XML, JS and CSS are always attachments; blob names with `.` or `..` segments are rejected. The security-headers middleware keeps a CSP already set on the response so this is not overwritten.
- SVG branding uploads are rejected (stored XSS); raster types are decoded with Pillow and must match their extension.
- FDRS `source_url` redirects go through the shared outbound-URL policy and an `IFRC_DOCUMENT_ALLOWED_HOSTS` allowlist; otherwise 404.

**Audit of similar endpoints**

| Route | Result |
|---|---|
| `/forms/public-document/<int>/download`, legacy `/public_documents/download/<int>` | Fixed: policy plus UUID redirect |
| `/documents/display/<int>`, `/documents/thumbnail/<int>` | Already required public and approved; UUID routes added |
| `/forms/template-image/<id>/<path>` | Fixed: preview bypass removed |
| `/api/v1/uploads/{branding,sectors,spef,ns}/<name>` | Shared helper rejects `.`, `..` and NUL names |
| `/resources/download/...`, sector/NS/indicator logo routes | Public by design; get the new upload headers |
| `/admin/documents/serve/<int>` | Not changed: does not check approved status (follow-up) |
| `/forms/public-submission/<int>/success` | Not changed: unauthenticated with sequential IDs (follow-up) |
| `/api/v1/public/documents/<int>[/download]` | Not changed: fallback download path imports a `StorageService` that does not exist (follow-up) |
| `/download_submission_pdf/<int>`, public submission view/edit, AI document routes | Already guarded |

## 3. Authentication, sessions and perimeter

| Finding | Fix |
|---|---|
| Site lock bypass with any `Authorization: Bearer x` or `X-API-Key` header (High) | Header presence never lifts the lock. Only `/api/*` and the `indicator_bank_compat` blueprint are exempt, by path. The bypass cookie stores an HMAC, not the secret |
| Bearer JWT authenticated on every route (Medium) | Bearer JWTs authenticate only under `MOBILE_JWT_BEARER_PATH_PREFIXES` (default `/api/mobile/v1/`). The cookie bridge is bound to the token's `sid` and revocation state; `exchange-session` refuses Bearer callers so an access token cannot mint a refresh token |
| Refresh reuse detection, session blacklist, lockout and rate limits were per worker (High/Medium) | Shared store (`app/utils/auth_state.py`): Redis if configured, otherwise the `auth_state_entry` table. Refresh tokens are single-use with a family ID; reuse revokes the family and session. The store fails closed (refresh and OAuth exchange return 503; the generic limiter degrades to per-process, never open). Writes use their own connection because the transaction middleware rolls back responses with status 400 or above, which had silently discarded the mobile lockout and reuse-revocation writes |
| Client IP trusted `X-Forwarded-For` (Medium) | One `get_client_ip()` (`app/utils/client_ip.py`): `remote_addr` after ProxyFix with `PROXY_FIX_X_FOR` trusted hops; forwarding headers are never read. `is_loopback_request()` rejects any request carrying a forwarding header. Staging ProxyFix wiring fixed |
| Unset `FLASK_CONFIG` selected development (High) | Unset means production (only an interactive `python run.py` on loopback gets development). `validate_security_settings` (`app/utils/security_startup.py`) aborts startup in production or staging (or with `STRICT_ENV_VALIDATION=true`) on a bad `AI_JWT_SECRET`, `DEBUG` on, or a bad auth-state backend. A missing, short or equal `MOBILE_JWT_SECRET`, and `ENABLE_SSH` left unset, are logged and shown on System Configuration without blocking startup. `MOBILE_JWT_SECRET` and `AI_JWT_SECRET` are separate, with `MOBILE_JWT_SECRET_PREVIOUS` for rotation. `PLUGIN_UPLOAD_ENABLED` is off in production and staging |
| Idle timeout skipped for `/api/*` (Medium) | Timeout and revocation apply to every cookie-authenticated request (JSON 401 on `/api/`); only Bearer-JWT requests are skipped |
| Mobile OAuth tokens in the deep-link query string (Medium) | `/login/azure` takes an S256 `app_code_challenge`; the callback redirects to `humdatabank://oauth-success?code=...`; the app redeems it at `POST /api/mobile/v1/auth/oauth/exchange {code, code_verifier}`. Codes are single-use, stored hashed, valid 60 seconds. The legacy flow stays behind `MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK` (default true, deprecated). Flutter files updated (`azure_login_screen.dart`, `deep_link_service.dart`, `auth_service.dart`, `app_config.dart`) but **not compiled or tested** |
| Enumeration and abuse (Medium/Low) | Login lockout shared across workers (10 failures per email in 15 minutes, web and mobile); dummy hash for unknown and deactivated users; generic 401 for deactivated mobile accounts (`MOBILE_REVEAL_DEACTIVATED_ACCOUNT` restores 403); `POST /register` limited to 5 per minute per IP; neutral message for existing emails (`REGISTRATION_REVEAL_EXISTING_EMAIL` restores the old message); `GET /register/check-email` returns 404 unless `REGISTRATION_EMAIL_CHECK_ENABLED=true` |
| Dev act-as could impersonate any user (Medium) | Only the seeded `test_sys@`, `test_admin@`, `test_focal@` users plus `DEV_ACT_AS_EXTRA_EMAILS`; requires development config, `DEBUG`, and a true loopback request with no forwarding headers. `DEBUG_SKIP_LOGIN` is now defined in `Config` and fatal at startup outside development |

Not closed: `api_bp`, `mobile_bp`, `mcp_bp`, `ai_bp` and `indicator_bank_compat_bp` are CSRF-exempt at blueprint level. A cookie-authenticated mutating call there is safe only if the route calls `enforce_api_or_csrf_protection()`; the startup audit does not verify that each route does.

## 4. API key capabilities

**How it worked before.** `api_keys.permissions` was never written by the create and edit forms, so it was `NULL` for almost every key. The only reader treated `NULL`, malformed or unknown values as full read access. `@require_api_key` only checked that the key was valid. `read_scoped` was honored only on `GET /api/v1/data`; other lists were organisation-wide and unpaginated (including public-submitter emails), `/users` and `/quiz/leaderboard` returned personal data, and `GET /submissions/<id>` opened any submission. `?api_key=` was accepted although a comment said otherwise, the `MOBILE_APP_API_KEY` env value acted as an unscoped elevated key, and `per_page` went up to 100000. The admin UI implied permissions the server did not enforce. This is Critical in the audit's ranking.

**How it works now**
- A key holds explicit **capabilities**; each key-accepting route declares the one it needs; enforcement is in one place (`require_api_key(capability=..., scope_aware=...)`, `require_api_key_or_session`, `api_capability`). A missing capability returns 403 with `required_permission`. Routes with no declared capability deny keys. `NULL`, malformed or unknown permission data grants nothing.

| Capability | Kind |
|---|---|
| `data:read` | scopable, sensitive |
| `submissions:read` | scopable, sensitive |
| `templates:read` | scopable |
| `documents:read` | sensitive |
| `users:read` | personal data |
| `reference:read` | standard |
| `content:read` | standard |
| `indicators:suggest` | write |
| `indicators:manage` | personal data |
| `mobile:client` | marker only |
| `mcp:use` | MCP proxy |

- **Scope.** A template and country scope applies to lists and single-record routes; out-of-scope records return 404; both lists empty means no data; scoped keys are refused on routes that cannot apply scope.
- **Query-string keys.** `?api_key=` is refused unless the key opts in, and the option is blocked with personal-data capabilities. Such responses are `no-store` with a `Warning` header and key values are redacted from logs.
- **Env mobile key.** Header-only and limited to `MOBILE_APP_API_KEY_CAPABILITIES` (default reference, content and the mobile marker).
- **Page size.** Capped at `API_KEY_MAX_PER_PAGE` (10000); `/users`, `/resources` and `/indicator-suggestions` at 500. `MAX_PER_PAGE` in `app/utils/api_helpers.py` went from 100000 to 10000, which also affects session callers.
- **Admin UI.** Plain-language capabilities, the endpoints each unlocks, presets, warnings and confirmation for sensitive access, and each key's effective access including "Legacy: full access".
- **Route catalog.** `app/services/security/api_key_route_catalog.py` is built from the live URL map, and a test asserts no key-accepting route lacks a capability.
- **Migration `api_key_permissions_v2`.** `NULL` and `read_all` become marked legacy full access; `read_scoped` becomes data and reference with the same scope; `none` becomes reference and content only; unknown or malformed becomes nothing. Downgrade restores the exact old value.

Full write-up: [`docs/setup/api-keys-and-permissions.md`](../setup/api-keys-and-permissions.md).

Also fixed: a pre-existing 500 on `GET /api/v1/submissions`. Consumers to update: the Website ships `NEXT_PUBLIC_API_KEY` (default `databank2026`) to browsers and uses `?api_key=` with `per_page=100000` (needs a server-side key with the "Website back end" preset, sent in a header); the remote FDRS importer's key needs `content:read`, `data:read` or `submissions:read` depending on what it reads.

## 5. Admin guards and scope

**Root cause.** About 392 of 545 admin handlers used `permission_required` alone, with no shared policy on which capabilities are administrator-only, which need a scope check, and which must be POST-only. Scope checks existed for some routes and not their siblings.

**Policy** (in `app/routes/admin/route_policy.py`, enforced by the startup audit)
- Every `/admin/**` route needs `admin_required`, `system_manager_required`, or a `permission_required*` / `admin_permission_required*` decorator with `admin.*` codes.
- Dangerous capabilities get their own permission or are system-manager-only. GET is safe; state changes are POST-only with CSRF.
- Scope is enforced server-side using the delegated-administration entity and country scope.
- No self-escalation: non-system-managers cannot grant restricted roles, `admin_*` roles they do not hold, or roles bundling permissions they lack.
- The audit (`startup_tasks.collect_admin_route_guard_findings`, `audit_admin_route_guards`) warns by default and raises in `error`, `strict` or `raise` mode. It reports unguarded routes, non-`admin.` permissions outside the allowlist, missing system-manager guards, permission mismatches, state-changing GETs, POST-only endpoints allowing GET, CSRF-exempt mutations, login-only POSTs and `/plugins/static`. It returns no findings on the real app (tested). Previously, `error` and `strict` modes never enforced anything because an outer `except` swallowed the error.

| Route | Before | After |
|---|---|---|
| `apply_imputed_value` and AI helpers (`data_exploration.py`) | Any admin could change any submission's value | New `admin.data_explore.impute`; 404 outside the actor's scope; rejects a form item from another template |
| User entity grants, role assignment, `/admin/api/rbac/roles` | A scoped admin could grant any entity or country | Limited to entities the actor can delegate; no self-grants or grants to admin targets |
| Country edit and delete, import | Not scoped | Edit scoped; delete needs `admin.countries.delete` plus scope; import checks scope per row. Also fixed: delete always crashed on a nonexistent `country.users` |
| Import change logs | `templates.view` or `audit.view` read any log | System manager, `admin.audit.view`, or the job's starter; others get 404 |
| `test_error_notification` | State change on GET | POST-only, CSRF, system-manager-only |
| Session cleanup and end-session, `resolve_security_event` | Behind read permission `admin.analytics.view` | `admin.system.maintain`; `admin.security.respond` |
| Plugin install, upload, uninstall | Not system-manager-only | System-manager-only; upload also needs `PLUGIN_UPLOAD_ENABLED`; name regex, symlink check, 300 MB uncompressed cap. Plugin upload is still remote code execution by design |
| `serve_plugin_static` | Unauthenticated | 401 for anonymous users unless listed in `PLUGIN_PUBLIC_STATIC_PLUGINS`; allowlisted extensions only |
| `refresh-csrf-token` (GET) | No protection | Refuses cross-site requests; `no-store` |
| `DEBUG_SKIP_LOGIN` | A rejected auto-login still ran the view unauthenticated | Honored only in development with `DEBUG`; requires `is_loopback_request()`; rebuilds the session; a rejected auto-login now falls through to normal checks |

**Seed catalog.** New permissions `admin.countries.delete`, `admin.system.maintain`, `admin.data_explore.impute`; new role `admin_system_maintainer`. `admin_full` excludes `admin.system.maintain` (alongside `admin.settings.manage` and `admin.plugins.manage`); `admin_countries_manager` gains delete; `admin_data_explorer_data_table` gains impute. No migration: the catalog is code and `flask rbac seed` runs on deploy. Existing `admin_core` and `admin_full` holders lose country delete, session cleanup and end-session, monitoring log clear and imputation until granted the new roles or permissions.

## 6. Form object-level authorization and locking

**Root cause.** Two access models had drifted apart. The web entry page used `AuthorizationService.can_access_assignment` / `can_edit_assignment` / `can_submit_assignment` (RBAC-, scope- and status-aware). The shared helpers and child-id routes used `EntityService.check_user_entity_access` (any `admin.*` permission passes) or only `@login_required`, and no helper mapped a child ID to its owning assignment.

**Fix.** Helpers in `app/utils/form_authorization.py` reuse the existing `can_*` methods: `authorize_child_json` (resolves the owner and authorizes the verb; missing or out-of-scope IDs return an opaque 404, a denied verb on a visible owner returns 403, orphans are system-manager-only), `authorize_aes_json` / `load_aes_for_user`, `check_aes_action`, `public_submission_access`, `user_can_access_template`, `user_can_read_lookup_list`, `lock_aes_for_update`, `begin_aes_transition`, `lock_aes_rows_for_update`. `get_aes_with_joins`, `check_aes_access_light` and `get_formdata_map` now use `can_access_assignment`.

| Route | Before | After |
|---|---|---|
| `PATCH repeat-instances/<id>/toggle-hide` (verified IDOR) | login only | child edit: 404 or 403, plus completion refresh |
| Dynamic indicators (update, remove, render, add, render-pending) | country check only, or any admin | child view or edit; the section must belong to the template (else 400) |
| Discussion comments | any admin | assignment view or edit |
| Lookup list options, matrix search | login only, full rows | 404 unless the list is used by a reachable template or the user is a system manager or holds a template/assignment admin permission; capped at 5000 rows with `truncated` |
| Public submission approve, reject, delete, status; view, edit; PDF | any admin; `?edit=true` granted write | `admin.assignments.public_submissions.manage`; `?edit=true` removed; PDF needs view access |
| Mobile access-request approve/reject, user activate/deactivate, template structure, toggle-public, generate-url | weaker than web | same as web permissions and scope; audit logs added |
| `POST /api/mobile/data/indicator-suggestions` | anonymous, in-memory rate limit | still anonymous (offered before login) but 5 per minute on the shared store, strict validation (`app/utils/suggestion_intake.py`), DB-backed caps (3 per email per day, 100 per hour), optional reCAPTCHA (`MOBILE_SUGGESTION_REQUIRE_CAPTCHA`, off by default) |

**Race conditions.** Every route and service that writes `AssignmentEntityStatus.status` now takes `SELECT ... FOR UPDATE` and re-validates the transition against the locked row: reopen, page reopen and return, approve (server now requires `submitted`), return for revision (requires `sent_for_review`), admin status PUT and bulk update (ascending ID order), page-mode toggle rollups, every entry-page POST, and the FDRS and UPR importers. There is no revoke, bulk-approve or mobile transition in the code. Two-connection Postgres tests prove a second concurrent transition is rejected or serialized and that opposite lock orders do not deadlock.

Real bugs fixed on the way: `routes/excel.py` used `ExcelService` and `_validate_assignment_editable_state` without defining them; `forms_api.py` was missing `from contextlib import suppress`; the indicator-bank sector search ran `LIKE` on a jsonb column and returned 500.

## 7. AI, RAG, MCP and exports

| Finding | Root cause | Fix |
|---|---|---|
| Same-organisation users could read non-public form data for any country (High) | Three different access rules (AI tools, data retrieval, entry form) | One `DataAccessPolicy` (`app/services/data_retrieval/access.py`) decides countries and `FormItem.privacy` values; used by AI tools, `form_retrieval`, `shared`, `form_helpers` and the assignment checks |
| Anonymous public chat could call databank tools | Tool catalog not restricted by caller | Anonymous callers get `PUBLIC_TOOL_ALLOWLIST`; `execute_tool` refuses tools not exposed to the caller; proxy secret uses `hmac.compare_digest`; dev fallback is loopback-only and fails closed |
| `allowed_roles` on AI documents never took effect; no scope on retrieval (High) | ACL copied into several places | `app/services/ai/documents/access.py` is the single authority (Python and SQL filter). Rule: doc-admin or internal, or (`is_public` and role check), or (owner and owner scope). `allowed_roles` NULL means everyone, a list needs one of those roles, `[]` means nobody. Used by vector store, tools, management, QA, public document service and the UPR plugin. Unapproved submitted documents are no longer AI-public |
| Cost and rate abuse; WebSocket checks at connect only (Medium) | Very high per-user caps; limiter failed open on Redis errors | Config-driven daily limits and cost budgets summed from `ai_reasoning_traces.total_cost_usd`; WebSocket limiter falls back to a stricter in-memory limit at half rate; each message re-checks authorization |
| Form-builder mode trusted client JSON (Medium) | `page_context.formBuilder` accepted as sent | Accepted only with a cookie session, `admin.templates.create` or `edit`, template access and a version belonging to the template; read only through `trusted_form_builder_context()` |
| Traces held full prompts and tool output (Medium) | No redaction or retention | Stored redacted by default (modes redacted, minimal, full); nightly purge at 03:30 (90 days for traces, 30 for tool content) and `ai_trace_purge` CLI; raw tool output visible to system managers only; `/api/ai/v2/health` generic for unauthenticated callers |
| Unauthenticated MCP reverse proxy (High) | No guard on `/mcp` | Requires an API key with `mcp:use` |
| CSV and XLSX formula injection (Medium) | No neutralization | `app/utils/export_safety.py` prefixes `'` to cells starting with `= + - @`, tab or CR; applied at about 15 export sites |
| Outbound URLs from configuration unchecked (Medium) | No shared policy | `app/utils/outbound_url.py`: https only, no credentials, host allowlist, blocked IP classes, DNS check. Applied to MCP and LibreTranslate (redirects disabled; private networks via `LIBRE_TRANSLATE_ALLOWED_NETWORKS`); the IFRC fetch validator delegates to it. DNS rebinding is a known remaining gap |

## 8. Injection, XSS and resource exhaustion

The injection audit found no exploitable SQL injection or SSTI. The fixes are defense in depth at shared-helper level.

| Finding | Fix |
|---|---|
| `ILIKE` wildcard widening | `escape_like` and `contains_pattern` in `app/utils/sql_utils.py`, used at about 20 call sites; `test_sql_like_safety.py` scans the tree and fails on any unescaped `ILIKE` |
| Data Explorer plugin panels rendered with `\|safe` | Template name validated, returned as `Markup`, `\|safe` removed; plugin contract documented |
| XSS sinks in JS and templates | `SafeDom` (`safe-dom.js`) hardened: escapes quotes, allowlists URLs, `sanitizeHtml`, denies by default when unavailable; about 15 JS and template files migrated. The sweep is "known sinks fixed", not proven complete |
| `document.write` on indicator-bank save | AJAX post reading JSON |
| Email header (CRLF) injection | `app/utils/email_headers.py` sanitizes subject, sender, recipients and attachment names |
| Redirect validation gaps | `is_safe_redirect_url` handles encoded, `//`, backslash and userinfo variants |
| Workbook and image resource exhaustion | `app/utils/safe_workbook.py` inspects the zip (size, members, ratio, declared dimensions) before parsing; `safe_image.py` sets Pillow pixel limits, clamps PDF DPI, adds an OCR timeout; CSV and JSON uploads capped. Defaults: 25 MB upload, 250 MB expanded, 200,000 rows, 1,024 columns (`WORKBOOK_MAX_*`) |
| Virus-scan fail-open; SSRF on `CLOUD_SCANNER_URL` | Fail-open logs at ERROR; scanner URL goes through the outbound-URL policy (`CLOUD_SCANNER_ALLOWED_NETWORKS`), no redirects |
| `str(e)` in responses | `ClientInputError` (`app/utils/api_errors.py`) plus generic messages in public integrations, data quality and 27 more handlers; `test_error_exposure.py` scans the tree |
| `\|safe` inventory | Pinned by `test_template_safe_inventory.py`. Real bugs fixed: script breakout via `config_json` in the interactive-map template, unescaped f-string HTML in `form_integration.py`, a blank-body fallback that could reassemble `<script>` |

## Handbook sections

`docs/DEVELOPER-HANDBOOK.md` gained: Canonical guard and permission model, Object-Level Authorization (with Locking status transitions), Serving files without login, AI access policy (who may read what), Plugin Data Explorer panel contract, and a pointer to the security setup notes.

## Behaviour changes to communicate

- Unset `FLASK_CONFIG` means production; weak or missing secrets stop startup.
- Legacy API keys keep full access until reviewed; new keys grant only what is ticked; query-string keys are off by default.
- Old integer public document URLs redirect to UUID URLs (and return 404 when the policy denies them).
- SVG logos and favicons cannot be uploaded; new uploads are sandboxed.
- Non-IFRC `source_url` redirects return 404 unless allowlisted.
- Some admin screens that showed raw exception text now show a generic message.
- Clients that retry a lost refresh response are signed out (deliberate; a grace window would weaken theft detection).
- Approving an assignment requires status `submitted` on the server.
- Every entry-page POST, including autosave, takes a per-assignment row lock.
- Same-organisation users no longer see non-public data outside their assigned countries; anonymous chat loses `compare_countries`, `get_country_information` and `validate_against_guidelines`.
- MCP clients need `mcp:use`; the form-builder AI assistant needs a cookie session.
- AI traces are stored redacted with retention limits.
- Custom roles holding only `admin.users.edit` lose mobile access-request approval.

## Open items and follow-ups

Not done in this PR:

- **History purge and rotation** for the committed production logs and HAR: runbook at `docs/runbooks/security/committed-artifacts-history-purge.md`; requires a force-push by the repository owner. Rotate publish and deploy credentials as a precaution; rotate `SECRET_KEY`, JWT secrets or the DB password only if those files held live values.
- Website uses a public API key and `?api_key=`; needs a server-side key.
- `EntityService.check_user_entity_access` still lets any admin through for content management and country data retrieval.
- `public_submission_success/<id>` is unauthenticated with sequential IDs; `/admin/documents/serve/<int>` does not check approved status; `services/public/document_service.py` imports a nonexistent `StorageService`.
- `forms_api` child-write endpoints check status but take no lock; `update_public_submission_status` is unlocked; the FDRS and UPR importers hold row locks until the run commits.
- CSRF enforcement inside exempt blueprints is not verified per route.
- Rate limits stay per worker unless Redis is configured; countries and periods routes have no `per_page` clamp.
- `User.api_key` and `flask generate-api-key` are dead code.
- Root `docker-compose.yml` defaults `TEST_*_PASSWORD` to `test123`; `auth.py` logs user emails; a few log lines include raw URLs.
- Dockerfile: unpinned `torch`, runs as root, requirements not hash-locked.
- `npm audit` production findings (dompurify, fflate, brace-expansion, nanoid).
- Pre-existing, unrelated: `ai_job_runner._recover_stuck_job_items` uses `db` without importing it.

Product decisions for the maintainers:

- Should legacy API keys lose personal-data access now instead of after review?
- Keep `SSH_AUTH_MODE=platform` as default or use `key` only? Should `ENABLE_SSH` and `SSH_*` be slot-sticky?
- Widen the external-redirect allowlist or add an interstitial page?
- Gate the system lookup lists (`country_map`, `national_society`, `indicator_bank`)?
- Enable the mobile suggestion captcha (requires the app to send a `token`)?
- Should `admin.system.maintain` and `admin.plugins.manage` stay outside `admin_full`; is system-manager-only right for plugin install and `test_error_notification`?
- Roll out `CSP_STRICT_MODE` in report-only first; run the container as non-root; pin `torch` and hash-lock requirements?
- Should `plugins/upr/ai/ifrc_routes.py` keep defaulting IFRC imports to `is_public=True`?
- Allow approving from `sent_for_review` as well as `submitted`?
- Lockout is keyed by email, which lets an attacker lock a known address for 15 minutes; consider email plus IP, CAPTCHA, or step-up. No absolute session lifetime or step-up re-authentication was added.

## Verification

See the PR description for the current test results and the comparison against `main`. Not run: `docker build`, Azure SSH, Flutter build and device test, browser or Playwright checks of the admin UI, a live deployment.
