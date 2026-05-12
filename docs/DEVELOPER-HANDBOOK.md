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

### Playwright MCP (browser screenshots)
- **Project config:** `.cursor/mcp.json` passes `--output-dir` `.playwright-mcp/screenshots/` (parent `.playwright-mcp/` is gitignored). Screenshots and related artifacts should land there, not in the repository root.
- **Tool calls:** Use **relative** screenshot filenames only. An absolute path in the filename can bypass `--output-dir` and write under that path instead.
- **Global MCP:** If you also enable Playwright MCP in user-level Cursor config, align `--output-dir` (or env `PLAYWRIGHT_MCP_OUTPUT_DIR`) with the same folder—or disable the duplicate server entry—to avoid conflicting behavior.

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
- LibreTranslate integration for automatic translation
- Supports 7 languages: EN, FR, ES, AR, RU, ZH, HI
- Translation files in `Backoffice/app/translations/`

### AI System Configuration (Backoffice)
- **Chat API**: `/api/ai/v2` (chat, stream, conversations, export/import). WebSocket: `/api/ai/v2/ws`. Health: `GET /api/ai/v2/health` (includes `agent_available`).
- **Auth**: Session (Backoffice) or Bearer token (e.g. mobile). Issue tokens via `GET /api/ai/v2/token` (authenticated).
- **Environment**: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-5-mini`), `GEMINI_API_KEY`, `AZURE_OPENAI_*` for providers. `AI_EMBEDDING_PROVIDER`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIMENSIONS` (must match pgvector column; changing requires migration and possibly re-embedding). `AI_AGENT_ENABLED`, `AI_AGENT_MAX_ITERATIONS`, `AI_AGENT_TIMEOUT_SECONDS`, `AI_AGENT_COST_LIMIT_USD`, `AI_AGENT_MAX_COMPLETION_TOKENS` (default 32768; cap 128000 for large tables; use 4096 for GPT-4o). `AI_TOOL_OBSERVATION_MAX_ROWS_TABLE_RESULT` (default 250; cap 2000; rows sent from indicator/UPR “all countries” tools; increase for full country datasets). `REDIS_URL` optional for cross-worker rate limiting.
- **Supported models**: Depend on OpenAI account. Some models (e.g. GPT-5) reject sampling params; see `app.utils.ai_utils.openai_model_supports_sampling_params`.
- **Shared helpers**: `app.utils.ai_utils` (e.g. `openai_model_supports_sampling_params`, `sanitize_page_context`). RAG: `app.services.ai_vector_store`, `app.services.ai_embedding_service`. Agent: `app.services.ai_agent_executor`, `app.services.ai_tools_registry`. Shared chat request handling: `app.services.ai_chat_request` (parse, resolve conversation, idempotency).
- **Optional dependencies**: `flask-sock` required for WebSocket endpoints (`/api/ai/v2/ws`, document QA WS). Without it, AI HTTP and SSE still work. `redis` (and `REDIS_URL`) optional for cross-worker WebSocket rate limiting; in-memory limiter used otherwise. `pgvector` required for RAG document search; run migrations so `ai_documents`, `ai_embeddings`, `ai_document_chunks` exist. For full chat (non-fallback): at least one of `OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure/Copilot keys. For RAG embeddings: `OPENAI_API_KEY` when `AI_EMBEDDING_PROVIDER=openai`, or local model when `AI_EMBEDDING_PROVIDER=local` (dimensions must match DB).

## Testing and Quality

### Backoffice Testing
```bash
# Run database migration check
python scripts/check_db_migration.py

# Import/export testing
python scripts/import_FDRS_data.py

# AI review queue (terminal triage packets)
python scripts/trigger_automated_trace_review.py --status pending --limit 5 --format text

