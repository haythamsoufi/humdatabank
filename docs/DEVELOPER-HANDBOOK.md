# Developer handbook

**Tracked reference** for this repository: architecture, local setup, conventions, AI/mobile pointers, and “where to change things”. Pair with **[`CONTRIBUTING.md`](../CONTRIBUTING.md)** (workflow, CI) and **[`Backoffice/docs/runbooks/README.md`](../Backoffice/docs/runbooks/README.md)** (operations).

Some tooling may sync from this file into Editor assistant configs locally — edits belong **here** so clones stay consistent.

---

*(Previously mirrored assistant-facing wording below — content applies to all contributors.)*

## Project Overview

The Humanitarian Databank is a comprehensive humanitarian data management and analytics ecosystem built with Flask backend, Next.js frontend, and Flutter mobile app. It manages forms, indicators, country data, translations, and provides public-facing data visualization across backoffice, website, and mobile app components.

## Architecture

### Backoffice (Flask Application)
- **Location**: `Backoffice/`
- **Framework**: Flask with SQLAlchemy ORM, Flask-Login, Flask-Migrate
- **Database**: PostgreSQL (required for all environments — development, staging, production, testing)
- **Key Features**: Multilingual support (7 languages), form builder, indicator management, analytics, API endpoints

### Website (Next.js Application)  
- **Location**: `Website/`
- **Framework**: Next.js with React, TailwindCSS
- **Features**: Public portal, data visualization, interactive maps, multilingual support

### Mobile App (Flutter)
- **Location**: `MobileApp/`
- **Notes**: iOS builds use CocoaPods; **`Podfile.lock` is maintained via macOS or the “Regenerate iOS Podfile.lock” GitHub Action** if you do not have a Mac (see Local Development Quickstart).
- **Agent architecture (keep consistent)**:
  - **Dependency injection**: `setupServiceLocator()` in `MobileApp/lib/main.dart` registers services (GetIt). Prefer **`sl<ApiService>()`** from `MobileApp/lib/di/service_locator.dart` over calling `ApiService()` directly so tests can override registrations.
  - **HTTP**: Legacy `ApiService` vs `DioClient` — new endpoints should prefer **`DioClient`** (`MobileApp/lib/services/dio_client.dart`); see comments there.
  - **Mobile JSON envelopes**: Use **`MobileApp/lib/utils/mobile_api_json.dart`** for `success` / `data` parsing aligned with Backoffice `app/utils/mobile_responses.py` — avoid ad-hoc `jsonDecode` + `['data']` copy-paste in new code.
  - **Loading / error UI**: Reuse **`AppLoadingIndicator`**, **`AppErrorState`**, **`AsyncBody`** (`MobileApp/lib/widgets/`), and optional **`MobileScreenScaffold`** for pushed routes — do not hand-roll full-screen spinners/error columns for each screen.
  - **Navigation**: The app uses **Navigator 1.0** + `AppRoutes` / `AppRouter` (`MobileApp/lib/config/`). **`go_router`** config exists for a future migration — **do not register the same path in both** until the app switches to `MaterialApp.router` (see **`MobileApp/README.md`** → Architecture notes).
  - **Tab shell**: **`MainNavigationScreen`** owns the bottom nav + page view; **child tabs supply their own `AppBar`** (outer scaffold uses `primary: false`). Do not add a second outer `Scaffold` around tab roots.
  - **Admin screen-view analytics**: Prefer **`AdminScreenViewLoggingMixin`** (`MobileApp/lib/utils/admin_screen_view_logging_mixin.dart`) instead of duplicating `scheduleMobileScreenViewForRoutePath` per screen.
  - **Provider async boilerplate**: **`AsyncOperationMixin`** (`MobileApp/lib/providers/shared/async_operation_mixin.dart`) for load/error/notify patterns where appropriate.
  - **Longer reference**: `MobileApp/README.md` (Architecture notes) when expanding mobile conventions.

## Local Development Quickstart

### Prerequisites
- **Python**: 3.x (use a virtual environment)
- **Node.js**: 18+ recommended (for Backoffice CSS build + Website)
- **Database**: PostgreSQL is required (no SQLite fallback). Use a local PostgreSQL instance for development (see `env.quickstart.example`).

### Backoffice (Flask) quickstart
```bash
cd Backoffice

# 1) Environment variables
# Copy one of:
# - env.quickstart.example -> .env   (fast local defaults, includes test passwords)
# - env.example -> .env             (full reference)

# 2) Python dependencies
pip install -r requirements.txt

# 3) Database
python -m flask db upgrade
python -m flask rbac seed
python -m flask seed-test-data

# 4) Run
python run.py
```

### Backoffice CSS (Tailwind) quickstart
```bash
cd Backoffice
npm install
npm run watch:css
```

**Important — rebuild CSS after template/JS class changes:** Backoffice Tailwind compiles to `Backoffice/app/static/css/output.css`. If you add or change utility classes in Jinja templates (e.g. `app/templates/`) or in inline scripts there, **run `npm run build:css`** (or keep **`npm run watch:css`** running) so the bundle is regenerated. Otherwise new classes—especially **arbitrary values** like `h-[1em]`—may be missing from `output.css`, and UI changes will not appear until you rebuild (a full page refresh alone is not enough). This is easy to mistake for a bug in HTML/JS when the issue is a stale CSS artifact.

### Website (Next.js) quickstart
```bash
cd Website
npm install
npm run dev
```

### Mobile App (Flutter)
- **Location**: `MobileApp/` (see `MobileApp/pubspec.yaml`, **`MobileApp/README.md`** for architecture and tooling notes).
- **iOS `Podfile.lock` without a Mac**: CocoaPods (`pod install`) only runs meaningfully on **macOS** with Xcode. **Windows/Linux cannot regenerate `MobileApp/ios/Podfile.lock` locally.** When the lockfile must be updated (e.g. after bumping `firebase_core` / `firebase_messaging` or other iOS pods, or when CI reports a CocoaPods version conflict), use the GitHub Action **“Regenerate iOS Podfile.lock”** (`.github/workflows/ios-regenerate-podfile-lock.yml`): **Actions → Regenerate iOS Podfile.lock → Run workflow**, then either download the **`ios-podfile-lock`** artifact and replace `MobileApp/ios/Podfile.lock` in a commit, or enable **Open a pull request** on the workflow to let the bot open a PR. Until the lock is regenerated, keep **`pubspec.yaml` Firebase (and related) versions aligned** with the committed `Podfile.lock` (see comments in `MobileApp/pubspec.yaml`).

### Windows / PowerShell note (FLASK_APP)
If `flask` commands complain about `FLASK_APP`, set it for your shell session:

```powershell
$env:FLASK_APP = "run.py"
```

**One Flask on port 5000.** Windows can bind two `python run.py` processes to `127.0.0.1:5000` at once, which makes assignment/PDF requests look stuck. Start only one server — a second `run.py` now exits with an error instead of sharing the port. To stop a forgotten copy: `netstat -ano | findstr :5000` then `taskkill /F /PID <pid>`. For WeasyPrint/P&B exports, `FLASK_USE_RELOADER=false` avoids mid-request restarts.

## Common Development Commands

### Backoffice Development
```bash
# Navigate to Backoffice directory
cd Backoffice

# Install dependencies
pip install -r requirements.txt

# Run development server
python run.py

# Database migrations
python -m flask db migrate -m "migration message"
python -m flask db upgrade

# Create admin user (interactive prompt)
python -m flask create-admin

# Seed test users (System Manager, Admin, Focal Point)
python -m flask seed-test-data

# Session management
python -m flask cleanup-sessions
python -m flask show-all-sessions

# Build CSS (TailwindCSS)
npm run build:css
npm run watch:css
```

### Website Development
```bash
# Navigate to Website directory
cd Website

# Install dependencies
npm install

# Development server
npm run dev

# Safe development (with error handling)
npm run dev:safe

# Build for production
npm run build

# Linting
npm run lint
```

### Playwright MCP (browser testing)
- **Project config:** `.cursor/mcp.json` runs with `--isolated` (fresh browser context each session — no stale cookies, HTTP cache, or service workers) and `--output-dir` `.playwright-mcp/screenshots/` (parent `.playwright-mcp/` is gitignored). Screenshots and related artifacts should land there, not in the repository root.
- **Dev login:** Backoffice at `http://127.0.0.1:5000/login` — yellow **Act as (dev only)** preset buttons when `DEBUG=true` and request is loopback. See `.cursor/rules/playwright-browser-testing.mdc`.
- **Tool calls:** Use **relative** screenshot filenames only. An absolute path in the filename can bypass `--output-dir` and write under that path instead.
- **Global MCP:** This repo owns Playwright MCP in `.cursor/mcp.json`. Remove or disable any user-level `playwright` entry in Cursor MCP settings — duplicates launch a second Chromium (often with mismatched versions) and can show a `--no-sandbox` stability banner. Pin `@playwright/mcp@0.0.78` — do not use `@latest` while 0.0.79 depends on `playwright-core@1.63.0-alpha-2026-08-05`, which crashes on startup (`Cannot read properties of undefined (reading 'dir')`) because Registry expects `chromium-tip-of-tree-headless-shell` and `browsers.json` no longer lists it. If Cursor still launches the broken cache, delete `%LOCALAPPDATA%\npm-cache\_npx\9833c18b2d85bc59` and reload MCP.

## Key Application Structure

### Backoffice Core Components

#### Models (`Backoffice/app/models/models.py`)
- **FormItem**: Unified model for indicators, questions, and document fields
- **User**: Authentication with role-based access and country assignments
- **Country**: Country data with multilingual support
- **FormTemplate**: Dynamic form templates with sections
- **IndicatorBank**: Centralized indicator repository

