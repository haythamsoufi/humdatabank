# Security

Security practices and configuration for the Backoffice.

> **Recent Security Updates (2024):** All critical and high-priority security issues have been resolved. See **`docs/setup/security.md`** (this page), **`docs/runbooks/security/`** (RBAC audit exemptions), and the **[runbooks index](../runbooks/README.md)** for operational security notes.

## SECRET_KEY

The `SECRET_KEY` is critical for session security, CSRF protection, and token generation. **It MUST be set in production.**

Generate a secure key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it in your environment:

```bash
export SECRET_KEY="your_generated_32_character_random_string_here"
```

## Authentication, sessions and perimeter

### Request flow

```
client -> reverse proxy -> ProxyFix (PROXY_FIX_X_*) -> request hooks -> site lock -> session timeout
       -> auth (cookie session | mobile Bearer JWT | API key | AI token) -> CSRF -> view
```

- **One client IP.** `app.utils.client_ip.get_client_ip()` returns `request.remote_addr` *after* ProxyFix has applied the configured number of trusted hops. `X-Forwarded-For`, `Forwarded` and `X-Real-IP` are never read directly. Rate limiting, login lockout, audit logs, session/device records and the dev-only loopback checks all use it. `is_loopback_request()` additionally refuses any request that carries a forwarding header, so a reverse proxy can never make a remote caller look local.
- **Cookie vs Bearer.** Bearer JWTs authenticate only under `MOBILE_JWT_BEARER_PATH_PREFIXES` (default `/api/mobile/v1/`). Elsewhere the header is ignored, so a mobile access token cannot open a web session on admin or other routes. A Bearer request does not create a session cookie; the WebView bridge that trades a token for a cookie is bound to the token's session id and revocation state.
- **Idle timeout and revocation** (`SESSION_INACTIVITY_TIMEOUT`, default 2 h) apply to every cookie-authenticated request, including `/api/` paths (JSON 401). Bearer-JWT requests are bounded by the access-token lifetime (30 min) and session revocation.
- **Site lock** (`COMING_SOON`): only `/api/*` and the Indicator Bank compat blueprint are exempt, by path. No request header lifts the lock. The bypass cookie stores an HMAC of the bypass secret, never the secret itself.

### Configuration selector fails closed

`FLASK_CONFIG` unset or empty resolves to **production**. Only an interactive `python run.py` bound to loopback defaults to development. `default` is a deprecated alias for `development` (warning), unknown values abort startup. The resolved name is written back to the environment so every module sees the same value.

### Startup validation (`app/utils/security_startup.py`)

In production/staging (or with `STRICT_ENV_VALIDATION=true`) the app refuses to start when: `DEBUG` is on; `AI_JWT_SECRET` is set but short or equal to another secret; `AUTH_STATE_BACKEND` is invalid or `redis` without a Redis URL; multiple workers run with `RATE_LIMIT_REQUIRE_SHARED_STORAGE=true` and no shared store. `DEBUG_SKIP_LOGIN=true` outside development + DEBUG is fatal in every environment. A missing, short, or `SECRET_KEY`-equal `MOBILE_JWT_SECRET`, and `ENABLE_SSH` left unset, are warnings: they are logged and shown on System Configuration, and they do not block startup. Other warnings (logged, not fatal): `AI_JWT_SECRET` falling back to `SECRET_KEY`, `TRUST_PROXY_HEADERS` off, `PLUGIN_UPLOAD_ENABLED` on, legacy compatibility flags still on, per-process rate limits with several workers. Worker count is read from `GUNICORN_WORKERS` / `WEB_CONCURRENCY` (`auto` = 2 x CPU + 1), else 3 under gunicorn, else 1.

### Signing secrets

