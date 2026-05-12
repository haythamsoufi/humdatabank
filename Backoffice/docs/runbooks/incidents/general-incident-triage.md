# General Incident Triage (Backoffice)

Use this playbook when behaviour breaks in staging or production and the cause is not immediately obvious. Work through the layers in order — most incidents resolve at layer 1 or 2.

---

## 1. Classify Where the Failure Happens

```
User / Browser  →  CDN / WAF (Azure)  →  App (Flask workers)  →  Database  →  Integrations (OpenAI, LibreTranslate, …)
```

| Symptoms | Likely layer | Go to |
|----------|-------------|-------|
| `403 Forbidden`, `Server: Microsoft-Azure-Application-Gateway*` in response headers | Edge WAF blocking body or path | [WAF 403 guide](waf-403-form-payload-refactor-guide.md) |
| 502 / 504 at gateway, site completely unreachable | App stopped / slot misconfigured / outbound block | [Azure App Service](../deployment/azure-app-service.md), [Logging & health](../observability/logging-and-health.md) |
| 500 from Flask; `error_id` in API response | Application exception in code | Application logs — tail and grep for the `error_id` |
| `no such column`, `undefined column`, schema errors | Migration not applied or multiple heads | [Flask-Migrate runbook](../data/flask-migrate-and-pgvector.md) |
| Sessions drop; CSRF errors after deploy | `SECRET_KEY` changed or cookie domain mismatch | [Session management](../sessions/session-management.md), [Security setup](../../setup/security.md) |
| AI chat empty, "no provider configured" | Missing API keys or wrong model name | [AI configuration](../../setup/ai-configuration.md), [AI health endpoint](../observability/logging-and-health.md#2-health-endpoints) |
| Form auto-save fails silently | WAF blocking save endpoint or JS error | [WAF 403 guide](waf-403-form-payload-refactor-guide.md), browser console |
| Excel export returns error | Server timeout or memory exhaustion | Logs — check for OOM; try smaller export (per-country) |
| Translation not appearing | LibreTranslate unreachable or language disabled | [Integrations overview](../integrations/overview.md) |
| Public-facing indicators/map data stale | Public assignment not published or downstream cache lag | Admin → Public Assignments → confirm published status; allow time for caches to refresh |

---

## 2. Minimum Information to Capture

Before investigating, collect:

- **UTC time window** and timezone of reporters.
- **URL path + HTTP method** (e.g. `POST /admin/settings`).
- **HTTP status code** the user received.
- **User role** (guest / focal point / admin / system manager).
- **Browser version** (and any client-reported build identifier from support tickets).
- **Request / correlation ID** if your hosting layer injects one (check response headers).
- **Whether the same action succeeds** on another environment (staging/local) or for another user.
- **Recent changes**: last deployment date, config changes, new migrations.

---

## 3. Safe First Checks (Read-Only)

Do these before making any changes:

### 3a. Tail application logs
```bash
az webapp log tail --name <webapp-name> --resource-group <rg-name>
```
Filter the output for `ERROR`, `CRITICAL`, and the time window of the incident.

### 3b. Check AI health endpoint
```
GET https://<app-url>/api/ai/v2/health
```
If `status` is not `ok`, the AI subsystem is degraded. Check provider keys.

### 3c. Confirm migration heads
```bash
python -m flask db heads
```
Must return exactly one revision. Multiple heads = migration graph branched; do not run `db upgrade`.

### 3d. Compare recent config changes
App Service configuration changes (env vars) often explain regressions faster than reading code diffs. Check the Azure App Service "Environment variables" history or deployment log for recent changes.

### 3e. Check RBAC startup warnings
Grep the startup logs for:
```
WARNING  rbac_audit
```
A newly deployed admin route missing its guard can cause unexpected permission behaviour.

---

## 4. Scenario-Specific Playbooks

### Scenario A: All users cannot log in

1. Confirm the app is running: `GET /` — if 502, the app is down.
2. Check startup logs for Python exceptions during app initialization.
3. If `SECRET_KEY` was recently rotated: all existing sessions are invalid — expected. Users must log in again.
4. If `DATABASE_URL` was changed: app may be pointing at empty/wrong DB.

### Scenario B: A specific user cannot access a page

1. Check the user's role and country assignments (Admin → User Management).
2. Check logs for `403` or RBAC-related messages for that user's requests.
3. Confirm the route has the correct RBAC guard (not a new route lacking `@admin_required`).
4. If the user is a focal point: confirm the assignment for their country is open.

### Scenario C: Form submissions failing

1. Open browser DevTools → Network tab → reproduce the save action → inspect the failing request.
2. If `403` from the server with `Microsoft-Azure-Application-Gateway` in headers: WAF block — see [WAF 403 guide](waf-403-form-payload-refactor-guide.md).
3. If `500`: tail application logs for the corresponding `ERROR` traceback.
4. If `CSRF` error: session expired mid-form (user left browser open too long). User must refresh and re-enter.
5. If no network request at all: JS error — check browser console.

### Scenario D: AI chat not working

1. `GET /api/ai/v2/health` → check which provider is unavailable.
2. If provider unavailable: verify API key in App Service env vars; test the key directly with provider's API.
3. If `agent_available: false`: check `AI_AGENT_ENABLED=true` in config.
4. If chat works but responses are poor: see [RAG quality](../ai/rag-quality-and-embeddings.md).
5. If costs are spiking: see [Chat cost drivers](../ai/ai-chat-cost-drivers.md).

### Scenario E: Database/migration issues

1. `python -m flask db heads` → if not one head, **stop all migration activity**.
2. `python -m flask db current` → confirm which revision is applied.
3. If schema errors appear: the migration was not run after deployment. Run `python -m flask db upgrade` (confirm single head first).
4. If a migration failed mid-apply: restore from the pre-deploy snapshot — do not attempt `db downgrade` without a recovery plan.

---

## 5. Escalation

### Infrastructure / WAF / firewall
Include in escalation ticket:
- WAF rule ID (`ruleId` from WAF logs)
- Matched field name (`matchVariableName`)
- Full URI and HTTP method
- Time window (UTC)
- Business justification for the content being legitimate

Request: **targeted path + argument exclusion only** — not global rule disablement.

### Security / RBAC regression
Never remove guards without reviewing [RBAC audit exemptions policy](../security/rbac-admin-route-audit-exemptions.md) and getting a second reviewer.

### Database corruption / migration failure
1. Immediately take a snapshot of the current DB state.
2. Do not run further migrations or schema-touching code.
3. Engage the development team with: current revision (`flask db current`), heads output, and the migration error message.
4. **If recovery involves restoring Azure PostgreSQL Flexible Server from backup:** restoring usually creates a **new** server behind **private networking** — engage **infrastructure** early to **recreate private endpoints and DNS**; then update `DATABASE_URL`. See [Backup & restore](../data/backup-and-restore.md) §2.

---

## 6. Post-Incident

After resolving a production incident:

1. Confirm the fix is stable (monitor logs for 30+ minutes).
2. Write a brief incident summary: what broke, why, how it was fixed, how to prevent recurrence.
3. If a WAF exclusion was added: update the [WAF 403 guide](waf-403-form-payload-refactor-guide.md) with the specific rule/field/endpoint.
4. If a RBAC gap was found: update [RBAC audit exemptions](../security/rbac-admin-route-audit-exemptions.md).
5. Update this runbook if you discovered a scenario that should be captured here.