# Seed deterministic low-quality review item for queue testing
python scripts/seed_low_quality_review.py
python scripts/seed_low_quality_review.py --trace-id 99999999 --create-trace-if-missing
```

### AI review queue scripts (Backoffice)
- `scripts/trigger_automated_trace_review.py` – exports pending/in-review trace packets from `ai_trace_reviews`/`ai_reasoning_traces` for automated terminal processing (`text` or `jsonl`), with paging and optional `--claim-in-review`.
- `scripts/export_trace_reviews.py` – compatibility wrapper (deprecated); forwards to `trigger_automated_trace_review.py`.
- `scripts/seed_low_quality_review.py` – marks a trace as low-quality (`llm_needs_review=True`) and creates/resets a pending review row; use for deterministic end-to-end testing of review queue workflows.

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
- Use `getFetch()` or `getApiFetch()` from `app/static/js/csrf.js` / `app/static/js/lib/api-fetch.js`: `(window.getFetch && window.getFetch()) || fetch` for raw CSRF-aware fetch, or `window.apiFetch` for JSON + optional error display.
- Avoid duplicating the inline pattern; prefer `getFetch()` / `getApiFetch()`.

### Template Safety Checklist (Backoffice Jinja)
- **Client console logging (`CLIENT_CONSOLE_LOGGING`):** `core/layout.html` includes `components/_client_console_guard.html` early in `<head>`, which sets `window.CLIENT_CONSOLE_LOGGING` and no-ops native `console.log` / `debug` / `info` / `warn` / `group*` when the flag is off. For **verbose or trace** output from inline scripts, use **`window.__clientLog`**, **`window.__clientWarn`**, etc. — not raw `console.log` / `console.warn`. **Never call `window.__consoleSaved.*`** (that object holds the *unwrapped* native methods and **bypasses** `CLIENT_CONSOLE_LOGGING`). Use `console.error` only for real failure paths you intend to keep visible. Other full-page templates (e.g. immersive chat, Swagger) include the guard explicitly; standalone HTML that does not extend `layout.html` has no guard unless you `{% include 'components/_client_console_guard.html' %}`. CI guardrail: `python Backoffice/scripts/check_no_console_saved_bypass.py`. Bulk template fixes: `python Backoffice/scripts/gate_template_console_calls.py`.
- **CSP / inline scripts:** Any inline `<script>` must include `nonce="{{ csp_nonce() }}"`. Prefer external JS for larger logic.
- **Server URLs in JS:** Always inject URLs/strings with `|tojson|safe` (avoid raw string interpolation in JS).
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

### Performance
- Database query optimization
- Static file serving
- Translation caching
- Form state management optimization

## Where to Change Things (Index)

- **Admin (Backoffice UI routes)**: `Backoffice/app/routes/admin/` (pick the closest module)
- **Form builder frontend JS**: `Backoffice/app/static/js/form_builder/`
- **Entry form rendering + client behavior**: `Backoffice/app/templates/forms/entry_form/` and `Backoffice/app/static/js/forms/`
- **AI endpoints + request handling**: `Backoffice/app/routes/ai.py`, `Backoffice/app/services/ai_chat_request.py`
- **RAG / embeddings / vector store**: `Backoffice/app/services/ai_embedding_service.py`, `Backoffice/app/services/ai_vector_store.py`
- **Translations / localization**: `Backoffice/app/utils/form_localization.py`, `Backoffice/app/translations/`
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
| `admin_analytics.py` | `GET /admin/analytics/dashboard-stats`, `GET /admin/analytics/dashboard-activity`, `GET /admin/analytics/login-logs`, `GET /admin/analytics/session-logs`, `POST /admin/analytics/sessions/<id>/end`, `GET /admin/analytics/audit-trail`, `POST /admin/notifications/send` | `admin.analytics.view`, `admin.audit.view`, `admin.notifications.manage` | `admin_dashboard_provider.dart`, `user_analytics_provider.dart`, `login_logs_provider.dart`, `session_logs_provider.dart`, `audit_trail_provider.dart` |
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

## Troubleshooting (Common)

- **iOS `pod` / CocoaPods on Windows**: `pod` is not available on Windows; you cannot refresh `MobileApp/ios/Podfile.lock` locally. Use the **Regenerate iOS Podfile.lock** GitHub Action (see **Mobile App (Flutter)** above).
- **`/api/ai/v2/ws` not working**: ensure `flask-sock` is installed/enabled; HTTP/SSE endpoints can still work without websockets.
- **RAG returns nothing / errors after changing embedding model**: `AI_EMBEDDING_DIMENSIONS` must match the pgvector column; changing it requires a migration and re-embedding.
- **AI falls back / “no provider configured”**: set at least one provider key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, or Azure equivalents) and confirm model name via `OPENAI_MODEL`.
- **CSS changes not appearing**: run `npm run watch:css` in `Backoffice/` (and ensure `npm install` was run there).
- **New button class not applying / missing styles**: the `.btn` system lives in `components.css` (static file, always served). Tailwind utility classes go through `output.css` (compiled). If a new Tailwind class on a button is missing, run `npm run build:css`. If a `.btn-*` class is missing, check `components.css` is loaded (via `layout.html`).
- **Button appears rounded when it should be sharp**: do not add `rounded-*` Tailwind classes to buttons. The sharp-corner rule is enforced globally in `theme.css`; only `.rounded-full` is excluded (for FAB/circular buttons).