| Purpose | Variable | Notes |
|---|---|---|
| Web sessions, CSRF, password-reset and OAuth state tokens | `SECRET_KEY` | Never used for mobile or AI tokens once the variables below are set. |
| Mobile access/refresh JWT | `MOBILE_JWT_SECRET` | Must differ from `SECRET_KEY`. `MOBILE_JWT_SECRET_PREVIOUS` (comma list) is accepted for verification during rotation. |
| AI WebSocket/stream tokens | `AI_JWT_SECRET` | Falls back to `SECRET_KEY` with a deprecation warning. |

Tokens signed by the old shared secret are still accepted while `MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY` / `AI_JWT_ACCEPT_LEGACY_SECRET_KEY` are `true` (default) so deployed apps are not logged out. New tokens always use the dedicated secret. Turn the flags off after one refresh-token lifetime (30 days).

### Shared authentication state

Refresh-token single-use markers, revoked sessions, token families, login-failure counters, mobile OAuth codes and the auth rate-limit counters live in a store that all workers and instances share (`app/utils/auth_state.py`):

1. Redis when `RATELIMIT_STORAGE_URI` or `REDIS_URL` is set (`AUTH_STATE_BACKEND=auto|redis`).
2. Otherwise the Postgres table `auth_state_entry` (created by migration `add_auth_state_entry`; entries expire by TTL and are purged opportunistically).

The store is authoritative and fails closed: if it cannot be reached, refresh, OAuth code exchange and login-lockout checks answer 503/deny instead of skipping the check. The generic per-route rate limiter degrades to the per-process limiter during an outage (never open). Writes use their own connection so they survive the request-level rollback for error responses.

### Mobile refresh tokens

Refresh tokens carry `jti` and a family id and are **single use**. Presenting an already-used refresh token is treated as theft: the whole family and its session are revoked and the client must sign in again. There is no replay grace window; a client that loses the response to a refresh call must re-authenticate. Logout revokes the family and the session; access tokens die with their session at the next request. Refresh tokens issued before this change (no family claim) still work and use their session id as family.

### Mobile Azure sign-in hand-off

The deep link no longer contains tokens. The app sends a PKCE `code_challenge` (`app_code_challenge`, S256) to `/login/azure`; the callback redirects to `humdatabank://oauth-success?code=...`; the app redeems `POST /api/mobile/v1/auth/oauth/exchange {code, code_verifier}` and receives the token pair in the response body. Codes are single use, expire after `MOBILE_OAUTH_CODE_TTL_SECONDS` (60), are stored hashed, and are bound to the challenge. Errors are returned as `humdatabank://oauth-error?error=invalid_request|app_update_required|temporarily_unavailable`.

App builds that predate the code flow send no challenge; while `MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK=true` (default, **deprecated**) they still receive tokens in the URL. Set it to `false` once the minimum supported app version sends the challenge.

### Abuse and enumeration controls

- Login lockout is shared across workers: 10 failed attempts per email in 15 minutes locks that address (web and mobile). Unknown and deactivated users run a dummy password hash so timing matches a real failure.
- Mobile login returns the same generic error for unknown, wrong password and deactivated accounts (`MOBILE_REVEAL_DEACTIVATED_ACCOUNT=true` restores the specific message). Web login still shows the deactivated notice.
- `POST /register` is limited to 5 per minute per IP (shared counter). An existing address gets the same neutral message as a new one (`REGISTRATION_REVEAL_EXISTING_EMAIL=true` restores the explicit message).
- `GET /register/check-email` returns 404 unless `REGISTRATION_EMAIL_CHECK_ENABLED=true`.
- Auth, password-reset, register and mobile-auth limits use the shared counters above, so scaling out does not multiply the allowance.

### Development-only shortcuts

Dev "Act as" needs `FLASK_CONFIG=development`, `DEBUG`, and a true loopback connection (no forwarding headers). It signs in as the seeded test users (plus `DEV_ACT_AS_EXTRA_EMAILS`) and as active accounts that have never completed a real sign-in (pre-added users). A `user_id` for someone who has already signed in, and is not on that allow list, is refused. Dev act-as itself is logged as `dev_act_as_login`, so using the picker does not count as registration. `DEBUG_SKIP_LOGIN` is now defined in `Config` (default false) and is fatal outside development + DEBUG. Plugin ZIP upload is controlled by `PLUGIN_UPLOAD_ENABLED` (default off in production/staging, on in development/testing).

