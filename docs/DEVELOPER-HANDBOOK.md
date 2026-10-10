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
python -m flask seed-test-data   # Testland, test users, focal points, sample assignments

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

# Seed test users (System Manager, Admin, Focal Point), extra focal points, and sample assignments
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

#### Models (`Backoffice/app/models/`)
There is no single `models.py`. Domain modules are re-exported from `app/models/__init__.py`:

- `core.py` — users, sessions, and account state
- `organization.py` — countries, entities, and org structure
- `forms.py` / `form_items.py` — templates, sections, and the unified form-item model (indicators, questions, document fields)
- `assignments.py` — assigned forms and entity status
- `indicator_bank.py` — centralized indicator repository
- `documents.py`, `rbac.py`, and the `ai_*.py` modules — documents, permissions, and AI jobs

#### Routes (`Backoffice/app/routes/`)
Packages, not the old flat modules (`forms.py`, `api.py`, `analytics.py` are gone):

- `forms/` — entry, submission, documents, matrix API, export, and validation summary (`forms/validation_summary.py`; `forms_validation_summary.py` is a shim)
- `forms_api.py` — authenticated form JSON API (still one module)
- `api/` — `/api/v1` plus `api/mobile/` for `/api/mobile/v1`
- `main/` — dashboard, assignments, and document views
- `public.py` — unauthenticated pages and legacy URL redirects
- `auth.py`, `ai.py`, `ai_ws.py`, `notifications.py`, `notifications_ws.py`, `excel.py`, `mcp.py` — still flat because each is one request surface

`admin/` is a mix of packages and remaining monoliths:

- Packages: `form_builder/`, `user_management/`, `organization/`, `system_admin/`, `reports/`, `utilities/`
- Still large single files: `assignment_management.py`, `content_management.py`, `ai_management.py`, `settings.py`, `api_management.py`, `data_sync_imputation.py`
- `notifications.py` serves the signed-in user until `/api/admin/assignments` (about line 1190); routes after that are the admin communication surface
- `shared.py` — decorators used by admin routes
- `route_policy.py` — CSRF and permission allowlists checked at startup

Public form templates live under `app/templates/forms/public/` (success and unavailable pages).

#### Services (`Backoffice/app/services/`)
Domain packages (`forms`, `organization`, `documents`, `security`, `imports`, `public`, `ai`). A few large modules are cohesive and should stay together: assignment-entity variable resolution, `FormDataService`, and `AIAgentExecutor`. Chat page copy and workflow replies are `ai/chat/page_explanations.py` and `ai/chat/workflow_responses.py`, re-exported from `ai/chat/helpers.py`.

#### Utilities (`Backoffice/app/utils/`)
Prefer `app/services/` for new domain logic. `utils/` holds request helpers, formatting, and authorization checks used by routes (`form_authorization.py`, `formatting.py`, `language_labels.py`, `request_validation.py`).

Three JSON envelopes are intentional and should not be merged:

| Module | Callers |
|---|---|
| `api_helpers.py` | External `/api/v1` (`json_response`, `api_error`, `error_id`) |
| `api_responses.py` | Admin and in-app AJAX (`json_ok`, `json_forbidden`, `json_not_found`) |
| `mobile_responses.py` | `/api/mobile/v1` only (`success` / `data` / `meta`) |

`/api/mobile/v1/data/countrymap` and the mobile sectors list are public reference data (rate-limited). The matching `/api/v1` routes stay API-key authenticated.