#### Routes (`Backoffice/app/routes/`)
- `forms.py` - Form management and data entry
- `forms_api.py` - REST API for forms
- `public.py` - Public-facing endpoints
- `api.py` - Main API endpoints
- `analytics.py` - Analytics and reporting
- `admin/` - Modular administrative interface:
  - `__init__.py` - Main admin dashboard and blueprint registration
  - `form_builder.py` - Form template and section management (40+ routes)
  - `user_management.py` - User CRUD operations (4 routes)
  - `assignment_management.py` - Form and public assignments (25+ routes)
  - `content_management.py` - Resources, publications, documents (20+ routes)
  - `system_admin.py` - Countries, sectors, indicator bank (30+ routes)
  - `analytics.py` - Dashboard APIs and reporting (13+ routes)
  - `utilities.py` - Import/export, translations, sessions (20+ routes)
  - `shared.py` - Common decorators and utilities

#### Services (`Backoffice/app/services/`)
- Form data processing and validation
- Public form management
- Excel import/export functionality

#### Utilities (`Backoffice/app/utils/`)
- `form_processing.py` - Form logic and calculations
- `form_localization.py` - Translation management
- `excel_service.py` - Excel operations
- `user_analytics.py` - Session and user tracking

### Website Components

#### Pages (`Website/pages/`)
- `index.js` - Landing page with country selection
- `indicator-bank.js` - Indicator browsing interface
- `dataviz.js` - Data visualization dashboard
- `disaggregation-analysis.js` - Analytics interface

#### Components (`Website/components/`)
- `InteractiveWorldMap.js` - Leaflet-based world map
- `LanguageSwitcher.js` - Multilingual support
- Layout components in `layout/`

## Database Architecture

### Form submission data tables

Entity answers are stored in three data tables, all keyed by either `assignment_entity_status_id` (authenticated entity submission) or `public_submission_id` (public URL submission):

| Table | Purpose |
|-------|---------|
| `form_data` | Standard form item answers (indicators, questions, matrix, plugins) |
| `dynamic_indicator_data` | Focal-point-selected indicators in dynamic sections |
| `dynamic_section_context` | Binds a dynamic section to a stable external context per submission (e.g. emergency appeal **code** for `[EO1]`/`[EO2]`/`[EO3]` sections); see [Emergency section binding](../Backoffice/plugins/emergency_operations/DYNAMIC_SECTION_BINDING.md) |
| `repeat_group_instance` + `repeat_group_data` | Repeat section row registry and per-row field answers |

**Dual-nullable-FK parent pattern (F10):** `form_data`, `dynamic_indicator_data`, and `repeat_group_instance` each have both parent FK columns nullable at the column level, with a PostgreSQL `CHECK` constraint enforcing that **at least one** is set. This is the canonical extension point if a third submission context is ever added (add another nullable FK + widen the check constraint). Do not introduce a different parent-link pattern for new submission types.

**Shared data columns:** `value`, `disagg_data`, `data_not_available`, `not_applicable`, `numeric_value`, and `submitted_at` are defined once on `DataEntryMixin` in [`Backoffice/app/models/forms.py`](Backoffice/app/models/forms.py) and inherited by the three data-entry models.

**Value / disaggregation invariant (F7):** When `disagg_data` is set for standard disaggregation (`mode` + `values` keys), `value` is a denormalized string cache of the numeric total. Matrix and plugin payloads may use `disagg_data` without `mode`/`values`. Always use `total_value` for reads and `set_simple_value` / `set_disaggregated_data` for writes — never mutate `disagg_data` in-place.

**Pre-migration integrity checks:** Run `python scripts/ops/check_data_submission_integrity.py` from `Backoffice/` before applying submission-data migrations (duplicate rows, orphan parents, malformed disagg shapes).

### Key Models Relationships
- **User ↔ Country**: Many-to-many (user_countries table)
- **FormTemplate ↔ FormSection**: One-to-many
- **FormSection ↔ FormItem**: One-to-many  
- **FormItem ↔ IndicatorBank**: Many-to-one (for indicator items)
- **PublicFormAssignment ↔ Country**: Many-to-many

### Form Data Structure
- Forms use unified `FormItem` model supporting indicators, questions, and document fields
- Disaggregation support for demographic data (age/sex breakdowns)
- Calculated lists for dynamic form behavior
- Pagination state restoration for large forms

## Configuration

### Environment Setup
- Copy `Backoffice/config/` templates for local configuration
- Set up `.env` file in Backoffice directory
- Configure database URL, API keys, translation services

### Translation Services
- Hosted IFRC/Azure translation is the default engine for EN, FR, ES, AR, RU, ZH, HI. LibreTranslate remains a local-dev fallback. A self-hosted NLLB sidecar (`services/nllb-sidecar`, compose profile `nllb`; CTranslate2 + `facebook/nllb-200-1.3B`, no external API) is available for all mapped languages, including the core seven, when selected in the auto-translate UI. Opt in from the Backoffice with `NLLB_SIDECAR_URL` (see `services/nllb-sidecar/README.md`).
- Gettext **values** live in `translation_string` (provenance, engine, status). `pybabel extract` / `.pot` stay the msgid source. Compiled `.mo` files remain the runtime path.
- Import existing catalogs with `flask translations import-catalog` (backfill `unknown_presumed_machine`), then `flask translations recover-provenance` to mark audited human edits. Seed must-terms with `flask translations seed-glossary` (Indicator Bank / Common Words → `translation_glossary_term`). Auto-translate reads those DB rows only: it keeps the English source term so the engine can set word order, then swaps unofficial renderings for the official target form. Add or edit terms on `/admin/translations/quality` — do not hardcode house terms or whole-phrase rows in code.
- Quality dashboard: `/admin/translations/quality` — Overview, Glossary, Inbox, and Unreviewed tabs. Glossary and Inbox use AG Grid (`GET /admin/translations/api/glossary-terms` and `…/glossary-candidates`). Engine eval (gated on a filled gold set): `python Backoffice/scripts/i18n/eval_translation_engines.py`.
- Knowledge Base language versions: on `/admin/ai/documents`, select the completed files for one publication → **Mark as same publication** (records deferred pairs; sentence-level TM stays off) → **Mine terminology**. Mining first joins shared `(ACRONYM)` expansions, then asks OpenAI to extract English glossary heads and pair them using embedding retrieval in each target document. A pair is stored only when the target wording appears in those retrieved chunks. Exact matches of an approved glossary form are dropped; a different form for the same source is flagged as a conflict. Review/accept (or edit) candidates on `/admin/translations/quality`. Accepting a conflict replaces the official term.

### Inline Translation Review (in-context editor)
Human translators can review UI strings directly on live pages without opening the admin translation grid.

**Enable / disable**
- Kill switch: `TRANSLATION_REVIEW_ENABLED` (env / `Config`, default `true`)

**Permissions & assignments**
- Permission: `translations.review.use` (scoped per locale via `RbacAccessGrant` with `scope_kind='language'`)
- Baseline role: `translator` (organizational label only; language access comes from scoped grants)
- Assign languages on the user form (`/admin/users/edit_user/<id>`) when the Translator role is selected (`admin.users.roles.assign` or `admin.translations.manage`)
- Users with `admin.translations.manage` may also use the tool for their active non-English UI locale

**Permission vs. UI visibility**
Permission (`user_can_use_translation_review`) and UI visibility (`user_wants_translation_review_tool`, both in `app/services/translation_review/assignment_service.py`) are intentionally decoupled:
- Users with explicit per-language grants (real translators) get the floating tool automatically.
- Everyone else who merely *has permission* via a broad role/grant (e.g. `system_manager`, `admin.translations.manage`) does **not** see the tool by default — it stays hidden until they opt in via the `translation_review_tool_enabled` checkbox on their own Account Settings page. This avoids showing an intrusive floating button + pointer overlay to every admin who technically has access but doesn't want it.
- Both the FAB rendering (`template_context.py`) and the `/translation-review/toggle` route enforce `permission AND wants`.

**How it works**
1. Translator toggles the floating **Translate** FAB (session flag `translation_review_mode`; page reload).
2. When review mode is active, Flask-Babel gettext output is wrapped with invisible Unicode markers encoding the English `msgid` (`app/services/translation_review/marker.py`).
3. Pointer mode scans DOM text/attributes for markers; click opens a modal with source, machine suggestion, and official text.
4. Placeholders (`%(name)s`, `%s`, `%d`, …) are protected client-side (chips) and validated server-side (`app/services/translation/placeholder_validator.py`).
5. **Approve official** writes `translation_string` with `provenance=human`, syncs the `.po` artifact, compiles `.mo`, calls `flask_babel.refresh()`, and logs `translation_review_edit` to `admin_action_log`.

**Key modules**
- Routes: `app/routes/translation_review/` (`/translation-review/toggle`, `/translation-review/api/string`, `/api/queue`, `/api/glossary-candidates`)
- Hooks: `app/services/translation_review/hooks.py` (wraps Jinja + `Domain.gettext`; strips markers from non-HTML responses)
- Frontend: `app/static/js/translation_review/core.js`, `app/static/css/translation-review.css`, included from `core/layout.html`
- Production propagation: `app/utils/translation_watcher.py` polls shared `translations/` in all environments so every Gunicorn worker refreshes catalogs after PO/MO changes

**Deploy notes**
- Run migrations: `add_rbac_language_scope`, `add_translation_review_tool_toggle`, `add_translation_quality`
- Seed RBAC: `python -m flask rbac seed`
- Ensure persistent translations volume is mounted (see `Backoffice/docs/setup/persistent-translations.md`)