### Deployment and upgrade notes

1. **Set `FLASK_CONFIG` explicitly** (`production` or `staging`). An unset value now means production, so a dev container that relied on the old implicit development default must set `FLASK_CONFIG=development`.
2. **Generate distinct secrets**: `MOBILE_JWT_SECRET` (flagged on System Configuration when missing, short, or equal to `SECRET_KEY`; startup continues) and `AI_JWT_SECRET` (recommended). Keep the legacy-accept flags on until tokens minted with `SECRET_KEY` have expired, then turn them off. Do not rotate `SECRET_KEY` and `MOBILE_JWT_SECRET` at the same moment. Set `ENABLE_SSH=true` if Azure portal SSH must stay available; when it is unset, System Configuration shows that container SSH is off.
3. **Proxy settings**: keep `TRUST_PROXY_HEADERS=true` behind a proxy and set `PROXY_FIX_X_FOR` to the real number of proxies (staging previously applied ProxyFix incorrectly). Verify in the admin session/device list that client IPs are the real client addresses, not the proxy.
4. **Run migrations** (`flask db upgrade`) before or with the deploy. Migration `add_auth_state_entry` only creates the new table and index and is safe to run ahead of the code. Without Redis the new code requires the table.
5. **Redis is recommended** for multi-worker or multi-instance deployments. Without it, the database backs the shared state (slightly higher latency on auth calls) and the app warns if limiter storage is per-process.
6. **Mobile app**: ship the build that sends `app_code_challenge` and calls `/auth/oauth/exchange`, then turn the legacy deep-link flag off. Existing sessions keep working across the deploy.
7. Refresh-token reuse now signs users out on every device sharing that token family; expect a small number of forced re-logins from clients that retry refresh calls.

### Decisions needed

- **Legacy deep link cut-off date** (`MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK`) and the minimum app version that forces the update.
- **Account lockout is keyed by email**, so an attacker can lock a known address for 15 minutes (denial of service). Alternatives (per email + IP, CAPTCHA, step-up) need a product decision.
- **Registration enumeration**: fully closing it requires email verification before an account is created; the neutral response only hides it partially (timing is equalised).
- **Absolute session lifetime**: sessions are bounded by inactivity and the 10 h cookie lifetime; a hard per-session maximum and re-authentication for sensitive actions are not added.
- **Refresh replay grace window** for flaky mobile networks is intentionally absent; adding one weakens theft detection.

## API key security

- Use the Authorization header: `Authorization: Bearer YOUR_API_KEY`
- API keys are database-managed (Admin > API Keys). Create and rotate keys via the admin interface.
- Every key holds explicit **capabilities** (form data, submissions, templates, personal data, reference data, ...) and optionally a data scope by template/country. A key can only call routes whose capability it holds; unknown or missing permissions grant nothing. Give each integration the smallest set that works. See [API keys and permissions](api-keys-and-permissions.md).
- `?api_key=` in the URL is refused unless the key explicitly allows it (not available with personal-data capabilities). Never ship a data-capable key in browser code.
- Keys created before the capability model were migrated as "legacy full access" so integrations kept working; review them and tighten, then set `API_KEY_ALLOW_LEGACY_FULL_ACCESS=false`.
- The env `MOBILE_APP_API_KEY` is deprecated, header-only and limited to `MOBILE_APP_API_KEY_CAPABILITIES`.

## File upload security

File uploads are validated for:

- File type (extension and MIME type via magic bytes)
- File size limits
- Path traversal prevention
- Dangerous file extensions are blocked

## Plugin security