`/mcp` is intentionally public as well. See [Public MCP connector](#public-mcp-connector-mcp). Do not put `mcp:use` back in front of it unless the MCP client starts calling a non-public route.

#### Plugins
Shipped plugins live in `Backoffice/plugins/` (FDRS, UPR, emergency operations, interactive map, PB progress). `Backoffice/app/plugins/` is the loader, not a place to add plugin packages.

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
- Hosted IFRC/Azure translation is the default engine for EN, FR, ES, AR, RU, ZH, HI. LibreTranslate remains a local-dev fallback. A self-hosted NLLB sidecar (`services/nllb-sidecar`, compose profile `nllb`; CTranslate2 + pinned `facebook/nllb-200-1.3B`, CC-BY-NC 4.0, no external API) is available for mapped languages, including the core seven, when selected in the auto-translate UI. It does not fine-tune from glossary rows or knowledge-base files; those tools only constrain terms after translation. Opt in with `NLLB_SIDECAR_URL` (see `services/nllb-sidecar/README.md`). Admins: [`Backoffice/docs/user-guides/admin/nllb-translation.md`](../Backoffice/docs/user-guides/admin/nllb-translation.md).
- Gettext **values** live in `translation_string` (provenance, engine, status). `pybabel extract` / `.pot` stay the msgid source. Compiled `.mo` files remain the runtime path, but they are disposable: `flask translations compile-catalog` rebuilds every locale's `.po`/`.mo` from the POT plus the database, and `entrypoint.sh` runs it on each boot. Nothing about a container's translation state needs to survive a deployment.
- Because msgids come from extraction and not from the database, adding a new `_()` call in Python or Jinja means running `python scripts/i18n/extract_update_translations.py` (or **Regenerate Strings** on `/admin/translations/manage`) and committing the catalog. The string cannot be translated in the admin grid until the catalog lists it.
- Import existing catalogs with `flask translations import-catalog` (backfill `unknown_presumed_machine`), then `flask translations recover-provenance` to mark audited human edits. Seed must-terms with `flask translations seed-glossary` (Indicator Bank / Common Words → `translation_glossary_term`). Auto-translate reads those DB rows only: it keeps the English source term so the engine can set word order, then swaps unofficial renderings for the official target form. Add or edit terms on `/admin/translations/quality` — do not hardcode house terms or whole-phrase rows in code.
- Quality dashboard: `/admin/translations/quality` — Overview, Glossary, Inbox, and Unreviewed tabs. Glossary and Inbox use AG Grid (`GET /admin/translations/api/glossary-terms` and `…/glossary-candidates`). Engine eval (gated on a filled gold set): `python Backoffice/scripts/i18n/eval_translation_engines.py`.
- Knowledge Base language versions: on `/admin/ai/knowledge-base`, select the completed files for one publication → **Mark as same publication** (records deferred pairs; sentence-level TM stays off) → **Mine terminology**. Mining first joins shared `(ACRONYM)` expansions, then asks OpenAI to extract English glossary heads and pair them using embedding retrieval in each target document. A pair is stored only when the target wording appears in those retrieved chunks. Exact matches of an approved glossary form are dropped; a different form for the same source is flagged as a conflict. Review/accept (or edit) candidates on `/admin/translations/quality`. Accepting a conflict replaces the official term.

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
- Production propagation: `app/utils/translation_watcher.py` polls `translation_catalog_version` in all environments; a worker whose artifacts are behind rebuilds them from the database and refreshes Babel. Falls back to the `translations/.sentinel` mtime when the database cannot be read.

**Deploy notes**
- Run migrations: `add_rbac_language_scope`, `add_translation_review_tool_toggle`, `add_translation_quality`, `add_translation_catalog_version`
- Seed RBAC: `python -m flask rbac seed`
- No translations volume is needed. `entrypoint.sh` rebuilds `.po`/`.mo` from `messages.pot` + `translation_string` after migrations. Deployments still mounting Azure Files at `/data/translations` must run `flask translations import-catalog` **before** upgrading — see `Backoffice/docs/setup/persistent-translations.md`.

### AI System Configuration (Backoffice)
- **Chat API**: `/api/ai/v2` (chat, stream, conversations, export/import). WebSocket: `/api/ai/v2/ws`. Health: `GET /api/ai/v2/health` (anonymous callers get only `{"ok": bool}`; system managers / `admin.ai.manage` also get per-check detail incl. `agent_available` and the `?probe=embedding` probe).
- **Auth**: Session (Backoffice) or Bearer token (e.g. mobile). Issue tokens via `GET /api/ai/v2/token` (cookie session, or a mobile access token as Bearer: this exact path is allowed in `bearer_jwt_allowed_for_path`, so the mobile app works without a session cookie).
- **Environment**: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-5-mini`), `GEMINI_API_KEY`, `AZURE_OPENAI_*` for providers. `AI_EMBEDDING_PROVIDER`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIMENSIONS` (must match pgvector column; changing requires migration and possibly re-embedding). `AI_AGENT_ENABLED`, `AI_AGENT_MAX_ITERATIONS`, `AI_AGENT_TIMEOUT_SECONDS`, `AI_AGENT_COST_LIMIT_USD`, `AI_AGENT_MAX_COMPLETION_TOKENS` (default 32768; cap 128000 for large tables; use 4096 for GPT-4o). `AI_TOOL_OBSERVATION_MAX_ROWS_TABLE_RESULT` (default 250; cap 2000; rows sent from indicator/UPR “all countries” tools; increase for full country datasets). `REDIS_URL` optional for cross-worker rate limiting.
- **Supported models**: Depend on OpenAI account. Some models (e.g. GPT-5) reject sampling params; see `app.utils.ai_utils.openai_model_supports_sampling_params`.
- **Shared helpers**: `app.utils.ai_utils` (e.g. `openai_model_supports_sampling_params`, `sanitize_page_context`). RAG: `app.services.ai_vector_store`, `app.services.ai_embedding_service`. Agent: `app.services.ai_agent_executor`, `app.services.ai_tools_registry`. Shared chat request handling: `app.services.ai_chat_request` (parse, resolve conversation, idempotency).
- **Optional dependencies**: `flask-sock` required for WebSocket endpoints (`/api/ai/v2/ws`, document QA WS). Without it, AI HTTP and SSE still work. `redis` (and `REDIS_URL`) optional for cross-worker WebSocket rate limiting; in-memory limiter used otherwise. `pgvector` required for RAG document search; run migrations so `ai_documents`, `ai_embeddings`, `ai_document_chunks` exist. For full chat (non-fallback): at least one of `OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure/Copilot keys. For RAG embeddings: `OPENAI_API_KEY` when `AI_EMBEDDING_PROVIDER=openai`, or local model when `AI_EMBEDDING_PROVIDER=local` (dimensions must match DB).

### AI access policy (who may read what)

One policy object per request answers "which data may this principal read?" for AI tools, RAG retrieval, structured data retrieval and the document APIs. Code: `app/services/ai/policies/access_policy.py` (`AIAccessPolicy`, built once by `_bind_ai_request_policy` in `routes/ai.py` / `routes/ai_ws.py`, stored on `flask.g.ai_access_policy`, deny-by-default when absent), `app/services/data_retrieval/access.py` (`DataAccessPolicy`), `app/services/ai/documents/access.py` (`DocumentPrincipal`, `ai_document_read_filter`, `can_read_ai_document`). Enforcement happens **in the query** (SQL predicate), never by post-filtering results.

| Principal | Tools | Structured (form) data | AI documents |
|---|---|---|---|
| Anonymous (Website proxy, needs `AI_PUBLIC_PROXY_SECRET`) | Allow-list only (`PUBLIC_TOOL_ALLOWLIST`: indicator bank / public form values / public documents / workflow help); sources clamped to `historical`, `system_documents`, `upr_documents` | `privacy='public'` items that are submitted/approved, any country | `is_public` AND role check (only the `public` role token) |
| Authenticated user (incl. same org e-mail domain) | Full RBAC-gated catalog | Public items anywhere; non-public items and drafts **only for countries the user is assigned to** (`UserEntityPermission`) | Public (role check) + own uploads (owner scope check) |
| Focal point | Same as user | Same as user: own countries only | Same as user |
| Admin / countries manager / system manager, elevated API key | Full catalog | Every country | Every document (document admins: `is_admin`, system manager, `admin.documents.manage`, `admin.ai.manage`) |
| Internal jobs (`user_role="system_manager"` with no user) | n/a | n/a | Every document |

Same-organisation e-mail domain alone never widens access. `page_context.formBuilder` is honoured only for a cookie-session user holding `admin.templates.create|edit` whose `template_id`/`version_id` pass `check_template_access` (`authorize_form_builder_context`); otherwise it is dropped before DLP, tool selection and prompting (`trusted_form_builder_context()` is the only source executors read).

**Document ACL semantics** (`can_read_ai_document`, mirrored in SQL by `ai_document_read_filter`):

```
readable = document admin
        OR internal job
        OR ( is_public AND role_ok )                 -- world-readable, optionally role-restricted
        OR ( owner AND owner_scope_ok )              -- the uploader, while still in scope
role_ok        = allowed_roles IS NULL OR principal role tokens ∩ allowed_roles ≠ ∅   ([] = nobody)
owner_scope_ok = document is not a submitted document OR the owner still has access to one of its countries
```

`allowed_roles` only *restricts* public documents; it never grants access to a private one. Country tags are retrieval metadata and do not widen access. Role tokens are the user's access level (`user`, `focal_point`, `admin`, `system_manager`), RBAC role codes, and `authenticated`/`public`. Set via `PATCH /api/ai/documents/<id>` (`allowed_roles`) or the `allowed_roles` upload field (admins only). Ingested submitted documents are `is_public` only while the source is public **and** approved. Search, tools (`list_documents`, `search_documents*`, `analyze_unified_plans_focus_areas`, UPR KPI tools), full-document QA, download and the public Website document API all use the same predicate.

**Limits and budgets** (`app/services/ai/policies/usage_budget.py`; `0` disables): `AI_CHAT_DAILY_USER_LIMIT` (1500/day), `AI_CHAT_DAILY_MANAGER_LIMIT`, `AI_CHAT_DAILY_ANON_IP_LIMIT` (150), `AI_CHAT_DAILY_ANON_LIMIT` (all anonymous, 20000), `AI_CHAT_DAILY_SYSTEM_LIMIT`, `AI_DAILY_COST_BUDGET_USER_USD` (10), `AI_DAILY_COST_BUDGET_ANON_USD` (25), `AI_DAILY_COST_BUDGET_SYSTEM_USD` (250; cost is summed from `ai_reasoning_traces`). WebSocket messages re-check user status, AI-beta access and the cost budget on every message; the admin document WebSocket re-checks `admin.ai.manage` per question. If Redis is configured but unavailable the WS limiter falls back to a stricter per-worker in-memory limit instead of failing open. Anonymous chat without `AI_PUBLIC_PROXY_SECRET` is refused unless the process is an explicit local dev run (`FLASK_CONFIG` development/default + DEBUG + loopback client).

**Trace privacy** (`app/services/ai/quality/trace_privacy.py`): traces and tool-usage rows are stored redacted by default (`AI_TRACE_STORE_MODE=redacted|minimal|full`). `AI_TRACE_RETENTION_DAYS` (90) scrubs trace content and `AI_TOOL_USAGE_PAYLOAD_RETENTION_DAYS` (30) nulls tool inputs/outputs via the nightly `purge_ai_trace_content` scheduler job (`flask ai-trace-purge [--dry-run]`). Raw step observations in the admin trace viewer are shown only to system managers or holders of the permission named by `AI_TRACE_RAW_OUTPUT_PERMISSION`.

### Public MCP connector (`/mcp`)

`/mcp` is **intentionally public** (`MCP_PROXY_AUTH_MODE=public`). Claude and other remote connectors use the URL with no API key and no Backoffice login.

The September 2026 review locked this route because the proxy had no guard (`mcp:use`). That lock was reversed. The upstream process (`humanitarian-databank-mcp`) only issues anonymous GETs, and `databank_client.is_public_databank_read_path` refuses any other path (`/data` with the public filter, `/indicator-bank`, and `/public/*`). Requiring a key does not hide private form data or personal data. It only blocks the connector.

Do not default the proxy back to `required`, and do not treat a missing `mcp:use` check as an open finding, while that client still only calls those paths. Set `MCP_PROXY_AUTH_MODE=required` in the same change that adds a non-public call. `admin.mcp.use` and the `mcp:use` capability apply only in that mode. Any other value of `MCP_PROXY_AUTH_MODE` fails closed to `required`.

Controls that stay on in public mode: caller cookies and `Authorization` are stripped before the upstream hop, the upstream host goes through `app/utils/outbound_url.py`, the body is capped, and the route is rate-limited per IP (default 120/minute). A browser that already has a Backoffice session cookie still has to pass CSRF on POST.

**Outbound requests and exports**: server-side fetches to admin/user-influenced URLs (MCP upstream, LibreTranslate, IFRC document fetch) go through `app/utils/outbound_url.py` (https only, no credentials, host allow-list where applicable, private/link-local/metadata ranges blocked after DNS resolution, redirects re-validated). Every CSV/XLSX writer must use `app/utils/export_safety.py` (`safe_csv_writer`, `safe_csv_dict_writer`, `sanitize_workbook`, `sanitize_dataframe`) so cells starting with `= + - @ TAB CR` are neutralised.

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
- Idle timeout and revocation apply to every cookie-authenticated request (including `/api/` paths); Bearer JWTs authenticate only under `MOBILE_JWT_BEARER_PATH_PREFIXES` (default `/api/mobile/v1/`).
- **Client IP has one source:** `app.utils.client_ip.get_client_ip()` (= `request.remote_addr` after ProxyFix with `PROXY_FIX_X_*` hops). Never read `X-Forwarded-For` / `request.remote_addr` directly in routes; use `is_loopback_request()` for dev-only loopback gates.
- **Revocation/rotation state is shared** (`app/utils/auth_state.py`: Redis, else Postgres `auth_state_entry`), never per-process. Mobile refresh tokens are single-use with family revocation on reuse. `FLASK_CONFIG` unset means production. A missing `MOBILE_JWT_SECRET` or `ENABLE_SSH` is flagged on System Configuration and does not block startup. Details, env vars and upgrade notes: [`Backoffice/docs/setup/security.md`](../Backoffice/docs/setup/security.md#authentication-sessions-and-perimeter).

### API Structure
- RESTful endpoints under `/api/v1/`
- Authentication varies by surface area (session auth in Backoffice UI; bearer/JWT used by some API clients)
- CORS enabled for frontend integration
- Request/response tracking and monitoring
- **API key authorization is capability-based and centrally enforced.** Every route that accepts a DB API key must declare exactly one capability via `@require_api_key(capability=..., scope_aware=...)`, `@require_api_key_or_session(capability=...)`, or `@api_capability(...)` plus `authenticate_api_request()` in the view. Routes without a capability are denied for keys (fail closed), and `undeclared_key_routes(app)` is tested to stay empty. Scopable capabilities (`data:read`, `submissions:read`, `templates:read`) must apply the key's data scope on lists **and** detail routes (`apply_api_key_data_scoping`, `api_key_scope_allows`) or leave `scope_aware=False` so scoped keys are refused. Vocabulary and parser: `app/services/security/api_key_permissions.py`. Details, route classification and migration: [`Backoffice/docs/setup/api-keys-and-permissions.md`](../Backoffice/docs/setup/api-keys-and-permissions.md).

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
- **`|safe` policy:** `|safe` is only for (a) `|tojson|safe` / `escapejs` / `safe_json_attr` output, (b) values that are already `Markup` produced by an escaping helper, or (c) trusted, developer-authored macro arguments (e.g. `excel_io_modal`, `_page_header` action content). For admin- or user-authored HTML use **`|rich_text`** (re-applies the allow-list at render time). Never `|safe` request, DB or API values directly. Hand-built HTML in Python (f-strings) must `markupsafe.escape` every interpolation and return `Markup`. Plugin `panel_template` output is trusted only through `_render_panel_template` (see [plugin panel contract](#plugin-data-explorer-panel-contract)).

### Safe primitives (injection & resource limits)

Use the shared primitive; do not hand-roll. A guard test fails the build if the pattern reappears.

| Threat | Primitive | Guard test |
|---|---|---|
| `LIKE`/`ILIKE` wildcard injection (`%`, `_`, `\` in user input) | [`app/utils/sql_utils.py`](../Backoffice/app/utils/sql_utils.py): `ilike_contains`, `ilike_prefix`, `ilike_equals`, `like_contains`, `safe_ilike_pattern`, `escape_like_wildcards`; for SQLAlchemy string ops `col.contains(x, autoescape=True)` / `startswith(x, autoescape=True)` | `tests/unit/test_utils/test_sql_like_safety.py` (AST scan of `app/`, `plugins/`, `scripts/`) |
| DOM XSS in Backoffice JS | [`app/static/js/lib/safe-dom.js`](../Backoffice/app/static/js/lib/safe-dom.js) (`window.SafeDom`): `escapeHtml` (escapes quotes), `safeUrl` / `safeHrefAttr` / `setHref` / `setSrc` / `openWindow` / `navigate` (http/https + same-origin allow-list, control-char and entity-obfuscation aware), `html` tagged template + `raw`, `setHtml`, `sanitizeHtml` (allow-list; `allowControls` for plugin config forms). There is **no identity fallback**: if `SafeDom` is missing, render text via `textContent`. Prefer DOM APIs / `textContent`; never concatenate data into `innerHTML` without `SafeDom.escapeHtml`. | `tests/js/lib/safe-dom.test.js` (`npx vitest run tests/js/lib`) |
| Email header / envelope injection | [`app/utils/email_headers.py`](../Backoffice/app/utils/email_headers.py): `sanitize_header_value`, `sanitize_subject`, `sanitize_filename`, `validate_email_address`, `sanitize_sender`. `services/email/client.send_email` applies them to subject, sender and every To/Cc/Bcc address (invalid recipients are dropped and logged; nothing valid left = `no_recipients`; bad sender = `invalid_sender`). | `tests/unit/test_utils/test_email_headers.py` |
| Open redirects | [`app/utils/redirect_utils.py`](../Backoffice/app/utils/redirect_utils.py): `is_safe_redirect_url` (root-relative or same-origin http(s) only; rejects `//`, backslashes, control characters, userinfo, encoded/NFKC-normalised variants), `safe_redirect`, `get_safe_redirect_url`. Never call `redirect(<user value>)`. For stored external URLs use `external_url_validation.safe_external_redirect_target`. | `tests/unit/test_utils/test_redirect_utils.py` |
| Zip/XML bombs and huge sheets in spreadsheets | [`app/utils/safe_workbook.py`](../Backoffice/app/utils/safe_workbook.py): `load_workbook_safe`, `read_excel_safe`, `inspect_xlsx`, `safe_iter_rows` (raw size, member count, uncompressed size, per-member ratio, declared rows/cols, sheet count, all checked **before** openpyxl parses; `read_only=True` by default). Limits: `WORKBOOK_MAX_*` config. Never call `openpyxl.load_workbook` / `pd.read_excel` on uploaded data. CSV/JSON uploads: `app/utils/file_parsing.py` (`read_stream_capped`, `load_json_upload`, `MAX_CSV_ROWS`). | `tests/unit/test_utils/test_safe_workbook.py` (includes a tree scan for raw loaders) |
| Decompression bombs / runaway OCR | [`app/utils/safe_image.py`](../Backoffice/app/utils/safe_image.py): `open_image_safe` (pixel budget from the header, `DecompressionBombWarning` is fatal), `clamp_dpi` / `clamp_render_scale` for PDF page rasterisation, `ocr_image_to_string` (tesseract timeout + downscale). | `tests/unit/test_utils/test_safe_image.py` |
| Exception text leaking to clients | `raise ClientInputError(...)` for deliberate, user-presentable validation messages and `client_error_message(exc)` in `except ValueError` blocks ([`app/utils/api_errors.py`](../Backoffice/app/utils/api_errors.py)); `handle_json_view_exception(e, GENERIC_ERROR_MESSAGE)` for everything else. Never `json_*(str(e))` from `except Exception`. | `tests/unit/test_utils/test_error_exposure.py` |
| Scanner outages / SSRF | `FILE_SCANNER_FAIL_OPEN=true` outside DEBUG logs a CRITICAL warning (uploads pass unscanned); default is fail-closed. `CLOUD_SCANNER_URL` is validated with `app.utils.outbound_url.validate_outbound_url` (https, no private/link-local/metadata; private scanners must be listed in `CLOUD_SCANNER_ALLOWED_NETWORKS`), redirects are not followed. | `tests/unit/test_utils/test_file_scanning_extended.py` |

### File Uploads
- Document management system
- PDF thumbnail generation
- Resource file organization by language

#### Serving files without login (public documents, logos, template images)

Rules for any route that returns a stored file to an unauthenticated or low-privilege caller:

1. **Authorization is the control; ids are defense in depth.** A document is publicly downloadable only when `SubmittedDocument.public_submission_id` is set **and** `is_public` **and** status is `approved` (thumbnails/cover images: `is_public` + `approved`). The policy lives in [`app/services/documents/public_access.py`](../Backoffice/app/services/documents/public_access.py); do not re-implement it in a route.
2. **Public URLs use the opaque `SubmittedDocument.public_id` (UUIDv4), never the integer primary key.** Build them only with `public_document_download_url` / `public_document_display_url` / `public_document_thumbnail_url`. The integer routes (`/forms/public-document/<int>/download`, `/documents/{display,thumbnail}/<int>`, `/public_documents/download/<int>`) remain for existing links: they apply the same policy, the download routes then 302 to the opaque URL with a `Deprecation: true` header, and denied and unknown ids are indistinguishable (404).
3. **Rate-limit unauthenticated downloads** with `@limiter.limit(public_access.public_download_rate_limit)` (default `60 per minute` per client IP; override with `PUBLIC_DOWNLOAD_RATE_LIMIT`).
4. **Always stream through `storage_service.stream_response`.** It adds `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; sandbox`, and forces `attachment` for active content (HTML, SVG, XML, JS, CSS) even when `as_attachment=False`. Inline PDFs get `nosniff` only (Chrome's viewer cannot render under `sandbox`). `add_security_headers` keeps a CSP that is already on the response. Do not use raw `send_file` / `send_from_directory` for user-supplied files.
5. **Never redirect to a stored URL** (`source_url`, FDRS-synced values) without `app.utils.external_url_validation.safe_external_redirect_target` (https + `IFRC_DOCUMENT_ALLOWED_HOSTS`, default port, no credentials, fail closed).
6. **Branding uploads accept raster images only** (PNG, JPEG, GIF, WebP; ICO for favicons), verified by decoding with Pillow so content must match the extension. SVG is not accepted; a bundled static `logo.svg` can still be set through the path field. Legacy uploaded SVGs are served as sandboxed attachments.
7. **Template images** (`/forms/template-image/<item>/<path>`): logged-in users, or anonymous visitors presenting `?public_token=<AssignedForm.unique_token>` of an active public form whose published version contains the item (the URL builder adds the token on the public form page). The old `?preview=` bypass no longer exists.

Migration `add_submitted_document_public_id` adds and backfills `submitted_document.public_id` (unique index `uq_submitted_doc_public_id`); downgrade drops it. Signed expiring URLs (`URLSafeTimedSerializer`) or per-submission tokens are the right tool if submitters ever need to view their own *unpublished* uploads; they are not needed for published documents.

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

### Object-Level Authorization (child ids, assignments, lookup lists)
Any route that takes an id of an object owned by an assignment (`RepeatGroupInstance`, `DynamicIndicatorData`, `SubmissionDiscussionComment`, `FormData`, ...) must resolve the **owner** and authorize the acting verb on it. `@login_required` plus "the id exists" is not authorization, and neither is `EntityService.check_user_entity_access` alone (it lets any `admin.*` holder through).

All helpers live in [`app/utils/form_authorization.py`](../Backoffice/app/utils/form_authorization.py) and delegate to `AuthorizationService.can_access_assignment` / `can_edit_assignment` / `can_submit_assignment` (RBAC-, entity-scope-, status- and round-aware - the same rules the entry page uses):

| Need | Helper |
|---|---|
| Child id in the URL/body (repeat instance, dynamic indicator, ...) | `authorize_child_json(Model, id, AES_ACTION_VIEW/EDIT/SUBMIT, label=...)` -> `(ChildAccess, None)` or `(None, response)` |
| AES id in the request | `authorize_aes_json(aes_id, action, forbidden_message=...)` |
| Already-loaded objects | `check_aes_action(aes, user, action)` / `authorize_child(obj, user, action)` -> `AUTH_OK` / `AUTH_HIDDEN` / `AUTH_FORBIDDEN` |
| Public submissions (country-scoped, not AES-scoped) | `public_submission_access(submission, user, PUBLIC_SUBMISSION_ACTION_VIEW/EDIT/MANAGE)` |
| Template structure (mobile) | `user_can_access_template(user, template_id)` |
| Lookup-list rows | `user_can_read_lookup_list(user, list_id)` |
| Status transitions (approve / reopen / return / page actions / admin overrides) | `begin_aes_transition(aes, user, permission=..., allowed_from=...)` - see *Locking status transitions* below |
| Bulk transitions / imports over many AES rows | `lock_aes_rows_for_update(ids, assigned_form_id=...)` (ascending id order) |
| Submit / send for review / save on the entry page | `lock_aes_for_update(aes)` (True when the row moved meanwhile); `forms.entry` calls it on every POST |

**Error policy.** A child addressed by its *own* id that is missing or not visible to the caller returns an opaque **404** (existence is not disclosed; unknown and out-of-scope look identical). If the caller can view the owner but the verb is denied (read-only user, submitted/locked assignment) the response is **403**. Requests that carry an AES id return **403** "Assignment not found or access denied" (the `ensure_aes_access` convention). An orphaned child (no owner) is reachable by System Managers only.

Lookup lists are global reference data with no owner. Numeric (admin-managed) lists are readable when a template the user can reach references them, or by System Managers / template and assignment admins; system lists (`country_map`, `national_society`, `indicator_bank`) and plugin lists stay open to authenticated users. Row responses are capped at 5000 with a `truncated` flag.

Mobile (`@mobile_auth_required`) routes follow the same rules as their web counterparts: the write routes require the exact web permission (`permission=`, not the any-of `permissions=`), record `log_admin_action`, and send the same notifications. The anonymous `POST /api/mobile/v1/data/indicator-suggestions` is protected by a shared-store rate limit, strict payload validation (`app/utils/suggestion_intake.py`), DB-backed per-email and global caps (`SUGGESTION_PER_EMAIL_DAILY_LIMIT`, `SUGGESTION_GLOBAL_HOURLY_LIMIT`) and an optional reCAPTCHA token (`MOBILE_SUGGESTION_REQUIRE_CAPTCHA=true`).

#### Locking status transitions (TOCTOU)
Every write to `AssignmentEntityStatus.status` (via `apply_entity_status_change` or directly) must hold the row lock and validate against the **locked** row, otherwise two concurrent requests both pass the "allowed from this status" check and transition twice (double notifications, approve over a just-reopened form).

1. Take `SELECT ... FOR UPDATE` on the AES row with `begin_aes_transition` (single row) or `lock_aes_rows_for_update` (many rows).
2. Re-validate on the locked row: `allowed_from=` (source statuses) and `permission=` (an `AuthorizationService.can_*` predicate, evaluated after the lock so status-dependent rules see the fresh status). The result has `ok`, `reason` (`ok` / `gone` / `stale_status` / `forbidden`) and `changed` (another transaction moved the row since it was loaded).
3. Only then write. Refuse with a redirect/flash (web) or JSON error, never by raising.

Rules that make this safe:
- The lock lasts until the request transaction ends. `transaction_middleware` commits at `after_request` for status < 400 and rolls back for >= 400 or exceptions, so keep the lock -> validate -> write sequence in one request and never `db.session.commit()` between the lock and the write. `FormDataService._commit_or_flush` only flushes in managed requests; routes marked `@no_auto_transaction` own their commit.
- Lock order is always **AES rows in ascending id, then dependent rows** (`AssignmentPageStatus`, child data). `lock_aes_rows_for_update` sorts ids and uses `ORDER BY id FOR UPDATE OF assignment_entity_status`; bulk paths must not lock rows one by one in request order or two overlapping bulk actions can deadlock.
- The approve route only accepts `submitted`, return-for-revision only `sent_for_review`; reopen / page actions rely on their `can_*` predicate (which already encodes the source status).
- Admin overrides (`update_entity_status`, `bulk_update_entity_status`, `edit_assignment_entity_status`) may set any status but still lock, so they serialize with user transitions and fail cleanly when the entity was removed meanwhile. Batch importers (FDRS status sync, UPR PNS pending reset) lock their rows up front for non-dry runs and hold them until the run commits.
- The tests in `tests/integration/test_assignment_transition_locking.py` run real Postgres lock contention (one thread and DB connection per request); add new transition routes there.

### Presence Tracking (Do Not Use `user_activity_log`)
- Live presence heartbeat endpoints (`/api/forms/presence/...`) should use cache/memory (Redis when available, in-memory fallback), not `user_activity_log`.
- `user_activity_log` is for meaningful audit/activity events; high-frequency heartbeat noise should not be written there.
- If a durable "last active" timestamp is needed for user features, store it on the `user` record (e.g., dedicated datetime field) with write throttling, rather than logging every heartbeat.

### Adding Details to an Audit Trail Row
Most admin mutations are recorded automatically by `activity_middleware`, which only knows the endpoint, method and status code — so the Audit Trail "Details" panel is empty unless the view says what changed.

- Call `set_audit_details(**fields)` and `set_audit_description(text)` from `app.utils.audit_context`. Both enrich the single `UserActivityLog` row the middleware already writes; view-supplied keys override anything the middleware inferred.
- Prefer humanized keys and values (resolved names, `Yes`/`No`, `before → after` strings). `details_service.humanize_audit_details_dict` renders them and hides request metadata, secrets and bare numeric IDs. See `app/services/audit/assignment_audit.py` for the pattern.
- Only reach for `log_admin_action(old_values=..., new_values=...)` when the blueprint is listed in `ADMIN_BLUEPRINTS_WITH_EXPLICIT_LOGGING` (`activity_logging_skip.py`); otherwise you get a duplicate row, because the middleware still logs the same POST.
- Cap collections — a bulk action can span every country on the platform.
- Wrap enrichment so it cannot fail the mutation it describes.

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
| FDRS plugin | [`Backoffice/plugins/fdrs/`](Backoffice/plugins/fdrs/) — backend-only Federation-wide Databank & Reporting System: data-api sync, document fetch, matrix validation, quality methodology, and publication to the public FDRS website (see [FDRS publication](#fdrs-publication-published_value) below). No Data Explorer tab. |
| UPR plugin | [`Backoffice/plugins/upr/`](Backoffice/plugins/upr/) — Unified Plan (template 24) / Report (template 33): live dashboards, Excel import/export, GO-API document import, and AI/RAG document intelligence. PNG/PDF/InDesign download; optional Word-narrative PDF or InDesign package; bulk PNG export on the Data Explorer **UPR** tab (replaces Tableau `UPR.twb`). Public landscape gallery of the same plans and reports as the mobile app, for a Power BI HTML visual: `GET /api/v1/upr/documents` (`?format=powerbi` returns the iframe snippet). Temporary People reached remapping: [`people-reached.md`](../Backoffice/plugins/upr/docs/people-reached.md) |
| Standalone tool scripts | `Backoffice/plugins/<id>/visuals/` (or similar subfolder) |

**To add a new admin-feature plugin:**

1. Create `Backoffice/plugins/<plugin_id>/plugin.py` subclassing `BasePlugin`.
2. Return `[]` from `get_field_types()` if the plugin has no form fields.
3. Implement `get_blueprint()`, and optionally `get_data_explorer_tab()`, `get_seed_permissions()`, `get_seed_roles()`, `get_csp_overrides()`, `get_panel_render_context()`, `get_api_endpoints()` (rows merged into Admin → API Management).
4. Add routes, services, templates under the same plugin folder.
5. No core app file changes required — `PluginManager` discovers `plugin.py` at startup.

**To unplug:** delete the plugin folder. Core Data Explorer tabs remain.

**Lifecycle semantics** (details in [`Backoffice/plugins/README.md`](../Backoffice/plugins/README.md)): admin-feature plugins are always on and cannot be deactivated; every other plugin's blueprint is registered at start and 404s while the plugin is inactive (state is shared across workers through `plugin_states.json`); a plugin declares prerequisites with `get_required_plugins()` (FDRS requires `pb_progress`); bundled plugins cannot be uninstalled from the UI; ZIP upload is System Manager only and off unless `PLUGIN_UPLOAD_ENABLED` is set; stored API keys in plugin settings are redacted in responses (`BasePluginRoutes(secret_paths=...)`).

#### Plugin Data Explorer panel contract

A plugin contributes a Data Explorer tab by returning a `DataExplorerTabConfig` with a `panel_template`. The core renders it in `app/routes/admin/data_exploration._render_panel_template` and embeds the result **without** `|safe` (the value is `Markup`). This is the only place plugin HTML is trusted, so panels must obey:

- `panel_template` must be a relative `.html`/`.htm` template path (no `..`, no leading `/`); other suffixes disable Jinja autoescaping and are rejected.
- Render with `{{ value }}` (autoescaped). Do **not** use `|safe`, `Markup(...)` or `{% autoescape false %}` on request-, DB- or API-derived data. JSON for scripts must go through `|tojson`.
- Context comes only from `get_panel_render_context()`; keep it to ids, flags and pre-escaped/Markup values. Inline scripts need `nonce="{{ csp_nonce() }}"`.
- Failures render an empty panel and are logged; a panel must not depend on exceptions for control flow.
- Field-type entry templates receive `config_json` as `Markup` from `htmlsafe_json_dumps` (safe inside `<script type="application/json">` with plain `{{ config_json }}`); `existing_data_json` is a plain string for attribute use (`{{ existing_data_json | e }}`).

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

*(Historical exception, not a pattern to repeat: a handful of older migrations — `add_reports_permissions`, `add_validation_admin_permissions`, `migrate_data_explorer_permissions`, `rename_admin_notifications_rbac_to_communication` — do write `rbac_permission`/`rbac_role` rows directly, predating this policy. `add_validation_admin_permissions` also backfilled extra permissions onto `admin_data_explorer_compliance` — see the callout in `_baseline_roles()` and the pitfall below. `add_reports_permissions` once did the same for `admin_data_explorer_analysis`; that grant was later removed so Analysis does not open the report builder.)*

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

**Pitfall — migration backfill onto an existing baseline role:** if a migration grants extra permissions directly to a role that's *also* defined in `_baseline_roles()` / a plugin's `get_seed_roles()` (e.g. to preserve access when splitting a permission in two), you **must** add those same codes to that role's `permission_codes` in code too. The reconciliation step in `seed_rbac_permissions_and_roles()` deletes any `rbac_role_permission` link for a catalog permission that isn't in the role's declared `permission_codes` — so a migration-only grant on a seeder-managed role survives only until the next `flask rbac seed` run (which, since `entrypoint.sh` runs it on every deploy, means the *next deploy*). `admin_data_explorer_compliance` still lists `admin.validation.{dashboard,questions,rules}` (backfilled by `add_validation_admin_permissions`) and that list is pinned by `TestBaselineRolesPreserveMigrationBackfilledPermissions`. `admin_data_explorer_analysis` no longer lists `admin.reports.{view,edit}`: the `add_reports_permissions` backfill was revoked on purpose, and the same test fails if those codes are added back. A role backfilled by a migration but **not** tracked in `_baseline_roles()`/a plugin (e.g. a custom role created via the admin UI) is safe from this — the reconciliation loop only ever touches roles it knows about.

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

- **Startup audit** — `audit_admin_route_guards()` in `app/startup_tasks.py` (findings collected by `collect_admin_route_guard_findings()`, rules in [`app/routes/admin/route_policy.py`](../Backoffice/app/routes/admin/route_policy.py)) walks `app.url_map` for every `/admin` rule plus `/plugins/static` and warns (or raises, if `RBAC_ADMIN_ROUTE_GUARD_MODE=error`/`strict`) about: `missing_guard` (no guard decorator and no `rbac_guard_audit_exempt`), `non_admin_permission` (guarded only by a non-`admin.*` code), `read_permission_on_mutating_route` (POST/PUT/PATCH/DELETE behind a `*.view` code; read-only POST lookups are listed in `READ_ONLY_POST_ALLOWLIST`), `get_side_effect_name` (GET-only view named `cleanup_*`/`delete_*`/`send_*`/`test_*`...), `csrf_exempt_mutation` (CSRF-exempt mutation not in `CSRF_EXEMPT_MUTATION_ALLOWLIST`), and the per-endpoint policy tables (`SYSTEM_MANAGER_ONLY_ENDPOINTS`, `POST_ONLY_ENDPOINTS`, `REQUIRED_PERMISSION_BY_ENDPOINT`). `tests/unit/test_routes/test_admin_rbac_scope_hardening.py::TestGuardAudit` fails if the live app has any finding, if a policy entry names an endpoint that no longer exists, and proves each finding kind fires on a synthetic route.
- **Catalog completeness test** — [`tests/unit/test_rbac_catalog_completeness.py`](../Backoffice/tests/unit/test_rbac_catalog_completeness.py) walks every registered view function's RBAC metadata (web + mobile) plus every baseline/plugin role's `permission_codes`, and asserts each referenced code exists in `_permission_catalog()` + `_extension_permission_catalog()`. Also guards against duplicate permission/role codes across core + plugins, and pins the compliance-role validation backfill from the pitfall above so those codes can't be trimmed from `_baseline_roles()` by accident. The same test asserts `admin_data_explorer_analysis` does not include report-builder permissions. Catches a **typo'd/renamed** code — the class of bug where the guard exists but silently protects a permission that no non-System-Manager role can ever hold.
- Neither check can verify *which* permission a route ought to have — only that a guard exists and that whatever it names is real. Code review still has to confirm `admin.foo.edit` is the *right* code for a given route (e.g. matching the equivalent HTML/JSON/mobile route for the same action).

### Privilege-escalation guard (RBAC role assignment)

Only a System Manager may grant/revoke the `system_manager`, `admin_full`, or `admin_plugins_manager` roles. The codes are centralized once in `_RESTRICTED_RBAC_ROLE_CODES` ([`app/routes/admin/user_management/helpers.py`](../Backoffice/app/routes/admin/user_management/helpers.py)) and imported by every call site that assigns roles: `admin/user_management/crud.py` (HTML), `admin/user_management/api.py` (JSON), `api/mobile/admin_users.py` (mobile).

`_critical_rbac_roles_integrity_ok(restricted_codes, restricted_role_ids)` gates all three call sites: if RBAC hasn't been seeded at all yet, there's nothing to enforce (returns `True`); if it *has* been seeded but one of those three role codes can't be resolved (renamed, corrupted, deleted out-of-band), it **fails closed** — RBAC role assignment is disabled entirely for non-System-Managers until `flask rbac seed` is re-run — rather than silently letting through whichever restriction couldn't be verified.

### Canonical guard and permission model (admin routes)

- **Canonical decorator:** `@permission_required('admin.<area>.<action>')` (or `permission_required_any`). An `admin.*` code can only come from a role or a *global* allow grant, which is exactly what `AuthorizationService.is_admin` tests, so it already implies the admin gate — `@admin_required` on top is redundant. The audit enforces the `admin.` prefix (non-`admin.` codes only for the `assignment.`/`documents.` families that carry their own object rules).
- **`@admin_required` alone** is only for pages open to every admin whose view performs an object-level check (e.g. import change logs). **`@system_manager_required`** (stacked under `admin_required`/`permission_required`) is for platform-level capabilities. `admin_permission_required` is a shorthand for the combination.
- **Read permissions never guard mutations.** Destructive housekeeping uses `admin.system.maintain` (end sessions, session cleanup, clear monitoring logs); resolving security events uses `admin.security.respond`; hard-deleting a country uses `admin.countries.delete`; writing Data Explorer imputed values uses `admin.data_explore.impute` (on top of `admin.data_explore.data_table`).
- **System Manager only:** plugin install / upload / uninstall (the archive is extracted into the plugins directory and imported as Python — remote-code-execution equivalent) and the monitoring error-notification test. Plugin upload additionally needs `PLUGIN_UPLOAD_ENABLED=true` (`config/config.py` enables it by default only for development/testing; with no configured value the route treats it as off); activating/deactivating/configuring plugins stays on `admin.plugins.manage`.
- **GET is safe and idempotent.** Side-effecting endpoints are POST-only (CSRF-protected). The one deliberate GET that mints a token is `/admin/api/refresh-csrf-token` (needed after a POST already failed on an expired token); it refuses `Sec-Fetch-Site: cross-site` and is `no-store`.
- **Scope is enforced server-side, not by the UI.** `admin.*` permissions are global by default; object-level actions must additionally check scope: countries (`AuthorizationService.has_country_scoped_permission`, honours entity-scoped `RbacAccessGrant` deny/allow), Data Explorer rows (template access + country access, same rules as `apply_user_template_scoping`), import logs (System Manager, `admin.audit.view`, or the initiating user).
- **Delegated administration (entity grants):** `AuthorizationService.can_delegate_entity_access(actor, entity_type, entity_id)` — System Managers everywhere; country-linked entities for actors with global country scope (`admin.countries.view|edit`, `admin.organization.manage`) or who hold the entity/its country themselves; Secretariat entities for `admin.organization.manage` or holders of the entity/its parent. Adding/removing a grant additionally refuses self-changes and admin/System Manager targets unless the actor is a System Manager. Form edits use `apply_scoped_entity_replace`, which never deletes rows the actor could not have granted.
- **Role assignment:** non-System-Managers cannot hand out restricted roles, `admin_*` roles they do not hold, or any role that bundles an `admin.*` permission they do not hold (`_role_ids_blocked_for_actor`); `GET /admin/api/rbac/roles` lists only assignable roles.

**Upgrade notes (no migration required; run `flask rbac seed`, which every deploy does):**

- New permissions: `admin.system.maintain`, `admin.countries.delete`, `admin.data_explore.impute`. New role `admin_system_maintainer` (analytics view + maintain). `admin_countries_manager` gains `delete`; `admin_data_explorer_data_table` gains `impute`; `admin_full` gains `delete`/`impute` but **not** `admin.system.maintain`, `admin.settings.manage` or `admin.plugins.manage` (those stay explicit grants).
- Behaviour changes for existing users: holders of only `admin.analytics.view` (including `admin_full`) can no longer end sessions / clean up sessions / clear monitoring logs until assigned `admin_system_maintainer`; `admin_plugins_manager` holders can no longer install/upload/uninstall plugins; custom roles that bundle the split-off actions must be given the new codes by an operator (the seeder does not touch custom roles). Non-System-Manager user managers can only delegate entity access within their own scope.
- Config: set `PLUGIN_UPLOAD_ENABLED=false` (or leave unset in production) to disable ZIP upload, and optional `PLUGIN_PUBLIC_STATIC_PLUGINS` (plugin ids whose `/plugins/static/<id>/...` assets may be fetched anonymously; default none — everything else requires login).

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

Repo helper (sets the right subscription): `azure_webapp_tools.bat prod logs` or `staging logs`.

Inspect a `/admin/security/events/<id>` row on the live DB (read-only; uploads `scripts/ops/inspect_security_event.py` over SSH):

```bash
azure_webapp_tools.bat prod security-event 894
azure_webapp_tools.bat prod security-event --list --unresolved --severity high
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
- **Business services (by domain)**: `Backoffice/app/services/` — subpackages include `forms/`, `data_retrieval/`, `organization/`, `validation/`, `platform/`, etc. FDRS- and UPR-specific services live in `Backoffice/plugins/fdrs/` and `Backoffice/plugins/upr/`.
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
| `app/templates/macros/excel_import_dropzone.html` | Shared two-state Excel file dropzone (drag/drop, optional validation status panel). Configure via macro params (`variant`, `validate_url`, `multiple`, copy) and `{% call %}` for hidden fields. JS: `initExcelImportDropzone()` in `app/static/js/components/excel-import-dropzone.js` — set `multiple=true` so browse and drop keep every accepted file. |
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

Deploy semantics worth knowing:

- Identity is **never overwritten by position**: a row that already has a key keeps it. Positional pairing only backfills legacy rows whose key is `NULL`, and only when a position is held by exactly one row on each side.
- Deploy is refused (fail-closed, nothing changes) if one version holds the same key on more than one row, or if submission rows would be left unmapped.
- Besides submission tables, deploy carries forward `AssignmentPageStatus` (page identity inferred from matched sections) and `version.variables[*].source_form_item_id`.
- Fields removed from the new version keep their data on the archived version (`archived=True`); **rolling back** (deploying an archived version) restores those rows.
- Create-draft and deploy lock the `FormTemplate` row so concurrent version changes serialise. Deploy with an unknown/foreign `version_id` is an error — it never falls back to the draft.
- Deleting a version is blocked while any data (including AI validations and page statuses) references it.
- Deploy refuses until the admin sends `acknowledge_orphaned_data=1` when live fields holding data have no match in the target version (the Form Builder dialogs and the field-mapping page send it).
- Data-entry saves post `form_version_id`; `entry_form_is_stale()` takes a share lock on the template row and refuses the save (HTTP 409 for AJAX) when the form belongs to an older published version. Same lock order as deploy: template, then assignment row.
- Field linking: different item kinds / section types are rejected; a differing data type or indicator needs `confirm_type_mismatch`.
- A page with workflow progress cannot be removed from a version (`PageInUseError`); `duplicate_template` remaps `variables[*].source_form_item_id` to the cloned items.
- Operations: `python scripts/ops/audit_template_versions.py` (read-only) and the runbook `Backoffice/docs/runbooks/operations/template-version-integrity.md`, which also holds the plan and checklist for the database constraints (partial unique indexes: one draft per template, unique `stable_key` per version; migration `add_template_version_integrity_constraints`). Tests that need an invalid state use the `without_version_integrity_indexes` fixture. Admin guide: `Backoffice/docs/user-guides/admin/template-versions.md`.

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
| `matrix_cells[]` | Normalized matrix cells; matrix-specific fields grouped under `matrix` (`row`, `column`, `entity`). Includes calculated row/column/grand totals flagged via top-level `is_calculated_total`/`total_kind` (`row`\|`column`\|`grand`) — check before summing `value`, or pass `include_calculated_totals=false` to omit them. Formula columns are recomputed per row and emitted with `is_formula: true`; they are not `is_calculated_total` rows. They stay out of the row total unless that column sets `include_in_row_total`. A calculated column with `calculation_save_value` stores the cell like any other input (a read-only column still snapshots the result on save); that stored number is emitted as a normal cell and wins over a fresh formula. `calculation_readonly` defaults to true. Some matrix items are configured (Form Builder → matrix item → Display → "Include Calculated Totals in API") to never emit `is_calculated_total` rows regardless of this flag — see `include_calculated_totals` below. |
| `assignment_statuses[]` | AssignmentEntityStatus rows for assigned `submission_id`s (workflow status, due date, `last_modified_at`); join when `submission_type` is `assigned` |
| `arrays` | Catalog describing each top-level array (included/excluded, grain, key fields) |

**Legacy:** `GET /api/v1/data/tables` returns HTTP 308 redirect to `/api/v1/data` (same query string).

**Query parameters:** `template_id`, `assignment_id` (single or comma-separated `AssignedForm.id`s), `submission_id` (`AssignmentEntityStatus.id`), `item_id`, `stable_key`, `version_scope`, `country_id`, `country_iso2`, `country_iso3`, `period_name`, `indicator_bank_id`, `indicator_bank_ids`, `date_from`, `date_to`, `sort`, `order`, `related`, `layout` (`flat`|`star`), `include_dynamic`, `include_repeat`, `include_dimensions`, `live`, `include_calculated_totals`, `include_non_reported`, `page`, `per_page`, …

**`assignment_id` vs. `submission_id`:** the two are easy to confuse since both are colloquially "the assignment". `assignment_id` expects an `AssignedForm.id`; `submission_id` expects an `AssignmentEntityStatus.id` — the id used by `assignment_statuses[]`, workflow, and status views. Passing a submission id as `assignment_id` (with no other `assignment_id` in the same call) auto-resolves to the equivalent `submission_id` lookup; the 404 for any id that still fails to resolve names the id and suggests the swap.

**`include_dimensions`** (default `true` for session/API-key auth, `false` for public/unauthenticated): pass `false` on authenticated calls once `countries[]`/`national_societies[]`/`indicator_bank[]` are already cached client-side (e.g. via `/countrymap`, `/nationalsocietymap`, `/indicator-bank`) to shrink the response; pass `true` on public calls to opt into the full dimensions.

**`live`** (default `false`): pass `true` to reload `countries[]`, `national_societies[]`, and `indicator_bank[]` from the database instead of the per-worker cache. Use this after a direct SQL edit to those tables; ORM writes already drop the cache on the worker that handled the write, and the cache otherwise expires after 24 hours. The response is sent with `Cache-Control: no-store`. Fact rows are queried live either way. Public callers still need `include_dimensions=true` to receive the tables.

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

### FDRS publication (`published_value`)

`FormData` carries a **published snapshot** — `published_value` / `published_disagg_data` / `published_numeric_value` / `published_source` / `published_at` / `published_by_user_id` — alongside the existing `prefilled_*`/`imputed_*` columns. It is a curated copy of the live `value`/`disagg_data`, falling back to `imputed_*` when the reported value is missing, decoupling what is currently editable/internal from what a public website actually displays. `published_source` is `reported` or `imputed` (or `NULL` if never published, cleared, or published before that column existed) — stamp it at publish time; do not infer it later from live columns. Nothing writes the snapshot automatically (regular form submission never touches it); it only changes when an admin runs the FDRS "Manage Publication" tool. `AssignmentEntityStatus` mirrors `published_at`/`published_by_user_id` so list views can show "last published" per country without aggregating `form_data` on every page load.

| Piece | Location |
|-------|----------|
| Diff/copy logic | [`Backoffice/plugins/fdrs/services/fdrs_publication_service.py`](../Backoffice/plugins/fdrs/services/fdrs_publication_service.py) — `get_assignment_publication_summary()` (per-country counts + review analysis), `get_country_change_detail()` (item-level diff), `publish_assignment()` (the actual copy) |
| Review analysis | [`Backoffice/plugins/fdrs/services/fdrs_publication_analysis.py`](../Backoffice/plugins/fdrs/services/fdrs_publication_analysis.py) — flags ≥50%/≥100% swings vs last published or the previous period, countries that are ≥10%/≥20% of the assignment-wide total for an indicator (or whose change moves that total by ≥5%/≥10%), Tukey outliers among peer % changes, and values that publishing would clear. Already-published (unchanged) rows are still checked vs the previous period and global share so a fully published assignment can surface values that would be questioned. Flags are **advisory** and appear on the publication review queue, toggleable **By country** or **By issue** (`Needs attention`, `Global impact`, `Large variation`, `Values removed`). |
| Background job | [`Backoffice/plugins/fdrs/services/fdrs_publication_job.py`](../Backoffice/plugins/fdrs/services/fdrs_publication_job.py) — Track A `AIJob` (`fdrs.publication`); POST `/publish` returns **202** + `job_id`, then poll `/publish/<job_id>/status` (cancel via POST `/cancel`). Tests run the worker synchronously. |
| Admin UI | `/admin/fdrs-tools#publication` (legacy `/admin/plugins/fdrs/publication` redirects here) — pick one assignment (reporting period), review one queue by country or by issue (search + focus filters do not change the publish selection), expand a country for indicator evidence, then publish the explicit country selection from the action bar. Progress and cancel stay in the publication panel. |
| Diff classification | `FormData.publication_diff_kind()`: `new` (publishable value — reported, or imputed when reported is missing — never published) / `changed` / `removed` (published before, no reported or imputed value now — publishing would clear the public value) / `source` (values match, but `published_source` is missing or stale — re-publish stamps reported vs imputed without changing the figure) / `unchanged` / `empty` |
| Public endpoint | `GET /api/v1/fdrs/published-data` ([`Backoffice/plugins/fdrs/public_api_routes.py`](../Backoffice/plugins/fdrs/public_api_routes.py)) |

Publication is **scoped to one `AssignedForm` (template + reporting period) at a time**, and within it to whichever `AssignmentEntityStatus` (country) rows are selected — the granularity the tool exposes is per-assignment-per-country, not a single global "publish everything" switch. It only ever touches `FormItem`s marked `privacy='public'` on the FDRS template (`FDRS_TEMPLATE_ID`, currently 21) — the same gate `GET /api/v1/data` uses for unauthenticated readers (`form_item_privacy_is_public_expr()` in `app/services/data_retrieval/shared.py`). `admin.templates.edit` + system-manager access is required to publish; `admin.templates.view` is enough to preview.

`GET /api/v1/fdrs/published-data` accepts a Bearer API key (`Authorization: Bearer ...`) **or** an authenticated Backoffice session (open the URL in the browser while logged in). The FDRS plugin registers the route via `get_api_endpoints()` so it appears on Admin → API Management. The feed only ever reads the `published_*` columns — never the live `value` — so a row with unpublished edits still returns the last-published figure until the next publish. Query params: `period_name`, `assignment_id` (`AssignedForm.id`), `country_id` / `country_iso2` / `country_iso3`, `form_item_id`, `page`, `per_page`. Each row in `data[]` includes `submission_id`, `assignment_id`, `period_name`, `country_id`/`country_name`/`iso2`/`iso3`, `form_item_id`, `stable_key`, `indicator_bank_id`, `item_label`, `value`, `num_value`, `disaggregation_data`, `value_source` (`reported` / `imputed` / `null`), `data_status`, and `published_at`.

## Troubleshooting (Common)

- **iOS `pod` / CocoaPods on Windows**: `pod` is not available on Windows; you cannot refresh `MobileApp/ios/Podfile.lock` locally. Use the **Regenerate iOS Podfile.lock** GitHub Action (see **Mobile App (Flutter)** above).
- **`/api/ai/v2/ws` not working**: ensure `flask-sock` is installed/enabled; HTTP/SSE endpoints can still work without websockets.
- **RAG returns nothing / errors after changing embedding model**: `AI_EMBEDDING_DIMENSIONS` must match the pgvector column; changing it requires a migration and re-embedding.
- **AI falls back / “no provider configured”**: set at least one provider key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure equivalents) and confirm model name via `OPENAI_MODEL`.
- **CSS changes not appearing**: run `npm run watch:css` in `Backoffice/` (and ensure `npm install` was run there).
- **New button class not applying / missing styles**: the `.btn` system lives in `components.css` (static file, always served). Tailwind utility classes go through `output.css` (compiled). If a new Tailwind class on a button is missing, run `npm run build:css`. If a `.btn-*` class is missing, check `components.css` is loaded (via `layout.html`).
- **Button appears rounded when it should be sharp**: do not add `rounded-*` Tailwind classes to buttons. The sharp-corner rule is enforced globally in `theme.css`; only `.rounded-full` is excluded (for FAB/circular buttons).
- **Login works, then the next admin/sidebar click flashes “Access denied. Please log in.” (especially on phones)**: the Flask session is a signed cookie (not Redis). A cookie over ~4KB is dropped by the browser — mobile Safari/Chrome are the least forgiving. Keep JWTs out of `session` (e.g. the B2C `id_token` is stored server-side via `store_oauth_logout_hint`, not in the cookie). See [session management](../Backoffice/docs/runbooks/sessions/session-management.md).