### AI System Configuration (Backoffice)
- **Chat API**: `/api/ai/v2` (chat, stream, conversations, export/import). WebSocket: `/api/ai/v2/ws`. Health: `GET /api/ai/v2/health` (includes `agent_available`).
- **Auth**: Session (Backoffice) or Bearer token (e.g. mobile). Issue tokens via `GET /api/ai/v2/token` (authenticated).
- **Environment**: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-5-mini`), `GEMINI_API_KEY`, `AZURE_OPENAI_*` for providers. `AI_EMBEDDING_PROVIDER`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIMENSIONS` (must match pgvector column; changing requires migration and possibly re-embedding). `AI_AGENT_ENABLED`, `AI_AGENT_MAX_ITERATIONS`, `AI_AGENT_TIMEOUT_SECONDS`, `AI_AGENT_COST_LIMIT_USD`, `AI_AGENT_MAX_COMPLETION_TOKENS` (default 32768; cap 128000 for large tables; use 4096 for GPT-4o). `AI_TOOL_OBSERVATION_MAX_ROWS_TABLE_RESULT` (default 250; cap 2000; rows sent from indicator/UPR “all countries” tools; increase for full country datasets). `REDIS_URL` optional for cross-worker rate limiting.
- **Supported models**: Depend on OpenAI account. Some models (e.g. GPT-5) reject sampling params; see `app.utils.ai_utils.openai_model_supports_sampling_params`.
- **Shared helpers**: `app.utils.ai_utils` (e.g. `openai_model_supports_sampling_params`, `sanitize_page_context`). RAG: `app.services.ai_vector_store`, `app.services.ai_embedding_service`. Agent: `app.services.ai_agent_executor`, `app.services.ai_tools_registry`. Shared chat request handling: `app.services.ai_chat_request` (parse, resolve conversation, idempotency).
- **Optional dependencies**: `flask-sock` required for WebSocket endpoints (`/api/ai/v2/ws`, document QA WS). Without it, AI HTTP and SSE still work. `redis` (and `REDIS_URL`) optional for cross-worker WebSocket rate limiting; in-memory limiter used otherwise. `pgvector` required for RAG document search; run migrations so `ai_documents`, `ai_embeddings`, `ai_document_chunks` exist. For full chat (non-fallback): at least one of `OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure/Copilot keys. For RAG embeddings: `OPENAI_API_KEY` when `AI_EMBEDDING_PROVIDER=openai`, or local model when `AI_EMBEDDING_PROVIDER=local` (dimensions must match DB).

### AI document batch jobs & processing (`AI_DOCS_*`)

Cross-worker batch imports/reprocess jobs use `AIJob` / `AIJobItem` with the generic runner in `Backoffice/app/services/ai/ai_job_runner.py`. Single-document upload/reprocess uses background threads plus `ai_documents.processing_stage` / `processing_heartbeat_at` (no job row).

| Config key | Default | Purpose |
|------------|---------|---------|
| `AI_DOCS_JOB_STALE_SECONDS` | `180` | Mark stuck in-flight job items failed when no live runner thread (60–3600) |
| `AI_DOCS_REPROCESS_CONCURRENCY` | `1` | Default worker count for bulk reprocess jobs (max 4) |
| `AI_DOCS_SYSTEM_IMPORT_CONCURRENCY` | falls back to IFRC | Default worker count for system-document bulk import |
| `AI_DOCS_IFRC_IMPORT_CONCURRENCY` | `2` | Default worker count for IFRC API bulk import |
| `AI_DOCS_AUTOFIX_STALE_PROCESSING_TIMEOUT_SECONDS` | `900` | Documents page auto-recovery for stale `processing` rows |
| `AI_DOCS_STUCK_NO_STAGE_TIMEOUT_SECONDS` | `3600` | Status poll marks `processing` failed when no stage/heartbeat |
| `AI_DOCS_STUCK_PENDING_TIMEOUT_SECONDS` | `900` | Status poll marks long-idle `pending` failed |
| `AI_DOCS_DUPLICATE_WAIT_SECONDS` | *(upload path)* | Wait for duplicate in-flight document before failing |

Advisory-lock namespace for AI batch jobs: see [multi-instance without Redis](Backoffice/docs/runbooks/deployment/multi-instance-without-redis.md) §3.3.

**Reusable pattern (migrate other features):** [Background jobs & progress UI](Backoffice/docs/architecture/background-jobs-and-progress-ui.md) — bulk runner, single-entity heartbeat, frontend banner, migration checklist for agents.

## Testing and Quality

### Backoffice Testing
```bash
# Run database migration check
python scripts/check_db_migration.py

# Import/export testing
python scripts/imports/import_fdrs_form_data.py

# AI review queue (terminal triage packets)
python scripts/ai/trigger_automated_trace_review.py --status pending --limit 5 --format text

# Seed deterministic low-quality review item for queue testing
python scripts/ai/seed_low_quality_review.py
python scripts/ai/seed_low_quality_review.py --trace-id 99999999 --create-trace-if-missing
```

### AI review queue scripts (Backoffice)
- `scripts/ai/trigger_automated_trace_review.py` – exports pending/in-review trace packets from `ai_trace_reviews`/`ai_reasoning_traces` for automated terminal processing (`text` or `jsonl`), with paging and optional `--claim-in-review`.
- `scripts/ai/seed_low_quality_review.py` – marks a trace as low-quality (`llm_needs_review=True`) and creates/resets a pending review row; use for deterministic end-to-end testing of review queue workflows.
- `scripts/archive/` – completed one-offs (record-specific probes, incident scripts); not used in CI.
- `scripts/codemods/` – template/JS bulk refactors; CI guardrails remain in `scripts/ci/`.

### Website Testing  
```bash
# Run linting
npm run lint