> **WARNING:** Plugins execute as full-privilege Python modules (`importlib.exec_module`) within the host application process. There is no OS-level sandbox, container, or restricted execution environment. Only install plugins from trusted sources. A malicious plugin has full access to the database, file system, network, and application secrets.

## Rate limiting

- Authentication, password-reset, register and mobile-auth endpoints: 5 requests/minute per client IP, counted in the shared auth-state store (see above)
- API endpoints: 60 requests/minute per IP
- Plugin management: 5 requests/minute per IP

## CORS

- **Production:** Set `CORS_ALLOWED_ORIGINS` with a comma-separated list of allowed origins  
  Example: `CORS_ALLOWED_ORIGINS=https://app.example.com,https://www.example.com`
- **Development:** Defaults to localhost origins (localhost:5000, localhost:3000)
- If `CORS_ALLOWED_ORIGINS` is not set in production, CORS is disabled by default

## Test user credentials (development only)

- Set `TEST_SYS_MANAGER_PASSWORD` for sys-manager@example.com
- Set `TEST_ADMIN_PASSWORD` for test_admin@example.com
- Set `TEST_FOCAL_PASSWORD` for test_focal@example.com

If not set, secure random passwords are generated. **Test credentials are blocked in production.**

## Security headers and CSP

`app/middleware/security_headers.py` sets, on every response: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, an expanded `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin-allow-popups`, `X-Permitted-Cross-Domain-Policies: none`, `X-XSS-Protection: 0`, and (HTML) `Cross-Origin-Resource-Policy: same-origin`. The CSP is nonce-based for scripts and adds `object-src 'none'`, `base-uri 'self'`, `form-action 'self'` and `frame-ancestors 'none'`.

| Variable | Effect |
|---|---|
| `CSP_STRICT_MODE` | Enables the stricter candidate policy (roll out via report-only first). |
| `CSP_IMG_SRC_EXTRA` | Extra `img-src` origins (space/comma separated). |
| `CSP_CONNECT_SRC_EXTRA` | Extra `connect-src` origins. |

`style-src` still allows `'unsafe-inline'` and `img-src` allows `https:` (templates rely on inline styles and remote map/tile images); tightening those is a follow-up.

## Logging redaction and error correlation

One redaction policy (`app/utils/logging_security.py`) is used by API usage tracking, activity form-data storage, security events and access logs. Errors carry an `X-Request-ID` and production error bodies are generic. See [Logging & health](../runbooks/observability/logging-and-health.md).

## Seeding guard

