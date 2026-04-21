# Security

Security practices and configuration for the Backoffice.

> **Recent Security Updates (2024):** All critical and high-priority security issues have been resolved. See the `docs/` directory and security-related runbooks for details.

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

## API key security

- Use the Authorization header: `Authorization: Bearer YOUR_API_KEY`
- API keys are database-managed (Admin > API Keys). Create and rotate keys via the admin interface.

## File upload security

File uploads are validated for:

- File type (extension and MIME type via magic bytes)
- File size limits
- Path traversal prevention
- Dangerous file extensions are blocked

## Plugin security

> **WARNING:** Plugins execute as full-privilege Python modules (`importlib.exec_module`) within the host application process. There is no OS-level sandbox, container, or restricted execution environment. Only install plugins from trusted sources. A malicious plugin has full access to the database, file system, network, and application secrets.

## Rate limiting

- Authentication endpoints: 5 requests/minute per IP
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

## Debug endpoints

- `/dbinfo` requires admin authentication (admin or system_manager role) and localhost-only access in production; returns 404 when disabled.
- Set `ENABLE_DBINFO=false` to disable.

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

## Pre–penetration test checklist (Backoffice)

Use this before handing staging or production to testers. Adjust items if the engagement scope excludes APIs, AI, or the public Website.

### Environment and runtime

- [ ] **`FLASK_CONFIG`** matches the target environment (`staging` or `production` for real tests; never `development` on internet-facing targets unless explicitly in scope).
- [ ] **`SECRET_KEY`** is set to a strong random value and is not reused from dev.
- [ ] **`DATABASE_URL`** (and any backup restore) uses credentials appropriate for a test window; testers only get accounts you intend.
- [ ] **`CLIENT_CONSOLE_LOGGING`** is unset or **`false`** so verbose browser output is suppressed on pages that load the client console guard (`components/_client_console_guard.html`). The guard no-ops native `console.log` / `debug` / `info` / `warn` / `group*` / etc., and Jinja templates use gated helpers (`window.__clientLog`, `window.__clientWarn`, …) so those calls respect the same flag even in development. **`console.error`** is still used for genuine failure paths (and is not silenced by the guard).
- [ ] **`DEBUG_SKIP_LOGIN`** is **`false`** (or unset). Do not enable auto-login shortcuts on assessed environments.
- [ ] **`ENABLE_DBINFO=false`** (or unset in a way that keeps `/dbinfo` disabled for non-local production use), unless the test plan explicitly includes it.

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

Penetration testing still covers authentication, authorization on every sensitive route, injection, CSRF coverage, file uploads, dependency CVEs, and (if in scope) AI/RAG and WebSocket behavior. The client console guard and template `__client*` helpers reduce noisy **browser console** disclosure; they do not fix server-side or design flaws. To add verbose logging in new inline scripts, use `window.__clientLog` / `window.__clientWarn` (not raw `console.log` / `console.warn`) so behavior stays consistent. Regenerate gated templates with `python scripts/gate_template_console_calls.py` after bulk edits if needed.
