# Backoffice Test Report

**Generated:** 2026-06-08 · **Last updated:** 2026-06-08 (new tests + fixes)  
**Baseline run:** 2026-06-08 18:56:47 UTC+2 · **New tests verified:** 2026-06-08 (192 unit tests passed)  
**Environment:** win32 · Python 3.13.3 · pytest 9.0.3  
**Status:** PASS — baseline suite exit code 0; new unit tests verified green

---

## Executive Summary

| Metric | Baseline (2026-06-08) | After new tests |
|--------|----------------------:|----------------:|
| Total tests | **1,028** | **1,262** (+234) |
| Passed | **1,028** (100%) | baseline unchanged; **192 new unit tests verified** |
| Failed | 0 | 0 (verified subset) |
| Errors | 0 | 0 |
| Skipped | 0 | 0 |
| Warnings | 831 | reduced — see [Fixes Applied](#fixes-applied) |
| Run duration | **44m 46s** (2,626 s) | — |
| Line coverage | **29.47%** (27,763 / 94,219 lines) | re-run full suite to refresh |
| Test modules | 68 | **76** (+8) |

The baseline run had all 1,028 tests passing. Since then, **234 tests** were added across **8 new modules**, and two warning sources were fixed in production/test code. The new unit tests (192) were verified in a focused run (~47 s); integration tests for user management and system admin (42 tests) should be confirmed with a full suite re-run.

---

## Fixes Applied

The following items from the original [Warnings](#warnings) / recommended-fixes list were implemented:

| Fix | File(s) | Change |
|-----|---------|--------|
| `InsecureKeyLengthWarning` | `tests/conftest.py` | `SECRET_KEY` and `MOBILE_JWT_SECRET` extended to ≥32 bytes |
| `LegacyAPIWarning` | `app/routes/api/mobile/admin_content.py` | All 14 `Model.query.get(id)` calls migrated to `db.session.get(Model, id)` |

Re-run the full suite and regenerate `test_results.xml` / `coverage.xml` to confirm warning count drop and updated coverage figures.

---

## New Tests Added (2026-06-08)

**234 tests** across **8 modules** — addressing all P0–P2 items from the original coverage-improvement plan.

| Module | Tests | Type | Priority | Covers |
|--------|------:|------|:--------:|--------|
| `tests/unit/test_ai_fastpaths.py` | 7 | Unit | P0 | Package re-export integrity; `run_unified_plans_focus_fastpath` query gating, tool availability, mocked success path |
| `tests/unit/test_upr.py` | 60 | Unit | P0 | `query_prefers_upr_documents`, `upr_kpi_applicable`, `upr_document_label`, `upr_suggestion_reason`, `format_ifrc_upr_extraction`, `_parse_int_number` |
| `tests/unit/test_services/test_ai_tools_utils.py` | 44 | Unit | P1 | `ToolExecutionError`, `json_sanitize`, `truncate_json_value`, `tool_wrapper`, `apply_document_source_filters`, `rewrite_document_search_query`, country inference |
| `tests/unit/test_services/test_fdrs_matrix.py` | 34 | Unit | P1 | `baseline_value`, `ytd_pct`, `threshold_exceeded`; `run_fdrs_matrix_rules` (death KPIs, non-zero, branches>units, fiscal year) |
| `tests/unit/test_services/test_ai_agent_circuit_breaker.py` | 20 | Unit | P1 | `CircuitBreaker` state machine — closed→open→half-open→closed, isolation, custom thresholds |
| `tests/integration/test_admin_user_management_routes.py` | 23 | Integration | P1 | User list/create/edit/archive/delete, access requests, B2C guard, self-delete guard |
| `tests/integration/test_admin_system_admin_routes.py` | 19 | Integration | P2 | Countries CRUD/JSON, sectors page, auth and 404 smoke tests |
| `tests/unit/test_services/test_notification_service.py` | 27 | Unit | P2 | `validate_notification_url` (15 URL-safety cases), audience helper edge cases |

---

## Test Breakdown by Category

| Category | Baseline | Added | Total | Modules |
|----------|--------:|------:|------:|--------:|
| Unit | 409 | +192 | **601** | 28 |
| Integration | 381 | +42 | **423** | 24 |
| API — Backoffice | 103 | — | **103** | 11 |
| API — Mobile | 135 | — | **135** | 13 |
| **Total** | **1,028** | **+234** | **1,262** | **76** |

---

## API Tests — Mobile (`tests/api/mobile/`)

These tests exercise the `GET /api/mobile/v1/*` surface consumed by the mobile app. Every module verifies both the authentication/authorisation contract (JWT Bearer, permission checks) and the response shape.

---

### `test_admin_analytics_routes` · 13 tests

**Critical functions:** dashboard stats, audit trail pagination, admin-only notification send  
**Covers:** `/api/mobile/v1/admin/analytics/*` — dashboard stats and activity, paginated login/session logs, audit trail, and an admin send-notification endpoint.  
Verifies RBAC (403 for non-admins on every endpoint), correct paginated shapes, 404 on missing sessions, and required-field validation on the notification payload.

---

### `test_admin_content_routes` · 22 tests

**Critical functions:** template/assignment/document CRUD guards, file access authentication  
**Covers:** `/api/mobile/v1/admin/content/*` — templates, assignments, documents, resources, indicator bank, and translations.  
Checks permission gating on list endpoints, list/pagination response contracts, 404 and 401 behaviour on CRUD and file-download operations, and archive actions on indicators.

---

### `test_admin_org_routes` · 5 tests

**Critical functions:** org hierarchy tree, admin-only access enforcement  
**Covers:** `/api/mobile/v1/admin/org/*` — branches list, subbranches, and full org-structure tree.  
Verifies JWT auth is required, list and tree response shapes are correct, and org-structure access is restricted to admin users.

---

### `test_admin_requests_routes` · 5 tests

**Critical functions:** access-request approval/rejection, bulk-approve on empty queue  
**Covers:** `/api/mobile/v1/admin/access-requests/*` — listing, approving, and rejecting access requests.  
Verifies admin-only permission gate, 404 handling on approve/reject for missing requests, and bulk-approve against an empty queue.

---

### `test_admin_users_routes` · 9 tests

**Critical functions:** user list/search/detail, activate/deactivate guards, RBAC role listing  
**Covers:** `/api/mobile/v1/admin/users/*` — user list with search, detail, update, activate, deactivate, and RBAC role listing.  
Verifies RBAC on every action, search filtering, 404 for missing users, and the critical self-deactivation guard (admin cannot deactivate their own account).

---

### `test_auth_routes` · 15 tests

**Critical functions:** login credential validation, inactive-user rejection, token refresh, password change, profile update  
**Covers:** `/api/mobile/v1/auth/*` — login, token refresh, session check, logout, password change, and profile read/update.  
Exercises credential validation, inactive-user rejection, token refresh error paths, and authenticated profile mutations.

---

### `test_device_routes` · 7 tests

**Critical functions:** push-device registration/unregistration, heartbeat  
**Covers:** `/api/mobile/v1/devices/*` — register, unregister, and heartbeat endpoints.  
Verifies auth requirements, mocked service calls for push registration/unregistration, platform validation, and heartbeat updates.

---

### `test_mobile_auth` · 7 tests

**Critical functions:** `mobile_auth_required` decorator — valid/expired/invalid JWT, permission checks, session-cookie fallback  
**Covers:** The `mobile_auth_required` decorator applied to a protected test endpoint.  
Tests JWT acceptance and rejection (expired, invalid Bearer), 403 on missing permissions, and fallback to session cookie when no Authorization header is present. This is the critical auth layer protecting all mobile admin routes.

---

### `test_mobile_jwt` · 12 tests (unit — no database)

**Critical functions:** token-pair issuance, encode/decode roundtrips, expiry/type/audience validation, secret-key precedence  
**Covers:** `app.utils.mobile_jwt` in isolation.  
Verifies tokens are distinct, all roundtrip variants work, and expected errors are raised for expired/wrong-type/wrong-audience tokens. Also confirms `MOBILE_JWT_SECRET` is preferred over the generic `SECRET_KEY`.

---

### `test_mobile_responses` · 20 tests (unit — no database)

**Critical functions:** JSON envelope consistency, HTTP status codes, pagination metadata, error wrappers  
**Covers:** `app.utils.mobile_responses` helper functions.  
Asserts all response helpers (`mobile_ok`, `mobile_created`, `mobile_paginated`, `mobile_error`, `bad_request`, `auth_error`, `forbidden`, `not_found`, `server_error`) produce correct envelopes and status codes.

---

### `test_notification_routes` · 9 tests

**Critical functions:** notification list/count, mark read/unread, preference management  
**Covers:** `/api/mobile/v1/notifications/*` — listing, counting, mark-read, mark-unread, and preference get/update.  
Verifies auth, mocked service responses, 400 validation on missing IDs, and the full preference update cycle.

---

### `test_public_data_routes` · 11 tests

**Critical functions:** unauthenticated public endpoints, indicator suggestion submission, quiz score submission  
**Covers:** `/api/mobile/v1/data/*` — country map, sectors/subsectors, indicator bank, suggestions, quiz leaderboard, and quiz score submission.  
Verifies public endpoints are accessible without authentication, response contracts for reference data, and input validation on suggestion and quiz score forms.

---

### `test_version_middleware` · 4 tests (unit — no database)

**Critical functions:** HTTP 426 enforcement for outdated mobile app versions  
**Covers:** `X-App-Version` enforcement middleware.  
Confirms requests pass when no minimum version is configured, that missing the header is allowed, and that outdated app versions receive **HTTP 426 Upgrade Required** while current versions succeed.

---

## API Tests — Backoffice (`tests/api/`)

These tests exercise the `/api/v1/*` and `/api/ai/v2/*` endpoints consumed by external API clients and internal services.

---

### `test_api_assignments` · 2 tests

**Critical functions:** API key auth, assigned-forms contract  
**Covers:** `GET /api/v1/assigned-forms`.  
Verifies API-key authentication is required and that an authenticated response matches the expected JSON contract.

---

### `test_api_countries` · 4 tests

**Critical functions:** dual auth (API key and session), periods listing  
**Covers:** `GET /api/v1/countrymap` and `GET /api/v1/periods`.  
Verifies the countrymap supports both API key and session auth, while periods is API-key-only.

---

### `test_api_data` · 9 tests

**Critical functions:** data export auth, star-layout tables, permission-based 403, template/country scoped data  
**Covers:** `GET /api/v1/data`, `GET /api/v1/data-tables`, and scoped template/country data endpoints.  
Tests auth via header and query param, response contracts including star-layout tables, 403 for API keys without data permission, and 404/happy-path for template and country scoped queries.

---

### `test_api_documents` · 2 tests

**Critical functions:** API key auth, submitted-documents paginated contract  
**Covers:** `GET /api/v1/submitted-documents`.  
Verifies API-key requirement and paginated JSON contract for document listings.

---

### `test_api_endpoints` · 24 tests

**Critical functions:** broad smoke coverage of every read endpoint under `/api/v1/*`  
**Covers:** A seeded-database fixture used to exercise all public API read paths: submissions, data, templates, countries, periods, resources, indicator bank, sectors, users, assigned forms, documents, quiz leaderboard, and common words.  
Each test confirms HTTP 200 and a structurally valid JSON payload. This is the key regression guard against API regressions across the entire v1 surface.

---

### `test_api_indicators` · 3 tests

**Critical functions:** public indicator bank (no auth), sectors/subsectors  
**Covers:** `GET /api/v1/indicator-bank` and `GET /api/v1/sectors`.  
Verifies the indicator bank is publicly readable without an API key, while authenticated responses match expected contracts.

---

### `test_api_submissions` · 3 tests

**Critical functions:** submissions auth, list contract, 404 on missing submission  
**Covers:** `GET /api/v1/submissions` and submission detail.  
Covers auth requirement, paginated list contract, and 404 for a non-existent submission ID.

---

### `test_api_templates` · 3 tests

**Critical functions:** templates auth, pagination, per-page clamping  
**Covers:** `GET /api/v1/templates`.  
Verifies auth, paginated list with seeded data, and that the `per_page` parameter is clamped to allowed bounds.

---

### `test_api_users` · 32 tests

**Critical functions:** user list/detail (pagination, search, RBAC fields, country fields), profile GET/PUT/PATCH, dashboard entity/assignment structure  
**Covers:** All five endpoints in `app/routes/api/users.py`: API-key user list, user detail, current-user profile GET, current-user profile update, and dashboard.  
This is the most comprehensive API test module. Key critical behaviours: RBAC role inclusion in list/detail, country extended fields, field-level profile updates (name, title, chatbot, color), PUT/PATCH idempotency, 400 on invalid fields, CSRF content-type enforcement, dashboard entity selection by user role (admin vs focal point), and assignment data shape.

---

### `test_api_v1_csrf` · 2 tests

**Critical functions:** CSRF enforcement on session-authenticated mutating endpoints  
**Covers:** Profile update and quiz score submission via session auth.  
Confirms that requests without a valid CSRF token are rejected — critical for session-based XSS protection.

---

### `test_ai_chat_endpoints` · 15 tests

**Critical functions:** AI chat auth, SSE streaming contract, conversation lifecycle, AI JWT issuance, Excel table export  
**Covers:** `/api/ai/v2/*` — health checks, conversations, chat, streaming chat, token issuance, and table export.  
Verifies auth for both session and Bearer tokens, input validation (message required, too long), SSE stream format, conversation list/export/delete/archive flows, AI JWT issuance for logged-in users, and Excel table export headers.

---

## Integration Tests (`tests/integration/`)

Integration tests boot the full Flask application with a test database and exercise complete HTTP request/response cycles.

---

### `test_admin_assignments` · 14 tests

**Critical functions:** assignment list RBAC, activate/deactivate toggle, delete, public URL generation, public-access toggle  
Verifies auth and permission gates on every admin assignment management action, and checks that toggle/delete/public-URL operations produce the expected HTTP outcomes.

---

### `test_admin_form_builder` · 20 tests

**Critical functions:** form builder edit page (ownership, 404), section/item CRUD, versioning (draft/deploy/discard), Excel export  
End-to-end tests covering the entire form-builder lifecycle. Verifies ownership redirects (non-owners cannot edit), permission enforcement on deploy/publish actions, and each CRUD operation on sections, items, and template variables.

---

### `test_admin_smoke` · 2 tests

**Critical functions:** admin route blanket deny for regular users, key admin JSON endpoints for admins  
Quick smoke checks that regular users are blocked from admin API routes while admins can reach health, users, and plugin endpoints.

---

### `test_admin_templates_list` · 8 tests

**Critical functions:** template list rendering, delete (with permission check), duplicate, create  
Tests the admin templates list page and the full template lifecycle: empty-state rendering, JSON delete-info API, permission-gated delete, duplicate, and create POST.

---

### `test_admin_user_edit_email_b2c` · 2 tests

**Critical functions:** email-edit guard when Azure B2C is active  
Verifies that editing a user's email in admin is blocked when Azure B2C is configured and allowed under local-only auth — prevents identity-provider conflict.

---

### `test_authentication` · 14 tests

**Critical functions:** session login/logout, API key lifecycle (valid, missing, revoked, expired), RBAC route guards, full password-reset flow  
Covers all authentication pathways. The password-reset tests cover the full token lifecycle: creation, invalid/expired token rejection, and successful password update with token invalidation.

---

### `test_b2c_identity_guards` · 4 tests

**Critical functions:** registration/new-user/email-check/password-reset blocked under Azure B2C  
When Azure B2C is the identity provider, local identity paths (registration, new-user creation, email checks, and password reset for Azure-only users) must all be blocked.

---

### `test_coming_soon_lock` · 7 tests

**Critical functions:** coming-soon and maintenance site-lock middleware, health endpoint exemption, bypass secret  
Tests the site-lock middleware in both coming-soon and maintenance modes. Verifies defaults, route blocking, health endpoint exemption, bypass secret access, and maintenance overriding coming-soon.

---

### `test_critical_routes_admin` · 12 tests (parametrized)

**Critical functions:** admin dashboard, all critical admin HTML pages — auth required, system-manager access, regular-user denied  
Smoke tests for all critical admin production routes. These serve as a fast regression check on the most important admin pages (assignments, templates, users, etc.) confirming auth requirement and role-based access.

---

### `test_critical_routes_focal` · 16 tests

**Critical functions:** focal-point dashboard, assignment form save/submit, approval workflow, public forms, country-access requests, profile summary  
Critical-route smoke tests from the focal-point user perspective. Covers the complete assignment lifecycle (save → submit → approve → return → reopen) and confirms public form rendering and profile summary access.

---

### `test_email` · 3 tests

**Critical functions:** email configuration validation, mocked send, configuration presence  
Validates email configuration correctness and that the Flask app context can execute a mocked send without errors.

---

### `test_entry_form` · 60+ tests

**Critical functions:** numeric value parsing, disaggregation data processing, form authorization, document save/delete, variable resolution, public submissions, repeat sections, dynamic indicators  
The largest integration suite. Covers helper functions (numeric parsing edge cases, slugify, section completion), services (form-data save/submit, template rendering, variables, documents), form authorization (admin vs focal-point vs denied), localization, plugin data processing, public form submission, preview mode, Excel import/export, PDF export, matrix row search, and dynamic indicator creation with disaggregation.

---

### `test_entry_form_apis` · 11 tests

**Critical functions:** lookup-list AJAX, repeat-instance toggle, dynamic indicator add/update/remove/render, collaborative presence heartbeat  
HTTP API tests for the entry-form AJAX endpoints called by the form JS. Tests the complete dynamic indicator lifecycle and the collaborative presence system (heartbeat and active users list).

---

### `test_entry_form_routes` · 18 tests

**Critical functions:** legacy redirect, form-type routing, document download/delete, PDF/matrix export, public submission edit, validation summary, send-for-review  
Route-level tests for the entry-form page hierarchy. Covers critical workflow actions: send-for-review status transition, validation summary access control, public-form POST saves data, and admin-only public submission view.

---

### `test_entry_form_v1_apis` · 18 tests

**Critical functions:** variable resolution (single and batch), matrix auto-load entities with tick filtering  
REST API contract tests for two advanced entry-form v1 APIs. Covers complete validation error coverage (missing body, missing fields, not-found, access denied, no published version) and all tick-filtering scenarios for auto-load entities.

---

### `test_excel_routes` · 9 tests

**Critical functions:** assignment Excel export (headers, real assignment), import validation (extension, size, permissions), import JSON contracts  
Assignment Excel import/export route tests. Verifies correct Content-Type/headers on export, import file validation (extension, file size), edit permission enforcement, and both success and failure JSON contracts on import.

---

### `test_malicious_file_uploads` · 18 tests

**Critical functions:** file upload security — script/executable/MIME-spoof/path-traversal/null-byte/oversize rejection  
Security tests for document upload on entry forms. Rejects: shell scripts, batch/PowerShell/Python/PHP/JavaScript/Ruby scripts, executables, DLLs, JARs, COM files, path traversal (Unix and Windows style), MIME-type spoofing (exe-as-PDF, sh-as-txt), null bytes in filenames, and oversized files. Accepts valid PDFs. This is a critical security gate.

---

### `test_notifications_routes` · 7 tests

**Critical functions:** notification center auth, list/count contracts, mark-read validation, archive/delete, preferences  
Covers the notifications center HTML page and all notification API routes: auth, JSON contracts for list and count, 400 validation on mark-read, archive/delete operations, and preference get/update.

---

### `test_profile_summary_authorization` · 2 tests

**Critical functions:** focal-point scope overlap determines profile visibility  
Verifies the profile-summary authorization logic: focal points get the full profile only when their scope overlaps with the request, and get an empty payload when no overlap exists.

---

### `test_public_routes` · 12 tests

**Critical functions:** resource download path traversal guard, PDF headers, legacy redirects, public document thumbnails, health endpoint with DB degradation  
Covers public/unauthenticated routes including a critical security test — path-traversal attempts on resource downloads must be rejected with 403. Also tests health endpoint degradation when the database is unavailable.

---

### `test_rbac_management_routes` · 40+ tests

**Critical functions:** roles CRUD, permissions listing, grants (user, role, deny), JSON API contracts  
The most comprehensive RBAC test module. Tests the full role lifecycle (create with duplicate-code blocking, edit, delete with user-assignment guard), grant management (global user, role, deny grants with invalid-input guards), and JSON APIs for listing roles/permissions and querying a user's roles.

---

### `test_static_cache` · 3 tests

**Critical functions:** long-cache headers for versioned assets, ETag headers  
Verifies that versioned static files receive long-lived cache headers and that ETags are present on all static assets.

---

### `test_transaction_middleware` · 8 tests

**Critical functions:** commit on 2xx, rollback on 4xx/exceptions, opt-out, streaming deferral, real DB rollback  
Tests the per-request SQLAlchemy transaction middleware — a critical data-integrity layer. Verifies commit on success, rollback on 4xx and unhandled exceptions, opt-out flag, and that streaming responses defer session removal.

---

### `test_websocket_routes_smoke` · 3 tests

**Critical functions:** WebSocket route registration for AI and notifications  
Smoke tests confirming AI and notification WebSocket routes are registered when Flask-Sock is available and that notification WebSockets are not registered when explicitly disabled.

---

### `test_admin_user_management_routes` · 23 tests *(new)*

**Critical functions:** user list/create/edit/archive/delete, access-request list, B2C create guard, self-deactivation/self-delete guards  
Integration tests for `routes/admin/user_management/crud.py`. Verifies auth on every route, admin access to user list and forms, duplicate-email rejection, Azure B2C blocking manual user creation, deactivate/archive toggling, system-manager-only delete, and access-request listing.

---

### `test_admin_system_admin_routes` · 19 tests *(new)*

**Critical functions:** countries create/edit/JSON endpoints, sectors page, auth and 404 smoke tests  
Integration smoke tests for `routes/admin/system_admin/*`. Covers country list redirect, create/edit forms, JSON data endpoints, 404 on missing countries, and sectors/subsectors management page access control.

---

## Unit Tests (`tests/unit/`)

Unit tests are isolated (no HTTP server, database access only where required by fixtures).

---

### `test_ai_fastpaths` · 7 tests *(new)*

**Critical functions:** package re-export, `run_unified_plans_focus_fastpath` query gating and tool execution  
Verifies `services.ai_fastpaths` re-exports the UPR focus-area fastpath entry point. Tests that non-matching queries return `None`, missing tools skip execution, and a matching unified-plan query with mocked registry executes `analyze_unified_plans_focus_areas`.

---

### `test_upr` · 60 tests *(new)*

**Critical functions:** UPR query detection, KPI applicability guardrails, document labels, suggestion reasons, extraction formatting, numeric parsing  
Pure unit coverage of `services.upr.query_detection` and `services.upr.validation`. Includes negative-flag cases (annual report / MYR), subset-indicator rejection (e.g. insured volunteers), year extraction from filenames, and lenient integer parsing with thousand separators.

---

### `test_assignment_lifecycle` · 8 tests

**Critical functions:** entry-allowed rules by status, closed-round edit permissions, self-deactivation safety  
Assignment lifecycle rules: active open assignments allow entry, inactive ones block it, and expired assignments allow entry but not public submission. Closed-round permissions ensure only assignment admins can edit while the round is closed, while entity-reopen allows focal-point editing within a still-closed round.

---

### `test_azure_b2c_config` · 2 tests

**Critical functions:** B2C configured/not-configured detection  
Verifies the `is_azure_b2c_configured()` helper returns the correct boolean based on presence of required config keys.

---

### `test_data_quality_fdrs_v1` · 10 tests

**Critical functions:** FDRS v1 weighted formula, reporting score, timeliness score, disability components  
FDRS v1 data-quality scoring logic: weighted formula for a Testland 2024 scenario, income-sources matrix coverage, governance and people-reached reporting scores, timeliness score (zero when submitted after cutoff), disability disaggregation components, and dashboard feature flag.

---

### `test_disability_questions_processing` · 3 tests

**Critical functions:** Washington Group merge, disagg-data storage, flag-gated ignoring  
Verifies disability question processing: yes/no stored in disagg data without overwriting the main value, Washington Group responses merged with numeric totals, and processing skipped entirely when the disability flag is disabled.

---

### `test_fdrs_compliance_doc_matching` · 4 tests

**Critical functions:** document label matching, pending-status tracking, active-country filtering  
FDRS compliance document matching: label lookup, tracking documents in pending status, pending counting toward requirements, and active-country map filtering out inactive countries.

---

### `test_fdrs_sync_helpers` · 18 tests

**Critical functions:** income-sources matrix, document import plan, DON parsing, assignment status derivation, disability KPI merge  
Comprehensive unit coverage of FDRS sync helper functions. Critical tests include assignment-status derivation from workflow KPIs and the disability-disaggregation merge that combines DDD and Washington Group Question data into the standard disagg structure.

---

### `test_middleware` (suite in `test_middleware/`)

**Critical functions:** session page-view counting — Sec-Fetch navigation vs API/fetch noise  
Session page-view counting middleware: uses `Sec-Fetch-Mode` headers to distinguish real page navigations from AJAX/CORS fetches. Verifies skipped endpoints, legacy UA fallback counting, and that API-prefix routes are excluded.

---

### `test_models` (suite in `test_models/`)

**Critical functions:** User model — password hashing, active default, RBAC role default, authentication interface  
User model fundamentals: creation, bcrypt password hashing and verification, active/RBAC defaults, Flask-Login `is_authenticated`, and string representation. Also tests user-agent browser display parsing for login logs (multi-word app names, Mobile Safari versioning, single-word browsers).

---

### `test_notification_audience_rules` · 4 tests

**Critical functions:** default audience merge, bucket defaults, override behavior, unknown-bucket handling  
Notification audience rules: default merge contains all notification types, assignment-submitted defaults all buckets to true, audience override can disable specific buckets, and unknown buckets return false.

---

### `test_plugins_smoke` · 1 test

**Critical functions:** plugin entry template rendering  
Smoke test confirming plugin entry templates render without error inside the app context.

---

### `test_power_query_workbook` · 2 tests

**Critical functions:** Power Query name sanitization, DataMashup embedding  
Verifies query name sanitization (invalid chars stripped) and that the workbook builder embeds a DataMashup blob correctly.

---

### `test_profile_summary_payload` · 12 tests

**Critical functions:** role badge generation, focal scope display rules, admin vs focal scope field inclusion  
Profile-summary payload construction: role badges from RBAC codes, focal scope display (full region, ≤5 country names, summarized count, global when all countries), and admin vs focal-point field inclusion.

---

### `test_services` (suite in `test_services/`)

254 tests covering services *(+125 since baseline)*:

| Sub-module | Critical functions |
|---|---|
| `test_ai_services` (70 tests) | Chunking, embeddings, tools registry, agent executor, routing policy, payload inference, charts, vector store, document processing, reasoning traces |
| `test_authorization_service` (15 tests) | Admin/system-manager detection, RBAC permission checks, focal-point restrictions, country-scoped access |
| `test_ai_tools_utils` (44 tests) *(new)* | `ToolExecutionError`, JSON sanitization, truncation, `tool_wrapper`, document source filters, query rewriting, country inference |
| `test_fdrs_matrix` (34 tests) *(new)* | Historical baseline/YTD/threshold helpers; FDRS matrix rules (deaths, non-zero KPIs, branches>units, fiscal year) |
| `test_notification_service` (27 tests) *(new)* | `validate_notification_url` URL safety; audience helper edge cases |
| `test_ai_agent_circuit_breaker` (20 tests) *(new)* | Per-tool circuit breaker — open/half-open/closed transitions, cooldown, isolation |
| `test_assignment_workflow_service` (8 tests) | Review feature flag, NS vs org submit transitions, delegation review source statuses |
| `test_assignment_ns_review_auth` (11 tests) | Who can edit/submit/send-for-review/return-for-revision in the NS review workflow |
| `test_ai_providers` (6 tests) | Embedding provider abstraction, local vs OpenAI factory selection |
| `test_indicator_bank_service` (7 tests) | API key permission scoping, star-schema serialization |
| `test_country_service` (8 tests) | ID/ISO2/ISO3 lookups with case insensitivity |
| `test_template_duplication_services` (4 tests) | Section and item duplication with child copying |
| `test_variable_resolution_service` (3 tests) | Safe formula evaluation, malicious-input rejection |
| Various analytics | API usage stats, page-path histogram, session touch, email delivery security, bot detection |

---

### `test_utils` (suite in `test_utils/`)

78 tests covering utility modules:

| Sub-module | Critical functions |
|---|---|
| `test_api_responses` (27 tests) | JSON error/ok/status helpers, body/content-type validation |
| `test_password_validator` (17 tests) | Complexity, common-password block, personal-info rejection, strength scoring |
| `test_api_helpers` (7 tests) | Safe JSON parsing with custom defaults |
| `test_country_utils` (10 tests) | ISO2/ISO3 resolution, region grouping |
| `test_request_utils` (9 tests) | JSON/AJAX/API request detection from headers and paths |
| `test_ai_pricing` (6 tests) | Model pricing lookup, cost estimation, config override |
| `test_activity_endpoint_catalog` (8 tests) | Key uniqueness, manual overrides, description generation, merge semantics |
| `test_audit_trail_display` (7 tests) | Activity type consolidation, AES extraction, consistent descriptions |
| `test_malicious_file_uploads` related | File scanning fail-closed vs fail-open policy |
| Various | JSONB text extraction, chatbot language normalization, notification email utilities, page-view path keys |

---

### `test_validation_*` (5 modules, 26 tests)

| Module | Tests | Critical functions |
|---|---|---|
| `test_validation_check_service` | 3 | AES resolution by year, rule-pack and assignment prerequisites |
| `test_validation_dashboard_service` | 5 | Indicator preview with historical values, flagged-first sorting, thousands formatting |
| `test_validation_question_assembler` | 2 | Template text fallback, highest-severity selection |
| `test_validation_question_follow_up` | 5 | Eligibility (answered status, open-child block), parent linking, round increment |
| `test_validation_questions_excel` | 12 | Serialization fields, lifecycle timestamps, import answer/status rules |
| `test_validation_tracker_service` | 6 | Section fill thresholds, reporting ratios, overall completion, tracker data shape |

---

## Performance

Total duration: **44m 46s** for 1,028 tests (baseline). With **1,262 tests**, expect ~52–55 minutes until fixture optimisations land. Average: ~2.55 s/test (expected — tests use a real database and full HTTP stack).

### Slowest Tests

| Rank | Test | Duration |
|------|------|:--------:|
| 1 | `test_ai_chat_endpoints::test_ai_chat_returns_success_with_fallback` | 24.24 s |
| 2 | `test_admin_content_routes::TestAssignmentRoutes::test_delete_not_found` | 11.80 s |
| 3 | `test_admin_analytics_routes::TestDashboardStats::test_requires_permission` | 10.35 s |
| 4 | `test_auth_routes::TestRefreshToken::test_missing_refresh_token` | 9.48 s |
| 5 | `test_admin_org_routes::TestOrgRoutes::test_structure_returns_tree` | 9.45 s |
| 6 | `test_admin_content_routes::TestDocumentRoutes::test_get_file_not_found` | 8.51 s |
| 7 | `test_admin_org_routes::TestOrgRoutes::test_structure_requires_permission` | 8.12 s |
| 8 | `test_admin_content_routes::TestDocumentRoutes::test_delete_not_found` | 8.09 s |
| 9 | `test_admin_content_routes::TestDocumentRoutes::test_list_requires_permission` | 7.99 s |
| 10 | `test_auth_routes::TestRefreshToken::test_valid_refresh` | 7.69 s |

The AI chat test (24 s) is expected for LLM integration. Mobile admin tests are consistently slow due to per-test JWT + database setup; investigate broader fixture scoping as an optimization.

---

## Warnings

**Baseline: 831** — all non-blocking (exit code 0). Two root causes were **fixed**; re-run the full suite to confirm the reduced count.

| Warning | Source | Status |
|---------|--------|--------|
| `InsecureKeyLengthWarning` | `PyJWT` | **Fixed** — test secrets in `tests/conftest.py` extended to ≥32 bytes |
| `LegacyAPIWarning` | `SQLAlchemy` | **Fixed** — all 14 `Query.get()` calls in `admin_content.py` migrated to `db.session.get()` |

Remaining warnings (if any after re-run) are likely from third-party libraries or other modules not yet migrated.

---

## Coverage Analysis

**Overall:** 29.47% line coverage (27,763 / 94,219 lines) — *baseline; re-run full suite to include new tests*  
**Branch coverage:** not measured (disabled in configuration)

The overall figure is below a typical 60–80% production target. Large portions of the codebase — admin UI routes, CLI commands, AI agent orchestration — are not yet exercised by automated tests.

### Coverage by Package

#### Full Coverage (100%)

| Package | Rate |
|---------|:----:|
| `forms.shared` | 100% |
| `forms.assignments` | 100% |
| `services.data_quality.catalogs` | 100% |
| `utils.activity_endpoint_catalog.generated` | 100% |
| `utils.activity_endpoint_catalog.generated.partials` | 100% |

#### High (60–99%)

| Package | Rate |
|---------|:----:|
| `services.validation` | 75.0% |
| `middleware` | 73.7% |
| `forms.form_builder` | 66.4% |
| `services.data_quality.methodologies` | 64.5% |
| `models` | 63.2% |
| `services.ai_providers` | 61.1% |

#### Medium (30–59%)

| Package | Rate |
|---------|:----:|
| `utils.activity_endpoint_catalog` | 58.2% |
| `forms` | 56.8% |
| `services.monitoring` | 56.5% |
| `services.data_quality` | 56.3% |
| `routes.api.mobile` | 51.5% |
| `utils` | 49.4% |
| `. (app root)` | 46.6% |
| `routes.api` | 44.5% |
| `routes.admin.form_builder` | 44.5% |
| `forms.system` | 42.0% |
| `plugins` | 41.5% |
| `services.security` | 39.0% |
| `services.email` | 38.3% |
| `forms.content` | 38.1% |
| `routes.forms` | 30.5% |

#### Low (<30%) — improvement priorities

| Package | Baseline rate | Priority | Tests added |
|---------|:------------:|----------|-------------|
| `services.ai_fastpaths` | 0.0% | **High** | ✅ 7 unit tests |
| `services.upr` | 3.2% | **High** | ✅ 60 unit tests |
| `services.ai_tools` | 13.2% | **High** | ✅ 44 unit tests |
| `services.validation.fdrs_matrix` | 11.5% | **High** | ✅ 34 unit tests |
| `services.ai_agent` | 25.9% | **High** | ✅ 20 unit tests (circuit breaker) |
| `routes.admin.user_management` | 25.8% | **High** | ✅ 23 integration tests |
| `services.notification` | 26.0% | Medium | ✅ 27 unit tests (URL validation + audience) |
| `routes.admin.system_admin` | 15.5% | Medium | ✅ 19 integration smoke tests |
| `routes` | 28.7% | Medium | — |
| `routes.main` | 28.4% | Medium | — |
| `swagger` | 26.3% | Low | — |
| `services` | 24.4% | **High** | partial |
| `cli_commands` | 20.9% | Low | — |
| `routes.admin` | 20.5% | Medium | — |
| `services.translation` | 13.3% | Medium | — |
| `routes.ai_documents` | 11.1% | Medium | — |
| `routes.admin.utilities` | 7.8% | Low | — |

### Recommended Next Tests

| Priority | Package | Status | Remaining work |
|----------|---------|--------|----------------|
| P0 | `services.ai_fastpaths` | ✅ Done | Extend with end-to-end LLM integration tests |
| P0 | `services.upr` | ✅ Done | Add tests for `data_retrieval`, `focus_area_analysis` (full flow) |
| P1 | `services.ai_tools` | ✅ Partial | Registry tool execution contracts, indicator-bank mgmt tools |
| P1 | `services.validation.fdrs_matrix` | ✅ Partial | Population/reach rules, document-missing rules with DB fixtures |
| P1 | `services.ai_agent` | ✅ Partial | `AIAgentExecutor` integration with mocked LLM provider |
| P1 | `routes.admin.user_management` | ✅ Partial | Device kickout/remove, deletion preview JSON, create-user happy path |
| P2 | `routes.admin.system_admin` | ✅ Partial | Indicator bank, lookups, POST create-country happy path |
| P2 | `services.notification` | ✅ Partial | Dispatch logic, digest scheduling, `core.py` emitters |
| — | `services.translation` | Pending | Unit tests for translation service |
| — | `routes.ai_documents` | Pending | Integration tests for AI document routes |
| — | `cli_commands` | Pending | CLI smoke tests |