# Development with error handling
npm run dev:safe
```

## Special Features

### Form Builder
- Dynamic indicators with real-time calculations
- Conditional field visibility based on relevance conditions
- Repeat sections for variable-length data
- AJAX auto-saving functionality

### Analytics
- User session tracking and cleanup
- API usage monitoring
- Activity logging and audit trails
- Public submission management

### Internationalization
- Automatic translation via LibreTranslate
- Multilingual indicator definitions and labels
- Country name translations
- Form localization support

## Development Notes

### Session Management
- Automatic cleanup of inactive sessions (2-hour timeout)
- Session blacklisting for security
- User activity tracking and analytics

### API Structure
- RESTful endpoints under `/api/v1/`
- Authentication varies by surface area (session auth in Backoffice UI; bearer/JWT used by some API clients)
- CORS enabled for frontend integration
- Request/response tracking and monitoring

### API Response Helpers

**`app.utils.api_responses`** – use for admin/AJAX routes and internal endpoints with fixed response shapes:
- **Success**: `json_ok(**extra)` (200), `json_accepted(**extra)` (202), `json_created(**extra)` (201)
- **Errors**: `json_bad_request(msg)`, `json_forbidden(msg)`, `json_not_found(msg)`, `json_server_error(msg)`, `json_error(msg, status=400, **extra)`
- **Auth**: `json_auth_required(msg)` (401)
- Prefer these over inline `jsonify()` for consistency. `GENERIC_ERROR_MESSAGE` is re-exported here.

**`app.utils.api_helpers`** – use for external API routes and error tracking:
- `api_error(...)` – returns JSON with `error_id` for external clients
- `json_response(data, status_code)` – low-level JSON response
- Use when you need error IDs or custom response semantics for external API consumers.

**When to keep `jsonify`**: Pass-through responses (`jsonify(result)` where `result` comes from a service), raw arrays, or responses with custom status/headers (e.g. manifest with `Content-Type`).

### AJAX / JSON Request Detection
- Use `is_json_request()` from `app.utils.request_utils` instead of ad-hoc checks (`request.is_json`, `Accept` headers, etc.).

### Client-Side Fetch (Backoffice JS)
- Use `getFetch()` or `getApiFetch()` from `app/static/js/core/csrf.js` / `app/static/js/lib/api-fetch.js`: `(window.getFetch && window.getFetch()) || fetch` for raw CSRF-aware fetch, or `window.apiFetch` for JSON + optional error display.
- Avoid duplicating the inline pattern; prefer `getFetch()` / `getApiFetch()`.

### Template Safety Checklist (Backoffice Jinja)
- **Client console logging (`CLIENT_CONSOLE_LOGGING`):** `core/layout.html` includes `components/_client_console_guard.html` early in `<head>`, which sets `window.CLIENT_CONSOLE_LOGGING` and no-ops native `console.log` / `debug` / `info` / `warn` / `group*` when the flag is off. For **verbose or trace** output from inline scripts, use **`window.__clientLog`**, **`window.__clientWarn`**, etc. — not raw `console.log` / `console.warn`. **Never call `window.__consoleSaved.*`** (that object holds the *unwrapped* native methods and **bypasses** `CLIENT_CONSOLE_LOGGING`). Use `console.error` only for real failure paths you intend to keep visible. Other full-page templates (e.g. immersive chat, Swagger) include the guard explicitly; standalone HTML that does not extend `layout.html` has no guard unless you `{% include 'components/_client_console_guard.html' %}`. CI guardrail: `python Backoffice/scripts/ci/check_no_console_saved_bypass.py`. Bulk template fixes: `python Backoffice/scripts/ci/gate_template_console_calls.py`.
- **CSP / inline scripts:** Any inline `<script>` must include `nonce="{{ csp_nonce() }}"`. Prefer external JS for larger logic.
- **Server URLs in JS:** Always inject URLs/strings with `|tojson|safe` (avoid raw string interpolation in JS).
- **Translated strings in JS or attributes:** Flask-Babel marks every `{{ _(...) }}` result as HTML-safe, so it is **not** autoescaped in `<script>` blocks or attribute values. Never embed translations inside quoted JS literals (`'{{ _("Label") }}'` breaks when French uses apostrophes). Use `{{ _('Label')|tojson|safe }}` as a standalone JS value (concatenate with `+` if needed), or the existing `|js` filter. For HTML attributes (`data-*`, `title`, `aria-*`, etc.), use `{{ _('Label')|forceescape }}`. CI guardrail: `python Backoffice/scripts/ci/check_unsafe_gettext_embedding.py`. Batch fix: `python Backoffice/scripts/codemods/fix_unsafe_gettext_embedding.py --apply`.
- **Fetch client standard:** Use `(window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch` (or `getFetch()` for non-JSON) instead of bare `fetch`.
- **Action-specific payloads:** For buttons like dismiss/archive/close, send only fields needed for that action; do not implicitly submit full form state.
- **Backend guardrails:** Validate `status` and only update fields intended for that status transition (e.g., dismiss should not overwrite annotation content).
- **Null-safe rendering:** Guard optional relationships (`if trace`, `if review.user`, etc.) before dereferencing attributes in links/labels.
- **Quick verification before merge:** Open page + browser console (CSP errors), exercise primary actions (save/dismiss), verify no unintended field mutation in DB.

### File Uploads
- Document management system
- PDF thumbnail generation
- Resource file organization by language

### Security
- CSRF protection enabled
- Role-based access control (admin, focal_point, view_only)
- Session security with HTTP-only cookies
- Input validation and sanitization

### Assignment Status Naming (ACS→AES Migration Complete)
- The canonical model is **`AssignmentEntityStatus`** (supports country + non-country entities). The codebase has been migrated from legacy `acs` naming to `aes`:
  - Use `aes`, `aes_id`, or explicit `assignment_entity_status_id` / `assignment_status_id` in all new code.
  - HTML data attributes use `data-aes-id`. JS variables use `aesId`.
  - Route parameters use `aes_id`. JSON keys use `assignment_entity_status_id`.
  - Service functions: `get_aes_with_joins`, `ensure_aes_access`.
- Do not reintroduce `acs` naming in new code.

### Presence Tracking (Do Not Use `user_activity_log`)
- Live presence heartbeat endpoints (`/api/forms/presence/...`) should use cache/memory (Redis when available, in-memory fallback), not `user_activity_log`.
- `user_activity_log` is for meaningful audit/activity events; high-frequency heartbeat noise should not be written there.
- If a durable "last active" timestamp is needed for user features, store it on the `user` record (e.g., dedicated datetime field) with write throttling, rather than logging every heartbeat.

## Admin Interface Architecture

### Modular Blueprint Structure
The admin interface has been modularized from a single monolithic file (340KB, 7000+ lines, 122 routes) into focused, maintainable modules:

#### Core Admin Blueprints
- **Main Admin** (`admin/__init__.py`): Dashboard, statistics, blueprint registration
- **Form Builder** (`admin/form_builder.py`): Template creation, section management, form item configuration
- **User Management** (`admin/user_management.py`): User CRUD operations, role assignments
- **Assignment Management** (`admin/assignment_management.py`): Form assignments, public assignments, submission management
- **Content Management** (`admin/content_management.py`): Resources, publications, document management
- **System Admin** (`admin/system_admin.py`): Countries, sectors, indicator bank, lookup lists
- **Analytics** (`admin/analytics.py`): Dashboard APIs, user activity tracking, system monitoring
- **Utilities** (`admin/utilities.py`): Import/export, translations, session management, CSRF handling

#### Shared Components (`admin/shared.py`)
- Permission decorators (`admin_required`, `permission_required`)
- Common utility functions
- Localization helpers
- Error handling patterns

#### Benefits of Modularization
- **Maintainability**: Focused modules with clear separation of concerns
- **Performance**: Reduced memory footprint and faster loading
- **Developer Experience**: Easier navigation and debugging
- **Scalability**: New features can be added without affecting other modules
- **Code Quality**: Better organization and reduced complexity

### Admin feature plugins (org-specific tools)

Org-specific admin features (e.g. IFRC P&B Visuals) live under [`Backoffice/plugins/<plugin_id>/`](Backoffice/plugins/) as **plugins** using the same `plugin.py` + `BasePlugin` contract as form-field plugins, with optional admin hooks.

| Piece | Location |
|-------|----------|
| Plugin contract | [`Backoffice/app/plugins/base.py`](Backoffice/app/plugins/base.py) (`BasePlugin`, optional admin hooks) |
| Discovery & lifecycle | [`Backoffice/app/plugins/manager.py`](Backoffice/app/plugins/manager.py) (`PluginManager`) |
| Example plugin | [`Backoffice/plugins/pb_progress/`](Backoffice/plugins/pb_progress/) |
| UPR visuals plugin | [`Backoffice/plugins/upr_visuals/`](Backoffice/plugins/upr_visuals/) — live Unified Plan (template 24) / Report (template 33) dashboards on assignment pages; PNG/PDF/InDesign download; optional Word-narrative PDF or InDesign package; bulk PNG export on the Data Explorer **UPR visuals** tab (replaces Tableau `UPR Visuals.twb`). Temporary People reached remapping: [`people-reached.md`](../Backoffice/plugins/upr_visuals/docs/people-reached.md) |
| Standalone tool scripts | `Backoffice/plugins/<id>/visuals/` (or similar subfolder) |

**To add a new admin-feature plugin:**

1. Create `Backoffice/plugins/<plugin_id>/plugin.py` subclassing `BasePlugin`.
2. Return `[]` from `get_field_types()` if the plugin has no form fields.
3. Implement `get_blueprint()`, and optionally `get_data_explorer_tab()`, `get_seed_permissions()`, `get_seed_roles()`, `get_csp_overrides()`, `get_panel_render_context()`.
4. Add routes, services, templates under the same plugin folder.
5. No core app file changes required — `PluginManager` discovers `plugin.py` at startup.

**To unplug:** delete the plugin folder. Core Data Explorer tabs remain.

**Config override:** `PB_VISUALS_TOOL_DIR` in Flask config overrides the default `plugins/pb_progress/visuals/` path for the P&B build pipeline.

### Native Report Builder (core platform)

Admins compose metadata-driven reports from Indicator Bank, templates, and assignment data. Unlike the P&B plugin, reports are user-defined and stored in the `report_definition` table.

| Piece | Location |
|-------|----------|
| Models | [`Backoffice/app/models/reports.py`](Backoffice/app/models/reports.py) |
| Definition schema (v1) | [`Backoffice/app/schemas/report_definition_v1.json`](Backoffice/app/schemas/report_definition_v1.json) |
| CRUD + scoping | [`Backoffice/app/services/reports/definition_service.py`](Backoffice/app/services/reports/definition_service.py) |
| Widget execution | [`Backoffice/app/services/reports/data_service.py`](Backoffice/app/services/reports/data_service.py) |
| Shared aggregation | [`Backoffice/app/services/data_retrieval/aggregation.py`](Backoffice/app/services/data_retrieval/aggregation.py) |
| Admin UI | `/admin/reports` — list, builder (`/edit`), viewer |
| JS renderers | [`Backoffice/app/static/js/reports/`](Backoffice/app/static/js/reports/) |
| Permissions | `admin.reports.view`, `admin.reports.edit`, `admin.reports.manage`; Data Explorer tab `admin.data_explore.reports` |

**Adding a widget type:** extend the JSON schema, add a `data_source.kind` handler in `ReportDataService.execute_widget`, and register the type in the builder palette (`builder/main.js`) plus `widget-renderer.js`.

**Relationship to `/api/v1/data`:** reports use the same underlying FormData/assignment joins via `aggregation.py` and `query_form_data` filters; the public data API remains the integration surface for external BI tools.

**Relationship to pb_progress:** P&B remains a specialized offline publish pipeline; it may later consume `aggregation.py` for system dataset generation, but is unchanged by the report builder v1.

**Not to be confused with the public country one-pager report** (`Backoffice/app/services/public/report_service.py`) — a separate, unauthenticated feature behind the Custom GPT `getCountryReport`/`getReportTemplate` Actions and the MCP connector's `databank_build_country_report`/`databank_get_report_template` tools. It has no `report_definition` row, no admin UI, and no widget model; it assembles a curated FDRS/UPR JSON spec plus an HTML/CSS design-template skeleton for an LLM to render (optionally as a PDF the LLM generates itself). Its style/layout assets live in `Backoffice/app/services/public/report_styles/<style>.html` (+ `<style>.tokens.json`), colocated with the one module that reads them — see [`humanitarian-databank-mcp/README.md`](../humanitarian-databank-mcp/README.md#report-design-templates) and [`Backoffice/docs/public/custom-gpt/README.md`](../Backoffice/docs/public/custom-gpt/README.md).

## RBAC & Permissions

Role-Based Access Control gates every `/admin` page, the mobile API's admin surface, and plugin routes. Models: [`Backoffice/app/models/rbac.py`](../Backoffice/app/models/rbac.py).

| Table | Purpose |
|-------|---------|
| `rbac_permission` | Catalog of permission codes (`admin.<area>.<action>`, e.g. `admin.users.edit`) — unique on `code` |
| `rbac_role` | Named bundles of permissions (`system_manager`, `admin_users_manager`, ...) — unique on `code` |
| `rbac_role_permission` | Role ↔ permission (many-to-many) |
| `rbac_user_role` | User ↔ role (many-to-many — a user can hold multiple roles) |
| `rbac_access_grant` | Scoped allow/deny exceptions on top of role permissions — `global` / `entity` / `template` / `assignment` / `language` scope, per user or per role (e.g. translator per-locale grants) |

**Evaluation** — `AuthorizationService.has_rbac_permission(user, code, scope=...)` in [`app/services/organization/authorization_service.py`](../Backoffice/app/services/organization/authorization_service.py):
1. `system_manager` role is a superuser shortcut — returns `True` immediately, **before** the permission code is even looked up.
2. Otherwise: does any of the user's roles carry the permission via `rbac_role_permission`?
3. Scoped grants layer on top of that — **most-specific scope wins** (`assignment` > `template` > `entity` > `language` > `global`), and **deny wins ties** at equal specificity.
4. An unrecognized `permission_code` (typo, or a plugin's seed not run yet) always evaluates to `False` for everyone *except* System Manager (who already returned `True` in step 1) — logged once per request in DEBUG (`"RBAC: unknown permission code '...' (seed missing or typo)"`), silent otherwise. It never raises.

### Permission catalog & seeding (single source of truth)

The catalog is **code, not data** — going forward, don't pre-populate `rbac_permission` / `rbac_role` via a data migration. [`Backoffice/app/services/organization/rbac_seed_service.py`](../Backoffice/app/services/organization/rbac_seed_service.py) is the intended sole writer:

*(Historical exception, not a pattern to repeat: a handful of older migrations — `add_reports_permissions`, `add_validation_admin_permissions`, `migrate_data_explorer_permissions`, `rename_admin_notifications_rbac_to_communication` — do write `rbac_permission`/`rbac_role` rows directly, predating this policy. Two of them (`add_reports_permissions`, `add_validation_admin_permissions`) also backfilled extra permissions onto an already-existing baseline role to avoid an abrupt access cut when a permission was split off — see the callout in `_baseline_roles()` for `admin_data_explorer_analysis` / `admin_data_explorer_compliance` and the "Migration vs. seeder drift" pitfall below before touching either role.)*

| Function | Returns |
|----------|---------|
| `_permission_catalog()` | Core `(code, name, description)` tuples |
| `_baseline_roles(permission_catalog)` | Core roles + their `permission_codes` (System Manager's list is literally *every* catalog code — not "every code anyone references") |
| `_extension_permission_catalog()` / `_extension_baseline_roles()` | Same shape, merged in from every loaded plugin's `BasePlugin.get_seed_permissions()` / `get_seed_roles()` (see `PluginManager.get_all_seed_permissions()` / `get_all_seed_roles()`) |
| `seed_rbac_permissions_and_roles(lock_mode=..., wait_timeout_seconds=...)` | Idempotent upsert-by-`code` of the combined core + plugin catalog, plus role↔permission link sync (adds missing links, deletes stale ones — scoped to the catalog's own permission ids, so unrelated roles are untouched) |
| `get_missing_baseline_role_codes()` | Read-only diagnostic: which expected role codes aren't in `rbac_role` yet |

**Adding a new permission — checklist:**
1. Add `(code, name, description)` to `_permission_catalog()` (core), or to a plugin's `get_seed_permissions()`.
2. Reference that **exact** code in the decorator (`@permission_required('admin.foo.bar')`) and/or in a role's `permission_codes` list.
3. Run `tests/unit/test_rbac_catalog_completeness.py` locally — it fails loudly if a decorator or role references a code that isn't in the catalog. A typo here silently makes the guarded route unreachable for every non-System-Manager, since `seed_rbac_permissions_and_roles()` only ever creates rows for catalog codes and no role can hold a code that doesn't exist.
4. Run `flask rbac seed` (or let the next deploy do it — see below). Only add a real DB migration if you also need to touch *existing* users'/roles' assignments — the seeder never assigns roles to users.

**Pitfall — migration backfill onto an existing baseline role:** if a migration grants extra permissions directly to a role that's *also* defined in `_baseline_roles()` / a plugin's `get_seed_roles()` (e.g. to preserve access when splitting a permission in two), you **must** add those same codes to that role's `permission_codes` in code too. The reconciliation step in `seed_rbac_permissions_and_roles()` deletes any `rbac_role_permission` link for a catalog permission that isn't in the role's declared `permission_codes` — so a migration-only grant on a seeder-managed role survives only until the next `flask rbac seed` run (which, since `entrypoint.sh` runs it on every deploy, means the *next deploy*). This bit `admin_data_explorer_analysis` (missing `admin.reports.{view,edit}`, backfilled by `add_reports_permissions`) and `admin_data_explorer_compliance` (missing `admin.validation.{dashboard,questions,rules}`, backfilled by `add_validation_admin_permissions`) — both fixed in code and pinned by `TestBaselineRolesPreserveMigrationBackfilledPermissions` in `test_rbac_catalog_completeness.py`. A role backfilled by a migration but **not** tracked in `_baseline_roles()`/a plugin (e.g. a custom role created via the admin UI) is safe from this — the reconciliation loop only ever touches roles it knows about.

**Seeding runs from three places, all funneling through `seed_rbac_permissions_and_roles()`:**
- `flask rbac seed` CLI ([`app/cli_commands/rbac.py`](../Backoffice/app/cli_commands/rbac.py)) — operator/deploy-triggered, `RbacSeedLockMode.WAIT` (30s default via `--wait-timeout`).
- `entrypoint.sh` — runs `flask rbac seed` unconditionally after every `flask db upgrade` (not just when the table is empty), so a plugin/catalog change ships on the very next deploy with no manual step. Skip via `RBAC_SEED_ON_STARTUP=false`.
- Background auto-seed thread at app boot ([`app/startup_tasks.py`](../Backoffice/app/startup_tasks.py) `deferred_rbac_seed`) — best-effort safety net on every Gunicorn worker, `RbacSeedLockMode.TRY` (never blocks startup).

**`RbacSeedLockMode`** (PostgreSQL session advisory lock, key `915037121`) exists because two processes seeding at once can hit spurious unique-constraint races:
- `TRY` — non-blocking; silently gives up if another process holds the lock (`skipped_due_to_lock`). Only for the boot-time background thread — losing the race to a sibling worker seeding the same catalog is harmless, and a boot-time thread must never block startup.
- `WAIT` — retries the non-blocking attempt in a poll loop for up to `wait_timeout_seconds` before giving up. Use for anything operator/deploy-triggered (CLI, entrypoint) — these must reliably apply catalog changes rather than reporting a misleading "0 created, 0 updated" just because a Gunicorn worker's background thread happened to be holding the lock at that instant.
- `NONE` — skip the lock entirely (tests only).

### Enforcing permissions

| Surface | Decorator / helper |
|---------|---------------------|
| `/admin` HTML + JSON routes | `admin_required`, `permission_required(code)`, `permission_required_any(*codes)`, `system_manager_required`, `admin_permission_required[_any]` (combo) — [`app/routes/admin/shared.py`](../Backoffice/app/routes/admin/shared.py) |
| Mobile API (`/api/mobile/v1/admin/...`) | `mobile_auth_required(permission=code)` / `(permissions=(...))` — [`app/utils/mobile_auth.py`](../Backoffice/app/utils/mobile_auth.py) |
| Inline checks (service code, either surface) | `AuthorizationService.has_rbac_permission(user, code, scope=...)`; route-local convenience wrapper `user_has_permission(code)` |
| Templates (UI gating only — **routes remain authoritative**) | Jinja global `has_permission(code)` ([`app/template_context.py`](../Backoffice/app/template_context.py)) |
| Intentionally-unguarded `/admin` route | `@rbac_guard_audit_exempt("reason")` — otherwise flagged by the startup audit below |

Every route decorator above (and `mobile_auth_required`) stamps metadata attributes on the view function (`_rbac_permissions_required`, `_rbac_permissions_any_required`, `_ep_permission(s)`, ...). Those attributes play no role in the actual per-request authorization decision — they exist purely so the two automated checks below can audit the app's routes without re-executing every decorator.

### Automated guardrails

- **Startup audit** — `audit_admin_route_guards()` in `app/startup_tasks.py` walks `app.url_map` for every `/admin` rule and warns (or raises, if `RBAC_ADMIN_ROUTE_GUARD_MODE=strict`) about any route with none of the guard decorators above and no `rbac_guard_audit_exempt`. Catches a **missing** guard.
- **Catalog completeness test** — [`tests/unit/test_rbac_catalog_completeness.py`](../Backoffice/tests/unit/test_rbac_catalog_completeness.py) walks every registered view function's RBAC metadata (web + mobile) plus every baseline/plugin role's `permission_codes`, and asserts each referenced code exists in `_permission_catalog()` + `_extension_permission_catalog()`. Also guards against duplicate permission/role codes across core + plugins, and pins the two migration-backfilled roles from the pitfall above so their extra codes can't be trimmed from `_baseline_roles()` by accident. Catches a **typo'd/renamed** code — the class of bug where the guard exists but silently protects a permission that no non-System-Manager role can ever hold.
- Neither check can verify *which* permission a route ought to have — only that a guard exists and that whatever it names is real. Code review still has to confirm `admin.foo.edit` is the *right* code for a given route (e.g. matching the equivalent HTML/JSON/mobile route for the same action).

### Privilege-escalation guard (RBAC role assignment)

Only a System Manager may grant/revoke the `system_manager`, `admin_full`, or `admin_plugins_manager` roles. The codes are centralized once in `_RESTRICTED_RBAC_ROLE_CODES` ([`app/routes/admin/user_management/helpers.py`](../Backoffice/app/routes/admin/user_management/helpers.py)) and imported by every call site that assigns roles: `admin/user_management/crud.py` (HTML), `admin/user_management/api.py` (JSON), `api/mobile/admin_users.py` (mobile).

`_critical_rbac_roles_integrity_ok(restricted_codes, restricted_role_ids)` gates all three call sites: if RBAC hasn't been seeded at all yet, there's nothing to enforce (returns `True`); if it *has* been seeded but one of those three role codes can't be resolved (renamed, corrupted, deleted out-of-band), it **fails closed** — RBAC role assignment is disabled entirely for non-System-Managers until `flask rbac seed` is re-run — rather than silently letting through whichever restriction couldn't be verified.

### Troubleshooting

- **A newly-added plugin role/permission is missing from the DB after deploy** — check `entrypoint.sh` actually ran `flask rbac seed` (not skipped via `RBAC_SEED_ON_STARTUP=false`), and that the plugin loaded successfully (`PluginManager.load_plugins()` logs per-plugin failures; one broken plugin doesn't fail the whole boot, but it does mean that plugin's permissions/roles never reach the seeder).
- **`flask rbac seed` reports "0 created, 0 updated" but a role/permission still doesn't exist** — the code most likely never made it into `_permission_catalog()` / `_baseline_roles()` / a plugin's `get_seed_*()` in the first place (the seeder can only create what's in code). Run the catalog completeness test and double-check the exact code string for typos.
- **A route 403s for every non-System-Manager, but System Manager can still get in** — the permission code passed to the decorator doesn't match any catalog entry. This is exactly the failure `tests/unit/test_rbac_catalog_completeness.py` guards against; check DEBUG logs for `"RBAC: unknown permission code '...'"`.

## Migration and Data Management

### Database Migrations
- Use Flask-Migrate for schema changes
- Check `Backoffice/migrations/versions/` for migration history
- Run migration check script before major changes
- **Single-head policy (mandatory):** Never run `flask db migrate`, `flask db upgrade`, or create/edit migration files without first running `python -m flask db heads`.
- If `db heads` returns more than one head, STOP and resolve the branch point first (do not proceed with new migrations or upgrade).
- New migration files must set `down_revision` to the current single head revision.
- After adding/changing a migration, run `python -m flask db heads` again and confirm exactly one head remains before any upgrade.

### Data Import/Export
- Excel import functionality for bulk data
- FDRS data structure support
- Automated data migration scripts in `Backoffice/scripts/`

## Monitoring and Logging

### Logging Configuration
- Configurable log levels (set `VERBOSE_FORM_DEBUG=true` for detailed logs)
- Session cleanup and activity logging
- API request/response tracking
- Error handling and reporting

### Azure App Service logs (staging)
- Requires **Azure CLI** (`az`) and an authenticated session (`az login`).
- Stream live application logs (stdout/stderr from the web app):

```bash
az webapp log tail --name <your-webapp-name> --resource-group <your-resource-group>
```

### Preventing 502 / 504 errors on Azure App Service

Key env vars to set in **Azure Portal → App Service → Configuration → Application settings**:

| Variable | Value | Purpose |
|----------|-------|---------|
| `GUNICORN_TIMEOUT` | `60` (default) | Heartbeat murder threshold, **not** a request timeout: gthread workers heartbeat from the accept loop, so stuck requests never trip it (App Gateway 504s clients at ~30s). Must exceed `GUNICORN_GRACEFUL_TIMEOUT` (15) + scheduler shutdown wait (10) with margin, or recycles get SIGKILLed mid-teardown (2026-07-16 incident) |
| `GUNICORN_WORKERS` | `3` or `4` (explicit) | Prevents RAM exhaustion on smaller SKUs |
| `GUNICORN_THREADS` | `8` (default) | Request slots per worker; also drives the per-worker WebSocket budget (threads − 2). The effective value is written back to the env so `ws_manager` always sees it |
| `WS_MAX_AI_CHAT` / `WS_MAX_AI_DOCS` / `WS_MAX_NOTIFICATIONS` | derived from budget | Optional per-channel WebSocket caps (on top of the total thread budget) so AI sockets cannot starve notifications |
| `WS_MAX_MESSAGE_BYTES` | `262144` | Max inbound WebSocket frame size (also set as `SOCK_SERVER_OPTIONS.max_message_size`) |
| `GUNICORN_KEEPALIVE` | `75` (default) | Backend keepalive must outlive App Gateway connection reuse to avoid idle-close 502 races |
| `GUNICORN_MAX_REQUESTS` | `500` | Workers recycle before OOM; jitter prevents mass recycling |
| `GUNICORN_MAX_REQUESTS_JITTER` | `100` | Spreads recycling across workers |
| `SCHEDULER_LOCK_FAIL_OPEN` | unset (default: fail closed) | On scheduler-lock filesystem errors the worker skips starting the scheduler; set `true` to start it anyway (risk: duplicate schedulers → duplicate digest emails) |
| `DB_STATEMENT_TIMEOUT_MS` | `120000` | Kills runaway queries so pool connections are released |
| `DB_CONNECT_TIMEOUT` | `10` | Aborts stale TCP handshakes to PostgreSQL |
| `REDIS_URL` | `rediss://…` | Cross-worker coordination (rate limits, presence, alert cooldown). Azure SKU: [Managed Redis Balanced B0, West Europe](../Backoffice/docs/runbooks/deployment/redis-provisioning.md). |
| `SCHEDULER_DISABLE_ALL_WORKERS` | `true` | Stop gunicorn workers from running APScheduler when background jobs run in an Azure Function / Container Job |

**ARR Affinity** (Azure Portal → App Service → Configuration → General settings):
- Set to **On** when `REDIS_URL` is not configured (required for session consistency).
- Can be **Off** when `REDIS_URL` is set.

**AI streaming / SSE**: Azure App Service front-end times out at ~230s. If AI agent runs longer, either place an **Application Gateway** (backend timeout ≥ 300s) in front, or lower `AI_AGENT_TIMEOUT_SECONDS` and `AI_SSE_IDLE_TIMEOUT_SECONDS` to fit within 200s.

Detailed runbook: [Incidents → Scenario F (502/504)](Backoffice/docs/runbooks/incidents/general-incident-triage.md#scenario-f-recurring-502--504-errors)

### Performance
- Database query optimization
- Static file serving
- Translation caching
- Form state management optimization

## Where to Change Things (Index)

- **Admin (Backoffice UI routes)**: `Backoffice/app/routes/admin/` (pick the closest module)
- **Form builder frontend JS**: `Backoffice/app/static/js/form_builder/`
- **Entry form rendering + client behavior**: `Backoffice/app/templates/forms/entry_form/` and `Backoffice/app/static/js/forms/`
- **AI endpoints + request handling**: `Backoffice/app/routes/ai.py`, `Backoffice/app/services/ai/chat/`
- **RAG / embeddings / vector store**: `Backoffice/app/services/ai/documents/`, `Backoffice/app/services/ai/providers/`
- **Business services (by domain)**: `Backoffice/app/services/` — subpackages include `forms/`, `data_retrieval/`, `organization/`, `validation/`, `platform/`, `upr/`, etc.
- **Translations / localization**: `Backoffice/app/utils/form_localization.py`, `Backoffice/translations/`, `Backoffice/app/services/translation_review/`
- **Button styles / design system**: `Backoffice/app/static/css/theme.css` (CSS variables), `Backoffice/app/static/css/components.css` (`.btn` system), `Backoffice/app/static/css/executive-header.css` (`.professional-action-btn` page-header variants)
- **Mobile app (Flutter)**: `MobileApp/` — routes: `lib/config/routes.dart`, `lib/config/app_router.dart`; DI: `lib/di/service_locator.dart`; API constants: `lib/config/app_config.dart` (no inline `/api/mobile/v1/...` strings in providers). Shared UI: `lib/widgets/loading_indicator.dart`, `lib/widgets/error_state.dart`, `lib/widgets/async/async_body.dart`, `lib/widgets/mobile_screen_scaffold.dart`. JSON helpers: `lib/utils/mobile_api_json.dart`. iOS CocoaPods / `Podfile.lock` without a Mac: **Regenerate iOS Podfile.lock** workflow (see **Mobile App (Flutter)** in Local Development Quickstart).

## Backoffice Button Design System

### Overview
Buttons use a three-layer system that must be kept consistent:

1. **CSS variables** (`theme.css`) — single source of truth for all semantic colours
2. **`.btn` component classes** (`components.css`) — all body/form/modal buttons
3. **`.professional-action-btn`** (`executive-header.css`) — page-header action buttons only

**After any change to button classes or templates: run `npm run build:css` in `Backoffice/`** to regenerate `output.css`.

### Colour Semantics (mandatory — follow for all new buttons)

| Colour | Class | When to use |
|--------|-------|-------------|
| Teal (primary) | `btn-primary` / `professional-action-btn-blue` | Preview, Edit, Save draft, Open, Reload, navigate without committing |
| Green (success) | `btn-success` / `professional-action-btn-green` | Submit, Confirm, Add, Approve, Export, Import — commits something |
| Red (danger) | `btn-danger` / `professional-action-btn-red` | Delete, Remove, Reject |
| Gray (secondary) | `btn-secondary` | Cancel, Close, Back — no destructive intent |
| Orange (warning) | `btn-warning` / `professional-action-btn-orange` | Auto-translate, automation, cautionary triggers |
| Purple | `btn-purple` / `professional-action-btn-purple` | Audit Trail, analytics, special views |
| Slate dark | `btn-dark` / `professional-action-btn` (default) | Generic header actions without a specific semantic colour |

Keep adjacent header actions visually distinct (e.g. Preview=teal, Audit Trail=purple, Excel=green, Auto Translate=orange).

### Standard Button Markup

```html
<!-- Body / form / modal buttons — use .btn + colour variant -->
<button class="btn btn-primary">Edit</button>
<button class="btn btn-success">Save</button>
<button class="btn btn-danger">Delete</button>
<button class="btn btn-secondary">Cancel</button>
<button class="btn btn-warning">Auto Translate</button>
<button class="btn btn-purple">Audit Trail</button>

<!-- Size modifiers -->
<button class="btn btn-success btn-sm">Save</button>   <!-- 12px, compact -->
<button class="btn btn-danger btn-lg">Delete</button>  <!-- 15px, prominent -->

<!-- Icon-only square button -->
<button class="btn btn-danger btn-icon" title="Delete"><i class="fas fa-trash"></i></button>

<!-- Full-width (modal footers, mobile) -->
<button class="btn btn-secondary btn-block">Cancel</button>

<!-- Ghost / outline variants -->
<button class="btn btn-ghost">Secondary action</button>         <!-- teal outline -->
<button class="btn btn-ghost-danger">Remove</button>            <!-- red outline -->

<!-- Loading state (add class via JS while request in-flight) -->
<button class="btn btn-success btn-loading">Saving…</button>

<!-- Disabled (native attribute handled automatically) -->
<button class="btn btn-primary" disabled>Save</button>

<!-- Page-header actions — use professional-action-btn inside .action-controls -->
<button class="professional-action-btn professional-action-btn-blue">Preview</button>
<button class="professional-action-btn professional-action-btn-green">Export</button>
```

### CSS Variables (all in `theme.css` `:root`)

| Variable set | Colours |
|---|---|
| `--btn-primary[-hover|-active|-focus]` | Teal — `#0d9488` |
| `--btn-success[-hover|-active|-focus]` | Green — `#16a34a` |
| `--btn-danger[-hover|-active|-focus]` | Red — `#dc2626` |
| `--btn-warning[-hover|-active|-focus]` | Orange — `#ea580c` |
| `--btn-purple[-hover|-active|-focus]` | Purple — `#9333ea` |
| `--btn-secondary-bg[-hover]`, `--btn-secondary-border`, `--btn-secondary-color` | Gray/white secondary |

Tailwind's `blue-*` and `teal-*` scales are remapped in `tailwind.config.js` to resolve to `--btn-primary`, so `bg-blue-600` in templates equals teal. `green-*` resolves to `--btn-success`.

### Backward-Compatible Aliases (existing templates)
These aliases in `theme.css` remain for existing markup but new code should use `.btn` + variant:
- `.btn-confirm` → equivalent to `btn btn-success`
- `.btn-cancel` → equivalent to `btn btn-secondary`
- `.btn-danger-standard` → equivalent to `btn btn-danger`

### Sharp Corners (design rule)
All system buttons use `border-radius: 0`. Do **not** add `rounded-*` Tailwind classes to buttons. Use `.rounded-full` only for FAB / circular icon-only buttons (this class is explicitly excluded from the sharp-corner enforcement).

### Files Reference
| File | Role |
|---|---|
| `app/static/css/theme.css` | CSS variables, sharp-corner enforcement, semantic aliases |
| `app/static/css/components.css` | Full `.btn` component system (base + variants + sizes + states) |
| `app/static/css/executive-header.css` | `.professional-action-btn` and colour variants for page headers |
| `app/static/css/notifications.css` | Notification-panel button sizing overrides only |
| `assets/tailwind.config.js` | Tailwind colour remap (`blue/teal/green → CSS variables`) |
| `app/templates/components/_page_header.html` | Page header macro (uses `.professional-action-btn` by default) |
| `app/templates/macros/delete_confirm_modal.html` | Delete confirmation modal (uses `btn btn-danger` / `btn btn-secondary`) |
| `app/templates/macros/translation_modal.html` | Translation modals (uses `btn btn-warning` / `btn btn-success` / etc.) |
| `app/templates/macros/modal_shell.html` | Generic modal shell |
| `app/templates/macros/excel_import_dropzone.html` | Shared two-state Excel file dropzone (drag/drop, optional validation status panel). Configure via macro params (`variant`, `validate_url`, copy) and `{% call %}` for hidden fields. JS: `initExcelImportDropzone()` in `app/static/js/components/excel-import-dropzone.js`. |
| `app/templates/macros/excel_io_modal.html` | Excel import/export modal layouts (`simple`, `split`, `tabs`). Passthrough `modal_shell` params plus `export_body` / `import_body` slots for page-specific actions. JS: `initExcelIoModal()` in `app/static/js/components/excel-io-modal.js`. |
| `app/templates/macros/excel_import_review_modal.html` | Second-step import review/confirm dialog (indicator bank pattern). |
| `app/templates/macros/excel_io_toolbar.html` | Bulk export link + import button bar (common words). |
| `app/static/css/excel-io.css` | Global styles for `.excel-io-dropzone` and modal layouts (linked from `core/layout.html`). |

### Template migration status (partial)

The `.btn` system is **not** applied to every template yet. New and touched UI should use `btn` + variants; legacy pages still mix long Tailwind utility strings (`inline-flex … bg-blue-600 …`), tab triggers, dropdown rows, and feature-specific CSS (chat, maps).

**Already on the design system (non-exhaustive):**

- Shared: `macros/delete_confirm_modal.html`, `macros/translation_modal.html`, `components/auto_translate_modal.html`, `components/_page_header.html` (header actions stay `professional-action-btn*`).
- Auth: `auth/login.html` (`.btn` + `.btn-login-oauth` for org/SSO brand red on Azure link).
- Examples: `admin/settings/manage_settings.html` (save), `admin/translations/manage_translations.html` (import/export + edit modal), `admin/user_management/user_form.html` (delete user modal).

**Intentionally different:**

- **Chat** (`layout.html` + `chatbot.css`): dedicated `chat-*` buttons.
- **Login** fullscreen / expand controls: circular icon buttons (`.fullscreen-btn`); not `.btn`.
- **Tabs / menus**: underline or `rounded-t-lg` tab buttons are navigation, not primary actions.
- **Notification centre**: uses `btn` + `.notifications-panel` spacing overrides in `notifications.css`.

**Find templates that still use raw Tailwind action buttons** (from repo root):

```bash
rg '<button[^>]+class="[^"]*bg-(blue|green|red|orange|purple|indigo)-600' Backoffice/app/templates
rg '<a[^>]+class="[^"]*bg-(blue|green)-600' Backoffice/app/templates
```

Also search `app/static/js` for string-built `class="…bg-*-600…"` on buttons. Migrate each hit to `btn btn-*` (+ `btn-block` / `btn-sm` as needed).

### Login page: `.btn-login-oauth`

`auth/login.html` defines **`.btn-login-oauth`** in a page `<style>` block for IFRC-style SSO branding (`#C8102E`). Use **`btn btn-block btn-login-oauth`** on that link only; do not use `btn-danger` for SSO (wrong semantics).

## Mobile API Surface (`/api/mobile/v1`)

### Architecture
- **Location**: `Backoffice/app/routes/api/mobile/` (sub-package with 10 modules)
- **Blueprint**: `mobile_bp`, registered in `app/__init__.py`, CSRF-exempt
- **Auth**: JWT Bearer via `@mobile_auth_required` (from `app.utils.mobile_auth`)
- **Response envelope**: `app.utils.mobile_responses` — `mobile_ok`, `mobile_paginated`, `mobile_error`
- **Rate limiting**: `mobile_rate_limit()`, `auth_rate_limit()` on sensitive endpoints
- **Version enforcement**: `X-App-Version` header checked against `MOBILE_MIN_APP_VERSION` config

### Module Inventory

| Module | Routes | Permission | Flutter Consumer |
|--------|--------|-----------|-----------------|
| `auth.py` | `POST /auth/token`, `POST /auth/refresh`, `POST /auth/exchange-session`, `GET /auth/session`, `POST /auth/logout`, `POST /auth/change-password`, `GET /auth/profile`, `PUT\|PATCH /auth/profile` | (none / authenticated) | `auth_service.dart`, `user_profile_service.dart` |
| `notifications.py` | `GET /notifications`, `GET /notifications/count`, `POST /notifications/mark-read`, `POST /notifications/mark-unread`, `GET\|POST /notifications/preferences` | (authenticated) | `notification_service.dart` |
| `devices.py` | `POST /devices/register`, `POST /devices/unregister`, `POST /devices/heartbeat` | (authenticated) | `push_notification_service.dart` |
| `admin_users.py` | `GET /admin/users`, `GET /admin/users/<id>`, `PUT\|PATCH /admin/users/<id>`, `POST /admin/users/<id>/activate\|deactivate`, `GET /admin/users/rbac-roles` | `admin.users.*` | `manage_users_provider.dart` |
| `admin_requests.py` | `GET /admin/access-requests`, `POST /admin/access-requests/<id>/approve\|reject`, `POST /admin/access-requests/approve-all` | `admin.access_requests.*` | `access_requests_provider.dart` |
| `admin_analytics.py` | `GET /admin/analytics/dashboard-stats`, `GET /admin/analytics/dashboard-activity`, `GET /admin/analytics/login-logs`, `GET /admin/analytics/session-logs`, `POST /admin/analytics/sessions/<id>/end`, `GET /admin/analytics/audit-trail`, `POST /admin/notifications/send` | `admin.analytics.view`, `admin.audit.view`, `admin.communication.manage` | `admin_dashboard_provider.dart`, `user_analytics_provider.dart`, `login_logs_provider.dart`, `session_logs_provider.dart`, `audit_trail_provider.dart` |
| `admin_content.py` | Templates CRUD, Assignments CRUD, Documents CRUD, Resources CRUD, Indicator Bank CRUD, Translations list/update (~18 routes) | `admin.templates.*`, `admin.assignments.*`, `admin.documents.*`, `admin.resources.*`, `admin.indicator_bank.*`, `admin.translations.*` | `templates_provider.dart`, `assignments_provider.dart`, `document_management_provider.dart`, `resources_management_provider.dart`, `indicator_bank_admin_provider.dart`, `translation_management_provider.dart` |
| `admin_org.py` | `GET /admin/org/branches/<country_id>`, `GET /admin/org/subbranches/<branch_id>`, `GET /admin/org/structure` | `admin.organization.manage` | `organizational_structure_provider.dart` |
| `public_data.py` | `GET /data/countrymap`, `GET /data/sectors-subsectors`, `GET /data/indicator-bank`, `POST /data/indicator-suggestions`, `GET /data/quiz/leaderboard`, `POST /data/quiz/submit-score` | (authenticated) | `indicator_bank_provider.dart`, `leaderboard_provider.dart`, `quiz_game_provider.dart` |

### Flutter AppConfig Constants
All mobile endpoints are defined as `static const String` in `MobileApp/lib/config/app_config.dart` under the `mobileApiPrefix` (`/api/mobile/v1`). Providers must **never** use inline path strings — always reference `AppConfig.*Endpoint`.

### API Versioning Policy
- Breaking changes require a new version prefix (`/api/mobile/v2`)
- Additive changes (new fields, new endpoints) are backward-compatible within v1
- `MOBILE_MIN_APP_VERSION` config key (e.g. `"1.2.0"`) rejects clients below that version with HTTP 426

### Files Reference
| File | Role |
|------|------|
| `app/routes/api/mobile/__init__.py` | Blueprint, version middleware, sub-module imports |
| `app/routes/api/mobile/auth.py` | Auth (token, refresh, SSO, logout, password, profile) |
| `app/routes/api/mobile/notifications.py` | Notification CRUD + preferences |
| `app/routes/api/mobile/devices.py` | Push device registration + heartbeat |
| `app/routes/api/mobile/admin_users.py` | User management |
| `app/routes/api/mobile/admin_requests.py` | Access requests |
| `app/routes/api/mobile/admin_analytics.py` | Dashboard, logs, audit trail, send notification |
| `app/routes/api/mobile/admin_content.py` | Templates, assignments, documents, resources, indicators, translations |
| `app/routes/api/mobile/admin_org.py` | Organization structure |
| `app/routes/api/mobile/public_data.py` | Country map, sectors, indicators, quiz |
| `app/utils/mobile_responses.py` | Standardized response envelope |
| `app/utils/mobile_auth.py` | JWT + session auth decorator |
| `app/utils/mobile_jwt.py` | JWT token issuance/decoding |

## HTML Sanitization Policy (Client-Side)

All client-side code that inserts dynamic HTML (via `innerHTML`, `outerHTML`, or `insertAdjacentHTML`) must follow these rules:

### Shared sanitizer: `SafeDom.sanitizeHtml(html)`
- **Location**: `app/static/js/lib/safe-dom.js`, loaded globally via `core/layout.html`.
- **Global alias**: `window.sanitizeHtml(html)` — available in all pages that extend `layout.html`.
- **What it strips**: `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<input>`, `<button>`, `<textarea>`, `<link>`, `<style>`, `<base>`, `<meta>` elements; all `on*` event handler attributes; all `style` attributes; `javascript:`, `vbscript:`, `data:` protocols on `href`/`src`/`action`.

### When to use which approach

| Scenario | Approach |
|---|---|
| Inserting **server-rendered HTML partials** (fetch → `.text()` → innerHTML) | `el.innerHTML = SafeDom.sanitizeHtml(html)` |
| Building HTML from **dynamic strings** (names, labels, values) | Use `escapeHtml()` / `escapeHtmlAttr()` for each interpolated value, or prefer DOM API (`createElement` + `.textContent` / `.value`) |
| **AI / chat HTML** (markdown-converted, streamed) | Chatbot has its own allowlist-based `sanitizeHtml` in the class; `traceSanitizeHtml` in trace_detail.html for traces |
| **Clearing** a container or inserting **static markup** | `innerHTML = ''` or static string literals — no sanitizer needed |

### Rules for new code
1. **Never** assign `fetch(...).then(r => r.text())` results directly to `innerHTML` without `SafeDom.sanitizeHtml`.
2. **Prefer DOM APIs** (`createElement`, `textContent`, `value`, `setAttribute`) over `innerHTML` when building UI from user/server data.
3. When `innerHTML` with template literals is unavoidable, **escape every interpolated value** with `escapeHtml()` for text context or `escapeHtmlAttr()` for attribute context.
4. Do not create new per-file sanitizer functions — use `SafeDom.sanitizeHtml` or `window.sanitizeHtml`.

## Template version field identity (`stable_key`)

Cross-version submission continuity uses a template-scoped logical id on structure rows:

- `form_item.stable_key` / `form_section.stable_key` (UUID, system-managed)
- Preserved on clone and Excel round-trip; auto-generated on new rows
- On **deploy**, `VersionDeployMigrationService.migrate_submission_fks()` bulk-remaps submission FKs from the archived published version to the new version where keys match

Query all version rows for one logical field:

```python
FormItem.by_stable_key(template_id, stable_key).all()
```

Operational scripts (run from `Backoffice/`):

- `python scripts/ops/template_version_scale_inventory.py` — per-template row counts before large deploys
- `python scripts/ops/backfill_stable_keys.py --dry-run` — one-time backfill for existing rows (run before first deploy migration in each environment)

See also [`Backoffice/docs/template-version-submission-identity.md`](../Backoffice/docs/template-version-submission-identity.md).

### Data API (`GET /api/v1/data`)

Unified submission data endpoint. Returns fact arrays plus dimension tables in one response.

| Array | Content |
|-------|---------|
| `data[]` | Static FormData rows (`field_type: static`). Matrix values are in `matrix_cells[]`, not nested here. `disaggregation_data`/`prefilled_disaggregation_data`/`imputed_disaggregation_data` ({mode, values}) are canonical; the raw on-disk `*_disagg_data` fields and `form_item_type` (on `form_items[]`, alias of `type`) are deprecated but retained for backward compatibility. |
| `dynamic_data[]` | Dynamic indicator rows |
| `dynamic_context[]` | Dynamic section bindings (e.g. emergency appeals) |
| `repeat_data[]` | Repeat-group field rows |
| `form_items[]` | Form items referenced by facts (`related=page` or `all`). `[assignment_year]` placeholders in labels/matrix column names are substituted when the request is scoped to a single assignment. |
| `countries[]` / `national_societies[]` / `indicator_bank[]` | Full dimension tables (~860 rows combined). Included by default for authenticated callers, omitted by default for public callers — see `include_dimensions`. |
| `matrix_cells[]` | Normalized matrix cells; matrix-specific fields grouped under `matrix` (`row`, `column`, `entity`). Includes calculated row/column/grand totals flagged via top-level `is_calculated_total`/`total_kind` (`row`\|`column`\|`grand`) — check before summing `value`, or pass `include_calculated_totals=false` to omit them. Some matrix items are configured (Form Builder → matrix item → Display → "Include Calculated Totals in API") to never emit `is_calculated_total` rows regardless of this flag — see `include_calculated_totals` below. |
| `assignment_statuses[]` | AssignmentEntityStatus rows for assigned `submission_id`s (workflow status / due date); join when `submission_type` is `assigned` |
| `arrays` | Catalog describing each top-level array (included/excluded, grain, key fields) |

**Legacy:** `GET /api/v1/data/tables` returns HTTP 308 redirect to `/api/v1/data` (same query string).

**Query parameters:** `template_id`, `assignment_id` (single or comma-separated `AssignedForm.id`s), `submission_id` (`AssignmentEntityStatus.id`), `item_id`, `stable_key`, `version_scope`, `country_id`, `country_iso2`, `country_iso3`, `period_name`, `indicator_bank_id`, `indicator_bank_ids`, `date_from`, `date_to`, `sort`, `order`, `related`, `layout` (`flat`|`star`), `include_dynamic`, `include_repeat`, `include_dimensions`, `include_calculated_totals`, `include_non_reported`, `page`, `per_page`, …

**`assignment_id` vs. `submission_id`:** the two are easy to confuse since both are colloquially "the assignment". `assignment_id` expects an `AssignedForm.id`; `submission_id` expects an `AssignmentEntityStatus.id` — the id used by `assignment_statuses[]`, workflow, and status views. Passing a submission id as `assignment_id` (with no other `assignment_id` in the same call) auto-resolves to the equivalent `submission_id` lookup; the 404 for any id that still fails to resolve names the id and suggests the swap.

**`include_dimensions`** (default `true` for session/API-key auth, `false` for public/unauthenticated): pass `false` on authenticated calls once `countries[]`/`national_societies[]`/`indicator_bank[]` are already cached client-side (e.g. via `/countrymap`, `/nationalsocietymap`, `/indicator-bank`) to shrink the response; pass `true` on public calls to opt into the full dimensions.

**`include_calculated_totals`** (default `true`): request-wide override — pass `false` to strip calculated row/column/grand totals from `matrix_cells[]` / `bridge_disagg_values[]` / `disaggregation_data` for every matrix in the response. This can only *remove* totals, never force them back in. Independently, each matrix item's `matrix_config.include_calculated_totals_in_api` flag (set via the Form Builder's matrix Display properties) controls the *default* for that item — it decouples on-screen totals (`show_row_totals`/`show_column_totals`, always shown to people filling in the form) from API/export exposure, so a form author can show totals in the UI while keeping them out of every API response and data export for that matrix, without callers needing to remember `include_calculated_totals=false`.

**Percentage values:** stored and entered as 0–100 (25 means 25%). The data-entry form shows a `%` suffix and warns if a value is between 0 and 1 exclusive (e.g. `0.2`), because that is often a mistaken fraction; it is **not** auto-converted to 20. `/api/v1/data` (flat and star) returns percentages as a **0–1 decimal** on `value` / `num_value` and in disaggregation / matrix cell numbers (25% → `0.25`, 100% → `1`). Counts and other numeric types are unchanged. Do not sum percentage `num_value`s across countries.

**Examples**

```http
GET /api/v1/data?template_id=33&related=all
GET /api/v1/data?template_id=12&stable_key=<uuid>
GET /api/v1/data?template_id=12&version_scope=all&layout=star
GET /api/v1/data?submission_id=1610&item_id=1403
```

**Star layout (`layout=star`, `schema_version: "1.2"`):** all facts live under `data.tables.fact_form_values` (static, dynamic, and repeat rows — filter by `field_type`); every row keeps its real `id`/`value`/etc. from the underlying FormData/DynamicIndicatorData/RepeatGroupData record. `matrix` is always `null` here (unlike `matrix_cells[].matrix` in the flat layout, a different, row/column/entity-grouped shape) — matrix cell values instead appear as a long array directly on `disaggregation_data`/`prefilled_disaggregation_data`/`imputed_disaggregation_data`: `[{row_entity_id, column_key, column_label, value, is_calculated_total?, total_kind?}, …]`. The same long array, keyed by `form_data_id`, is mirrored in `data.tables.bridge_disagg_values[]` for BI tools that prefer a dedicated bridge table over expanding a nested array.

## Troubleshooting (Common)

- **iOS `pod` / CocoaPods on Windows**: `pod` is not available on Windows; you cannot refresh `MobileApp/ios/Podfile.lock` locally. Use the **Regenerate iOS Podfile.lock** GitHub Action (see **Mobile App (Flutter)** above).
- **`/api/ai/v2/ws` not working**: ensure `flask-sock` is installed/enabled; HTTP/SSE endpoints can still work without websockets.
- **RAG returns nothing / errors after changing embedding model**: `AI_EMBEDDING_DIMENSIONS` must match the pgvector column; changing it requires a migration and re-embedding.
- **AI falls back / “no provider configured”**: set at least one provider key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure equivalents) and confirm model name via `OPENAI_MODEL`.
- **CSS changes not appearing**: run `npm run watch:css` in `Backoffice/` (and ensure `npm install` was run there).
- **New button class not applying / missing styles**: the `.btn` system lives in `components.css` (static file, always served). Tailwind utility classes go through `output.css` (compiled). If a new Tailwind class on a button is missing, run `npm run build:css`. If a `.btn-*` class is missing, check `components.css` is loaded (via `layout.html`).
- **Button appears rounded when it should be sharp**: do not add `rounded-*` Tailwind classes to buttons. The sharp-corner rule is enforced globally in `theme.css`; only `.rounded-full` is excluded (for FAB/circular buttons).