`init_data.py`, `app/seeding.py` and the `seed-test-data` CLI command are an allowlist, not a denylist: they run only when `FLASK_CONFIG` is exactly `development` (unset, unknown or typo'd values fail closed) **and** the database host is local (loopback, `host.docker.internal`, a unix socket, or a host listed in `SEED_ALLOWED_DB_HOSTS`). A restored production dump on a remote server cannot be seeded. The `create-admin` command asks for confirmation and validates password strength. There are no hardcoded default passwords any more: `test123` was removed and is no longer allow-listed in the secret scanner. Set the `TEST_*_PASSWORD` variables or let random ones be generated.

## Container SSH

sshd in the image is opt-in (`ENABLE_SSH=true`) and hardened; see [Container SSH access](../runbooks/operations/container-ssh-access.md). Committed-artifact clean-up: [history purge & rotation](../runbooks/security/committed-artifacts-history-purge.md).

## Deployment security checklist

- [ ] `SECRET_KEY` is set and is a strong random value (32+ characters)
- [ ] `DATABASE_URL` uses strong credentials
- [ ] `API_KEY` is set and kept secret
- [ ] Test credentials are disabled in production (enforced by code)
- [ ] HTTPS is enabled in production
- [ ] Security headers are enabled (`SECURITY_HEADERS_ENABLED=true`)
- [ ] File upload size limits are configured appropriately
- [ ] Rate limiting is enabled and configured
- [ ] CORS restricted to specific origins
- [ ] Environment variables are not committed to version control
- [ ] `ENABLE_SSH` is unset except during a break-glass session
- [ ] `FLASK_CONFIG=production` (image default; an unset value is treated as production)
- [ ] `MOBILE_JWT_SECRET` and `AI_JWT_SECRET` are set, distinct from `SECRET_KEY` and from each other
- [ ] `PROXY_FIX_X_FOR` matches the real number of proxies; `TRUST_PROXY_HEADERS=true` behind a proxy
- [ ] Migration `add_auth_state_entry` applied (or Redis configured) so refresh/lockout state is shared across workers
- [ ] `PLUGIN_UPLOAD_ENABLED` unset/false unless plugin installs are intended
- [ ] Legacy flags (`MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY`, `AI_JWT_ACCEPT_LEGACY_SECRET_KEY`, `MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK`) turned off once clients have migrated

## Pre–penetration test checklist (Backoffice)

Use this before handing staging or production to testers. Adjust items if the engagement scope excludes APIs, AI, or the public Website.

### Environment and runtime

- [ ] **`FLASK_CONFIG`** matches the target environment (`staging` or `production` for real tests; never `development` on internet-facing targets unless explicitly in scope).
- [ ] **`SECRET_KEY`** is set to a strong random value and is not reused from dev.
- [ ] **`DATABASE_URL`** (and any backup restore) uses credentials appropriate for a test window; testers only get accounts you intend.
- [ ] **`CLIENT_CONSOLE_LOGGING`** is unset or **`false`** so verbose browser output is suppressed on pages that load the client console guard (`components/_client_console_guard.html`). The guard no-ops native `console.log` / `debug` / `info` / `warn` / `group*` / etc., and Jinja templates use gated helpers (`window.__clientLog`, `window.__clientWarn`, …) so those calls respect the same flag even in development. **`console.error`** is still used for genuine failure paths (and is not silenced by the guard).
- [ ] **`DEBUG_SKIP_LOGIN`** is **`false`** (or unset). Do not enable auto-login shortcuts on assessed environments.

### Transport, cookies, and headers

- [ ] **HTTPS** is enforced end-to-end; **`SESSION_COOKIE_SECURE`** is on in production-like configs.
- [ ] **`SECURITY_HEADERS_ENABLED=true`** (default) and CSP behaves as expected on key admin pages (no unexpected inline-script violations in the browser console for normal flows).

### API and CORS

- [ ] **`CORS_ALLOWED_ORIGINS`** lists only origins that should call the Backoffice API in that environment.
- [ ] **API keys** for third-party or internal automation are rotated after the test if they were shared with testers or used on a shared staging URL.

### Scope pack for the testers

- [ ] **Written scope:** hostnames, IP allowlists (if any), in-scope roles (e.g. focal vs admin), and **out-of-scope** actions (destructive bulk delete, DoS, social engineering, production data exfiltration beyond agreed limits).
- [ ] **Dedicated test accounts** with the minimum roles needed; separate accounts for vertical privilege checks if requested.
- [ ] **Contact** for false positives, critical findings, and emergency stop (disable test accounts or take staging offline).

### Monitoring and response

- [ ] **Application and access logs** are retained and someone is assigned to triage alerts during the test window.
- [ ] **Backup / rollback** for staging is understood if testers are allowed destructive tests.

### What this checklist does not replace

Penetration testing still covers authentication, authorization on every sensitive route, injection, CSRF coverage, file uploads, dependency CVEs, and (if in scope) AI/RAG and WebSocket behavior. The client console guard and template `__client*` helpers reduce noisy **browser console** disclosure; they do not fix server-side or design flaws. To add verbose logging in new inline scripts, use `window.__clientLog` / `window.__clientWarn` (not raw `console.log` / `console.warn`) so behavior stays consistent. Regenerate gated templates with `python scripts/ci/gate_template_console_calls.py` after bulk edits if needed.
