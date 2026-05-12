# Engineering & Operations Runbooks — Backoffice

> **Who this is for:** The IFRC App team taking over maintenance and development of the Humanitarian Databank Backoffice. Whether you are triaging a live incident, releasing a feature, or training a new developer — start here.

---

## How to Navigate

| I need to… | Go to |
|---|---|
| Triage a production incident fast | [General incident triage](incidents/general-incident-triage.md) |
| Add a new user or change their role | [User & role management](operations/user-and-role-management.md) |
| Create or manage a form | [Form operations](operations/form-operations.md) |
| Run routine maintenance tasks | [Routine maintenance](operations/routine-maintenance.md) |
| Deploy a code change or release | [Release process](development/release-process.md) + [Azure App Service](deployment/azure-app-service.md) |
| Understand application logs | [Logging & health](observability/logging-and-health.md) |
| Investigate a WAF 403 in production | [WAF 403 guide](incidents/waf-403-form-payload-refactor-guide.md) |
| Manage database migrations safely | [Flask-Migrate & pgvector](data/flask-migrate-and-pgvector.md) |
| Restore from backup | [Backup & restore](data/backup-and-restore.md) |
| Understand the AI chat system | [AI system docs](ai/) |
| Set up a new developer locally | **[Developer handbook](../../../docs/DEVELOPER-HANDBOOK.md)** — Quickstarts · [Backoffice README](../../README.md) · [Documentation index](../../docs/README.md) |

---

## Operations (Day-to-Day)

These runbooks cover the recurring tasks the IFRC ops team performs without needing a developer.

| Runbook | When to use |
|---------|-------------|
| [User & role management](operations/user-and-role-management.md) | Creating accounts, assigning roles and countries, approving self-service access requests, deactivating leavers |
| [Form operations](operations/form-operations.md) | Building templates, assigning forms to countries, reviewing and exporting submissions |
| [Routine maintenance](operations/routine-maintenance.md) | Weekly/monthly checks: session cleanup, DB health, AI trace review, translation sync |

---

## Incidents

| Runbook | When to use |
|---------|-------------|
| [General incident triage](incidents/general-incident-triage.md) | First stop for any unexplained production failure |
| [WAF 403 — form payloads](incidents/waf-403-form-payload-refactor-guide.md) | Azure Application Gateway blocking large admin/form POST bodies |

---

## Deployment & Platform

| Runbook | When to use |
|---------|-------------|
| [Azure App Service](deployment/azure-app-service.md) | Deploy order, migrations, slots, rollback, Redis/workers |
| [Release process](development/release-process.md) | Branch strategy, pre-release checklist, migration safety, CSS rebuild, go/no-go |

---

## Observability

| Runbook | When to use |
|---------|-------------|
| [Logging & health](observability/logging-and-health.md) | Streaming logs, health endpoints, startup diagnostics, reading errors |

---

## Data & Storage

| Runbook | When to use |
|---------|-------------|
| [Flask-Migrate & pgvector](data/flask-migrate-and-pgvector.md) | Schema changes, migration single-head policy, pgvector / AI embedding caveats |
| [Backup & restore](data/backup-and-restore.md) | PostgreSQL dumps, file storage backups, DR checklist (includes **Azure Flexible Server restore → infra must recreate private endpoints**) |

---

## Security

| Runbook | When to use |
|---------|-------------|
| [RBAC audit exemptions](security/rbac-admin-route-audit-exemptions.md) | When adding or reviewing admin routes exempt from the startup RBAC guard |
| [Security setup](../setup/security.md) | Secrets, CORS, rate limiting, CSRF baseline |

---

## Sessions

| Runbook | When to use |
|---------|-------------|
| [Session management & presence](sessions/session-management.md) | CLI cleanup, cookie security, multi-worker affinity, presence heartbeats |

---

## Forms & Submissions

| Runbook | When to use |
|---------|-------------|
| [Submissions & Excel](forms-data/submissions-and-excel-notes.md) | AES naming reference, VERBOSE_FORM_DEBUG, Excel import/export triage |

---

## Development Toolchain

| Runbook | When to use |
|---------|-------------|
| [Release process](development/release-process.md) | Pre-release checklist, branch/migration safety, CSS rebuild, rollback |
| [Tailwind & template safety](development/tailwind-and-template-safety.md) | CSS rebuild, CSP, sanitization, CI console guards |
| [`scripts/` catalogue](development/repo-maintenance-scripts.md) | DB migration checker, AI trace exporters, console guard tooling |

---

## Integrations

| Runbook | When to use |
|---------|-------------|
| [Overview](integrations/overview.md) | LibreTranslate, Azure Files, AI providers — failure modes and links |

---

## AI System

| Runbook | When to use |
|---------|-------------|
| [Upgrade plan status](ai/ai-upgrade-plan-status.md) | Historical Phase 5 completion anchors |
| [Chat cost drivers](ai/ai-chat-cost-drivers.md) | Why token spend spikes; env knobs to tune |
| [RAG quality & embeddings](ai/rag-quality-and-embeddings.md) | Retrieval tuning, rerank/diversity flags |
| [Agent development map](ai/ai-agent-development-map.md) | Where new agent behaviour belongs in code |
| [Indicator resolution](ai/indicator-resolution.md) | Vector + optional LLM disambiguation vs keyword fallback |
| [AI detailed config](../setup/ai-configuration.md) | All AI env vars, provider keys, model selection |

---

## UI Design System

Button styles use semantic CSS variables in `app/static/css/theme.css`, `.btn` rules in `components.css`, and header actions in `executive-header.css`; Tailwind colour remap lives in `assets/tailwind.config.js`. After template/class changes run `npm run build:css` in `Backoffice/`. Full semantics table and markup patterns: [Tailwind & template safety — §5 Button design system](development/tailwind-and-template-safety.md#5-button-design-system-backoffice).

---

## Quick Reference — Most Common Tasks

### Create a new user
See [User & role management](operations/user-and-role-management.md) → Creating a user.

### Assign a user to a country
See [User & role management](operations/user-and-role-management.md) → Country assignments.

### Approve a pending access request
See [User & role management](operations/user-and-role-management.md) → Self-service access requests.

### Run the session cleanup
```bash
cd Backoffice
python -m flask cleanup-sessions
```

### Check migration heads before any schema change
```bash
cd Backoffice
python -m flask db heads
# Must return exactly ONE head. If not, resolve before proceeding.
```

### Stream production logs
```bash
az webapp log tail --name <webapp-name> --resource-group <rg-name>
```

### Check AI system health
```
GET /api/ai/v2/health
```

### Rebuild CSS after template changes
```bash
cd Backoffice
npm run build:css
```
